from datetime import datetime, timezone

import pytest

from action_planning import (
    ACTION_PLANNING_VERSION,
    build_action_plan,
    compute_source_snapshot_hash,
)

pytestmark = pytest.mark.unit


def _inputs(recommendations=None, confidence=0.85, risk="HIGH", urgency="TODAY", data_quality="PARTIAL"):
    opportunity = {"id": "opp-1", "company_id": "company-1"}
    context = {
        "context_id": "ctx-1",
        "opportunity_id": "opp-1",
        "company_id": "company-1",
        "snapshot_version": "1.0.0",
        "source_snapshot_hash": "context-hash",
        "context": {"data_quality": data_quality, "proposal": {"proposal_id": "proposal-1"}},
    }
    insight = {
        "insight_id": "insight-1",
        "company_id": "company-1",
        "opportunity_id": "opp-1",
        "context_id": "ctx-1",
        "context_version": "1.0.0",
        "engine_version": "1.0.0",
        "priority": "P1_HIGH",
        "urgency": urgency,
        "confidence": confidence,
        "evidence": [{"source": "sales_intelligence", "source_id": "insight-1", "field": "followup_state", "value": "OVERDUE"}],
        "insight": {"commercial_risk": {"level": risk}},
        "recommendations": recommendations if recommendations is not None else [{
            "action": "FOLLOW_UP", "channel": "UNKNOWN", "priority": "P1_HIGH", "reason": "Proposta sem atividade há 8 dias.", "confidence": 0.91,
            "evidence": [{"source": "sales_intelligence", "source_id": "insight-1", "field": "followup_state", "value": "OVERDUE"}],
        }],
    }
    return opportunity, insight, context


def test_follow_up_has_advisory_fields_and_unknown_channel():
    opportunity, insight, context = _inputs()
    plan = build_action_plan("company-1", opportunity, insight, context)
    action = plan["actions"][0]
    assert action["type"] == "FOLLOW_UP"
    assert action["channel"] == "UNKNOWN"
    assert action["priority"] == "P1_HIGH"
    assert action["urgency"] == "TODAY"
    assert action["recommended_window"] == "WITHIN_24_HOURS"
    assert action["objective"]
    assert action["reason"]
    assert action["evidence"]
    assert action["status"] == "PENDING_APPROVAL"
    assert plan["plan"]["plan_risk"] == "HIGH"


def test_dependency_order_is_deterministic():
    recommendations = [
        {"action": "FOLLOW_UP", "channel": "UNKNOWN", "priority": "P1_HIGH", "reason": "follow-up", "confidence": 0.8, "evidence": [{"field": "followup_state"}]},
        {"action": "REVIEW_PROPOSAL", "channel": "UNKNOWN", "priority": "P1_HIGH", "reason": "review", "confidence": 0.7, "evidence": [{"field": "sales_state"}]},
    ]
    opportunity, insight, context = _inputs(recommendations)
    plan = build_action_plan("company-1", opportunity, insight, context)
    assert [item["type"] for item in plan["actions"]] == ["REVIEW_PROPOSAL", "FOLLOW_UP"]
    assert plan["actions"][0]["sequence"] == 1
    assert plan["actions"][1]["sequence"] == 2
    assert plan["actions"][1]["depends_on"] == [plan["actions"][0]["action_id"]]


def test_price_review_never_becomes_discount_and_unknown_intent_is_not_invented():
    recommendations = [{"action": "REVIEW_PRICE", "channel": "UNKNOWN", "priority": "P2_MEDIUM", "reason": "Evidência de preço disponível.", "confidence": 0.7, "evidence": [{"field": "objection_type", "value": "price"}]}]
    opportunity, insight, context = _inputs(recommendations)
    plan = build_action_plan("company-1", opportunity, insight, context)
    assert plan["actions"][0]["type"] == "REVIEW_PRICE"
    assert "discount" not in str(plan).lower()
    assert "concorrente" not in str(plan).lower()


def test_duplicate_recommendations_are_removed_and_no_action_is_terminal():
    recommendations = [
        {"action": "FOLLOW_UP", "reason": "one", "confidence": 0.8},
        {"action": "FOLLOW_UP", "reason": "two", "confidence": 0.9},
        {"action": "NO_ACTION", "reason": "fallback", "confidence": 0.4},
    ]
    opportunity, insight, context = _inputs(recommendations)
    plan = build_action_plan("company-1", opportunity, insight, context)
    assert [item["type"] for item in plan["actions"]] == ["FOLLOW_UP"]


def test_conflict_or_insufficient_evidence_forces_human_review():
    opportunity, insight, context = _inputs(confidence=0.4, data_quality="INSUFFICIENT")
    insight["evidence"] = [{"type": "CONFLICT", "field": "mapping", "value": "ambiguous"}]
    plan = build_action_plan("company-1", opportunity, insight, context, knowledge_items=[{"confidence": 1.0, "support_count": 1000}])
    assert [item["type"] for item in plan["actions"]] == ["HUMAN_REVIEW"]


def test_knowledge_alone_cannot_create_follow_up():
    opportunity, insight, context = _inputs(recommendations=[], confidence=0.1, data_quality="INSUFFICIENT")
    insight["evidence"] = []
    plan = build_action_plan("company-1", opportunity, insight, context, knowledge_items=[{"confidence": 1.0, "support_count": 1000}])
    assert [item["type"] for item in plan["actions"]] == ["HUMAN_REVIEW"]


def test_snapshot_hash_and_plan_are_deterministic_without_timestamp():
    opportunity, insight, context = _inputs()
    first_hash = compute_source_snapshot_hash(insight, context)
    second_hash = compute_source_snapshot_hash({**insight, "calculation_timestamp": "later"}, context)
    first = build_action_plan("company-1", opportunity, insight, context, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    second = build_action_plan("company-1", opportunity, insight, context, now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert first_hash == second_hash
    assert first["action_plan_id"] == second["action_plan_id"]
    assert first["source_snapshot_hash"] == second["source_snapshot_hash"]
    assert first["engine_version"] == ACTION_PLANNING_VERSION


@pytest.mark.parametrize("field", ["company_id", "opportunity_id", "context_id", "context_version"])
def test_consistency_checks_abort_mismatched_inputs(field):
    opportunity, insight, context = _inputs()
    if field == "company_id":
        insight["company_id"] = "other"
    elif field == "opportunity_id":
        insight["opportunity_id"] = "other"
    elif field == "context_id":
        insight["context_id"] = "other"
    else:
        insight["context_version"] = "other"
    with pytest.raises(ValueError):
        build_action_plan("company-1", opportunity, insight, context)


def test_stale_insight_is_rejected():
    opportunity, insight, context = _inputs()
    context["context_id"] = "new-context"
    with pytest.raises(ValueError, match="STALE_INSIGHT"):
        build_action_plan("company-1", opportunity, insight, context)


def test_performance_with_ten_thousand_sales_insights_is_deterministic():
    import time

    started = time.perf_counter()
    plans = []
    for index in range(10000):
        opportunity, insight, context = _inputs()
        opportunity["id"] = f"opp-{index}"
        insight["opportunity_id"] = opportunity["id"]
        insight["insight_id"] = f"insight-{index}"
        context["opportunity_id"] = opportunity["id"]
        context["context_id"] = f"ctx-{index}"
        insight["context_id"] = context["context_id"]
        plans.append(build_action_plan("company-1", opportunity, insight, context))
    elapsed = time.perf_counter() - started
    assert elapsed < 20.0
    assert len({plan["action_plan_id"] for plan in plans}) == 10000

    opportunity, insight, context = _inputs()
    first = build_action_plan("company-1", opportunity, insight, context)
    second = build_action_plan("company-1", opportunity, insight, context)
    assert first["action_plan_id"] == second["action_plan_id"]
    assert first["source_snapshot_hash"] == second["source_snapshot_hash"]
