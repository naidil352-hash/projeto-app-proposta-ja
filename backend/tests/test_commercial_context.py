"""Phase 3.2 — Commercial Context Engine (unit tests)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from commercial_context import (
    COMMERCIAL_CONTEXT_VERSION,
    build_client_context,
    build_commercial_context,
    build_opportunity_context,
    build_product_context,
    build_proposal_context,
    build_timeline_context,
    compute_data_quality,
)

pytestmark = pytest.mark.unit


def iso_days_ago(days: int, now: datetime) -> str:
    return (now - timedelta(days=days)).isoformat()


def _opportunity(now, **overrides):
    base = {
        "id": "opp-1",
        "company_id": "company-a",
        "client_id": "client-1",
        "proposal_id": "prop-1",
        "seller_id": "seller-1",
        "seller_name": "Vendedor Um",
        "title": "Venda de motores",
        "status": "OPEN",
        "stage": "NEGOCIACAO",
        "temperature": "QUENTE",
        "probability": 70,
        "estimated_value": 3000.0,
        "created_at": iso_days_ago(10, now),
        "updated_at": iso_days_ago(1, now),
        "timeline": [{"id": "t1", "type": "PROPOSAL_SENT", "created_at": iso_days_ago(7, now)}],
    }
    base.update(overrides)
    return base


def _proposal(now, **overrides):
    base = {
        "id": "prop-1",
        "status": "aberto",
        "grand_total": 3000.0,
        "created_at": iso_days_ago(9, now),
        "updated_at": iso_days_ago(8, now),
        "products": [{"code": "MTR-001", "description": "Motor 5 CV", "quantity": 2, "unit_price": 1500.0, "total": 3000.0}],
    }
    base.update(overrides)
    return base


def _client(**overrides):
    base = {"id": "client-1", "name": "ACME", "document": "12345678000199", "deleted": False, "updated_at": "2026-01-01T00:00:00+00:00"}
    base.update(overrides)
    return base


# 1. opportunity context
def test_opportunity_context_uses_only_existing_fields():
    now = datetime.now(timezone.utc)
    ctx = build_opportunity_context(_opportunity(now), now)
    assert ctx["opportunity_age_days"] == 10
    assert ctx["temperature"] == "QUENTE"
    assert ctx["stage"] == "NEGOCIACAO"


# 2. client context
def test_client_context_consolidates_known_fields_only():
    ctx = build_client_context(_client(), related_opportunities=None)
    assert ctx["client_name"] == "ACME"
    assert ctx["history"]["total_opportunities"] is None


# 3. proposal context
def test_proposal_context_reports_only_existing_data():
    now = datetime.now(timezone.utc)
    ctx = build_proposal_context(_proposal(now))
    assert ctx["proposal_value"] == 3000.0
    assert ctx["items_count"] == 1
    assert ctx["total_quantity"] == 2


# 4. product context
def test_product_context_does_not_infer_technical_attributes():
    products = build_product_context([{"code": "MTR-001", "description": "Motor 5 CV", "quantity": 2, "unit_price": 1500.0, "total": 3000.0}])
    assert products == [{"product_code": "MTR-001", "description": "Motor 5 CV", "quantity": 2, "unit_price": 1500.0, "total": 3000.0}]


# 5. timeline
def test_timeline_context_limits_and_orders_relevant_events():
    now = datetime.now(timezone.utc)
    events = [{"type": f"EVENT_{i}", "created_at": iso_days_ago(i, now)} for i in range(15)]
    ctx = build_timeline_context(events, max_events=5)
    assert len(ctx["relevant_events"]) == 5
    assert ctx["total_events"] == 15
    assert ctx["relevant_events"][0]["event_type"] == "EVENT_0"


# 6. opportunity age
def test_opportunity_age_days_matches_created_at_delta():
    now = datetime.now(timezone.utc)
    ctx = build_opportunity_context(_opportunity(now, created_at=iso_days_ago(25, now)), now)
    assert ctx["opportunity_age_days"] == 25


# 7. days since activity / 8 win rate / 9 average ticket
def test_client_history_win_rate_and_average_ticket_only_from_known_values():
    related = [
        {"status": "WON", "value": 1000.0},
        {"status": "WON", "value": None},
        {"status": "LOST", "value": None},
        {"status": "OPEN", "value": None},
    ]
    ctx = build_client_context(_client(), related)
    assert ctx["history"]["total_opportunities"] == 4
    assert ctx["history"]["won_opportunities"] == 2
    assert ctx["history"]["win_rate"] == 0.5
    assert ctx["history"]["average_ticket"] == 1000.0  # only the known won value is used


# 10. signals / 11 severity
def test_signals_and_severity_are_deterministic():
    now = datetime.now(timezone.utc)
    context = build_commercial_context("company-a", _opportunity(now), _client(), _proposal(now), related_opportunities=[{"status": "WON", "value": 100.0}], now=now)
    signal_codes = {item["signal"] for item in context["context"]["signals"]}
    assert "PROPOSAL_AGING" in signal_codes
    assert "STALE_OPPORTUNITY" in signal_codes
    assert "HIGH_PROBABILITY" in signal_codes
    assert "HIGH_TEMPERATURE" in signal_codes
    stale = next(item for item in context["context"]["signals"] if item["signal"] == "STALE_OPPORTUNITY")
    assert stale["severity"] in {"MEDIUM", "HIGH", "CRITICAL"}


# 12/13/14. KNOWN / DERIVED / UNKNOWN
def test_evidence_classification_known_derived_unknown():
    now = datetime.now(timezone.utc)
    context = build_commercial_context("company-a", _opportunity(now), _client(), _proposal(now), related_opportunities=[{"status": "WON", "value": 100.0}], now=now)
    assert context["evidence"]["temperature"] == "KNOWN"
    assert context["evidence"]["win_rate"] == "DERIVED"
    assert context["evidence"]["competitor"] == "UNKNOWN"


# 15. data quality
def test_data_quality_levels_are_deterministic():
    assert compute_data_quality(True, True, True) == "COMPLETE"
    assert compute_data_quality(True, True, False) == "PARTIAL"
    assert compute_data_quality(True, False, False) == "LIMITED"
    assert compute_data_quality(False, False, False) == "INSUFFICIENT"


# 16/17/18. missing proposal / client / timeline never fail
def test_missing_proposal_client_and_timeline_do_not_fail():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, timeline=[])
    context = build_commercial_context("company-a", opportunity, client=None, proposal=None, related_opportunities=None, now=now)
    assert context["context"]["proposal"] is None
    assert context["context"]["client"]["client_status"] == "UNKNOWN"
    assert context["context"]["data_quality"] == "INSUFFICIENT"
    assert context["context"]["opportunity"]["days_since_last_activity"] is None


# 19. deterministic context
def test_deterministic_context_same_inputs_same_output():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now)
    client = _client()
    proposal = _proposal(now)
    first = build_commercial_context("company-a", opportunity, client, proposal, [{"status": "WON", "value": 100.0}], now=now)
    second = build_commercial_context("company-a", opportunity, client, proposal, [{"status": "WON", "value": 100.0}], now=now)
    assert first == second


# 20. idempotency (same source snapshot -> same context_id)
def test_idempotency_same_source_snapshot_yields_same_context_id():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now)
    first = build_commercial_context("company-a", opportunity, _client(), _proposal(now), now=now)
    second = build_commercial_context("company-a", opportunity, _client(), _proposal(now), now=now + timedelta(hours=1))
    assert first["context_id"] == second["context_id"]


def test_idempotency_changed_source_snapshot_yields_different_context_id():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now)
    changed_opportunity = _opportunity(now, updated_at=(now).isoformat())
    first = build_commercial_context("company-a", opportunity, _client(), _proposal(now), now=now)
    second = build_commercial_context("company-a", changed_opportunity, _client(), _proposal(now), now=now)
    assert first["context_id"] != second["context_id"]


# 21. privacy
def test_privacy_does_not_copy_sensitive_fields_unnecessarily():
    now = datetime.now(timezone.utc)
    context = build_commercial_context("company-a", _opportunity(now), _client(), _proposal(now), now=now)
    serialized = str(context)
    assert "12345678000199" not in serialized  # CNPJ not duplicated into context


# 22. source traceability
def test_source_traceability_references_ids_not_values():
    now = datetime.now(timezone.utc)
    context = build_commercial_context("company-a", _opportunity(now), _client(), _proposal(now), now=now)
    assert context["sources"]["opportunity"] == "opp-1"
    assert context["sources"]["client"] == "client-1"
    assert context["sources"]["proposal"] == "prop-1"


# 23. versioning
def test_snapshot_version_is_recorded():
    now = datetime.now(timezone.utc)
    context = build_commercial_context("company-a", _opportunity(now), now=now)
    assert context["snapshot_version"] == COMMERCIAL_CONTEXT_VERSION


# Fundamental test (section 40 of the request)
def test_fundamental_scenario_ages_and_signals():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(
        now,
        created_at=iso_days_ago(10, now),
        temperature="QUENTE",
        probability=70,
        timeline=[{"id": "t1", "type": "PROPOSAL_SENT", "created_at": iso_days_ago(7, now)}],
    )
    proposal = _proposal(now, updated_at=iso_days_ago(8, now))
    context = build_commercial_context("company-a", opportunity, _client(), proposal, now=now)
    opp_ctx = context["context"]["opportunity"]
    assert opp_ctx["opportunity_age_days"] == 10
    assert opp_ctx["days_since_proposal"] == 8
    assert opp_ctx["days_since_last_activity"] == 7
    signal_codes = {item["signal"] for item in context["context"]["signals"]}
    assert "PROPOSAL_AGING" in signal_codes
    assert "STALE_OPPORTUNITY" in signal_codes
    # No recommendation-like action must ever appear in the context.
    forbidden = {"envie", "negocie", "ligue", "desconto", "recommend"}
    assert not any(word in str(context).lower() for word in forbidden)


# Non-fabrication test (section 42)
def test_non_fabrication_of_competitor_intent_and_loss_reason():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, competitor="", customer_intent="", customer_sentiment="", loss_reason="")
    context = build_commercial_context("company-a", opportunity, now=now)
    assert context["evidence"]["competitor"] == "UNKNOWN"
    assert context["evidence"]["customer_intent"] == "UNKNOWN"
    assert context["evidence"]["customer_sentiment"] == "UNKNOWN"
    assert context["evidence"]["loss_reason"] == "UNKNOWN"


# Performance (section 44): 10,000 synthetic opportunities, no Mongo, no AI.
def test_performance_with_ten_thousand_synthetic_opportunities():
    import time

    now = datetime.now(timezone.utc)
    started = time.perf_counter()
    signal_counts = 0
    for index in range(10000):
        opportunity = _opportunity(
            now,
            id=f"opp-{index}",
            created_at=iso_days_ago(index % 20, now),
            temperature="QUENTE" if index % 3 == 0 else "FRIO",
            probability=(index % 100),
            timeline=[{"id": "t1", "type": "PROPOSAL_SENT", "created_at": iso_days_ago(index % 15, now)}],
        )
        context = build_commercial_context("company-perf", opportunity, now=now)
        signal_counts += len(context["context"]["signals"])
    elapsed = time.perf_counter() - started
    assert elapsed < 15.0
    assert signal_counts > 0
