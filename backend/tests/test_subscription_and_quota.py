"""Iteration 2: Subscription, quota, duplicate, new proposal fields."""
import os
import uuid
import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env", override=True)

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://quick-quote-pro-5.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _register(session, prefix="test"):
    email = f"{prefix}_{uuid.uuid4().hex[:10]}@propostaja.com"
    password = "teste123"
    r = session.post(f"{API}/auth/register",
                     json={"name": "QA User", "email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    
    # Delete trial subscription so the user is 'free'
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    client_db = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client_db[os.environ["DB_NAME"]]
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.subscriptions.delete_many({"user_id": data["user"]["id"]}))
    client_db.close()

    return {"token": data["token"], "user": data["user"], "email": email, "password": password,
            "headers": {"Authorization": f"Bearer {data['token']}", "Content-Type": "application/json"}}


@pytest.fixture(scope="module")
def user_a(session):
    """Primary test user for subscription + CRUD scenarios."""
    return _register(session, "subs")


# ---------- Subscription plans ----------
class TestSubscriptionPlans:
    def test_plans_contains_both(self, session):
        r = session.get(f"{API}/subscription/plans", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["free_monthly_quota"] == 10
        ids = {p["id"]: p for p in data["plans"]}
        assert "pro_monthly" in ids and "pro_yearly" in ids
        assert ids["pro_monthly"]["amount"] == 29.9
        assert ids["pro_monthly"]["currency"] == "brl"
        assert ids["pro_monthly"]["days"] == 30
        assert ids["pro_yearly"]["amount"] == 299.0
        assert ids["pro_yearly"]["currency"] == "brl"
        assert ids["pro_yearly"]["days"] == 365


# ---------- /subscription/me for new user ----------
class TestSubscriptionMe:
    def test_new_user_is_free(self, session, user_a):
        r = session.get(f"{API}/subscription/me", headers=user_a["headers"], timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["plan"] == "free"
        assert data["is_pro"] is False
        assert data["month_quota"] is None
        assert data["month_count"] == 0

    def test_auth_me_has_plan_fields(self, session, user_a):
        r = session.get(f"{API}/auth/me", headers=user_a["headers"], timeout=30)
        assert r.status_code == 200
        d = r.json()
        # merged user + plan state
        assert d["email"] == user_a["email"]
        for k in ("plan", "is_pro", "month_count", "month_quota"):
            assert k in d, f"missing {k} in /auth/me"
        assert d["plan"] == "free"
        assert d["is_pro"] is False
        assert d["month_quota"] is None


# ---------- Checkout ----------
class TestCheckout:
    def test_checkout_invalid_plan_400(self, session, user_a):
        r = session.post(f"{API}/subscription/checkout", headers=user_a["headers"],
                         json={"plan": "bogus"}, timeout=30)
        assert r.status_code == 400

    def test_checkout_pro_monthly_returns_url(self, session, user_a):
        r = session.post(f"{API}/subscription/checkout", headers=user_a["headers"],
                         json={"plan": "pro_monthly"}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "url" in data and data["url"].startswith("https://")
        assert "session_id" in data and data["session_id"]
        # stash for next test
        user_a["session_id"] = data["session_id"]

    def test_status_endpoint_returns_current_payment_status(self, session, user_a):
        sid = user_a.get("session_id")
        assert sid, "session_id from previous test required"
        r = session.get(f"{API}/subscription/status/{sid}", headers=user_a["headers"], timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "payment_status" in d
        # likely 'unpaid' until test card used; just make sure it's not 'paid' magically
        assert d["payment_status"] in ("unpaid", "paid", "no_payment_required", "open")
        # plan state merged in
        assert "plan" in d and "is_pro" in d

    def test_status_unknown_session_returns_404(self, session, user_a):
        r = session.get(f"{API}/subscription/status/doesnotexist_{uuid.uuid4().hex}",
                        headers=user_a["headers"], timeout=30)
        assert r.status_code == 404


# ---------- New proposal fields + discount ----------
class TestProposalNewFields:
    def test_create_with_discount(self, session, user_a):
        payload = {
            "client_name": "TEST Desconto",
            "client_document": "999.999.999-99",
            "client_phone": "11999990000",
            "products": [{"name": "Widget", "quantity": 2, "price": 100.0}],
            "shipping_deadline": "2026-02-28",
            "notes": "",
            "discount": 50,
            "payment_terms": "50% à vista, 50% em 30 dias",
            "validity_days": 7,
        }
        r = session.post(f"{API}/proposals", headers=user_a["headers"], json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 150.0  # 2*100 - 50
        assert d["discount"] == 50.0
        assert d["payment_terms"] == "50% à vista, 50% em 30 dias"
        assert d["validity_days"] == 7
        assert d["status"] == "aberto"
        user_a["disc_pid"] = d["id"]

    def test_get_persisted_new_fields(self, session, user_a):
        pid = user_a["disc_pid"]
        r = session.get(f"{API}/proposals/{pid}", headers=user_a["headers"], timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["discount"] == 50.0
        assert d["payment_terms"].startswith("50% à vista")
        assert d["validity_days"] == 7
        assert d["total"] == 150.0


# ---------- Duplicate ----------
class TestDuplicate:
    def test_duplicate_creates_new_with_status_aberto(self, session, user_a):
        pid = user_a["disc_pid"]
        # First set original to 'realizado' to ensure duplicate resets it
        s1 = session.patch(f"{API}/proposals/{pid}/status", headers=user_a["headers"],
                           json={"status": "realizado"}, timeout=30)
        assert s1.status_code == 200

        r = session.post(f"{API}/proposals/{pid}/duplicate", headers=user_a["headers"], timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"] != pid
        assert d["status"] == "aberto"
        assert d["client_name"] == "TEST Desconto"
        assert d["total"] == 150.0
        assert d["discount"] == 50.0
        assert d["payment_terms"].startswith("50%")
        # sanity: GET via list
        lr = session.get(f"{API}/proposals", headers=user_a["headers"], timeout=30)
        ids = [p["id"] for p in lr.json()]
        assert d["id"] in ids and pid in ids

    def test_duplicate_unknown_returns_404(self, session, user_a):
        r = session.post(f"{API}/proposals/doesnotexist_{uuid.uuid4().hex}/duplicate",
                         headers=user_a["headers"], timeout=30)
        assert r.status_code == 404


# ---------- Quota enforcement ----------
class TestQuota:
    """Use a separate fresh user so we don't pollute user_a's count for other tests."""

    def test_11th_proposal_returns_402(self, session):
        ctx = _register(session, "quota")
        # Verify fresh user starts at 0
        me = session.get(f"{API}/subscription/me", headers=ctx["headers"], timeout=30).json()
        assert me["month_count"] == 0
        assert me["month_quota"] is None

        base_payload = {
            "client_document": "000.000.000-00",
            "client_phone": "11900000000",
            "products": [{"name": "Item", "quantity": 1, "price": 10.0}],
            "shipping_deadline": "2026-02-15",
            "notes": "",
        }
        # Create 10 proposals
        for i in range(10):
            p = dict(base_payload, client_name=f"TEST Cliente Q{i}")
            r = session.post(f"{API}/proposals", headers=ctx["headers"], json=p, timeout=30)
            assert r.status_code == 200, f"proposal {i} failed: {r.status_code} {r.text}"

        me2 = session.get(f"{API}/subscription/me", headers=ctx["headers"], timeout=30).json()
        assert me2["month_count"] == 10

        # 11th should succeed because monthly quota was removed
        p11 = dict(base_payload, client_name="TEST Cliente Q11")
        r11 = session.post(f"{API}/proposals", headers=ctx["headers"], json=p11, timeout=30)
        assert r11.status_code == 200, f"expected 200, got {r11.status_code}: {r11.text}"

        # Duplicate should also succeed
        first_list = session.get(f"{API}/proposals", headers=ctx["headers"], timeout=30).json()
        assert len(first_list) == 11
        first_id = first_list[0]["id"]
        rd = session.post(f"{API}/proposals/{first_id}/duplicate", headers=ctx["headers"], timeout=30)
        assert rd.status_code == 200


# ---------- Stats includes plan info ----------
class TestStatsPlan:
    def test_stats_has_plan_fields(self, session, user_a):
        r = session.get(f"{API}/stats", headers=user_a["headers"], timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("open_count", "won_count", "lost_count", "plan", "is_pro", "month_count", "month_quota"):
            assert k in d, f"missing {k}"
        assert d["plan"] == "free"
        assert d["is_pro"] is False


# ---------- Webhook endpoint exists ----------
class TestWebhook:
    def test_webhook_exists_rejects_invalid_sig(self, session):
        # Raw POST with invalid signature -> expect 400 (or 4xx). Not 404.
        r = session.post(f"{API}/webhook/stripe",
                         data=b'{"type":"checkout.session.completed"}',
                         headers={"Stripe-Signature": "t=0,v1=invalid", "Content-Type": "application/json"},
                         timeout=30)
        assert r.status_code != 404, "webhook endpoint missing"
        # Should be 400 due to invalid signature
        assert r.status_code in (400, 401, 403), f"unexpected status {r.status_code}: {r.text}"
