import pytest
import asyncio
import os
import uuid
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from server import create_access_token, get_role_label

mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
client_db = AsyncIOMotorClient(mongo_url)
db = client_db[db_name]

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api"

@pytest.fixture(scope="module")
def setup_test_data():
    loop = asyncio.get_event_loop()
    company_id = f"company-5b-{uuid.uuid4().hex[:6]}"
    
    owner_id = f"owner-5b-{uuid.uuid4().hex[:6]}"
    owner_email = f"{owner_id}@test.com"
    
    admin_id = f"admin-5b-{uuid.uuid4().hex[:6]}"
    admin_email = f"{admin_id}@test.com"
    
    # Owner will have pre-existing phone and signature
    owner_user = {
        "id": owner_id,
        "email": owner_email,
        "name": "Owner 5B",
        "company_id": company_id,
        "role": "owner",
        "active": True,
        "deleted": False,
        "phone": "+5511999998888",
        "whatsapp": "+5511999998888",
        "signature_url": "https://example.com/sig.png"
    }
    
    admin_user = {
        "id": admin_id,
        "email": admin_email,
        "name": "Admin 5B",
        "company_id": company_id,
        "role": "admin",
        "active": True,
        "deleted": False,
        "phone": "",
        "whatsapp": "",
        "signature_url": ""
    }

    loop.run_until_complete(db.users.insert_many([owner_user, admin_user]))
    loop.run_until_complete(db.companies.insert_one({"id": company_id, "user_id": owner_id, "company_name": "Company 5B"}))

    tokens = {
        "owner": create_access_token(owner_id, owner_email),
        "admin": create_access_token(admin_id, admin_email),
    }

    yield {
        "company_id": company_id,
        "owner_id": owner_id,
        "owner_email": owner_email,
        "admin_id": admin_id,
        "admin_email": admin_email,
        "tokens": tokens
    }

    # Cleanup
    loop.run_until_complete(db.users.delete_many({"company_id": company_id}))
    loop.run_until_complete(db.companies.delete_many({"id": company_id}))
    loop.run_until_complete(db.proposals.delete_many({"company_id": company_id}))


def test_get_role_label():
    assert get_role_label("owner") == "Proprietário"
    assert get_role_label("admin") == "Administrador"
    assert get_role_label("seller") == "Consultor Comercial"
    assert get_role_label("other") == "other"
    assert get_role_label("") == ""


def test_create_user_with_fields(setup_test_data):
    data = setup_test_data
    headers = {"Authorization": f"Bearer {data['tokens']['owner']}"}
    
    new_user_email = f"seller-5b-{uuid.uuid4().hex[:6]}@test.com"
    payload = {
        "name": "New Seller 5B",
        "email": new_user_email,
        "password": "password123",
        "role": "seller",
        "phone": "+5511977776666",
        "whatsapp": "+5511977776666",
        "signature_url": "https://example.com/sig-seller.png"
    }
    
    res = requests.post(f"{API}/users", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    res_data = res.json()
    assert res_data["phone"] == "+5511977776666"
    assert res_data["whatsapp"] == "+5511977776666"
    assert res_data["signature_url"] == "https://example.com/sig-seller.png"


def test_update_user_fields(setup_test_data):
    data = setup_test_data
    headers = {"Authorization": f"Bearer {data['tokens']['owner']}"}
    
    # We update the admin user's fields
    payload = {
        "name": "Admin 5B Updated",
        "phone": "+5511988887777",
        "whatsapp": "+5511988887777",
        "signature_url": "https://example.com/sig-admin.png"
    }
    
    res = requests.put(f"{API}/users/{data['admin_id']}", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    res_data = res.json()
    assert res_data["name"] == "Admin 5B Updated"
    assert res_data["phone"] == "+5511988887777"
    assert res_data["whatsapp"] == "+5511988887777"
    assert res_data["signature_url"] == "https://example.com/sig-admin.png"


def test_proposal_snapshots(setup_test_data):
    data = setup_test_data
    
    # Create proposal with owner (has phone, whatsapp, signature)
    headers = {"Authorization": f"Bearer {data['tokens']['owner']}"}
    payload = {
        "client_name": "Test Client 5B",
        "client_document": "12.345.678/0001-99",
        "client_phone": "(11) 99999-1111",
        "products": [
            {"name": "Consultoria", "quantity": 1, "unit_price": 5000.0}
        ],
        "shipping_deadline": "Immediate",
        "notes": "Test notes",
        "discount": 0.0,
        "validity_days": 10
    }
    
    res = requests.post(f"{API}/proposals", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    res_data = res.json()
    
    # Verify snapshot
    assert res_data["seller_name"] == "Owner 5B"
    assert res_data["seller_email"] == data["owner_email"]
    assert res_data["seller_phone"] == "+5511999998888"
    assert res_data["seller_role"] == "owner"
    assert res_data["seller_signature"] == "https://example.com/sig.png"

    # Create proposal with admin (phone and signature updated in previous test)
    headers_admin = {"Authorization": f"Bearer {data['tokens']['admin']}"}
    res_admin = requests.post(f"{API}/proposals", json=payload, headers=headers_admin)
    assert res_admin.status_code == 200, res_admin.text
    res_admin_data = res_admin.json()
    
    # Verify snapshot has admin's phone and signature
    assert res_admin_data["seller_name"] == "Admin 5B Updated"
    assert res_admin_data["seller_phone"] == "+5511988887777"
    assert res_admin_data["seller_signature"] == "https://example.com/sig-admin.png"


def test_proposal_snapshot_empty_phone(setup_test_data):
    data = setup_test_data
    loop = asyncio.get_event_loop()
    
    # Create a user with empty phone
    empty_user_id = f"empty-5b-{uuid.uuid4().hex[:6]}"
    empty_user_email = f"{empty_user_id}@test.com"
    empty_user = {
        "id": empty_user_id,
        "email": empty_user_email,
        "name": "Empty Seller 5B",
        "company_id": data["company_id"],
        "role": "seller",
        "active": True,
        "deleted": False,
        "phone": "",
        "whatsapp": "",
        "signature_url": ""
    }
    loop.run_until_complete(db.users.insert_one(empty_user))
    token_empty = create_access_token(empty_user_id, empty_user_email)
    
    headers = {"Authorization": f"Bearer {token_empty}"}
    payload = {
        "client_name": "Test Client 5B Empty",
        "client_document": "12.345.678/0001-99",
        "client_phone": "(11) 99999-1111",
        "products": [
            {"name": "Consultoria", "quantity": 1, "unit_price": 5000.0}
        ],
        "shipping_deadline": "Immediate",
        "notes": "Test notes",
        "discount": 0.0,
        "validity_days": 10
    }
    
    res = requests.post(f"{API}/proposals", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    res_data = res.json()
    
    # Verify phone is empty string
    assert res_data["seller_phone"] == ""
    assert res_data["seller_signature"] == ""


def test_legacy_proposals_retrocompatibility(setup_test_data):
    # Insert legacy proposal with missing seller fields directly to db
    data = setup_test_data
    loop = asyncio.get_event_loop()
    legacy_id = f"legacy-5b-{uuid.uuid4().hex[:6]}"
    
    legacy_proposal = {
        "id": legacy_id,
        "user_id": data["owner_id"],
        "company_id": data["company_id"],
        "client_name": "Legacy Client",
        "client_document": "111",
        "client_phone": "111",
        "products": [{"name": "Item A", "quantity": 1, "unit_price": 100.0}],
        "shipping_deadline": "5 dias",
        "status": "aberto",
        "total": 100.0,
        "deleted": False
    }
    
    loop.run_until_complete(db.proposals.insert_one(legacy_proposal))
    
    # Retrieve legacy proposal via API and check normalization
    headers = {"Authorization": f"Bearer {data['tokens']['owner']}"}
    res = requests.get(f"{API}/proposals/{legacy_id}", headers=headers)
    assert res.status_code == 200, res.text
    res_data = res.json()
    
    assert res_data["seller_name"] == ""
    assert res_data["seller_email"] == ""
    assert res_data["seller_phone"] == ""
    assert res_data["seller_role"] == ""
    assert res_data["seller_signature"] == ""
