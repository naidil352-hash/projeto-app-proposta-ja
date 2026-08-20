import pytest

from integration_hub import IntegrationValidationError, validate_connection_definition
from tabular_preview_adapter import build_tabular_previews, normalize_tabular_table, validate_entity_mapping


pytestmark = pytest.mark.unit


def _connection(**overrides):
    value = {
        "connection_id": "arquivo-principal",
        "company_id": "company-1",
        "provider": "generic_file",
        "authentication": "NONE",
        "enabled": True,
        "source_of_truth": {
            "CLIENT": "EXTERNAL",
            "PRODUCT": "EXTERNAL",
            "PROPOSAL": "PROPOSTA_JA",
        },
    }
    value.update(overrides)
    return validate_connection_definition(value)


def test_normalizes_csv_rows_and_maps_client_to_preview_only():
    table = {"format": "csv", "source_name": "clientes.csv", "sheet_name": "Clientes", "columns": ["ID", "Nome", "CNPJ"], "rows": [["c-1", "Ana", "123"]]}
    result = build_tabular_previews(_connection(), table, {"entity": "CLIENT", "external_id_field": "ID", "fields": {"name": "Nome", "document": "CNPJ"}})
    record = result["records"][0]
    assert result["mode"] == "PREVIEW"
    assert result["will_read_files"] is False
    assert result["will_perform_external_io"] is False
    assert record["event"]["fields"] == {"name": "Ana", "document": "123"}
    assert record["preview"]["action"] == "READY_FOR_REVIEW"


def test_normalizes_xlsx_object_rows_and_maps_product():
    table = {"format": "XLSX", "columns": ["SKU", "Descrição", "Preço"], "rows": [{"SKU": "sku-1", "Descrição": "Serviço", "Preço": 19.9}]}
    result = build_tabular_previews(_connection(), table, {"entity": "PRODUCT", "external_id_field": "SKU", "fields": {"name": "Descrição", "price": "Preço"}})
    assert result["records"][0]["event"]["fields"]["price"] == 19.9


def test_proposal_export_requires_human_approval():
    table = {"format": "TABULAR", "columns": ["Código", "Valor"], "rows": [["p-1", 100]]}
    mapping = {"entity": "PROPOSAL", "external_id_field": "Código", "fields": {"total": "Valor"}}
    blocked = build_tabular_previews(_connection(), table, mapping, direction="EXPORT")
    ready = build_tabular_previews(_connection(), table, mapping, direction="EXPORT", approved=True)
    assert blocked["records"][0]["preview"]["blockers"] == ["HUMAN_APPROVAL_REQUIRED"]
    assert ready["records"][0]["preview"]["action"] == "READY_FOR_REVIEW"


def test_external_source_of_truth_blocks_export():
    table = {"columns": ["ID", "Nome"], "rows": [["c-1", "Ana"]]}
    mapping = {"entity": "CLIENT", "external_id_field": "ID", "fields": {"name": "Nome"}}
    result = build_tabular_previews(_connection(), table, mapping, direction="EXPORT", approved=True)
    assert "SOURCE_OF_TRUTH_IS_EXTERNAL" in result["records"][0]["preview"]["blockers"]


def test_same_normalized_table_generates_idempotent_events():
    table = {"format": "CSV", "columns": ["ID", "Nome"], "rows": [["c-1", "Ana"]]}
    mapping = {"entity": "CLIENT", "external_id_field": "ID", "fields": {"name": "Nome"}}
    first = build_tabular_previews(_connection(), table, mapping)
    second = build_tabular_previews(_connection(), table, mapping)
    assert first["table_fingerprint"] == second["table_fingerprint"]
    assert first["records"][0]["event"]["idempotency_key"] == second["records"][0]["event"]["idempotency_key"]


def test_rejects_duplicate_headers_unknown_fields_and_ambiguous_mapping():
    with pytest.raises(IntegrationValidationError, match="duplicate columns"):
        normalize_tabular_table({"columns": ["ID", "ID"], "rows": []})
    table = {"columns": ["ID", "Nome"], "rows": [["c-1", "Ana"]]}
    with pytest.raises(IntegrationValidationError, match="mapped headers not found"):
        validate_entity_mapping(table, {"entity": "CLIENT", "external_id_field": "ID", "fields": {"name": "Ausente"}})
    with pytest.raises(IntegrationValidationError, match="cannot map"):
        validate_entity_mapping(table, {"entity": "CLIENT", "external_id_field": "ID", "fields": {"name": "Nome", "nickname": "Nome"}})
