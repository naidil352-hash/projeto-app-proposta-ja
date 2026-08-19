from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def communication_db():
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


def documents(company_id: str, suffix: str, channel: str = "WHATSAPP", mode: str = "SIMULATION", phone: str | None = "5511999999999"):
    opportunity_id = f"opp-{suffix}"
    action_id = f"action-{suffix}"
    plan_id = f"plan-{suffix}"
    job_id = f"job-{suffix}"
    action = {"action_id": action_id, "type": "FOLLOW_UP", "channel": channel, "status": "PENDING_APPROVAL"}
    plan = {
        "action_plan_id": plan_id, "company_id": company_id, "opportunity_id": opportunity_id,
        "status": "APPROVED", "actions": [action], "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    opportunity = {"id": opportunity_id, "company_id": company_id, "client_id": f"client-{suffix}", "deleted": False}
    client = {"id": f"client-{suffix}", "company_id": company_id, "name": "Cliente", "document": f"TEST-{suffix}", "phone": phone, "email": "client@example.com", "deleted": False}
    job = {
        "execution_job_id": job_id, "company_id": company_id, "action_plan_id": plan_id,
        "action_id": action_id, "opportunity_id": opportunity_id, "status": "CREATED", "mode": mode,
        "channel": channel, "action_type": "FOLLOW_UP",
        "payload": {"context": {"opportunity_id": opportunity_id}},
        "policy": {"requires_approval": True, "allow_external_side_effects": False, "max_attempts": 1},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return job, plan, opportunity, client


async def insert_chain(database, chain):
    job, plan, opportunity, client = chain
    await database.execution_jobs.insert_one(job)
    await database.action_plans.insert_one(plan)
    await database.opportunities.insert_one(opportunity)
    await database.clients.insert_one(client)


async def cleanup(database, companies):
    for collection in ["communication_requests", "execution_jobs", "action_plans", "opportunities", "clients", "audit_logs"]:
        await database[collection].delete_many({"company_id": {"$in": companies}})


@pytest.mark.asyncio
async def test_prepare_one_hundred_times_simulate_and_preserve_upstream(communication_db, monkeypatch):
    import server

    company_id = "comm-a-" + uuid.uuid4().hex
    suffix = uuid.uuid4().hex
    user = {"id": "user-" + suffix, "company_id": company_id}
    chain = documents(company_id, suffix)
    try:
        await insert_chain(communication_db, chain)
        monkeypatch.setattr(server, "db", communication_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)
        job, plan, opportunity, client = chain
        baselines = {
            "execution_jobs": await communication_db.execution_jobs.find_one({"company_id": company_id}, {"_id": 0}),
            "action_plans": await communication_db.action_plans.find_one({"company_id": company_id}, {"_id": 0}),
            "opportunities": await communication_db.opportunities.find_one({"company_id": company_id}, {"_id": 0}),
            "clients": await communication_db.clients.find_one({"company_id": company_id}, {"_id": 0}),
        }
        prepared = [await server.prepare_communication_request(job["execution_job_id"], user) for _ in range(100)]
        assert len({item["request_id"] for item in prepared}) == 1
        assert await communication_db.communication_requests.count_documents({"company_id": company_id}) == 1
        simulated = await server.simulate_communication(prepared[0]["request_id"], user)
        assert simulated["status"] == "SIMULATED"
        assert simulated["result"]["external_side_effect"] is False
        assert simulated["result"]["sent"] is False
        assert simulated["result"]["delivered"] is False
        for collection, baseline in baselines.items():
            assert await communication_db[collection].find_one({"company_id": company_id}, {"_id": 0}) == baseline
        audits = await communication_db.audit_logs.find({"company_id": company_id, "entity_type": "communication_request"}).to_list(None)
        actions = {item["action"] for item in audits}
        assert {"COMMUNICATION_REQUEST_RECEIVED", "COMMUNICATION_REQUEST_VALIDATED", "COMMUNICATION_REQUEST_PREPARED", "COMMUNICATION_REQUEST_SIMULATED"} <= actions
        assert not actions & {"WHATSAPP_SENT", "EMAIL_SENT", "SMS_SENT", "CALL_COMPLETED", "MESSAGE_DELIVERED"}
    finally:
        await cleanup(communication_db, [company_id])


@pytest.mark.asyncio
async def test_missing_contact_unknown_and_live_persist_safe_states(communication_db, monkeypatch):
    import server

    company_id = "comm-block-" + uuid.uuid4().hex
    user = {"id": "user-block", "company_id": company_id}
    try:
        monkeypatch.setattr(server, "db", communication_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)
        missing = documents(company_id, uuid.uuid4().hex, phone=None)
        unknown = documents(company_id, uuid.uuid4().hex, channel="UNKNOWN")
        live = documents(company_id, uuid.uuid4().hex, mode="LIVE")
        for chain in [missing, unknown, live]:
            await insert_chain(communication_db, chain)
        missing_request = await server.prepare_communication_request(missing[0]["execution_job_id"], user)
        unknown_request = await server.prepare_communication_request(unknown[0]["execution_job_id"], user)
        live_request = await server.prepare_communication_request(live[0]["execution_job_id"], user)
        assert missing_request["status"] == "BLOCKED"
        assert missing_request["recipient"]["phone"] is None
        assert unknown_request["status"] == "BLOCKED"
        assert live_request["status"] == "REJECTED"
        assert live_request["reason"] == "LIVE_MODE_NOT_AVAILABLE"
        assert all(item.get("result") == {} for item in [missing_request, unknown_request, live_request])
    finally:
        await cleanup(communication_db, [company_id])


@pytest.mark.asyncio
async def test_tenant_isolation_filters_and_cancel(communication_db, monkeypatch):
    import server

    company_a = "comm-iso-a-" + uuid.uuid4().hex
    company_b = "comm-iso-b-" + uuid.uuid4().hex
    user_a = {"id": "user-a", "company_id": company_a}
    user_b = {"id": "user-b", "company_id": company_b}
    try:
        monkeypatch.setattr(server, "db", communication_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)
        chain_a = documents(company_a, uuid.uuid4().hex)
        chain_b = documents(company_b, uuid.uuid4().hex)
        await insert_chain(communication_db, chain_a)
        await insert_chain(communication_db, chain_b)
        request_a = await server.prepare_communication_request(chain_a[0]["execution_job_id"], user_a)
        await server.prepare_communication_request(chain_b[0]["execution_job_id"], user_b)
        with pytest.raises(Exception):
            await server.get_communication_request(request_a["request_id"], user_b)
        with pytest.raises(Exception):
            await server.cancel_communication(request_a["request_id"], user_b)
        listed = await server.list_communication_requests(
            channel="WHATSAPP", action_type="FOLLOW_UP", status="PREPARED",
            opportunity_id=chain_a[0]["opportunity_id"], execution_job_id=chain_a[0]["execution_job_id"],
            created_at=None, user=user_a,
        )
        assert [item["request_id"] for item in listed] == [request_a["request_id"]]
        cancelled = await server.cancel_communication(request_a["request_id"], user_a)
        assert cancelled["status"] == "REJECTED"
        assert cancelled["reason"] == "CANCELLED_BY_USER"
    finally:
        await cleanup(communication_db, [company_a, company_b])
