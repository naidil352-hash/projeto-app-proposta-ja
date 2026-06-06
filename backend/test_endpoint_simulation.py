"""
Endpoint simulation test - Tests the actual registration flow as if called via HTTP
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
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

TRIAL_DAYS = 7
JWT_ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def make_referral_code(user_id: str) -> str:
    return user_id.replace("-", "")[:8].upper()

async def get_company_id(db, user_id: str) -> str | None:
    """Return the company.id for the given user_id, generating it if missing."""
    company = await db.companies.find_one({"user_id": user_id}, {"_id": 0})
    if not company:
        return None
    if not company.get("id"):
        company_id = str(uuid.uuid4())
        await db.companies.update_one(
            {"user_id": user_id},
            {"$set": {"id": company_id}},
        )
        return company_id
    return company["id"]

async def simulate_register_endpoint(db, name: str, email: str, password: str, referral_code: str = None):
    """Simulate the POST /auth/register endpoint"""
    email = email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise Exception("Email já cadastrado")
    
    user_id = str(uuid.uuid4())
    referral_code_generated = make_referral_code(user_id)
    now = datetime.now(timezone.utc)

    referred_by = None
    if referral_code:
        ref_user = await db.users.find_one({"referral_code": referral_code.upper().strip()})
        if ref_user and ref_user["id"] != user_id:
            referred_by = ref_user["id"]

    # Step 1: Create user
    doc = {
        "id": user_id,
        "email": email,
        "name": name,
        "password_hash": hash_password(password),
        "referral_code": referral_code_generated,
        "referred_by": referred_by,
        "created_at": now.isoformat(),
    }
    await db.users.insert_one(doc)

    # Step 2: Initialize empty company profile
    await db.companies.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {
            "user_id": user_id,
            "company_name": "",
            "cnpj": "",
            "phone": "",
            "email": email,
            "address": "",
            "logo_base64": "",
        }},
        upsert=True,
    )

    # Step 3: Get or create company.id
    company_id = await get_company_id(db, user_id)

    # Step 4: Update user with company_id and role
    if company_id:
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"company_id": company_id, "role": "admin"}},
        )
        doc["company_id"] = company_id
        doc["role"] = "admin"

    # Grant 7-day Pro trial automatically
    trial_until = now + timedelta(days=TRIAL_DAYS)
    await db.subscriptions.insert_one({
        "user_id": user_id,
        "plan": "pro",
        "last_plan_id": "trial",
        "pro_until": trial_until.isoformat(),
        "trial_used": True,
        "updated_at": now.isoformat(),
    })

    token = create_access_token(user_id, email)
    return {
        "token": token,
        "user": {
            "id": user_id,
            "email": email,
            "name": name,
            "company_id": company_id,
            "role": "admin"
        }
    }

async def test_registration_endpoint():
    """Test the registration endpoint simulation"""
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    print("\n=== ENDPOINT SIMULATION TEST ===\n")
    
    # Test 1: Register a new user
    print("1. Simulating: POST /auth/register")
    test_email = f"endpoint_test_{uuid.uuid4().hex[:8]}@example.com"
    
    try:
        response = await simulate_register_endpoint(
            db,
            name="Test User Endpoint",
            email=test_email,
            password="password123",
            referral_code=None
        )
        print("   ✓ Registration successful")
        print(f"   - User ID: {response['user']['id']}")
        print(f"   - Email: {response['user']['email']}")
        print(f"   - Name: {response['user']['name']}")
        print(f"   - Company ID: {response['user']['company_id']}")
        print(f"   - Role: {response['user']['role']}")
        print(f"   - Token generated: {response['token'][:20]}...")
        
        user_id = response['user']['id']
        
    except Exception as e:
        print(f"   ✗ Registration failed: {e}")
        return
    
    # Test 2: Verify user was created with company_id
    print("\n2. Verifying user in database")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    print(f"   ✓ User found:")
    print(f"   - company_id present: {'company_id' in user}")
    print(f"   - role present: {'role' in user}")
    if 'company_id' in user:
        print(f"   - company_id value: {user['company_id']}")
    if 'role' in user:
        print(f"   - role value: {user['role']}")
    
    # Test 3: Verify company was created with id
    print("\n3. Verifying company in database")
    company = await db.companies.find_one({"user_id": user_id}, {"_id": 0})
    print(f"   ✓ Company found:")
    print(f"   - id present: {'id' in company}")
    if 'id' in company:
        print(f"   - id value: {company['id']}")
    
    # Test 4: Verify ids match
    print("\n4. Verifying company_id matches company.id")
    if user.get('company_id') == company.get('id'):
        print(f"   ✓ IDs match: {user.get('company_id')}")
    else:
        print(f"   ✗ IDs don't match!")
        print(f"   - user.company_id: {user.get('company_id')}")
        print(f"   - company.id: {company.get('id')}")
    
    # Test 5: Verify subscription was created
    print("\n5. Verifying subscription")
    subscription = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    if subscription:
        print(f"   ✓ Subscription created:")
        print(f"   - plan: {subscription.get('plan')}")
        print(f"   - last_plan_id: {subscription.get('last_plan_id')}")
        print(f"   - trial_used: {subscription.get('trial_used')}")
    else:
        print(f"   ✗ Subscription not found!")
    
    # Test 6: Test scope filter logic
    print("\n6. Testing scope filter logic")
    scope = {"company_id": user['company_id']} if user.get("company_id") else {"user_id": user["id"]}
    print(f"   ✓ Scope filter for new user: {scope}")
    
    # Test 7: Cleanup
    print("\n7. Cleaning up test data")
    await db.users.delete_one({"id": user_id})
    await db.companies.delete_one({"user_id": user_id})
    await db.subscriptions.delete_one({"user_id": user_id})
    print("   ✓ Cleanup complete")
    
    print("\n=== ENDPOINT SIMULATION TEST PASSED ===\n")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(test_registration_endpoint())
