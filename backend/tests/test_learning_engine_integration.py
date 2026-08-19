import json
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.requests import Request

pytestmark = pytest.mark.integration


@pytest.fixture
async def learning_db():
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


def request_json(payload):
    body = json.dumps(payload).encode()
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [(b"content-type", b"application/json")], "client": ("test", 1), "root_path": "", "scheme": "http", "server": ("test", 80), "query_string": b""}, receive=receive)


@pytest.mark.asyncio
async def test_learning_feedback_projection_privacy_rebuild_and_tenant_isolation(learning_db, monkeypatch):
    import server
    company_a = "learn-a-" + uuid.uuid4().hex
    company_b = "learn-b-" + uuid.uuid4().hex
    user_a = {"id": "user-a-" + uuid.uuid4().hex, "company_id": company_a}
    user_b = {"id": "user-b-" + uuid.uuid4().hex, "company_id": company_b}
    source = {"normalized_name": "vlr_unit", "type": "DECIMAL", "sheet_context": "orcamentos", "patterns": ["CURRENCY_LIKE"]}
    try:
        monkeypatch.setattr(server, "db", learning_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)
        first = await server.create_learning_feedback(request_json({"action": "CONFIRM", "source_pattern": source, "target_field": "item_unit_price", "idempotency_key": "same-feedback"}), user_a)
        second = await server.create_learning_feedback(request_json({"action": "CONFIRM", "source_pattern": source, "target_field": "item_unit_price", "idempotency_key": "same-feedback"}), user_a)
        await server.create_learning_feedback(request_json({"action": "CORRECT", "source_pattern": source, "target_field": "item_total", "idempotency_key": "correction"}), user_a)
        await server.create_learning_feedback(request_json({"action": "CONFIRM", "source_pattern": source, "target_field": "product_price", "idempotency_key": "company-b"}), user_b)

        knowledge_a = await server.list_company_knowledge(user_a)
        knowledge_b = await server.list_company_knowledge(user_b)
        summary = await server.get_company_knowledge_summary(user_a)
        events = await server.list_learning_events(user_a)
        rebuilt = await server.rebuild_learning_knowledge(user_a)

        assert first["event"]["event_id"] == second["event"]["event_id"]
        assert len(await learning_db.learning_events.find({"company_id": company_a}).to_list(None)) == 2
        assert {item["company_id"] for item in knowledge_a} == {company_a}
        assert {item["company_id"] for item in knowledge_b} == {company_b}
        assert summary["conflicted"] >= 1
        assert events and all("original_record_json" not in event for event in events)
        assert rebuilt["rebuilt"] is True
        assert await learning_db.raw_records.count_documents({"company_id": company_a}) == 0
    finally:
        for collection in ["learning_events", "learning_observations", "company_knowledge", "learning_feedback", "learning_versions", "audit_logs"]:
            await learning_db[collection].delete_many({"company_id": {"$in": [company_a, company_b]}})
