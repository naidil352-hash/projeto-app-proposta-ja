import pytest
import uuid
import os
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from server import create_access_token

# Connect directly to MongoDB for setup/cleanup
mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
client_db = AsyncIOMotorClient(mongo_url)
db = client_db[db_name]

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api"

@pytest.fixture(scope="module")
def setup_data():
    """Sets up a mock company and users with different roles for testing."""
    company_id = str(uuid.uuid4())
    owner_id = str(uuid.uuid4())
    admin_id = str(uuid.uuid4())
    seller_a_id = str(uuid.uuid4())
    seller_b_id = str(uuid.uuid4())
    legacy_user_id = str(uuid.uuid4())
    inactive_user_id = str(uuid.uuid4())

    owner_email = f"owner_{uuid.uuid4().hex[:6]}@test.com"
    admin_email = f"admin_{uuid.uuid4().hex[:6]}@test.com"
    seller_a_email = f"seller_a_{uuid.uuid4().hex[:6]}@test.com"
    seller_b_email = f"seller_b_{uuid.uuid4().hex[:6]}@test.com"
    legacy_email = f"legacy_{uuid.uuid4().hex[:6]}@test.com"
    inactive_email = f"inactive_{uuid.uuid4().hex[:6]}@test.com"

    # Insert users
    users = [
        {"id": owner_id, "email": owner_email, "name": "Owner User", "company_id": company_id, "role": "owner", "active": True},
        {"id": admin_id, "email": admin_email, "name": "Admin User", "company_id": company_id, "role": "admin", "active": True},
        {"id": seller_a_id, "email": seller_a_email, "name": "Seller A", "company_id": company_id, "role": "seller", "active": True},
        {"id": seller_b_id, "email": seller_b_email, "name": "Seller B", "company_id": company_id, "role": "seller", "active": True},
        {"id": legacy_user_id, "email": legacy_email, "name": "Legacy User"}, # Missing active, role, company_id
        {"id": inactive_user_id, "email": inactive_email, "name": "Inactive User", "company_id": company_id, "role": "seller", "active": False}
    ]

    # Tokens
    tokens = {
        "owner": create_access_token(owner_id, owner_email),
        "admin": create_access_token(admin_id, admin_email),
        "seller_a": create_access_token(seller_a_id, seller_a_email),
        "seller_b": create_access_token(seller_b_id, seller_b_email),
        "legacy": create_access_token(legacy_user_id, legacy_email),
        "inactive": create_access_token(inactive_user_id, inactive_email)
    }

    # Insert mock company document so fallback can look it up
    companies = [
        {"id": company_id, "user_id": owner_id, "company_name": "Test Company"}
    ]

    # Run DB setup
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.users.insert_many(users))
    loop.run_until_complete(db.companies.insert_many(companies))

    yield {
        "company_id": company_id,
        "owner_id": owner_id,
        "admin_id": admin_id,
        "seller_a_id": seller_a_id,
        "seller_b_id": seller_b_id,
        "legacy_user_id": legacy_user_id,
        "tokens": tokens
    }

    # Cleanup
    loop.run_until_complete(db.users.delete_many({"id": {"$in": [owner_id, admin_id, seller_a_id, seller_b_id, legacy_user_id, inactive_user_id]}}))
    loop.run_until_complete(db.companies.delete_many({"id": company_id}))
    loop.run_until_complete(db.proposals.delete_many({"company_id": company_id}))
    loop.run_until_complete(db.products.delete_many({"company_id": company_id}))
    client_db.close()


def test_products_creation_permissions(setup_data):
    # Seller A tries to create a product (Should return 403)
    headers = {"Authorization": f"Bearer {setup_data['tokens']['seller_a']}"}
    r = requests.post(f"{API}/products", json={"code": "P1", "name": "Prod 1", "price": 10.0}, headers=headers)
    assert r.status_code == 403

    # Admin tries to create a product (Should return 200)
    headers = {"Authorization": f"Bearer {setup_data['tokens']['admin']}"}
    r = requests.post(f"{API}/products", json={"code": "P1", "name": "Prod 1", "price": 10.0}, headers=headers)
    assert r.status_code == 200


def test_proposal_isolation_and_leakage(setup_data):
    # Seller A creates a proposal
    headers_a = {"Authorization": f"Bearer {setup_data['tokens']['seller_a']}"}
    payload = {
        "client_name": "Cliente A",
        "client_document": "123",
        "client_phone": "123",
        "products": [{"name": "P1", "quantity": 1, "price": 100}],
        "shipping_deadline": "5 dias"
    }
    r = requests.post(f"{API}/proposals", json=payload, headers=headers_a)
    assert r.status_code == 200
    prop_id = r.json()["id"]

    # Seller A can read their own proposal
    r = requests.get(f"{API}/proposals/{prop_id}", headers=headers_a)
    assert r.status_code == 200

    # Seller B tries to read Seller A's proposal (Should return 404 Not Found to prevent leakage)
    headers_b = {"Authorization": f"Bearer {setup_data['tokens']['seller_b']}"}
    r = requests.get(f"{API}/proposals/{prop_id}", headers=headers_b)
    assert r.status_code == 404

    # Seller B tries to update Seller A's proposal (Should return 404 Not Found)
    r = requests.put(f"{API}/proposals/{prop_id}", json=payload, headers=headers_b)
    assert r.status_code == 404

    # Seller B tries to delete Seller A's proposal (Should return 404 Not Found)
    r = requests.delete(f"{API}/proposals/{prop_id}", headers=headers_b)
    assert r.status_code == 404

    # Seller B tries to duplicate Seller A's proposal (Should return 404 Not Found)
    r = requests.post(f"{API}/proposals/{prop_id}/duplicate", headers=headers_b)
    assert r.status_code == 404


def test_legacy_user_fallbacks(setup_data):
    # Legacy user makes a request to /auth/me
    headers = {"Authorization": f"Bearer {setup_data['tokens']['legacy']}"}
    r = requests.get(f"{API}/auth/me", headers=headers)
    assert r.status_code == 200
    data = r.json()
    
    # Assert fallbacks are populated
    assert data["role"] == "owner"
    assert data["active"] is True
    assert "company_id" in data


def test_inactive_user_blocked(setup_data):
    # Inactive user tries to access /auth/me (Should return 403 desativado)
    headers = {"Authorization": f"Bearer {setup_data['tokens']['inactive']}"}
    r = requests.get(f"{API}/auth/me", headers=headers)
    assert r.status_code == 403
    assert r.json()["detail"] == "Usuário desativado"
