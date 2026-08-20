"""In-memory CSV/XLSX-normalized table adapter for Integration Hub previews.

The caller supplies tabular content already parsed into headers and rows. This
module intentionally does not open files, call a database or perform network
I/O.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from integration_hub import (
    CANONICAL_ENTITIES,
    ConnectionDefinition,
    IntegrationValidationError,
    build_sync_event,
    build_sync_preview,
)


TABULAR_PREVIEW_ADAPTER_VERSION = "1.0.0"
SUPPORTED_TABULAR_FORMATS = frozenset({"CSV", "XLSX", "TABULAR"})


def _text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise IntegrationValidationError(f"{field} is required")
    return text


def _stable_hash(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()


def normalize_tabular_table(table: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize an already parsed CSV/XLSX table in memory."""
    if not isinstance(table, Mapping):
        raise IntegrationValidationError("table must be an object")
    source_format = _text(table.get("format", "TABULAR"), "format").upper()
    if source_format not in SUPPORTED_TABULAR_FORMATS:
        raise IntegrationValidationError("unsupported tabular format")
    source_name = _text(table.get("source_name", "uploaded-table"), "source_name")
    sheet_name = _text(table.get("sheet_name", "Sheet1"), "sheet_name")
    columns = table.get("columns")
    rows = table.get("rows")
    if not isinstance(columns, Sequence) or isinstance(columns, (str, bytes)) or not columns:
        raise IntegrationValidationError("columns must be a non-empty list")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise IntegrationValidationError("rows must be a list")
    normalized_columns = [_text(column, "column") for column in columns]
    if len(set(normalized_columns)) != len(normalized_columns):
        raise IntegrationValidationError("duplicate columns are not allowed")
    normalized_rows: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=1):
        if isinstance(row, Mapping):
            unknown = set(row) - set(normalized_columns)
            if unknown:
                raise IntegrationValidationError(f"row {row_number} has unknown columns")
            normalized_rows.append({column: row.get(column) for column in normalized_columns})
            continue
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes)) or len(row) != len(normalized_columns):
            raise IntegrationValidationError(f"row {row_number} must match the column count")
        normalized_rows.append(dict(zip(normalized_columns, row)))
    result = {
        "format": source_format,
        "source_name": source_name,
        "sheet_name": sheet_name,
        "columns": normalized_columns,
        "rows": normalized_rows,
    }
    result["table_fingerprint"] = _stable_hash(result)
    return result


def validate_entity_mapping(table: Mapping[str, Any], mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an explicit header-to-canonical-fields mapping without guessing."""
    normalized_table = normalize_tabular_table(table)
    if not isinstance(mapping, Mapping):
        raise IntegrationValidationError("mapping must be an object")
    entity = _text(mapping.get("entity"), "mapping entity").upper()
    if entity not in CANONICAL_ENTITIES:
        raise IntegrationValidationError("unsupported mapping entity")
    external_id_field = _text(mapping.get("external_id_field"), "external_id_field")
    fields = mapping.get("fields")
    if not isinstance(fields, Mapping) or not fields:
        raise IntegrationValidationError("mapping fields are required")
    selected_headers = [external_id_field, *fields.values()]
    missing = sorted({_text(header, "mapped header") for header in selected_headers} - set(normalized_table["columns"]))
    if missing:
        raise IntegrationValidationError(f"mapped headers not found: {', '.join(missing)}")
    if len(set(fields)) != len(fields):
        raise IntegrationValidationError("duplicate canonical fields are not allowed")
    if len(set(fields.values())) != len(fields):
        raise IntegrationValidationError("a source header cannot map to multiple canonical fields")
    return {
        "entity": entity,
        "external_id_field": external_id_field,
        "fields": {str(canonical): _text(header, "mapped header") for canonical, header in fields.items()},
    }


def build_tabular_previews(
    connection: ConnectionDefinition,
    table: Mapping[str, Any],
    mapping: Mapping[str, Any],
    *,
    direction: str = "IMPORT",
    approved: bool = False,
) -> dict[str, Any]:
    """Convert normalized rows into canonical events and non-mutating previews."""
    normalized_table = normalize_tabular_table(table)
    validated_mapping = validate_entity_mapping(normalized_table, mapping)
    records: list[dict[str, Any]] = []
    for row_number, row in enumerate(normalized_table["rows"], start=1):
        external_id = _text(row.get(validated_mapping["external_id_field"]), f"row {row_number} external id")
        fields = {canonical: row[header] for canonical, header in validated_mapping["fields"].items()}
        event = build_sync_event(
            connection,
            entity=validated_mapping["entity"],
            external_id=external_id,
            operation="UPSERT",
            fields=fields,
            event_id=f"{normalized_table['table_fingerprint']}:{row_number}",
        )
        records.append({"row_number": row_number, "event": event, "preview": build_sync_preview(connection, event, direction=direction, approved=approved)})
    return {
        "tabular_preview_adapter_version": TABULAR_PREVIEW_ADAPTER_VERSION,
        "mode": "PREVIEW",
        "will_read_files": False,
        "will_perform_external_io": False,
        "table_fingerprint": normalized_table["table_fingerprint"],
        "entity": validated_mapping["entity"],
        "record_count": len(records),
        "records": records,
    }
