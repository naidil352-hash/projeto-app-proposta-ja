"""
Debug test to understand company document creation
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Load environment
ROOT_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(ROOT_DIR, ".env"))

mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]

async def debug_company_creation():
    """Debug company creation and id generation."""
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    print("\n=== DEBUG COMPANY CREATION ===\n")
    
    test_user_id = str(uuid.uuid4())
    test_email = f"debug_{uuid.uuid4().hex[:8]}@example.com"
    
    # Step 1: Create company with upsert
    print(f"1. Creating company for user: {test_user_id}")
    result = await db.companies.update_one(
        {"user_id": test_user_id},
        {"$setOnInsert": {
            "user_id": test_user_id,
            "company_name": "Test Company",
            "cnpj": "",
            "phone": "",
            "email": test_email,
            "address": "",
            "logo_base64": "",
        }},
        upsert=True,
    )
    print(f"   Matched: {result.matched_count}, Upserted: {result.upserted_id}")
    
    # Step 2: Find the company without projection
    print("\n2. Finding company (no projection):")
    company_full = await db.companies.find_one({"user_id": test_user_id}, {"_id": 0})
    print(f"   {company_full}")
    
    # Step 3: Find the company with projection
    print("\n3. Finding company (with projection {_id: 0, id: 1}):")
    company_proj = await db.companies.find_one({"user_id": test_user_id}, {"_id": 0, "id": 1})
    print(f"   Result: {company_proj}")
    print(f"   Is falsy: {not company_proj}")
    
    # Step 4: Check if id field exists
    print("\n4. Checking id field:")
    has_id = company_full.get("id") if company_full else None
    print(f"   company_full.get('id'): {has_id}")
    
    # Step 5: Generate and assign id
    print("\n5. Generating and assigning company id:")
    generated_id = str(uuid.uuid4())
    print(f"   Generated ID: {generated_id}")
    
    update_result = await db.companies.update_one(
        {"user_id": test_user_id},
        {"$set": {"id": generated_id}},
    )
    print(f"   Matched: {update_result.matched_count}, Modified: {update_result.modified_count}")
    
    # Step 6: Verify id was set
    print("\n6. Verifying id was set:")
    company_with_id = await db.companies.find_one({"user_id": test_user_id}, {"_id": 0})
    print(f"   company.id: {company_with_id.get('id')}")
    
    # Step 7: Cleanup
    await db.companies.delete_one({"user_id": test_user_id})
    print("\n7. Cleaned up test company")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(debug_company_creation())
