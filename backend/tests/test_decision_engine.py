import json
from time import perf_counter

import pytest

from decision_engine import (
    AUTO_MIN_MARGIN,
    DECISION_ENGINE_VERSION,
    DecisionState,
    decide_mapping_candidates,
)

pytestmark = pytest.mark.unit


def candidate(target="client_name", score=0.95, evidence=None):
    return {
        "target_field": target,
        "score": score,
        "evidence": evidence or [
            {"type": "NAME_MATCH", "score": 1.0, "weight": 0.35, "detail": "exact alias"},
            {"type": "TYPE_COMPATIBILITY", "score": 1.0, "weight": 0.18, "detail": "compatible"},
            {"type": "PATTERN_COMPATIBILITY", "score": 1.0, "weight": 0.18, "detail": "pattern"},
        ],
    }


def mapping(sources, warnings=None):
    return {
        "mapping_engine_version": "1.0.0",
        "import_batch_id": "batch-1",
        "structure_profile_id": "profile-1",
        "candidates": sources,
        "warnings": warnings or [],
    }


def source(name="Campo", index=0, sheet="Aba", candidates=None, **extra):
    return {
        "source_field": {"source_name": name, "source_index": index, "sheet_name": sheet, **extra},
        "candidates": candidates or [],
    }


def decision(result):
    return result["decisions"][0]


def test_auto_requires_high_score_margin_and_strong_evidence():
    result = decide_mapping_candidates(mapping([source(candidates=[candidate(score=0.99), candidate("client_code", 0.20)])]))
    item = decision(result)
    assert item["decision"] == DecisionState.AUTO.value
    assert item["margin"] == 0.79
    assert item["candidate_score"] == 0.99
    assert "candidate_score" in item and "decision_score" in item
    assert 0.0 <= item["decision_score"] <= 1.0
    assert item["decision_engine_version"] == DECISION_ENGINE_VERSION
    assert item["decision_reasons"][0]["code"] == "AUTO_HIGH_SCORE_HIGH_MARGIN"


def test_low_margin_blocks_auto():
    item = decision(decide_mapping_candidates(mapping([source(candidates=[candidate(score=0.99), candidate("client_code", 0.96)])])))
    assert item["decision"] == "CONFIRM"
    assert "INSUFFICIENT_MARGIN" in {reason["code"] for reason in item["blocking_reasons"]}


def test_conflict_blocks_auto():
    evidence = candidate().get("evidence") + [{"type": "CONFLICT", "score": 0.0, "weight": 0.0, "detail": "financial conflict"}]
    item = decision(decide_mapping_candidates(mapping([source(candidates=[candidate(score=0.94, evidence=evidence), candidate("item_total", 0.30)])])))
    assert item["decision"] != "AUTO"
    assert "HIGH_COMPETITION" in {reason["code"] for reason in item["blocking_reasons"]}


def test_collision_blocks_auto_for_two_sources_same_target():
    result = decide_mapping_candidates(mapping([
        source("CNPJ", 0, candidates=[candidate("client_document", 0.98)]),
        source("Documento", 1, candidates=[candidate("client_document", 0.97)]),
    ]))
    assert all(item["decision"] != "AUTO" for item in result["decisions"])
    assert all("TARGET_COLLISION" in {reason["code"] for reason in item["blocking_reasons"]} for item in result["decisions"])


def test_type_incompatibility_blocks_auto():
    evidence = candidate().get("evidence") + [{"type": "TYPE_COMPATIBILITY", "score": 0.0, "weight": 0.18, "detail": "incompatible date"}]
    item = decision(decide_mapping_candidates(mapping([source(candidates=[candidate(score=0.95, evidence=evidence)])])))
    assert item["decision"] != "AUTO"
    assert "TYPE_CONFLICT" in {reason["code"] for reason in item["blocking_reasons"]}


def test_suggest_confirm_unknown_and_empty():
    suggest = decision(decide_mapping_candidates(mapping([source(candidates=[candidate(score=0.80), candidate("client_code", 0.30)])])))
    confirm = decision(decide_mapping_candidates(mapping([source(candidates=[candidate(score=0.80), candidate("client_code", 0.77)])])))
    unknown = decision(decide_mapping_candidates(mapping([source(candidates=[candidate(score=0.40)])])))
    empty = decision(decide_mapping_candidates(mapping([source(candidates=[])])))
    assert suggest["decision"] == "SUGGEST"
    assert confirm["decision"] == "CONFIRM"
    assert unknown["decision"] == "UNKNOWN"
    assert empty["decision"] == "UNKNOWN"
    assert empty["selected_candidate"] is None


def test_single_candidate_margin_is_top_score_and_never_invented():
    item = decision(decide_mapping_candidates(mapping([source(candidates=[candidate(score=0.95)])])))
    assert item["runner_up"] is None
    assert item["margin"] == 0.95


def test_score_bounds_fail_closed():
    for invalid in (-0.01, 1.01, "0.9"):
        with pytest.raises(ValueError):
            decide_mapping_candidates(mapping([source(candidates=[candidate(score=invalid)])]))


def test_duplicate_source_identity_is_blocked():
    result = decide_mapping_candidates(mapping([
        source("Código", 0, "Produtos", [candidate("product_code", 0.98)], duplicate=True),
    ]))
    item = decision(result)
    assert item["decision"] != "AUTO"
    assert "DUPLICATE_SOURCE" in {reason["code"] for reason in item["blocking_reasons"]}


def test_determinism_and_summary():
    document = mapping([source("CNPJ", candidates=[candidate("client_document", 0.99), candidate("client_code", 0.20)])])
    first = decide_mapping_candidates(document)
    second = decide_mapping_candidates(document)
    assert first == second
    assert first["summary"] == {"total": 1, "auto": 1, "suggest": 0, "confirm": 0, "unknown": 0}


def test_required_unmapped_is_not_a_business_blocker():
    result = decide_mapping_candidates(mapping([source("Opcional", candidates=[])]))
    assert result["summary"]["unknown"] == 1
    assert result["decisions"][0]["decision"] == "UNKNOWN"


def test_large_structure_profile_is_fast_bounded_and_deterministic():
    sources = [
        source(f"Coluna {index:02d}", index=index, sheet="Grande", candidates=[candidate(f"client_name", 0.80), candidate("client_code", 0.30)])
        for index in range(20)
    ]
    document = mapping(sources)
    document["global_statistics"] = {"total_rows": 10000, "total_columns": 20}
    started = perf_counter()
    outputs = [decide_mapping_candidates(document) for _ in range(3)]
    elapsed = perf_counter() - started
    assert elapsed < 2.0
    assert outputs[0] == outputs[1] == outputs[2]
    assert len(outputs[0]["decisions"]) == 20
    assert len(json.dumps(outputs[0])) < 200000
