"""Phase 3.3 — Sales Intelligence Engine (integration tests).

Uses exclusively TEST_MONGO_URL / TEST_DB_NAME=proposta_ja_test.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from sales_intelligence import SALES_INTELLIGENCE_VERSION

pytestmark = pytest.mark.integration


@pytest.fixture
async def sales_db():
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


def _opportunity(company_id, opp_id, **overrides):
    base = {
        "id": opp_id,
        "company_id": company_id,
        "client_id": None,
        "proposal_id": None,
        "seller_id": None,
        "title": "Oportunidade Teste",
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
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_analyze_get_summary_and_audit_never_touches_opportunity(sales_db, monkeypatch):
    import server
    company_a = "sales-a-" + uuid.uuid4().hex
    opp_id = "opp-" + uuid.uuid4().hex
    user_a = {"id": "sales-user-a-" + uuid.uuid4().hex, "company_id": company_a}
    try:
        opportunity_before = _opportunity(company_a, opp_id)
        await sales_db.opportunities.insert_one(dict(opportunity_before))
        monkeypatch.setattr(server, "db", sales_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        insight = await server.analyze_sales_intelligence(opp_id, user_a)
        fetched = await server.get_sales_intelligence(opp_id, user_a)
        summary = await server.get_sales_intelligence_summary(user_a)

        assert insight["engine_version"] == SALES_INTELLIGENCE_VERSION
        assert insight["priority"] in {"P0_CRITICAL", "P1_HIGH", "P2_MEDIUM", "P3_LOW", "P4_NONE"}
        assert fetched["insight_id"] == insight["insight_id"]
        assert summary["total_insights"] == 1

        opportunity_after = await sales_db.opportunities.find_one({"id": opp_id}, {"_id": 0})
        assert opportunity_after == opportunity_before

        audits = await sales_db.audit_logs.find({"company_id": company_a, "entity_type": "sales_insight"}).to_list(None)
        assert {item["action"] for item in audits} == {"SALES_INTELLIGENCE_STARTED", "SALES_INTELLIGENCE_COMPLETED"}
    finally:
        for collection in ["sales_insights", "commercial_contexts", "opportunities", "audit_logs"]:
            await sales_db[collection].delete_many({"company_id": company_a})


@pytest.mark.asyncio
async def test_idempotent_analysis_does_not_duplicate(sales_db, monkeypatch):
    import server
    company_a = "sales-idem-" + uuid.uuid4().hex
    opp_id = "opp-idem-" + uuid.uuid4().hex
    user_a = {"id": "sales-idem-user-" + uuid.uuid4().hex, "company_id": company_a}
    try:
        await sales_db.opportunities.insert_one(_opportunity(company_a, opp_id))
        monkeypatch.setattr(server, "db", sales_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        first = await server.analyze_sales_intelligence(opp_id, user_a)
        second = await server.analyze_sales_intelligence(opp_id, user_a)
        count = await sales_db.sales_insights.count_documents({"company_id": company_a, "opportunity_id": opp_id})

        assert first["insight_id"] == second["insight_id"]
        assert count == 1
    finally:
        for collection in ["sales_insights", "commercial_contexts", "opportunities", "audit_logs"]:
            await sales_db[collection].delete_many({"company_id": company_a})


@pytest.mark.asyncio
async def test_tenant_isolation_insights_never_cross_companies(sales_db, monkeypatch):
    import server
    company_a = "sales-iso-a-" + uuid.uuid4().hex
    company_b = "sales-iso-b-" + uuid.uuid4().hex
    opp_a = "opp-iso-a-" + uuid.uuid4().hex
    opp_b = "opp-iso-b-" + uuid.uuid4().hex
    user_a = {"id": "sales-iso-user-a-" + uuid.uuid4().hex, "company_id": company_a}
    user_b = {"id": "sales-iso-user-b-" + uuid.uuid4().hex, "company_id": company_b}
    try:
        await sales_db.opportunities.insert_many([_opportunity(company_a, opp_a), _opportunity(company_b, opp_b)])
        monkeypatch.setattr(server, "db", sales_db)
        monkeypatch.setattr(server, "ensure_db_for_current_loop", lambda: None)

        await server.analyze_sales_intelligence(opp_a, user_a)
        await server.analyze_sales_intelligence(opp_b, user_b)

        with pytest.raises(Exception):
            await server.get_sales_intelligence(opp_b, user_a)
        with pytest.raises(Exception):
            await server.get_sales_intelligence(opp_a, user_b)

        summary_a = await server.get_sales_intelligence_summary(user_a)
        summary_b = await server.get_sales_intelligence_summary(user_b)
        assert summary_a["total_insights"] == 1
        assert summary_b["total_insights"] == 1
    finally:
        for collection in ["sales_insights", "commercial_contexts", "opportunities", "audit_logs"]:
            await sales_db[collection].delete_many({"company_id": {"$in": [company_a, company_b]}})
