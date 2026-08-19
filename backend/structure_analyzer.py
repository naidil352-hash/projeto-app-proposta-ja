"""Structural analysis for imported CSV/XLSX raw records.

This module describes observed structure only. It does not assign business
meaning to source columns and never mutates raw records.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import re
from typing import Any, Iterable

ANALYZER_VERSION = "1.0.0"
MAX_SAMPLE_VALUES = 5
NULL_THRESHOLDS = {"low": 0.10, "medium": 0.40, "high": 0.80}

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_RE = re.compile(r"^(?:\+?\d[\d ()-]{7,}\d)$")
_CPF_RE = re.compile(r"^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$")
_CNPJ_RE = re.compile(r"^\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}$")
_CEP_RE = re.compile(r"^\d{5}-?\d{3}$")
_URL_RE = re.compile(r"^(?:https?://|www\.)\S+$", re.IGNORECASE)
_SKU_RE = re.compile(r"^(?:SKU[-_ ]?)?[A-Z0-9]+[-_][A-Z0-9-]+$", re.IGNORECASE)
_CODE_RE = re.compile(r"^[A-Z0-9]+(?:[-_/][A-Z0-9]+)+$", re.IGNORECASE)
_DATE_RE = re.compile(r"^(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2})(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?$")
_PERCENT_RE = re.compile(r"^-?\d+(?:[.,]\d+)?%$")
_CURRENCY_RE = re.compile(r"^(?:R\$\s*)?-?\d{1,3}(?:\.\d{3})*(?:,\d+)?$|^(?:R\$\s*)?-?\d+(?:[.,]\d+)?$")


def _is_null(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _display_value(value: Any) -> Any:
    return value if not isinstance(value, (date, datetime)) else value.isoformat()


def _text(value: Any) -> str:
    return str(value).strip()


def normalize_name(value: Any) -> str:
    return " ".join(_text(value).lower().split())


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = _text(value).replace("R$", "").replace(" ", "")
    if not text or _PERCENT_RE.match(text):
        return None
    if re.match(r"^-?\d{1,3}(?:\.\d{3})+,\d+$", text):
        text = text.replace(".", "").replace(",", ".")
    elif "," in text and "." not in text:
        text = text.replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        parsed = float(text)
        return int(parsed) if parsed.is_integer() else parsed
    except ValueError:
        return None


def _pattern_flags(values: Iterable[Any]) -> list[str]:
    texts = [_text(value) for value in values if not _is_null(value)]
    if not texts:
        return []
    flags: list[str] = []
    checks = (
        ("EMAIL_LIKE", _EMAIL_RE),
        ("PHONE_LIKE", _PHONE_RE),
        ("CPF_LIKE", _CPF_RE),
        ("CNPJ_LIKE", _CNPJ_RE),
        ("CEP_LIKE", _CEP_RE),
        ("URL_LIKE", _URL_RE),
        ("SKU_LIKE", _SKU_RE),
        ("CODE_LIKE", _CODE_RE),
        ("DATE_LIKE", _DATE_RE),
        ("PERCENTAGE_LIKE", _PERCENT_RE),
    )
    for name, pattern in checks:
        if sum(bool(pattern.match(value)) for value in texts) / len(texts) >= 0.8:
            flags.append(name)
    if sum(bool(_CURRENCY_RE.match(value)) for value in texts) / len(texts) >= 0.8:
        flags.append("CURRENCY_LIKE")
    return flags


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = _text(value)
    if not _DATE_RE.match(text):
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _data_type(values: list[Any], flags: list[str]) -> str:
    non_null = [value for value in values if not _is_null(value)]
    if not non_null:
        return "EMPTY"
    if all(isinstance(value, bool) or _text(value).lower() in {"true", "false", "sim", "não", "nao", "yes", "no"} for value in non_null):
        return "BOOLEAN"
    if all(_parse_date(value) is not None for value in non_null):
        return "DATETIME" if any(re.search(r"[ T]\d{1,2}:", _text(value)) for value in non_null) else "DATE"
    numbers = [_number(value) for value in non_null]
    if all(number is not None for number in numbers):
        if "PERCENTAGE_LIKE" in flags:
            return "PERCENTAGE_LIKE"
        if "CURRENCY_LIKE" in flags and any(re.search(r"R\$|,", _text(value)) for value in non_null):
            return "CURRENCY_LIKE"
        return "INTEGER" if all(float(number).is_integer() for number in numbers) else "DECIMAL"
    if "CURRENCY_LIKE" in flags:
        return "CURRENCY_LIKE"
    if "PERCENTAGE_LIKE" in flags:
        return "PERCENTAGE_LIKE"
    if "IDENTIFIER_LIKE" in flags:
        return "IDENTIFIER_LIKE"
    type_names = {type(value).__name__ for value in non_null}
    return "MIXED" if len(type_names) > 1 or any(_number(value) is not None for value in non_null) else "STRING"


def _identifier_like(name: str, values: list[Any], unique_ratio: float) -> bool:
    texts = [_text(value) for value in values if not _is_null(value)]
    if not texts or unique_ratio < 0.7:
        return False
    compact = sum(bool(re.match(r"^[A-Za-z0-9_-]{3,32}$", value)) and " " not in value for value in texts)
    return compact / len(texts) >= 0.8


def _null_class(ratio: float, total: int) -> str:
    if total == 0 or ratio == 1:
        return "ALL_NULL"
    if ratio == 0:
        return "COMPLETE"
    if ratio <= NULL_THRESHOLDS["low"]:
        return "LOW_NULL"
    if ratio <= NULL_THRESHOLDS["medium"]:
        return "MEDIUM_NULL"
    return "HIGH_NULL"


def _cardinality_class(unique_count: int, non_null_count: int) -> str:
    if not non_null_count:
        return "ALL_SAME"
    ratio = unique_count / non_null_count
    if unique_count == 1:
        return "ALL_SAME"
    if ratio >= 0.9:
        return "UNIQUE_LIKE"
    if ratio >= 0.6:
        return "HIGH_CARDINALITY"
    if ratio <= 0.2:
        return "LOW_CARDINALITY"
    return "REPEATED"


def analyze_column(source_name: Any, source_index: int, values: list[Any], max_sample_values: int = MAX_SAMPLE_VALUES) -> dict[str, Any]:
    non_null = [value for value in values if not _is_null(value)]
    null_count = len(values) - len(non_null)
    unique_values = {_text(value) for value in non_null}
    unique_count = len(unique_values)
    unique_ratio = unique_count / len(non_null) if non_null else 0.0
    flags = _pattern_flags(non_null)
    if _identifier_like(normalize_name(source_name), non_null, unique_ratio):
        flags.append("IDENTIFIER_LIKE")
    values_by_text = {}
    for value in non_null:
        values_by_text.setdefault(_text(value), _display_value(value))
    samples = list(values_by_text.values())[:max_sample_values]
    numbers = [_number(value) for value in non_null]
    numeric_values = [number for number in numbers if number is not None]
    hints = list(flags)
    if "IDENTIFIER_LIKE" in flags:
        hints.append("semantic_meaning:unknown")
    result = {
        "source_name": _text(source_name),
        "source_index": source_index,
        "normalized_name_for_analysis": normalize_name(source_name),
        "data_type": _data_type(values, flags),
        "null_count": null_count,
        "non_null_count": len(non_null),
        "null_ratio": round(null_count / len(values), 4) if values else 0.0,
        "null_class": _null_class(null_count / len(values) if values else 1.0, len(values)),
        "unique_count": unique_count,
        "unique_ratio": round(unique_ratio, 4),
        "cardinality_class": _cardinality_class(unique_count, len(non_null)),
        "sample_values": samples,
        "min_value": min(numeric_values) if numeric_values else None,
        "max_value": max(numeric_values) if numeric_values else None,
        "pattern_flags": flags,
        "semantic_hints": hints,
        "potential_identifier": "IDENTIFIER_LIKE" in flags,
        "semantic_meaning": "unknown",
    }
    return result


def _sheet_status(entry: dict[str, Any], records: list[dict[str, Any]]) -> str:
    explicit = entry.get("header_detection_status")
    if not records and not entry.get("rows"):
        return "NOT_APPLICABLE"
    if not records:
        return "AMBIGUOUS" if explicit in {"AMBIGUOUS", "DETECTED"} else "NOT_FOUND"
    return "CONFIDENT" if explicit in {"DETECTED", "CONFIDENT"} else "AMBIGUOUS"


def analyze_structure(file_summary: dict[str, Any], raw_records: list[dict[str, Any]], sheet_entries: list[dict[str, Any]] | None = None, max_sample_values: int = MAX_SAMPLE_VALUES) -> dict[str, Any]:
    """Build a StructureProfile from existing raw records and parser metadata."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in raw_records:
        grouped[record.get("source_sheet", "Sheet")].append(record)
    entries_by_name = {entry.get("sheet", "Sheet"): entry for entry in (sheet_entries or [])}
    names = list(dict.fromkeys([*(entry.get("sheet", "Sheet") for entry in (sheet_entries or [])), *grouped.keys()]))
    sheets: list[dict[str, Any]] = []
    relationship_columns: dict[str, list[str]] = defaultdict(list)
    warnings: list[dict[str, Any]] = []
    total_rows = 0
    total_columns = 0
    tabular_sheets = 0
    empty_sheets = 0

    for sheet_index, sheet_name in enumerate(names):
        records = grouped.get(sheet_name, [])
        metadata = records[0].get("raw_metadata", {}) if records else {}
        entry = {**metadata, **entries_by_name.get(sheet_name, {})}
        headers: list[str] = [str(header) for header in entry.get("headers", [])]
        if not headers:
            for record in records:
                headers.extend(str(key) for key in record.get("original_record_json", {}).keys())
            headers = list(dict.fromkeys(headers))
        if not headers and entry.get("columns"):
            headers = [f"column_{index + 1}" for index in range(int(entry["columns"]))]
        columns = []
        for index, header in enumerate(headers):
            values = [record.get("original_record_json", {}).get(header, "") for record in records]
            column = analyze_column(header, index, values, max_sample_values)
            columns.append(column)
            for flag in column["pattern_flags"]:
                if flag in {"CNPJ_LIKE", "CPF_LIKE", "EMAIL_LIKE", "CODE_LIKE", "SKU_LIKE", "IDENTIFIER_LIKE"}:
                    relationship_columns[flag].append(f"{sheet_name}.{header}")
        row_count = int(entry["rows"]) if "rows" in entry else (len(records) + (int(entry.get("header_row") or 1)))
        data_row_count = len(records)
        is_empty = not records and row_count == 0
        structure_status = "EMPTY" if is_empty else ("TABULAR" if headers and records else "TEXT_ONLY")
        header_status = _sheet_status(entry, records)
        sheet_warnings: list[str] = []
        if is_empty:
            sheet_warnings.append("EMPTY_SHEET")
            warnings.append({"code": "EMPTY_SHEET", "sheet_name": sheet_name})
            empty_sheets += 1
        if structure_status == "TEXT_ONLY":
            sheet_warnings.append("NON_TABULAR_SHEET")
            warnings.append({"code": "NON_TABULAR_SHEET", "sheet_name": sheet_name})
        duplicate_names = [name for name, count in Counter(headers).items() if count > 1]
        if duplicate_names:
            sheet_warnings.append("DUPLICATE_COLUMN_NAMES")
            warnings.append({"code": "DUPLICATE_COLUMN_NAMES", "sheet_name": sheet_name, "columns": duplicate_names})
        for column in columns:
            if column["null_class"] in {"HIGH_NULL", "ALL_NULL"}:
                warnings.append({"code": "HIGH_EMPTY_RATIO", "sheet_name": sheet_name, "column": column["source_name"]})
            if column["data_type"] == "MIXED":
                warnings.append({"code": "MIXED_DATA_TYPES", "sheet_name": sheet_name, "column": column["source_name"]})
            if column["cardinality_class"] in {"REPEATED", "ALL_SAME"} and column["non_null_count"] > 1:
                warnings.append({"code": "HIGH_DUPLICATION", "sheet_name": sheet_name, "column": column["source_name"]})
        sheets.append({
            "sheet_name": sheet_name,
            "sheet_index": sheet_index,
            "is_empty": is_empty,
            "header_row": entry.get("header_row"),
            "header_detection_status": header_status,
            "header_detection_method": entry.get("header_detection_method", "raw_records"),
            "row_count": row_count,
            "data_row_count": data_row_count,
            "column_count": len(headers),
            "structure_status": structure_status,
            "columns": columns,
            "warnings": sheet_warnings,
        })
        total_rows += row_count
        total_columns += len(headers)
        if structure_status == "TABULAR":
            tabular_sheets += 1

    relationships = []
    for hint, locations in relationship_columns.items():
        if len({location.split(".", 1)[0] for location in locations}) > 1:
            relationships.append({"hint_type": "potential_shared_key", "pattern": hint, "columns": locations})
    total_sheets = len(sheets)
    return {
        "analyzer_version": ANALYZER_VERSION,
        "status": "ANALYZED",
        "file_summary": {**file_summary, "sheets_count": file_summary.get("sheets_count", total_sheets)},
        "sheets": sheets,
        "global_statistics": {
            "total_sheets": total_sheets,
            "total_rows": total_rows,
            "total_columns": total_columns,
            "tabular_sheets": tabular_sheets,
            "empty_sheets": empty_sheets,
        },
        "sheet_relationship_hints": relationships,
        "warnings": warnings,
    }
