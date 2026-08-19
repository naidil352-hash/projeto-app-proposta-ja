"""Sales Intelligence Engine — deterministic, advisory-only analysis of a
Commercial Context (Phase 3.2) plus optional Company Knowledge (Phase 3.0/3.1).

This module NEVER executes a commercial action and NEVER mutates Opportunity,
Proposal, Client, Product, or Learning collections. It only classifies,
prioritizes and explains — a human (or a future action engine) decides what
to do with the output.

Loop protection: this module MUST NOT create learning_events or otherwise
feed Company Knowledge. Knowledge flows in one direction only:
    Company Knowledge -> Sales Intelligence (bounded, advisory)
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from commercial_context import (
    HIGH_PROBABILITY_MIN,
    HIGH_TEMPERATURES,
    LOW_PROBABILITY_MAX,
    PROPOSAL_AGING_MIN_DAYS,
    RECENT_ACTIVITY_MAX_DAYS,
    STALE_OPPORTUNITY_MIN_DAYS,
)
from knowledge_adapter import MAX_KNOWLEDGE_INFLUENCE

SALES_INTELLIGENCE_VERSION = "1.0.0"

INFO_TYPES = {"FACT", "DERIVED", "INFERENCE", "UNKNOWN"}
SALES_STATES = {
    "NEW", "ACTIVE", "ENGAGED", "WAITING_CLIENT", "NEGOTIATION", "HIGH_INTENT",
    "STALE", "AT_RISK", "WON", "LOST", "CANCELLED", "UNKNOWN",
}
PRIORITY_LEVELS = ("P0_CRITICAL", "P1_HIGH", "P2_MEDIUM", "P3_LOW", "P4_NONE")
URGENCY_LEVELS = ("IMMEDIATE", "TODAY", "THIS_WEEK", "NORMAL", "NONE")
RISK_LEVELS = ("NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL")
OPPORTUNITY_LEVELS = ("NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL")
FOLLOWUP_STATES = {"NOT_NEEDED", "NOT_DUE", "DUE", "OVERDUE", "URGENT", "UNKNOWN"}
RECOMMENDATION_ACTIONS = {
    "FOLLOW_UP", "REVIEW_PROPOSAL", "REVIEW_PRICE", "WAIT", "CONTACT_CLIENT",
    "REQUEST_INFORMATION", "HUMAN_REVIEW", "NO_ACTION",
}
CHANNELS = {"WHATSAPP", "EMAIL", "PHONE", "IN_PERSON", "UNKNOWN"}
EVIDENCE_STRENGTHS = ("WEAK", "MODERATE", "STRONG", "VERY_STRONG")

# Centralized thresholds (deterministic). Reuses Commercial Context thresholds
# where the same concept applies, instead of duplicating magic numbers.
NEW_MAX_AGE_DAYS = 2
NEW_MAX_EVENTS = 1
AT_RISK_MIN_PROBABILITY = 50
HIGH_INTENT_MIN_PROBABILITY = HIGH_PROBABILITY_MIN
MIN_BEHAVIOR_SAMPLE_SIZE = 5
BEHAVIOR_CONFIDENCE_DIVISOR = 20  # confidence = min(1.0, sample_size / divisor)
PRICE_OBJECTION_MARKERS = ("preco", "preço", "price", "valor")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fact(value: Any) -> dict[str, Any]:
    known = value not in (None, "")
    return {"type": "FACT" if known else "UNKNOWN", "value": value if known else None}


def _evidence_item(source: str, source_id: str | None, field: str, value: Any, calculation: str, strength: str) -> dict[str, Any]:
    return {"source": source, "source_id": source_id, "field": field, "value": value, "calculation": calculation, "strength": strength}


def _normalize(text: str) -> str:
    return "".join(char for char in text.lower() if char.isalnum() or char.isspace())


def detect_price_signal(opportunity: dict[str, Any], related_loss_reasons: list[str] | None = None) -> dict[str, Any]:
    """PRICE_REVIEW_POSSIBLE only with real evidence; never a discount recommendation."""
    objection_type = _normalize(str(opportunity.get("objection_type") or ""))
    if any(marker in objection_type for marker in PRICE_OBJECTION_MARKERS):
        return {"status": "PRICE_REVIEW_POSSIBLE", "type": "FACT", "evidence_field": "objection_type", "value": opportunity.get("objection_type")}
    loss_reason = _normalize(str(opportunity.get("loss_reason") or ""))
    if any(marker in loss_reason for marker in PRICE_OBJECTION_MARKERS):
        return {"status": "PRICE_REVIEW_POSSIBLE", "type": "FACT", "evidence_field": "loss_reason", "value": opportunity.get("loss_reason")}
    for reason in related_loss_reasons or []:
        if any(marker in _normalize(str(reason)) for marker in PRICE_OBJECTION_MARKERS):
            return {"status": "PRICE_REVIEW_POSSIBLE", "type": "DERIVED", "evidence_field": "historical_loss_reasons", "value": reason}
    return {"status": "UNKNOWN", "type": "UNKNOWN", "evidence_field": None, "value": None}


def build_customer_behavior(
    response_times_days: list[float] | None = None,
    purchase_cycle_days: list[float] | None = None,
    followup_response_rate: float | None = None,
    followup_sample_size: int = 0,
) -> dict[str, Any]:
    """Historical behavior, only usable as evidence when sample is sufficient."""

    def _metric(values: list[float] | None, basis_label: str) -> dict[str, Any]:
        sample_size = len(values or [])
        if sample_size < MIN_BEHAVIOR_SAMPLE_SIZE:
            return {"value": None, "sample_size": sample_size, "confidence": 0.0, "basis": f"insufficient sample (n={sample_size} < {MIN_BEHAVIOR_SAMPLE_SIZE})"}
        average = round(sum(values) / sample_size, 2)
        confidence = round(min(1.0, sample_size / BEHAVIOR_CONFIDENCE_DIVISOR), 4)
        return {"value": average, "sample_size": sample_size, "confidence": confidence, "basis": f"{sample_size} historical {basis_label}"}

    followup_metric = {"value": None, "sample_size": followup_sample_size, "confidence": 0.0, "basis": f"insufficient sample (n={followup_sample_size} < {MIN_BEHAVIOR_SAMPLE_SIZE})"}
    if followup_response_rate is not None and followup_sample_size >= MIN_BEHAVIOR_SAMPLE_SIZE:
        followup_metric = {
            "value": round(followup_response_rate, 4),
            "sample_size": followup_sample_size,
            "confidence": round(min(1.0, followup_sample_size / BEHAVIOR_CONFIDENCE_DIVISOR), 4),
            "basis": f"{followup_sample_size} historical follow-ups",
        }

    return {
        "average_response_time": _metric(response_times_days, "responses"),
        "average_purchase_cycle": _metric(purchase_cycle_days, "purchase cycles"),
        "historical_followup_response_rate": followup_metric,
    }


def _followup_state(days_since_last_activity: int | None, behavior: dict[str, Any]) -> tuple[str, str]:
    """Return (followup_state, calculation) using behavior when the sample is sufficient."""
    if days_since_last_activity is None:
        return "UNKNOWN", "no timeline activity recorded"

    response_metric = behavior.get("average_response_time", {})
    if response_metric.get("sample_size", 0) >= MIN_BEHAVIOR_SAMPLE_SIZE and response_metric.get("value"):
        expected = response_metric["value"]
        ratio = days_since_last_activity / expected if expected else None
        if ratio is None:
            pass
        elif ratio < 1:
            return "NOT_DUE", f"delay_ratio={round(ratio, 2)} < 1"
        elif ratio < 2:
            return "DUE", f"delay_ratio={round(ratio, 2)} in [1,2)"
        elif ratio < 4:
            return "OVERDUE", f"delay_ratio={round(ratio, 2)} in [2,4)"
        else:
            return "URGENT", f"delay_ratio={round(ratio, 2)} >= 4"

    # Fallback to static thresholds when historical behavior is not reliable.
    if days_since_last_activity < STALE_OPPORTUNITY_MIN_DAYS:
        return "NOT_DUE", f"days_since_last_activity={days_since_last_activity} < {STALE_OPPORTUNITY_MIN_DAYS}"
    if days_since_last_activity < STALE_OPPORTUNITY_MIN_DAYS * 2:
        return "DUE", f"days_since_last_activity={days_since_last_activity} in [{STALE_OPPORTUNITY_MIN_DAYS},{STALE_OPPORTUNITY_MIN_DAYS * 2})"
    if days_since_last_activity < STALE_OPPORTUNITY_MIN_DAYS * 4:
        return "OVERDUE", f"days_since_last_activity={days_since_last_activity} in [{STALE_OPPORTUNITY_MIN_DAYS * 2},{STALE_OPPORTUNITY_MIN_DAYS * 4})"
    return "URGENT", f"days_since_last_activity={days_since_last_activity} >= {STALE_OPPORTUNITY_MIN_DAYS * 4}"


def _strength_for_ratio_state(state: str) -> str:
    return {"NOT_DUE": "WEAK", "DUE": "MODERATE", "OVERDUE": "STRONG", "URGENT": "VERY_STRONG", "UNKNOWN": "WEAK"}[state]


def determine_sales_state(opportunity: dict[str, Any], opp_ctx: dict[str, Any], signal_codes: set[str], total_events: int) -> tuple[str, str, list[str]]:
    """Deterministic, evidence-backed state; first matching rule wins."""
    status = opportunity.get("status")
    if status == "WON":
        return "WON", "Opportunity status is WON.", ["status=WON"]
    if status == "LOST":
        return "LOST", "Opportunity status is LOST.", ["status=LOST"]
    if status == "CANCELLED":
        return "CANCELLED", "Opportunity status is CANCELLED.", ["status=CANCELLED"]

    probability = opp_ctx.get("probability")
    stale = "STALE_OPPORTUNITY" in signal_codes
    age_days = opp_ctx.get("opportunity_age_days")

    if stale and isinstance(probability, (int, float)) and probability >= AT_RISK_MIN_PROBABILITY:
        return "AT_RISK", "High probability opportunity with no recent activity.", [f"probability={probability}>={AT_RISK_MIN_PROBABILITY}", "signal=STALE_OPPORTUNITY"]
    if stale:
        return "STALE", "No recent activity beyond the stale threshold.", ["signal=STALE_OPPORTUNITY"]
    if status == "WAITING":
        return "WAITING_CLIENT", "Opportunity status is WAITING.", ["status=WAITING"]
    stage = opp_ctx.get("stage")
    if stage in {"NEGOCIACAO", "AGUARDANDO_APROVACAO", "ALTA_INTENCAO"}:
        return "NEGOTIATION", f"Stage is {stage}.", [f"stage={stage}"]
    if (
        isinstance(probability, (int, float)) and probability >= HIGH_INTENT_MIN_PROBABILITY
        and "RECENT_ACTIVITY" in signal_codes and "RECENT_CLIENT_RESPONSE" in signal_codes
    ):
        return "HIGH_INTENT", "High probability with recent activity and recent client response.", [
            f"probability={probability}>={HIGH_INTENT_MIN_PROBABILITY}", "signal=RECENT_ACTIVITY", "signal=RECENT_CLIENT_RESPONSE",
        ]
    if "RECENT_ACTIVITY" in signal_codes and total_events >= 2:
        return "ENGAGED", "Recent activity with multiple recorded events.", ["signal=RECENT_ACTIVITY", f"total_events={total_events}>=2"]
    if age_days is not None and age_days <= NEW_MAX_AGE_DAYS and total_events <= NEW_MAX_EVENTS:
        return "NEW", "Opportunity was created very recently with minimal history.", [f"opportunity_age_days={age_days}<={NEW_MAX_AGE_DAYS}"]
    if age_days is not None:
        return "ACTIVE", "Opportunity is open without a specific pattern match.", [f"opportunity_age_days={age_days}"]
    return "UNKNOWN", "Insufficient data to classify sales state.", []


def determine_commercial_risk(signal_codes: set[str], probability: Any) -> tuple[str, list[str]]:
    high_probability = isinstance(probability, (int, float)) and probability >= HIGH_PROBABILITY_MIN
    stale = "STALE_OPPORTUNITY" in signal_codes
    aging = "PROPOSAL_AGING" in signal_codes
    if stale and high_probability:
        return "HIGH", [f"probability>={HIGH_PROBABILITY_MIN}", "signal=STALE_OPPORTUNITY"]
    if stale and aging:
        return "HIGH", ["signal=STALE_OPPORTUNITY", "signal=PROPOSAL_AGING"]
    if stale or aging:
        return "MEDIUM", [f"signal={'STALE_OPPORTUNITY' if stale else 'PROPOSAL_AGING'}"]
    if "LOW_PROBABILITY" in signal_codes or "LOW_TEMPERATURE" in signal_codes:
        return "LOW", ["signal=LOW_PROBABILITY or LOW_TEMPERATURE"]
    return "NONE", []


def determine_commercial_opportunity(signal_codes: set[str], probability: Any, win_rate: float | None) -> tuple[str, list[str]]:
    high_probability = isinstance(probability, (int, float)) and probability >= HIGH_PROBABILITY_MIN
    recent_response = "RECENT_CLIENT_RESPONSE" in signal_codes
    recent_activity = "RECENT_ACTIVITY" in signal_codes
    favorable_history = isinstance(win_rate, (int, float)) and win_rate >= 0.6
    if high_probability and recent_response and favorable_history:
        return "CRITICAL", [f"probability>={HIGH_PROBABILITY_MIN}", "signal=RECENT_CLIENT_RESPONSE", f"win_rate>={0.6}"]
    if high_probability and recent_activity:
        return "HIGH", [f"probability>={HIGH_PROBABILITY_MIN}", "signal=RECENT_ACTIVITY"]
    if high_probability or recent_response:
        return "MEDIUM", [f"probability>={HIGH_PROBABILITY_MIN}" if high_probability else "signal=RECENT_CLIENT_RESPONSE"]
    if recent_activity:
        return "LOW", ["signal=RECENT_ACTIVITY"]
    return "NONE", []


def determine_priority(commercial_risk: str, commercial_opportunity: str, followup_state: str) -> str:
    if commercial_risk == "CRITICAL" or followup_state == "URGENT":
        return "P0_CRITICAL"
    if commercial_risk == "HIGH" or followup_state == "OVERDUE":
        return "P1_HIGH"
    if commercial_risk == "MEDIUM" or followup_state == "DUE" or commercial_opportunity in {"HIGH", "CRITICAL"}:
        return "P2_MEDIUM"
    if commercial_risk == "LOW" or commercial_opportunity == "MEDIUM":
        return "P3_LOW"
    return "P4_NONE"


def determine_urgency(followup_state: str) -> str:
    return {
        "URGENT": "IMMEDIATE", "OVERDUE": "TODAY", "DUE": "THIS_WEEK",
        "NOT_DUE": "NORMAL", "UNKNOWN": "NORMAL", "NOT_NEEDED": "NONE",
    }[followup_state]


def build_recommendations(
    context_id: str,
    sales_state: str,
    followup_state: str,
    days_since_last_activity: int | None,
    price_signal: dict[str, Any],
    priority: str,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    if sales_state in {"WON", "LOST", "CANCELLED"}:
        recommendations.append({"action": "NO_ACTION", "channel": "UNKNOWN", "priority": "P4_NONE", "reason": f"Opportunity is already {sales_state}.", "confidence": 1.0, "evidence": [_evidence_item("commercial_context", context_id, "status", sales_state, "state is terminal", "STRONG")]})
        return recommendations

    if followup_state in {"DUE", "OVERDUE", "URGENT"}:
        strength = _strength_for_ratio_state(followup_state)
        confidence = {"DUE": 0.6, "OVERDUE": 0.85, "URGENT": 0.95}[followup_state]
        recommendations.append({
            "action": "FOLLOW_UP",
            "channel": "UNKNOWN",
            "priority": priority,
            "reason": f"No activity for {days_since_last_activity} day(s); follow-up state is {followup_state}.",
            "confidence": confidence,
            "evidence": [_evidence_item("commercial_context", context_id, "days_since_last_activity", days_since_last_activity, f"followup_state={followup_state}", strength)],
        })
    if price_signal["status"] == "PRICE_REVIEW_POSSIBLE":
        recommendations.append({
            "action": "REVIEW_PRICE",
            "channel": "UNKNOWN",
            "priority": "P2_MEDIUM",
            "reason": "Price-related objection evidence was found.",
            "confidence": 0.7 if price_signal["type"] == "FACT" else 0.5,
            "evidence": [_evidence_item("opportunity", context_id, price_signal["evidence_field"], price_signal["value"], "price objection marker detected", "MODERATE")],
        })
    if sales_state == "WAITING_CLIENT" and followup_state in {"NOT_DUE", "UNKNOWN"}:
        recommendations.append({"action": "WAIT", "channel": "UNKNOWN", "priority": "P3_LOW", "reason": "Client response is not yet due based on history/thresholds.", "confidence": 0.55, "evidence": [_evidence_item("commercial_context", context_id, "sales_state", sales_state, "waiting on client", "WEAK")]})
    if sales_state in {"NEGOTIATION", "HIGH_INTENT"} and not recommendations:
        recommendations.append({"action": "REVIEW_PROPOSAL", "channel": "UNKNOWN", "priority": priority, "reason": f"Opportunity is in {sales_state} and may benefit from proposal review.", "confidence": 0.5, "evidence": [_evidence_item("commercial_context", context_id, "sales_state", sales_state, "active negotiation stage", "WEAK")]})
    if not recommendations:
        recommendations.append({"action": "NO_ACTION", "channel": "UNKNOWN", "priority": "P4_NONE", "reason": "No objective signal currently requires action.", "confidence": 0.4, "evidence": []})
    return recommendations


def apply_bounded_knowledge_support(state_confidence: float, knowledge_items: list[dict[str, Any]] | None) -> tuple[float, list[dict[str, Any]]]:
    """Knowledge may only nudge confidence within a bounded cap; it can never
    create or elevate a recommendation/priority by itself (dominance protection)."""
    if not knowledge_items:
        return state_confidence, []
    supporting = [item for item in knowledge_items if item.get("status") == "ACTIVE" and item.get("confidence", 0) >= 0.5 and item.get("support_count", 0) >= 3]
    if not supporting:
        return state_confidence, []
    boost = min(MAX_KNOWLEDGE_INFLUENCE, max(item.get("confidence", 0) for item in supporting) * 0.15)
    evidence = [_evidence_item("company_knowledge", item.get("observation_id"), "confidence", item.get("confidence"), "bounded advisory support", "MODERATE") for item in supporting[:3]]
    return round(min(1.0, state_confidence + boost), 4), evidence


def build_sales_insight(
    company_id: str,
    opportunity: dict[str, Any],
    commercial_context: dict[str, Any],
    knowledge_items: list[dict[str, Any]] | None = None,
    customer_behavior: dict[str, Any] | None = None,
    related_loss_reasons: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic Sales Insight from an existing Commercial Context.

    This function never reads RawRecords, never duplicates engine logic, and
    never mutates any commercial document. Knowledge only nudges confidence
    within a bounded cap and never creates recommendations by itself.
    """
    now = now or _now()
    context_id = commercial_context.get("context_id")
    opp_ctx = commercial_context.get("context", {}).get("opportunity", {})
    timeline_ctx = commercial_context.get("context", {}).get("timeline", {})
    client_history = commercial_context.get("context", {}).get("client", {}).get("history", {})
    signals = commercial_context.get("context", {}).get("signals", [])
    signal_codes = {signal.get("signal") for signal in signals}
    total_events = timeline_ctx.get("total_events", 0)
    days_since_last_activity = opp_ctx.get("days_since_last_activity")

    behavior = customer_behavior or build_customer_behavior()
    sales_state, state_reason, state_evidence = determine_sales_state(opportunity, opp_ctx, signal_codes, total_events)
    followup_state, followup_calc = _followup_state(days_since_last_activity, behavior) if sales_state not in {"WON", "LOST", "CANCELLED"} else ("NOT_NEEDED", f"sales_state={sales_state}")
    commercial_risk, risk_evidence = determine_commercial_risk(signal_codes, opp_ctx.get("probability"))
    commercial_opportunity, opportunity_evidence = determine_commercial_opportunity(signal_codes, opp_ctx.get("probability"), client_history.get("win_rate"))
    priority = determine_priority(commercial_risk, commercial_opportunity, followup_state)
    urgency = determine_urgency(followup_state)
    price_signal = detect_price_signal(opportunity, related_loss_reasons)

    base_confidence = 0.6 + 0.1 * len(state_evidence)
    state_confidence = round(min(0.95, base_confidence), 4)
    state_confidence, knowledge_evidence = apply_bounded_knowledge_support(state_confidence, knowledge_items)

    recommendations = build_recommendations(context_id, sales_state, followup_state, days_since_last_activity, price_signal, priority)

    evidence: list[dict[str, Any]] = []
    for item in state_evidence:
        evidence.append(_evidence_item("commercial_context", context_id, item.split("=")[0], item.split("=", 1)[1] if "=" in item else None, item, "STRONG"))
    evidence.append(_evidence_item("commercial_context", context_id, "followup_state", followup_state, followup_calc, _strength_for_ratio_state(followup_state) if followup_state in {"NOT_DUE", "DUE", "OVERDUE", "URGENT"} else "WEAK"))
    evidence.extend(knowledge_evidence)

    insight = {
        "sales_state": {"state": sales_state, "reason": state_reason, "evidence": state_evidence, "confidence": state_confidence},
        "priority": priority,
        "urgency": urgency,
        "commercial_risk": {"level": commercial_risk, "evidence": risk_evidence},
        "commercial_opportunity": {"level": commercial_opportunity, "evidence": opportunity_evidence},
        "followup_state": {"state": followup_state, "calculation": followup_calc},
        "price_signal": price_signal,
        "competitor": _fact(opportunity.get("competitor")),
        "loss_reason": _fact(opportunity.get("loss_reason")),
        "customer_intent": _fact(opportunity.get("customer_intent")),
        "customer_sentiment": _fact(opportunity.get("customer_sentiment")),
        "probability_source": {"type": "FACT", "value": opp_ctx.get("probability"), "label": "SOURCE_DATA"},
        "historical_behavior": behavior,
    }

    source_hash_input = "|".join([
        str(commercial_context.get("source_snapshot_hash", "")),
        str(sorted(item.get("observation_id", "") for item in (knowledge_items or []))),
        str(behavior),
    ])
    source_snapshot_hash = hashlib.sha256(source_hash_input.encode("utf-8")).hexdigest()
    analysis_id = "insight-" + hashlib.sha256(
        f"{company_id}:{opportunity.get('id')}:{SALES_INTELLIGENCE_VERSION}:{context_id}:{source_snapshot_hash}".encode("utf-8")
    ).hexdigest()[:24]

    return {
        "insight_id": analysis_id,
        "company_id": company_id,
        "opportunity_id": opportunity.get("id"),
        "context_id": context_id,
        "context_version": commercial_context.get("snapshot_version"),
        "engine_version": SALES_INTELLIGENCE_VERSION,
        "sales_intelligence_version": SALES_INTELLIGENCE_VERSION,
        "insight": insight,
        "recommendations": recommendations,
        "priority": priority,
        "urgency": urgency,
        "confidence": state_confidence,
        "evidence": evidence,
        "source_snapshot_hash": source_snapshot_hash,
        "calculation_timestamp": now.isoformat(),
    }
