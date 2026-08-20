from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.requests import Request

pytestmark = pytest.mark.integration


@pytest.fixture
async def whatsapp_db():
    name = os.environ["TEST_DB_NAME"]
    if name != "proposta_ja_test":
        pytest.fail(f"SAFETY STOP: expected proposta_ja_test, got {name}")
    client = AsyncIOMotorClient(os.environ["TEST_MONGO_URL"], serverSelectionTimeoutMS=5000)
    try:
        await client[name].command("ping")
    except Exception as exc:
        client.close()
        pytest.skip(f"Mongo unavailable: {exc}")
    yield client[name]
    client.close()


def request_json(payload: dict) -> Request:
    body = json.dumps(payload).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b""}, receive)


def documents(company: str, suffix: str):
    now = datetime.now(timezone.utc).isoformat()
    client_id = f"client-{suffix}"
    opportunity_id = f"opp-{suffix}"
    plan_id = f"plan-{suffix}"
    job_id = f"job-{suffix}"
    request_id = f"comm-{suffix}"
    draft_id = f"draft-{suffix}"
    return {
        "clients": {"company_id": company, "id": client_id, "name": "Cliente", "phone": "+55 11 99999-9999", "deleted": False},
        "opportunities": {"company_id": company, "id": opportunity_id, "client_id": client_id, "proposal_id": None, "deleted": False},
        "action_plans": {"company_id": company, "action_plan_id": plan_id, "opportunity_id": opportunity_id, "status": "APPROVED", "actions": [{"action_id": f"action-{suffix}"}]},
        "execution_jobs": {"company_id": company, "execution_job_id": job_id, "action_plan_id": plan_id, "action_id": f"action-{suffix}", "opportunity_id": opportunity_id, "status": "CREATED"},
        "communication_requests": {"company_id": company, "request_id": request_id, "execution_job_id": job_id, "action_plan_id": plan_id, "action_id": f"action-{suffix}", "opportunity_id": opportunity_id, "status": "PREPARED"},
        "message_drafts": {"company_id": company, "message_draft_id": draft_id, "communication_request_id": request_id, "execution_job_id": job_id, "action_plan_id": plan_id, "action_id": f"action-{suffix}", "opportunity_id": opportunity_id, "status": "APPROVED", "human_approved": True, "source_snapshot_hash": f"hash-{suffix}", "content": {"opening": "[TESTE PROPOSTA JÁ]", "body": "Esta é uma mensagem de validação.", "call_to_action": None, "closing": None}, "edited_content": None},
        "whatsapp_recipient_consents": {"company_id": company, "client_id": client_id, "status": "OPTED_IN", "blocked": False, "evidence": "Teste autorizado", "source": "TEST"},
        "whatsapp_templates": {"company_id": company, "name": "hello_world", "language": "en_US", "version": "1", "category": "UTILITY", "status": "APPROVED", "variables": [], "resolved_variables": {}, "estimated_cost": 0.0},
    }


async def insert_documents(database, docs):
    for collection, document in docs.items():
        await database[collection].insert_one(document)


async def cleanup(database, company):
    for collection in ["clients", "opportunities", "action_plans", "execution_jobs", "communication_requests", "message_drafts", "whatsapp_recipient_consents", "whatsapp_templates", "whatsapp_messages", "whatsapp_usage", "audit_logs"]:
        await database[collection].delete_many({"company_id": company})


@pytest.mark.asyncio
async def test_prepare_and_simulate_are_idempotent_and_never_mutate_upstream(whatsapp_db, monkeypatch):
    import server

    company = "wa-sim-" + uuid.uuid4().hex
    suffix = uuid.uuid4().hex
    user = {"id": "user-" + suffix, "company_id": company}
    docs = documents(company, suffix)
    try:
        await insert_documents(whatsapp_db, docs)
        monkeypatch.setattr(server, "db", whatsapp_db)
        baselines = {name: await whatsapp_db[name].find_one({"company_id": company}, {"_id": 0}) for name in docs}
        draft_id = docs["message_drafts"]["message_draft_id"]
        body = {"mode": "SIMULATION", "template_name": "hello_world", "template_language": "en_US", "template_version": "1"}
        first = await server.prepare_whatsapp_send(draft_id, request_json(body), user)
        second = await server.prepare_whatsapp_send(draft_id, request_json(body), user)
        simulated = await server.send_whatsapp_message(draft_id, request_json({"confirm_send": True}), user)
        assert first["message_id"] == second["message_id"]
        assert await whatsapp_db.whatsapp_messages.count_documents({"company_id": company}) == 1
        assert simulated["provider_status"] == "SIMULATED"
        assert simulated["result"]["external_side_effect"] is False
        for collection, baseline in baselines.items():
            assert await whatsapp_db[collection].find_one({"company_id": company}, {"_id": 0}) == baseline
        audits = await whatsapp_db.audit_logs.find({"company_id": company, "entity_type": "whatsapp_message"}).to_list(None)
        assert {item["action"] for item in audits} >= {"WHATSAPP_SEND_REQUESTED", "WHATSAPP_SEND_APPROVED"}
        assert not any(item["action"] == "WHATSAPP_SEND_STARTED" for item in audits)
    finally:
        await cleanup(whatsapp_db, company)


@pytest.mark.asyncio
async def test_sandbox_all_guards_then_exactly_one_provider_call(whatsapp_db, monkeypatch):
    import server

    company = "wa-sandbox-" + uuid.uuid4().hex
    suffix = uuid.uuid4().hex
    user = {"id": "user-" + suffix, "company_id": company}
    docs = documents(company, suffix)
    calls = []

    class FakeProvider:
        def execute(self, message):
            calls.append(message["message_id"])
            return {"provider_message_id": "wamid.test", "provider_request_id": "trace-test", "status_code": 200}

    try:
        await insert_documents(whatsapp_db, docs)
        monkeypatch.setattr(server, "db", whatsapp_db)
        for key, value in {
            "WHATSAPP_ENABLED": "true", "WHATSAPP_SANDBOX_ENABLED": "true", "WHATSAPP_LIVE_ENABLED": "false",
            "WHATSAPP_REQUIRE_HUMAN_APPROVAL": "true", "WHATSAPP_ALLOW_EXTERNAL_SIDE_EFFECTS": "true",
            "WHATSAPP_GLOBAL_KILL_SWITCH": "false", "WHATSAPP_ACCESS_TOKEN": "test-secret", "WHATSAPP_PHONE_NUMBER_ID": "phone-id",
            "WHATSAPP_BUSINESS_ACCOUNT_ID": "waba-id", "WHATSAPP_APP_ID": "app-id", "WHATSAPP_APP_SECRET": "app-secret",
            "WHATSAPP_VERIFY_TOKEN": "verify", "WHATSAPP_CONFIG_COMPANY_ID": company, "WHATSAPP_TEST_RECIPIENTS": "+5511999999999",
        }.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr(server.WhatsAppProviderFactory, "create", staticmethod(lambda mode, configuration: FakeProvider()))
        draft_id = docs["message_drafts"]["message_draft_id"]
        prepared = await server.prepare_whatsapp_send(draft_id, request_json({"mode": "SANDBOX", "template_name": "hello_world", "template_language": "en_US", "template_version": "1"}), user)
        accepted = await server.send_whatsapp_message(draft_id, request_json({"confirm_send": True}), user)
        repeated = await server.send_whatsapp_message(draft_id, request_json({"confirm_send": True}), user)
        assert prepared["status"] == "PREPARED"
        assert accepted["provider_message_id"] == "wamid.test"
        assert repeated["provider_message_id"] == "wamid.test"
        assert calls == [prepared["message_id"]]
        persisted = await whatsapp_db.whatsapp_messages.find({"company_id": company}, {"_id": 0}).to_list(None)
        audits = await whatsapp_db.audit_logs.find({"company_id": company}, {"_id": 0}).to_list(None)
        serialized = json.dumps({"messages": persisted, "audits": audits}, default=str)
        assert "test-secret" not in serialized
        assert "app-secret" not in serialized
    finally:
        await cleanup(whatsapp_db, company)


@pytest.mark.asyncio
async def test_tenant_isolation_message_status_and_conversation(whatsapp_db, monkeypatch):
    import server

    company_a = "wa-a-" + uuid.uuid4().hex
    company_b = "wa-b-" + uuid.uuid4().hex
    docs_a = documents(company_a, uuid.uuid4().hex)
    docs_b = documents(company_b, uuid.uuid4().hex)
    user_a = {"id": "a", "company_id": company_a}
    user_b = {"id": "b", "company_id": company_b}
    try:
        await insert_documents(whatsapp_db, docs_a)
        await insert_documents(whatsapp_db, docs_b)
        monkeypatch.setattr(server, "db", whatsapp_db)
        msg_a = await server.prepare_whatsapp_send(docs_a["message_drafts"]["message_draft_id"], request_json({"mode": "SIMULATION", "template_name": "hello_world", "template_language": "en_US", "template_version": "1"}), user_a)
        with pytest.raises(Exception):
            await server.get_whatsapp_message(msg_a["message_id"], user_b)
        with pytest.raises(Exception):
            await server.get_whatsapp_conversation(docs_a["clients"]["id"], user_b)
    finally:
        await cleanup(whatsapp_db, company_a)
        await cleanup(whatsapp_db, company_b)


@pytest.mark.asyncio
async def test_real_sandbox_send_is_skipped_without_every_explicit_guard(whatsapp_db, monkeypatch):
    import server

    recipient = os.environ.get("WHATSAPP_REAL_TEST_RECIPIENT")
    template_name = os.environ.get("WHATSAPP_REAL_TEST_TEMPLATE_NAME")
    required = [
        os.environ.get("WHATSAPP_REAL_TEST_ENABLED") == "true",
        os.environ.get("WHATSAPP_GLOBAL_KILL_SWITCH") == "false",
        os.environ.get("WHATSAPP_SANDBOX_ENABLED") == "true",
        os.environ.get("WHATSAPP_ALLOW_EXTERNAL_SIDE_EFFECTS") == "true",
        os.environ.get("WHATSAPP_REAL_TEST_TEMPLATE_CONFIRMED_TEST_ONLY") == "true",
        bool(recipient),
        bool(template_name),
        recipient in os.environ.get("WHATSAPP_TEST_RECIPIENTS", "").split(","),
    ]
    if not all(required):
        pytest.skip("Real WhatsApp sandbox test is fail-closed and not explicitly enabled")
    company = os.environ.get("WHATSAPP_CONFIG_COMPANY_ID")
    if not company:
        pytest.skip("WHATSAPP_CONFIG_COMPANY_ID is required for isolated real test")
    suffix = "real-" + uuid.uuid4().hex
    user = {"id": "real-test-operator", "company_id": company}
    docs = documents(company, suffix)
    docs["clients"]["phone"] = recipient
    docs["whatsapp_templates"].update({
        "name": template_name,
        "language": os.environ.get("WHATSAPP_REAL_TEST_TEMPLATE_LANGUAGE", "pt_BR"),
        "version": os.environ.get("WHATSAPP_REAL_TEST_TEMPLATE_VERSION", "1"),
        "category": os.environ.get("WHATSAPP_REAL_TEST_TEMPLATE_CATEGORY", "UTILITY"),
    })
    try:
        await insert_documents(whatsapp_db, docs)
        monkeypatch.setattr(server, "db", whatsapp_db)
        draft_id = docs["message_drafts"]["message_draft_id"]
        await server.prepare_whatsapp_send(draft_id, request_json({
            "mode": "SANDBOX",
            "template_name": docs["whatsapp_templates"]["name"],
            "template_language": docs["whatsapp_templates"]["language"],
            "template_version": docs["whatsapp_templates"]["version"],
        }), user)
        result = await server.send_whatsapp_message(draft_id, request_json({"confirm_send": True}), user)
        assert result["provider_message_id"]
        assert result["provider_status"] == "ACCEPTED"
        assert await whatsapp_db.whatsapp_messages.count_documents({"company_id": company, "direction": {"$ne": "INBOUND"}}) == 1
    finally:
        await cleanup(whatsapp_db, company)
