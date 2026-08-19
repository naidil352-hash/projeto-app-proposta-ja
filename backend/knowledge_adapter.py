"""Knowledge Adapter — bridges Company Knowledge into Decision Engine evidence.

This module is the ONLY bridge between the Learning Engine (Phase 3.0) and the
Decision Engine (Phase 2.2B). It never mutates knowledge, never mutates
decisions by itself, and never crosses tenant boundaries: callers must supply
knowledge that has already been scoped to a single company_id.

Advisory-only guarantees enforced here:
- Knowledge can only ever produce a bounded, capped evidence contribution.
- Knowledge alone can never be the reason a decision becomes AUTO.
- Knowledge with CONFLICTED status can only make decisions more conservative.
"""
from __future__ import annotations

from typing import Any

from learning_engine import pattern_signature

KNOWLEDGE_ADAPTER_VERSION = "1.0.0"

# Advisory bounds: knowledge may nudge a decision, never dominate it.
MAX_KNOWLEDGE_INFLUENCE = 0.15
LEARNED_MATCH_WEIGHT = 0.15
MIN_SUPPORT_FOR_EVIDENCE = 3
MIN_CONFIDENCE_FOR_EVIDENCE = 0.5

IdentityKey = tuple[Any, Any, Any, str]


def _source_pattern_from_column(sheet_name: str, column: dict[str, Any]) -> dict[str, Any]:
    return {
        "normalized_name": column.get("source_name", ""),
        "type": column.get("data_type", "UNKNOWN"),
        "sheet_context": sheet_name,
        "patterns": column.get("pattern_flags", []),
    }


def index_knowledge_by_signature(knowledge_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index a company's knowledge by its pattern_signature for O(1) lookup."""
    return {item["pattern_signature"]: item for item in knowledge_items if item.get("pattern_signature")}


def build_learned_evidence_index(
    structure_profile: dict[str, Any] | None,
    mapping_document: dict[str, Any],
    knowledge_items: list[dict[str, Any]],
) -> dict[IdentityKey, dict[str, Any]]:
    """Map (sheet_name, source_index, source_name, target_field) -> knowledge item.

    Only candidates that already exist in the mapping_document are considered,
    so this never invents new source/target combinations.
    """
    if not structure_profile or not knowledge_items:
        return {}
    knowledge_by_signature = index_knowledge_by_signature(knowledge_items)
    if not knowledge_by_signature:
        return {}

    columns_by_identity: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for sheet in structure_profile.get("sheets", []):
        sheet_name = sheet.get("sheet_name", "")
        for column in sheet.get("columns", []):
            identity = (sheet_name, column.get("source_index", 0), column.get("source_name", ""))
            columns_by_identity[identity] = _source_pattern_from_column(sheet_name, column)

    index: dict[IdentityKey, dict[str, Any]] = {}
    for source in mapping_document.get("candidates", mapping_document.get("sources", [])):
        field = source.get("source_field", {})
        identity = (field.get("sheet_name"), field.get("source_index"), field.get("source_name"))
        source_pattern = columns_by_identity.get(identity)
        if not source_pattern:
            continue
        for candidate in source.get("candidates", []):
            target = candidate.get("target_field")
            if not target:
                continue
            signature = pattern_signature(source_pattern, target)
            knowledge = knowledge_by_signature.get(signature)
            if knowledge:
                index[(*identity, target)] = knowledge
    return index


def build_learned_evidence(knowledge_item: dict[str, Any] | None) -> dict[str, Any] | None:
    """Turn a single knowledge item into a bounded, explainable evidence entry.

    Returns None when the knowledge is too weak, disabled, or expired to be
    used as evidence at all (conservative by default).
    """
    if not knowledge_item:
        return None
    status = knowledge_item.get("status")
    confidence = float(knowledge_item.get("confidence", 0.0) or 0.0)
    support = int(knowledge_item.get("support_count", 0) or 0)

    if status == "CONFLICTED":
        return {
            "type": "LEARNED_CONFLICT",
            "weight": 0.0,
            "score": 0.0,
            "detail": f"Company knowledge reports a conflicting historical pattern (support={support}).",
        }
    if status in {"DISABLED", "EXPIRED"}:
        return None
    if support < MIN_SUPPORT_FOR_EVIDENCE or confidence < MIN_CONFIDENCE_FOR_EVIDENCE:
        return None
    bounded_score = max(0.0, min(1.0, confidence))
    return {
        "type": "LEARNED_MATCH",
        "weight": LEARNED_MATCH_WEIGHT,
        "score": bounded_score,
        "detail": f"Company knowledge supports this mapping (confidence={bounded_score}, support={support}).",
    }


def bounded_influence(evidence: dict[str, Any]) -> float:
    """Compute the capped numeric influence a piece of learned evidence may exert."""
    return round(min(MAX_KNOWLEDGE_INFLUENCE, evidence.get("weight", 0.0) * evidence.get("score", 0.0)), 4)
