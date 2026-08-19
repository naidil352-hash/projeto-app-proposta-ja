import copy
import os
import uuid
from datetime import datetime, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.requests import Request


pytestmark = pytest.mark.integration


@pytest.fixture
async def application_db():
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


def _request(payload):
    body = __import__("json").dumps(payload).encode()
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"content-type", b"application/json")],
        "client": ("test", 1),
        "root_path": "",
        "scheme": "http",
        "server": ("test", 80),
        "query_string": b"",
    }
    return Request(scope, receive=receive)


def _profile(company, batch):
    return {
        "id": "profile-" + uuid.uuid4().hex,
        "company_id": company,
        "import_batch_id": batch,
        "analyzer_version": "1.0.0",
        "sheets": [{"sheet_name": "Clientes", "columns": [{"source_name": "CNPJ", "source_index": 0, "data_type": "STRING", "pattern_flags": ["CNPJ_LIKE"]}, {"source_name": "Nome", "source_index": 1, "data_type": "STRING", "pattern_flags": []}]}],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.mark.asyncio
async def test_full_confirmation_template_plan_apply_and_raw_preservation(application_db, monkeypatch):
    import server
    company = "application-test-" + uuid.uuid4().hex
    other_company = "application-other-" + uuid.uuid4().hex
    batch = "application-batch-" + uuid.uuid4().hex
    user = {"id": "application-user-" + uuid.uuid4().hex, "company_id": company}
    raw = {"id": "raw-" + uuid.uuid4().hex, "company_id": company, "import_batch_id": batch, "source_sheet": "Clientes", "source_row": 2, "original_record_json": {"CNPJ": "ABC", "Nome": "ACME"}, "raw_metadata": {"headers": ["CNPJ", "Nome"]}}
    try:
        await application_db.import_structure_profiles.insert_one(_profile(company, batch))
        await application_db.raw_records.insert_one(raw)
        monkeypatch.setattr(server, "db", application_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        confirmation = await server.create_import_mapping_confirmation(batch, _request({
            "source_field_identity": {"sheet_name": "Clientes", "source_name": "CNPJ", "source_index": 0},
            "target_field": "client_document",
            "action": "CONFIRM",
        }), user)
        template = await server.create_import_mapping_template(batch, _request({"name": "Clientes padrão"}), user)
        plan = await server.create_mapping_application_plan(batch, _request({"template_id": template["template_id"]}), user)
        before = copy.deepcopy(await application_db.raw_records.find_one({"id": raw["id"]}))
        applied = await server.apply_mapping_application(batch, _request({"template_id": template["template_id"]}), user)
        repeated = await server.apply_mapping_application(batch, _request({"template_id": template["template_id"]}), user)
        retry = await server.apply_mapping_application(batch, _request({"template_id": template["template_id"], "retry": True}), user)
        records = await server.get_standard_records(batch, user)

        assert template["template_version"] == 1
        assert plan["summary"]["ready"] == 1
        assert applied["status"] == "PARTIAL"
        assert repeated["application_id"] == applied["application_id"]
        assert retry["application_id"] != applied["application_id"]
        assert retry["run_number"] == 2
        assert len(records) == 1
        assert records[0]["data"] == {"client_document": "ABC"}
        assert records[0]["source_record_id"] == raw["id"]
        assert records[0]["field_provenance"][0]["target"] == "client_document"
        assert await application_db.raw_records.find_one({"id": raw["id"]}) == before
        assert await application_db.clients.count_documents({"company_id": company}) == 0
        assert await application_db.products.count_documents({"company_id": company}) == 0
        assert await application_db.proposals.count_documents({"company_id": company}) == 0
        assert await server.get_standard_records(batch, {"id": "other", "company_id": other_company}) == []
        actions = await application_db.audit_logs.find({"company_id": company, "entity_type": "mapping_application"}).to_list(None)
        assert {item["action"] for item in actions} >= {"MAPPING_APPLICATION_STARTED", "MAPPING_APPLICATION_PARTIAL"}
    finally:
        for collection in ["standard_records", "application_errors", "mapping_applications", "mapping_templates", "mapping_confirmations", "import_structure_profiles", "raw_records", "audit_logs"]:
            await application_db[collection].delete_many({"company_id": {"$in": [company, other_company]}})
