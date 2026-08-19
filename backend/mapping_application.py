"""Human confirmation, templates, planning and standard-record application."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from mapping_engine import normalize_field_name
from target_field_catalog import TARGET_FIELD_BY_NAME

CONFIRMATION_STATES = {"CONFIRMED", "REJECTED", "MODIFIED", "PENDING"}
APPLICATION_STATES = {"PLANNED", "RUNNING", "COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}
PLAN_STATES = {"READY", "BLOCKED", "WARNING", "SKIPPED", "INVALID"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_identity(source: dict[str, Any]) -> dict[str, Any]:
    field = source.get("source_field", source)
    return {
        "sheet_name": field.get("sheet_name", ""),
        "source_index": field.get("source_index", field.get("column_index", 0)),
        "source_name": field.get("source_name", ""),
    }


def source_key(source: dict[str, Any]) -> tuple[Any, Any, Any]:
    identity = source_identity(source)
    return identity["sheet_name"], identity["source_index"], identity["source_name"]


def validate_source(profile: dict[str, Any], requested: dict[str, Any]) -> bool:
    wanted = source_key({"source_field": requested})
    return any(
        source_key({"source_field": {**column, "sheet_name": sheet.get("sheet_name", "")}}) == wanted
        for sheet in profile.get("sheets", [])
        for column in sheet.get("columns", [])
    )


def validate_target(target_field: str) -> bool:
    return target_field in TARGET_FIELD_BY_NAME


def create_confirmation(
    company_id: str,
    batch_id: str,
    source_field: dict[str, Any],
    target_field: str | None,
    action: str,
    user_id: str,
    previous_decision: dict[str, Any] | None = None,
    template_id: str | None = None,
    template_version: int | None = None,
    reason: str = "",
) -> dict[str, Any]:
    action = action.upper()
    if action not in {"CONFIRM", "REJECT", "MODIFY"}:
        raise ValueError("invalid confirmation action")
    if action != "REJECT" and (not target_field or not validate_target(target_field)):
        raise ValueError("target_field does not exist in target catalog")
    state = {"CONFIRM": "CONFIRMED", "REJECT": "REJECTED", "MODIFY": "MODIFIED"}[action]
    now = utc_now()
    identity = source_key({"source_field": source_field})
    return {
        "id": "confirmation-" + hashlib.sha256(f"{company_id}:{batch_id}:{identity}:{now}".encode()).hexdigest()[:24],
        "company_id": company_id,
        "import_batch_id": batch_id,
        "source_field": source_field,
        "target_field": target_field,
        "decision": state,
        "previous_decision": previous_decision,
        "previous_candidate": (previous_decision.get("selected_candidate") or {"target_field": previous_decision.get("target_field")} if previous_decision else None),
        "new_target": target_field if action == "MODIFY" else None,
        "confirmed_by": user_id,
        "confirmed_at": now,
        "reason": reason,
        "template_id": template_id,
        "template_version": template_version,
    }


def build_source_signature(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "sheets": [
            {
                "sheet_name": sheet.get("sheet_name", ""),
                "columns": [
                    {
                        "normalized_name": normalize_field_name(column.get("source_name", "")),
                        "type": column.get("data_type", "UNKNOWN"),
                        "index": column.get("source_index", 0),
                        "patterns": sorted(column.get("pattern_flags", [])),
                    }
                    for column in sheet.get("columns", [])
                ],
            }
            for sheet in profile.get("sheets", [])
        ]
    }


def create_template(company_id: str, name: str, profile: dict[str, Any], confirmations: list[dict[str, Any]], user_id: str, version: int = 1, created_from_version: int | None = None, change_reason: str = "") -> dict[str, Any]:
    mappings = [
        {"source_field": item["source_field"], "target_field": item["target_field"], "decision": item["decision"]}
        for item in confirmations if item.get("decision") in {"CONFIRMED", "MODIFIED"} and item.get("target_field")
    ]
    now = utc_now()
    return {
        "company_id": company_id,
        "template_id": "template-" + hashlib.sha256(f"{company_id}:{name}:{version}:{now}".encode()).hexdigest()[:24],
        "name": name,
        "status": "ACTIVE",
        "scope": "COMPANY",
        "source_signature": build_source_signature(profile),
        "mappings": mappings,
        "template_version": version,
        "created_from_version": created_from_version,
        "created_by": user_id,
        "changed_by": user_id,
        "change_reason": change_reason,
        "created_at": now,
        "updated_at": now,
    }


def detect_template_drift(profile: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    current = build_source_signature(profile)
    expected = template.get("source_signature", {})
    current_sheets = {sheet["sheet_name"]: sheet for sheet in current.get("sheets", [])}
    expected_sheets = {sheet["sheet_name"]: sheet for sheet in expected.get("sheets", [])}
    changes = []
    for name in sorted(set(current_sheets) - set(expected_sheets)):
        changes.append({"type": "SHEET_ADDED", "sheet_name": name})
    for name in sorted(set(expected_sheets) - set(current_sheets)):
        changes.append({"type": "SHEET_REMOVED", "sheet_name": name})
    for name in sorted(set(current_sheets) & set(expected_sheets)):
        current_cols = current_sheets[name]["columns"]
        expected_cols = expected_sheets[name]["columns"]
        current_names = {column["normalized_name"] for column in current_cols}
        expected_names = {column["normalized_name"] for column in expected_cols}
        changes.extend({"type": "COLUMN_ADDED", "sheet_name": name, "column": col} for col in sorted(current_names - expected_names))
        changes.extend({"type": "COLUMN_REMOVED", "sheet_name": name, "column": col} for col in sorted(expected_names - current_names))
        if current_names == expected_names and current_cols != expected_cols:
            changes.append({"type": "COLUMN_STRUCTURE_CHANGED", "sheet_name": name})
    level = "NO_DRIFT" if not changes else "LOW_DRIFT" if len(changes) == 1 else "MEDIUM_DRIFT" if len(changes) < 3 else "HIGH_DRIFT"
    return {"status": level, "changes": changes, "source_signature": current}


def build_application_plan(profile: dict[str, Any], confirmations: list[dict[str, Any]], template: dict[str, Any] | None = None) -> dict[str, Any]:
    identity_map = {source_key(item): item for item in confirmations if item.get("decision") in {"CONFIRMED", "MODIFIED"}}
    drift = detect_template_drift(profile, template) if template else {"status": "NO_DRIFT", "changes": []}
    items = []
    for sheet in profile.get("sheets", []):
        for column in sheet.get("columns", []):
            identity = {"sheet_name": sheet.get("sheet_name"), "source_index": column.get("source_index", 0), "source_name": column.get("source_name", "")}
            confirmation = identity_map.get(source_key({"source_field": identity}))
            if not confirmation:
                items.append({"source_field": identity, "target_field": None, "action": "SKIP", "status": "SKIPPED", "reason": "MAPPING_NOT_CONFIRMED"})
            elif drift["status"] == "HIGH_DRIFT":
                items.append({"source_field": identity, "target_field": confirmation.get("target_field"), "action": "MAP", "status": "BLOCKED", "reason": "TEMPLATE_DRIFT"})
            else:
                items.append({"source_field": identity, "target_field": confirmation.get("target_field"), "action": "MAP", "status": "READY"})
    counts = {state.lower(): sum(item["status"] == state for item in items) for state in PLAN_STATES}
    return {"status": "READY" if any(item["status"] == "READY" for item in items) else "BLOCKED", "items": items, "drift": drift, "summary": {"total": len(items), **counts}}


def _invalid_value(target: str, value: Any) -> bool:
    if value in (None, ""):
        return False
    text = str(value).strip()
    if target.endswith("document") and not any(char.isdigit() for char in text):
        return True
    return False


def apply_standard_records(raw_records: list[dict[str, Any]], plan: dict[str, Any], application_id: str, company_id: str, batch_id: str, template: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ready = {source_key(item["source_field"]): item for item in plan.get("items", []) if item.get("status") == "READY" and item.get("target_field")}
    records, errors = [], []
    for raw in raw_records:
        data: dict[str, Any] = {}
        provenance: list[dict[str, Any]] = []
        original = raw.get("original_record_json", {})
        for identity_key, item in ready.items():
            if identity_key[0] != raw.get("source_sheet"):
                continue
            source_name = identity_key[2]
            value = original.get(source_name)
            target = item["target_field"]
            data[target] = value
            provenance.append({"target": target, "source": {"sheet": raw.get("source_sheet"), "column": source_name, "index": identity_key[1]}, "value_hash": hashlib.sha256(str(value).encode()).hexdigest()})
            if _invalid_value(target, value):
                errors.append({"application_id": application_id, "company_id": company_id, "source_record_id": raw.get("id"), "source_field": source_name, "target_field": target, "error_code": "INVALID_SOURCE_VALUE", "message": "Source value was copied without correction.", "created_at": utc_now()})
        records.append({"id": "standard-" + hashlib.sha256(f"{application_id}:{raw.get('id')}".encode()).hexdigest()[:24], "company_id": company_id, "import_batch_id": batch_id, "source_record_id": raw.get("id"), "record_type": "STANDARD", "data": data, "field_provenance": provenance, "mapping_template_id": template.get("template_id") if template else None, "mapping_template_version": template.get("template_version") if template else None, "application_id": application_id, "created_at": utc_now(), "updated_at": utc_now()})
    return records, errors
