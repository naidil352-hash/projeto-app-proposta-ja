import copy

import pytest

from mapping_application import (
    apply_standard_records,
    build_application_plan,
    build_source_signature,
    create_confirmation,
    create_template,
    detect_template_drift,
)

pytestmark = pytest.mark.unit


def profile():
    return {"id": "profile", "import_batch_id": "batch", "sheets": [{"sheet_name": "Clientes", "columns": [{"source_name": "CNPJ", "source_index": 0, "data_type": "STRING", "pattern_flags": ["CNPJ_LIKE"]}, {"source_name": "Nome", "source_index": 1, "data_type": "STRING", "pattern_flags": []}]}]}


def confirmation(target="client_document", name="CNPJ", index=0):
    return create_confirmation("company", "batch", {"sheet_name": "Clientes", "source_name": name, "source_index": index}, target, "CONFIRM", "user")


def test_confirmation_confirm_reject_modify_and_validation():
    confirmed = confirmation()
    rejected = create_confirmation("company", "batch", {"sheet_name": "Clientes", "source_name": "Nome", "source_index": 1}, None, "REJECT", "user")
    modified = create_confirmation("company", "batch", {"sheet_name": "Clientes", "source_name": "CNPJ", "source_index": 0}, "client_code", "MODIFY", "user", confirmed, reason="manual correction")
    assert confirmed["decision"] == "CONFIRMED"
    assert rejected["decision"] == "REJECTED"
    assert modified["previous_candidate"]
    with pytest.raises(ValueError):
        create_confirmation("company", "batch", {"source_name": "X"}, "does_not_exist", "CONFIRM", "user")


def test_template_signature_version_and_drift():
    template = create_template("company", "Template", profile(), [confirmation()], "user")
    assert template["template_version"] == 1
    assert template["source_signature"] == build_source_signature(profile())
    changed = copy.deepcopy(profile())
    changed["sheets"][0]["columns"].append({"source_name": "Email", "source_index": 2, "data_type": "STRING", "pattern_flags": []})
    drift = detect_template_drift(changed, template)
    assert drift["status"] == "LOW_DRIFT"
    assert drift["changes"]


def test_application_plan_blocks_drift_and_skips_unconfirmed():
    template = create_template("company", "Template", profile(), [confirmation()], "user")
    plan = build_application_plan(profile(), [confirmation()], template)
    assert plan["summary"]["ready"] == 1
    assert plan["summary"]["skipped"] == 1
    changed = copy.deepcopy(profile())
    changed["sheets"][0]["columns"].append({"source_name": "A", "source_index": 2, "data_type": "STRING", "pattern_flags": []})
    changed["sheets"][0]["columns"].append({"source_name": "B", "source_index": 3, "data_type": "STRING", "pattern_flags": []})
    changed["sheets"][0]["columns"].append({"source_name": "C", "source_index": 4, "data_type": "STRING", "pattern_flags": []})
    blocked = build_application_plan(changed, [confirmation()], template)
    assert blocked["status"] == "BLOCKED"


def test_standard_records_preserve_raw_and_provenance():
    raw = {"id": "raw-1", "source_sheet": "Clientes", "source_row": 2, "original_record_json": {"CNPJ": "ABC"}}
    snapshot = copy.deepcopy(raw)
    plan = build_application_plan(profile(), [confirmation()])
    records, errors = apply_standard_records([raw], plan, "application", "company", "batch")
    assert raw == snapshot
    assert records[0]["data"] == {"client_document": "ABC"}
    assert records[0]["field_provenance"][0]["source"]["column"] == "CNPJ"
    assert errors[0]["error_code"] == "INVALID_SOURCE_VALUE"


def test_duplicate_raw_records_are_not_deduplicated():
    raw = [{"id": "raw-1", "source_sheet": "Clientes", "original_record_json": {"CNPJ": "1"}}, {"id": "raw-2", "source_sheet": "Clientes", "original_record_json": {"CNPJ": "1"}}]
    plan = build_application_plan(profile(), [confirmation()])
    records, _ = apply_standard_records(raw, plan, "application", "company", "batch")
    assert len(records) == 2
    assert {record["source_record_id"] for record in records} == {"raw-1", "raw-2"}
