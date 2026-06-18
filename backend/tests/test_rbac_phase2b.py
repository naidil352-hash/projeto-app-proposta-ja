import pytest
import uuid
import os
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from server import create_access_token, hash_password

mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
client_db = AsyncIOMotorClient(mongo_url)
db = client_db[db_name]

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api"

@pytest.fixture(scope="module")
def setup_data():
    company_id = str(uuid.uuid4())
    owner_id = str(uuid.uuid4())
    admin_id = str(uuid.uuid4())
    seller_id = str(uuid.uuid4())

    owner_email = f"owner_{uuid.uuid4().hex[:6]}@test.com"
    admin_email = f"admin_{uuid.uuid4().hex[:6]}@test.com"
    seller_email = f"seller_{uuid.uuid4().hex[:6]}@test.com"

    users = [
        {"id": owner_id, "email": owner_email, "name": "Owner", "company_id": company_id, "role": "owner", "active": True, "password_hash": hash_password("teste123"), "created_at": "2026-06-14T22:00:00Z"},
        {"id": admin_id, "email": admin_email, "name": "Admin", "company_id": company_id, "role": "admin", "active": True, "password_hash": hash_password("teste123"), "created_at": "2026-06-14T22:00:00Z"},
        {"id": seller_id, "email": seller_email, "name": "Seller", "company_id": company_id, "role": "seller", "active": True, "password_hash": hash_password("teste123"), "created_at": "2026-06-14T22:00:00Z"}
    ]

    tokens = {
        "owner": create_access_token(owner_id, owner_email),
        "admin": create_access_token(admin_id, admin_email),
        "seller": create_access_token(seller_id, seller_email)
    }

    companies = [
        {"id": company_id, "user_id": owner_id, "company_name": "CRUD Test Company"}
    ]

    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.users.insert_many(users))
    loop.run_until_complete(db.companies.insert_many(companies))

    yield {
        "company_id": company_id,
        "owner_id": owner_id,
        "admin_id": admin_id,
        "seller_id": seller_id,
        "tokens": tokens,
        "emails": {
            "owner": owner_email,
            "admin": admin_email,
            "seller": seller_email
        }
    }

    # Cleanup
    loop.run_until_complete(db.users.delete_many({"company_id": company_id}))
    loop.run_until_complete(db.companies.delete_many({"id": company_id}))
    client_db.close()


def test_list_users_permissions(setup_data):
    headers_owner = {"Authorization": f"Bearer {setup_data['tokens']['owner']}"}
    headers_admin = {"Authorization": f"Bearer {setup_data['tokens']['admin']}"}
    headers_seller = {"Authorization": f"Bearer {setup_data['tokens']['seller']}"}

    # Seller cannot list users (Should return 403)
    r = requests.get(f"{API}/users", headers=headers_seller)
    assert r.status_code == 403

    # Owner can list users (Should return 200)
    r = requests.get(f"{API}/users", headers=headers_owner)
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 3
    # Check that password_hash is hidden
    for u in data:
        assert "password_hash" not in u
        assert "password" not in u

    # Admin can list users (Should return 200)
    r = requests.get(f"{API}/users", headers=headers_admin)
    assert r.status_code == 200


def test_create_user_hierarchy(setup_data):
    headers_owner = {"Authorization": f"Bearer {setup_data['tokens']['owner']}"}
    headers_admin = {"Authorization": f"Bearer {setup_data['tokens']['admin']}"}

    # 1. Owner creates admin (200)
    email_adm = f"new_adm_{uuid.uuid4().hex[:6]}@test.com"
    r = requests.post(f"{API}/users", json={"name": "New Admin", "email": email_adm, "password": "password123", "role": "admin"}, headers=headers_owner)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    assert "password_hash" not in r.json()

    # 2. Owner creates seller (200)
    email_sel = f"new_sel_{uuid.uuid4().hex[:6]}@test.com"
    r = requests.post(f"{API}/users", json={"name": "New Seller 1", "email": email_sel, "password": "password123", "role": "seller"}, headers=headers_owner)
    assert r.status_code == 200

    # 3. Admin creates seller (200)
    email_sel2 = f"new_sel2_{uuid.uuid4().hex[:6]}@test.com"
    r = requests.post(f"{API}/users", json={"name": "New Seller 2", "email": email_sel2, "password": "password123", "role": "seller"}, headers=headers_admin)
    assert r.status_code == 200

    # 4. Admin tries to create admin (Should return 403)
    email_adm2 = f"new_adm2_{uuid.uuid4().hex[:6]}@test.com"
    r = requests.post(f"{API}/users", json={"name": "New Admin 2", "email": email_adm2, "password": "password123", "role": "admin"}, headers=headers_admin)
    assert r.status_code == 403

    # 5. Nobody can create owner (Should return 422/400 because of pydantic literal validation)
    # The Literal constraint on role enforces it to be "admin" or "seller"
    email_own = f"new_own_{uuid.uuid4().hex[:6]}@test.com"
    r = requests.post(f"{API}/users", json={"name": "New Owner", "email": email_own, "password": "password123", "role": "owner"}, headers=headers_owner)
    assert r.status_code in (400, 422)


def test_edit_user_hierarchy_and_protections(setup_data):
    headers_owner = {"Authorization": f"Bearer {setup_data['tokens']['owner']}"}
    headers_admin = {"Authorization": f"Bearer {setup_data['tokens']['admin']}"}

    # Owner can edit themselves (200)
    r = requests.put(f"{API}/users/{setup_data['owner_id']}", json={"name": "Owner Edited"}, headers=headers_owner)
    assert r.status_code == 200
    assert r.json()["name"] == "Owner Edited"

    # Owner can edit admin (200)
    r = requests.put(f"{API}/users/{setup_data['admin_id']}", json={"name": "Admin Edited"}, headers=headers_owner)
    assert r.status_code == 200

    # Admin tries to edit owner (Should return 403)
    r = requests.put(f"{API}/users/{setup_data['owner_id']}", json={"name": "Owner Hack"}, headers=headers_admin)
    assert r.status_code == 403

    # Admin tries to promote seller to admin (Should return 403)
    r = requests.put(f"{API}/users/{setup_data['seller_id']}", json={"role": "admin"}, headers=headers_admin)
    assert r.status_code == 403


def test_delete_and_reactivate(setup_data):
    headers_owner = {"Authorization": f"Bearer {setup_data['tokens']['owner']}"}
    headers_admin = {"Authorization": f"Bearer {setup_data['tokens']['admin']}"}

    # 1. Admin tries to delete owner (400)
    r = requests.delete(f"{API}/users/{setup_data['owner_id']}", headers=headers_admin)
    assert r.status_code == 400

    # 2. Admin tries to delete self (400)
    r = requests.delete(f"{API}/users/{setup_data['admin_id']}", headers=headers_admin)
    assert r.status_code == 400

    # 3. Admin deletes seller (200)
    r = requests.delete(f"{API}/users/{setup_data['seller_id']}", headers=headers_admin)
    assert r.status_code == 200

    # 4. Deleted seller is inactive and blocked from calling auth/me (Should return 403)
    token_seller = create_access_token(setup_data["seller_id"], setup_data["emails"]["seller"])
    headers_sel = {"Authorization": f"Bearer {token_seller}"}
    r = requests.get(f"{API}/auth/me", headers=headers_sel)
    assert r.status_code == 403

    # 5. Admin reactivates seller (200)
    r = requests.patch(f"{API}/users/{setup_data['seller_id']}/activate", headers=headers_admin)
    assert r.status_code == 200

    # 6. Seller can log in and access auth/me again (200)
    r = requests.get(f"{API}/auth/me", headers=headers_sel)
    assert r.status_code == 200
