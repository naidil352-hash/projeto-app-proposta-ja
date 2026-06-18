import pytest
import asyncio
import os
import uuid
import requests
from datetime import datetime, timezone, timedelta
from server import db, create_access_token

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api"

def test_phase3c_crm_and_pipeline():
    loop = asyncio.get_event_loop()
    
    # 10. Multi-company isolation data setup
    company_a = f"comp-crm-a-{uuid.uuid4().hex[:6]}"
    company_b = f"comp-crm-b-{uuid.uuid4().hex[:6]}"
    
    owner_a_id = f"owner-crm-a-{uuid.uuid4().hex[:6]}"
    owner_b_id = f"owner-crm-b-{uuid.uuid4().hex[:6]}"
    
    email_a = f"{owner_a_id}@test.com"
    email_b = f"{owner_b_id}@test.com"
    
    users = [
        {"id": owner_a_id, "email": email_a, "name": "Seller A", "company_id": company_a, "role": "owner", "active": True},
        {"id": owner_b_id, "email": email_b, "name": "Seller B", "company_id": company_b, "role": "owner", "active": True}
    ]
    
    tokens = {
        "user_a": create_access_token(owner_a_id, email_a),
        "user_b": create_access_token(owner_b_id, email_b)
    }
    
    # Insert users
    loop.run_until_complete(db.users.insert_many(users))
    
    # 12. Setup active catalog product for Company A
    prod_a_id = f"prod-a-{uuid.uuid4().hex[:6]}"
    prod_a = {
        "id": prod_a_id,
        "company_id": company_a,
        "code": "CAT-A",
        "name": "Super Product A",
        "description": "Desc A",
        "price": 100.0,
        "unit": "UN",
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    loop.run_until_complete(db.products.insert_one(prod_a))
    
    headers_a = {"Authorization": f"Bearer {tokens['user_a']}"}
    headers_b = {"Authorization": f"Bearer {tokens['user_b']}"}
    
    try:
        # Scenario 1: Automatic client creation
        proposal_payload = {
            "client_name": "Client A",
            "client_document": "111.111.111-11",
            "client_phone": "(11) 91111-1111",
            "products": [
                {"product_id": prod_a_id, "quantity": 2.0}
            ],
            "shipping_deadline": "5 dias",
            "discount": 10.0,
            "payment_terms": "Pix",
            "validity_days": 10
        }
        
        # Post new proposal for Company A
        r = requests.post(f"{API}/proposals", json=proposal_payload, headers=headers_a)
        assert r.status_code == 200, r.text
        prop_a1 = r.json()
        
        # Verify client_id exists in proposal
        client_id_a1 = prop_a1.get("client_id")
        assert client_id_a1 is not None
        assert client_id_a1.startswith("cli_")
        
        # Verify client is created in clients collection
        client_in_db = loop.run_until_complete(db.clients.find_one({"id": client_id_a1}))
        assert client_in_db is not None
        assert client_in_db["company_id"] == company_a
        assert client_in_db["document"] == "111.111.111-11"
        assert client_in_db["name"] == "Client A"
        assert client_in_db["phone"] == "(11) 91111-1111"
        
        # Verify item type defaults to catalog
        assert prop_a1["products"][0]["item_type"] == "catalog"
        
        # Verify status_updated_at is populated
        assert prop_a1.get("status_updated_at") is not None
        
        # Scenario 2: Reusing client
        proposal_payload_2 = {
            "client_name": "Client A Changed Name",
            "client_document": "111.111.111-11",
            "client_phone": "(11) 92222-2222",
            "products": [
                {"name": "Manual Item 1", "unit_price": 50.0, "quantity": 4.0}
            ],
            "shipping_deadline": "5 dias",
            "discount": 0.0
        }
        
        r2 = requests.post(f"{API}/proposals", json=proposal_payload_2, headers=headers_a)
        assert r2.status_code == 200
        prop_a2 = r2.json()
        
        # Should reuse same client_id
        assert prop_a2.get("client_id") == client_id_a1
        
        # Verify item type manual is stored
        assert prop_a2["products"][0]["item_type"] == "manual"
        
        # Scenario 10: Multi-company isolation for clients
        # Company B creates proposal with same client document
        r3 = requests.post(f"{API}/proposals", json=proposal_payload, headers=headers_b)
        assert r3.status_code == 404 # Prod A doesn't belong to company B
        
        # Try manual product for Company B
        proposal_payload_b = dict(proposal_payload)
        proposal_payload_b["products"] = [{"name": "Manual Item B", "unit_price": 200.0, "quantity": 1.0}]
        r4 = requests.post(f"{API}/proposals", json=proposal_payload_b, headers=headers_b)
        assert r4.status_code == 200
        prop_b1 = r4.json()
        client_id_b1 = prop_b1.get("client_id")
        assert client_id_b1 != client_id_a1 # Client IDs must be isolated
        
        client_b_db = loop.run_until_complete(db.clients.find_one({"id": client_id_b1}))
        assert client_b_db["company_id"] == company_b
        
        # Scenario 4: Pipeline complete & status transitions
        # prop_a1 has status "aberto"
        pid_a1 = prop_a1["id"]
        
        # Transitions check:
        # aberto -> qualificado (Allowed)
        r_trans = requests.patch(f"{API}/proposals/{pid_a1}/status", json={"status": "qualificado"}, headers=headers_a)
        assert r_trans.status_code == 200
        prop_a1_updated = r_trans.json()
        assert prop_a1_updated["status"] == "qualificado"
        assert prop_a1_updated["status_updated_at"] != prop_a1["status_updated_at"]
        
        # qualificado -> aberto (Blocked)
        r_blocked = requests.patch(f"{API}/proposals/{pid_a1}/status", json={"status": "aberto"}, headers=headers_a)
        assert r_blocked.status_code == 400
        
        # qualificado -> negociacao (Allowed)
        r_trans2 = requests.patch(f"{API}/proposals/{pid_a1}/status", json={"status": "negociacao"}, headers=headers_a)
        assert r_trans2.status_code == 200
        
        # negociacao -> aprovado (Allowed)
        r_trans3 = requests.patch(f"{API}/proposals/{pid_a1}/status", json={"status": "aprovado"}, headers=headers_a)
        assert r_trans3.status_code == 200
        assert r_trans3.json()["status"] == "aprovado"
        
        # Scenario 5 & 15: Manual item type conversion
        pid_a2 = prop_a2["id"]
        # Index 0 is manual item
        r_conv = requests.post(f"{API}/proposals/{pid_a2}/items/0/convert", headers=headers_a)
        assert r_conv.status_code == 200
        new_prod = r_conv.json()
        assert new_prod["code"].startswith("PRD-")
        assert new_prod["name"] == "Manual Item 1"
        assert new_prod["price"] == 50.0
        assert new_prod["created_from_manual_item"] is True
        
        # Check proposal remains unchanged
        r_prop_check = requests.get(f"{API}/proposals/{pid_a2}", headers=headers_a)
        assert r_prop_check.status_code == 200
        assert r_prop_check.json()["products"][0]["product_id"] == ""
        
        # Scenario 6 & 7 & 8 & 9: Analytics and Stats
        # Company A has:
        # prop_a1: Approved (Aprovado), Total = 2.0 * 100.0 - 10.0 = 190.0
        # prop_a2: Open (Aberto), Total = 4.0 * 50.0 = 200.0
        # Let's change prop_a2's status to perdido via valid path:
        # aberto -> qualificado -> negociacao -> perdido
        requests.patch(f"{API}/proposals/{pid_a2}/status", json={"status": "qualificado"}, headers=headers_a)
        requests.patch(f"{API}/proposals/{pid_a2}/status", json={"status": "negociacao"}, headers=headers_a)
        r_lost = requests.patch(f"{API}/proposals/{pid_a2}/status", json={"status": "perdido", "lost_reason": "Preço alto"}, headers=headers_a)
        assert r_lost.status_code == 200
        
        # Get client history
        r_hist = requests.get(f"{API}/clients/{client_id_a1}/history", headers=headers_a)
        assert r_hist.status_code == 200
        hist = r_hist.json()
        assert hist["proposal_count"] == 2
        assert hist["open_count"] == 0
        assert hist["approved_count"] == 1
        assert hist["lost_count"] == 1
        assert hist["total_value"] == 390.0
        assert hist["won_value"] == 190.0
        assert hist["lost_value"] == 200.0
        assert hist["conversion_rate"] == 50.0
        
        # Scenario 10: Multi-company history check
        # Company B tries to access client history of A
        r_hist_b = requests.get(f"{API}/clients/{client_id_a1}/history", headers=headers_b)
        assert r_hist_b.status_code == 404
        
        # Get stats
        r_stats = requests.get(f"{API}/stats", headers=headers_a)
        assert r_stats.status_code == 200
        stats = r_stats.json()
        assert stats["total_revenue"] == 190.0
        assert stats["ticket_average"] == 190.0
        assert stats["clients_count"] == 1
        assert stats["clients_active"] == 1
        assert stats["clients_lost"] == 0
        assert stats["negotiation_count"] == 0
        
        # Get products analytics
        r_ap = requests.get(f"{API}/analytics/products", headers=headers_a)
        assert r_ap.status_code == 200
        ap = r_ap.json()
        assert len(ap) == 1
        assert ap[0]["name"] == "Super Product A"
        assert ap[0]["quantity_sold"] == 2.0
        assert ap[0]["revenue"] == 200.0
        assert ap[0]["proposal_count"] == 1
        
        # Get sellers analytics
        r_as = requests.get(f"{API}/analytics/sellers", headers=headers_a)
        assert r_as.status_code == 200
        as_res = r_as.json()
        assert len(as_res) == 1
        assert as_res[0]["seller_name"] == "Seller A"
        assert as_res[0]["proposal_count"] == 2
        assert as_res[0]["approved_count"] == 1
        assert as_res[0]["lost_count"] == 1
        assert as_res[0]["revenue"] == 190.0
        assert as_res[0]["conversion_rate"] == 50.0
        assert as_res[0]["ticket_average"] == 190.0
        
        # Scenario 11 & 13: Retroactivity & realizado -> aprovado normalization
        # Manual insert of legacy proposal with status "realizado" and no item_type/client_id
        legacy_pid = f"prop-legacy-{uuid.uuid4().hex[:6]}"
        legacy_doc = {
            "id": legacy_pid,
            "company_id": company_a,
            "user_id": owner_a_id,
            "seller_name": "Seller A",
            "client_name": "Legacy Client",
            "client_document": "999.999.999-99",
            "client_phone": "(11) 99999-9999",
            "products": [
                {
                    "product_id": prod_a_id,
                    "code": "CAT-A",
                    "name": "Super Product A",
                    "description": "Desc A",
                    "unit": "UN",
                    "quantity": 1.0,
                    "unit_price": 100.0,
                    "total": 100.0
                }
            ],
            "shipping_deadline": "5 dias",
            "discount": 0.0,
            "subtotal": 100.0,
            "grand_total": 100.0,
            "total": 100.0,
            "status": "realizado",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(), # Old date
            "updated_at": (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        }
        loop.run_until_complete(db.proposals.insert_one(legacy_doc))
        
        # Retrieve legacy proposal via GET list
        r_list = requests.get(f"{API}/proposals", headers=headers_a)
        assert r_list.status_code == 200
        proposals_list = r_list.json()
        legacy_retrieved = next(p for p in proposals_list if p["id"] == legacy_pid)
        
        # Status must be normalized to "aprovado"
        assert legacy_retrieved["status"] == "aprovado"
        # Item type must be defaulted to "catalog"
        assert legacy_retrieved["products"][0]["item_type"] == "catalog"
        # status_updated_at must fallback
        assert legacy_retrieved.get("status_updated_at") != ""
        
        # Check that GET proposals filtering by status=aprovado returns legacy proposal
        r_list_filtered = requests.get(f"{API}/proposals?status=aprovado", headers=headers_a)
        assert r_list_filtered.status_code == 200
        pids = [p["id"] for p in r_list_filtered.json()]
        assert legacy_pid in pids
        
        # Check stats recalculation with legacy client inactive for 200 days (180+ days)
        r_stats_leg = requests.get(f"{API}/stats", headers=headers_a)
        assert r_stats_leg.status_code == 200
        stats_leg = r_stats_leg.json()
        assert stats_leg["clients_count"] == 1 # Only 1 client in clients collection
        assert stats_leg["clients_active"] == 1 # Client A is active
        assert stats_leg["clients_lost"] == 1 # Legacy Client has no activity for 200 days
        assert stats_leg["total_revenue"] == 290.0 # 190 + 100
        assert stats_leg["ticket_average"] == 145.0 # 290 / 2
        
    finally:
        # Cleanup DB
        loop.run_until_complete(db.users.delete_many({"company_id": {"$in": [company_a, company_b]}}))
        loop.run_until_complete(db.products.delete_many({"company_id": {"$in": [company_a, company_b]}}))
        loop.run_until_complete(db.clients.delete_many({"company_id": {"$in": [company_a, company_b]}}))
        loop.run_until_complete(db.proposals.delete_many({"company_id": {"$in": [company_a, company_b]}}))
