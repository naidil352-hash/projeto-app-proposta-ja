import os
import uuid
from datetime import datetime, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from mapping_engine import MAPPING_ENGINE_VERSION

pytestmark = pytest.mark.integration


@pytest.fixture
async def mapping_db():
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


def _profile(company_id, batch_id, profile_id):
    return {
        "id": profile_id,
        "company_id": company_id,
        "import_batch_id": batch_id,
        "analyzer_version": "1.0.0",
        "status": "ANALYZED",
        "sheets": [{
            "sheet_name": "Clientes",
            "structure_status": "TABULAR",
            "columns": [{
                "source_name": "CNPJ",
                "source_index": 0,
                "data_type": "STRING",
                "pattern_flags": ["CNPJ_LIKE"],
                "cardinality_class": "UNIQUE_LIKE",
                "unique_count": 1,
                "unique_ratio": 1.0,
                "null_ratio": 0.0,
                "sample_values": ["00.000.000/0001-00"],
            }],
        }],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.mark.asyncio
async def test_mapping_api_persistence_idempotency_and_tenant_isolation(mapping_db, monkeypatch):
    import server

    company_a = "mapping-test-a-" + uuid.uuid4().hex
    company_b = "mapping-test-b-" + uuid.uuid4().hex
    batch_a = "mapping-batch-a-" + uuid.uuid4().hex
    batch_b = "mapping-batch-b-" + uuid.uuid4().hex
    profile_a_id = "mapping-profile-a-" + uuid.uuid4().hex
    profile_b_id = "mapping-profile-b-" + uuid.uuid4().hex
    user_a = {"id": "mapping-user-a-" + uuid.uuid4().hex, "company_id": company_a}
    user_b = {"id": "mapping-user-b-" + uuid.uuid4().hex, "company_id": company_b}
    try:
        await mapping_db.import_structure_profiles.insert_many([
            _profile(company_a, batch_a, profile_a_id),
            _profile(company_b, batch_b, profile_b_id),
        ])
        monkeypatch.setattr(server, "db", mapping_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        first = await server.analyze_import_mapping_candidates(batch_a, user_a)
        second = await server.analyze_import_mapping_candidates(batch_a, user_a)
        fetched = await server.get_import_mapping_candidates(batch_a, user_a)
        field = await server.get_import_mapping_candidates_for_field(batch_a, "CNPJ", None, user_a)

        assert first["mapping_engine_version"] == MAPPING_ENGINE_VERSION
        assert first["company_id"] == company_a
        assert first["structure_profile_id"] == profile_a_id
        assert second["id"] == first["id"]
        assert fetched["id"] == first["id"]
        assert field["matches"][0]["source_field"]["source_name"] == "CNPJ"
        assert any(candidate["target_field"] == "client_document" for candidate in field["matches"][0]["candidates"])

        with pytest.raises(Exception):
            await server.get_import_mapping_candidates(batch_a, user_b)

        audits = await mapping_db.audit_logs.find({
            "company_id": company_a,
            "entity_type": "mapping_candidates",
        }).to_list(None)
        assert {audit["action"] for audit in audits} == {
            "MAPPING_ANALYSIS_STARTED",
            "MAPPING_ANALYSIS_COMPLETED",
        }
        assert await mapping_db.clients.count_documents({"company_id": company_a}) == 0
        assert await mapping_db.products.count_documents({"company_id": company_a}) == 0
        assert await mapping_db.proposals.count_documents({"company_id": company_a}) == 0
    finally:
        await mapping_db.mapping_candidates.delete_many({"company_id": {"$in": [company_a, company_b]}})
        await mapping_db.import_structure_profiles.delete_many({"company_id": {"$in": [company_a, company_b]}})
        await mapping_db.audit_logs.delete_many({"company_id": {"$in": [company_a, company_b]}})
