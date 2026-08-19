"""Deterministic, fail-closed decisions over candidate mappings."""

from __future__ import annotations

from enum import Enum
from typing import Any

from knowledge_adapter import KNOWLEDGE_ADAPTER_VERSION, bounded_influence, build_learned_evidence

DECISION_ENGINE_VERSION = "1.0.0"
AUTO_MIN_SCORE = 0.92
SUGGEST_MIN_SCORE = 0.75
CONFIRM_MIN_SCORE = 0.45
UNKNOWN_MAX_SCORE = 0.4499
AUTO_MIN_MARGIN = 0.20
SUGGEST_MIN_MARGIN = 0.08

EVIDENCE_QUALITY = {
    "STRONG": {"NAME_MATCH", "PATTERN_COMPATIBILITY", "TYPE_COMPATIBILITY", "FORMULA_RELATIONSHIP"},
    "MEDIUM": {"NAME_SIMILARITY", "COLUMN_CONTEXT", "CARDINALITY"},
    "WEAK": {"POSITION_HINT", "SHEET_CONTEXT"},
}
CRITICAL_BLOCKERS = {
    "CONFLICT",
    "TARGET_COLLISION",
    "TYPE_INCOMPATIBILITY",
    "MIXED_DATA_TYPES",
    "AMBIGUOUS_HEADER",
    "UNKNOWN_STRUCTURE",
    "LOW_SIGNAL",
    "INSUFFICIENT_MARGIN",
}


class DecisionState(str, Enum):
    AUTO = "AUTO"
    SUGGEST = "SUGGEST"
    CONFIRM = "CONFIRM"
    UNKNOWN = "UNKNOWN"


def _validate_score(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{label} must be between 0.0 and 1.0")
    return float(value)


def _quality(evidence: list[dict[str, Any]]) -> tuple[str, float]:
    types = {item.get("type") for item in evidence}
    strong = len(types & EVIDENCE_QUALITY["STRONG"])
    medium = len(types & EVIDENCE_QUALITY["MEDIUM"])
    weak = len(types & EVIDENCE_QUALITY["WEAK"])
    if strong >= 2 or (strong >= 1 and medium >= 1):
        return "STRONG", 1.0
    if medium >= 2 or strong == 1:
        return "MEDIUM", 0.75
    if weak:
        return "WEAK", 0.45
    return "INSUFFICIENT", 0.0


def _reason(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _source_identity(source: dict[str, Any]) -> tuple[Any, Any, Any]:
    field = source.get("source_field", source)
    return field.get("sheet_name"), field.get("source_index"), field.get("source_name")


def _candidate_sources(mapping_document: dict[str, Any]) -> list[dict[str, Any]]:
    return list(mapping_document.get("candidates", mapping_document.get("sources", [])))


def decide_mapping_candidates(
    mapping_document: dict[str, Any],
    learned_evidence_index: dict[tuple[Any, Any, Any, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return one immutable decision record per source field.

    This function consumes only the Candidate Mapping document. It does not
    inspect RawRecords or modify any imported/business document.

    ``learned_evidence_index`` is an optional, advisory-only bridge to Company
    Knowledge (Phase 3.1). When absent, behavior is identical to Phase 2.2B.
    Knowledge can only nudge ``decision_score`` within a bounded cap and can
    only ever make a decision MORE conservative (CONFLICTED knowledge can
    downgrade AUTO), never promote a decision across states by itself.
    """
    sources = _candidate_sources(mapping_document)
    collision_targets: dict[str, list[tuple[Any, Any, Any]]] = {}
    for source in sources:
        for candidate in source.get("candidates", []):
            score = _validate_score(candidate.get("score"), "candidate score")
            if score >= CONFIRM_MIN_SCORE:
                collision_targets.setdefault(candidate.get("target_field"), []).append(_source_identity(source))
    collision_sources = {
        target: set(identities)
        for target, identities in collision_targets.items()
        if len(set(identities)) > 1
    }

    decisions: list[dict[str, Any]] = []
    for source in sources:
        source_field = dict(source.get("source_field", {}))
        candidates = list(source.get("candidates", []))
        candidates.sort(key=lambda item: (-_validate_score(item.get("score"), "candidate score"), str(item.get("target_field", ""))))
        top = candidates[0] if candidates else None
        top_score = _validate_score(top.get("score"), "candidate score") if top else 0.0
        runner = candidates[1] if len(candidates) > 1 else None
        runner_score = _validate_score(runner.get("score"), "runner-up score") if runner else 0.0
        margin = top_score - runner_score if runner else top_score
        evidence = list(top.get("evidence", [])) if top else []
        quality_name, quality_score = _quality(evidence)
        blocking_reasons: list[dict[str, str]] = []
        reasons: list[dict[str, str]] = []
        warnings: list[dict[str, Any]] = []
        evidence_types = {item.get("type") for item in evidence}

        if not top:
            reasons.append(_reason("INSUFFICIENT_EVIDENCE", "No candidate was produced for this source field."))
            decision = DecisionState.UNKNOWN
        else:
            if top.get("target_field") in collision_sources:
                blocking_reasons.append(_reason("TARGET_COLLISION", "Multiple source fields compete for this target."))
            if "CONFLICT" in evidence_types:
                blocking_reasons.append(_reason("HIGH_COMPETITION", "Candidate evidence reports a semantic conflict."))
            if any(item.get("score") == 0 and item.get("type") == "TYPE_COMPATIBILITY" for item in evidence):
                blocking_reasons.append(_reason("TYPE_CONFLICT", "Candidate type is incompatible with the source structure."))
            if source_field.get("duplicate"):
                blocking_reasons.append(_reason("DUPLICATE_SOURCE", "Source identity is duplicated and requires disambiguation."))
            if quality_score == 0:
                blocking_reasons.append(_reason("INSUFFICIENT_EVIDENCE", "Evidence quality is insufficient."))
            if top_score < CONFIRM_MIN_SCORE:
                reasons.append(_reason("LOW_SCORE", "Top candidate is below the confirmation threshold."))
                decision = DecisionState.UNKNOWN
            elif margin < SUGGEST_MIN_MARGIN:
                blocking_reasons.append(_reason("INSUFFICIENT_MARGIN", "Top candidate is too close to its runner-up."))
                reasons.append(_reason("LOW_MARGIN", "Candidate ranking is ambiguous."))
                decision = DecisionState.CONFIRM
            elif top_score >= AUTO_MIN_SCORE and margin >= AUTO_MIN_MARGIN and not blocking_reasons and quality_name == "STRONG":
                reasons.append(_reason("AUTO_HIGH_SCORE_HIGH_MARGIN", "Top candidate exceeds threshold with sufficient margin."))
                decision = DecisionState.AUTO
            elif top_score >= SUGGEST_MIN_SCORE and margin >= SUGGEST_MIN_MARGIN and not any(item["code"] in {"TYPE_CONFLICT", "DUPLICATE_SOURCE"} for item in blocking_reasons):
                reasons.append(_reason("SUGGEST_REASONABLE_EVIDENCE", "Candidate has reasonable evidence but is not safe for automation."))
                decision = DecisionState.SUGGEST
            elif top_score >= CONFIRM_MIN_SCORE:
                reasons.append(_reason("AMBIGUOUS_STRUCTURE", "A plausible candidate exists but requires controlled review."))
                decision = DecisionState.CONFIRM
            else:
                reasons.append(_reason("INSUFFICIENT_EVIDENCE", "Evidence is insufficient for a candidate decision."))
                decision = DecisionState.UNKNOWN

            if blocking_reasons and decision == DecisionState.AUTO:
                decision = DecisionState.CONFIRM
                reasons.append(_reason("BLOCKED_AUTO", "A critical blocker prevents automatic eligibility."))
            if decision == DecisionState.CONFIRM and not blocking_reasons and quality_name == "INSUFFICIENT":
                blocking_reasons.append(_reason("INSUFFICIENT_EVIDENCE", "Evidence quality is insufficient."))

        decision_score = round(max(0.0, min(1.0, top_score * (0.7 + 0.3 * quality_score))), 4)
        knowledge_influence = 0.0
        learned = None
        if learned_evidence_index and top:
            identity = (*_source_identity(source), top.get("target_field"))
            learned = build_learned_evidence(learned_evidence_index.get(identity))
        if learned:
            evidence.append(learned)
            if learned["type"] == "LEARNED_MATCH":
                knowledge_influence = bounded_influence(learned)
                decision_score = round(min(1.0, decision_score + knowledge_influence), 4)
                reasons.append(_reason("KNOWLEDGE_SUPPORTED", "Company knowledge provides bounded advisory support for this mapping."))
            elif learned["type"] == "LEARNED_CONFLICT":
                blocking_reasons.append(_reason("LEARNING_CONFLICT", "Company knowledge reports a conflicting historical pattern for this source."))
                if decision == DecisionState.AUTO:
                    decision = DecisionState.CONFIRM
                    reasons.append(_reason("BLOCKED_BY_LEARNING_CONFLICT", "Automatic eligibility revoked due to conflicting company knowledge."))

        decisions.append({
            "source_field": source_field,
            "selected_candidate": ({"target_field": top.get("target_field"), "score": top_score} if top else None),
            "decision": decision.value,
            "decision_score": decision_score,
            "candidate_score": top_score,
            "runner_up": ({"target_field": runner.get("target_field"), "score": runner_score} if runner else None),
            "margin": round(max(0.0, min(1.0, margin)), 4),
            "evidence": evidence,
            "evidence_quality": quality_name,
            "decision_reasons": reasons,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
            "knowledge_influence": knowledge_influence,
            "knowledge_adapter_version": KNOWLEDGE_ADAPTER_VERSION if learned_evidence_index is not None else None,
            "mapping_engine_version": mapping_document.get("mapping_engine_version", "unknown"),
            "decision_engine_version": DECISION_ENGINE_VERSION,
        })

    counts = {state.value.lower(): 0 for state in DecisionState}
    for item in decisions:
        counts[item["decision"].lower()] += 1
    return {
        "mapping_engine_version": mapping_document.get("mapping_engine_version", "unknown"),
        "decision_engine_version": DECISION_ENGINE_VERSION,
        "import_batch_id": mapping_document.get("import_batch_id"),
        "structure_profile_id": mapping_document.get("structure_profile_id"),
        "decisions": decisions,
        "required_target_unmapped": [],
        "summary": {"total": len(decisions), **counts},
    }
