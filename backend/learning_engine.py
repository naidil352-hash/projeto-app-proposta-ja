"""Deterministic, event-sourced company learning memory.

Knowledge is a projection of immutable learning events and is advisory-only.
It never changes mappings, records, or commercial entities.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import math
from typing import Any, Iterable

LEARNING_VERSION = "1.0.0"
EVENT_TYPES = {
    "MAPPING_CONFIRMED", "MAPPING_REJECTED", "MAPPING_MODIFIED",
    "TEMPLATE_CREATED", "TEMPLATE_REUSED", "TEMPLATE_CORRECTED",
    "APPLICATION_COMPLETED", "APPLICATION_PARTIAL", "APPLICATION_FAILED",
    "USER_CORRECTION", "PATTERN_CONFIRMED", "PATTERN_REJECTED", "PATTERN_EXPIRED",
    "POSITIVE_FEEDBACK", "NEGATIVE_FEEDBACK", "CORRECTION_FEEDBACK",
    "POSITIVE_USAGE_SIGNAL", "CORRECTION_SIGNAL", "KNOWLEDGE_DISABLED", "KNOWLEDGE_REACTIVATED",
}
KNOWLEDGE_STATES = {"ACTIVE", "CONFLICTED", "WEAK", "EXPIRED", "DISABLED"}
FEEDBACK_ACTIONS = {"CONFIRM", "REJECT", "CORRECT"}

POSITIVE_EVENTS = {"MAPPING_CONFIRMED", "PATTERN_CONFIRMED", "POSITIVE_FEEDBACK", "POSITIVE_USAGE_SIGNAL", "TEMPLATE_REUSED", "APPLICATION_COMPLETED"}
NEGATIVE_EVENTS = {"MAPPING_REJECTED", "PATTERN_REJECTED", "NEGATIVE_FEEDBACK", "APPLICATION_FAILED"}
CORRECTION_EVENTS = {"MAPPING_MODIFIED", "USER_CORRECTION", "CORRECTION_FEEDBACK", "CORRECTION_SIGNAL", "TEMPLATE_CORRECTED", "APPLICATION_PARTIAL"}
USAGE_EVENTS = {"TEMPLATE_REUSED", "POSITIVE_USAGE_SIGNAL", "APPLICATION_COMPLETED", "APPLICATION_PARTIAL", "APPLICATION_FAILED"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_unit(value: Any, label: str = "value") -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{label} must be between 0.0 and 1.0")
    return float(value)


def normalize_pattern_name(value: str) -> str:
    from mapping_engine import normalize_field_name
    return normalize_field_name(value).replace(" ", "_")


def pattern_signature(source_pattern: dict[str, Any], target_field: str) -> str:
    payload = {
        "normalized_name": normalize_pattern_name(source_pattern.get("normalized_name", source_pattern.get("source_name", ""))),
        "type": source_pattern.get("type", "UNKNOWN"),
        "sheet_context": normalize_pattern_name(source_pattern.get("sheet_context", "")),
        "patterns": sorted(source_pattern.get("patterns", source_pattern.get("pattern_flags", []))),
        "target_field": target_field,
    }
    raw = "|".join(f"{key}={payload[key]}" for key in sorted(payload))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_learning_event(company_id: str, event_type: str, source: str, source_id: str, subject: dict[str, Any], observation: dict[str, Any], created_by: str | None = None, event_id: str | None = None, created_at: str | None = None) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported learning event type: {event_type}")
    if not company_id:
        raise ValueError("company_id is required")
    return {
        "event_id": event_id or "learning-event-" + hashlib.sha256(f"{company_id}:{source}:{source_id}:{event_type}:{created_at or now_iso()}".encode()).hexdigest()[:24],
        "company_id": company_id,
        "event_type": event_type,
        "source": source,
        "source_id": source_id,
        "subject": dict(subject),
        "observation": dict(observation),
        "created_by": created_by,
        "created_at": created_at or now_iso(),
        "learning_version": LEARNING_VERSION,
    }


def feedback_event_type(action: str) -> str:
    action = action.upper()
    if action not in FEEDBACK_ACTIONS:
        raise ValueError("feedback action must be CONFIRM, REJECT, or CORRECT")
    return {"CONFIRM": "POSITIVE_FEEDBACK", "REJECT": "NEGATIVE_FEEDBACK", "CORRECT": "CORRECTION_FEEDBACK"}[action]


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _decay(last_confirmed_at: str | None, now: datetime) -> float:
    confirmed = _parse_date(last_confirmed_at)
    if not confirmed:
        return 1.0
    days = max(0, (now - confirmed).days)
    return math.exp(-days / 365.0)


def project_observations(events: Iterable[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """Rebuild observations from events; no event is mutated."""
    current = now or datetime.now(timezone.utc)
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("event_type") not in EVENT_TYPES:
            continue
        subject = event.get("subject", {})
        source_pattern = subject.get("source_pattern", {})
        target = subject.get("target_field")
        if not target:
            continue
        signature = pattern_signature(source_pattern, "")
        groups[(event.get("company_id", ""), signature, target)].append(event)

    by_company_pattern: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (company_id, signature, target), grouped in groups.items():
        positive = sum(event.get("event_type") in POSITIVE_EVENTS for event in grouped)
        negative = sum(event.get("event_type") in NEGATIVE_EVENTS for event in grouped)
        corrections = sum(event.get("event_type") in CORRECTION_EVENTS for event in grouped)
        usage = sum(event.get("event_type") in USAGE_EVENTS for event in grouped)
        confirms = [_parse_date(event.get("created_at")) for event in grouped if event.get("event_type") in POSITIVE_EVENTS]
        rejects = [_parse_date(event.get("created_at")) for event in grouped if event.get("event_type") in NEGATIVE_EVENTS]
        last_confirmed = max((item for item in confirms if item), default=None)
        last_rejected = max((item for item in rejects if item), default=None)
        # Conservative formula: base + confirmations/usages - rejection/correction penalties.
        raw_confidence = 0.15 + positive * 0.055 + usage * 0.01 - negative * 0.08 - corrections * 0.18
        confidence = max(0.0, min(1.0, raw_confidence * _decay(last_confirmed.isoformat() if last_confirmed else None, current)))
        support = positive + corrections
        competing = {item[0][2] for item in groups.items() if item[0][0] == company_id and item[0][1] == signature and item[0][2] != target}
        status = "CONFLICTED" if competing and (positive or corrections) else "ACTIVE" if confidence >= 0.45 else "WEAK"
        if grouped and all(event.get("event_type") == "PATTERN_EXPIRED" for event in grouped):
            status = "EXPIRED"
        if any(event.get("event_type") == "KNOWLEDGE_DISABLED" for event in grouped):
            status = "DISABLED"
        sample = grouped[-1].get("subject", {}).get("source_pattern", {})
        observation = {
            "company_id": company_id,
            "observation_id": "observation-" + hashlib.sha256(f"{signature}:{target}".encode()).hexdigest()[:24],
            "source_pattern": {key: sample.get(key) for key in ("normalized_name", "type", "sheet_context", "patterns") if sample.get(key) is not None},
            "pattern_signature": signature,
            "target_field": target,
            "confidence": round(validate_unit(confidence, "learning_confidence"), 4),
            "support_count": support,
            "positive_count": positive,
            "negative_count": negative,
            "rejection_count": negative,
            "usage_count": usage,
            "correction_count": corrections,
            "last_confirmed_at": last_confirmed.isoformat() if last_confirmed else None,
            "last_rejected_at": last_rejected.isoformat() if last_rejected else None,
            "last_used_at": max((item for item in (_parse_date(event.get("created_at")) for event in grouped if event.get("event_type") in USAGE_EVENTS) if item), default=None).isoformat() if any(event.get("event_type") in USAGE_EVENTS for event in grouped) else None,
            "decay_factor": round(_decay(last_confirmed.isoformat() if last_confirmed else None, current), 4),
            "status": status,
            "learning_version": LEARNING_VERSION,
        }
        by_company_pattern[(company_id, signature)].append(observation)

    result = []
    for observations in by_company_pattern.values():
        if len(observations) > 1:
            for observation in observations:
                observation = {**observation, "status": "CONFLICTED"}
                result.append(observation)
        else:
            result.extend(observations)
    return sorted(result, key=lambda item: (item["company_id"], item["pattern_signature"], item["target_field"]))


def project_knowledge(events: Iterable[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    return project_observations(events, now)


def build_learning_summary(knowledge: Iterable[dict[str, Any]]) -> dict[str, int]:
    items = list(knowledge)
    return {
        "total_patterns": len(items),
        "active": sum(item.get("status") == "ACTIVE" for item in items),
        "weak": sum(item.get("status") == "WEAK" for item in items),
        "conflicted": sum(item.get("status") == "CONFLICTED" for item in items),
        "expired": sum(item.get("status") == "EXPIRED" for item in items),
        "disabled": sum(item.get("status") == "DISABLED" for item in items),
        "high_confidence": sum(item.get("confidence", 0) >= 0.8 and item.get("support_count", 0) >= 5 for item in items),
    }
