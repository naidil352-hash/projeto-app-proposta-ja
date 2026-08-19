import os
import uuid
from datetime import datetime, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from decision_engine import DECISION_ENGINE_VERSION

pytestmark = pytest.mark.integration


@pytest.fixture
async def decision_db():
    url = os.environ["TEST_MONGO_URL"]
    db_name = os.environ["TEST_DB_NAME"]
    if db_name != "proposta_ja_test":
        pytest.fail(f"SAFETY STOP: expected proposta_ja_test, got {db_name}")
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=5000)
    try:
        await client[db_name].command("ping")
    except Exception as exc:
        client.close()
        pytest.skip(f"MongoDB not available: {exc}")
    yield client[db_name]
    client.close()


def _candidate_document(company_id, batch_id, profile_id):
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
        "candidates": [
            {"source_field": {"sheet_name": "Clientes", "source_index": 0, "source_name": "CNPJ"}, "candidates": [{"target_field": "client_document", "score": 0.99, "evidence": strong}]},
            {"source_field": {"sheet_name": "Clientes", "source_index": 1, "source_name": "Referência"}, "candidates": [{"target_field": "product_code", "score": 0.40, "evidence": [{"type": "POSITION_HINT", "score": 0.3, "weight": 0.03, "detail": "weak"}]}]},
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.mark.asyncio
async def test_decision_api_persistence_summary_idempotency_and_tenant_isolation(decision_db, monkeypatch):
    import server

    company_a = "decision-test-a-" + uuid.uuid4().hex
    company_b = "decision-test-b-" + uuid.uuid4().hex
    batch_a = "decision-batch-a-" + uuid.uuid4().hex
    batch_b = "decision-batch-b-" + uuid.uuid4().hex
    profile_a = "decision-profile-a-" + uuid.uuid4().hex
    profile_b = "decision-profile-b-" + uuid.uuid4().hex
    user_a = {"id": "decision-user-a-" + uuid.uuid4().hex, "company_id": company_a}
    user_b = {"id": "decision-user-b-" + uuid.uuid4().hex, "company_id": company_b}
    try:
        await decision_db.mapping_candidates.insert_many([
            _candidate_document(company_a, batch_a, profile_a),
            _candidate_document(company_b, batch_b, profile_b),
        ])
        monkeypatch.setattr(server, "db", decision_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        first = await server.analyze_import_mapping_decisions(batch_a, user_a)
        second = await server.analyze_import_mapping_decisions(batch_a, user_a)
        fetched = await server.get_import_mapping_decisions(batch_a, user_a)
        field = await server.get_import_mapping_decision_for_field(batch_a, "CNPJ", user_a)
        summary = await server.get_import_mapping_decisions_summary(batch_a, user_a)

        assert first["decision_engine_version"] == DECISION_ENGINE_VERSION
        assert first["summary"] == {"total": 2, "auto": 1, "suggest": 0, "confirm": 0, "unknown": 1}
        assert second["decisions"] == first["decisions"]
        assert fetched["decisions"] == first["decisions"]
        assert field["decisions"][0]["decision"] == "AUTO"
        assert summary == first["summary"]

        with pytest.raises(Exception):
            await server.get_import_mapping_decisions(batch_a, user_b)

        audit_actions = await decision_db.audit_logs.find({"company_id": company_a, "entity_type": "mapping_decisions"}).to_list(None)
        assert {item["action"] for item in audit_actions} == {"DECISION_ANALYSIS_STARTED", "DECISION_ANALYSIS_COMPLETED"}
        assert await decision_db.clients.count_documents({"company_id": company_a}) == 0
        assert await decision_db.products.count_documents({"company_id": company_a}) == 0
        assert await decision_db.proposals.count_documents({"company_id": company_a}) == 0
        assert await decision_db.opportunities.count_documents({"company_id": company_a}) == 0
    finally:
        await decision_db.mapping_decisions.delete_many({"company_id": {"$in": [company_a, company_b]}})
        await decision_db.mapping_candidates.delete_many({"company_id": {"$in": [company_a, company_b]}})
        await decision_db.audit_logs.delete_many({"company_id": {"$in": [company_a, company_b]}})
