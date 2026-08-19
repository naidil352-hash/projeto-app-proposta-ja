"""
Integration tests for Opportunity CRUD with MongoDB.
Uses proposta_ja_test database only.
"""

import pytest
import os
import uuid
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def mongo_test_db():
    """Create and connect to test MongoDB."""
    test_url = os.environ.get("TEST_MONGO_URL", "mongodb://127.0.0.1:27017")
    test_db_name = os.environ.get("TEST_DB_NAME", "proposta_ja_test")

    # Safety check
    if test_db_name != "proposta_ja_test":
        pytest.skip(f"SAFETY: TEST_DB_NAME must be proposta_ja_test, got {test_db_name}")

    try:
        client = AsyncIOMotorClient(test_url, serverSelectionTimeoutMS=5000)
        await client.admin.command("ping")
    except Exception as e:
        pytest.skip(f"MongoDB not available: {e}")

    db = client[test_db_name]

    # Clean before test
    for coll in ["opportunities", "users", "companies"]:
        await db[coll].delete_many({})

    yield db

    # Clean after test
    for coll in ["opportunities", "users", "companies"]:
        await db[coll].delete_many({})

    client.close()


@pytest.mark.asyncio
async def test_opportunity_mongodb_connection(mongo_test_db):
    """Verify MongoDB connection to test database."""
    assert mongo_test_db is not None
    # Create a simple test collection entry
    result = await mongo_test_db.opportunities.insert_one({
        "_id": "test-connection-" + str(uuid.uuid4()),
        "title": "Connection Test",
    })
    assert result.inserted_id is not None


@pytest.mark.asyncio
async def test_opportunity_multi_tenant_isolation(mongo_test_db):
    """Verify opportunities from different tenants are isolated."""
    tenant_a_id = str(uuid.uuid4())
    tenant_b_id = str(uuid.uuid4())

    # Create opportunities for each tenant
    opp_a = {
        "id": str(uuid.uuid4()),
        "company_id": tenant_a_id,
        "title": "Tenant A Opp",
        "stage": "prospeccao",
        "temperature": "quente",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "deleted": False,
    }

    opp_b = {
        "id": str(uuid.uuid4()),
        "company_id": tenant_b_id,
        "title": "Tenant B Opp",
        "stage": "negociacao",
        "temperature": "morna",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "deleted": False,
    }

    await mongo_test_db.opportunities.insert_many([opp_a, opp_b])

    # Verify isolation
    tenant_a_opps = await mongo_test_db.opportunities.find(
        {"company_id": tenant_a_id, "deleted": {"$ne": True}}
    ).to_list(None)

    tenant_b_opps = await mongo_test_db.opportunities.find(
        {"company_id": tenant_b_id, "deleted": {"$ne": True}}
    ).to_list(None)

    assert len(tenant_a_opps) == 1
    assert len(tenant_b_opps) == 1
    assert tenant_a_opps[0]["id"] == opp_a["id"]
    assert tenant_b_opps[0]["id"] == opp_b["id"]


@pytest.mark.asyncio
async def test_opportunity_stage_values(mongo_test_db):
    """Verify valid stage values can be stored."""
    tenant_id = str(uuid.uuid4())
    valid_stages = ["prospeccao", "negociacao", "aprovacao", "fechada"]

    for stage in valid_stages:
        opp = {
            "id": str(uuid.uuid4()),
            "company_id": tenant_id,
            "title": f"Opp {stage}",
            "stage": stage,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "deleted": False,
        }
        await mongo_test_db.opportunities.insert_one(opp)

    count = await mongo_test_db.opportunities.count_documents({"company_id": tenant_id})
    assert count == len(valid_stages)


@pytest.mark.asyncio
async def test_opportunity_temperature_values(mongo_test_db):
    """Verify valid temperature values can be stored."""
    tenant_id = str(uuid.uuid4())
    valid_temps = ["fria", "morna", "quente"]

    for temp in valid_temps:
        opp = {
            "id": str(uuid.uuid4()),
            "company_id": tenant_id,
            "title": f"Opp {temp}",
            "temperature": temp,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "deleted": False,
        }
        await mongo_test_db.opportunities.insert_one(opp)

    count = await mongo_test_db.opportunities.count_documents({"company_id": tenant_id})
    assert count == len(valid_temps)


@pytest.mark.asyncio
async def test_opportunity_soft_delete(mongo_test_db):
    """Verify soft delete behavior."""
    tenant_id = str(uuid.uuid4())
    opp_id = str(uuid.uuid4())

    opp = {
        "id": opp_id,
        "company_id": tenant_id,
        "title": "To Delete",
        "stage": "prospeccao",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "deleted": False,
    }

    await mongo_test_db.opportunities.insert_one(opp)

    # Verify it exists in active list
    found = await mongo_test_db.opportunities.find_one({
        "id": opp_id,
        "deleted": {"$ne": True}
    })
    assert found is not None

    # Soft delete
    await mongo_test_db.opportunities.update_one(
        {"id": opp_id},
        {"$set": {"deleted": True}}
    )

    # Verify it's hidden from active list
    active = await mongo_test_db.opportunities.find_one({
        "id": opp_id,
        "deleted": {"$ne": True}
    })
    assert active is None

    # But still exists in DB
    deleted = await mongo_test_db.opportunities.find_one({"id": opp_id})
    assert deleted is not None
    assert deleted["deleted"] is True
