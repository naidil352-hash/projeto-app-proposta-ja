"""Backend API tests for PROPOSTA JÁ."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://quick-quote-pro-5.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def user_ctx(session):
    """Register a fresh user and return {token, user, email, password}."""
    email = f"test_{uuid.uuid4().hex[:10]}@propostaja.com"
    password = "teste123"
    payload = {"name": "Vendedor Teste", "email": email, "password": password}
    r = session.post(f"{API}/auth/register", json=payload, timeout=30)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and "user" in data
    assert data["user"]["email"].lower() == email.lower()
    return {"token": data["token"], "user": data["user"], "email": email.lower(), "password": password}


@pytest.fixture(scope="module")
def auth_headers(user_ctx):
    return {"Authorization": f"Bearer {user_ctx['token']}", "Content-Type": "application/json"}


# ---------- Auth ----------
class TestAuth:
    def test_register_duplicate_returns_400(self, session, user_ctx):
        r = session.post(f"{API}/auth/register", json={
            "name": "Dup", "email": user_ctx["email"], "password": user_ctx["password"]
        }, timeout=30)
        assert r.status_code == 400

    def test_login_returns_token(self, session, user_ctx):
        r = session.post(f"{API}/auth/login", json={
            "email": user_ctx["email"], "password": user_ctx["password"]
        }, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "token" in data and data["user"]["email"] == user_ctx["email"]

    def test_login_invalid_password_401(self, session, user_ctx):
        r = session.post(f"{API}/auth/login", json={
            "email": user_ctx["email"], "password": "wrongpass"
        }, timeout=30)
        assert r.status_code == 401

    def test_me_returns_user(self, session, auth_headers, user_ctx):
        r = session.get(f"{API}/auth/me", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == user_ctx["email"]
        assert "password_hash" not in data

    def test_me_without_token_returns_401(self, session):
        r = session.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401

    def test_proposals_without_token_returns_401(self, session):
        r = session.get(f"{API}/proposals", timeout=30)
        assert r.status_code == 401


# ---------- Company ----------
class TestCompany:
    def test_get_company_default(self, session, auth_headers, user_ctx):
        r = session.get(f"{API}/company", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["user_id"] == user_ctx["user"]["id"]
        assert "logo_base64" in data

    def test_put_company_saves_logo(self, session, auth_headers):
        payload = {
            "company_name": "TEST Empresa",
            "cnpj": "12.345.678/0001-99",
            "phone": "11999990000",
            "email": "empresa@test.com",
            "address": "Rua Teste, 123",
            "logo_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==",
        }
        r = session.put(f"{API}/company", headers=auth_headers, json=payload, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["company_name"] == "TEST Empresa"
        assert data["logo_base64"].startswith("data:image/png;base64,")

        # GET to verify persistence
        r2 = session.get(f"{API}/company", headers=auth_headers, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["company_name"] == "TEST Empresa"


# ---------- Proposals ----------
@pytest.fixture(scope="module")
def proposal_store():
    return {}


class TestProposals:
    def test_create_proposal(self, session, auth_headers, proposal_store):
        payload = {
            "client_name": "TEST Cliente A",
            "client_document": "111.222.333-44",
            "client_phone": "11988887777",
            "products": [
                {"name": "Parafuso", "quantity": 10, "price": 2.5},
                {"name": "Porca", "quantity": 5, "price": 1.0},
            ],
            "shipping_deadline": "2026-02-15",
            "notes": "Entregar cedo",
        }
        r = session.post(f"{API}/proposals", headers=auth_headers, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "aberto"
        assert data["total"] == 30.0  # 10*2.5 + 5*1
        assert data["client_name"] == "TEST Cliente A"
        assert "id" in data
        proposal_store["p1"] = data["id"]

    def test_create_second_proposal(self, session, auth_headers, proposal_store):
        payload = {
            "client_name": "TEST Cliente B",
            "client_document": "222.333.444-55",
            "client_phone": "11977776666",
            "products": [{"name": "Item X", "quantity": 2, "price": 50.0}],
            "shipping_deadline": "2026-03-01",
            "notes": "",
        }
        r = session.post(f"{API}/proposals", headers=auth_headers, json=payload, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 100.0
        proposal_store["p2"] = data["id"]

    def test_list_proposals(self, session, auth_headers, proposal_store):
        r = session.get(f"{API}/proposals", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        items = r.json()
        ids = [p["id"] for p in items]
        assert proposal_store["p1"] in ids
        assert proposal_store["p2"] in ids

    def test_list_filter_by_status_aberto(self, session, auth_headers, proposal_store):
        r = session.get(f"{API}/proposals?status=aberto", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 2
        assert all(p["status"] == "aberto" for p in items)

    def test_get_single_proposal(self, session, auth_headers, proposal_store):
        pid = proposal_store["p1"]
        r = session.get(f"{API}/proposals/{pid}", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["id"] == pid

    def test_get_unknown_proposal_returns_404(self, session, auth_headers):
        r = session.get(f"{API}/proposals/nonexistent-id", headers=auth_headers, timeout=30)
        assert r.status_code == 404

    def test_status_to_realizado(self, session, auth_headers, proposal_store):
        pid = proposal_store["p1"]
        r = session.patch(f"{API}/proposals/{pid}/status", headers=auth_headers,
                          json={"status": "realizado"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "aprovado"
        # Verify via GET
        r2 = session.get(f"{API}/proposals/{pid}", headers=auth_headers, timeout=30)
        assert r2.json()["status"] == "aprovado"

    def test_status_to_perdido_without_reason_400(self, session, auth_headers, proposal_store):
        pid = proposal_store["p2"]
        r = session.patch(f"{API}/proposals/{pid}/status", headers=auth_headers,
                          json={"status": "perdido"}, timeout=30)
        assert r.status_code == 400

    def test_status_to_perdido_with_reason(self, session, auth_headers, proposal_store):
        pid = proposal_store["p2"]
        r = session.patch(f"{API}/proposals/{pid}/status", headers=auth_headers,
                          json={"status": "perdido", "lost_reason": "Preço alto"}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "perdido"
        assert data["lost_reason"] == "Preço alto"


# ---------- Stats ----------
class TestStats:
    def test_stats_counters(self, session, auth_headers):
        r = session.get(f"{API}/stats", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        for k in ("open_count", "won_count", "lost_count", "open_value", "month_won_value", "stale_count"):
            assert k in data
        assert data["won_count"] >= 1
        assert data["lost_count"] >= 1
        assert data["month_won_value"] >= 30.0  # p1 total


# ---------- Clients ----------
class TestClients:
    def test_clients_aggregate(self, session, auth_headers):
        r = session.get(f"{API}/clients", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 2
        docs = [c["client_document"] for c in items]
        assert "111.222.333-44" in docs
        # Check aggregated fields
        for c in items:
            assert "proposals_count" in c
            assert "total_value" in c


# ---------- Delete (cleanup) ----------
class TestDelete:
    def test_delete_proposal(self, session, auth_headers, proposal_store):
        pid = proposal_store["p1"]
        r = session.delete(f"{API}/proposals/{pid}", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        # Verify 404 after delete
        r2 = session.get(f"{API}/proposals/{pid}", headers=auth_headers, timeout=30)
        assert r2.status_code == 404

    def test_delete_unknown_returns_404(self, session, auth_headers):
        r = session.delete(f"{API}/proposals/does-not-exist", headers=auth_headers, timeout=30)
        assert r.status_code == 404

    def test_cleanup_second_proposal(self, session, auth_headers, proposal_store):
        pid = proposal_store["p2"]
        r = session.delete(f"{API}/proposals/{pid}", headers=auth_headers, timeout=30)
        assert r.status_code == 200
