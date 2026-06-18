import pytest
import asyncio
import os
import uuid
from datetime import datetime, timezone
from server import db, create_access_token

def test_critical_indexes_exist():
    loop = asyncio.get_event_loop()
    
    users_indexes = loop.run_until_complete(db.users.index_information())
    assert "id_1" in users_indexes
    assert users_indexes["id_1"].get("unique") is True
    
    companies_indexes = loop.run_until_complete(db.companies.index_information())
    assert "id_1" in companies_indexes
    assert companies_indexes["id_1"].get("unique") is True
    assert "user_id_1" in companies_indexes
    assert companies_indexes["user_id_1"].get("unique") is True
    
    subs_indexes = loop.run_until_complete(db.subscriptions.index_information())
    assert "company_id_1" in subs_indexes
    assert subs_indexes["company_id_1"].get("sparse") is True
    assert subs_indexes["company_id_1"].get("unique") is not True


def test_proposals_indexes_exist():
    loop = asyncio.get_event_loop()
    indexes = loop.run_until_complete(db.proposals.index_information())
    
    # 1. index id_1 exists and is unique
    assert "id_1" in indexes
    assert indexes["id_1"].get("unique") is True
    
    # 2. company_id_1_created_at_-1 exists and correct order
    name_company_created = "company_id_1_created_at_-1"
    assert name_company_created in indexes
    assert indexes[name_company_created]["key"] == [("company_id", 1), ("created_at", -1)]
    
    # 3. (company_id, user_id, status, created_at) index
    name_comp_user_stat_created = "company_id_1_user_id_1_status_1_created_at_-1"
    assert name_comp_user_stat_created in indexes
    assert indexes[name_comp_user_stat_created]["key"] == [
        ("company_id", 1),
        ("user_id", 1),
        ("status", 1),
        ("created_at", -1),
    ]
    
    # 4. (company_id, status, created_at) index
    name_comp_stat_created = "company_id_1_status_1_created_at_-1"
    assert name_comp_stat_created in indexes
    assert indexes[name_comp_stat_created]["key"] == [
        ("company_id", 1),
        ("status", 1),
        ("created_at", -1),
    ]
    
    # 5. (user_id, created_at) index
    name_user_created = "user_id_1_created_at_-1"
    assert name_user_created in indexes
    assert indexes[name_user_created]["key"] == [
        ("user_id", 1),
        ("created_at", -1),
    ]


def test_users_id_unique():
    loop = asyncio.get_event_loop()
    user_id = "test-dup-id"
    # Clean up first
    loop.run_until_complete(db.users.delete_many({"id": user_id}))
    
    # Insert first
    loop.run_until_complete(db.users.insert_one({
        "id": user_id,
        "email": "test-dup-1@test.com",
        "name": "Test User 1"
    }))
    
    # Insert second (should raise DuplicateKeyError)
    from pymongo.errors import DuplicateKeyError
    with pytest.raises(DuplicateKeyError):
        loop.run_until_complete(db.users.insert_one({
            "id": user_id,
            "email": "test-dup-2@test.com",
            "name": "Test User 2"
        }))
        
    # Clean up
    loop.run_until_complete(db.users.delete_many({"id": user_id}))


def test_subscriptions_company_id_sparse():
    loop = asyncio.get_event_loop()
    test_sub_ids = ["test-sub-1", "test-sub-2", "test-sub-3", "test-sub-4"]
    # Clean up first
    loop.run_until_complete(db.subscriptions.delete_many({"user_id": {"$in": test_sub_ids}}))
    
    # 1. Insert two documents without company_id (should succeed)
    loop.run_until_complete(db.subscriptions.insert_one({
        "user_id": "test-sub-1",
        "plan": "free"
    }))
    loop.run_until_complete(db.subscriptions.insert_one({
        "user_id": "test-sub-2",
        "plan": "free"
    }))
    
    # 2. Insert two documents with the same company_id (should succeed because sparse index is not unique)
    dup_company_id = "test-dup-company-id"
    loop.run_until_complete(db.subscriptions.insert_one({
        "user_id": "test-sub-3",
        "company_id": dup_company_id,
        "plan": "pro"
    }))
    loop.run_until_complete(db.subscriptions.insert_one({
        "user_id": "test-sub-4",
        "company_id": dup_company_id,
        "plan": "pro"
    }))
    
    # Verify both were inserted and can be queried
    count = loop.run_until_complete(db.subscriptions.count_documents({"company_id": dup_company_id}))
    assert count == 2
    
    # Clean up
    loop.run_until_complete(db.subscriptions.delete_many({"user_id": {"$in": test_sub_ids}}))


def test_stats_endpoint_behavior():
    import requests
    
    BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    API = f"{BASE_URL}/api"
    
    loop = asyncio.get_event_loop()
    
    # Generate unique IDs
    company_a = f"comp-a-{uuid.uuid4().hex[:6]}"
    company_b = f"comp-b-{uuid.uuid4().hex[:6]}"
    
    owner_a_id = f"owner-a-{uuid.uuid4().hex[:6]}"
    admin_a_id = f"admin-a-{uuid.uuid4().hex[:6]}"
    seller_a1_id = f"seller-a1-{uuid.uuid4().hex[:6]}"
    seller_a2_id = f"seller-a2-{uuid.uuid4().hex[:6]}"
    legacy_user_id = f"legacy-u-{uuid.uuid4().hex[:6]}"
    owner_b_id = f"owner-b-{uuid.uuid4().hex[:6]}"
    
    # Emails
    owner_a_email = f"{owner_a_id}@test.com"
    admin_a_email = f"{admin_a_id}@test.com"
    seller_a1_email = f"{seller_a1_id}@test.com"
    seller_a2_email = f"{seller_a2_id}@test.com"
    legacy_user_email = f"{legacy_user_id}@test.com"
    owner_b_email = f"{owner_b_id}@test.com"
    
    # Mock data setup (Users)
    users = [
        {"id": owner_a_id, "email": owner_a_email, "name": "Owner A", "company_id": company_a, "role": "owner", "active": True},
        {"id": admin_a_id, "email": admin_a_email, "name": "Admin A", "company_id": company_a, "role": "admin", "active": True},
        {"id": seller_a1_id, "email": seller_a1_email, "name": "Seller A1", "company_id": company_a, "role": "seller", "active": True},
        {"id": seller_a2_id, "email": seller_a2_email, "name": "Seller A2", "company_id": company_a, "role": "seller", "active": True},
        {"id": legacy_user_id, "email": legacy_user_email, "name": "Legacy Owner", "role": "owner", "active": True},
        {"id": owner_b_id, "email": owner_b_email, "name": "Owner B", "company_id": company_b, "role": "owner", "active": True}
    ]
    
    # Tokens
    tokens = {
        "owner_a": create_access_token(owner_a_id, owner_a_email),
        "admin_a": create_access_token(admin_a_id, admin_a_email),
        "seller_a1": create_access_token(seller_a1_id, seller_a1_email),
        "seller_a2": create_access_token(seller_a2_id, seller_a2_email),
        "legacy": create_access_token(legacy_user_id, legacy_user_email),
        "owner_b": create_access_token(owner_b_id, owner_b_email)
    }
    
    # Mock Proposals
    now_str = datetime.now(timezone.utc).isoformat()
    proposals = [
        {"id": f"p-a1-{uuid.uuid4().hex[:6]}", "company_id": company_a, "user_id": seller_a1_id, "status": "realizado", "total": 150.0, "created_at": now_str},
        {"id": f"p-a2-{uuid.uuid4().hex[:6]}", "company_id": company_a, "user_id": seller_a1_id, "status": "aberto", "total": 200.0, "created_at": now_str},
        {"id": f"p-a3-{uuid.uuid4().hex[:6]}", "company_id": company_a, "user_id": seller_a2_id, "status": "perdido", "total": 300.0, "created_at": now_str},
        {"id": f"p-leg-{uuid.uuid4().hex[:6]}", "user_id": legacy_user_id, "status": "realizado", "total": 500.0, "created_at": now_str},
        {"id": f"p-b1-{uuid.uuid4().hex[:6]}", "company_id": company_b, "user_id": owner_b_id, "status": "realizado", "total": 1000.0, "created_at": now_str}
    ]
    
    # DB Insert
    loop.run_until_complete(db.users.insert_many(users))
    loop.run_until_complete(db.proposals.insert_many(proposals))
    
    try:
        # Scenario 1 & 7 & 8 & 9 & 10: Seller A1 checks stats
        headers = {"Authorization": f"Bearer {tokens['seller_a1']}"}
        r = requests.get(f"{API}/stats", headers=headers)
        assert r.status_code == 200
        res = r.json()
        assert res["total_proposals"] == 2
        assert res["approved_proposals"] == 1
        assert res["pending_proposals"] == 1
        assert res["rejected_proposals"] == 0
        assert res["conversion_rate"] == 50.0
        assert res["total_revenue"] == 150.0
        
        # Scenario 2: Admin A sees consolidated company numbers
        headers = {"Authorization": f"Bearer {tokens['admin_a']}"}
        r = requests.get(f"{API}/stats", headers=headers)
        assert r.status_code == 200
        res = r.json()
        assert res["total_proposals"] == 3
        assert res["approved_proposals"] == 1
        assert res["pending_proposals"] == 1
        assert res["rejected_proposals"] == 1
        assert res["conversion_rate"] == 33.33
        assert res["total_revenue"] == 150.0
        
        # Scenario 3: Owner A sees consolidated company numbers
        headers = {"Authorization": f"Bearer {tokens['owner_a']}"}
        r = requests.get(f"{API}/stats", headers=headers)
        assert r.status_code == 200
        res = r.json()
        assert res["total_proposals"] == 3
        assert res["approved_proposals"] == 1
        assert res["pending_proposals"] == 1
        assert res["rejected_proposals"] == 1
        assert res["conversion_rate"] == 33.33
        assert res["total_revenue"] == 150.0
        
        # Scenario 4: Company A doesn't see Company B
        assert res["total_revenue"] == 150.0
        assert res["total_proposals"] == 3
        
        # Scenario 5: Legacy Owner (without company_id) fallback
        headers = {"Authorization": f"Bearer {tokens['legacy']}"}
        r = requests.get(f"{API}/stats", headers=headers)
        assert r.status_code == 200
        res = r.json()
        assert res["total_proposals"] == 1
        assert res["approved_proposals"] == 1
        assert res["total_revenue"] == 500.0
        assert res["conversion_rate"] == 100.0
        
        # Scenario 6: Owner B check
        headers = {"Authorization": f"Bearer {tokens['owner_b']}"}
        r = requests.get(f"{API}/stats", headers=headers)
        assert r.status_code == 200
        res = r.json()
        assert res["total_proposals"] == 1
        assert res["approved_proposals"] == 1
        assert res["total_revenue"] == 1000.0
        
    finally:
        user_ids = [u["id"] for u in users]
        prop_ids = [p["id"] for p in proposals]
        loop.run_until_complete(db.users.delete_many({"id": {"$in": user_ids}}))
        loop.run_until_complete(db.proposals.delete_many({"id": {"$in": prop_ids}}))


def test_optional_pagination():
    import requests
    import uuid
    import asyncio
    
    BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    API = f"{BASE_URL}/api"
    
    loop = asyncio.get_event_loop()
    
    # Generate unique test data
    company_id = f"test-pag-company-{uuid.uuid4().hex[:6]}"
    user_id = f"test-pag-user-{uuid.uuid4().hex[:6]}"
    user_email = f"test_pag_{uuid.uuid4().hex[:6]}@test.com"
    token = create_access_token(user_id, user_email)
    
    user = {
        "id": user_id,
        "email": user_email,
        "name": "Pag Tester",
        "company_id": company_id,
        "role": "owner",
        "active": True
    }
    
    # Insert 15 proposals
    proposals = []
    for i in range(15):
        proposals.append({
            "id": f"prop-pag-{i}-{uuid.uuid4()}",
            "user_id": user_id,
            "company_id": company_id,
            "client_name": f"Client {i:02d}",
            "client_document": "123",
            "products": [],
            "status": "aberto",
            "total": 100.0 * (i + 1),
            "created_at": f"2026-06-16T12:00:{i:02d}Z"
        })
        
    # Insert 15 products
    products = []
    for i in range(15):
        products.append({
            "id": f"prod-pag-{i}-{uuid.uuid4()}",
            "company_id": company_id,
            "code": f"CODE{i:02d}",
            "name": f"Product {i:02d}",
            "description": f"Desc {i:02d}",
            "price": 10.0 * (i + 1),
            "unit": "UN",
            "active": True
        })
        
    # Run DB insertion
    loop.run_until_complete(db.users.insert_one(user))
    loop.run_until_complete(db.proposals.insert_many(proposals))
    loop.run_until_complete(db.products.insert_many(products))
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # 1. proposals sem paginação
        # Should return all 15 proposals (in descending order of created_at)
        r = requests.get(f"{API}/proposals", headers=headers)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        assert len(items) >= 15
        
        # 12. compatibilidade de formato List[Item] (no wrapper, no total_count, no metadata)
        # Check first item structure
        assert "id" in items[0]
        assert "client_name" in items[0]
        assert "total" in items[0]
        
        # 2. proposals page=1&page_size=10
        # Should return the first 10 items
        r = requests.get(f"{API}/proposals?page=1&page_size=10", headers=headers)
        assert r.status_code == 200
        p1 = r.json()
        assert isinstance(p1, list)
        assert len(p1) == 10
        # proposals are sorted by created_at desc, so Client 14 is first
        assert p1[0]["client_name"] == "Client 14"
        assert p1[9]["client_name"] == "Client 05"
        
        # 3. proposals page=2&page_size=10
        # Should return the next 5 items
        r = requests.get(f"{API}/proposals?page=2&page_size=10", headers=headers)
        assert r.status_code == 200
        p2 = r.json()
        assert isinstance(p2, list)
        assert len(p2) == 5
        assert p2[0]["client_name"] == "Client 04"
        assert p2[4]["client_name"] == "Client 00"
        
        # 4. proposals page_size > 100
        r = requests.get(f"{API}/proposals?page=1&page_size=101", headers=headers)
        assert r.status_code == 422
        
        # 5. products sem paginação
        r = requests.get(f"{API}/products", headers=headers)
        assert r.status_code == 200
        prod_items = r.json()
        assert isinstance(prod_items, list)
        assert len(prod_items) >= 15
        assert "name" in prod_items[0]
        
        # 6. products page=1&page_size=10
        # Sorted by name asc, so Product 00 to Product 09
        r = requests.get(f"{API}/products?page=1&page_size=10", headers=headers)
        assert r.status_code == 200
        pr1 = r.json()
        assert isinstance(pr1, list)
        assert len(pr1) == 10
        assert pr1[0]["name"] == "Product 00"
        assert pr1[9]["name"] == "Product 09"
        
        # 7. products page=2&page_size=10
        r = requests.get(f"{API}/products?page=2&page_size=10", headers=headers)
        assert r.status_code == 200
        pr2 = r.json()
        assert isinstance(pr2, list)
        assert len(pr2) == 5
        assert pr2[0]["name"] == "Product 10"
        assert pr2[4]["name"] == "Product 14"
        
        # 8. page inválido (<1)
        r = requests.get(f"{API}/proposals?page=0&page_size=10", headers=headers)
        assert r.status_code == 422
        
        r = requests.get(f"{API}/proposals?page=-5&page_size=10", headers=headers)
        assert r.status_code == 422
        
        # 9. page_size inválido (<1)
        r = requests.get(f"{API}/proposals?page=1&page_size=0", headers=headers)
        assert r.status_code == 422
        
        r = requests.get(f"{API}/proposals?page=1&page_size=-1", headers=headers)
        assert r.status_code == 422
        
        # 10. page sem page_size
        r = requests.get(f"{API}/proposals?page=1", headers=headers)
        assert r.status_code == 422
        
        # 11. page_size sem page
        r = requests.get(f"{API}/proposals?page_size=10", headers=headers)
        assert r.status_code == 422
        
    finally:
        # Clean up
        loop.run_until_complete(db.users.delete_one({"id": user_id}))
        loop.run_until_complete(db.proposals.delete_many({"id": {"$in": [p["id"] for p in proposals]}}))
        loop.run_until_complete(db.products.delete_many({"id": {"$in": [pr["id"] for pr in products]}}))


def test_products_crud_fase3a():
    import requests
    import uuid
    import asyncio
    
    BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    API = f"{BASE_URL}/api"
    
    loop = asyncio.get_event_loop()
    
    # Empresa A
    company_a = f"comp-a-{uuid.uuid4().hex[:6]}"
    owner_a = f"usr-owner-a-{uuid.uuid4().hex[:6]}"
    admin_a = f"usr-admin-a-{uuid.uuid4().hex[:6]}"
    seller_a = f"usr-seller-a-{uuid.uuid4().hex[:6]}"
    
    # Empresa B
    company_b = f"comp-b-{uuid.uuid4().hex[:6]}"
    owner_b = f"usr-owner-b-{uuid.uuid4().hex[:6]}"
    admin_b = f"usr-admin-b-{uuid.uuid4().hex[:6]}"
    seller_b = f"usr-seller-b-{uuid.uuid4().hex[:6]}"
    
    # Tokens
    token_owner_a = create_access_token(owner_a, "owner_a@test.com")
    token_admin_a = create_access_token(admin_a, "admin_a@test.com")
    token_seller_a = create_access_token(seller_a, "seller_a@test.com")
    
    token_owner_b = create_access_token(owner_b, "owner_b@test.com")
    token_admin_b = create_access_token(admin_b, "admin_b@test.com")
    token_seller_b = create_access_token(seller_b, "seller_b@test.com")
    
    users = [
        {"id": owner_a, "email": "owner_a@test.com", "name": "Owner A", "company_id": company_a, "role": "owner", "active": True},
        {"id": admin_a, "email": "admin_a@test.com", "name": "Admin A", "company_id": company_a, "role": "admin", "active": True},
        {"id": seller_a, "email": "seller_a@test.com", "name": "Seller A", "company_id": company_a, "role": "seller", "active": True},
        {"id": owner_b, "email": "owner_b@test.com", "name": "Owner B", "company_id": company_b, "role": "owner", "active": True},
        {"id": admin_b, "email": "admin_b@test.com", "name": "Admin B", "company_id": company_b, "role": "admin", "active": True},
        {"id": seller_b, "email": "seller_b@test.com", "name": "Seller B", "company_id": company_b, "role": "seller", "active": True},
    ]
    
    loop.run_until_complete(db.users.insert_many(users))
    
    # We will track created products for cleanup
    product_ids = []
    
    try:
        # Helper to build auth headers
        def headers_for(token):
            return {"Authorization": f"Bearer {token}"}
            
        # 1. Owner cria produto (Empresa A)
        r = requests.post(
            f"{API}/products",
            json={"code": "PROD-A", "name": "Alpha Product", "description": "Desc A", "price": 100.0, "unit": "UN"},
            headers=headers_for(token_owner_a)
        )
        assert r.status_code == 200
        p_a = r.json()
        assert p_a["code"] == "PROD-A"
        assert p_a["company_id"] == company_a
        product_ids.append(p_a["id"])
        
        # 2. Admin cria produto (Empresa A)
        r = requests.post(
            f"{API}/products",
            json={"code": "PROD-B", "name": "Beta Product", "description": "Desc B", "price": 150.0, "unit": "UN"},
            headers=headers_for(token_admin_a)
        )
        assert r.status_code == 200
        p_b = r.json()
        assert p_b["code"] == "PROD-B"
        product_ids.append(p_b["id"])
        
        # 3. Seller não cria produto (403)
        r = requests.post(
            f"{API}/products",
            json={"code": "PROD-C", "name": "Gamma Product", "price": 200.0},
            headers=headers_for(token_seller_a)
        )
        assert r.status_code == 403
        
        # 16. Duplicidade de code na mesma empresa (409)
        r = requests.post(
            f"{API}/products",
            json={"code": "PROD-A", "name": "Another Alpha", "price": 50.0},
            headers=headers_for(token_owner_a)
        )
        assert r.status_code == 409
        
        # 17. Mesmo code em empresas diferentes permitido
        # Owner B cria PROD-A na Empresa B
        r = requests.post(
            f"{API}/products",
            json={"code": "PROD-A", "name": "Alpha Product B", "price": 120.0},
            headers=headers_for(token_owner_b)
        )
        assert r.status_code == 200
        p_b_prod = r.json()
        assert p_b_prod["company_id"] == company_b
        product_ids.append(p_b_prod["id"])
        
        # 4. Owner lista produtos (deve vir apenas os da Empresa A, ativos + inativos)
        r = requests.get(f"{API}/products", headers=headers_for(token_owner_a))
        assert r.status_code == 200
        list_owner = r.json()
        assert len(list_owner) == 2
        
        # 5. Admin lista produtos
        r = requests.get(f"{API}/products", headers=headers_for(token_admin_a))
        assert r.status_code == 200
        assert len(r.json()) == 2
        
        # 6. Seller lista produtos
        r = requests.get(f"{API}/products", headers=headers_for(token_seller_a))
        assert r.status_code == 200
        assert len(r.json()) == 2
        
        # 22. Isolamento: Empresa A não enxerga produtos Empresa B
        # List de Owner A tem 2 itens. List de Owner B tem 1 item.
        r = requests.get(f"{API}/products", headers=headers_for(token_owner_b))
        assert r.status_code == 200
        list_b = r.json()
        assert len(list_b) == 1
        assert list_b[0]["id"] == p_b_prod["id"]
        
        # 7. Owner visualiza produto
        r = requests.get(f"{API}/products/{p_a['id']}", headers=headers_for(token_owner_a))
        assert r.status_code == 200
        assert r.json()["code"] == "PROD-A"
        
        # 8. Admin visualiza produto
        r = requests.get(f"{API}/products/{p_a['id']}", headers=headers_for(token_admin_a))
        assert r.status_code == 200
        
        # 9. Seller visualiza produto
        r = requests.get(f"{API}/products/{p_a['id']}", headers=headers_for(token_seller_a))
        assert r.status_code == 200
        
        # 25. Isolamento: Seller Empresa A não visualiza produto Empresa B (404)
        r = requests.get(f"{API}/products/{p_b_prod['id']}", headers=headers_for(token_seller_a))
        assert r.status_code == 404
        
        # 10. Owner atualiza produto
        r = requests.put(
            f"{API}/products/{p_a['id']}",
            json={"code": "PROD-A-EDIT", "name": "Alpha Edited", "description": "New desc", "price": 95.0, "unit": "KG", "active": False},
            headers=headers_for(token_owner_a)
        )
        assert r.status_code == 200
        p_a_edited = r.json()
        assert p_a_edited["name"] == "Alpha Edited"
        assert p_a_edited["code"] == "PROD-A-EDIT"
        assert p_a_edited["active"] is False  # can be updated to inactive
        
        # 2. GET /products deve retornar ativos e inativos!
        r = requests.get(f"{API}/products", headers=headers_for(token_owner_a))
        assert r.status_code == 200
        list_after_inactive = r.json()
        assert len(list_after_inactive) == 2  # still returns both, active + inactive!
        
        # 11. Admin atualiza produto (voltar o código para PROD-A)
        r = requests.put(
            f"{API}/products/{p_a['id']}",
            json={"code": "PROD-A", "name": "Alpha Reverted", "description": "Desc reverted", "price": 100.0, "unit": "UN", "active": True},
            headers=headers_for(token_admin_a)
        )
        assert r.status_code == 200
        
        # 12. Seller não atualiza (403)
        r = requests.put(
            f"{API}/products/{p_a['id']}",
            json={"code": "PROD-A", "name": "Seller Try", "price": 100.0},
            headers=headers_for(token_seller_a)
        )
        assert r.status_code == 403
        
        # 23. Isolamento: Owner Empresa A não edita produto Empresa B (404)
        r = requests.put(
            f"{API}/products/{p_b_prod['id']}",
            json={"code": "PROD-B-HACK", "name": "Hacked", "price": 10.0},
            headers=headers_for(token_owner_a)
        )
        assert r.status_code == 404
        
        # 24. Isolamento: Admin Empresa A não edita produto Empresa B (404)
        r = requests.put(
            f"{API}/products/{p_b_prod['id']}",
            json={"code": "PROD-B-HACK", "name": "Hacked", "price": 10.0},
            headers=headers_for(token_admin_a)
        )
        assert r.status_code == 404
        
        # Teste de conflito de código durante UPDATE (Requisito 5: conflito de código na mesma empresa -> 409)
        # Tenta atualizar o PROD-B (p_b) para usar o código "PROD-A" (que pertence a p_a)
        r = requests.put(
            f"{API}/products/{p_b['id']}",
            json={"code": "PROD-A", "name": "Beta Duplicated", "price": 150.0},
            headers=headers_for(token_owner_a)
        )
        assert r.status_code == 409
        
        # 18. Busca por name
        r = requests.get(f"{API}/products?search=beta", headers=headers_for(token_owner_a))
        assert r.status_code == 200
        search_res = r.json()
        assert len(search_res) == 1
        assert search_res[0]["code"] == "PROD-B"
        
        # 19. Busca por code
        r = requests.get(f"{API}/products?search=prod-a", headers=headers_for(token_owner_a))
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["name"] == "Alpha Reverted"
        
        # 20. Ordenação por name, code, price (asc e desc)
        # Ordenação por price desc (p_b = 150.0, p_a = 100.0) -> p_b deve vir primeiro
        r = requests.get(f"{API}/products?sort_by=price&sort_order=desc", headers=headers_for(token_owner_a))
        assert r.status_code == 200
        res_sort = r.json()
        assert res_sort[0]["price"] == 150.0
        assert res_sort[1]["price"] == 100.0
        
        # Ordenação por price asc -> p_a deve vir primeiro
        r = requests.get(f"{API}/products?sort_by=price&sort_order=asc", headers=headers_for(token_owner_a))
        assert r.status_code == 200
        res_sort = r.json()
        assert res_sort[0]["price"] == 100.0
        assert res_sort[1]["price"] == 150.0
        
        # 21. sort_by inválido retorna 400
        r = requests.get(f"{API}/products?sort_by=invalid_field", headers=headers_for(token_owner_a))
        assert r.status_code == 400
        
        r = requests.get(f"{API}/products?sort_by=price&sort_order=invalid_dir", headers=headers_for(token_owner_a))
        assert r.status_code == 400
        
        # 26. Compatibilidade da paginação continua funcionando
        # Pagination page=1&page_size=1 sorted by name -> first product (Alpha Reverted)
        r = requests.get(f"{API}/products?page=1&page_size=1", headers=headers_for(token_owner_a))
        assert r.status_code == 200
        pag_items = r.json()
        assert len(pag_items) == 1
        assert pag_items[0]["name"] == "Alpha Reverted"
        
        # 15. Seller não exclui produto (403)
        r = requests.delete(f"{API}/products/{p_a['id']}", headers=headers_for(token_seller_a))
        assert r.status_code == 403
        
        # 13. Owner exclui produto (Empresa A)
        r = requests.delete(f"{API}/products/{p_a['id']}", headers=headers_for(token_owner_a))
        assert r.status_code == 200
        
        # Verificar que p_a foi realmente deletado fisicamente (Hard Delete)
        r = requests.get(f"{API}/products/{p_a['id']}", headers=headers_for(token_owner_a))
        assert r.status_code == 404
        
        # 14. Admin exclui produto (Empresa A)
        r = requests.delete(f"{API}/products/{p_b['id']}", headers=headers_for(token_admin_a))
        assert r.status_code == 200
        
        # Verificar que p_b foi realmente deletado
        r = requests.get(f"{API}/products/{p_b['id']}", headers=headers_for(token_admin_a))
        assert r.status_code == 404
        
    finally:
        # Clean up
        loop.run_until_complete(db.users.delete_many({"id": {"$in": [u["id"] for u in users]}}))
        loop.run_until_complete(db.products.delete_many({"id": {"$in": product_ids}}))


def test_proposals_commercial_engine_fase3b():
    import requests
    import uuid
    import asyncio
    
    BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    API = f"{BASE_URL}/api"
    
    loop = asyncio.get_event_loop()
    
    # Generate unique test data for Company A & B
    company_a = f"comp-a-{uuid.uuid4().hex[:6]}"
    company_b = f"comp-b-{uuid.uuid4().hex[:6]}"
    
    user_a = f"usr-a-{uuid.uuid4().hex[:6]}"
    user_b = f"usr-b-{uuid.uuid4().hex[:6]}"
    
    email_a = f"{user_a}@test.com"
    email_b = f"{user_b}@test.com"
    
    token_a = create_access_token(user_a, email_a)
    token_b = create_access_token(user_b, email_b)
    
    # Users setup
    db_users = [
        {"id": user_a, "email": email_a, "name": "User A", "company_id": company_a, "role": "owner", "active": True},
        {"id": user_b, "email": email_b, "name": "User B", "company_id": company_b, "role": "owner", "active": True}
    ]
    
    # Products setup (Empresa A)
    prod_a1_id = f"p-a1-{uuid.uuid4().hex[:6]}"
    prod_a2_id = f"p-a2-{uuid.uuid4().hex[:6]}"
    prod_a_inactive_id = f"p-ainact-{uuid.uuid4().hex[:6]}"
    
    # Product (Empresa B)
    prod_b1_id = f"p-b1-{uuid.uuid4().hex[:6]}"
    
    db_products = [
        {"id": prod_a1_id, "company_id": company_a, "code": "P-A1", "name": "Product A1", "description": "Desc A1", "price": 100.0, "unit": "UN", "active": True},
        {"id": prod_a2_id, "company_id": company_a, "code": "P-A2", "name": "Product A2", "description": "Desc A2", "price": 50.0, "unit": "UN", "active": True},
        {"id": prod_a_inactive_id, "company_id": company_a, "code": "P-AINACT", "name": "Product Inactive", "description": "Inactive", "price": 30.0, "unit": "UN", "active": False},
        {"id": prod_b1_id, "company_id": company_b, "code": "P-B1", "name": "Product B1", "description": "Desc B1", "price": 200.0, "unit": "UN", "active": True}
    ]
    
    loop.run_until_complete(db.users.insert_many(db_users))
    loop.run_until_complete(db.products.insert_many(db_products))
    
    # We will track created proposal IDs for cleanup
    proposal_ids = []
    
    try:
        # Helper for auth headers
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}
        
        # 1. 404 for nonexistent product
        payload_invalid = {
            "client_name": "Client Invalid",
            "client_document": "123",
            "client_phone": "11999999999",
            "products": [{"product_id": "nonexistent-id", "quantity": 1.0}],
            "shipping_deadline": "10 dias",
            "discount": 0.0
        }
        r = requests.post(f"{API}/proposals", json=payload_invalid, headers=headers_a)
        assert r.status_code == 404 # Scenario 6
        
        # 2. 404 for inactive product
        payload_inactive = {
            "client_name": "Client Inactive",
            "client_document": "123",
            "client_phone": "11999999999",
            "products": [{"product_id": prod_a_inactive_id, "quantity": 1.0}],
            "shipping_deadline": "10 dias",
            "discount": 0.0
        }
        r = requests.post(f"{API}/proposals", json=payload_inactive, headers=headers_a)
        assert r.status_code == 404 # Product must be active
        
        # 3. 404 for company isolation (User A trying to use Product of Company B)
        payload_cross = {
            "client_name": "Client Cross",
            "client_document": "123",
            "client_phone": "11999999999",
            "products": [{"product_id": prod_b1_id, "quantity": 1.0}],
            "shipping_deadline": "10 dias",
            "discount": 0.0
        }
        r = requests.post(f"{API}/proposals", json=payload_cross, headers=headers_a)
        assert r.status_code == 404 # Scenario 7
        
        # 4. Proposal with 1 item
        payload_single = {
            "client_name": "Client Single",
            "client_document": "123",
            "client_phone": "11999999999",
            "products": [{"product_id": prod_a1_id, "quantity": 2.0}],
            "shipping_deadline": "10 dias",
            "discount": 10.0
        }
        r = requests.post(f"{API}/proposals", json=payload_single, headers=headers_a)
        assert r.status_code == 200
        prop_single = r.json()
        proposal_ids.append(prop_single["id"])
        
        # Verify single item fields (snapshot details)
        assert len(prop_single["products"]) == 1 # Scenario 1
        item = prop_single["products"][0]
        assert item["product_id"] == prod_a1_id
        assert item["code"] == "P-A1"
        assert item["name"] == "Product A1"
        assert item["description"] == "Desc A1"
        assert item["unit"] == "UN"
        assert item["quantity"] == 2.0
        assert item["unit_price"] == 100.0
        assert item["total"] == 200.0
        
        # Verify totals
        assert prop_single["subtotal"] == 200.0 # Scenario 3
        assert prop_single["discount"] == 10.0 # Scenario 4
        assert prop_single["grand_total"] == 190.0 # Scenario 5
        assert prop_single["total"] == 190.0 # total = grand_total compatibility
        
        # 5. Proposal with multiple items
        payload_multi = {
            "client_name": "Client Multi",
            "client_document": "123456",
            "client_phone": "11999999999",
            "products": [
                {"product_id": prod_a1_id, "quantity": 3.0},
                {"product_id": prod_a2_id, "quantity": 4.0}
            ],
            "shipping_deadline": "15 dias",
            "discount": 1000.0 # Discount larger than subtotal to test grand_total minimum 0
        }
        r = requests.post(f"{API}/proposals", json=payload_multi, headers=headers_a)
        assert r.status_code == 200
        prop_multi = r.json()
        proposal_ids.append(prop_multi["id"])
        
        assert len(prop_multi["products"]) == 2 # Scenario 2
        assert prop_multi["subtotal"] == (3.0 * 100.0) + (4.0 * 50.0) # subtotal = 500.0
        assert prop_multi["discount"] == 1000.0
        assert prop_multi["grand_total"] == 0.0 # grand_total must be min 0
        assert prop_multi["total"] == 0.0
        
        # 6. Duplication
        r = requests.post(f"{API}/proposals/{prop_single['id']}/duplicate", headers=headers_a)
        assert r.status_code == 200
        duplicated = r.json()
        proposal_ids.append(duplicated["id"])
        
        # Verify duplicated proposal details
        assert duplicated["id"] != prop_single["id"]
        assert duplicated["status"] == "aberto"
        assert duplicated["discount"] == 10.0 # Scenario 9 (copies discount)
        assert len(duplicated["products"]) == 1 # Scenario 8 (copies items)
        dup_item = duplicated["products"][0]
        assert dup_item["product_id"] == prod_a1_id
        assert dup_item["quantity"] == 2.0
        assert duplicated["subtotal"] == 200.0
        assert duplicated["grand_total"] == 190.0
        assert duplicated["total"] == 190.0
        
        # 7. Check PDF data compatibility (check if fields for PDF layout are present)
        for p_data in [prop_single, duplicated]:
            assert "subtotal" in p_data # Scenario 11
            assert "discount" in p_data # Scenario 12
            assert "grand_total" in p_data or "total" in p_data # Scenario 13
            assert "products" in p_data
            for pr in p_data["products"]:
                assert "code" in pr
                assert "name" in pr
                assert "description" in pr
                assert "quantity" in pr
                assert "unit_price" in pr or "price" in pr
                assert "total" in pr # Scenario 10
                
        # 8. Stats Revenue uses grand_total
        # Mark prop_single as "realizado" (won)
        r = requests.patch(f"{API}/proposals/{prop_single['id']}/status", json={"status": "realizado"}, headers=headers_a)
        assert r.status_code == 200
        
        r = requests.get(f"{API}/stats", headers=headers_a)
        assert r.status_code == 200
        stats = r.json()
        assert stats["total_revenue"] == 190.0 # Scenario 14
        
    finally:
        # Clean up
        loop.run_until_complete(db.users.delete_many({"id": {"$in": [user_a, user_b]}}))
        loop.run_until_complete(db.products.delete_many({"id": {"$in": [prod_a1_id, prod_a2_id, prod_a_inactive_id, prod_b1_id]}}))
        loop.run_until_complete(db.proposals.delete_many({"id": {"$in": proposal_ids}}))


def test_proposals_hybrid_items_fase3b1():
    import requests
    import uuid
    import asyncio
    
    BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    API = f"{BASE_URL}/api"
    
    loop = asyncio.get_event_loop()
    
    # Generate unique test data for Company A
    company_a = f"comp-hybrid-a-{uuid.uuid4().hex[:6]}"
    user_a = f"usr-hybrid-a-{uuid.uuid4().hex[:6]}"
    email_a = f"{user_a}@test.com"
    token_a = create_access_token(user_a, email_a)
    
    # Users setup
    db_users = [
        {"id": user_a, "email": email_a, "name": "User Hybrid A", "company_id": company_a, "role": "owner", "active": True}
    ]
    
    # Products setup (Empresa A)
    prod_catalog_id = f"p-cat-{uuid.uuid4().hex[:6]}"
    prod_inactive_id = f"p-inact-{uuid.uuid4().hex[:6]}"
    
    db_products = [
        {"id": prod_catalog_id, "company_id": company_a, "code": "CAT-PROD", "name": "Catalog Product", "description": "Catalog Desc", "price": 150.0, "unit": "UN", "active": True},
        {"id": prod_inactive_id, "company_id": company_a, "code": "INACT-PROD", "name": "Inactive Catalog Product", "description": "Inactive", "price": 50.0, "unit": "UN", "active": False}
    ]
    
    loop.run_until_complete(db.users.insert_many(db_users))
    loop.run_until_complete(db.products.insert_many(db_products))
    
    proposal_ids = []
    
    try:
        headers_a = {"Authorization": f"Bearer {token_a}"}
        
        # 1. Proposta usando produto catálogo
        payload_cat = {
            "client_name": "Client Cat",
            "client_document": "123",
            "client_phone": "11999999999",
            "products": [{"product_id": prod_catalog_id, "quantity": 3.0}],
            "shipping_deadline": "10 dias",
            "discount": 50.0
        }
        r = requests.post(f"{API}/proposals", json=payload_cat, headers=headers_a)
        assert r.status_code == 200
        prop_cat = r.json()
        proposal_ids.append(prop_cat["id"])
        assert prop_cat["subtotal"] == 450.0
        assert prop_cat["grand_total"] == 400.0
        assert prop_cat["total"] == 400.0
        assert prop_cat["products"][0]["product_id"] == prod_catalog_id
        assert prop_cat["products"][0]["code"] == "CAT-PROD"
        
        # 2. Proposta usando item avulso
        payload_avulso = {
            "client_name": "Client Manual",
            "client_document": "123",
            "client_phone": "11999999999",
            "products": [{
                "name": "Serpentina FCU 12TR",
                "description": "8 filas tubo 3/8",
                "unit": "UN",
                "unit_price": 2500.0,
                "quantity": 2.0
            }],
            "shipping_deadline": "10 dias",
            "discount": 0.0
        }
        r = requests.post(f"{API}/proposals", json=payload_avulso, headers=headers_a)
        assert r.status_code == 200
        prop_avulso = r.json()
        proposal_ids.append(prop_avulso["id"])
        assert prop_avulso["subtotal"] == 5000.0
        assert prop_avulso["grand_total"] == 5000.0
        assert prop_avulso["total"] == 5000.0
        assert prop_avulso["products"][0]["product_id"] == ""
        assert prop_avulso["products"][0]["name"] == "Serpentina FCU 12TR"
        
        # 3. Proposta usando ambos na mesma proposta
        payload_mixed = {
            "client_name": "Client Mixed",
            "client_document": "123",
            "client_phone": "11999999999",
            "products": [
                {"product_id": prod_catalog_id, "quantity": 2.0},
                {
                    "name": "Item Avulso",
                    "description": "Avulso Desc",
                    "unit": "UN",
                    "unit_price": 100.0,
                    "quantity": 5.0
                }
            ],
            "shipping_deadline": "10 dias",
            "discount": 100.0
        }
        r = requests.post(f"{API}/proposals", json=payload_mixed, headers=headers_a)
        assert r.status_code == 200
        prop_mixed = r.json()
        proposal_ids.append(prop_mixed["id"])
        # subtotal: (2 * 150) + (5 * 100) = 300 + 500 = 800
        # grand_total = 800 - 100 = 700
        assert prop_mixed["subtotal"] == 800.0
        assert prop_mixed["grand_total"] == 700.0
        assert prop_mixed["total"] == 700.0
        assert prop_mixed["products"][0]["product_id"] == prod_catalog_id
        assert prop_mixed["products"][1]["product_id"] == ""
        
        # 4. Product_id inexistente retorna 404
        payload_invalid_id = {
            "client_name": "Client Invalid",
            "client_document": "123",
            "client_phone": "11999999999",
            "products": [{"product_id": "nonexistent-id", "quantity": 1.0}],
            "shipping_deadline": "10 dias"
        }
        r = requests.post(f"{API}/proposals", json=payload_invalid_id, headers=headers_a)
        assert r.status_code == 404
        
        # 5. Produto inativo retorna 404
        payload_inactive = {
            "client_name": "Client Inactive",
            "client_document": "123",
            "client_phone": "11999999999",
            "products": [{"product_id": prod_inactive_id, "quantity": 1.0}],
            "shipping_deadline": "10 dias"
        }
        r = requests.post(f"{API}/proposals", json=payload_inactive, headers=headers_a)
        assert r.status_code == 404
        
        # 6. Item manual sem name retorna 422
        payload_no_name = {
            "client_name": "Client No Name",
            "client_document": "123",
            "client_phone": "11999999999",
            "products": [{
                "description": "manual",
                "unit": "UN",
                "unit_price": 100.0,
                "quantity": 1.0
            }],
            "shipping_deadline": "10 dias"
        }
        r = requests.post(f"{API}/proposals", json=payload_no_name, headers=headers_a)
        assert r.status_code == 422
        
        # 7. Item manual sem unit_price retorna 422
        payload_no_price = {
            "client_name": "Client No Price",
            "client_document": "123",
            "client_phone": "11999999999",
            "products": [{
                "name": "Manual",
                "description": "manual",
                "unit": "UN",
                "quantity": 1.0
            }],
            "shipping_deadline": "10 dias"
        }
        r = requests.post(f"{API}/proposals", json=payload_no_price, headers=headers_a)
        assert r.status_code == 422
        
        # 8. Cálculo financeiro correto: Validated in mixed/cat/avulso above
        
        # 9. Duplicação preserva ambos os tipos
        r = requests.post(f"{API}/proposals/{prop_mixed['id']}/duplicate", headers=headers_a)
        assert r.status_code == 200
        duplicated = r.json()
        proposal_ids.append(duplicated["id"])
        assert len(duplicated["products"]) == 2
        assert duplicated["products"][0]["product_id"] == prod_catalog_id
        assert duplicated["products"][1]["product_id"] == ""
        assert duplicated["products"][1]["name"] == "Item Avulso"
        assert duplicated["subtotal"] == 800.0
        assert duplicated["grand_total"] == 700.0
        assert duplicated["total"] == 700.0
        
        # 10. Stats continuam usando grand_total
        # Mark prop_cat as realizado (revenue = 400.0)
        r = requests.patch(f"{API}/proposals/{prop_cat['id']}/status", json={"status": "realizado"}, headers=headers_a)
        assert r.status_code == 200
        
        # Mark prop_mixed as realizado (revenue = 700.0)
        r = requests.patch(f"{API}/proposals/{prop_mixed['id']}/status", json={"status": "realizado"}, headers=headers_a)
        assert r.status_code == 200
        
        r = requests.get(f"{API}/stats", headers=headers_a)
        assert r.status_code == 200
        stats = r.json()
        assert stats["total_revenue"] == 1100.0 # 400.0 + 700.0
        
    finally:
        # Clean up
        loop.run_until_complete(db.users.delete_many({"id": user_a}))
        loop.run_until_complete(db.products.delete_many({"id": {"$in": [prod_catalog_id, prod_inactive_id]}}))
        loop.run_until_complete(db.proposals.delete_many({"id": {"$in": proposal_ids}}))

