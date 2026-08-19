import os
import uuid
from datetime import datetime, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from structure_analyzer import ANALYZER_VERSION, analyze_structure

pytestmark = pytest.mark.integration


@pytest.fixture
async def structure_db():
    url = os.environ["TEST_MONGO_URL"]
    db_name = os.environ["TEST_DB_NAME"]
    if db_name != "proposta_ja_test":
        pytest.fail(f"SAFETY STOP: expected proposta_ja_test, got {db_name}")
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=5000)
    try:
        await client.admin.command("ping")
    except Exception as exc:
        client.close()
        pytest.skip(f"MongoDB not available: {exc}")
    yield client[db_name]
    client.close()


def _record(company_id, batch_id, value):
    return {
        "id": str(uuid.uuid4()),
        "company_id": company_id,
        "import_batch_id": batch_id,
        "source_sheet": "CSV",
        "source_row": 2,
        "original_record_json": {"Valor": value},
        "raw_metadata": {"header_row": 1, "header_detection_status": "DETECTED"},
    }


@pytest.mark.asyncio
async def test_structure_profile_persistence_tenant_isolation_and_idempotency(structure_db):
    company_a = "structure-test-a-" + uuid.uuid4().hex
    company_b = "structure-test-b-" + uuid.uuid4().hex
    batch_id = "batch-" + uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    profile = analyze_structure(
        {"filename": "values.csv", "file_type": "CSV", "file_size": 10, "checksum": uuid.uuid4().hex},
        [_record(company_a, batch_id, "10.50")],
    )
    profile.update({
        "id": "profile-" + uuid.uuid4().hex,
        "company_id": company_a,
        "import_batch_id": batch_id,
        "created_at": now,
        "updated_at": now,
    })
    audit_started = {"id": str(uuid.uuid4()), "company_id": company_a, "action": "STRUCTURE_ANALYSIS_STARTED", "entity_id": batch_id}
    audit_completed = {"id": str(uuid.uuid4()), "company_id": company_a, "action": "STRUCTURE_ANALYSIS_COMPLETED", "entity_id": profile["id"]}
    try:
        await structure_db.import_structure_profiles.insert_one(profile)
        await structure_db.audit_logs.insert_many([audit_started, audit_completed])
        other_profile = {key: value for key, value in profile.items() if key != "_id"}
        other_profile.update({"id": "other-" + uuid.uuid4().hex, "company_id": company_b})
        await structure_db.import_structure_profiles.insert_one(other_profile)

        same_version = await structure_db.import_structure_profiles.find_one({
            "company_id": company_a,
            "import_batch_id": batch_id,
            "analyzer_version": ANALYZER_VERSION,
        })
        other_tenant = await structure_db.import_structure_profiles.find_one({
            "company_id": company_b,
            "import_batch_id": batch_id,
        })
        audits = await structure_db.audit_logs.find({"company_id": company_a, "entity_id": {"$in": [batch_id, profile["id"]]}}).to_list(None)

        assert same_version["id"] == profile["id"]
        assert other_tenant["company_id"] == company_b
        assert {audit["action"] for audit in audits} == {
            "STRUCTURE_ANALYSIS_STARTED",
            "STRUCTURE_ANALYSIS_COMPLETED",
        }
    finally:
        await structure_db.import_structure_profiles.delete_many({"company_id": {"$in": [company_a, company_b]}})
        await structure_db.audit_logs.delete_many({"company_id": {"$in": [company_a, company_b]}})


@pytest.mark.asyncio
async def test_structure_api_analyze_get_sheet_and_idempotency(structure_db, monkeypatch):
    import server

    company_id = "structure-api-" + uuid.uuid4().hex
    batch_id = "batch-api-" + uuid.uuid4().hex
    user = {"id": "user-api-" + uuid.uuid4().hex, "company_id": company_id}
    batch = {
        "id": batch_id,
        "company_id": company_id,
        "filename": "api.csv",
        "file_type": "CSV",
        "file_size": 12,
        "checksum": uuid.uuid4().hex,
        "status": "COMPLETED",
        "deleted": False,
    }
    record = _record(company_id, batch_id, "R$ 10,50")
    try:
        await structure_db.import_batches.insert_one(batch)
        await structure_db.raw_records.insert_one(record)
        monkeypatch.setattr(server, "db", structure_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        first = await server.analyze_import_structure(batch_id, user)
        second = await server.analyze_import_structure(batch_id, user)
        fetched = await server.get_import_structure(batch_id, user)
        sheet = await server.get_import_structure_sheet(batch_id, "CSV", user)

        assert first["import_batch_id"] == batch_id
        assert first["company_id"] == company_id
        assert second["id"] == first["id"]
        assert fetched["id"] == first["id"]
        assert sheet["sheet_name"] == "CSV"
        updated_batch = await structure_db.import_batches.find_one({"id": batch_id})
        assert updated_batch["profile_id"] == first["id"]
        assert updated_batch["profile_version"] == ANALYZER_VERSION
    finally:
        await structure_db.import_structure_profiles.delete_many({"company_id": company_id})
        await structure_db.raw_records.delete_many({"company_id": company_id})
        await structure_db.import_batches.delete_many({"company_id": company_id})
        await structure_db.audit_logs.delete_many({"company_id": company_id})
