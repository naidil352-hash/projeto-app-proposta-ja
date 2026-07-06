import pytest
import os
import uuid
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api"

@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s

@pytest.fixture(scope="module")
def user_ctx(session):
    email = f"owner_s7_{uuid.uuid4().hex[:6]}@propostaja.com"
    password = "teste123"
    payload = {"name": "Owner Sprint 7", "email": email, "password": password}
    r = session.post(f"{API}/auth/register", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    return {"token": data["token"], "user": data["user"], "email": email, "password": password}

@pytest.fixture(scope="module")
def auth_headers(user_ctx):
    return {"Authorization": f"Bearer {user_ctx['token']}", "Content-Type": "application/json"}

def test_commercial_templates_crud(session, auth_headers):
    # 1. List templates. An automatic default template should be generated.
    r_list = session.get(f"{API}/commercial-templates", headers=auth_headers, timeout=30)
    assert r_list.status_code == 200, r_list.text
    templates = r_list.json()
    assert len(templates) == 1
    assert templates[0]["name"] == "Condições Comerciais Padrão"
    assert templates[0]["is_default"] is True
    
    # 2. Create a new custom template
    payload = {
        "name": "Template FOB Personalizado",
        "is_default": False,
        "payment_terms": "30 dias",
        "shipping_type": "FOB",
        "shipping_responsible": "Destinatário",
        "shipping_company": "Alfa Trans",
        "manufacturing_days": "10 dias",
        "delivery_days": "5 dias",
        "warranty": "12 meses",
        "validity_days": 30,
        "incoterm": "FOB",
        "currency": "USD",
        "commercial_conditions": "FOB extra info",
        "internal_notes": "Internal only"
    }
    r_create = session.post(f"{API}/commercial-templates", headers=auth_headers, json=payload, timeout=30)
    assert r_create.status_code == 200, r_create.text
    new_tpl = r_create.json()
    assert new_tpl["name"] == "Template FOB Personalizado"
    assert new_tpl["is_default"] is False
    assert new_tpl["currency"] == "USD"
    
    # List should now show 2 templates
    r_list2 = session.get(f"{API}/commercial-templates", headers=auth_headers, timeout=30)
    assert len(r_list2.json()) == 2
    
    # 3. Update the custom template to be the default template
    payload_update = {**payload, "is_default": True, "name": "FOB Default"}
    r_update = session.put(f"{API}/commercial-templates/{new_tpl['id']}", headers=auth_headers, json=payload_update, timeout=30)
    assert r_update.status_code == 200, r_update.text
    updated = r_update.json()
    assert updated["name"] == "FOB Default"
    assert updated["is_default"] is True
    
    # The previous default template should have been cleared of is_default
    r_list3 = session.get(f"{API}/commercial-templates", headers=auth_headers, timeout=30)
    tpls = r_list3.json()
    prev_default = next(t for t in tpls if t["id"] == templates[0]["id"])
    assert prev_default["is_default"] is False
    
    # 4. Set default back to the first template via set-default endpoint
    r_set_def = session.post(f"{API}/commercial-templates/{templates[0]['id']}/set-default", headers=auth_headers, timeout=30)
    assert r_set_def.status_code == 200
    
    # Verify set-default
    r_list4 = session.get(f"{API}/commercial-templates", headers=auth_headers, timeout=30)
    tpls4 = r_list4.json()
    t0 = next(t for t in tpls4 if t["id"] == templates[0]["id"])
    t1 = next(t for t in tpls4 if t["id"] == new_tpl["id"])
    assert t0["is_default"] is True
    assert t1["is_default"] is False
    
    # 5. Delete the custom template
    r_del = session.delete(f"{API}/commercial-templates/{new_tpl['id']}", headers=auth_headers, timeout=30)
    assert r_del.status_code == 200
    
    # Verify deletion
    r_list5 = session.get(f"{API}/commercial-templates", headers=auth_headers, timeout=30)
    assert len(r_list5.json()) == 1
