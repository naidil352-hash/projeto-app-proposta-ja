import json
from time import perf_counter

import pytest

from mapping_engine import (
    MAPPING_ENGINE_VERSION,
    MAX_CANDIDATES_PER_SOURCE,
    SCORE_WEIGHTS,
    generate_candidate_mappings,
    normalize_field_name,
)
from target_field_catalog import TARGET_FIELD_CATALOG

pytestmark = pytest.mark.unit


def _column(name, data_type="STRING", patterns=None, index=0, cardinality="HIGH_CARDINALITY"):
    return {
        "source_name": name,
        "source_index": index,
        "normalized_name_for_analysis": name.lower(),
        "data_type": data_type,
        "pattern_flags": patterns or [],
        "unique_count": 10,
        "unique_ratio": 1.0,
        "cardinality_class": cardinality,
        "null_ratio": 0.0,
        "sample_values": ["sample"],
    }


def _profile(columns, sheet_name="Clientes", formula_hints=None):
    return {
        "id": "structure-1",
        "import_batch_id": "batch-1",
        "analyzer_version": "1.0.0",
        "sheets": [{
            "sheet_name": sheet_name,
            "columns": columns,
            "structure_status": "TABULAR",
        }],
        "formula_relationship_hints": formula_hints or [],
    }


def _source(result, source_name, sheet_name="Clientes", index=0):
    for source in result["sources"]:
        ref = source["source_field"]
        if ref["source_name"] == source_name and ref["sheet_name"] == sheet_name and ref["source_index"] == index:
            return source
    raise AssertionError(f"source not found: {source_name}")


def _top(result, source_name, sheet_name="Clientes", index=0):
    return _source(result, source_name, sheet_name, index)["candidates"][0]


@pytest.mark.parametrize(
    ("source", "target", "data_type", "patterns"),
    [
        ("Cliente", "client_name", "STRING", []),
        ("Razão Social", "client_legal_name", "STRING", []),
        ("CNPJ", "client_document", "STRING", ["CNPJ_LIKE"]),
        ("Email", "client_email", "STRING", ["EMAIL_LIKE"]),
        ("Telefone", "client_phone", "STRING", ["PHONE_LIKE"]),
        ("SKU", "product_code", "IDENTIFIER_LIKE", ["SKU_LIKE", "IDENTIFIER_LIKE"]),
        ("Descrição", "product_description", "STRING", []),
        ("Qtd", "item_quantity", "INTEGER", []),
        ("Preço Unitário", "item_unit_price", "CURRENCY_LIKE", ["CURRENCY_LIKE"]),
        ("Total", "item_total", "CURRENCY_LIKE", ["CURRENCY_LIKE"]),
    ],
)
def test_expected_name_and_pattern_candidates(source, target, data_type, patterns):
    result = generate_candidate_mappings(_profile([_column(source, data_type, patterns)]))
    candidates = _source(result, source)["candidates"]
    candidate = next(candidate for candidate in candidates if candidate["target_field"] == target)
    assert 0.0 <= candidate["score"] <= 1.0
    assert candidate["evidence"]


def test_normalization_removes_accents_and_punctuation_without_changing_source():
    assert normalize_field_name("Razão Social") == "razao social"
    assert normalize_field_name("Vlr. Unitário (R$)") == "vlr unitario r$"
    assert normalize_field_name("Qtd.") == "qtd"
    assert normalize_field_name("DESCRIÇÃO MATERIAL") == "descricao material"


def test_catalog_has_small_extensible_schema_for_requested_entities():
    entities = {field["entity"] for field in TARGET_FIELD_CATALOG}
    assert {"CLIENT", "PROPOSAL", "PRODUCT", "PROPOSAL_ITEM", "SELLER", "COMPANY", "CONTACT", "PAYMENT", "SHIPPING", "FINANCIAL"} <= entities
    assert len(TARGET_FIELD_CATALOG) < 70
    assert all(field["aliases"] and field["compatible_types"] for field in TARGET_FIELD_CATALOG)


def test_pattern_evidence_is_explainable():
    result = generate_candidate_mappings(_profile([_column("CNPJ", "STRING", ["CNPJ_LIKE"])]))
    candidate = _top(result, "CNPJ")
    evidence_types = {evidence["type"] for evidence in candidate["evidence"]}
    assert "PATTERN_COMPATIBILITY" in evidence_types
    assert any("CNPJ_LIKE" in evidence["detail"] for evidence in candidate["evidence"])


def test_incompatible_date_does_not_score_as_price():
    result = generate_candidate_mappings(_profile([_column("Preço Unitário", "DATE", ["DATE_LIKE"])]))
    price = next(candidate for candidate in _source(result, "Preço Unitário")["candidates"] if candidate["target_field"] == "item_unit_price")
    assert price["score"] < 0.5
    assert any(evidence["score"] == 0.0 for evidence in price["evidence"] if evidence["type"] == "TYPE_COMPATIBILITY")


def test_ambiguous_value_emits_conflict_evidence():
    result = generate_candidate_mappings(_profile([_column("Valor", "CURRENCY_LIKE", ["CURRENCY_LIKE"])]), max_candidates=MAX_CANDIDATES_PER_SOURCE)
    candidates = _source(result, "Valor")["candidates"]
    assert any(any(evidence["type"] == "CONFLICT" for evidence in candidate["evidence"]) for candidate in candidates)


def test_formula_relationship_evidence_is_consumed_from_profile():
    columns = [_column("Qtd", "INTEGER"), _column("Preço", "CURRENCY_LIKE", ["CURRENCY_LIKE"], 1), _column("Total", "CURRENCY_LIKE", ["CURRENCY_LIKE"], 2)]
    hints = [{"sheet_name": "Itens", "quantity": "Qtd", "unit_price": "Preço", "total": "Total"}]
    result = generate_candidate_mappings(_profile(columns, "Itens", hints))
    for source_name, target in (("Qtd", "item_quantity"), ("Preço", "item_unit_price"), ("Total", "item_total")):
        index = {"Qtd": 0, "Preço": 1, "Total": 2}[source_name]
        candidate = next(item for item in _source(result, source_name, "Itens", index)["candidates"] if item["target_field"] == target)
        assert any(evidence["type"] == "FORMULA_RELATIONSHIP" for evidence in candidate["evidence"])


def test_ambiguous_document_uses_sheet_and_neighbor_context():
    client_profile = _profile([
        _column("Documento", "STRING", ["CNPJ_LIKE"], 0),
        _column("Razão Social", "STRING", [], 1),
    ], "Clientes")
    client_document = next(candidate for candidate in _source(generate_candidate_mappings(client_profile), "Documento")["candidates"] if candidate["target_field"] == "client_document")
    product_profile = _profile([
        _column("Documento", "STRING", [], 0),
        _column("Código", "IDENTIFIER_LIKE", ["CODE_LIKE"], 1),
        _column("Descrição", "STRING", [], 2),
    ], "Produtos")
    product_document = next(candidate for candidate in _source(generate_candidate_mappings(product_profile), "Documento", "Produtos")["candidates"] if candidate["target_field"] == "client_document")
    assert client_document["score"] > product_document["score"]
    assert product_document["score"] < 0.75


def test_target_collision_is_reported_without_resolution():
    columns = [_column("Valor", "CURRENCY_LIKE", ["CURRENCY_LIKE"], 0), _column("Valor Total", "CURRENCY_LIKE", ["CURRENCY_LIKE"], 1), _column("Total", "CURRENCY_LIKE", ["CURRENCY_LIKE"], 2)]
    result = generate_candidate_mappings(_profile(columns, "Orçamentos"))
    assert any(warning["type"] == "TARGET_COLLISION" for warning in result["warnings"])
    assert len(result["sources"]) == 3


def test_duplicate_source_columns_are_not_overwritten():
    columns = [_column("Código", "IDENTIFIER_LIKE", ["CODE_LIKE"], 0), _column("Descrição", index=1), _column("Código", "IDENTIFIER_LIKE", ["CODE_LIKE"], 2)]
    result = generate_candidate_mappings(_profile(columns, "Itens"))
    codes = [source for source in result["sources"] if source["source_field"]["source_name"] == "Código"]
    assert len(codes) == 2
    assert {source["source_field"]["source_index"] for source in codes} == {0, 2}


def test_low_signal_field_is_not_promoted_and_ranking_is_bounded():
    result = generate_candidate_mappings(_profile([_column("ABC123", "STRING", [], 0)]))
    source = _source(result, "ABC123")
    assert len(source["candidates"]) <= MAX_CANDIDATES_PER_SOURCE
    assert all(source["candidates"][index]["score"] >= source["candidates"][index + 1]["score"] for index in range(len(source["candidates"]) - 1))


def test_determinism_and_score_bounds():
    profile = _profile([_column("Cliente"), _column("Valor", "CURRENCY_LIKE", ["CURRENCY_LIKE"], 1)])
    first = generate_candidate_mappings(profile)
    second = generate_candidate_mappings(profile)
    assert first == second
    assert all(0.0 <= candidate["score"] <= 1.0 for source in first["sources"] for candidate in source["candidates"])
    assert abs(sum(SCORE_WEIGHTS.values()) - 1.0) < 0.0001


def test_performance_uses_profile_columns_not_raw_rows():
    profile = _profile([_column(f"Coluna {index:02d}", "STRING", [], index) for index in range(20)], "Grande")
    profile["global_statistics"] = {"total_rows": 10000, "total_columns": 20}
    started = perf_counter()
    result = generate_candidate_mappings(profile)
    elapsed = perf_counter() - started
    assert elapsed < 2.0
    assert len(result["sources"]) == 20
    assert all(len(source["candidates"]) <= MAX_CANDIDATES_PER_SOURCE for source in result["sources"])
    assert len(json.dumps(result)) < 200000
