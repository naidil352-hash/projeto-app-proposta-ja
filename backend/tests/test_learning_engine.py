from datetime import datetime, timedelta, timezone
import json
import time

import pytest

from learning_engine import (
    EVENT_TYPES,
    KNOWLEDGE_STATES,
    LEARNING_VERSION,
    build_learning_summary,
    create_learning_event,
    pattern_signature,
    project_knowledge,
)

pytestmark = pytest.mark.unit


def subject(name="vlr_unit", target="item_unit_price"):
    source = {"normalized_name": name, "type": "DECIMAL", "sheet_context": "orcamentos", "patterns": ["CURRENCY_LIKE"]}
    return {"source_pattern": source, "target_field": target, "pattern_signature": pattern_signature(source, target)}


def event(event_type, target="item_unit_price", created_at=None, event_id=None):
    return create_learning_event("company-a", event_type, "test", event_id or event_type, subject(target=target), {"value": "metadata"}, "user", event_id=event_id, created_at=created_at)


def test_event_creation_closed_types_and_version():
    created = event("MAPPING_CONFIRMED")
    assert created["learning_version"] == LEARNING_VERSION
    assert set(EVENT_TYPES)
    with pytest.raises(ValueError):
        create_learning_event("company", "INVALID", "test", "1", {}, {})


def test_event_idempotency_identity_and_privacy():
    created = event("POSITIVE_FEEDBACK", event_id="same")
    again = event("POSITIVE_FEEDBACK", event_id="same")
    assert created["event_id"] == again["event_id"]
    assert "raw_records" not in json.dumps(created).lower()
    assert "ABC" not in json.dumps(created)


def test_positive_negative_correction_confidence_and_bounds():
    events = [event("MAPPING_CONFIRMED", event_id=f"p{i}") for i in range(10)]
    events.append(event("MAPPING_MODIFIED", target="item_total", event_id="correction"))
    result = project_knowledge(events)
    assert all(0.0 <= item["confidence"] <= 1.0 for item in result)
    assert any(item["correction_count"] == 1 for item in result)
    assert any(item["status"] == "CONFLICTED" for item in result)


def test_low_support_is_conservative_and_strong_support_can_be_high():
    weak = project_knowledge([event("MAPPING_CONFIRMED", event_id="one")])[0]
    strong = project_knowledge([event("MAPPING_CONFIRMED", event_id=str(index)) for index in range(20)])[0]
    assert weak["confidence"] < 0.8
    assert strong["confidence"] > weak["confidence"]
    assert build_learning_summary([strong])["high_confidence"] == 1


def test_usage_signal_is_weaker_than_correction():
    usage = project_knowledge([event("POSITIVE_USAGE_SIGNAL", event_id="usage")])[0]
    corrected = project_knowledge([event("POSITIVE_USAGE_SIGNAL", event_id="usage"), event("CORRECTION_SIGNAL", target="item_total", event_id="correction")])
    assert usage["confidence"] > corrected[0]["confidence"] or any(item["status"] == "CONFLICTED" for item in corrected)


def test_decay_is_deterministic_and_old_knowledge_drops():
    recent = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    recent_item = project_knowledge([event("MAPPING_CONFIRMED", created_at=recent, event_id="recent")])[0]
    old_item = project_knowledge([event("MAPPING_CONFIRMED", created_at=old, event_id="old")])[0]
    assert old_item["confidence"] < recent_item["confidence"]
    assert project_knowledge([event("MAPPING_CONFIRMED", created_at=old, event_id="old")]) == project_knowledge([event("MAPPING_CONFIRMED", created_at=old, event_id="old")])


def test_expired_disabled_and_reactivation_events_are_closed():
    expired = project_knowledge([event("PATTERN_EXPIRED", event_id="expired")])[0]
    disabled = project_knowledge([event("KNOWLEDGE_DISABLED", event_id="disabled")])[0]
    assert expired["status"] in KNOWLEDGE_STATES
    assert disabled["status"] == "DISABLED"


def test_company_isolation_and_pattern_signature_context():
    source_a = {"normalized_name": "preco", "type": "DECIMAL", "sheet_context": "clientes", "patterns": []}
    source_b = {**source_a, "sheet_context": "produtos"}
    assert pattern_signature(source_a, "item_unit_price") != pattern_signature(source_b, "item_unit_price")
    a = create_learning_event("a", "MAPPING_CONFIRMED", "test", "a", {"source_pattern": source_a, "target_field": "item_unit_price"}, {})
    b = create_learning_event("b", "MAPPING_CONFIRMED", "test", "b", {"source_pattern": source_b, "target_field": "product_price"}, {})
    assert {item["company_id"] for item in project_knowledge([a, b])} == {"a", "b"}


def test_rebuild_is_projection_only():
    events = [event("MAPPING_CONFIRMED", event_id="rebuild")]
    first = project_knowledge(events)
    second = project_knowledge(events)
    assert first == second
    assert events[0]["event_type"] == "MAPPING_CONFIRMED"


def test_large_projection_is_bounded_and_fast():
    events = [event("MAPPING_CONFIRMED", event_id=str(index)) for index in range(100000)]
    started = time.perf_counter()
    result = project_knowledge(events)
    elapsed = time.perf_counter() - started
    assert elapsed < 8.0
    assert len(result) == 1
    assert result[0]["support_count"] == 100000
    assert len(json.dumps(result)) < 10000
