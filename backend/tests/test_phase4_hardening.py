import pytest
import asyncio
import os
import uuid
import requests
from datetime import datetime, timezone, timedelta
from server import db, create_access_token, hash_password

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api"

def test_phase4_hardening_and_security():
    loop = asyncio.get_event_loop()
    
    # 1. Setup company and users
    company_id = f"company-hard-{uuid.uuid4().hex[:6]}"
    
    master_id = f"master-hard-{uuid.uuid4().hex[:6]}"
    master_email = f"master_{master_id}@test.com"
    
    admin_id = f"admin-hard-{uuid.uuid4().hex[:6]}"
    admin_email = f"admin_{admin_id}@test.com"
    
    seller_id = f"seller-hard-{uuid.uuid4().hex[:6]}"
    seller_email = f"seller_{seller_id}@test.com"
    
    # Insert users
    users = [
        {
            "id": master_id,
            "company_id": company_id,
            "email": master_email,
            "name": "Master Owner",
            "password_hash": hash_password("teste123"),
            "role": "owner",
            "is_master": True,
            "active": True,
            "deleted": False
        },
        {
            "id": admin_id,
            "company_id": company_id,
            "email": admin_email,
            "name": "Admin User",
            "password_hash": hash_password("teste123"),
            "role": "admin",
            "active": True,
            "deleted": False
        },
        {
            "id": seller_id,
            "company_id": company_id,
            "email": seller_email,
            "name": "Seller User",
            "password_hash": hash_password("teste123"),
            "role": "seller",
            "active": True,
            "deleted": False
        }
    ]
    loop.run_until_complete(db.users.insert_many(users))
    
    # Tokens
    master_session = str(uuid.uuid4())
    admin_session = str(uuid.uuid4())
    seller_session = str(uuid.uuid4())
    
    loop.run_until_complete(db.users.update_one({"id": master_id}, {"$set": {"session_id": master_session}}))
    loop.run_until_complete(db.users.update_one({"id": admin_id}, {"$set": {"session_id": admin_session}}))
    loop.run_until_complete(db.users.update_one({"id": seller_id}, {"$set": {"session_id": seller_session}}))
    
    master_token = create_access_token(master_id, master_email, session_id=master_session)
    admin_token = create_access_token(admin_id, admin_email, session_id=admin_session)
    seller_token = create_access_token(seller_id, seller_email, session_id=seller_session)
    
    headers_master = {"Authorization": f"Bearer {master_token}"}
    headers_admin = {"Authorization": f"Bearer {admin_token}"}
    headers_seller = {"Authorization": f"Bearer {seller_token}"}
    
    try:
        # -------------------------------------------------------------
        # 2. TEST SYSTEM MONITORING & INFO
        # -------------------------------------------------------------
        # Health (public)
        r_health = requests.get(f"{API}/health")
        assert r_health.status_code == 200
        health_data = r_health.json()
        assert health_data["status"] == "healthy"
        assert health_data["database"] == "connected"
        
        # Metrics (requires owner role)
        r_metrics = requests.get(f"{API}/metrics", headers=headers_master)
        assert r_metrics.status_code == 200
        metrics_data = r_metrics.json()
        assert metrics_data["success"] is True
        assert "users_count" in metrics_data["data"]
        
        # metrics unauthorized
        r_metrics_bad = requests.get(f"{API}/metrics", headers=headers_seller)
        assert r_metrics_bad.status_code == 403
        
        # Backup-info (requires admin)
        r_backup = requests.get(f"{API}/admin/backup-info", headers=headers_admin)
        assert r_backup.status_code == 200
        backup_data = r_backup.json()
        assert backup_data["success"] is True
        assert "last_backup_simulation" in backup_data["data"]
        
        # Public plans & features
        r_plans = requests.get(f"{API}/public/plans")
        assert r_plans.status_code == 200
        plans_data = r_plans.json()
        assert plans_data["success"] is True
        
        r_features = requests.get(f"{API}/public/features")
        assert r_features.status_code == 200
        features_data = r_features.json()
        assert features_data["success"] is True
        
        # -------------------------------------------------------------
        # 3. TEST RATE LIMITS (Login / Register / Recover)
        # -------------------------------------------------------------
        # We can clean rate limits collection first
        loop.run_until_complete(db.rate_limits.delete_many({}))
        
        # Call login multiple times (limit is 5 per minute)
        login_payload = {"email": "nonexistent@test.com", "password": "wrongpassword"}
        for i in range(5):
            requests.post(f"{API}/auth/login", json=login_payload)
            
        r_limit_triggered = requests.post(f"{API}/auth/login", json=login_payload)
        assert r_limit_triggered.status_code == 429
        
        # Check standard exception middleware format on 429 error
        limit_err = r_limit_triggered.json()
        assert limit_err["success"] is False
        assert "Muitas tentativas" in limit_err["message"]
        
        # Clean limits again
        loop.run_until_complete(db.rate_limits.delete_many({}))
        
        # -------------------------------------------------------------
        # 4. TEST SESSIONS & LOGOUT
        # -------------------------------------------------------------
        # Call an authenticated endpoint
        r_me_valid = requests.get(f"{API}/auth/me", headers=headers_seller)
        assert r_me_valid.status_code == 200
        
        # Logout seller
        r_logout = requests.post(f"{API}/auth/logout", headers=headers_seller)
        assert r_logout.status_code == 200
        logout_data = r_logout.json()
        assert logout_data["success"] is True
        
        # Try auth/me again (should be rejected since session_id is now None in DB)
        r_me_invalid = requests.get(f"{API}/auth/me", headers=headers_seller)
        assert r_me_invalid.status_code == 401
        
        # check audit log contains logout
        last_logout_log = loop.run_until_complete(db.audit_logs.find_one({"action": "logout", "user_id": seller_id}))
        assert last_logout_log is not None
        assert last_logout_log["entity_type"] == "auth"
        
        # -------------------------------------------------------------
        # 5. TEST RECOVERY & VERIFICATION FLOWS
        # -------------------------------------------------------------
        # Forgot password (non existent - standard success return)
        r_forgot = requests.post(f"{API}/auth/forgot-password", json={"email": "nobody@test.com"})
        assert r_forgot.status_code == 200
        assert r_forgot.json()["success"] is True
        
        # Forgot password (existent)
        r_forgot_ex = requests.post(f"{API}/auth/forgot-password", json={"email": admin_email})
        assert r_forgot_ex.status_code == 200
        assert r_forgot_ex.json()["success"] is True
        
        admin_db = loop.run_until_complete(db.users.find_one({"id": admin_id}))
        assert admin_db.get("reset_token") is not None
        assert admin_db.get("reset_token_expires_at") is not None
        
        # Reset password
        reset_token = admin_db["reset_token"]
        r_reset = requests.post(f"{API}/auth/reset-password", json={"token": reset_token, "new_password": "newpassword123"})
        assert r_reset.status_code == 200
        assert r_reset.json()["success"] is True
        
        # Token cleared
        admin_db_after = loop.run_until_complete(db.users.find_one({"id": admin_id}))
        assert admin_db_after.get("reset_token") is None
        
        # Verify password updated by logging in
        r_login_new = requests.post(f"{API}/auth/login", json={"email": admin_email, "password": "newpassword123"})
        assert r_login_new.status_code == 200
        admin_token = r_login_new.json()["token"]
        headers_admin = {"Authorization": f"Bearer {admin_token}"}
        
        # Verification Flow: send-verification
        r_send_ver = requests.post(f"{API}/auth/send-verification", json={"email": admin_email})
        assert r_send_ver.status_code == 200
        assert r_send_ver.json()["success"] is True
        
        admin_db_ver = loop.run_until_complete(db.users.find_one({"id": admin_id}))
        assert admin_db_ver.get("verification_token") is not None
        
        # verify email
        ver_token = admin_db_ver["verification_token"]
        r_verify = requests.post(f"{API}/auth/verify-email", json={"token": ver_token})
        assert r_verify.status_code == 200
        assert r_verify.json()["success"] is True
        
        admin_db_ver_after = loop.run_until_complete(db.users.find_one({"id": admin_id}))
        assert admin_db_ver_after.get("verified_email") is True
        assert admin_db_ver_after.get("verification_token") is None
        
        # -------------------------------------------------------------
        # 6. TEST SUPPORT MODE (IMPERSONATE)
        # -------------------------------------------------------------
        # Impersonate seller using admin account (should fail - only master owner is allowed)
        r_imp_bad = requests.get(f"{API}/admin/impersonate/{seller_id}", headers=headers_admin)
        assert r_imp_bad.status_code == 403
        
        # Impersonate seller using master owner
        r_imp_good = requests.get(f"{API}/admin/impersonate/{seller_id}", headers=headers_master)
        assert r_imp_good.status_code == 200
        imp_data = r_imp_good.json()
        assert imp_data["success"] is True
        assert "token" in imp_data["data"]
        assert imp_data["data"]["user"]["id"] == seller_id
        
        # check audit log has impersonation
        imp_log = loop.run_until_complete(db.audit_logs.find_one({"action": "impersonate", "user_id": master_id}))
        assert imp_log is not None
        assert imp_log["user_id"] == master_id
        assert imp_log["new_value"]["impersonated_user_id"] == seller_id
        
        # -------------------------------------------------------------
        # 7. TEST SOFT DELETE & AUDIT LOGGING FOR OTHER ENTITIES
        # -------------------------------------------------------------
        # Insert a product for soft delete test
        prod_id = f"prod-del-{uuid.uuid4().hex[:6]}"
        product = {
            "id": prod_id,
            "company_id": company_id,
            "code": "CODE-DEL",
            "name": "To Delete",
            "price": 10.0,
            "unit": "UN",
            "active": True,
            "deleted": False
        }
        loop.run_until_complete(db.products.insert_one(product))
        
        # Get product list
        r_prod_list_before = requests.get(f"{API}/products", headers=headers_master)
        assert any(p["id"] == prod_id for p in r_prod_list_before.json())
        
        # Delete product
        r_del_prod = requests.delete(f"{API}/products/{prod_id}", headers=headers_admin)
        assert r_del_prod.status_code == 200
        
        # Get product (should be 404 now)
        r_prod_after = requests.get(f"{API}/products/{prod_id}", headers=headers_master)
        assert r_prod_after.status_code == 404
        
        # List products (should be empty/no del product)
        r_prod_list_after = requests.get(f"{API}/products", headers=headers_master)
        assert not any(p["id"] == prod_id for p in r_prod_list_after.json())
        
        # Check database: still physically exists with deleted=True
        prod_in_db = loop.run_until_complete(db.products.find_one({"id": prod_id}))
        assert prod_in_db is not None
        assert prod_in_db["deleted"] is True
        assert prod_in_db["deleted_by"] == admin_id
        
        # Check audit log for product deletion
        prod_del_log = loop.run_until_complete(db.audit_logs.find_one({"action": "delete", "entity_type": "product", "entity_id": prod_id}))
        assert prod_del_log is not None
        assert prod_del_log["old_value"]["code"] == "CODE-DEL"
        
        # Create a client dynamically via proposal creation
        proposal_payload = {
            "client_name": "CRM Client",
            "client_document": "222.222.222-22",
            "client_phone": "(11) 92222-2222",
            "products": [
                {"name": "Manual Item 1", "unit_price": 50.0, "quantity": 1.0}
            ],
            "shipping_deadline": "5 dias",
            "discount": 0.0
        }
        r_prop_create = requests.post(f"{API}/proposals", json=proposal_payload, headers=headers_master)
        assert r_prop_create.status_code == 200
        prop_data = r_prop_create.json()
        client_id = prop_data["client_id"]
        prop_id = prop_data["id"]
        
        # List clients history
        r_clients = requests.get(f"{API}/clients", headers=headers_master)
        assert any(c["client_id"] == client_id for c in r_clients.json())
        
        # Soft delete client
        r_del_client = requests.delete(f"{API}/clients/{client_id}", headers=headers_master)
        assert r_del_client.status_code == 200
        
        # Client history should return 404
        r_client_hist_after = requests.get(f"{API}/clients/{client_id}/history", headers=headers_master)
        assert r_client_hist_after.status_code == 404
        
        # Client list should exclude soft deleted clients
        r_clients_after = requests.get(f"{API}/clients", headers=headers_master)
        assert not any(c["client_id"] == client_id for c in r_clients_after.json())
        
        # Soft delete proposal
        r_del_prop = requests.delete(f"{API}/proposals/{prop_id}", headers=headers_master)
        assert r_del_prop.status_code == 200
        
        # Retrieve proposal (should return 404)
        r_prop_get = requests.get(f"{API}/proposals/{prop_id}", headers=headers_master)
        assert r_prop_get.status_code == 404
        
        # Create another proposal with same client document -> should undelete client!
        r_prop_create2 = requests.post(f"{API}/proposals", json=proposal_payload, headers=headers_master)
        assert r_prop_create2.status_code == 200
        assert r_prop_create2.json()["client_id"] == client_id
        
        client_in_db_reactivated = loop.run_until_complete(db.clients.find_one({"id": client_id}))
        assert client_in_db_reactivated["deleted"] is False
        
        # Soft delete user
        # Add seller to delete
        user_to_del_id = f"user-del-{uuid.uuid4().hex[:6]}"
        user_to_del = {
            "id": user_to_del_id,
            "company_id": company_id,
            "email": f"{user_to_del_id}@test.com",
            "name": "User To Delete",
            "password_hash": hash_password("teste123"),
            "role": "seller",
            "active": True,
            "deleted": False
        }
        loop.run_until_complete(db.users.insert_one(user_to_del))
        
        r_del_user = requests.delete(f"{API}/users/{user_to_del_id}", headers=headers_admin)
        assert r_del_user.status_code == 200
        
        # Verify in DB
        deleted_user_db = loop.run_until_complete(db.users.find_one({"id": user_to_del_id}))
        assert deleted_user_db["deleted"] is True
        assert deleted_user_db["active"] is False
        assert deleted_user_db["deleted_by"] == admin_id
        
        # -------------------------------------------------------------
        # 8. TEST LGPD ENDPOINTS
        # -------------------------------------------------------------
        # Export data
        r_export = requests.get(f"{API}/account/export", headers=headers_master)
        assert r_export.status_code == 200
        export_json = r_export.json()
        assert export_json["success"] is True
        assert "proposals" in export_json["data"]
        
        # Delete account
        r_lgpd_del = requests.delete(f"{API}/account", headers=headers_master)
        assert r_lgpd_del.status_code == 200
        
        # Check company data completely physical deleted
        comp_check = loop.run_until_complete(db.companies.find_one({"id": company_id}))
        assert comp_check is None
        
        user_check = loop.run_until_complete(db.users.find_one({"company_id": company_id}))
        assert user_check is None
        
    finally:
        # Cleanup remaining test company data if any
        loop.run_until_complete(db.users.delete_many({"company_id": company_id}))
        loop.run_until_complete(db.companies.delete_many({"id": company_id}))
        loop.run_until_complete(db.products.delete_many({"company_id": company_id}))
        loop.run_until_complete(db.proposals.delete_many({"company_id": company_id}))
        loop.run_until_complete(db.clients.delete_many({"company_id": company_id}))
        loop.run_until_complete(db.subscriptions.delete_many({"company_id": company_id}))
        loop.run_until_complete(db.subscriptions.delete_many({"user_id": {"$in": [master_id, admin_id, seller_id]}}))
