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
async def execution_db():
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


def documents(company_id: str, suffix: str, plan_status: str = "APPROVED") -> tuple[dict, dict, dict, dict]:
    opportunity_id = f"opp-{suffix}"
    action = {
        "action_id": f"action-{suffix}", "type": "FOLLOW_UP", "channel": "WHATSAPP",
        "objective": "Obter uma atualização objetiva da oportunidade.", "reason": "Follow-up overdue.",
        "evidence": [{"source": "sales_intelligence", "source_id": f"insight-{suffix}", "field": "followup_state", "value": "OVERDUE"}],
        "confidence": 0.91, "status": "PENDING_APPROVAL", "sequence": 1, "depends_on": [],
    }
    plan = {
        "action_plan_id": f"plan-{suffix}", "company_id": company_id, "opportunity_id": opportunity_id,
        "sales_insight_id": f"insight-{suffix}", "context_id": f"ctx-{suffix}", "status": plan_status,
        "source_snapshot_hash": f"plan-hash-{suffix}", "actions": [action],
        "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    opportunity = {"id": opportunity_id, "company_id": company_id, "deleted": False, "title": "Execution test"}
    insight = {
        "insight_id": f"insight-{suffix}", "company_id": company_id, "opportunity_id": opportunity_id,
        "context_id": f"ctx-{suffix}", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    context = {
        "context_id": f"ctx-{suffix}", "company_id": company_id, "opportunity_id": opportunity_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return plan, opportunity, insight, context


async def insert_chain(database, chain):
    plan, opportunity, insight, context = chain
    await database.action_plans.insert_one(plan)
    await database.opportunities.insert_one(opportunity)
    await database.sales_insights.insert_one(insight)
    await database.commercial_contexts.insert_one(context)


async def cleanup(database, company_ids):
    for collection in ["execution_jobs", "action_plans", "sales_insights", "commercial_contexts", "opportunities", "proposals", "clients", "audit_logs"]:
        await database[collection].delete_many({"company_id": {"$in": company_ids}})


@pytest.mark.asyncio
async def test_create_idempotent_simulate_and_no_upstream_mutation(execution_db, monkeypatch):
    import server

    company_id = "exec-a-" + uuid.uuid4().hex
    suffix = uuid.uuid4().hex
    user = {"id": "user-" + suffix, "company_id": company_id}
    chain = documents(company_id, suffix)
    try:
        await insert_chain(execution_db, chain)
        await execution_db.proposals.insert_one({"id": "proposal-" + suffix, "company_id": company_id, "status": "aberto"})
        await execution_db.clients.insert_one({"id": "client-" + suffix, "company_id": company_id, "name": "Cliente"})
        monkeypatch.setattr(server, "db", execution_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)
        plan, _, _, _ = chain
        original_opportunity = await execution_db.opportunities.find_one({"company_id": company_id}, {"_id": 0})
        original_proposal = await execution_db.proposals.find_one({"company_id": company_id}, {"_id": 0})
        original_client = await execution_db.clients.find_one({"company_id": company_id}, {"_id": 0})
        payload = {"action_id": plan["actions"][0]["action_id"], "mode": "SIMULATION"}

        first = await server.create_execution_job(plan["action_plan_id"], request_json(payload), user)
        second = await server.create_execution_job(plan["action_plan_id"], request_json(payload), user)
        simulated = await server.simulate_execution(first["execution_job_id"], user)

        assert first["execution_job_id"] == second["execution_job_id"]
        assert await execution_db.execution_jobs.count_documents({"company_id": company_id}) == 1
        assert simulated["status"] == "SIMULATED"
        assert simulated["result"]["external_side_effect"] is False
        assert await execution_db.opportunities.find_one({"company_id": company_id}, {"_id": 0}) == original_opportunity
        assert await execution_db.proposals.find_one({"company_id": company_id}, {"_id": 0}) == original_proposal
        assert await execution_db.clients.find_one({"company_id": company_id}, {"_id": 0}) == original_client
        audits = await execution_db.audit_logs.find({"company_id": company_id, "entity_type": "execution_job"}).to_list(None)
        actions = {item["action"] for item in audits}
        assert {"EXECUTION_JOB_CREATED", "EXECUTION_JOB_SIMULATION_STARTED", "EXECUTION_JOB_SIMULATED"} <= actions
        assert not actions & {"MESSAGE_SENT", "EMAIL_SENT", "WHATSAPP_SENT", "CALL_COMPLETED"}
    finally:
        await cleanup(execution_db, [company_id])


@pytest.mark.asyncio
async def test_draft_live_superseded_and_stale_are_blocked_without_jobs(execution_db, monkeypatch):
    import server

    company_id = "exec-block-" + uuid.uuid4().hex
    user = {"id": "user-block", "company_id": company_id}
    try:
        monkeypatch.setattr(server, "db", execution_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)
        for status in ["DRAFT", "SUPERSEDED"]:
            suffix = uuid.uuid4().hex
            chain = documents(company_id, suffix, status)
            await insert_chain(execution_db, chain)
            plan = chain[0]
            with pytest.raises(Exception):
                await server.create_execution_job(plan["action_plan_id"], request_json({"action_id": plan["actions"][0]["action_id"]}), user)
        live_suffix = uuid.uuid4().hex
        live_chain = documents(company_id, live_suffix)
        await insert_chain(execution_db, live_chain)
        live_plan = live_chain[0]
        with pytest.raises(Exception):
            await server.create_execution_job(live_plan["action_plan_id"], request_json({"action_id": live_plan["actions"][0]["action_id"], "mode": "LIVE"}), user)
        stale_suffix = uuid.uuid4().hex
        stale_chain = documents(company_id, stale_suffix)
        await insert_chain(execution_db, stale_chain)
        await execution_db.sales_insights.update_one({"insight_id": f"insight-{stale_suffix}"}, {"$set": {"insight_id": "new-insight"}})
        stale_plan = stale_chain[0]
        with pytest.raises(Exception):
            await server.create_execution_job(stale_plan["action_plan_id"], request_json({"action_id": stale_plan["actions"][0]["action_id"]}), user)
        assert await execution_db.execution_jobs.count_documents({"company_id": company_id}) == 0
    finally:
        await cleanup(execution_db, [company_id])


@pytest.mark.asyncio
async def test_tenant_filters_get_and_cancel(execution_db, monkeypatch):
    import server

    company_a = "exec-iso-a-" + uuid.uuid4().hex
    company_b = "exec-iso-b-" + uuid.uuid4().hex
    user_a = {"id": "user-a", "company_id": company_a}
    user_b = {"id": "user-b", "company_id": company_b}
    try:
        monkeypatch.setattr(server, "db", execution_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)
        chain_a = documents(company_a, uuid.uuid4().hex)
        chain_b = documents(company_b, uuid.uuid4().hex)
        await insert_chain(execution_db, chain_a)
        await insert_chain(execution_db, chain_b)
        plan_a, plan_b = chain_a[0], chain_b[0]
        job_a = await server.create_execution_job(plan_a["action_plan_id"], request_json({"action_id": plan_a["actions"][0]["action_id"]}), user_a)
        await server.create_execution_job(plan_b["action_plan_id"], request_json({"action_id": plan_b["actions"][0]["action_id"]}), user_b)
        with pytest.raises(Exception):
            await server.get_execution_job(job_a["execution_job_id"], user_b)
        with pytest.raises(Exception):
            await server.cancel_execution(job_a["execution_job_id"], user_b)
        listed_a = await server.list_execution_jobs(status="CREATED", channel="WHATSAPP", action_type="FOLLOW_UP", opportunity_id=plan_a["opportunity_id"], date=None, user=user_a)
        assert [item["execution_job_id"] for item in listed_a] == [job_a["execution_job_id"]]
        cancelled = await server.cancel_execution(job_a["execution_job_id"], user_a)
        assert cancelled["status"] == "CANCELLED"
    finally:
        await cleanup(execution_db, [company_a, company_b])
