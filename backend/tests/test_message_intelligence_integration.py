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
async def message_db():
    name = os.environ["TEST_DB_NAME"]
    if name != "proposta_ja_test":
        pytest.fail(f"SAFETY STOP: expected proposta_ja_test, got {name}")
    client = AsyncIOMotorClient(os.environ["TEST_MONGO_URL"], serverSelectionTimeoutMS=5000)
    try:
        await client[name].command("ping")
    except Exception as exc:
        client.close()
        pytest.skip(f"MongoDB unavailable: {exc}")
    yield client[name]
    client.close()


def request_json(payload: dict) -> Request:
    body = json.dumps(payload).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b""}, receive)


def documents(company_id: str, suffix: str):
    now = datetime.now(timezone.utc).isoformat()
    opportunity_id = f"opp-{suffix}"
    client_id = f"client-{suffix}"
    proposal_id = f"proposal-{suffix}"
    action_id = f"action-{suffix}"
    plan_id = f"plan-{suffix}"
    insight_id = f"insight-{suffix}"
    context_id = f"ctx-{suffix}"
    job_id = f"job-{suffix}"
    request_id = f"comm-{suffix}"
    opportunity = {"id": opportunity_id, "company_id": company_id, "client_id": client_id, "proposal_id": proposal_id, "deleted": False}
    client = {"id": client_id, "company_id": company_id, "name": "João", "phone": "5511999999999", "email": "joao@example.com", "deleted": False}
    proposal = {"id": proposal_id, "company_id": company_id, "grand_total": 1250.75, "products": [{"description": "Produto existente"}]}
    context = {
        "context_id": context_id, "company_id": company_id, "opportunity_id": opportunity_id, "snapshot_version": "1.0.0",
        "context": {"opportunity": {"days_since_last_activity": 7}, "proposal": {"proposal_id": proposal_id, "proposal_value": 1250.75}, "products": [{"description": "Produto existente"}], "seller": {"seller_name": "Maria"}, "data_quality": "COMPLETE"},
        "created_at": now,
    }
    insight = {
        "insight_id": insight_id, "company_id": company_id, "opportunity_id": opportunity_id, "context_id": context_id,
        "confidence": 0.85, "insight": {"price_signal": {"status": "UNKNOWN", "type": "UNKNOWN"}},
        "evidence": [{"source": "commercial_context", "field": "followup_state", "value": "OVERDUE"}], "created_at": now,
    }
    action = {"action_id": action_id, "type": "FOLLOW_UP", "channel": "WHATSAPP", "reason": "Ação aprovada", "status": "PENDING_APPROVAL"}
    plan = {
        "action_plan_id": plan_id, "company_id": company_id, "opportunity_id": opportunity_id, "sales_insight_id": insight_id,
        "context_id": context_id, "status": "APPROVED", "actions": [action], "created_at": now,
    }
    job = {
        "execution_job_id": job_id, "company_id": company_id, "action_plan_id": plan_id, "action_id": action_id,
        "opportunity_id": opportunity_id, "channel": "WHATSAPP", "action_type": "FOLLOW_UP", "mode": "SIMULATION",
        "policy": {"allow_external_side_effects": False}, "created_at": now,
    }
    communication = {
        "request_id": request_id, "company_id": company_id, "execution_job_id": job_id, "action_plan_id": plan_id,
        "action_id": action_id, "opportunity_id": opportunity_id, "channel": "WHATSAPP", "action_type": "FOLLOW_UP",
        "recipient": {"client_id": client_id, "name": "João", "phone": "5511999999999", "email": "joao@example.com"},
        "content": {"subject": None, "body": None, "template_id": None, "variables": {}},
        "policy": {"allow_external_side_effects": False}, "mode": "SIMULATION", "status": "PREPARED", "created_at": now,
    }
    return {"opportunities": opportunity, "clients": client, "proposals": proposal, "commercial_contexts": context, "sales_insights": insight, "action_plans": plan, "execution_jobs": job, "communication_requests": communication}


async def insert_chain(database, docs):
    for collection, document in docs.items():
        await database[collection].insert_one(document)


async def cleanup(database, companies):
    for collection in ["message_drafts", "communication_requests", "execution_jobs", "action_plans", "sales_insights", "commercial_contexts", "opportunities", "clients", "proposals", "audit_logs"]:
        await database[collection].delete_many({"company_id": {"$in": companies}})


@pytest.mark.asyncio
async def test_generate_100_edit_approve_and_preserve_every_upstream_document(message_db, monkeypatch):
    import server

    company_id = "msg-a-" + uuid.uuid4().hex
    suffix = uuid.uuid4().hex
    user = {"id": "user-" + suffix, "company_id": company_id}
    docs = documents(company_id, suffix)
    try:
        await insert_chain(message_db, docs)
        monkeypatch.setattr(server, "db", message_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)
        baselines = {collection: await message_db[collection].find_one({"company_id": company_id}, {"_id": 0}) for collection in docs}
        request_id = docs["communication_requests"]["request_id"]
        generated = [await server.generate_message_draft(request_id, user) for _ in range(100)]
        assert len({item["message_draft_id"] for item in generated}) == 1
        assert await message_db.message_drafts.count_documents({"company_id": company_id}) == 1
        draft = generated[0]
        edited_content = {**draft["content"], "closing": "Atenciosamente."}
        edited = await server.edit_message_draft(draft["message_draft_id"], request_json({"content": edited_content, "reason": "Ajuste humano"}), user)
        approved = await server.approve_message_draft(draft["message_draft_id"], user)
        stored = await message_db.message_drafts.find_one({"message_draft_id": draft["message_draft_id"]}, {"_id": 0})
        assert edited["original_content"] == draft["content"]
        assert edited["edited_content"] == edited_content
        assert stored["original_content"] == draft["content"]
        assert stored["edit_history"][0]["edit_reason"] == "Ajuste humano"
        assert approved["status"] == "APPROVED"
        assert stored["status"] == "APPROVED"
        for collection, baseline in baselines.items():
            assert await message_db[collection].find_one({"company_id": company_id}, {"_id": 0}) == baseline
        audits = await message_db.audit_logs.find({"company_id": company_id, "entity_type": "message_draft"}).to_list(None)
        actions = {item["action"] for item in audits}
        assert {"MESSAGE_DRAFT_GENERATION_STARTED", "MESSAGE_DRAFT_GENERATED", "MESSAGE_DRAFT_EDITED", "MESSAGE_DRAFT_APPROVED"} <= actions
        assert not actions & {"MESSAGE_SENT", "MESSAGE_DELIVERED", "CLIENT_CONTACTED"}
    finally:
        await cleanup(message_db, [company_id])


@pytest.mark.asyncio
async def test_reject_and_regenerate_changed_context_preserves_history(message_db, monkeypatch):
    import server

    company_id = "msg-history-" + uuid.uuid4().hex
    suffix = uuid.uuid4().hex
    user = {"id": "user-history", "company_id": company_id}
    docs = documents(company_id, suffix)
    try:
        await insert_chain(message_db, docs)
        monkeypatch.setattr(server, "db", message_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)
        first = await server.generate_message_draft(docs["communication_requests"]["request_id"], user)
        rejected = await server.reject_message_draft(first["message_draft_id"], request_json({"reason": "Não adequado"}), user)
        assert rejected["status"] == "REJECTED"
        await message_db.commercial_contexts.update_one({"company_id": company_id}, {"$set": {"context.opportunity.days_since_last_activity": 12}})
        second = await server.regenerate_message_draft(first["message_draft_id"], user)
        assert second["message_draft_id"] != first["message_draft_id"]
        assert second["source_snapshot_hash"] != first["source_snapshot_hash"]
        assert await message_db.message_drafts.count_documents({"company_id": company_id}) == 2
        old = await message_db.message_drafts.find_one({"message_draft_id": first["message_draft_id"]}, {"_id": 0})
        assert old["status"] == "REJECTED"
        await message_db.commercial_contexts.update_one({"company_id": company_id}, {"$set": {"context.opportunity.days_since_last_activity": 15}})
        third = await server.regenerate_message_draft(second["message_draft_id"], user)
        superseded = await message_db.message_drafts.find_one({"message_draft_id": second["message_draft_id"]}, {"_id": 0})
        assert third["message_draft_id"] != second["message_draft_id"]
        assert superseded["status"] == "SUPERSEDED"
        assert await message_db.message_drafts.count_documents({"company_id": company_id}) == 3
    finally:
        await cleanup(message_db, [company_id])


@pytest.mark.asyncio
async def test_tenant_isolation_list_and_get(message_db, monkeypatch):
    import server

    company_a = "msg-iso-a-" + uuid.uuid4().hex
    company_b = "msg-iso-b-" + uuid.uuid4().hex
    user_a = {"id": "user-a", "company_id": company_a}
    user_b = {"id": "user-b", "company_id": company_b}
    try:
        monkeypatch.setattr(server, "db", message_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)
        docs_a = documents(company_a, uuid.uuid4().hex)
        docs_b = documents(company_b, uuid.uuid4().hex)
        await insert_chain(message_db, docs_a)
        await insert_chain(message_db, docs_b)
        draft_a = await server.generate_message_draft(docs_a["communication_requests"]["request_id"], user_a)
        await server.generate_message_draft(docs_b["communication_requests"]["request_id"], user_b)
        with pytest.raises(Exception):
            await server.get_message_draft(draft_a["message_draft_id"], user_b)
        with pytest.raises(Exception):
            await server.list_message_drafts(company=company_b, opportunity=None, channel=None, action_type=None, status=None, created_at=None, user=user_a)
        listed = await server.list_message_drafts(company=company_a, opportunity=docs_a["opportunities"]["id"], channel="WHATSAPP", action_type="FOLLOW_UP", status="READY_FOR_REVIEW", created_at=None, user=user_a)
        assert [item["message_draft_id"] for item in listed] == [draft_a["message_draft_id"]]
    finally:
        await cleanup(message_db, [company_a, company_b])
