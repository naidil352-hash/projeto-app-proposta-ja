"""Commercial Context Engine — deterministic projection of existing commercial data.

This module NEVER creates or mutates Client/Proposal/Opportunity/Product/Timeline
documents. It only consolidates already-known facts into a structured, explainable
snapshot. No AI, no inference of subjective states (interest, sentiment, reason for
loss) beyond what a human already recorded.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

COMMERCIAL_CONTEXT_VERSION = "1.0.0"

EVIDENCE_STATES = {"KNOWN", "DERIVED", "UNKNOWN"}
DATA_QUALITY_LEVELS = {"COMPLETE", "PARTIAL", "LIMITED", "INSUFFICIENT"}
SEVERITY_LEVELS = {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
SIGNAL_TYPES = {
    "NO_RECENT_ACTIVITY", "PROPOSAL_AGING", "HIGH_PROBABILITY", "LOW_PROBABILITY",
    "HIGH_TEMPERATURE", "LOW_TEMPERATURE", "MULTIPLE_FOLLOWUPS", "RECENT_ACTIVITY",
    "RECENT_CLIENT_RESPONSE", "STALE_OPPORTUNITY",
}

# Deterministic thresholds, centralized (never scattered magic numbers).
STALE_OPPORTUNITY_MIN_DAYS = 7
PROPOSAL_AGING_MIN_DAYS = 7
RECENT_ACTIVITY_MAX_DAYS = 2
HIGH_PROBABILITY_MIN = 70
LOW_PROBABILITY_MAX = 30
MULTIPLE_FOLLOWUPS_MIN_COUNT = 3
HIGH_TEMPERATURES = {"QUENTE", "MUITO_QUENTE"}
LOW_TEMPERATURES = {"FRIO"}
FOLLOWUP_EVENT_MARKERS = ("followup", "contact", "call", "whatsapp")
_OPEN_STATUSES = {"OPEN", "WAITING", "HUMAN_ACTION"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _days_since(value: str | None, now: datetime) -> int | None:
    parsed = _parse_iso(value)
    if not parsed:
        return None
    return max(0, (now - parsed).days)


def _severity_by_days(days: int) -> str:
    if days >= 30:
        return "CRITICAL"
    if days >= 14:
        return "HIGH"
    return "MEDIUM"


def _signal(signal: str, severity: str, source: str, source_id: str | None, calculation: str, detail: str, now: datetime) -> dict[str, Any]:
    return {
        "signal": signal,
        "severity": severity,
        "source": source,
        "source_id": source_id,
        "calculation": calculation,
        "detail": detail,
        "created_at": now.isoformat(),
    }


def build_opportunity_context(opportunity: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Consolidate only fields that already exist on the opportunity document."""
    now = now or _now()
    age_days = _days_since(opportunity.get("created_at"), now)
    return {
        "opportunity_id": opportunity.get("id"),
        "title": opportunity.get("title"),
        "stage": opportunity.get("stage") or "NOVO",
        "status": opportunity.get("status"),
        "temperature": opportunity.get("temperature"),
        "probability": opportunity.get("probability"),
        "estimated_value": opportunity.get("estimated_value"),
        "created_at": opportunity.get("created_at"),
        "updated_at": opportunity.get("updated_at"),
        "closed_at": opportunity.get("closed_at"),
        "opportunity_age_days": age_days,
        "calculation_timestamp": now.isoformat(),
    }


def build_client_context(client: dict[str, Any] | None, related_opportunities: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Consolidate client identity plus history computed strictly from provided data.

    ``related_opportunities`` is a list of {"status": str, "value": float | None}
    already scoped to this client/company by the caller. Nothing is fabricated:
    counts that cannot be computed are ``None``, never ``0``.
    """
    if not client:
        return {
            "client_id": None,
            "client_name": None,
            "client_status": "UNKNOWN",
            "history": _empty_client_history(),
        }

    history = _empty_client_history()
    if related_opportunities is not None:
        total = len(related_opportunities)
        won = [item for item in related_opportunities if item.get("status") == "WON"]
        lost = sum(1 for item in related_opportunities if item.get("status") == "LOST")
        open_count = sum(1 for item in related_opportunities if item.get("status") in _OPEN_STATUSES)
        cancelled = sum(1 for item in related_opportunities if item.get("status") == "CANCELLED")
        known_won_values = [item["value"] for item in won if item.get("value") is not None]
        history = {
            "total_opportunities": total,
            "won_opportunities": len(won),
            "lost_opportunities": lost,
            "open_opportunities": open_count,
            "cancelled_opportunities": cancelled,
            "win_rate": round(len(won) / total, 4) if total > 0 else None,
            "average_ticket": round(sum(known_won_values) / len(known_won_values), 2) if known_won_values else None,
            "total_revenue_won": round(sum(known_won_values), 2) if known_won_values else None,
        }

    return {
        "client_id": client.get("id"),
        "client_name": client.get("name"),
        "client_status": "ACTIVE" if not client.get("deleted") else "INACTIVE",
        "history": history,
    }


def _empty_client_history() -> dict[str, Any]:
    return {
        "total_opportunities": None,
        "won_opportunities": None,
        "lost_opportunities": None,
        "open_opportunities": None,
        "cancelled_opportunities": None,
        "win_rate": None,
        "average_ticket": None,
        "total_revenue_won": None,
    }


def build_proposal_context(proposal: dict[str, Any] | None) -> dict[str, Any] | None:
    if not proposal:
        return None
    products = proposal.get("products") or []
    return {
        "proposal_id": proposal.get("id"),
        "proposal_status": proposal.get("status"),
        "proposal_value": proposal.get("grand_total", proposal.get("total")),
        "created_at": proposal.get("created_at"),
        "updated_at": proposal.get("updated_at"),
        "items_count": len(products),
        "total_quantity": sum(item.get("quantity", 0) or 0 for item in products) if products else None,
    }


def build_product_context(products: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not products:
        return []
    return [
        {
            "product_code": item.get("code") or None,
            "description": item.get("description") or item.get("name"),
            "quantity": item.get("quantity"),
            "unit_price": item.get("unit_price"),
            "total": item.get("total"),
        }
        for item in products
    ]


def build_timeline_context(timeline: list[dict[str, Any]] | None, max_events: int = 10) -> dict[str, Any]:
    events = timeline or []
    relevant = sorted(events, key=lambda item: item.get("created_at") or "", reverse=True)[:max_events]
    return {
        "relevant_events": [
            {"event_type": event.get("type") or event.get("event_type"), "created_at": event.get("created_at"), "source": "timeline"}
            for event in relevant
        ],
        "total_events": len(events),
    }


def build_seller_context(opportunity: dict[str, Any], seller_stats: dict[str, Any] | None) -> dict[str, Any] | None:
    seller_id = opportunity.get("seller_id") or opportunity.get("user_id")
    if not seller_id:
        return None
    context = {
        "seller_id": seller_id,
        "seller_name": opportunity.get("seller_name"),
        "seller_opportunities": None,
        "seller_won": None,
        "seller_lost": None,
        "seller_open": None,
    }
    if seller_stats:
        context.update({
            "seller_opportunities": seller_stats.get("total"),
            "seller_won": seller_stats.get("won"),
            "seller_lost": seller_stats.get("lost"),
            "seller_open": seller_stats.get("open"),
        })
    return context


def detect_commercial_signals(
    opportunity_ctx: dict[str, Any],
    proposal_ctx: dict[str, Any] | None,
    timeline_ctx: dict[str, Any],
    opportunity: dict[str, Any],
    now: datetime,
) -> tuple[list[dict[str, Any]], int | None, int | None]:
    """Return (signals, days_since_last_activity, days_since_proposal)."""
    signals: list[dict[str, Any]] = []
    opportunity_id = opportunity_ctx.get("opportunity_id")

    last_event = timeline_ctx["relevant_events"][0] if timeline_ctx.get("relevant_events") else None
    days_since_last_activity = _days_since(last_event.get("created_at"), now) if last_event else None

    days_since_proposal = _days_since(proposal_ctx.get("updated_at"), now) if proposal_ctx else None

    if days_since_last_activity is None:
        signals.append(_signal("NO_RECENT_ACTIVITY", "LOW", "timeline", opportunity_id, "no timeline events recorded", "Nenhuma atividade registrada na timeline.", now))
    elif days_since_last_activity >= STALE_OPPORTUNITY_MIN_DAYS:
        signals.append(_signal("STALE_OPPORTUNITY", _severity_by_days(days_since_last_activity), "timeline", opportunity_id, f"days_since_last_activity >= {STALE_OPPORTUNITY_MIN_DAYS}", f"Sem atividade há {days_since_last_activity} dias.", now))
    elif days_since_last_activity <= RECENT_ACTIVITY_MAX_DAYS:
        signals.append(_signal("RECENT_ACTIVITY", "INFO", "timeline", opportunity_id, f"days_since_last_activity <= {RECENT_ACTIVITY_MAX_DAYS}", f"Atividade recente há {days_since_last_activity} dia(s).", now))

    if days_since_proposal is not None and days_since_proposal >= PROPOSAL_AGING_MIN_DAYS:
        signals.append(_signal("PROPOSAL_AGING", _severity_by_days(days_since_proposal), "proposal", proposal_ctx.get("proposal_id"), f"days_since_proposal >= {PROPOSAL_AGING_MIN_DAYS}", f"Proposta sem atualização há {days_since_proposal} dias.", now))

    probability = opportunity_ctx.get("probability")
    if isinstance(probability, (int, float)):
        if probability >= HIGH_PROBABILITY_MIN:
            signals.append(_signal("HIGH_PROBABILITY", "INFO", "opportunity", opportunity_id, f"probability >= {HIGH_PROBABILITY_MIN}", f"Probabilidade alta ({probability}%).", now))
        elif probability <= LOW_PROBABILITY_MAX:
            signals.append(_signal("LOW_PROBABILITY", "LOW", "opportunity", opportunity_id, f"probability <= {LOW_PROBABILITY_MAX}", f"Probabilidade baixa ({probability}%).", now))

    temperature = opportunity_ctx.get("temperature")
    if temperature in HIGH_TEMPERATURES:
        signals.append(_signal("HIGH_TEMPERATURE", "INFO", "opportunity", opportunity_id, f"temperature in {sorted(HIGH_TEMPERATURES)}", f"Temperatura {temperature}.", now))
    elif temperature in LOW_TEMPERATURES:
        signals.append(_signal("LOW_TEMPERATURE", "LOW", "opportunity", opportunity_id, f"temperature in {sorted(LOW_TEMPERATURES)}", f"Temperatura {temperature}.", now))

    followup_count = sum(
        1 for event in (opportunity.get("timeline") or [])
        if any(marker in str(event.get("type") or event.get("event_type") or "").lower() for marker in FOLLOWUP_EVENT_MARKERS)
    )
    if followup_count >= MULTIPLE_FOLLOWUPS_MIN_COUNT:
        signals.append(_signal("MULTIPLE_FOLLOWUPS", "MEDIUM", "timeline", opportunity_id, f"followup_count >= {MULTIPLE_FOLLOWUPS_MIN_COUNT}", f"{followup_count} tentativas de contato registradas.", now))

    last_response_days = _days_since(opportunity.get("last_customer_response_at"), now)
    if last_response_days is not None and last_response_days <= RECENT_ACTIVITY_MAX_DAYS:
        signals.append(_signal("RECENT_CLIENT_RESPONSE", "INFO", "opportunity", opportunity_id, f"days_since(last_customer_response_at) <= {RECENT_ACTIVITY_MAX_DAYS}", f"Cliente respondeu há {last_response_days} dia(s).", now))

    return signals, days_since_last_activity, days_since_proposal


def _evidence(value: Any) -> str:
    if value in (None, ""):
        return "UNKNOWN"
    return "KNOWN"


def build_evidence(opportunity: dict[str, Any], client_history: dict[str, Any]) -> dict[str, str]:
    return {
        "temperature": _evidence(opportunity.get("temperature")),
        "probability": _evidence(opportunity.get("probability")),
        "customer_intent": _evidence(opportunity.get("customer_intent")),
        "customer_sentiment": _evidence(opportunity.get("customer_sentiment")),
        "loss_reason": _evidence(opportunity.get("loss_reason")),
        "competitor": _evidence(opportunity.get("competitor")),
        "win_rate": "DERIVED" if client_history.get("win_rate") is not None else "UNKNOWN",
        "average_ticket": "DERIVED" if client_history.get("average_ticket") is not None else "UNKNOWN",
    }


def compute_data_quality(has_client_history: bool, has_proposal: bool, has_timeline: bool) -> str:
    pillars_present = sum([has_client_history, has_proposal, has_timeline])
    return {3: "COMPLETE", 2: "PARTIAL", 1: "LIMITED", 0: "INSUFFICIENT"}[pillars_present]


def compute_source_snapshot_hash(opportunity: dict[str, Any], client: dict[str, Any] | None, proposal: dict[str, Any] | None, timeline: list[dict[str, Any]] | None) -> str:
    last_event = max((event.get("created_at") for event in (timeline or []) if event.get("created_at")), default="")
    raw = "|".join([
        str(opportunity.get("updated_at") or ""),
        str(client.get("updated_at") or "") if client else "",
        str(proposal.get("updated_at") or "") if proposal else "",
        last_event,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_commercial_context(
    company_id: str,
    opportunity: dict[str, Any],
    client: dict[str, Any] | None = None,
    proposal: dict[str, Any] | None = None,
    related_opportunities: list[dict[str, Any]] | None = None,
    seller_stats: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic Commercial Context snapshot.

    Same inputs + same ``now`` always produce the same context (except the
    ``created_at``/``updated_at`` timestamps of the persisted document, which
    are assigned by the caller, not by this function).
    """
    now = now or _now()
    opportunity_id = opportunity.get("id")
    timeline = opportunity.get("timeline") or []

    opportunity_ctx = build_opportunity_context(opportunity, now)
    client_ctx = build_client_context(client, related_opportunities)
    proposal_ctx = build_proposal_context(proposal)
    products_source = (proposal or {}).get("products") or opportunity.get("products") or []
    product_ctx = build_product_context(products_source)
    timeline_ctx = build_timeline_context(timeline)
    seller_ctx = build_seller_context(opportunity, seller_stats)

    signals, days_since_last_activity, days_since_proposal = detect_commercial_signals(
        opportunity_ctx, proposal_ctx, timeline_ctx, opportunity, now
    )
    opportunity_ctx["days_since_last_activity"] = days_since_last_activity
    opportunity_ctx["days_since_proposal"] = days_since_proposal

    data_quality = compute_data_quality(
        has_client_history=related_opportunities is not None,
        has_proposal=proposal is not None,
        has_timeline=bool(timeline),
    )
    evidence = build_evidence(opportunity, client_ctx["history"])

    confidence: dict[str, Any] = {}
    if client_ctx["history"]["win_rate"] is not None:
        total = client_ctx["history"]["total_opportunities"]
        won = client_ctx["history"]["won_opportunities"]
        confidence["win_rate"] = {"value": client_ctx["history"]["win_rate"], "confidence": 1.0, "basis": f"{won} wins / {total} opportunities"}
    if client_ctx["history"]["average_ticket"] is not None:
        confidence["average_ticket"] = {"value": client_ctx["history"]["average_ticket"], "confidence": 1.0, "basis": "known won-value opportunities only"}

    source_snapshot_hash = compute_source_snapshot_hash(opportunity, client, proposal, timeline)
    context_id = "context-" + hashlib.sha256(
        f"{company_id}:{opportunity_id}:{COMMERCIAL_CONTEXT_VERSION}:{source_snapshot_hash}".encode("utf-8")
    ).hexdigest()[:24]

    return {
        "context_id": context_id,
        "company_id": company_id,
        "opportunity_id": opportunity_id,
        "client_id": client.get("id") if client else opportunity.get("client_id") or None,
        "proposal_id": proposal.get("id") if proposal else opportunity.get("proposal_id") or None,
        "snapshot_version": COMMERCIAL_CONTEXT_VERSION,
        "context": {
            "opportunity": opportunity_ctx,
            "client": client_ctx,
            "proposal": proposal_ctx,
            "products": product_ctx,
            "timeline": timeline_ctx,
            "seller": seller_ctx,
            "signals": signals,
            "data_quality": data_quality,
        },
        "confidence": confidence,
        "evidence": evidence,
        "sources": {
            "opportunity": opportunity_id,
            "client": client.get("id") if client else None,
            "proposal": proposal.get("id") if proposal else None,
            "timeline": "opportunity.timeline",
            "products": "proposal.products" if proposal else ("opportunity.products" if opportunity.get("products") else None),
        },
        "source_snapshot_hash": source_snapshot_hash,
        "calculation_timestamp": now.isoformat(),
    }
