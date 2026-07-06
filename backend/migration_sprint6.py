import pymongo
import uuid
from datetime import datetime, timezone

def run_migration():
    mongo_url = "mongodb://propostaja:Hugo1409Dom@ac-nbnck3d-shard-00-00.sgusjn4.mongodb.net:27017,ac-nbnck3d-shard-00-01.sgusjn4.mongodb.net:27017,ac-nbnck3d-shard-00-02.sgusjn4.mongodb.net:27017/?ssl=true&replicaSet=atlas-ttkqid-shard-0&authSource=admin&appName=Cluster0"
    client = pymongo.MongoClient(mongo_url)
    
    # We migrate both databases to be absolutely robust
    dbs = ["proposta_ja", "propostaja"]
    
    for db_name in dbs:
        db = client[db_name]
        print(f"\n>>> Starting migration for database: {db_name}")
        
        proposals_col = db.proposals
        total_docs = proposals_col.count_documents({})
        print(f"Total proposals found: {total_docs}")
        
        migrated_count = 0
        
        # Query all proposals
        proposals = list(proposals_col.find({}))
        
        for p in proposals:
            updates = {}
            needs_update = False
            
            # 1. Check/initialize temperature
            if "temperature" not in p:
                updates["temperature"] = "morna"
                needs_update = True
                
            # 2. Check/initialize next_action_date
            if "next_action_date" not in p:
                updates["next_action_date"] = None
                needs_update = True
                
            # 3. Check/initialize next_action_description
            if "next_action_description" not in p:
                updates["next_action_description"] = ""
                needs_update = True
                
            # 4. Check/initialize timeline
            if "timeline" not in p or p["timeline"] is None:
                timeline = []
                user_id = p.get("user_id") or "system"
                created_at = p.get("created_at") or datetime.now(timezone.utc).isoformat()
                
                # Add default Created event
                timeline.append({
                    "id": str(uuid.uuid4()),
                    "type": "created",
                    "description": "Proposta criada.",
                    "created_at": created_at,
                    "created_by": user_id,
                    "next_action_date": None,
                    "next_action_description": ""
                })
                
                # Add default Sent event
                timeline.append({
                    "id": str(uuid.uuid4()),
                    "type": "sent",
                    "description": "📤 Proposta enviada.",
                    "created_at": created_at,
                    "created_by": user_id,
                    "next_action_date": None,
                    "next_action_description": ""
                })
                
                # Add Viewed event if proposal was viewed
                viewed_at = p.get("proposal_viewed_at")
                if viewed_at:
                    timeline.append({
                        "id": str(uuid.uuid4()),
                        "type": "viewed",
                        "description": "👁 Cliente visualizou.",
                        "created_at": viewed_at,
                        "created_by": user_id,
                        "next_action_date": None,
                        "next_action_description": ""
                    })
                    
                # Add Accepted/Rejected events
                acceptance_status = p.get("acceptance_status") or "pending"
                status = p.get("status")
                accept_date = p.get("accept_date") or p.get("updated_at") or created_at
                
                if acceptance_status == "accepted" or status == "aprovado":
                    timeline.append({
                        "id": str(uuid.uuid4()),
                        "type": "accepted",
                        "description": "✅ Cliente aceitou.",
                        "created_at": accept_date,
                        "created_by": user_id,
                        "next_action_date": None,
                        "next_action_description": ""
                    })
                elif acceptance_status == "rejected" or status == "perdido":
                    timeline.append({
                        "id": str(uuid.uuid4()),
                        "type": "rejected",
                        "description": "❌ Cliente recusou.",
                        "created_at": accept_date,
                        "created_by": user_id,
                        "next_action_date": None,
                        "next_action_description": ""
                    })
                    
                updates["timeline"] = timeline
                needs_update = True
                
            if needs_update:
                proposals_col.update_one({"_id": p["_id"]}, {"$set": updates})
                migrated_count += 1
                
        print(f"Migration completed for {db_name}. Migrated {migrated_count} proposals.")
        
    client.close()
    print("\n>>> All migrations completed successfully!")

if __name__ == "__main__":
    run_migration()
