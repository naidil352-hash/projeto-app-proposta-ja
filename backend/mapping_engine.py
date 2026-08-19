"""Deterministic candidate mapping engine.

The engine proposes candidates from a StructureProfile. It never applies a
mapping or mutates imported data.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any, Iterable

from target_field_catalog import TARGET_FIELD_CATALOG

MAPPING_ENGINE_VERSION = "1.0.0"
MAX_CANDIDATES_PER_SOURCE = 5
SCORE_WEIGHTS = {
    "name": 0.35,
    "type": 0.18,
    "pattern": 0.18,
    "sheet": 0.05,
    "column": 0.05,
    "cardinality": 0.04,
    "position": 0.03,
    "formula": 0.12,
}
CONFLICT_PENALTY = 0.12
MINIMUM_CANDIDATE_SCORE = 0.12


def normalize_field_name(value: Any) -> str:
    """Normalize only for comparison; preserve source names elsewhere."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower().replace("_", " ")
    text = re.sub(r"[^\w\s$]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _name_similarity(source_name: str, target: dict[str, Any]) -> tuple[float, str, str]:
    source = normalize_field_name(source_name)
    target_name = normalize_field_name(target["field"].replace("_", " "))
    aliases = [normalize_field_name(alias) for alias in target.get("aliases", [])]
    candidates = [target_name, *aliases]
    exact_alias = next((alias for alias in aliases if source == alias), None)
    if exact_alias is not None:
        return 1.0, "NAME_MATCH", f"normalized source name exactly matches alias '{exact_alias}'"
    if source == target_name:
        return 1.0, "NAME_MATCH", "normalized source name exactly matches target field"
    scores = [(SequenceMatcher(None, source, candidate).ratio(), candidate) for candidate in candidates if candidate]
    similarity, closest = max(scores, default=(0.0, ""))
    if similarity < 0.35:
        return 0.0, "NAME_SIMILARITY", "no meaningful normalized-name similarity"
    return similarity, "NAME_SIMILARITY", f"normalized source name is similar to '{closest}'"


def _type_compatibility(column: dict[str, Any], target: dict[str, Any]) -> tuple[float, str]:
    source_type = column.get("data_type", "UNKNOWN")
    compatible = set(target.get("compatible_types", []))
    if source_type in compatible:
        return 1.0, f"source type {source_type} is compatible with target type"
    if source_type == "MIXED":
        return 0.35, "mixed source values provide weak type compatibility"
    if source_type in {"EMPTY", "UNKNOWN"}:
        return 0.15, "source type has insufficient observations"
    target_type = target.get("type")
    if source_type in {"DATE", "DATETIME"} and target_type not in {"DATE", "DATETIME"}:
        return 0.0, f"date source is incompatible with target type {target_type}"
    if source_type in {"DECIMAL", "INTEGER", "CURRENCY_LIKE"} and target_type == "STRING":
        return 0.2, "numeric source is weakly compatible with a string target"
    return 0.2, f"source type {source_type} has weak compatibility with target"


def _pattern_compatibility(column: dict[str, Any], target: dict[str, Any]) -> tuple[float, str]:
    source_patterns = set(column.get("pattern_flags", []))
    target_patterns = set(target.get("patterns", []))
    if source_patterns & target_patterns:
        return 1.0, f"shared structural pattern: {sorted(source_patterns & target_patterns)[0]}"
    if not source_patterns or not target_patterns:
        return 0.25, "no direct pattern evidence observed"
    return 0.0, "observed patterns do not match target patterns"


def _sheet_context(sheet_name: str, target: dict[str, Any]) -> tuple[float, str]:
    sheet = normalize_field_name(sheet_name)
    contexts = [normalize_field_name(context) for context in target.get("sheet_context", [])]
    if any(context and context in sheet for context in contexts):
        return 1.0, f"sheet name '{sheet_name}' supports target context"
    return 0.0, "sheet name provides no direct target-context evidence"


def _column_context(column: dict[str, Any], columns: list[dict[str, Any]], target: dict[str, Any]) -> tuple[float, str]:
    target_entity = target.get("entity")
    other_columns = [item for item in columns if item is not column]
    patterns = {pattern for item in other_columns for pattern in item.get("pattern_flags", [])}
    if target_entity == "CLIENT" and patterns & {"CNPJ_LIKE", "CPF_LIKE", "EMAIL_LIKE", "PHONE_LIKE"}:
        return 0.8, "neighboring contact/document columns support CLIENT context"
    if target_entity == "PRODUCT" and patterns & {"SKU_LIKE", "CODE_LIKE"}:
        return 0.7, "neighboring code columns support PRODUCT context"
    if target_entity == "PROPOSAL_ITEM" and any(item.get("data_type") in {"INTEGER", "DECIMAL", "CURRENCY_LIKE"} for item in other_columns):
        return 0.65, "neighboring numeric columns support PROPOSAL_ITEM context"
    return 0.0, "no direct neighboring-column evidence"


def _cardinality_signal(column: dict[str, Any], target: dict[str, Any]) -> tuple[float, str]:
    cardinality = column.get("cardinality_class")
    hint = target.get("cardinality_hint")
    if not hint:
        return 0.5, "cardinality is neutral for this target"
    if hint == "high" and cardinality in {"UNIQUE_LIKE", "HIGH_CARDINALITY"}:
        return 1.0, "high source cardinality supports identifier-like target"
    if hint == "low" and cardinality in {"LOW_CARDINALITY", "ALL_SAME", "REPEATED"}:
        return 1.0, "low source cardinality supports repeated-value target"
    return 0.35, "cardinality provides weak target evidence"


def _position_signal(source_index: int, target: dict[str, Any]) -> tuple[float, str]:
    field = target["field"]
    if source_index == 0 and any(token in field for token in ("code", "id", "name", "description")):
        return 0.7, "first-column position is a weak code/name hint"
    return 0.3, "column position is weak or neutral evidence"


def _formula_signal(profile: dict[str, Any], sheet_name: str, source_name: str, target_field: str) -> tuple[float, str] | None:
    for hint in profile.get("formula_relationship_hints", []):
        if hint.get("sheet_name") not in {None, sheet_name}:
            continue
        role_by_target = {
            "item_quantity": "quantity",
            "item_unit_price": "unit_price",
            "item_total": "total",
        }
        role = role_by_target.get(target_field)
        if not role:
            continue
        if normalize_field_name(hint.get(role, "")) == normalize_field_name(source_name):
            return 1.0, f"formula relationship identifies source as {role}"
    return None


def _confidence(score: float) -> str:
    if score >= 0.75:
        return "HIGH"
    if score >= 0.50:
        return "MEDIUM"
    return "LOW"


def _evidence(evidence_type: str, weight: float, score: float, detail: str) -> dict[str, Any]:
    return {"type": evidence_type, "weight": weight, "score": round(max(0.0, min(1.0, score)), 4), "detail": detail}


def _source_columns(profile: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    sources = []
    for sheet in profile.get("sheets", []):
        for column in sheet.get("columns", []):
            source = {
                "sheet_name": sheet.get("sheet_name", ""),
                "source_index": column.get("source_index", 0),
                "source_name": column.get("source_name", ""),
                "data_type": column.get("data_type", "UNKNOWN"),
            }
            sources.append((sheet, column))
    return sources


def generate_candidate_mappings(profile: dict[str, Any], max_candidates: int = MAX_CANDIDATES_PER_SOURCE) -> dict[str, Any]:
    """Generate ranked, explainable candidates from a StructureProfile."""
    source_columns = _source_columns(profile)
    sources: list[dict[str, Any]] = []
    for sheet, column in source_columns:
        sheet_name = sheet.get("sheet_name", "")
        source_name = column.get("source_name", "")
        scored: list[dict[str, Any]] = []
        for target in TARGET_FIELD_CATALOG:
            name_score, name_type, name_detail = _name_similarity(source_name, target)
            type_score, type_detail = _type_compatibility(column, target)
            pattern_score, pattern_detail = _pattern_compatibility(column, target)
            sheet_score, sheet_detail = _sheet_context(sheet_name, target)
            column_score, column_detail = _column_context(column, sheet.get("columns", []), target)
            cardinality_score, cardinality_detail = _cardinality_signal(column, target)
            position_score, position_detail = _position_signal(column.get("source_index", 0), target)
            formula = _formula_signal(profile, sheet_name, source_name, target["field"])
            formula_score, formula_detail = formula or (0.0, "no formula relationship evidence")
            evidence = [
                _evidence(name_type, SCORE_WEIGHTS["name"], name_score, name_detail),
                _evidence("TYPE_COMPATIBILITY", SCORE_WEIGHTS["type"], type_score, type_detail),
                _evidence("PATTERN_COMPATIBILITY", SCORE_WEIGHTS["pattern"], pattern_score, pattern_detail),
                _evidence("SHEET_CONTEXT", SCORE_WEIGHTS["sheet"], sheet_score, sheet_detail),
                _evidence("COLUMN_CONTEXT", SCORE_WEIGHTS["column"], column_score, column_detail),
                _evidence("CARDINALITY", SCORE_WEIGHTS["cardinality"], cardinality_score, cardinality_detail),
                _evidence("POSITION_HINT", SCORE_WEIGHTS["position"], position_score, position_detail),
            ]
            if formula:
                evidence.append(_evidence("FORMULA_RELATIONSHIP", SCORE_WEIGHTS["formula"], formula_score, formula_detail))
            score = sum(item["weight"] * item["score"] for item in evidence)
            scored.append({
                "source_field": source_name,
                "target_field": target["field"],
                "score": score,
                "confidence": _confidence(score),
                "evidence": evidence,
                "analyzer_version": profile.get("analyzer_version", "unknown"),
                "mapping_engine_version": MAPPING_ENGINE_VERSION,
            })

        financial = [
            candidate for candidate in scored
            if candidate["target_field"] in {"proposal_total", "proposal_net_total", "item_total", "item_unit_price", "product_price"}
            and any(item["type"] in {"NAME_MATCH", "NAME_SIMILARITY"} and item["score"] >= 0.75 for item in candidate["evidence"])
        ]
        if normalize_field_name(source_name) in {"valor", "total"} and len(financial) > 1:
            for candidate in financial:
                candidate["evidence"].append(_evidence("CONFLICT", 0.0, 0.0, "source field matches multiple financial targets"))
                candidate["score"] = max(0.0, candidate["score"] - CONFLICT_PENALTY)

        scored = [candidate for candidate in scored if candidate["score"] >= MINIMUM_CANDIDATE_SCORE]
        scored.sort(key=lambda item: (-round(item["score"], 8), item["target_field"]))
        sources.append({
            "source_field": {
                "sheet_name": sheet_name,
                "source_index": column.get("source_index", 0),
                "source_name": source_name,
            },
            "candidates": [
                {**candidate, "score": round(max(0.0, min(1.0, candidate["score"])), 4), "confidence": _confidence(candidate["score"])}
                for candidate in scored[:max_candidates]
            ],
        })

    warnings: list[dict[str, Any]] = []
    target_sources: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        for candidate in source["candidates"]:
            if candidate["score"] >= 0.5:
                target_sources.setdefault(candidate["target_field"], []).append(source["source_field"])
    for target_field, source_fields in sorted(target_sources.items()):
        unique_sources = {(item["sheet_name"], item["source_index"], item["source_name"]) for item in source_fields}
        if len(unique_sources) > 1:
            warnings.append({
                "type": "TARGET_COLLISION",
                "target_field": target_field,
                "source_fields": source_fields,
                "detail": "multiple source columns compete for the same target field",
            })
            for source in sources:
                source_key = (source["source_field"]["sheet_name"], source["source_field"]["source_index"], source["source_field"]["source_name"])
                if source_key in {(item["sheet_name"], item["source_index"], item["source_name"]) for item in source_fields}:
                    for candidate in source["candidates"]:
                        if candidate["target_field"] == target_field:
                            candidate["evidence"].append(_evidence("TARGET_COLLISION", 0.0, 0.0, "target is also suggested for another source column"))

    return {
        "mapping_engine_version": MAPPING_ENGINE_VERSION,
        "structure_profile_id": profile.get("id"),
        "import_batch_id": profile.get("import_batch_id"),
        "sources": sources,
        "warnings": warnings,
        "global_statistics": {
            "source_fields": len(sources),
            "candidate_count": sum(len(source["candidates"]) for source in sources),
            "target_collisions": len(warnings),
        },
    }
