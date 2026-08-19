from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.requests import Request

pytestmark = pytest.mark.integration


@pytest.fixture
async def action_db():
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


def iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def opportunity(company_id: str, opportunity_id: str) -> dict:
    return {
        "id": opportunity_id,
        "company_id": company_id,
        "client_id": None,
        "proposal_id": None,
        "title": "Plano teste",
        "status": "OPEN",
        "stage": "NEGOCIACAO",
        "temperature": "QUENTE",
        "probability": 70,
        "estimated_value": 3000.0,
        "created_at": iso_days_ago(15),
        "updated_at": iso_days_ago(1),
        "timeline": [{"id": "t1", "type": "PROPOSAL_SENT", "created_at": iso_days_ago(8)}],
        "deleted": False,
    }


def request_json(payload: dict) -> Request:
    body = str(payload).replace("'", '"').encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b""}, receive)


@pytest.mark.asyncio
async def test_generate_idempotent_and_approve_does_not_mutate_opportunity(action_db, monkeypatch):
    import server

    company_id = "action-a-" + uuid.uuid4().hex
    opportunity_id = "opp-action-" + uuid.uuid4().hex
    user = {"id": "user-" + uuid.uuid4().hex, "company_id": company_id}
    original = opportunity(company_id, opportunity_id)
    try:
        await action_db.opportunities.insert_one(dict(original))
        monkeypatch.setattr(server, "db", action_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        await server.analyze_sales_intelligence(opportunity_id, user)
        first = await server.generate_action_plan(opportunity_id, user)
        second = await server.generate_action_plan(opportunity_id, user)
        approved = await server.approve_action_plan(first["action_plan_id"], user)

        assert first["action_plan_id"] == second["action_plan_id"]
        assert approved["status"] == "APPROVED"
        assert await action_db.action_plans.count_documents({"company_id": company_id}) == 1
        assert await action_db.opportunities.find_one({"id": opportunity_id}, {"_id": 0}) == original
        audits = await action_db.audit_logs.find({"company_id": company_id, "entity_type": "action_plan"}).to_list(None)
        assert {item["action"] for item in audits} >= {"ACTION_PLAN_GENERATION_STARTED", "ACTION_PLAN_GENERATED", "ACTION_PLAN_APPROVED"}
        assert not any(item["action"] == "ACTION_EXECUTED" for item in audits)
    finally:
        for collection in ["action_plans", "sales_insights", "commercial_contexts", "opportunities", "audit_logs"]:
            await action_db[collection].delete_many({"company_id": company_id})


@pytest.mark.asyncio
async def test_reject_records_reason_user_and_timestamp_without_external_action(action_db, monkeypatch):
    import server

    company_id = "action-reject-" + uuid.uuid4().hex
    opportunity_id = "opp-reject-" + uuid.uuid4().hex
    user = {"id": "user-reject-" + uuid.uuid4().hex, "company_id": company_id}
    try:
        await action_db.opportunities.insert_one(opportunity(company_id, opportunity_id))
        monkeypatch.setattr(server, "db", action_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)
        await server.analyze_sales_intelligence(opportunity_id, user)
        plan = await server.generate_action_plan(opportunity_id, user)
        rejected = await server.reject_action_plan(plan["action_plan_id"], request_json({"reason": "Dados precisam de revisão"}), user)
        stored = await action_db.action_plans.find_one({"action_plan_id": plan["action_plan_id"]}, {"_id": 0})
        assert rejected["status"] == "REJECTED"
        assert stored["rejection"]["reason"] == "Dados precisam de revisão"
        assert stored["rejection"]["user_id"] == user["id"]
        assert stored["rejection"]["timestamp"]
    finally:
        for collection in ["action_plans", "sales_insights", "commercial_contexts", "opportunities", "audit_logs"]:
            await action_db[collection].delete_many({"company_id": company_id})


@pytest.mark.asyncio
async def test_tenant_isolation_and_consistency_guard(action_db, monkeypatch):
    import server

    company_a = "action-iso-a-" + uuid.uuid4().hex
    company_b = "action-iso-b-" + uuid.uuid4().hex
    opp_a = "opp-iso-a-" + uuid.uuid4().hex
    opp_b = "opp-iso-b-" + uuid.uuid4().hex
    user_a = {"id": "user-a-" + uuid.uuid4().hex, "company_id": company_a}
    user_b = {"id": "user-b-" + uuid.uuid4().hex, "company_id": company_b}
    try:
        await action_db.opportunities.insert_many([opportunity(company_a, opp_a), opportunity(company_b, opp_b)])
        monkeypatch.setattr(server, "db", action_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)
        await server.analyze_sales_intelligence(opp_a, user_a)
        await server.analyze_sales_intelligence(opp_b, user_b)
        await server.generate_action_plan(opp_a, user_a)
        await server.generate_action_plan(opp_b, user_b)

        with pytest.raises(Exception):
            await server.get_action_plan(opp_b, user_a)
        with pytest.raises(Exception):
            await server.get_action_plan(opp_a, user_b)
        assert (await server.get_action_plan_summary(user_a))["total"] == 1
        assert (await server.get_action_plan_summary(user_b))["total"] == 1
    finally:
        for collection in ["action_plans", "sales_insights", "commercial_contexts", "opportunities", "audit_logs"]:
            await action_db[collection].delete_many({"company_id": {"$in": [company_a, company_b]}})
