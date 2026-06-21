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
def setup_sprint5a_data():
    loop = asyncio.get_event_loop()
    company_id = f"company-5a-{uuid.uuid4().hex[:6]}"
    
    owner_id = f"owner-5a-{uuid.uuid4().hex[:6]}"
    owner_email = f"{owner_id}@test.com"
    
    admin_id = f"admin-5a-{uuid.uuid4().hex[:6]}"
    admin_email = f"{admin_id}@test.com"
    
    seller_a_id = f"seller-a-5a-{uuid.uuid4().hex[:6]}"
    seller_a_email = f"{seller_a_id}@test.com"
    
    seller_b_id = f"seller-b-5a-{uuid.uuid4().hex[:6]}"
    seller_b_email = f"{seller_b_id}@test.com"

    users = [
        {"id": owner_id, "email": owner_email, "name": "Owner 5A", "company_id": company_id, "role": "owner", "active": True},
        {"id": admin_id, "email": admin_email, "name": "Admin 5A", "company_id": company_id, "role": "admin", "active": True},
        {"id": seller_a_id, "email": seller_a_email, "name": "Seller A 5A", "company_id": company_id, "role": "seller", "active": True},
        {"id": seller_b_id, "email": seller_b_email, "name": "Seller B 5A", "company_id": company_id, "role": "seller", "active": True},
    ]

    tokens = {
        "owner": create_access_token(owner_id, owner_email),
        "admin": create_access_token(admin_id, admin_email),
        "seller_a": create_access_token(seller_a_id, seller_a_email),
        "seller_b": create_access_token(seller_b_id, seller_b_email),
    }

    companies = [
        {"id": company_id, "user_id": owner_id, "company_name": "Company 5A"}
    ]

    prop_1_id = f"prop-1-5a-{uuid.uuid4().hex[:6]}"
    prop_2_id = f"prop-2-5a-{uuid.uuid4().hex[:6]}"
    prop_3_id = f"prop-3-5a-{uuid.uuid4().hex[:6]}"

    # Insert Proposals (1 normal, 1 legacy, 1 other seller)
    proposals = [
        {
            "id": prop_1_id,
            "user_id": seller_a_id,
            "company_id": company_id,
            "seller_name": "Seller A",
            "seller_email": seller_a_email,
            "seller_phone": "123",
            "seller_role": "seller",
            "client_name": "Cliente 1",
            "client_document": "111",
            "client_phone": "111",
            "products": [{"name": "Item A", "quantity": 1, "unit_price": 100.0}],
            "shipping_deadline": "5 dias",
            "status": "aberto",
            "total": 100.0,
            "grand_total": 100.0,
            "acceptance_status": "pending",
            "accept_name": "",
            "accept_document": "",
            "accept_role": "",
            "accept_date": "",
            "accept_ip": "",
            "accept_device": "",
            "deleted": False
        },
        # Legacy proposal: missing acceptance and seller snapshot fields
        {
            "id": prop_2_id,
            "user_id": seller_a_id,
            "company_id": company_id,
            "client_name": "Cliente 2 (Legacy)",
            "client_document": "222",
            "client_phone": "222",
            "products": [{"name": "Item B", "quantity": 2, "unit_price": 50.0}],
            "shipping_deadline": "10 dias",
            "status": "aberto",
            "total": 100.0,
            "grand_total": 100.0,
            "deleted": False
        },
        # Proposal belonging to Seller B
        {
            "id": prop_3_id,
            "user_id": seller_b_id,
            "company_id": company_id,
            "seller_name": "Seller B",
            "seller_email": seller_b_email,
            "client_name": "Cliente 3",
            "client_document": "333",
            "client_phone": "333",
            "products": [],
            "shipping_deadline": "1 dia",
            "status": "aberto",
            "total": 0.0,
            "grand_total": 0.0,
            "deleted": False
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
        "prop_1_id": prop_1_id,
        "prop_2_id": prop_2_id,
        "prop_3_id": prop_3_id,
        "tokens": tokens
    }

    loop.run_until_complete(db.users.delete_many({"company_id": company_id}))
    loop.run_until_complete(db.companies.delete_many({"id": company_id}))
    loop.run_until_complete(db.proposals.delete_many({"company_id": company_id}))
    client_db.close()

def test_legacy_proposals_normalization(setup_sprint5a_data):
    tokens = setup_sprint5a_data["tokens"]
    prop_2_id = setup_sprint5a_data["prop_2_id"]
    headers = {"Authorization": f"Bearer {tokens['owner']}"}

    r = requests.get(f"{API}/proposals/{prop_2_id}", headers=headers)
    assert r.status_code == 200
    res = r.json()
    
    # Assert legacy fallbacks
    assert res["acceptance_status"] == "pending"
    assert res["seller_name"] == ""
    assert res["seller_email"] == ""
    assert res["seller_phone"] == ""
    assert res["seller_role"] == ""
    assert res["accept_name"] == ""
    assert res["accept_document"] == ""
    assert res["accept_role"] == ""
    assert res["accept_date"] == ""
    assert res["accept_ip"] == ""
    assert res["accept_device"] == ""

def test_proposal_accept_approved(setup_sprint5a_data):
    tokens = setup_sprint5a_data["tokens"]
    prop_1_id = setup_sprint5a_data["prop_1_id"]
    headers_owner = {"Authorization": f"Bearer {tokens['owner']}"}

    payload = {
        "name": "João Assinante",
        "document": "123.456.789-10",
        "role": "Diretor Financeiro",
        "accepted": True
    }
    
    # Accept proposal
    r = requests.post(f"{API}/proposals/{prop_1_id}/accept", json=payload)
    assert r.status_code == 200
    res = r.json()
    
    # Assert acceptance metadata
    assert res["acceptance_status"] == "accepted"
    assert res["status"] == "aprovado"
    assert res["accept_name"] == "João Assinante"
    assert res["accept_document"] == "123.456.789-10"
    assert res["accept_role"] == "Diretor Financeiro"
    assert res["accept_date"] != ""
    assert res["accept_ip"] != ""
    assert res["accept_device"] != ""

    # Test protection: Cannot accept again once finalized
    r_repeat = requests.post(f"{API}/proposals/{prop_1_id}/accept", json=payload)
    assert r_repeat.status_code == 400
    assert "já foi finalizado" in r_repeat.json()["detail"]

    # Test protection: Cannot edit details after acceptance
    edit_payload = {
        "client_name": "Editado",
        "client_document": "111",
        "client_phone": "111",
        "products": [],
        "shipping_deadline": "1 dia"
    }
    r_edit = requests.put(f"{API}/proposals/{prop_1_id}", json=edit_payload, headers=headers_owner)
    assert r_edit.status_code == 400
    assert "Não é permitido editar" in r_edit.json()["detail"]

    # Test protection: Cannot change status after acceptance
    status_payload = {"status": "negociacao"}
    r_status = requests.patch(f"{API}/proposals/{prop_1_id}/status", json=status_payload, headers=headers_owner)
    assert r_status.status_code == 400
    assert "Não é permitido alterar o status" in r_status.json()["detail"]

    # Test protection: Cannot delete accepted proposal
    r_delete = requests.delete(f"{API}/proposals/{prop_1_id}", headers=headers_owner)
    assert r_delete.status_code == 400
    assert "Não é permitido deletar" in r_delete.json()["detail"]

def test_proposal_accept_rejected(setup_sprint5a_data):
    prop_2_id = setup_sprint5a_data["prop_2_id"]

    payload = {
        "name": "Maria Recusante",
        "document": "987.654.321-00",
        "role": "Gerente",
        "accepted": False
    }
    
    # Reject proposal
    r = requests.post(f"{API}/proposals/{prop_2_id}/accept", json=payload)
    assert r.status_code == 200
    res = r.json()
    
    assert res["acceptance_status"] == "rejected"
    assert res["status"] == "perdido"
    assert res["lost_reason"] == "Recusado pelo cliente no aceite digital"

def test_reopen_proposal(setup_sprint5a_data):
    tokens = setup_sprint5a_data["tokens"]
    prop_1_id = setup_sprint5a_data["prop_1_id"]
    
    headers_owner = {"Authorization": f"Bearer {tokens['owner']}"}
    headers_seller = {"Authorization": f"Bearer {tokens['seller_a']}"}

    # Test protection: Seller cannot reopen
    r_sel = requests.post(f"{API}/proposals/{prop_1_id}/reopen", headers=headers_seller)
    assert r_sel.status_code == 403

    # Owner can reopen accepted proposal
    r_own = requests.post(f"{API}/proposals/{prop_1_id}/reopen", headers=headers_owner)
    assert r_own.status_code == 200
    res = r_own.json()
    
    # Verify reset
    assert res["acceptance_status"] == "pending"
    assert res["accept_name"] == ""
    assert res["accept_document"] == ""
    assert res["accept_role"] == ""
    assert res["accept_date"] == ""
    assert res["accept_ip"] == ""
    assert res["accept_device"] == ""

def test_rbac_proposals_isolation_visibility(setup_sprint5a_data):
    tokens = setup_sprint5a_data["tokens"]
    prop_1_id = setup_sprint5a_data["prop_1_id"] # Owned by Seller A
    prop_3_id = setup_sprint5a_data["prop_3_id"] # Owned by Seller B
    
    headers_owner = {"Authorization": f"Bearer {tokens['owner']}"}
    headers_admin = {"Authorization": f"Bearer {tokens['admin']}"}
    headers_seller_a = {"Authorization": f"Bearer {tokens['seller_a']}"}

    # 1. Owner can access all
    assert requests.get(f"{API}/proposals/{prop_1_id}", headers=headers_owner).status_code == 200
    assert requests.get(f"{API}/proposals/{prop_3_id}", headers=headers_owner).status_code == 200

    # 2. Admin can access all
    assert requests.get(f"{API}/proposals/{prop_1_id}", headers=headers_admin).status_code == 200
    assert requests.get(f"{API}/proposals/{prop_3_id}", headers=headers_admin).status_code == 200

    # 3. Seller A can access only their own
    assert requests.get(f"{API}/proposals/{prop_1_id}", headers=headers_seller_a).status_code == 200
    assert requests.get(f"{API}/proposals/{prop_3_id}", headers=headers_seller_a).status_code == 404
