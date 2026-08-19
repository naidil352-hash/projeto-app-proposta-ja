"""Phase 3.2 — Commercial Context Engine (integration tests).

Uses exclusively TEST_MONGO_URL / TEST_DB_NAME=proposta_ja_test.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from commercial_context import COMMERCIAL_CONTEXT_VERSION

pytestmark = pytest.mark.integration


@pytest.fixture
async def context_db():
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


def iso_days_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _opportunity(company_id, opp_id, client_id=None, proposal_id=None, seller_id=None, timeline=None):
    return {
        "id": opp_id,
        "company_id": company_id,
        "client_id": client_id,
        "proposal_id": proposal_id,
        "seller_id": seller_id,
        "seller_name": "Vendedor",
        "title": "Oportunidade Teste",
        "status": "OPEN",
        "stage": "NEGOCIACAO",
        "temperature": "QUENTE",
        "probability": 70,
        "estimated_value": 3000.0,
        "created_at": iso_days_ago(10),
        "updated_at": iso_days_ago(1),
        "timeline": timeline if timeline is not None else [{"id": "t1", "type": "PROPOSAL_SENT", "created_at": iso_days_ago(7)}],
        "deleted": False,
    }


@pytest.mark.asyncio
async def test_create_refresh_get_summary_and_audit(context_db, monkeypatch):
    import server
    company_a = "ctx-a-" + uuid.uuid4().hex
    opp_id = "opp-" + uuid.uuid4().hex
    client_id = "client-" + uuid.uuid4().hex
    proposal_id = "prop-" + uuid.uuid4().hex
    user_a = {"id": "ctx-user-a-" + uuid.uuid4().hex, "company_id": company_a}
    try:
        await context_db.opportunities.insert_one(_opportunity(company_a, opp_id, client_id, proposal_id))
        await context_db.clients.insert_one({"id": client_id, "company_id": company_a, "name": "ACME", "document": "12345678000199", "deleted": False})
        await context_db.proposals.insert_one({"id": proposal_id, "company_id": company_a, "status": "aberto", "grand_total": 3000.0, "created_at": iso_days_ago(9), "updated_at": iso_days_ago(8), "products": []})
        monkeypatch.setattr(server, "db", context_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        created = await server.refresh_commercial_context(opp_id, user_a)
        fetched = await server.get_commercial_context(opp_id, user_a)
        summary = await server.get_commercial_context_summary(user_a)

        assert created["snapshot_version"] == COMMERCIAL_CONTEXT_VERSION
        assert created["context"]["opportunity"]["opportunity_age_days"] == 10
        assert fetched["context_id"] == created["context_id"]
        assert summary["total_contexts"] == 1

        audits = await context_db.audit_logs.find({"company_id": company_a, "entity_type": "commercial_context"}).to_list(None)
        assert any(item["action"] == "COMMERCIAL_CONTEXT_CREATED" for item in audits)
    finally:
        for collection in ["commercial_contexts", "opportunities", "clients", "proposals", "audit_logs"]:
            await context_db[collection].delete_many({"company_id": company_a})


@pytest.mark.asyncio
async def test_idempotent_refresh_does_not_duplicate(context_db, monkeypatch):
    import server
    company_a = "ctx-idem-" + uuid.uuid4().hex
    opp_id = "opp-idem-" + uuid.uuid4().hex
    user_a = {"id": "ctx-idem-user-" + uuid.uuid4().hex, "company_id": company_a}
    try:
        await context_db.opportunities.insert_one(_opportunity(company_a, opp_id))
        monkeypatch.setattr(server, "db", context_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        first = await server.refresh_commercial_context(opp_id, user_a)
        second = await server.refresh_commercial_context(opp_id, user_a)
        count = await context_db.commercial_contexts.count_documents({"company_id": company_a, "opportunity_id": opp_id})

        assert first["context_id"] == second["context_id"]
        assert count == 1
    finally:
        for collection in ["commercial_contexts", "opportunities", "audit_logs"]:
            await context_db[collection].delete_many({"company_id": company_a})


@pytest.mark.asyncio
async def test_missing_data_returns_partial_context_without_failing(context_db, monkeypatch):
    import server
    company_a = "ctx-missing-" + uuid.uuid4().hex
    opp_id = "opp-missing-" + uuid.uuid4().hex
    user_a = {"id": "ctx-missing-user-" + uuid.uuid4().hex, "company_id": company_a}
    try:
        await context_db.opportunities.insert_one(_opportunity(company_a, opp_id, client_id=None, proposal_id=None, timeline=[]))
        monkeypatch.setattr(server, "db", context_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        context = await server.refresh_commercial_context(opp_id, user_a)

        assert context["context"]["proposal"] is None
        assert context["context"]["client"]["client_status"] == "UNKNOWN"
        assert context["context"]["data_quality"] == "INSUFFICIENT"
    finally:
        for collection in ["commercial_contexts", "opportunities", "audit_logs"]:
            await context_db[collection].delete_many({"company_id": company_a})


@pytest.mark.asyncio
async def test_tenant_isolation_context_never_crosses_companies(context_db, monkeypatch):
    import server
    company_a = "ctx-iso-a-" + uuid.uuid4().hex
    company_b = "ctx-iso-b-" + uuid.uuid4().hex
    opp_a = "opp-iso-a-" + uuid.uuid4().hex
    opp_b = "opp-iso-b-" + uuid.uuid4().hex
    user_a = {"id": "ctx-iso-user-a-" + uuid.uuid4().hex, "company_id": company_a}
    user_b = {"id": "ctx-iso-user-b-" + uuid.uuid4().hex, "company_id": company_b}
    try:
        await context_db.opportunities.insert_many([_opportunity(company_a, opp_a), _opportunity(company_b, opp_b)])
        monkeypatch.setattr(server, "db", context_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        await server.refresh_commercial_context(opp_a, user_a)
        await server.refresh_commercial_context(opp_b, user_b)

        with pytest.raises(Exception):
            await server.get_commercial_context(opp_b, user_a)
        with pytest.raises(Exception):
            await server.get_commercial_context(opp_a, user_b)

        summary_a = await server.get_commercial_context_summary(user_a)
        summary_b = await server.get_commercial_context_summary(user_b)
        assert summary_a["total_contexts"] == 1
        assert summary_b["total_contexts"] == 1
    finally:
        for collection in ["commercial_contexts", "opportunities", "audit_logs"]:
            await context_db[collection].delete_many({"company_id": {"$in": [company_a, company_b]}})
