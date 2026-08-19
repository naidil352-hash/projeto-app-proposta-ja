"""Deterministic, offline Message Intelligence Engine (Phase 3.7)."""
from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import json
from typing import Any

MESSAGE_INTELLIGENCE_VERSION = "1.0.0"
MESSAGE_OBJECTIVES = {
    "FOLLOW_UP", "REACTIVATE", "REQUEST_INFORMATION", "HANDLE_OBJECTION",
    "REVIEW_PROPOSAL", "REVIEW_PRICE", "CONFIRM_NEXT_STEP", "WAIT",
    "HUMAN_REVIEW", "NO_ACTION", "UNKNOWN",
}
STRATEGIES = {
    "GENTLE_REACTIVATION", "DIRECT_FOLLOW_UP", "VALUE_REINFORCEMENT",
    "QUESTION_BASED", "INFORMATION_REQUEST", "PRICE_REVIEW",
    "NEXT_STEP_CONFIRMATION", "HUMAN_HANDOFF", "NO_COMMUNICATION", "UNKNOWN",
}
TONES = {"PROFESSIONAL", "FRIENDLY", "DIRECT", "CONSULTATIVE", "CONCISE", "FORMAL", "UNKNOWN"}
EVIDENCE_TYPES = {"FACT", "DERIVED", "INFERENCE", "UNKNOWN"}
DRAFT_STATUSES = {"CREATED", "READY_FOR_REVIEW", "APPROVED", "REJECTED", "SUPERSEDED", "EXPIRED", "BLOCKED", "SIMULATED"}
WARNINGS = {
    "MISSING_CONTEXT", "LOW_CONFIDENCE", "STALE_CONTEXT", "MISSING_RECIPIENT",
    "MISSING_PROPOSAL", "MISSING_PRICE", "MISSING_OBJECTIVE", "UNSUPPORTED_CLAIM",
    "NO_COMMUNICATION_ACTION", "HUMAN_REVIEW_REQUIRED",
}
CHANNEL_LENGTH_LIMITS = {"WHATSAPP": 1000, "SMS": 300, "EMAIL": 5000, "PHONE": 0, "IN_PERSON": 0, "UNKNOWN": 0}
POLICY = {
    "requires_human_approval": True,
    "allow_external_side_effects": False,
    "allow_live_channel": False,
    "max_message_length": 1000,
    "allow_assumptions": True,
    "allow_unverified_claims": False,
}
TEMPLATE_VERSION = "1.0.0"
TEMPLATES = {
    "FOLLOW_UP_GENTLE_V1": {
        "opening": "Olá{client_name_suffix}.",
        "body_with_proposal": "Gostaria de saber se conseguiu avaliar nossa proposta{proposal_number_suffix}.",
        "body_without_proposal": "Gostaria de retomar nosso contato sobre esta oportunidade.",
        "call_to_action": "Pode nos informar se há alguma atualização?",
        "closing": "Fico à disposição.",
    },
    "FOLLOW_UP_DIRECT_V1": {
        "opening": "Olá{client_name_suffix}.",
        "body_with_proposal": "Retomo o contato sobre nossa proposta{proposal_number_suffix}.",
        "body_without_proposal": "Retomo o contato sobre esta oportunidade.",
        "call_to_action": "Podemos confirmar o próximo passo?",
        "closing": "Fico à disposição.",
    },
    "REQUEST_INFORMATION_V1": {
        "opening": "Olá{client_name_suffix}.",
        "body_with_proposal": "Para avançarmos com a proposta{proposal_number_suffix}, precisamos confirmar uma informação.",
        "body_without_proposal": "Para avançarmos com esta oportunidade, precisamos confirmar uma informação.",
        "call_to_action": "Pode nos ajudar com essa confirmação?",
        "closing": "Agradeço desde já.",
    },
    "VALUE_REINFORCEMENT_V1": {
        "opening": "Olá{client_name_suffix}.",
        "body_with_proposal": "Gostaria de revisar os pontos registrados em nossa proposta{proposal_number_suffix}.",
        "body_without_proposal": "Gostaria de revisar os pontos registrados para esta oportunidade.",
        "call_to_action": "Podemos verificar juntos se ela permanece adequada?",
        "closing": "Fico à disposição.",
    },
    "PRICE_REVIEW_V1": {
        "opening": "Olá{client_name_suffix}.",
        "body_with_proposal": "Gostaria de revisar os aspectos de preço registrados na proposta{proposal_number_suffix}.",
        "body_without_proposal": "Gostaria de revisar os aspectos de preço registrados para esta oportunidade.",
        "call_to_action": "Podemos conversar sobre os pontos já registrados?",
        "closing": "Fico à disposição.",
    },
    "HUMAN_HANDOFF_V1": {"opening": None, "body_with_proposal": None, "body_without_proposal": None, "call_to_action": None, "closing": None},
}


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _canonical(value[key])
            for key in sorted(value)
            if key not in {"created_at", "updated_at", "calculation_timestamp", "edited_at"}
        }
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def compute_source_snapshot_hash(
    company_id: str,
    opportunity: dict[str, Any],
    commercial_context: dict[str, Any],
    sales_intelligence: dict[str, Any],
    action_plan: dict[str, Any],
    communication_request: dict[str, Any],
) -> str:
    payload = {
        "company_id": company_id,
        "opportunity_id": opportunity.get("id"),
        "action_plan_id": action_plan.get("action_plan_id"),
        "action_id": communication_request.get("action_id"),
        "commercial_context": _canonical(commercial_context),
        "sales_intelligence": _canonical(sales_intelligence),
        "action_plan": _canonical(action_plan),
        "communication_request": _canonical(communication_request),
        "message_intelligence_version": MESSAGE_INTELLIGENCE_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_inputs(
    company_id: str,
    execution_job: dict[str, Any],
    communication_request: dict[str, Any],
    action_plan: dict[str, Any],
    opportunity: dict[str, Any],
    client: dict[str, Any] | None,
    sales_intelligence: dict[str, Any],
    commercial_context: dict[str, Any],
) -> list[str]:
    documents = [execution_job, communication_request, action_plan, opportunity, sales_intelligence, commercial_context]
    if any(document.get("company_id") != company_id for document in documents):
        raise ValueError("TENANT_MISMATCH")
    if client and client.get("company_id") != company_id:
        raise ValueError("TENANT_MISMATCH_CLIENT")
    opportunity_id = opportunity.get("id")
    if any(document.get("opportunity_id") != opportunity_id for document in [execution_job, communication_request, action_plan, sales_intelligence, commercial_context]):
        raise ValueError("OPPORTUNITY_MISMATCH")
    if communication_request.get("execution_job_id") != execution_job.get("execution_job_id"):
        raise ValueError("EXECUTION_JOB_MISMATCH")
    if communication_request.get("action_plan_id") != action_plan.get("action_plan_id"):
        raise ValueError("ACTION_PLAN_MISMATCH")
    if communication_request.get("action_id") != execution_job.get("action_id"):
        raise ValueError("ACTION_MISMATCH")
    if action_plan.get("sales_insight_id") != sales_intelligence.get("insight_id"):
        return ["STALE_CONTEXT"]
    if action_plan.get("context_id") != commercial_context.get("context_id"):
        return ["STALE_CONTEXT"]
    if sales_intelligence.get("context_id") != commercial_context.get("context_id"):
        return ["STALE_CONTEXT"]
    return []


def _objective(action_type: str) -> str:
    return {
        "FOLLOW_UP": "FOLLOW_UP",
        "CONTACT_CLIENT": "CONFIRM_NEXT_STEP",
        "REQUEST_INFORMATION": "REQUEST_INFORMATION",
        "REVIEW_PROPOSAL": "REVIEW_PROPOSAL",
        "REVIEW_PRICE": "REVIEW_PRICE",
        "WAIT": "WAIT",
        "HUMAN_REVIEW": "HUMAN_REVIEW",
        "NO_ACTION": "NO_ACTION",
    }.get(action_type, "UNKNOWN")


def _days_since_last_contact(commercial_context: dict[str, Any]) -> int | None:
    return commercial_context.get("context", {}).get("opportunity", {}).get("days_since_last_activity")


def _has_price_evidence(sales_intelligence: dict[str, Any]) -> bool:
    price = sales_intelligence.get("insight", {}).get("price_signal", {})
    return price.get("status") == "PRICE_REVIEW_POSSIBLE" and price.get("type") in {"FACT", "DERIVED"}


def _strategy(objective: str, commercial_context: dict[str, Any], sales_intelligence: dict[str, Any]) -> str:
    if objective in {"WAIT", "NO_ACTION"}:
        return "NO_COMMUNICATION"
    if objective == "HUMAN_REVIEW":
        return "HUMAN_HANDOFF"
    if objective == "REQUEST_INFORMATION":
        return "INFORMATION_REQUEST"
    if objective == "REVIEW_PRICE":
        return "PRICE_REVIEW" if _has_price_evidence(sales_intelligence) else "HUMAN_HANDOFF"
    if objective == "REVIEW_PROPOSAL":
        return "VALUE_REINFORCEMENT"
    if objective == "CONFIRM_NEXT_STEP":
        return "NEXT_STEP_CONFIRMATION"
    if objective == "FOLLOW_UP":
        days = _days_since_last_contact(commercial_context)
        return "GENTLE_REACTIVATION" if days is None or days >= 7 else "DIRECT_FOLLOW_UP"
    return "UNKNOWN"


def _tone(channel: str, strategy: str) -> str:
    if strategy in {"HUMAN_HANDOFF", "NO_COMMUNICATION", "UNKNOWN"}:
        return "UNKNOWN"
    if channel == "SMS":
        return "CONCISE"
    if strategy in {"PRICE_REVIEW", "VALUE_REINFORCEMENT"}:
        return "CONSULTATIVE"
    if strategy in {"DIRECT_FOLLOW_UP", "NEXT_STEP_CONFIRMATION"}:
        return "DIRECT"
    return "PROFESSIONAL"


def _template_id(strategy: str) -> str:
    return {
        "GENTLE_REACTIVATION": "FOLLOW_UP_GENTLE_V1",
        "DIRECT_FOLLOW_UP": "FOLLOW_UP_DIRECT_V1",
        "INFORMATION_REQUEST": "REQUEST_INFORMATION_V1",
        "VALUE_REINFORCEMENT": "VALUE_REINFORCEMENT_V1",
        "PRICE_REVIEW": "PRICE_REVIEW_V1",
        "NEXT_STEP_CONFIRMATION": "FOLLOW_UP_DIRECT_V1",
        "HUMAN_HANDOFF": "HUMAN_HANDOFF_V1",
        "NO_COMMUNICATION": "HUMAN_HANDOFF_V1",
        "UNKNOWN": "HUMAN_HANDOFF_V1",
    }[strategy]


def _proposal_data(commercial_context: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    context = commercial_context.get("context", {})
    return context.get("proposal"), context.get("products") or []


def _variables(client: dict[str, Any] | None, commercial_context: dict[str, Any], action_plan: dict[str, Any]) -> dict[str, Any]:
    proposal, products = _proposal_data(commercial_context)
    seller = commercial_context.get("context", {}).get("seller") or {}
    return {
        "client_name": (client or {}).get("name"),
        "seller_name": seller.get("seller_name"),
        "company_name": None,
        "proposal_number": (proposal or {}).get("proposal_id"),
        "proposal_value": (proposal or {}).get("proposal_value"),
        "days_since_last_contact": _days_since_last_contact(commercial_context),
        "last_contact_date": None,
        "product_description": products[0].get("description") if products else None,
        "next_step": None,
        "contact_reason": next((item.get("reason") for item in action_plan.get("actions", []) if item.get("action_id")), None),
    }


def _compose(template_id: str, channel: str, variables: dict[str, Any], has_proposal: bool) -> dict[str, Any]:
    if channel in {"PHONE", "IN_PERSON"}:
        return {"subject": None, "opening": None, "body": None, "call_to_action": None, "closing": None}
    template = TEMPLATES[template_id]
    name_suffix = f", {variables['client_name']}" if variables.get("client_name") else ""
    proposal_suffix = f" {variables['proposal_number']}" if variables.get("proposal_number") else ""
    format_values = {"client_name_suffix": name_suffix, "proposal_number_suffix": proposal_suffix}
    body_key = "body_with_proposal" if has_proposal else "body_without_proposal"
    content = {
        "subject": None,
        "opening": template["opening"].format(**format_values) if template["opening"] else None,
        "body": template[body_key].format(**format_values) if template[body_key] else None,
        "call_to_action": template["call_to_action"].format(**format_values) if template["call_to_action"] else None,
        "closing": template["closing"].format(**format_values) if template["closing"] else None,
    }
    if channel == "EMAIL":
        content["subject"] = "Acompanhamento comercial"
    return content


def _evidence(commercial_context: dict[str, Any], sales_intelligence: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    days = _days_since_last_contact(commercial_context)
    if days is not None:
        evidence.append({"type": "FACT", "source": "commercial_context", "field": "days_since_last_contact", "value": days, "description": f"{days} dia(s) desde a última atividade registrada"})
    proposal, products = _proposal_data(commercial_context)
    if proposal:
        evidence.append({"type": "FACT", "source": "commercial_context", "field": "proposal_id", "value": proposal.get("proposal_id"), "description": "Proposta registrada no contexto"})
    if products:
        evidence.append({"type": "FACT", "source": "commercial_context", "field": "product_description", "value": products[0].get("description"), "description": "Produto registrado no contexto"})
    for item in sales_intelligence.get("evidence", []):
        evidence.append({
            "type": "DERIVED" if item.get("source") == "company_knowledge" else "FACT",
            "source": item.get("source", "sales_intelligence"), "field": item.get("field"),
            "value": item.get("value"), "description": item.get("calculation") or "Evidência da análise comercial",
        })
    return evidence


def _warnings(
    communication_request: dict[str, Any], commercial_context: dict[str, Any], sales_intelligence: dict[str, Any],
    objective: str, strategy: str, recipient: dict[str, Any], stale_warnings: list[str],
) -> list[str]:
    values = list(stale_warnings)
    if communication_request.get("status") in {"BLOCKED", "REJECTED"}:
        values.append("NO_COMMUNICATION_ACTION" if communication_request.get("reason") == "NOT_COMMUNICATION_ACTION" else "MISSING_CONTEXT")
    if communication_request.get("mode") == "LIVE" or communication_request.get("policy", {}).get("allow_external_side_effects") is not False:
        values.append("HUMAN_REVIEW_REQUIRED")
    if not recipient.get("name"):
        values.append("MISSING_RECIPIENT")
    proposal, _ = _proposal_data(commercial_context)
    if not proposal:
        values.append("MISSING_PROPOSAL")
    elif proposal.get("proposal_value") is None:
        values.append("MISSING_PRICE")
    if objective == "UNKNOWN":
        values.append("MISSING_OBJECTIVE")
    if strategy == "HUMAN_HANDOFF" or sales_intelligence.get("confidence", 0) < 0.5:
        values.extend(["LOW_CONFIDENCE", "HUMAN_REVIEW_REQUIRED"])
    if commercial_context.get("context", {}).get("data_quality") == "INSUFFICIENT":
        values.extend(["MISSING_CONTEXT", "HUMAN_REVIEW_REQUIRED"])
    return sorted(set(value for value in values if value in WARNINGS))


def _quality(content: dict[str, Any], evidence: list[dict[str, Any]], warnings: list[str], objective: str) -> dict[str, float]:
    has_content = bool(content.get("body") or content.get("call_to_action"))
    clarity = 0.9 if has_content else 0.2
    relevance = 0.9 if objective not in {"UNKNOWN", "NO_ACTION", "WAIT"} else 0.3
    evidence_support = min(1.0, 0.35 + len(evidence) * 0.15) if evidence else 0.1
    specificity = 0.7 if evidence else 0.3
    safety = 1.0 if "UNSUPPORTED_CLAIM" not in warnings else 0.2
    actionability = 0.9 if content.get("call_to_action") else 0.2
    scores = {"clarity": clarity, "relevance": relevance, "evidence_support": round(evidence_support, 4), "specificity": specificity, "safety": safety, "actionability": actionability}
    scores["overall_quality"] = round(sum(scores.values()) / len(scores), 4)
    return scores


class MessageGenerationProvider(ABC):
    @abstractmethod
    def generate(self, template_id: str, channel: str, variables: dict[str, Any], has_proposal: bool) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def validate(self, content: dict[str, Any], channel: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        raise NotImplementedError


class DeterministicMessageProvider(MessageGenerationProvider):
    name = "DETERMINISTIC"

    def generate(self, template_id: str, channel: str, variables: dict[str, Any], has_proposal: bool) -> dict[str, Any]:
        content = _compose(template_id, channel, variables, has_proposal)
        self.validate(content, channel)
        return content

    def validate(self, content: dict[str, Any], channel: str) -> None:
        if channel not in CHANNEL_LENGTH_LIMITS:
            raise ValueError("UNSUPPORTED_CHANNEL")
        if channel in {"PHONE", "IN_PERSON"} and content.get("body") is not None:
            raise ValueError("BODY_NOT_ALLOWED_FOR_CHANNEL")
        length = sum(len(str(value)) for value in content.values() if value)
        if length > CHANNEL_LENGTH_LIMITS[channel]:
            raise ValueError("MESSAGE_LENGTH_EXCEEDED")

    def health_check(self) -> dict[str, Any]:
        return {"provider": self.name, "healthy": True, "network_access": False, "llm": False}


class MessageProviderFactory:
    @staticmethod
    def create(provider: str) -> MessageGenerationProvider:
        if provider == "LLM":
            raise ValueError("LLM_PROVIDER_NOT_AVAILABLE")
        if provider != "DETERMINISTIC":
            raise ValueError("UNKNOWN_MESSAGE_PROVIDER")
        return DeterministicMessageProvider()


def build_message_draft(
    company_id: str,
    execution_job: dict[str, Any],
    communication_request: dict[str, Any],
    action_plan: dict[str, Any],
    opportunity: dict[str, Any],
    client: dict[str, Any] | None,
    proposal: dict[str, Any] | None,
    sales_intelligence: dict[str, Any],
    commercial_context: dict[str, Any],
    provider_name: str = "DETERMINISTIC",
) -> dict[str, Any]:
    del proposal
    stale_warnings = validate_inputs(company_id, execution_job, communication_request, action_plan, opportunity, client, sales_intelligence, commercial_context)
    action_type = communication_request.get("action_type", "UNKNOWN")
    objective = _objective(action_type)
    strategy = _strategy(objective, commercial_context, sales_intelligence)
    tone = _tone(communication_request.get("channel", "UNKNOWN"), strategy)
    recipient = {
        "client_id": (client or {}).get("id"), "name": (client or {}).get("name"),
        "phone": (client or {}).get("phone") or None, "email": (client or {}).get("email") or None,
    }
    warning_list = _warnings(communication_request, commercial_context, sales_intelligence, objective, strategy, recipient, stale_warnings)
    blocked = bool(stale_warnings) or action_plan.get("status") == "SUPERSEDED" or communication_request.get("status") in {"BLOCKED", "REJECTED"}
    blocked = blocked or communication_request.get("mode") == "LIVE" or communication_request.get("policy", {}).get("allow_external_side_effects") is not False
    if objective in {"WAIT", "HUMAN_REVIEW", "NO_ACTION", "UNKNOWN"}:
        blocked = True
        warning_list = sorted(set(warning_list + ["NO_COMMUNICATION_ACTION", "HUMAN_REVIEW_REQUIRED"]))
    if objective == "REVIEW_PRICE" and not _has_price_evidence(sales_intelligence):
        blocked = True
        warning_list = sorted(set(warning_list + ["MISSING_PRICE", "HUMAN_REVIEW_REQUIRED"]))
    template_id = _template_id(strategy)
    variables = _variables(client, commercial_context, action_plan)
    proposal_context, _ = _proposal_data(commercial_context)
    provider = MessageProviderFactory.create(provider_name)
    content = {"subject": None, "opening": None, "body": None, "call_to_action": None, "closing": None}
    if not blocked:
        content = provider.generate(template_id, communication_request.get("channel", "UNKNOWN"), variables, proposal_context is not None)
    evidence = _evidence(commercial_context, sales_intelligence)
    quality = _quality(content, evidence, warning_list, objective)
    confidence = round(quality["overall_quality"] * (0.75 if warning_list else 1.0), 4)
    if confidence < 0.5 and "LOW_CONFIDENCE" not in warning_list:
        warning_list = sorted(set(warning_list + ["LOW_CONFIDENCE", "HUMAN_REVIEW_REQUIRED"]))
    snapshot_hash = compute_source_snapshot_hash(company_id, opportunity, commercial_context, sales_intelligence, action_plan, communication_request)
    draft_id = "draft-" + hashlib.sha256(
        f"{company_id}:{communication_request.get('request_id')}:{MESSAGE_INTELLIGENCE_VERSION}:{snapshot_hash}".encode("utf-8")
    ).hexdigest()[:24]
    policy = {**POLICY, "max_message_length": CHANNEL_LENGTH_LIMITS.get(communication_request.get("channel"), 0)}
    return {
        "message_draft_id": draft_id,
        "company_id": company_id,
        "execution_job_id": execution_job.get("execution_job_id"),
        "communication_request_id": communication_request.get("request_id"),
        "action_plan_id": action_plan.get("action_plan_id"),
        "action_id": communication_request.get("action_id"),
        "opportunity_id": opportunity.get("id"),
        "channel": communication_request.get("channel"),
        "action_type": action_type,
        "objective": objective,
        "strategy": strategy,
        "tone": tone,
        "recipient": recipient,
        "content": content,
        "evidence": evidence,
        "confidence": confidence,
        "message_confidence": confidence,
        "message_quality": quality,
        "assumptions": [],
        "warnings": warning_list,
        "policy": policy,
        "source_snapshot_hash": snapshot_hash,
        "message_intelligence_version": MESSAGE_INTELLIGENCE_VERSION,
        "template_id": template_id,
        "template_version": TEMPLATE_VERSION,
        "provider": provider.name,
        "status": "BLOCKED" if blocked else "READY_FOR_REVIEW",
        "original_content": content,
        "edited_content": None,
        "edit_history": [],
        "human_edited": False,
        "human_approved": False,
        "human_rejected": False,
        "edit_delta": None,
        "result": None,
    }
