import pytest
import os
import uuid
import requests
from datetime import datetime, timezone, timedelta

mongo_url = os.environ.get("MONGO_URL")
db_name = os.environ.get("DB_NAME")

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api"

@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s

@pytest.fixture(scope="module")
def user_ctx(session):
    email = f"seller_s6_{uuid.uuid4().hex[:6]}@propostaja.com"
    password = "teste123"
    payload = {"name": "Seller Sprint 6", "email": email, "password": password}
    r = session.post(f"{API}/auth/register", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    return {"token": data["token"], "user": data["user"], "email": email, "password": password}

@pytest.fixture(scope="module")
def auth_headers(user_ctx):
    return {"Authorization": f"Bearer {user_ctx['token']}", "Content-Type": "application/json"}

def test_sprint6_proposal_flow(session, auth_headers, user_ctx):
    # 1. Create a proposal and check default timeline and temperature
    payload = {
        "client_name": "Cliente Sprint 6",
        "client_document": "12345678909",
        "client_phone": "11988887777",
        "products": [
            {"name": "Consultoria", "quantity": 1, "price": 1000.0}
        ],
        "shipping_deadline": "2026-07-01",
        "notes": "Nova proposta",
    }
    r = session.post(f"{API}/proposals", headers=auth_headers, json=payload, timeout=30)
    assert r.status_code == 200, r.text
    prop = r.json()
    pid = prop["id"]
    pcode = prop["public_code"]
    
    assert prop["temperature"] == "morna"
    assert "timeline" in prop
    timeline = prop["timeline"]
    assert len(timeline) >= 2
    types = [t["type"] for t in timeline]
    assert "created" in types
    assert "sent" in types

    # 2. Access the public proposal page (1st time)
    r_pub1 = session.get(f"{API}/public/proposals/{pid}", timeout=30)
    assert r_pub1.status_code == 200
    pub_data = r_pub1.json()
    assert len(pub_data["proposal"]["timeline"]) == len(timeline) + 1
    assert pub_data["proposal"]["timeline"][-1]["type"] == "viewed"
    
    # 3. Access public proposal page by code (repeated view)
    r_pub2 = session.get(f"{API}/public/proposals/code/{pcode}", timeout=30)
    assert r_pub2.status_code == 200
    pub_data2 = r_pub2.json()
    # Check that we appended a second viewed event (repeated views registered in timeline)
    assert len(pub_data2["proposal"]["timeline"]) == len(timeline) + 2
    assert pub_data2["proposal"]["timeline"][-2]["type"] == "viewed"
    assert pub_data2["proposal"]["timeline"][-1]["type"] == "viewed"

    # 4. Patch temperature directly
    r_temp = session.patch(
        f"{API}/proposals/{pid}/temperature",
        headers=auth_headers,
        json={"temperature": "quente"},
        timeout=30
    )
    assert r_temp.status_code == 200
    # verify update
    r_get = session.get(f"{API}/proposals", headers=auth_headers, timeout=30)
    assert r_get.status_code == 200
    props = r_get.json()
    prop_updated = next(p for p in props if p["id"] == pid)
    assert prop_updated["temperature"] == "quente"

    # 5. Add manual timeline event and set next action
    tomorrow_str = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    manual_payload = {
        "type": "whatsapp",
        "description": "WhatsApp enviado cobrando retorno",
        "next_action_date": tomorrow_str,
        "next_action_description": "Ligar se não responder",
        "temperature": "quente"
    }
    r_manual = session.post(
        f"{API}/proposals/{pid}/timeline",
        headers=auth_headers,
        json=manual_payload,
        timeout=30
    )
    assert r_manual.status_code == 200, r_manual.text
    manual_res = r_manual.json()
    assert manual_res["next_action_date"] == tomorrow_str
    assert manual_res["next_action_description"] == "Ligar se não responder"
    
    # Verify timeline is updated
    timeline_updated = manual_res["timeline"]
    assert timeline_updated[-1]["type"] == "whatsapp"
    assert timeline_updated[-1]["description"] == "WhatsApp enviado cobrando retorno"

    # 6. Accept proposal and check timeline
    accept_payload = {
        "name": "Assinante Teste",
        "document": "123.456.789-00",
        "role": "Diretor",
        "accepted": True
    }
    r_accept = session.post(f"{API}/proposals/{pid}/accept", json=accept_payload, timeout=30)
    assert r_accept.status_code == 200, r_accept.text
    accept_res = r_accept.json()
    assert accept_res["status"] == "aprovado"
    assert accept_res["acceptance_status"] == "accepted"
    
    # Check that accepted is in timeline
    assert accept_res["timeline"][-1]["type"] == "accepted"
