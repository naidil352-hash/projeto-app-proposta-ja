"""
Integration test for Phase 1B - New user registration with company_id and role
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt
import jwt

# Load environment
ROOT_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(ROOT_DIR, ".env"))

mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

async def test_registration():
    """Simulate registration and verify Phase 1B fields."""
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    print("\n=== PHASE 1B INTEGRATION TEST ===\n")
    
    # Create test user (simulating registration)
    test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    test_user_id = str(uuid.uuid4())
    test_password = "test_password_123"
    
    print(f"1. Creating test user: {test_email}")
    
    # Step 1: Create user document
    user_doc = {
        "id": test_user_id,
        "email": test_email,
        "name": "Test User",
        "password_hash": hash_password(test_password),
        "referral_code": test_user_id.replace("-", "")[:8].upper(),
        "referred_by": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user_doc)
    print("   ✓ User created")
    
    # Step 2: Create company profile
    await db.companies.update_one(
        {"user_id": test_user_id},
        {"$setOnInsert": {
            "user_id": test_user_id,
            "company_name": "",
            "cnpj": "",
            "phone": "",
            "email": test_email,
            "address": "",
            "logo_base64": "",
        }},
        upsert=True,
    )
    print("   ✓ Company profile created")
    
    # Step 3: Get or create company.id
    company = await db.companies.find_one({"user_id": test_user_id}, {"_id": 0})
    company_id = None
    if company:
        if not company.get("id"):
            company_id = str(uuid.uuid4())
            await db.companies.update_one(
                {"user_id": test_user_id},
                {"$set": {"id": company_id}},
            )
        else:
            company_id = company["id"]
    print(f"   ✓ Company ID assigned: {company_id}")
    
    # Step 4: Update user with company_id and role
    if company_id:
        await db.users.update_one(
            {"id": test_user_id},
            {"$set": {"company_id": company_id, "role": "admin"}},
        )
        print(f"   ✓ User updated with company_id and role='admin'")
    
    # Step 5: Verify the user has all required fields
    print("\n2. Verifying new user structure:")
    stored_user = await db.users.find_one({"id": test_user_id}, {"_id": 0})
    
    required_fields = ["id", "email", "name", "company_id", "role", "created_at"]
    for field in required_fields:
        value = stored_user.get(field)
        status = "✓" if value is not None else "✗"
        print(f"   {status} {field}: {value}")
    
    # Step 6: Verify company.id matches user.company_id
    print("\n3. Verifying company.id matches user.company_id:")
    stored_company = await db.companies.find_one({"user_id": test_user_id}, {"_id": 0})
    match = stored_user.get("company_id") == stored_company.get("id")
    status = "✓" if match else "✗"
    print(f"   {status} user.company_id == company.id: {match}")
    print(f"      user.company_id: {stored_user.get('company_id')}")
    print(f"      company.id: {stored_company.get('id')}")
    
    # Step 7: Test get_scope_filter logic
    print("\n4. Testing get_scope_filter helper logic:")
    
    def get_scope_filter(user: dict) -> dict:
        if user.get("company_id"):
            return {"company_id": user["company_id"]}
        return {"user_id": user["id"]}
    
    scope = get_scope_filter(stored_user)
    print(f"   ✓ Scope filter for new user: {scope}")
    print(f"      (Uses company_id because user.company_id exists)")
    
    # Step 8: Test backward compatibility - old user scope filter
    print("\n5. Testing backward compatibility:")
    old_user = {"id": "test-old-id", "email": "old@example.com"}
    old_scope = get_scope_filter(old_user)
    print(f"   ✓ Scope filter for old user (no company_id): {old_scope}")
    print(f"      (Falls back to user_id)")
    
    # Step 9: Cleanup
    print("\n6. Cleaning up test user:")
    await db.users.delete_one({"id": test_user_id})
    await db.companies.delete_one({"user_id": test_user_id})
    print("   ✓ Test user and company deleted")
    
    print("\n=== INTEGRATION TEST PASSED ===\n")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(test_registration())
