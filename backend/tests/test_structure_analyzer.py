import pytest
from openpyxl import Workbook

from structure_analyzer import ANALYZER_VERSION, analyze_column, analyze_structure
from server import _extract_raw_records, _parse_xlsx_file

pytestmark = pytest.mark.unit


def _record(sheet, row, values):
    return {
        "source_sheet": sheet,
        "source_row": row,
        "original_record_json": values,
        "raw_metadata": {
            "header_row": 4,
            "header_detection_method": "structural",
            "header_detection_status": "DETECTED",
            "sheet_rows": 7,
            "sheet_columns": len(values),
        },
    }


def _profile(records, entries=None):
    return analyze_structure(
        {"filename": "sample.csv", "file_type": "CSV", "file_size": 10, "checksum": "abc"},
        records,
        entries,
    )


def test_csv_simple_and_header_profile():
    profile = _profile([_record("CSV", 5, {"Cliente": "ACME", "Valor": "10"})])
    sheet = profile["sheets"][0]
    assert sheet["sheet_name"] == "CSV"
    assert sheet["header_row"] == 4
    assert sheet["header_detection_status"] == "CONFIDENT"
    assert sheet["structure_status"] == "TABULAR"


def test_xlsx_simple_and_multiple_sheets():
    records = [
        _record("Orcamentos", 2, {"CNPJ": "00.000.000/0001-00", "Valor": "10.500,00"}),
        _record("Clientes", 2, {"CNPJ": "00.000.000/0001-00", "Email": "a@example.com"}),
    ]
    entries = [
        {"sheet": "Orcamentos", "rows": 2, "columns": 2, "header_row": 1, "header_detection_status": "DETECTED"},
        {"sheet": "Clientes", "rows": 2, "columns": 2, "header_row": 1, "header_detection_status": "DETECTED"},
    ]
    profile = _profile(records, entries)
    assert profile["global_statistics"]["total_sheets"] == 2
    assert {sheet["sheet_name"] for sheet in profile["sheets"]} == {"Orcamentos", "Clientes"}
    assert profile["sheet_relationship_hints"]


def test_real_xlsx_empty_sheet_is_profiled(tmp_path):
    workbook = Workbook()
    workbook.active.title = "Dados"
    workbook.active.append(["Cliente", "Valor"])
    workbook.active.append(["ACME", "10"])
    workbook.create_sheet("Vazia")
    path = tmp_path / "empty-sheet.xlsx"
    workbook.save(path)

    entries = _parse_xlsx_file(str(path))
    raw_records, _ = _extract_raw_records(str(path), "XLSX")
    profile = _profile(raw_records, entries)
    empty_sheet = next(sheet for sheet in profile["sheets"] if sheet["sheet_name"] == "Vazia")
    assert empty_sheet["structure_status"] == "EMPTY"


def test_empty_and_text_only_sheets():
    profile = _profile([], [
        {"sheet": "Vazia", "rows": 0, "columns": 0},
        {"sheet": "Observacoes", "rows": 2, "columns": 1, "header_detection_status": "AMBIGUOUS"},
    ])
    sheets = {sheet["sheet_name"]: sheet for sheet in profile["sheets"]}
    assert sheets["Vazia"]["structure_status"] == "EMPTY"
    assert sheets["Observacoes"]["structure_status"] == "TEXT_ONLY"
    assert "EMPTY_SHEET" in {warning["code"] for warning in profile["warnings"]}


def test_header_line_four_is_preserved():
    profile = _profile([_record("CSV", 5, {"Cliente": "ACME"})])
    assert profile["sheets"][0]["header_row"] == 4
    assert profile["sheets"][0]["header_detection_method"] == "structural"


@pytest.mark.parametrize(
    ("value", "expected_type"),
    [
        ("10", "INTEGER"),
        ("10.25", "DECIMAL"),
        ("R$ 10.500,00", "CURRENCY_LIKE"),
        ("01/08/2026", "DATE"),
        ("2026-08-01 14:30:00", "DATETIME"),
        ("10%", "PERCENTAGE_LIKE"),
    ],
)
def test_structural_data_types(value, expected_type):
    column = analyze_column("Valor", 0, [value, value])
    assert column["data_type"] == expected_type


def test_identifier_and_semantic_unknown():
    column = analyze_column("Referência", 0, ["ABC123", "MTR-001", "SKU-5500"])
    assert column["potential_identifier"] is True
    assert column["semantic_meaning"] == "unknown"
    assert "IDENTIFIER_LIKE" in column["pattern_flags"]


def test_null_and_cardinality_analysis():
    column = analyze_column("Status", 0, ["novo", "novo", "", None, "novo"])
    assert column["null_count"] == 2
    assert column["null_ratio"] == 0.4
    assert column["null_class"] == "MEDIUM_NULL"
    assert column["cardinality_class"] == "ALL_SAME"

    unique = analyze_column("CNPJ", 0, ["1", "2", "3", "4"])
    assert unique["cardinality_class"] == "UNIQUE_LIKE"
    assert unique["unique_ratio"] == 1.0


def test_samples_are_bounded_and_original_values_preserved():
    column = analyze_column("Nome", 0, ["João", "João", "Maria", "Pedro", "Ana", "Luís"], max_sample_values=3)
    assert len(column["sample_values"]) == 3
    assert "João" in column["sample_values"]
    assert column["source_name"] == "Nome"
    assert column["normalized_name_for_analysis"] == "nome"


def test_pattern_detection_and_mixed_types():
    email = analyze_column("Contato", 0, ["a@example.com", "b@example.com"])
    assert "EMAIL_LIKE" in email["pattern_flags"]
    phone = analyze_column("Telefone", 0, ["11999998888", "21988887777"])
    assert "PHONE_LIKE" in phone["pattern_flags"]
    cpf = analyze_column("Documento", 0, ["123.456.789-00", "987.654.321-00"])
    assert "CPF_LIKE" in cpf["pattern_flags"]
    mixed = analyze_column("Valor", 0, ["10", "indefinido"])
    assert mixed["data_type"] == "MIXED"


def test_duplicate_names_warning_and_version():
    profile = _profile(
        [_record("CSV", 2, {"Valor": "1"})],
        [{"sheet": "CSV", "rows": 2, "columns": 2, "headers": ["Valor", "Valor"], "header_row": 1}],
    )
    assert profile["analyzer_version"] == ANALYZER_VERSION
    assert any(warning["code"] == "DUPLICATE_COLUMN_NAMES" for warning in profile["warnings"])
