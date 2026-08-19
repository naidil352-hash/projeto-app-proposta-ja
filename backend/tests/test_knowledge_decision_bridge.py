"""Phase 3.1 — Knowledge -> Decision Intelligence bridge (unit tests).

These tests exercise only pure functions: no Mongo, no server wiring.
"""
from __future__ import annotations

import pytest

from decision_engine import DecisionState, decide_mapping_candidates
from knowledge_adapter import (
    KNOWLEDGE_ADAPTER_VERSION,
    MAX_KNOWLEDGE_INFLUENCE,
    MIN_CONFIDENCE_FOR_EVIDENCE,
    MIN_SUPPORT_FOR_EVIDENCE,
    build_learned_evidence,
    build_learned_evidence_index,
    bounded_influence,
)
from learning_engine import pattern_signature

pytestmark = pytest.mark.unit


def _profile():
    return {
        "sheets": [{
            "sheet_name": "Clientes",
            "columns": [{
                "source_name": "CNPJ",
                "source_index": 0,
                "data_type": "STRING",
                "pattern_flags": ["CNPJ_LIKE"],
            }],
        }],
    }


def _source_pattern():
    return {"normalized_name": "CNPJ", "type": "STRING", "sheet_context": "Clientes", "patterns": ["CNPJ_LIKE"]}


def _knowledge(status="ACTIVE", confidence=0.9, support=10, target="client_document"):
    return {
        "status": status,
        "confidence": confidence,
        "support_count": support,
        "target_field": target,
        "pattern_signature": pattern_signature(_source_pattern(), target),
    }


def _mapping_document(score=0.99, runner_score=0.2, target="client_document"):
    return {
        "mapping_engine_version": "1.0.0",
        "candidates": [{
            "source_field": {"sheet_name": "Clientes", "source_index": 0, "source_name": "CNPJ"},
            "candidates": [
                {
                    "target_field": target,
                    "score": score,
                    "evidence": [
                        {"type": "NAME_MATCH", "score": 1.0, "weight": 0.35, "detail": "exact"},
                        {"type": "TYPE_COMPATIBILITY", "score": 1.0, "weight": 0.18, "detail": "compatible"},
                        {"type": "PATTERN_COMPATIBILITY", "score": 1.0, "weight": 0.18, "detail": "CNPJ_LIKE"},
                    ],
                },
                {"target_field": "client_code", "score": runner_score, "evidence": []},
            ],
        }],
    }


def _decision(result):
    return result["decisions"][0]


# ---------- Knowledge Adapter ----------

def test_knowledge_adapter_builds_index_only_for_existing_candidates():
    index = build_learned_evidence_index(_profile(), _mapping_document(), [_knowledge()])
    assert ("Clientes", 0, "CNPJ", "client_document") in index
    assert len(index) == 1


def test_knowledge_adapter_ignores_mismatched_signature():
    mismatched = _knowledge()
    mismatched["pattern_signature"] = pattern_signature({**_source_pattern(), "type": "DECIMAL"}, "client_document")
    index = build_learned_evidence_index(_profile(), _mapping_document(), [mismatched])
    assert index == {}


def test_knowledge_adapter_empty_when_no_profile_or_knowledge():
    assert build_learned_evidence_index(None, _mapping_document(), [_knowledge()]) == {}
    assert build_learned_evidence_index(_profile(), _mapping_document(), []) == {}


# ---------- Learned Evidence ----------

def test_learned_evidence_shape_for_active_knowledge():
    evidence = build_learned_evidence(_knowledge())
    assert evidence["type"] == "LEARNED_MATCH"
    assert 0.0 <= evidence["score"] <= 1.0
    assert evidence["weight"] > 0


def test_learned_evidence_conflict_for_conflicted_knowledge():
    evidence = build_learned_evidence(_knowledge(status="CONFLICTED"))
    assert evidence["type"] == "LEARNED_CONFLICT"
    assert evidence["weight"] == 0.0


def test_learned_evidence_none_for_disabled_expired_and_weak_signals():
    assert build_learned_evidence(_knowledge(status="DISABLED")) is None
    assert build_learned_evidence(_knowledge(status="EXPIRED")) is None
    assert build_learned_evidence(_knowledge(support=MIN_SUPPORT_FOR_EVIDENCE - 1)) is None
    assert build_learned_evidence(_knowledge(confidence=MIN_CONFIDENCE_FOR_EVIDENCE - 0.01)) is None
    assert build_learned_evidence(None) is None


# ---------- Evidence Fusion ----------

def test_evidence_fusion_adds_learned_entry_to_decision_evidence():
    index = build_learned_evidence_index(_profile(), _mapping_document(), [_knowledge()])
    result = decide_mapping_candidates(_mapping_document(), learned_evidence_index=index)
    decision = _decision(result)
    assert any(item["type"] == "LEARNED_MATCH" for item in decision["evidence"])


def test_knowledge_influence_limit_never_exceeds_cap():
    index = build_learned_evidence_index(_profile(), _mapping_document(), [_knowledge(confidence=1.0, support=1000)])
    baseline = _decision(decide_mapping_candidates(_mapping_document()))
    fused = _decision(decide_mapping_candidates(_mapping_document(), learned_evidence_index=index))
    assert fused["knowledge_influence"] <= MAX_KNOWLEDGE_INFLUENCE
    assert round(fused["decision_score"] - baseline["decision_score"], 4) <= MAX_KNOWLEDGE_INFLUENCE
    assert bounded_influence({"weight": 999, "score": 999}) == MAX_KNOWLEDGE_INFLUENCE


def test_knowledge_dominance_protection_cannot_promote_decision_state():
    # Weak structural candidate: baseline would never be AUTO on its own.
    weak_document = _mapping_document(score=0.5, runner_score=0.48)
    baseline = _decision(decide_mapping_candidates(weak_document))
    index = build_learned_evidence_index(_profile(), weak_document, [_knowledge(confidence=1.0, support=1000)])
    fused = _decision(decide_mapping_candidates(weak_document, learned_evidence_index=index))
    assert baseline["decision"] != DecisionState.AUTO.value
    assert fused["decision"] == baseline["decision"]


def test_conflict_protection_downgrades_auto_to_confirm():
    strong_document = _mapping_document(score=0.99, runner_score=0.2)
    baseline = _decision(decide_mapping_candidates(strong_document))
    conflicted_knowledge = _knowledge(status="CONFLICTED")
    index = build_learned_evidence_index(_profile(), strong_document, [conflicted_knowledge])
    fused = _decision(decide_mapping_candidates(strong_document, learned_evidence_index=index))
    assert baseline["decision"] == DecisionState.AUTO.value
    assert fused["decision"] == DecisionState.CONFIRM.value
    assert any(reason["code"] == "LEARNING_CONFLICT" for reason in fused["blocking_reasons"])


def test_determinism_of_fusion_is_stable_across_runs():
    index = build_learned_evidence_index(_profile(), _mapping_document(), [_knowledge()])
    first = decide_mapping_candidates(_mapping_document(), learned_evidence_index=index)
    second = decide_mapping_candidates(_mapping_document(), learned_evidence_index=index)
    assert first == second


def test_no_knowledge_matches_phase_2_2b_baseline():
    without_param = decide_mapping_candidates(_mapping_document())
    with_empty_index = decide_mapping_candidates(_mapping_document(), learned_evidence_index={})
    decision_without = _decision(without_param)
    decision_with_empty = _decision(with_empty_index)
    assert decision_without["decision"] == decision_with_empty["decision"]
    assert decision_without["decision_score"] == decision_with_empty["decision_score"]
    assert decision_without["knowledge_adapter_version"] is None
    assert decision_with_empty["knowledge_adapter_version"] == KNOWLEDGE_ADAPTER_VERSION


def test_versioning_field_present_when_bridge_is_used():
    index = build_learned_evidence_index(_profile(), _mapping_document(), [_knowledge()])
    fused = _decision(decide_mapping_candidates(_mapping_document(), learned_evidence_index=index))
    assert fused["knowledge_adapter_version"] == KNOWLEDGE_ADAPTER_VERSION
