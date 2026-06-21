import pytest
import asyncio
import os
import uuid
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from server import create_access_token

mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
client_db = AsyncIOMotorClient(mongo_url)
db = client_db[db_name]

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api"

@pytest.fixture(scope="module")
def setup_sprint4c_data():
    loop = asyncio.get_event_loop()
    company_id = f"company-4c-{uuid.uuid4().hex[:6]}"
    
    owner_id = f"owner-4c-{uuid.uuid4().hex[:6]}"
    owner_email = f"{owner_id}@test.com"
    
    admin_id = f"admin-4c-{uuid.uuid4().hex[:6]}"
    admin_email = f"{admin_id}@test.com"
    
    seller_a_id = f"seller-a-4c-{uuid.uuid4().hex[:6]}"
    seller_a_email = f"{seller_a_id}@test.com"
    
    seller_b_id = f"seller-b-4c-{uuid.uuid4().hex[:6]}"
    seller_b_email = f"{seller_b_id}@test.com"

    users = [
        {"id": owner_id, "email": owner_email, "name": "Owner 4C", "company_id": company_id, "role": "owner", "active": True},
        {"id": admin_id, "email": admin_email, "name": "Admin 4C", "company_id": company_id, "role": "admin", "active": True},
        {"id": seller_a_id, "email": seller_a_email, "name": "Seller A 4C", "company_id": company_id, "role": "seller", "active": True},
        {"id": seller_b_id, "email": seller_b_email, "name": "Seller B 4C", "company_id": company_id, "role": "seller", "active": True},
    ]

    tokens = {
        "owner": create_access_token(owner_id, owner_email),
        "admin": create_access_token(admin_id, admin_email),
        "seller_a": create_access_token(seller_a_id, seller_a_email),
        "seller_b": create_access_token(seller_b_id, seller_b_email),
    }

    companies = [
        {"id": company_id, "user_id": owner_id, "company_name": "Company 4C"}
    ]

    # Insert Proposals with different seller snapshots and statuses
    proposals = [
        # Seller A proposals
        {
            "id": f"prop-1-{uuid.uuid4().hex[:6]}",
            "user_id": seller_a_id,
            "company_id": company_id,
            "seller_name": "Vendedor A",
            "seller_email": seller_a_email,
            "seller_phone": "123456",
            "seller_role": "seller",
            "client_name": "Cliente 1",
            "client_document": "111",
            "client_phone": "111",
            "status": "aberto",
            "total": 100.0,
            "grand_total": 100.0,
            "deleted": False
        },
        {
            "id": f"prop-2-{uuid.uuid4().hex[:6]}",
            "user_id": seller_a_id,
            "company_id": company_id,
            "seller_name": "Vendedor A",
            "seller_email": seller_a_email,
            "seller_phone": "123456",
            "seller_role": "seller",
            "client_name": "Cliente 2",
            "client_document": "222",
            "client_phone": "222",
            "status": "aprovado",
            "total": 300.0,
            "grand_total": 300.0,
            "deleted": False
        },
        # Seller B proposals
        {
            "id": f"prop-3-{uuid.uuid4().hex[:6]}",
            "user_id": seller_b_id,
            "company_id": company_id,
            "seller_name": "Vendedor B",
            "seller_email": seller_b_email,
            "seller_phone": "7890",
            "seller_role": "seller",
            "client_name": "Cliente 3",
            "client_document": "333",
            "client_phone": "333",
            "status": "negociacao",
            "total": 500.0,
            "grand_total": 500.0,
            "deleted": False
        },
        {
            "id": f"prop-4-{uuid.uuid4().hex[:6]}",
            "user_id": seller_b_id,
            "company_id": company_id,
            "seller_name": "Vendedor B",
            "seller_email": seller_b_email,
            "seller_phone": "7890",
            "seller_role": "seller",
            "client_name": "Cliente 4",
            "client_document": "444",
            "client_phone": "444",
            "status": "perdido",
            "total": 200.0,
            "grand_total": 200.0,
            "deleted": False
        },
        # Owner proposal
        {
            "id": f"prop-5-{uuid.uuid4().hex[:6]}",
            "user_id": owner_id,
            "company_id": company_id,
            "seller_name": "Owner Seller",
            "seller_email": owner_email,
            "seller_phone": "999",
            "seller_role": "owner",
            "client_name": "Cliente 5",
            "client_document": "555",
            "client_phone": "555",
            "status": "aberto",
            "total": 1000.0,
            "grand_total": 1000.0,
            "deleted": False
        },
        # Deleted proposal (should be ignored by all queries)
        {
            "id": f"prop-del-{uuid.uuid4().hex[:6]}",
            "user_id": seller_a_id,
            "company_id": company_id,
            "seller_name": "Vendedor A",
            "seller_email": seller_a_email,
            "status": "aberto",
            "total": 1500.0,
            "grand_total": 1500.0,
            "deleted": True
        }
    ]

    loop.run_until_complete(db.users.insert_many(users))
    loop.run_until_complete(db.companies.insert_many(companies))
    loop.run_until_complete(db.proposals.insert_many(proposals))

    yield {
        "company_id": company_id,
        "owner_id": owner_id,
        "admin_id": admin_id,
        "seller_a_id": seller_a_id,
        "seller_b_id": seller_b_id,
        "tokens": tokens
    }

    loop.run_until_complete(db.users.delete_many({"company_id": company_id}))
    loop.run_until_complete(db.companies.delete_many({"id": company_id}))
    loop.run_until_complete(db.proposals.delete_many({"company_id": company_id}))
    client_db.close()

def test_proposals_list_rbac_and_filters(setup_sprint4c_data):
    tokens = setup_sprint4c_data["tokens"]
    seller_a_id = setup_sprint4c_data["seller_a_id"]
    
    headers_owner = {"Authorization": f"Bearer {tokens['owner']}"}
    headers_admin = {"Authorization": f"Bearer {tokens['admin']}"}
    headers_seller_a = {"Authorization": f"Bearer {tokens['seller_a']}"}

    # 1. Owner sees all non-deleted proposals (5 total)
    r = requests.get(f"{API}/proposals", headers=headers_owner)
    assert r.status_code == 200
    res = r.json()
    assert len(res) == 5
    assert all(not p.get("deleted") for p in res)

    # 2. Admin sees all non-deleted proposals (5 total)
    r = requests.get(f"{API}/proposals", headers=headers_admin)
    assert r.status_code == 200
    assert len(r.json()) == 5

    # 3. Seller A sees only their own proposals (2 total)
    r = requests.get(f"{API}/proposals", headers=headers_seller_a)
    assert r.status_code == 200
    res = r.json()
    assert len(res) == 2
    assert all(p["user_id"] == seller_a_id for p in res)

    # 4. Filter scope=team (or meu_time) with owner token -> returns other team members' proposals (4 total)
    # excludes owner's own proposal (prop-5)
    r = requests.get(f"{API}/proposals?scope=team", headers=headers_owner)
    assert r.status_code == 200
    res = r.json()
    assert len(res) == 4
    assert not any(p["user_id"] == setup_sprint4c_data["owner_id"] for p in res)

    # 5. Filter scope=vendedor & seller_id with owner token -> returns specific seller proposals
    r = requests.get(f"{API}/proposals?scope=vendedor&seller_id={seller_a_id}", headers=headers_owner)
    assert r.status_code == 200
    res = r.json()
    assert len(res) == 2
    assert all(p["user_id"] == seller_a_id for p in res)

    # 6. Filter by seller_name exact or search
    r = requests.get(f"{API}/proposals?seller_name=Vendedor B", headers=headers_owner)
    assert r.status_code == 200
    res = r.json()
    assert len(res) == 2
    assert all(p["seller_name"] == "Vendedor B" for p in res)

def test_sellers_analytics(setup_sprint4c_data):
    tokens = setup_sprint4c_data["tokens"]
    
    headers_owner = {"Authorization": f"Bearer {tokens['owner']}"}
    headers_seller_a = {"Authorization": f"Bearer {tokens['seller_a']}"}

    # 1. Owner sees all sellers stats
    r = requests.get(f"{API}/analytics/sellers", headers=headers_owner)
    assert r.status_code == 200
    res = r.json()
    
    # 3 unique seller names represented among active proposals: "Vendedor A", "Vendedor B", "Owner Seller"
    assert len(res) == 3
    
    # Map by seller_name to verify details
    stats_map = {item["seller_name"]: item for item in res}
    
    # Vendedor A: 1 aberto (100.0), 1 aprovado (300.0)
    stats_a = stats_map["Vendedor A"]
    assert stats_a["proposal_count"] == 2
    assert stats_a["approved_count"] == 1
    assert stats_a["won_count"] == 1
    assert stats_a["open_count"] == 1
    assert stats_a["lost_count"] == 0
    assert stats_a["revenue"] == 300.0
    assert stats_a["value_sold"] == 300.0
    assert stats_a["value_negotiated"] == 100.0
    assert stats_a["conversion_rate"] == 50.0

    # Vendedor B: 1 negociacao (500.0), 1 perdido (200.0)
    stats_b = stats_map["Vendedor B"]
    assert stats_b["proposal_count"] == 2
    assert stats_b["approved_count"] == 0
    assert stats_b["open_count"] == 1
    assert stats_b["lost_count"] == 1
    assert stats_b["revenue"] == 0.0
    assert stats_b["value_sold"] == 0.0
    assert stats_b["value_negotiated"] == 500.0
    assert stats_b["conversion_rate"] == 0.0

    # Owner Seller: 1 aberto (1000.0)
    stats_owner = stats_map["Owner Seller"]
    assert stats_owner["proposal_count"] == 1
    assert stats_owner["open_count"] == 1
    assert stats_owner["revenue"] == 0.0
    assert stats_owner["value_negotiated"] == 1000.0

    # 2. Seller A sees only their own stats
    r = requests.get(f"{API}/analytics/sellers", headers=headers_seller_a)
    assert r.status_code == 200
    res_seller = r.json()
    assert len(res_seller) == 1
    assert res_seller[0]["seller_name"] == "Vendedor A"
