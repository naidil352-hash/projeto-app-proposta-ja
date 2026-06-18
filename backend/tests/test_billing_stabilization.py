import pytest
import uuid
import os
import asyncio
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env", override=True)

# Imports from server
from server import (
    _activate_subscription,
    get_user_plan_state,
    db
)

@pytest.fixture(scope="function")
def setup_data():
    company_id = str(uuid.uuid4())
    owner_id = str(uuid.uuid4())
    admin_id = str(uuid.uuid4())
    legacy_id = str(uuid.uuid4())
    
    owner_email = f"owner_{uuid.uuid4().hex[:6]}@test.com"
    admin_email = f"admin_{uuid.uuid4().hex[:6]}@test.com"
    legacy_email = f"legacy_{uuid.uuid4().hex[:6]}@test.com"
    
    users = [
        {"id": owner_id, "email": owner_email, "name": "Owner User", "company_id": company_id, "role": "owner", "active": True, "created_at": "2026-06-14T22:00:00Z"},
        {"id": admin_id, "email": admin_email, "name": "Admin User", "company_id": company_id, "role": "admin", "active": True, "created_at": "2026-06-14T22:00:00Z"},
        {"id": legacy_id, "email": legacy_email, "name": "Legacy User", "active": True}
    ]
    
    companies = [
        {"id": company_id, "user_id": owner_id, "company_name": "Stabilization Test Company"}
    ]
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.users.insert_many(users))
    loop.run_until_complete(db.companies.insert_many(companies))
    
    yield {
        "company_id": company_id,
        "owner_id": owner_id,
        "admin_id": admin_id,
        "legacy_id": legacy_id
    }
    
    # Cleanup
    loop.run_until_complete(db.users.delete_many({"id": {"$in": [owner_id, admin_id, legacy_id]}}))
    loop.run_until_complete(db.companies.delete_many({"id": company_id}))
    loop.run_until_complete(db.subscriptions.delete_many({"user_id": {"$in": [owner_id, admin_id, legacy_id]}}))
    loop.run_until_complete(db.subscriptions.delete_many({"company_id": company_id}))
    loop.run_until_complete(db.payment_transactions.delete_many({"user_id": {"$in": [owner_id, admin_id, legacy_id]}}))


def test_scenario_1_owner_pays_company_pro(setup_data):
    owner_id = setup_data["owner_id"]
    company_id = setup_data["company_id"]
    loop = asyncio.get_event_loop()
    
    # Owner pays
    loop.run_until_complete(_activate_subscription(owner_id, "pro_monthly", session_id="sess_owner_1"))
    
    # Verify subscription record
    sub = loop.run_until_complete(db.subscriptions.find_one({"company_id": company_id}))
    assert sub is not None
    assert sub["user_id"] == owner_id
    assert sub["company_id"] == company_id
    
    # Verify owner gets PRO plan state
    state = loop.run_until_complete(get_user_plan_state(owner_id))
    assert state["plan"] == "pro"
    assert state["is_pro"] is True


def test_scenario_2_admin_pays_company_pro(setup_data):
    owner_id = setup_data["owner_id"]
    admin_id = setup_data["admin_id"]
    company_id = setup_data["company_id"]
    loop = asyncio.get_event_loop()
    
    # Admin pays
    loop.run_until_complete(_activate_subscription(admin_id, "pro_monthly", session_id="sess_admin_1"))
    
    # Verify subscription record is linked to Owner and Company, not the admin
    sub = loop.run_until_complete(db.subscriptions.find_one({"company_id": company_id}))
    assert sub is not None
    assert sub["user_id"] == owner_id
    assert sub["company_id"] == company_id
    
    sub_admin = loop.run_until_complete(db.subscriptions.find_one({"user_id": admin_id}))
    assert sub_admin is None
    
    # Verify admin gets PRO plan state (inherited from company owner)
    state = loop.run_until_complete(get_user_plan_state(admin_id))
    assert state["plan"] == "pro"
    assert state["is_pro"] is True


def test_scenario_3_owner_queries_plan_after_admin_pays(setup_data):
    owner_id = setup_data["owner_id"]
    admin_id = setup_data["admin_id"]
    loop = asyncio.get_event_loop()
    
    # Admin pays
    loop.run_until_complete(_activate_subscription(admin_id, "pro_monthly", session_id="sess_admin_2"))
    
    # Owner queries plan state
    state = loop.run_until_complete(get_user_plan_state(owner_id))
    assert state["plan"] == "pro"
    assert state["is_pro"] is True


def test_scenario_4_admin_queries_plan_after_owner_pays(setup_data):
    owner_id = setup_data["owner_id"]
    admin_id = setup_data["admin_id"]
    loop = asyncio.get_event_loop()
    
    # Owner pays
    loop.run_until_complete(_activate_subscription(owner_id, "pro_monthly", session_id="sess_owner_2"))
    
    # Admin queries plan state
    state = loop.run_until_complete(get_user_plan_state(admin_id))
    assert state["plan"] == "pro"
    assert state["is_pro"] is True


def test_scenario_5_and_6_idempotency_webhook_and_polling(setup_data):
    admin_id = setup_data["admin_id"]
    company_id = setup_data["company_id"]
    owner_id = setup_data["owner_id"]
    session_id = f"sess_idemp_{uuid.uuid4().hex[:6]}"
    loop = asyncio.get_event_loop()
    
    # Register mock payment transaction
    loop.run_until_complete(db.payment_transactions.insert_one({
        "session_id": session_id,
        "user_id": admin_id,
        "plan": "pro_monthly",
        "payment_status": "initiated",
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat()
    }))
    
    # Define a simulated Webhook block execution
    async def simulate_webhook():
        tx = await db.payment_transactions.find_one({"session_id": session_id})
        if tx and tx.get("payment_status") != "paid":
            res = await db.payment_transactions.update_one(
                {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                {"$set": {"payment_status": "paid", "status": "complete"}},
            )
            if res.modified_count > 0:
                await _activate_subscription(tx["user_id"], tx["plan"], session_id=session_id)
                
    # Define a simulated Polling block execution
    async def simulate_polling():
        tx = await db.payment_transactions.find_one({"session_id": session_id})
        if tx and tx.get("payment_status") != "paid":
            res = await db.payment_transactions.update_one(
                {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                {"$set": {
                    "payment_status": "paid",
                    "status": "complete",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
            if res.modified_count > 0:
                await _activate_subscription(tx["user_id"], tx["plan"], session_id=session_id)

    # 1. Simulating Scenario 5: Webhook first, Polling after
    loop.run_until_complete(simulate_webhook())
    sub_1 = loop.run_until_complete(db.subscriptions.find_one({"company_id": company_id}))
    assert sub_1 is not None
    pro_until_1 = datetime.fromisoformat(sub_1["pro_until"])
    
    # Polling runs second
    loop.run_until_complete(simulate_polling())
    sub_2 = loop.run_until_complete(db.subscriptions.find_one({"company_id": company_id}))
    pro_until_2 = datetime.fromisoformat(sub_2["pro_until"])
    
    # Check that pro_until was NOT extended twice (it must be identical)
    assert pro_until_1 == pro_until_2
    
    # Clean up subscription and transaction for next test
    loop.run_until_complete(db.subscriptions.delete_many({"company_id": company_id}))
    loop.run_until_complete(db.payment_transactions.update_one({"session_id": session_id}, {"$set": {"payment_status": "initiated", "status": "open"}}))
    
    # 2. Simulating Scenario 6: Polling first, Webhook after
    loop.run_until_complete(simulate_polling())
    sub_3 = loop.run_until_complete(db.subscriptions.find_one({"company_id": company_id}))
    assert sub_3 is not None
    pro_until_3 = datetime.fromisoformat(sub_3["pro_until"])
    
    # Webhook runs second
    loop.run_until_complete(simulate_webhook())
    sub_4 = loop.run_until_complete(db.subscriptions.find_one({"company_id": company_id}))
    pro_until_4 = datetime.fromisoformat(sub_4["pro_until"])
    
    # Must be identical
    assert pro_until_3 == pro_until_4


def test_scenario_7_legacy_user_fallback(setup_data):
    legacy_id = setup_data["legacy_id"]
    loop = asyncio.get_event_loop()
    
    # Legacy user pays (no company_id)
    loop.run_until_complete(_activate_subscription(legacy_id, "pro_monthly", session_id="sess_legacy_1"))
    
    # Verify subscription record is linked to Legacy User directly
    sub = loop.run_until_complete(db.subscriptions.find_one({"user_id": legacy_id}))
    assert sub is not None
    assert sub.get("company_id") is None
    
    # Verify legacy user gets PRO plan state
    state = loop.run_until_complete(get_user_plan_state(legacy_id))
    assert state["plan"] == "pro"
    assert state["is_pro"] is True
