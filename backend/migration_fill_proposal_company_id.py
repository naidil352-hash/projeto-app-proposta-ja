import os
import sys
import asyncio
import argparse
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

async def run_migration(db):
    # Retorna o total de propostas que já possuem o campo company_id para a contagem de ignorados
    total_with_company = await db.proposals.count_documents({"company_id": {"$exists": True}})
    
    cursor = db.proposals.find({"company_id": {"$exists": False}})
    total_updated = 0
    total_orphan = 0
    orphan_ids = []
    
    async for prop in cursor:
        prop_db_id = prop["_id"]
        prop_id = prop.get("id")
        user_id = prop.get("user_id")
        
        company_id = None
        if user_id:
            # 1. Procurar user pelo user_id da proposta
            user = await db.users.find_one({"id": user_id})
            if user:
                # 2. Se user.company_id existir: proposal.company_id = user.company_id
                company_id = user.get("company_id")
            
            # 3. Senão procurar: companies.user_id == proposal.user_id
            if not company_id:
                company = await db.companies.find_one({"user_id": user_id})
                if company:
                    # 4. Se encontrado: proposal.company_id = company.id
                    company_id = company.get("id")
                    
        if company_id:
            # 2 e 4. Atualizar proposta se encontrado
            res = await db.proposals.update_one(
                {"_id": prop_db_id, "company_id": {"$exists": False}},
                {"$set": {"company_id": company_id, "migrated_v11_backfill": True}}
            )
            if res.modified_count > 0:
                total_updated += 1
        else:
            # 5. Se não encontrado: registrar em relatório de órfãos
            total_orphan += 1
            orphan_ids.append(prop_id or str(prop_db_id))
            
    report = {
        "total_analyzed": total_with_company + total_updated + total_orphan,
        "total_updated": total_updated,
        "total_ignored": total_with_company,
        "total_orphan": total_orphan,
        "orphan_ids": orphan_ids
    }
    
    print("=== RELATÓRIO DE MIGRAÇÃO ===")
    print(f"* total analisado: {report['total_analyzed']}")
    print(f"* total atualizado: {report['total_updated']}")
    print(f"* total ignorado: {report['total_ignored']}")
    print(f"* total órfão: {report['total_orphan']}")
    print(f"* ids órfãos: {report['orphan_ids']}")
    print("=============================")
    return report

async def run_rollback(db):
    res = await db.proposals.update_many(
        {"migrated_v11_backfill": True},
        {"$unset": {"company_id": "", "migrated_v11_backfill": ""}}
    )
    print("=== RELATÓRIO DE ROLLBACK ===")
    print(f"Total revertido: {res.modified_count}")
    print("=============================")
    return res.modified_count

async def main():
    parser = argparse.ArgumentParser(description="Migração de company_id em propostas legadas.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", action="store_true", help="Executa o backfill de company_id.")
    group.add_argument("--rollback", action="store_true", help="Desfaz a migração.")
    
    args = parser.parse_args()
    
    ROOT_DIR = Path(__file__).resolve().parent
    load_dotenv(ROOT_DIR / ".env", override=True)
    
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    
    if not mongo_url or not db_name:
        print("Erro: MONGO_URL ou DB_NAME não configurados no ambiente.")
        sys.exit(1)
        
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    try:
        if args.run:
            await run_migration(db)
        elif args.rollback:
            await run_rollback(db)
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(main())
