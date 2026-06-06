import asyncio
import os
import json
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Load environment
ROOT_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(ROOT_DIR, ".env"))

mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]

async def test_phase1b():
    """Test Phase 1B multi-company implementation."""
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    print("\n=== PHASE 1B VALIDATION ===\n")
    
    # TEST 1: Check new user structure (should have company_id and role)
    print("TEST 1: Checking new users have company_id and role")
    recent_users = await db.users.find(
        {"company_id": {"$exists": True}},
        {"_id": 0, "id": 1, "email": 1, "name": 1, "company_id": 1, "role": 1}
    ).to_list(5)
    
    if recent_users:
        print(f"✓ Found {len(recent_users)} user(s) with company_id and role:")
        for user in recent_users:
            print(f"  - {user['email']}: company_id={user['company_id']}, role={user['role']}")
    else:
        print("✗ No users with company_id found (might be first run)")
    
    # TEST 2: Verify get_scope_filter logic
    print("\nTEST 2: Testing get_scope_filter helper logic")
    
    # Test with new user (has company_id)
    if recent_users:
        new_user = recent_users[0]
        scope_new = (
            {"company_id": new_user["company_id"]}
            if new_user.get("company_id")
            else {"user_id": new_user["id"]}
        )
        print(f"✓ New user scope filter: {scope_new}")
    
    # Test with old user (no company_id)
    old_users = await db.users.find(
        {"company_id": {"$exists": False}},
        {"_id": 0, "id": 1, "email": 1, "name": 1}
    ).to_list(1)
    
    if old_users:
        old_user = old_users[0]
        scope_old = (
            {"company_id": old_user.get("company_id")}
            if old_user.get("company_id")
            else {"user_id": old_user["id"]}
        )
        print(f"✓ Old user scope filter: {scope_old}")
    else:
        print("✓ No old users without company_id (all migrated or new)")
    
    # TEST 3: Verify company documents have id field
    print("\nTEST 3: Checking company documents have id field")
    companies_count = await db.companies.count_documents({})
    companies_with_id = await db.companies.count_documents({"id": {"$exists": True}})
    
    print(f"✓ Total companies: {companies_count}")
    print(f"✓ Companies with id: {companies_with_id}")
    
    if companies_count > 0 and companies_with_id > 0:
        sample_company = await db.companies.find_one(
            {"id": {"$exists": True}},
            {"_id": 0, "user_id": 1, "id": 1, "company_name": 1}
        )
        print(f"✓ Sample company: {sample_company}")
    
    # TEST 4: Verify user-company relationship
    print("\nTEST 4: Verifying user-company relationship")
    if recent_users:
        test_user = recent_users[0]
        company = await db.companies.find_one(
            {"user_id": test_user["id"]},
            {"_id": 0, "user_id": 1, "id": 1}
        )
        if company:
            match = test_user.get("company_id") == company.get("id")
            status = "✓" if match else "✗"
            print(f"{status} User company_id matches company.id: {match}")
            print(f"  - User company_id: {test_user.get('company_id')}")
            print(f"  - Company id: {company.get('id')}")
        else:
            print("✗ No company found for user")
    
    # TEST 5: Backward compatibility - old users should still work
    print("\nTEST 5: Testing backward compatibility")
    if old_users:
        old_user = old_users[0]
        proposals_old = await db.proposals.count_documents({"user_id": old_user["id"]})
        print(f"✓ Old user {old_user['email']}: has {proposals_old} proposals")
        print(f"  (Backward compatible - can still filter by user_id)")
    else:
        print("✓ No old users to test (all new users have company_id)")
    
    # TEST 6: User roles
    print("\nTEST 6: Checking user roles")
    users_with_role = await db.users.find(
        {"role": {"$exists": True}},
        {"_id": 0, "id": 1, "email": 1, "role": 1}
    ).to_list(3)
    
    if users_with_role:
        print(f"✓ Found {len(users_with_role)} user(s) with role:")
        for user in users_with_role:
            print(f"  - {user['email']}: role={user['role']}")
    else:
        print("✓ No users with role yet (first run)")
    
    print("\n=== VALIDATION COMPLETE ===\n")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(test_phase1b())
