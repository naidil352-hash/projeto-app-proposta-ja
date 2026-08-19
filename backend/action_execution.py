"""Controlled Action Execution Core with simulation-only adapters (Phase 3.5)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

ACTION_EXECUTOR_VERSION = "1.0.0"
EXECUTION_STATUSES = {
    "CREATED", "QUEUED", "RUNNING", "SIMULATED", "SUCCEEDED", "FAILED",
    "CANCELLED", "RETRY_PENDING", "EXPIRED", "BLOCKED",
}
EXECUTION_MODES = {"SIMULATION", "DRY_RUN", "LIVE"}
ALLOWED_EXECUTION_MODES = {"SIMULATION", "DRY_RUN"}
CHANNELS = {"WHATSAPP", "EMAIL", "PHONE", "IN_PERSON", "UNKNOWN"}
EXECUTABLE_ACTION_STATUSES = {"PENDING_APPROVAL", "APPROVED"}
CANCELLABLE_STATUSES = {"CREATED", "QUEUED", "RETRY_PENDING", "BLOCKED"}
DEFAULT_POLICY = {
    "mode": "SIMULATION",
    "requires_approval": True,
    "allow_external_side_effects": False,
    "max_attempts": 1,
    "timeout_seconds": 30,
}


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _canonical(value[key])
            for key in sorted(value)
            if key not in {"created_at", "updated_at", "started_at", "completed_at", "attempts"}
        }
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def validate_policy(mode: str, requested_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if mode not in ALLOWED_EXECUTION_MODES:
        raise ValueError("LIVE_MODE_FORBIDDEN")
    requested_policy = requested_policy or {}
    if requested_policy.get("allow_external_side_effects") is True:
        raise ValueError("EXTERNAL_SIDE_EFFECTS_FORBIDDEN")
    if requested_policy.get("requires_approval") is False:
        raise ValueError("APPROVAL_REQUIRED")
    policy = {
        **DEFAULT_POLICY,
        "mode": mode,
        "requires_approval": True,
        "allow_external_side_effects": False,
        "max_attempts": 1,
    }
    timeout = requested_policy.get("timeout_seconds", DEFAULT_POLICY["timeout_seconds"])
    if not isinstance(timeout, int) or timeout <= 0 or timeout > 300:
        raise ValueError("INVALID_TIMEOUT")
    policy["timeout_seconds"] = timeout
    return policy


def validate_execution_inputs(
    company_id: str,
    action_plan: dict[str, Any],
    action: dict[str, Any],
    opportunity: dict[str, Any],
    sales_insight: dict[str, Any],
    commercial_context: dict[str, Any],
) -> None:
    documents = [action_plan, opportunity, sales_insight, commercial_context]
    if any(document.get("company_id") != company_id for document in documents):
        raise ValueError("TENANT_MISMATCH")
    opportunity_id = action_plan.get("opportunity_id")
    if opportunity.get("id") != opportunity_id:
        raise ValueError("OPPORTUNITY_MISMATCH")
    if sales_insight.get("opportunity_id") != opportunity_id:
        raise ValueError("SALES_INSIGHT_MISMATCH")
    if commercial_context.get("opportunity_id") != opportunity_id:
        raise ValueError("CONTEXT_MISMATCH")
    if action_plan.get("sales_insight_id") != sales_insight.get("insight_id"):
        raise ValueError("STALE_INSIGHT")
    if action_plan.get("context_id") != commercial_context.get("context_id"):
        raise ValueError("STALE_CONTEXT")
    if sales_insight.get("context_id") != commercial_context.get("context_id"):
        raise ValueError("STALE_INSIGHT")
    if action_plan.get("status") != "APPROVED":
        raise ValueError(f"PLAN_NOT_EXECUTABLE:{action_plan.get('status')}")
    if action.get("action_id") not in {item.get("action_id") for item in action_plan.get("actions", [])}:
        raise ValueError("ACTION_NOT_IN_PLAN")
    if action.get("status") not in EXECUTABLE_ACTION_STATUSES:
        raise ValueError(f"ACTION_NOT_EXECUTABLE:{action.get('status')}")
    if action.get("channel") not in CHANNELS:
        raise ValueError("INVALID_CHANNEL")


def compute_execution_snapshot_hash(
    action_plan: dict[str, Any],
    action: dict[str, Any],
    mode: str,
    policy: dict[str, Any],
) -> str:
    payload = {
        "action_plan_id": action_plan.get("action_plan_id"),
        "action_plan_snapshot_hash": action_plan.get("source_snapshot_hash"),
        "action": _canonical(action),
        "mode": mode,
        "policy": _canonical(policy),
        "executor_version": ACTION_EXECUTOR_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_execution_job(
    company_id: str,
    action_plan: dict[str, Any],
    action: dict[str, Any],
    opportunity: dict[str, Any],
    sales_insight: dict[str, Any],
    commercial_context: dict[str, Any],
    mode: str = "SIMULATION",
    requested_policy: dict[str, Any] | None = None,
    expires_at: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    policy = validate_policy(mode, requested_policy)
    validate_execution_inputs(company_id, action_plan, action, opportunity, sales_insight, commercial_context)
    now = now or datetime.now(timezone.utc)
    if expires_at:
        expiration = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expiration <= now:
            raise ValueError("EXECUTION_EXPIRED")
    snapshot_hash = compute_execution_snapshot_hash(action_plan, action, mode, policy)
    job_id = "job-" + hashlib.sha256(
        f"{company_id}:{action_plan.get('action_plan_id')}:{action.get('action_id')}:{mode}:{ACTION_EXECUTOR_VERSION}:{snapshot_hash}".encode("utf-8")
    ).hexdigest()[:24]
    timestamp = now.isoformat()
    payload = {
        "action_type": action.get("type"),
        "channel": action.get("channel", "UNKNOWN"),
        "objective": action.get("objective"),
        "reason": action.get("reason"),
        "evidence": action.get("evidence", []),
        "context": {
            "opportunity_id": action_plan.get("opportunity_id"),
            "sales_insight_id": action_plan.get("sales_insight_id"),
            "context_id": action_plan.get("context_id"),
        },
    }
    return {
        "execution_job_id": job_id,
        "company_id": company_id,
        "action_plan_id": action_plan.get("action_plan_id"),
        "action_id": action.get("action_id"),
        "opportunity_id": action_plan.get("opportunity_id"),
        "status": "CREATED",
        "mode": mode,
        "channel": action.get("channel", "UNKNOWN"),
        "action_type": action.get("type"),
        "payload": payload,
        "policy": policy,
        "result": {},
        "attempts": 0,
        "executor_version": ACTION_EXECUTOR_VERSION,
        "source_snapshot_hash": snapshot_hash,
        "expires_at": expires_at,
        "created_at": timestamp,
        "updated_at": timestamp,
        "started_at": None,
        "completed_at": None,
    }


class CommunicationAdapter(ABC):
    @abstractmethod
    def validate(self, job: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def prepare(self, job: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def execute(self, prepared: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        raise NotImplementedError


class SimulationAdapter(CommunicationAdapter):
    name = "simulation"

    def validate(self, job: dict[str, Any]) -> None:
        if job.get("mode") not in ALLOWED_EXECUTION_MODES:
            raise ValueError("LIVE_MODE_FORBIDDEN")
        if job.get("policy", {}).get("allow_external_side_effects") is not False:
            raise ValueError("EXTERNAL_SIDE_EFFECTS_FORBIDDEN")
        if job.get("status") != "CREATED":
            raise ValueError(f"JOB_NOT_SIMULATABLE:{job.get('status')}")

    def prepare(self, job: dict[str, Any]) -> dict[str, Any]:
        self.validate(job)
        return {
            "execution_job_id": job.get("execution_job_id"),
            "mode": job.get("mode"),
            "channel": job.get("channel"),
            "action_type": job.get("action_type"),
            "payload": job.get("payload"),
            "external_side_effect": False,
        }

    def execute(self, prepared: dict[str, Any]) -> dict[str, Any]:
        return {
            "mode": prepared.get("mode"),
            "simulated": True,
            "external_side_effect": False,
            "channel": prepared.get("channel"),
            "action_type": prepared.get("action_type"),
            "result": "SIMULATED_SUCCESS",
            "status": "SIMULATED",
            "success": True,
            "adapter": self.name,
            "message": "Action simulated successfully",
        }

    def health_check(self) -> dict[str, Any]:
        return {"adapter": self.name, "healthy": True, "external_connectivity": False}


def simulate_execution_job(
    job: dict[str, Any],
    adapter: CommunicationAdapter | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if job.get("expires_at"):
        expiration = datetime.fromisoformat(str(job["expires_at"]).replace("Z", "+00:00"))
        if expiration <= now:
            return {**job, "status": "EXPIRED", "updated_at": now.isoformat(), "completed_at": now.isoformat()}
    if job.get("attempts", 0) >= job.get("policy", {}).get("max_attempts", 1):
        raise ValueError("MAX_ATTEMPTS_EXCEEDED")
    simulation_adapter = adapter or SimulationAdapter()
    prepared = simulation_adapter.prepare(job)
    result = simulation_adapter.execute(prepared)
    timestamp = now.isoformat()
    return {
        **job,
        "status": "SIMULATED",
        "result": result,
        "attempts": job.get("attempts", 0) + 1,
        "started_at": timestamp,
        "completed_at": timestamp,
        "updated_at": timestamp,
    }


def cancel_execution_job(job: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    if job.get("status") not in CANCELLABLE_STATUSES:
        raise ValueError(f"JOB_NOT_CANCELLABLE:{job.get('status')}")
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    return {**job, "status": "CANCELLED", "updated_at": timestamp, "completed_at": timestamp}
