"""Phase 3.3 — Sales Intelligence Engine (unit tests)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from commercial_context import build_commercial_context
from sales_intelligence import (
    MIN_BEHAVIOR_SAMPLE_SIZE,
    SALES_INTELLIGENCE_VERSION,
    build_customer_behavior,
    build_sales_insight,
)

pytestmark = pytest.mark.unit


def iso_days_ago(days, now):
    return (now - timedelta(days=days)).isoformat()


def _opportunity(now, **overrides):
    base = {
        "id": "opp-1",
        "client_id": "client-1",
        "seller_id": "seller-1",
        "seller_name": "Vendedor",
        "title": "Venda de motores",
        "status": "OPEN",
        "stage": "NOVO",
        "temperature": "MORNO",
        "probability": 40,
        "estimated_value": 3000.0,
        "created_at": iso_days_ago(1, now),
        "updated_at": iso_days_ago(1, now),
        "timeline": [],
        "competitor": "",
        "loss_reason": "",
        "customer_intent": "",
        "customer_sentiment": "",
        "objection_type": "",
    }
    base.update(overrides)
    return base


def _context(opportunity, now, **kwargs):
    return build_commercial_context("company-a", opportunity, now=now, **kwargs)


def _insight(opportunity, now, **kwargs):
    context = _context(opportunity, now, **{k: v for k, v in kwargs.items() if k in {"client", "proposal", "related_opportunities", "seller_stats"}})
    return build_sales_insight("company-a", opportunity, context, now=now, **{k: v for k, v in kwargs.items() if k in {"knowledge_items", "customer_behavior", "related_loss_reasons"}})


# 1. NEW
def test_state_new_for_fresh_opportunity_with_no_history():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, created_at=now.isoformat(), timeline=[])
    insight = _insight(opportunity, now)
    assert insight["insight"]["sales_state"]["state"] == "NEW"


# 2. ACTIVE
def test_state_active_for_open_opportunity_without_specific_pattern():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, created_at=iso_days_ago(5, now), timeline=[])
    insight = _insight(opportunity, now)
    assert insight["insight"]["sales_state"]["state"] == "ACTIVE"


# 3. ENGAGED
def test_state_engaged_with_recent_multiple_activity():
    now = datetime.now(timezone.utc)
    timeline = [{"id": "1", "type": "CALL", "created_at": iso_days_ago(1, now)}, {"id": "2", "type": "NOTE", "created_at": iso_days_ago(2, now)}]
    opportunity = _opportunity(now, created_at=iso_days_ago(10, now), timeline=timeline)
    insight = _insight(opportunity, now)
    assert insight["insight"]["sales_state"]["state"] == "ENGAGED"


# 4. WAITING_CLIENT
def test_state_waiting_client_from_status():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, status="WAITING", created_at=iso_days_ago(5, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(5, now)}])
    insight = _insight(opportunity, now)
    assert insight["insight"]["sales_state"]["state"] == "WAITING_CLIENT"


# 5. NEGOTIATION
def test_state_negotiation_from_stage():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, stage="NEGOCIACAO", created_at=iso_days_ago(5, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(5, now)}])
    insight = _insight(opportunity, now)
    assert insight["insight"]["sales_state"]["state"] == "NEGOTIATION"


# 6. HIGH_INTENT
def test_state_high_intent_requires_multiple_objective_signals():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(
        now, probability=80, temperature="QUENTE", created_at=iso_days_ago(5, now),
        last_customer_response_at=iso_days_ago(1, now),
        timeline=[{"id": "1", "type": "CALL", "created_at": iso_days_ago(1, now)}],
    )
    insight = _insight(opportunity, now)
    assert insight["insight"]["sales_state"]["state"] == "HIGH_INTENT"
    # Temperature alone must never be sufficient proof.
    weak = _opportunity(now, probability=10, temperature="QUENTE", created_at=iso_days_ago(5, now), timeline=[])
    assert _insight(weak, now)["insight"]["sales_state"]["state"] != "HIGH_INTENT"


# 7. STALE
def test_state_stale_with_low_probability():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, probability=20, created_at=iso_days_ago(20, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(10, now)}])
    insight = _insight(opportunity, now)
    assert insight["insight"]["sales_state"]["state"] == "STALE"


# 8. AT_RISK
def test_state_at_risk_with_high_probability_and_stale():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, probability=70, created_at=iso_days_ago(20, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(10, now)}])
    insight = _insight(opportunity, now)
    assert insight["insight"]["sales_state"]["state"] == "AT_RISK"


# 9. WON
def test_state_won_never_recommends_followup():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, status="WON")
    insight = _insight(opportunity, now)
    assert insight["insight"]["sales_state"]["state"] == "WON"
    assert insight["insight"]["followup_state"]["state"] == "NOT_NEEDED"
    assert all(item["action"] == "NO_ACTION" for item in insight["recommendations"])


# 10. LOST
def test_state_lost():
    now = datetime.now(timezone.utc)
    insight = _insight(_opportunity(now, status="LOST"), now)
    assert insight["insight"]["sales_state"]["state"] == "LOST"


# 11. CANCELLED
def test_state_cancelled():
    now = datetime.now(timezone.utc)
    insight = _insight(_opportunity(now, status="CANCELLED"), now)
    assert insight["insight"]["sales_state"]["state"] == "CANCELLED"


# 12. priority / 13. urgency
def test_priority_and_urgency_are_consistent_with_followup_state():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, probability=70, created_at=iso_days_ago(40, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(35, now)}])
    insight = _insight(opportunity, now)
    assert insight["priority"] == "P0_CRITICAL"
    assert insight["urgency"] == "IMMEDIATE"


# 14. commercial risk
def test_commercial_risk_high_when_probability_and_stale_combine():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, probability=75, created_at=iso_days_ago(15, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(8, now)}])
    insight = _insight(opportunity, now)
    assert insight["insight"]["commercial_risk"]["level"] == "HIGH"


# 15. commercial opportunity
def test_commercial_opportunity_high_with_probability_and_recent_activity():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, probability=80, created_at=iso_days_ago(5, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(1, now)}])
    insight = _insight(opportunity, now)
    assert insight["insight"]["commercial_opportunity"]["level"] in {"HIGH", "CRITICAL"}


# 16. followup state
def test_followup_state_due_overdue_urgent_progression():
    now = datetime.now(timezone.utc)
    due = _opportunity(now, created_at=iso_days_ago(20, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(8, now)}])
    urgent = _opportunity(now, created_at=iso_days_ago(60, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(29, now)}])
    assert _insight(due, now)["insight"]["followup_state"]["state"] in {"DUE", "OVERDUE"}
    assert _insight(urgent, now)["insight"]["followup_state"]["state"] == "URGENT"


# 17. recommendation
def test_recommendation_contains_follow_up_when_due():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, created_at=iso_days_ago(20, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(8, now)}])
    insight = _insight(opportunity, now)
    actions = {item["action"] for item in insight["recommendations"]}
    assert "FOLLOW_UP" in actions


# 18. evidence
def test_every_recommendation_has_traceable_evidence():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, created_at=iso_days_ago(20, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(8, now)}])
    insight = _insight(opportunity, now)
    for recommendation in insight["recommendations"]:
        for evidence in recommendation["evidence"]:
            assert {"source", "source_id", "field", "value", "calculation", "strength"} <= set(evidence)
            assert evidence["strength"] in {"WEAK", "MODERATE", "STRONG", "VERY_STRONG"}


# 19. confidence
def test_confidence_is_bounded_and_distinct_from_probability():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, probability=90)
    insight = _insight(opportunity, now)
    assert 0.0 <= insight["confidence"] <= 1.0
    assert insight["insight"]["probability_source"]["value"] == 90
    assert insight["confidence"] != 90


# 20. fact vs inference
def test_fact_vs_inference_types_are_distinguished():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, competitor="ConcorrenteX")
    insight = _insight(opportunity, now)
    assert insight["insight"]["competitor"]["type"] == "FACT"
    assert insight["insight"]["loss_reason"]["type"] == "UNKNOWN"


# 21. UNKNOWN
def test_unknown_fields_stay_unknown_without_evidence():
    now = datetime.now(timezone.utc)
    insight = _insight(_opportunity(now), now)
    assert insight["insight"]["competitor"]["type"] == "UNKNOWN"
    assert insight["insight"]["customer_intent"]["type"] == "UNKNOWN"


# 22. insufficient sample
def test_insufficient_behavior_sample_is_not_used_as_strong_evidence():
    now = datetime.now(timezone.utc)
    behavior = build_customer_behavior(response_times_days=[2.0, 3.0])
    assert behavior["average_response_time"]["value"] is None
    assert behavior["average_response_time"]["sample_size"] == 2
    assert behavior["average_response_time"]["confidence"] == 0.0


# 23. behavior history
def test_sufficient_behavior_sample_computes_average_and_confidence():
    behavior = build_customer_behavior(response_times_days=[2.0, 2.0, 2.0, 3.0, 3.5])
    metric = behavior["average_response_time"]
    assert metric["sample_size"] == 5
    assert metric["value"] == 2.5
    assert metric["confidence"] > 0


# 24. price signal
def test_price_signal_detected_only_with_objection_evidence():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, objection_type="preco")
    insight = _insight(opportunity, now)
    assert insight["insight"]["price_signal"]["status"] == "PRICE_REVIEW_POSSIBLE"
    actions = {item["action"] for item in insight["recommendations"]}
    assert "REVIEW_PRICE" in actions


# 25. competitor unknown
def test_competitor_remains_unknown_without_evidence():
    now = datetime.now(timezone.utc)
    insight = _insight(_opportunity(now), now)
    assert insight["insight"]["competitor"]["type"] == "UNKNOWN"


# 26. loss reason unknown
def test_loss_reason_remains_unknown_without_evidence():
    now = datetime.now(timezone.utc)
    insight = _insight(_opportunity(now), now)
    assert insight["insight"]["loss_reason"]["type"] == "UNKNOWN"


# 27. deterministic
def test_deterministic_output_for_same_inputs():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, probability=70, created_at=iso_days_ago(15, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(8, now)}])
    context = _context(opportunity, now)
    first = build_sales_insight("company-a", opportunity, context, now=now)
    second = build_sales_insight("company-a", opportunity, context, now=now)
    assert first == second


# 28. idempotency
def test_idempotency_same_snapshot_yields_same_insight_id():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now)
    context = _context(opportunity, now)
    first = build_sales_insight("company-a", opportunity, context, now=now)
    second = build_sales_insight("company-a", opportunity, context, now=now + timedelta(hours=2))
    assert first["insight_id"] == second["insight_id"]


# 29. versioning
def test_versioning_fields_are_recorded():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now)
    context = _context(opportunity, now)
    insight = build_sales_insight("company-a", opportunity, context, now=now)
    assert insight["engine_version"] == SALES_INTELLIGENCE_VERSION
    assert insight["context_version"] == context["snapshot_version"]


# 30. multi-tenant (module-level: company_id is explicit input, never inferred)
def test_company_id_is_explicit_and_recorded():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now)
    context_a = build_commercial_context("company-a", opportunity, now=now)
    context_b = build_commercial_context("company-b", opportunity, now=now)
    insight_a = build_sales_insight("company-a", opportunity, context_a, now=now)
    insight_b = build_sales_insight("company-b", opportunity, context_b, now=now)
    assert insight_a["company_id"] == "company-a"
    assert insight_b["company_id"] == "company-b"
    assert insight_a["insight_id"] != insight_b["insight_id"]


# Fundamental test (section 45)
def test_fundamental_scenario_stale_overdue_high_priority_followup():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(
        now,
        probability=70,
        temperature="QUENTE",
        created_at=iso_days_ago(10, now),
        timeline=[{"id": "1", "type": "PROPOSAL_SENT", "created_at": iso_days_ago(7, now)}],
    )
    behavior = build_customer_behavior(response_times_days=[2.3] * 17)
    context = _context(opportunity, now, proposal={"id": "prop-1", "status": "aberto", "grand_total": 3000.0, "created_at": iso_days_ago(9, now), "updated_at": iso_days_ago(8, now), "products": []})
    insight = build_sales_insight("company-a", opportunity, context, customer_behavior=behavior, now=now)

    assert insight["insight"]["sales_state"]["state"] in {"STALE", "AT_RISK"}
    assert insight["insight"]["followup_state"]["state"] == "OVERDUE"
    assert insight["priority"] in {"P0_CRITICAL", "P1_HIGH"}
    actions = {item["action"] for item in insight["recommendations"]}
    assert "FOLLOW_UP" in actions


# False-certainty test (section 46)
def test_false_certainty_never_fabricated():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, loss_reason="", competitor="", customer_intent="", customer_sentiment="")
    insight = _insight(opportunity, now)
    for field in ("loss_reason", "competitor", "customer_intent", "customer_sentiment"):
        assert insight["insight"][field]["type"] == "UNKNOWN"
    forbidden = {"perdeu por preco", "cliente perdeu", "cliente gostou", "vai comprar"}
    assert not any(phrase in str(insight).lower() for phrase in forbidden)


# Knowledge dominance test (section 48)
def test_knowledge_alone_cannot_produce_high_priority_recommendation():
    now = datetime.now(timezone.utc)
    weak_opportunity = _opportunity(now, probability=10, created_at=iso_days_ago(1, now), timeline=[])
    strong_knowledge = [{"observation_id": "obs-1", "status": "ACTIVE", "confidence": 0.99, "support_count": 1000}] * 5
    insight = _insight(weak_opportunity, now, knowledge_items=strong_knowledge)
    assert insight["priority"] in {"P3_LOW", "P4_NONE"}
    assert not any(item["action"] == "FOLLOW_UP" for item in insight["recommendations"])


# Determinism at scale (section 50): run 100 times, identical results.
def test_determinism_across_one_hundred_runs():
    now = datetime.now(timezone.utc)
    opportunity = _opportunity(now, probability=70, created_at=iso_days_ago(15, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(8, now)}])
    context = _context(opportunity, now)
    results = [build_sales_insight("company-a", opportunity, context, now=now) for _ in range(100)]
    assert all(result == results[0] for result in results)


# Performance (section 51): 10,000 synthetic Commercial Contexts, no Mongo, no AI.
def test_performance_with_ten_thousand_synthetic_contexts_is_deterministic():
    import time

    now = datetime.now(timezone.utc)
    started = time.perf_counter()
    priorities = set()
    for index in range(10000):
        opportunity = _opportunity(
            now,
            id=f"opp-{index}",
            probability=index % 100,
            created_at=iso_days_ago(index % 40, now),
            timeline=[{"id": "t1", "type": "NOTE", "created_at": iso_days_ago(index % 30, now)}],
        )
        context = _context(opportunity, now)
        insight = build_sales_insight("company-perf", opportunity, context, now=now)
        priorities.add(insight["priority"])
    elapsed = time.perf_counter() - started
    assert elapsed < 20.0
    assert priorities <= set(("P0_CRITICAL", "P1_HIGH", "P2_MEDIUM", "P3_LOW", "P4_NONE"))

    # Same input, same output (determinism at scale, run twice on one sample).
    opportunity = _opportunity(now, probability=70, created_at=iso_days_ago(15, now), timeline=[{"id": "1", "type": "NOTE", "created_at": iso_days_ago(8, now)}])
    context = _context(opportunity, now)
    first = build_sales_insight("company-perf", opportunity, context, now=now)
    second = build_sales_insight("company-perf", opportunity, context, now=now)
    assert first == second
