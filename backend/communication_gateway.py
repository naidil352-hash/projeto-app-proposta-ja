"""Channel-independent, simulation-only Communication Gateway (Phase 3.6)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

COMMUNICATION_GATEWAY_VERSION = "1.0.0"
CHANNELS = {"WHATSAPP", "EMAIL", "PHONE", "SMS", "IN_PERSON", "UNKNOWN"}
ACTION_TYPES = {
    "FOLLOW_UP", "CONTACT_CLIENT", "REQUEST_INFORMATION", "REVIEW_PROPOSAL",
    "REVIEW_PRICE", "WAIT", "HUMAN_REVIEW", "NO_ACTION",
}
COMMUNICATION_ACTIONS = {"FOLLOW_UP", "CONTACT_CLIENT", "REQUEST_INFORMATION", "REVIEW_PROPOSAL", "REVIEW_PRICE"}
NON_COMMUNICATION_ACTIONS = {"WAIT", "HUMAN_REVIEW", "NO_ACTION"}
GATEWAY_STATES = {"RECEIVED", "VALIDATED", "PREPARED", "SIMULATED", "BLOCKED", "FAILED", "REJECTED"}
ALLOWED_MODES = {"SIMULATION", "DRY_RUN"}
CANCELLABLE_STATES = {"RECEIVED", "VALIDATED", "PREPARED", "BLOCKED"}


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value) if key not in {"created_at", "updated_at"}}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def communication_request_hash(
    company_id: str,
    execution_job_id: str,
    channel: str,
    action_type: str,
    recipient: dict[str, Any],
    content: dict[str, Any],
    mode: str,
) -> str:
    payload = {
        "company_id": company_id,
        "execution_job_id": execution_job_id,
        "channel": channel,
        "action_type": action_type,
        "recipient": _canonical(recipient),
        "content": _canonical(content),
        "gateway_version": COMMUNICATION_GATEWAY_VERSION,
        "mode": mode,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_gateway_documents(
    company_id: str,
    execution_job: dict[str, Any],
    action_plan: dict[str, Any],
    opportunity: dict[str, Any],
    client: dict[str, Any] | None,
) -> None:
    if any(document.get("company_id") != company_id for document in [execution_job, action_plan, opportunity]):
        raise ValueError("TENANT_MISMATCH")
    if client and client.get("company_id") != company_id:
        raise ValueError("TENANT_MISMATCH_CLIENT")
    if execution_job.get("action_plan_id") != action_plan.get("action_plan_id"):
        raise ValueError("ACTION_PLAN_MISMATCH")
    if execution_job.get("opportunity_id") != opportunity.get("id"):
        raise ValueError("OPPORTUNITY_MISMATCH")
    if action_plan.get("opportunity_id") != opportunity.get("id"):
        raise ValueError("OPPORTUNITY_MISMATCH")
    if execution_job.get("action_id") not in {item.get("action_id") for item in action_plan.get("actions", [])}:
        raise ValueError("ACTION_NOT_IN_PLAN")
    if action_plan.get("status") != "APPROVED":
        raise ValueError("ACTION_PLAN_NOT_APPROVED")
    required = ["execution_job_id", "action_plan_id", "action_id", "opportunity_id", "channel", "action_type", "mode", "policy"]
    missing = [field for field in required if execution_job.get(field) in (None, "")]
    if missing:
        raise ValueError("MISSING_REQUIRED_FIELDS:" + ",".join(missing))


def _recipient(client: dict[str, Any] | None) -> dict[str, Any]:
    client = client or {}
    return {
        "client_id": client.get("id"),
        "name": client.get("name"),
        "phone": client.get("phone") or None,
        "email": client.get("email") or None,
    }


def _content() -> dict[str, Any]:
    return {"subject": None, "body": None, "template_id": None, "variables": {}}


def _blocking_reason(channel: str, action_type: str, recipient: dict[str, Any], mode: str, policy: dict[str, Any], job_status: str) -> tuple[str, str | None]:
    if job_status in {"CANCELLED", "EXPIRED", "BLOCKED", "FAILED"}:
        return "BLOCKED", "EXECUTION_JOB_NOT_COMMUNICABLE"
    if mode == "LIVE":
        return "REJECTED", "LIVE_MODE_NOT_AVAILABLE"
    if mode not in ALLOWED_MODES:
        return "REJECTED", "INVALID_MODE"
    if policy.get("allow_external_side_effects") is not False:
        return "REJECTED", "EXTERNAL_SIDE_EFFECTS_FORBIDDEN"
    if action_type not in ACTION_TYPES:
        return "REJECTED", "INVALID_ACTION_TYPE"
    if action_type in NON_COMMUNICATION_ACTIONS:
        return "BLOCKED", "NOT_COMMUNICATION_ACTION"
    if channel not in CHANNELS or channel == "UNKNOWN":
        return "BLOCKED", "UNKNOWN_CHANNEL"
    if channel in {"WHATSAPP", "PHONE", "SMS"} and not recipient.get("phone"):
        return "BLOCKED", "MISSING_RECIPIENT_CONTACT"
    if channel == "EMAIL" and not recipient.get("email"):
        return "BLOCKED", "MISSING_RECIPIENT_CONTACT"
    return "PREPARED", None


def build_communication_request(
    company_id: str,
    execution_job: dict[str, Any],
    action_plan: dict[str, Any],
    opportunity: dict[str, Any],
    client: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    validate_gateway_documents(company_id, execution_job, action_plan, opportunity, client)
    mode = str(execution_job.get("mode")).upper()
    channel = str(execution_job.get("channel")).upper()
    action_type = str(execution_job.get("action_type")).upper()
    policy = {
        **execution_job.get("policy", {}),
        "allow_external_side_effects": execution_job.get("policy", {}).get("allow_external_side_effects"),
    }
    recipient = _recipient(client)
    content = _content()
    status, reason = _blocking_reason(channel, action_type, recipient, mode, policy, execution_job.get("status"))
    fingerprint = communication_request_hash(
        company_id, execution_job["execution_job_id"], channel, action_type, recipient, content, mode
    )
    request_id = "comm-" + hashlib.sha256(
        f"{company_id}:{execution_job['execution_job_id']}:{fingerprint}:{COMMUNICATION_GATEWAY_VERSION}".encode("utf-8")
    ).hexdigest()[:24]
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    adapter = None
    if status == "PREPARED":
        adapter = CommunicationAdapterFactory.create(channel, mode).name
    return {
        "request_id": request_id,
        "company_id": company_id,
        "execution_job_id": execution_job["execution_job_id"],
        "action_plan_id": execution_job["action_plan_id"],
        "action_id": execution_job["action_id"],
        "opportunity_id": execution_job["opportunity_id"],
        "channel": channel,
        "action_type": action_type,
        "recipient": recipient,
        "content": content,
        "context": execution_job.get("payload", {}).get("context", {}),
        "policy": policy,
        "mode": mode,
        "status": status,
        "reason": reason,
        "communication_request_hash": fingerprint,
        "gateway_version": COMMUNICATION_GATEWAY_VERSION,
        "adapter": adapter,
        "result": {},
        "created_at": timestamp,
        "updated_at": timestamp,
    }


class CommunicationAdapter(ABC):
    name = "simulation"
    channel = "UNKNOWN"

    @abstractmethod
    def validate(self, request: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def prepare(self, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        raise NotImplementedError


class SimulationCommunicationAdapter(CommunicationAdapter):
    name = "simulation"

    def validate(self, request: dict[str, Any]) -> None:
        if request.get("mode") == "LIVE":
            raise ValueError("LIVE_MODE_NOT_AVAILABLE")
        if request.get("mode") not in ALLOWED_MODES:
            raise ValueError("INVALID_MODE")
        if request.get("policy", {}).get("allow_external_side_effects") is not False:
            raise ValueError("EXTERNAL_SIDE_EFFECTS_FORBIDDEN")
        if request.get("status") != "PREPARED":
            raise ValueError(f"REQUEST_NOT_SIMULATABLE:{request.get('status')}")
        if request.get("channel") != self.channel:
            raise ValueError("ADAPTER_CHANNEL_MISMATCH")
        if request.get("content", {}).get("body") is not None:
            raise ValueError("MESSAGE_CONTENT_NOT_ALLOWED")

    def prepare(self, request: dict[str, Any]) -> dict[str, Any]:
        self.validate(request)
        return _canonical(request)

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        prepared = self.prepare(request)
        return {
            "request_id": prepared["request_id"],
            "status": "SIMULATED",
            "channel": prepared["channel"],
            "adapter": self.name,
            "success": True,
            "external_side_effect": False,
            "delivered": False,
            "sent": False,
            "prepared": True,
            "details": {"simulation": True, "network_access": False},
            "gateway_version": COMMUNICATION_GATEWAY_VERSION,
        }

    def health_check(self) -> dict[str, Any]:
        return {"healthy": True, "adapter": self.name, "channel": self.channel, "external_connectivity": False}


class WhatsAppAdapter(SimulationCommunicationAdapter):
    name = "whatsapp_simulation"
    channel = "WHATSAPP"


class EmailAdapter(SimulationCommunicationAdapter):
    name = "email_simulation"
    channel = "EMAIL"


class PhoneAdapter(SimulationCommunicationAdapter):
    name = "phone_simulation"
    channel = "PHONE"


class SmsAdapter(SimulationCommunicationAdapter):
    name = "sms_simulation"
    channel = "SMS"


class InPersonAdapter(SimulationCommunicationAdapter):
    name = "in_person_simulation"
    channel = "IN_PERSON"


class CommunicationAdapterFactory:
    ADAPTERS = {
        "WHATSAPP": WhatsAppAdapter,
        "EMAIL": EmailAdapter,
        "PHONE": PhoneAdapter,
        "SMS": SmsAdapter,
        "IN_PERSON": InPersonAdapter,
    }

    @classmethod
    def create(cls, channel: str, mode: str) -> CommunicationAdapter:
        if mode == "LIVE":
            raise ValueError("LIVE_MODE_NOT_AVAILABLE")
        if mode not in ALLOWED_MODES:
            raise ValueError("INVALID_MODE")
        adapter_type = cls.ADAPTERS.get(channel)
        if not adapter_type:
            raise ValueError("UNKNOWN_CHANNEL")
        return adapter_type()


def simulate_communication_request(request: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    if request.get("mode") == "DRY_RUN":
        return {
            **request,
            "status": "PREPARED",
            "result": {
                "request_id": request.get("request_id"), "status": "PREPARED", "channel": request.get("channel"),
                "adapter": request.get("adapter"), "success": True, "external_side_effect": False,
                "delivered": False, "sent": False, "prepared": True, "details": {"dry_run": True},
                "gateway_version": COMMUNICATION_GATEWAY_VERSION,
            },
            "updated_at": (now or datetime.now(timezone.utc)).isoformat(),
        }
    adapter = CommunicationAdapterFactory.create(request.get("channel"), request.get("mode"))
    result = adapter.execute(request)
    return {
        **request,
        "status": "SIMULATED",
        "adapter": adapter.name,
        "result": result,
        "updated_at": (now or datetime.now(timezone.utc)).isoformat(),
    }


def cancel_communication_request(request: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    if request.get("status") not in CANCELLABLE_STATES:
        raise ValueError(f"COMMUNICATION_REQUEST_NOT_CANCELLABLE:{request.get('status')}")
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    return {
        **request,
        "status": "REJECTED",
        "reason": "CANCELLED_BY_USER",
        "updated_at": timestamp,
    }
