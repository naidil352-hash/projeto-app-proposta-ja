import pytest
import asyncio
import os
import uuid
import requests
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from server import create_access_token, get_company_trial_status

mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
client_db = AsyncIOMotorClient(mongo_url)
db = client_db[db_name]

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api"

@pytest.fixture(scope="module")
def setup_sprint5c_data():
    loop = asyncio.get_event_loop()
    company_id_active = f"company-5c-active-{uuid.uuid4().hex[:6]}"
    company_id_expired = f"company-5c-exp-{uuid.uuid4().hex[:6]}"
    company_id_founder = f"company-5c-fnd-{uuid.uuid4().hex[:6]}"

    owner_active_id = f"owner-active-{uuid.uuid4().hex[:6]}"
    owner_expired_id = f"owner-expired-{uuid.uuid4().hex[:6]}"
    owner_founder_id = f"owner-founder-{uuid.uuid4().hex[:6]}"

    now = datetime.now(timezone.utc)
    
    # Active trial company (started 10 days ago, expires in 50 days)
    started_active = (now - timedelta(days=10)).isoformat()
    expires_active = (now + timedelta(days=50)).isoformat()
    
    # Expired trial company (started 70 days ago, expired 10 days ago)
    started_expired = (now - timedelta(days=70)).isoformat()
    expires_expired = (now - timedelta(days=10)).isoformat()

    users = [
        {
            "id": owner_active_id,
            "email": f"{owner_active_id}@test.com",
            "name": "Owner Active",
            "company_id": company_id_active,
            "role": "owner",
            "active": True,
            "deleted": False,
            "phone": "+5511999991111",
            "whatsapp": "+5511999991111"
        },
        {
            "id": owner_expired_id,
            "email": f"{owner_expired_id}@test.com",
            "name": "Owner Expired",
            "company_id": company_id_expired,
            "role": "owner",
            "active": True,
            "deleted": False,
            "phone": "+5511999992222",
            "whatsapp": "+5511999992222"
        },
        {
            "id": owner_founder_id,
            "email": f"{owner_founder_id}@test.com",
            "name": "Owner Founder",
            "company_id": company_id_founder,
            "role": "owner",
            "active": True,
            "deleted": False,
            "founder": True,
            "lifetime": True,
            "plan": "pro"
        }
    ]

    companies = [
        {
            "id": company_id_active,
            "user_id": owner_active_id,
            "company_name": "Active Corp",
            "trial_days": 60,
            "trial_started_at": started_active,
            "trial_expires_at": expires_active
        },
        {
            "id": company_id_expired,
            "user_id": owner_expired_id,
            "company_name": "Expired Corp",
            "trial_days": 60,
            "trial_started_at": started_expired,
            "trial_expires_at": expires_expired
        },
        {
            "id": company_id_founder,
            "user_id": owner_founder_id,
            "company_name": "Founder Corp"
            # trial_expires_at is null/not set
        }
    ]

    loop.run_until_complete(db.users.insert_many(users))
    loop.run_until_complete(db.companies.insert_many(companies))

    tokens = {
        "active": create_access_token(owner_active_id, f"{owner_active_id}@test.com"),
        "expired": create_access_token(owner_expired_id, f"{owner_expired_id}@test.com"),
        "founder": create_access_token(owner_founder_id, f"{owner_founder_id}@test.com"),
    }

    yield {
        "company_id_active": company_id_active,
        "company_id_expired": company_id_expired,
        "company_id_founder": company_id_founder,
        "tokens": tokens,
        "owner_active_id": owner_active_id,
        "owner_expired_id": owner_expired_id,
        "owner_founder_id": owner_founder_id
    }

    # Cleanup
    loop.run_until_complete(db.users.delete_many({"company_id": {"$in": [company_id_active, company_id_expired, company_id_founder]}}))
    loop.run_until_complete(db.companies.delete_many({"id": {"$in": [company_id_active, company_id_expired, company_id_founder]}}))
    loop.run_until_complete(db.proposals.delete_many({"company_id": {"$in": [company_id_active, company_id_expired, company_id_founder]}}))
    loop.run_until_complete(db.products.delete_many({"company_id": {"$in": [company_id_active, company_id_expired, company_id_founder]}}))
    loop.run_until_complete(db.clients.delete_many({"company_id": {"$in": [company_id_active, company_id_expired, company_id_founder]}}))


def test_auth_me_trial_fields(setup_sprint5c_data):
    data = setup_sprint5c_data
    
    # Active trial user
    headers = {"Authorization": f"Bearer {data['tokens']['active']}"}
    res = requests.get(f"{API}/auth/me", headers=headers)
    assert res.status_code == 200
    me = res.json()
    assert me["trial_is_expired"] is False
    assert me["trial_days_remaining"] is not None
    assert me["trial_days_remaining"] > 0
    assert "trial_stats" in me
    
    # Expired trial user
    headers_exp = {"Authorization": f"Bearer {data['tokens']['expired']}"}
    res_exp = requests.get(f"{API}/auth/me", headers=headers_exp)
    assert res_exp.status_code == 200
    me_exp = res_exp.json()
    assert me_exp["trial_is_expired"] is True
    assert me_exp["trial_days_remaining"] == 0
    
    # Founder user
    headers_fnd = {"Authorization": f"Bearer {data['tokens']['founder']}"}
    res_fnd = requests.get(f"{API}/auth/me", headers=headers_fnd)
    assert res_fnd.status_code == 200
    me_fnd = res_fnd.json()
    assert me_fnd["trial_is_expired"] is False
    assert me_fnd["trial_days_remaining"] is None
    assert me_fnd["plan"] == "pro"


def test_trial_expiration_blocks(setup_sprint5c_data):
    data = setup_sprint5c_data
    headers_exp = {"Authorization": f"Bearer {data['tokens']['expired']}"}
    headers_active = {"Authorization": f"Bearer {data['tokens']['active']}"}

    proposal_payload = {
        "client_name": "Test Client 5C",
        "client_document": "12.345.678/0001-99",
        "client_phone": "(11) 99999-1111",
        "products": [
            {"name": "Consultoria", "quantity": 1, "unit_price": 1000.0}
        ],
        "shipping_deadline": "Immediate",
        "notes": "Test notes",
        "discount": 0.0,
        "validity_days": 15
    }

    # 1. Block creating proposal for expired company
    res = requests.post(f"{API}/proposals", json=proposal_payload, headers=headers_exp)
    assert res.status_code == 403
    assert "Seu período de avaliação terminou" in res.json()["detail"]
    assert "0 propostas" in res.json()["detail"]

    # 2. Allow creating proposal for active company
    res_active = requests.post(f"{API}/proposals", json=proposal_payload, headers=headers_active)
    assert res_active.status_code == 200
    proposal = res_active.json()
    assert proposal["public_code"] != ""
    assert len(proposal["public_code"]) == 6

    # 3. Block duplicating proposal for expired company
    pid = proposal["id"]
    res_dup = requests.post(f"{API}/proposals/{pid}/duplicate", headers=headers_exp)
    assert res_dup.status_code == 403

    # 4. Block creating product for expired company
    product_payload = {
        "code": "PROD-5C",
        "name": "Product 5C",
        "description": "Desc",
        "price": 150.0,
        "unit": "UN"
    }
    res_prod = requests.post(f"{API}/products", json=product_payload, headers=headers_exp)
    assert res_prod.status_code == 403


def test_public_code_and_view_tracking(setup_sprint5c_data):
    data = setup_sprint5c_data
    headers_active = {"Authorization": f"Bearer {data['tokens']['active']}"}

    proposal_payload = {
        "client_name": "Public Code Client",
        "client_document": "12.345.678/0001-00",
        "client_phone": "(11) 99999-2222",
        "products": [
            {"name": "Consultoria", "quantity": 1, "unit_price": 2000.0}
        ],
        "shipping_deadline": "Immediate",
        "notes": "Test",
        "discount": 0.0,
        "validity_days": 15
    }

    # Create proposal to get a public code
    res = requests.post(f"{API}/proposals", json=proposal_payload, headers=headers_active)
    assert res.status_code == 200
    prop = res.json()
    pid = prop["id"]
    code = prop["public_code"]
    
    assert code != ""
    assert len(code) == 6
    assert code.isupper()

    # Get proposal via public endpoint (view tracking check)
    headers_view = {"User-Agent": "Mozilla/5.0 TestUA", "X-Forwarded-For": "192.168.1.100"}
    res_public = requests.get(f"{API}/public/proposals/{pid}", headers=headers_view)
    assert res_public.status_code == 200
    public_data = res_public.json()
    assert "proposal" in public_data
    p_doc = public_data["proposal"]
    assert p_doc["proposal_viewed_at"] != ""
    assert p_doc["proposal_viewed_ip"] == "192.168.1.100"
    assert p_doc["proposal_viewed_ua"] == "Mozilla/5.0 TestUA"

    # Get proposal via public short code endpoint
    res_code = requests.get(f"{API}/public/proposals/code/{code}", headers=headers_view)
    assert res_code.status_code == 200
