"""Phase 3.1 — Knowledge -> Decision Intelligence bridge (integration tests).

Uses exclusively TEST_MONGO_URL / TEST_DB_NAME=proposta_ja_test.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from decision_engine import DECISION_ENGINE_VERSION
from knowledge_adapter import KNOWLEDGE_ADAPTER_VERSION
from learning_engine import pattern_signature

pytestmark = pytest.mark.integration


@pytest.fixture
async def bridge_db():
    url = os.environ["TEST_MONGO_URL"]
    name = os.environ["TEST_DB_NAME"]
    if name != "proposta_ja_test":
        pytest.fail(f"SAFETY STOP: expected proposta_ja_test, got {name}")
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=5000)
    try:
        await client[name].command("ping")
    except Exception as exc:
        client.close()
        pytest.skip(f"MongoDB unavailable: {exc}")
    yield client[name]
    client.close()


def _profile(company_id, batch_id, profile_id):
    return {
        "id": profile_id,
        "company_id": company_id,
        "import_batch_id": batch_id,
        "analyzer_version": "1.0.0",
        "sheets": [{
            "sheet_name": "Clientes",
            "columns": [{"source_name": "CNPJ", "source_index": 0, "data_type": "STRING", "pattern_flags": ["CNPJ_LIKE"]}],
        }],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _mapping_candidates(company_id, batch_id, profile_id, score, runner_score):
    strong = [
        {"type": "NAME_MATCH", "score": 1.0, "weight": 0.35, "detail": "exact"},
        {"type": "TYPE_COMPATIBILITY", "score": 1.0, "weight": 0.18, "detail": "compatible"},
        {"type": "PATTERN_COMPATIBILITY", "score": 1.0, "weight": 0.18, "detail": "CNPJ_LIKE"},
    ]
    return {
        "id": "candidate-" + uuid.uuid4().hex,
        "company_id": company_id,
        "import_batch_id": batch_id,
        "structure_profile_id": profile_id,
        "mapping_engine_version": "1.0.0",
        "candidates": [{
            "source_field": {"sheet_name": "Clientes", "source_index": 0, "source_name": "CNPJ"},
            "candidates": [
                {"target_field": "client_document", "score": score, "evidence": strong},
                {"target_field": "client_code", "score": runner_score, "evidence": []},
            ],
        }],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _knowledge(company_id, status, confidence, support):
    source_pattern = {"normalized_name": "CNPJ", "type": "STRING", "sheet_context": "Clientes", "patterns": ["CNPJ_LIKE"]}
    return {
        "observation_id": "observation-" + uuid.uuid4().hex,
        "company_id": company_id,
        "source_pattern": source_pattern,
        "pattern_signature": pattern_signature(source_pattern, "client_document"),
        "target_field": "client_document",
        "status": status,
        "confidence": confidence,
        "support_count": support,
    }


@pytest.mark.asyncio
async def test_conflicted_knowledge_downgrades_auto_and_is_audited(bridge_db, monkeypatch):
    import server
    company_a = "bridge-a-" + uuid.uuid4().hex
    batch_a = "bridge-batch-a-" + uuid.uuid4().hex
    profile_a = "bridge-profile-a-" + uuid.uuid4().hex
    user_a = {"id": "bridge-user-a-" + uuid.uuid4().hex, "company_id": company_a}
    try:
        await bridge_db.import_structure_profiles.insert_one(_profile(company_a, batch_a, profile_a))
        await bridge_db.mapping_candidates.insert_one(_mapping_candidates(company_a, batch_a, profile_a, 0.99, 0.2))
        await bridge_db.company_knowledge.insert_one(_knowledge(company_a, "CONFLICTED", 0.9, 10))
        monkeypatch.setattr(server, "db", bridge_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        result = await server.analyze_import_mapping_decisions(batch_a, user_a)
        decision = result["decisions"][0]

        assert decision["decision"] == "CONFIRM"
        assert decision["decision_engine_version"] == DECISION_ENGINE_VERSION
        assert decision["knowledge_adapter_version"] == KNOWLEDGE_ADAPTER_VERSION
        assert any(reason["code"] == "LEARNING_CONFLICT" for reason in decision["blocking_reasons"])
        assert any(item["type"] == "LEARNED_CONFLICT" for item in decision["evidence"])

        audits = await bridge_db.audit_logs.find({"company_id": company_a, "action": "DECISION_KNOWLEDGE_FUSION_APPLIED"}).to_list(None)
        assert len(audits) == 1
    finally:
        for collection in ["mapping_decisions", "mapping_candidates", "import_structure_profiles", "company_knowledge", "audit_logs"]:
            await bridge_db[collection].delete_many({"company_id": company_a})


@pytest.mark.asyncio
async def test_tenant_isolation_knowledge_never_crosses_companies(bridge_db, monkeypatch):
    import server
    company_a = "bridge-iso-a-" + uuid.uuid4().hex
    company_b = "bridge-iso-b-" + uuid.uuid4().hex
    batch_a = "bridge-iso-batch-a-" + uuid.uuid4().hex
    batch_b = "bridge-iso-batch-b-" + uuid.uuid4().hex
    profile_a = "bridge-iso-profile-a-" + uuid.uuid4().hex
    profile_b = "bridge-iso-profile-b-" + uuid.uuid4().hex
    user_a = {"id": "bridge-iso-user-a-" + uuid.uuid4().hex, "company_id": company_a}
    user_b = {"id": "bridge-iso-user-b-" + uuid.uuid4().hex, "company_id": company_b}
    try:
        await bridge_db.import_structure_profiles.insert_many([
            _profile(company_a, batch_a, profile_a),
            _profile(company_b, batch_b, profile_b),
        ])
        await bridge_db.mapping_candidates.insert_many([
            _mapping_candidates(company_a, batch_a, profile_a, 0.80, 0.30),
            _mapping_candidates(company_b, batch_b, profile_b, 0.80, 0.30),
        ])
        # Only company A has knowledge; company B must never be influenced by it.
        await bridge_db.company_knowledge.insert_one(_knowledge(company_a, "ACTIVE", 0.95, 20))
        monkeypatch.setattr(server, "db", bridge_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        result_a = await server.analyze_import_mapping_decisions(batch_a, user_a)
        result_b = await server.analyze_import_mapping_decisions(batch_b, user_b)
        decision_a = result_a["decisions"][0]
        decision_b = result_b["decisions"][0]

        assert decision_a["knowledge_influence"] > 0
        assert any(item["type"] == "LEARNED_MATCH" for item in decision_a["evidence"])
        assert decision_b["knowledge_influence"] == 0
        assert not any(item["type"] in {"LEARNED_MATCH", "LEARNED_CONFLICT"} for item in decision_b["evidence"])
    finally:
        for collection in ["mapping_decisions", "mapping_candidates", "import_structure_profiles", "company_knowledge", "audit_logs"]:
            await bridge_db[collection].delete_many({"company_id": {"$in": [company_a, company_b]}})


@pytest.mark.asyncio
async def test_determinism_across_repeated_calls_is_idempotent(bridge_db, monkeypatch):
    import server
    company_a = "bridge-det-a-" + uuid.uuid4().hex
    batch_a = "bridge-det-batch-a-" + uuid.uuid4().hex
    profile_a = "bridge-det-profile-a-" + uuid.uuid4().hex
    user_a = {"id": "bridge-det-user-a-" + uuid.uuid4().hex, "company_id": company_a}
    try:
        await bridge_db.import_structure_profiles.insert_one(_profile(company_a, batch_a, profile_a))
        await bridge_db.mapping_candidates.insert_one(_mapping_candidates(company_a, batch_a, profile_a, 0.85, 0.3))
        await bridge_db.company_knowledge.insert_one(_knowledge(company_a, "ACTIVE", 0.9, 10))
        monkeypatch.setattr(server, "db", bridge_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        first = await server.analyze_import_mapping_decisions(batch_a, user_a)
        second = await server.analyze_import_mapping_decisions(batch_a, user_a)
        assert first["decisions"] == second["decisions"]
    finally:
        for collection in ["mapping_decisions", "mapping_candidates", "import_structure_profiles", "company_knowledge", "audit_logs"]:
            await bridge_db[collection].delete_many({"company_id": company_a})
