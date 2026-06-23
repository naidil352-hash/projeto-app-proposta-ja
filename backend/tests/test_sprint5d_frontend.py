import pytest
import asyncio
import os
import uuid
import requests
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from server import create_access_token

mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
client_db = AsyncIOMotorClient(mongo_url)
db = client_db[db_name]

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api"

@pytest.fixture(scope="module")
def setup_sprint5d_data():
    loop = asyncio.get_event_loop()
    company_id = f"company-5d-{uuid.uuid4().hex[:6]}"
    owner_id = f"owner-5d-{uuid.uuid4().hex[:6]}"
    owner_email = f"{owner_id}@test.com"

    user = {
        "id": owner_id,
        "email": owner_email,
        "name": "Owner 5D",
        "company_id": company_id,
        "role": "owner",
        "active": True,
        "deleted": False,
        "phone": "+5511999991234",
        "whatsapp": "+5511999991234"
    }

    company = {
        "id": company_id,
        "user_id": owner_id,
        "company_name": "Proposta Ja LTDA",
        "cnpj": "12.345.678/0001-00",
        "phone": "+551133334444",
        "email": "contato@propostaja.com.br",
        "address": "Av Paulista, 1000",
        "trial_days": 60,
        "trial_started_at": datetime.now(timezone.utc).isoformat(),
        "trial_expires_at": (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    }

    loop.run_until_complete(db.users.insert_one(user))
    loop.run_until_complete(db.companies.insert_one(company))

    token = create_access_token(owner_id, owner_email)

    yield {
        "company_id": company_id,
        "owner_id": owner_id,
        "token": token
    }

    # Cleanup
    loop.run_until_complete(db.users.delete_many({"company_id": company_id}))
    loop.run_until_complete(db.companies.delete_many({"id": company_id}))
    loop.run_until_complete(db.proposals.delete_many({"company_id": company_id}))
    client_db.close()

def test_sprint5d_cycle(setup_sprint5d_data):
    data = setup_sprint5d_data
    token = data["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create a proposal as a Consultant/Owner
    proposal_payload = {
        "client_name": "Cliente Teste 5D",
        "client_document": "99.999.999/0001-99",
        "client_phone": "(11) 98888-7777",
        "products": [
            {
                "name": "Servico Exemplo",
                "description": "Descricao do servico de homologacao",
                "quantity": 2,
                "unit_price": 500.0,
                "unit": "UN"
            }
        ],
        "shipping_deadline": "5 dias uteis",
        "notes": "Minhas observações de teste",
        "discount": 100.0,
        "validity_days": 10
    }

    res_create = requests.post(f"{API}/proposals", json=proposal_payload, headers=headers)
    assert res_create.status_code == 200
    prop = res_create.json()
    
    assert "id" in prop
    assert "public_code" in prop
    assert len(prop["public_code"]) == 6
    assert prop["public_code"].isupper()
    
    pid = prop["id"]
    code = prop["public_code"]

    # 2. WhatsApp: check that seller snapshot and seller_whatsapp exist on the proposal
    assert prop["seller_name"] == "Owner 5D"
    assert prop["seller_whatsapp"] == "+5511999991234"
    assert prop["seller_phone"] == "+5511999991234"

    # 3. Visualização (View tracking via short URL)
    headers_view = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15",
        "X-Forwarded-For": "203.0.113.195"
    }
    res_public = requests.get(f"{API}/public/proposals/code/{code}", headers=headers_view)
    assert res_public.status_code == 200
    public_data = res_public.json()
    
    assert "proposal" in public_data
    assert "company" in public_data
    
    p_doc = public_data["proposal"]
    assert p_doc["proposal_viewed_at"] != ""
    assert p_doc["proposal_viewed_ip"] == "203.0.113.195"
    assert "iPhone" in p_doc["proposal_viewed_ua"] or p_doc["proposal_viewed_ua"] == "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15"

    # 4. Aceite (Submit Accept)
    accept_payload = {
        "name": "Maria Gestora",
        "document": "222.222.222-22",
        "role": "CEO",
        "accepted": True
    }
    res_accept = requests.post(f"{API}/proposals/{pid}/accept", json=accept_payload)
    assert res_accept.status_code == 200
    accepted_prop = res_accept.json()
    
    assert accepted_prop["acceptance_status"] == "accepted"
    assert accepted_prop["status"] == "aprovado"
    assert accepted_prop["accept_name"] == "Maria Gestora"
    assert accepted_prop["accept_document"] == "222.222.222-22"
    assert accepted_prop["accept_role"] == "CEO"
    assert accepted_prop["accept_date"] != ""

    # 5. Atualização de status verification for consultant
    res_detail = requests.get(f"{API}/proposals/{pid}", headers=headers)
    assert res_detail.status_code == 200
    detailed_prop = res_detail.json()
    
    assert detailed_prop["status"] == "aprovado" or detailed_prop["status"] == "accepted"
    assert detailed_prop["acceptance_status"] == "accepted"

    # 6. Recusa (Test with a new proposal)
    res_create2 = requests.post(f"{API}/proposals", json=proposal_payload, headers=headers)
    prop2 = res_create2.json()
    pid2 = prop2["id"]
    
    reject_payload = {
        "name": "Maria Gestora",
        "document": "222.222.222-22",
        "role": "CEO",
        "accepted": False
    }
    res_reject = requests.post(f"{API}/proposals/{pid2}/accept", json=reject_payload)
    assert res_reject.status_code == 200
    rejected_prop = res_reject.json()
    
    assert rejected_prop["acceptance_status"] == "rejected"
    assert rejected_prop["status"] == "perdido"
