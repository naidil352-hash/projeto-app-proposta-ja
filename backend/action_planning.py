"""Deterministic, advisory-only Action Planning Engine (Phase 3.4)."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from commercial_context import COMMERCIAL_CONTEXT_VERSION
from learning_engine import LEARNING_VERSION
from sales_intelligence import SALES_INTELLIGENCE_VERSION

ACTION_PLANNING_VERSION = "1.0.0"
PLAN_STATUSES = {"DRAFT", "PENDING_REVIEW", "APPROVED", "REJECTED", "EXPIRED", "SUPERSEDED", "EXECUTED", "FAILED"}
GENERATED_PLAN_STATUSES = {"DRAFT", "PENDING_REVIEW", "APPROVED", "REJECTED", "EXPIRED", "SUPERSEDED"}
ACTION_TYPES = {
    "FOLLOW_UP", "CONTACT_CLIENT", "REVIEW_PROPOSAL", "REVIEW_PRICE",
    "REQUEST_INFORMATION", "WAIT", "HUMAN_REVIEW", "NO_ACTION",
}
CHANNELS = {"WHATSAPP", "EMAIL", "PHONE", "IN_PERSON", "UNKNOWN"}
URGENCIES = {"IMMEDIATE", "TODAY", "THIS_WEEK", "NORMAL", "NONE"}
WINDOWS = {"IMMEDIATE", "TODAY", "WITHIN_24_HOURS", "WITHIN_3_DAYS", "THIS_WEEK", "NO_ACTION", "UNKNOWN"}
PLAN_RISKS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
APPROVAL_STATUSES = {"DRAFT", "PENDING_REVIEW"}

OBJECTIVES = {
    "FOLLOW_UP": "Obter uma atualização objetiva da oportunidade.",
    "CONTACT_CLIENT": "Obter uma atualização objetiva da oportunidade.",
    "REVIEW_PROPOSAL": "Verificar se a proposta permanece adequada ao cenário atual.",
    "REVIEW_PRICE": "Verificar o posicionamento de preço com base na evidência disponível.",
    "REQUEST_INFORMATION": "Obter a informação necessária para avançar a oportunidade.",
    "WAIT": "Aguardar o próximo sinal objetivo antes de uma nova intervenção.",
    "HUMAN_REVIEW": "Revisar os dados e a recomendação antes de qualquer decisão comercial.",
    "NO_ACTION": "Manter o plano sem ação comercial neste momento.",
}

ACTION_ORDER = {
    "REVIEW_PROPOSAL": 10,
    "REVIEW_PRICE": 20,
    "REQUEST_INFORMATION": 30,
    "HUMAN_REVIEW": 40,
    "CONTACT_CLIENT": 50,
    "FOLLOW_UP": 60,
    "WAIT": 70,
    "NO_ACTION": 80,
}


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value) if key not in {"calculation_timestamp", "created_at", "updated_at"}}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def compute_source_snapshot_hash(
    sales_insight: dict[str, Any],
    commercial_context: dict[str, Any],
) -> str:
    payload = {
        "sales_insight": _canonical(sales_insight),
        "context_id": commercial_context.get("context_id"),
        "context_snapshot_hash": commercial_context.get("source_snapshot_hash"),
        "context_version": commercial_context.get("snapshot_version", COMMERCIAL_CONTEXT_VERSION),
        "sales_intelligence_version": sales_insight.get("engine_version", SALES_INTELLIGENCE_VERSION),
        "commercial_context_version": COMMERCIAL_CONTEXT_VERSION,
        "knowledge_version": LEARNING_VERSION,
        "action_planning_version": ACTION_PLANNING_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_inputs(
    company_id: str,
    opportunity: dict[str, Any],
    sales_insight: dict[str, Any],
    commercial_context: dict[str, Any],
) -> None:
    if opportunity.get("company_id") != company_id:
        raise ValueError("TENANT_MISMATCH_OPPORTUNITY")
    if sales_insight.get("company_id") != company_id:
        raise ValueError("TENANT_MISMATCH_SALES_INSIGHT")
    if commercial_context.get("company_id") != company_id:
        raise ValueError("TENANT_MISMATCH_CONTEXT")
    opportunity_id = opportunity.get("id")
    if sales_insight.get("opportunity_id") != opportunity_id:
        raise ValueError("OPPORTUNITY_MISMATCH_SALES_INSIGHT")
    if commercial_context.get("opportunity_id") != opportunity_id:
        raise ValueError("OPPORTUNITY_MISMATCH_CONTEXT")
    if sales_insight.get("context_id") != commercial_context.get("context_id"):
        raise ValueError("STALE_INSIGHT")
    if sales_insight.get("context_version") != commercial_context.get("snapshot_version"):
        raise ValueError("STALE_INSIGHT")


def _insight_value(sales_insight: dict[str, Any], key: str, default: Any = None) -> Any:
    value = sales_insight.get("insight", {}).get(key, default)
    if isinstance(value, dict) and "state" in value:
        return value["state"]
    if isinstance(value, dict) and "level" in value:
        return value["level"]
    return value


def _risk(sales_insight: dict[str, Any]) -> str:
    value = _insight_value(sales_insight, "commercial_risk", "NONE")
    return value if value in PLAN_RISKS else "MEDIUM"


def _recommended_window(urgency: str, action_type: str) -> str:
    if action_type == "NO_ACTION":
        return "NO_ACTION"
    return {
        "IMMEDIATE": "IMMEDIATE",
        "TODAY": "WITHIN_24_HOURS",
        "THIS_WEEK": "WITHIN_3_DAYS",
        "NORMAL": "THIS_WEEK",
        "NONE": "UNKNOWN",
    }.get(urgency, "UNKNOWN")


def _has_conflict(sales_insight: dict[str, Any], commercial_context: dict[str, Any]) -> bool:
    values = [json.dumps(sales_insight, default=str).lower(), json.dumps(commercial_context, default=str).lower()]
    return any(marker in " ".join(values) for marker in ("conflict", "conflicted", "ambiguous"))


def _insufficient_evidence(sales_insight: dict[str, Any], commercial_context: dict[str, Any]) -> bool:
    context_data = commercial_context.get("context", {})
    return (
        sales_insight.get("confidence", 0) < 0.5
        or not sales_insight.get("evidence")
        or context_data.get("data_quality") == "INSUFFICIENT"
        or (
            not context_data.get("proposal")
            and any(item.get("action") == "REVIEW_PROPOSAL" for item in sales_insight.get("recommendations", []))
        )
    )


def _action_evidence(sales_insight: dict[str, Any], recommendation: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = recommendation.get("evidence") or sales_insight.get("evidence") or []
    return [
        {
            "source": item.get("source", "sales_intelligence"),
            "source_id": item.get("source_id") or sales_insight.get("insight_id"),
            "field": item.get("field", "recommendation"),
            "value": item.get("value"),
        }
        for item in evidence
    ]


def _reason(recommendation: dict[str, Any], sales_insight: dict[str, Any]) -> str:
    reason = recommendation.get("reason")
    if reason:
        return reason
    return f"Sales Intelligence recomendou {recommendation.get('action', 'NO_ACTION')}."


def _make_action(
    recommendation: dict[str, Any],
    sales_insight: dict[str, Any],
    sequence: int,
    depends_on: list[str],
) -> dict[str, Any]:
    action_type = recommendation["action"]
    action_id = "action-" + hashlib.sha256(
        f"{sales_insight.get('insight_id')}:{action_type}:{sequence}".encode("utf-8")
    ).hexdigest()[:24]
    channel = recommendation.get("channel", "UNKNOWN")
    if channel not in CHANNELS:
        channel = "UNKNOWN"
    priority = recommendation.get("priority") or sales_insight.get("priority", "P4_NONE")
    urgency = sales_insight.get("urgency", "NORMAL")
    if urgency not in URGENCIES:
        urgency = "NORMAL"
    action = {
        "action_id": action_id,
        "type": action_type,
        "channel": channel,
        "priority": priority,
        "urgency": urgency,
        "objective": OBJECTIVES[action_type],
        "reason": _reason(recommendation, sales_insight),
        "evidence": _action_evidence(sales_insight, recommendation),
        "confidence": round(float(recommendation.get("confidence", 0.0)), 4),
        "status": "PENDING_APPROVAL",
        "sequence": sequence,
        "depends_on": depends_on,
        "recommended_window": _recommended_window(urgency, action_type),
    }
    return action


def _deduplicate_recommendations(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for recommendation in recommendations:
        action_type = recommendation.get("action")
        if action_type in ACTION_TYPES and action_type not in selected:
            selected[action_type] = recommendation
    return sorted(selected.values(), key=lambda item: (ACTION_ORDER[item["action"]], item["action"]))


def build_action_plan(
    company_id: str,
    opportunity: dict[str, Any],
    sales_insight: dict[str, Any],
    commercial_context: dict[str, Any],
    knowledge_items: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    del knowledge_items
    validate_inputs(company_id, opportunity, sales_insight, commercial_context)
    now = now or datetime.now(timezone.utc)
    snapshot_hash = compute_source_snapshot_hash(sales_insight, commercial_context)
    risk = _risk(sales_insight)
    conflict = _has_conflict(sales_insight, commercial_context)
    insufficient = _insufficient_evidence(sales_insight, commercial_context)
    if conflict or insufficient:
        recommendations = [{
            "action": "HUMAN_REVIEW",
            "priority": sales_insight.get("priority", "P4_NONE"),
            "channel": "UNKNOWN",
            "reason": "Conflito ou insuficiência de evidências exige revisão humana antes de qualquer decisão.",
            "confidence": min(float(sales_insight.get("confidence", 0.0)), 0.5),
            "evidence": sales_insight.get("evidence", []),
        }]
    else:
        recommendations = _deduplicate_recommendations(sales_insight.get("recommendations", []))

    actions: list[dict[str, Any]] = []
    review_action_id: str | None = None
    for recommendation in recommendations:
        if recommendation["action"] == "NO_ACTION" and len(recommendations) > 1:
            continue
        depends_on = [review_action_id] if recommendation["action"] == "FOLLOW_UP" and review_action_id else []
        action = _make_action(recommendation, sales_insight, len(actions) + 1, depends_on)
        actions.append(action)
        if action["type"] in {"REVIEW_PROPOSAL", "REVIEW_PRICE"}:
            review_action_id = action["action_id"]

    if not actions:
        fallback = {"action": "NO_ACTION", "priority": "P4_NONE", "channel": "UNKNOWN", "reason": "Não há recomendação baseada em evidência suficiente.", "confidence": 0.0, "evidence": []}
        actions.append(_make_action(fallback, sales_insight, 1, []))

    action_plan_id = "plan-" + hashlib.sha256(
        f"{company_id}:{opportunity.get('id')}:{sales_insight.get('insight_id')}:{ACTION_PLANNING_VERSION}:{snapshot_hash}".encode("utf-8")
    ).hexdigest()[:24]
    urgency = sales_insight.get("urgency", "NORMAL")
    summary = "Plano de acompanhamento recomendado com base nos sinais objetivos disponíveis."
    if any(action["type"] == "FOLLOW_UP" for action in actions):
        summary = "Plano de acompanhamento recomendado devido ao estado de follow-up identificado."
    return {
        "action_plan_id": action_plan_id,
        "company_id": company_id,
        "opportunity_id": opportunity.get("id"),
        "sales_insight_id": sales_insight.get("insight_id"),
        "context_id": commercial_context.get("context_id"),
        "engine_version": ACTION_PLANNING_VERSION,
        "status": "DRAFT",
        "plan": {
            "summary": summary,
            "plan_risk": risk,
            "priority": sales_insight.get("priority", "P4_NONE"),
            "urgency": urgency if urgency in URGENCIES else "NORMAL",
            "recommended_window": actions[0]["recommended_window"],
            "commercial_context_version": COMMERCIAL_CONTEXT_VERSION,
            "sales_intelligence_version": sales_insight.get("engine_version", SALES_INTELLIGENCE_VERSION),
            "knowledge_version": LEARNING_VERSION,
            "action_planning_version": ACTION_PLANNING_VERSION,
        },
        "actions": actions,
        "evidence": sales_insight.get("evidence", []),
        "confidence": round(float(sales_insight.get("confidence", 0.0)), 4),
        "source_snapshot_hash": snapshot_hash,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
