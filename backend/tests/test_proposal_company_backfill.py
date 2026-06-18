import pytest
import asyncio
import os
import uuid
from dotenv import load_dotenv
from pathlib import Path

# Garante o carregamento das variáveis do arquivo .env
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=True)

from server import db
from migration_fill_proposal_company_id import run_migration, run_rollback

@pytest.fixture
def setup_test_db():
    loop = asyncio.get_event_loop()
    
    # IDs únicos para isolar os dados de testes
    test_user_with_company_id = f"test-user-wc-{uuid.uuid4()}"
    test_user_fallback_id = f"test-user-fb-{uuid.uuid4()}"
    test_user_no_company_id = f"test-user-nc-{uuid.uuid4()}"
    test_company_id = f"test-company-{uuid.uuid4()}"
    test_fallback_company_id = f"test-company-fb-{uuid.uuid4()}"
    
    # 1. Usuário com company_id
    user_wc = {
        "id": test_user_with_company_id,
        "email": f"user_wc_{uuid.uuid4().hex[:6]}@test.com",
        "company_id": test_company_id,
        "name": "User WC"
    }
    
    # 2. Usuário para fallback
    user_fb = {
        "id": test_user_fallback_id,
        "email": f"user_fb_{uuid.uuid4().hex[:6]}@test.com",
        "name": "User FB"
        # Sem company_id
    }
    company_fb = {
        "id": test_fallback_company_id,
        "user_id": test_user_fallback_id,
        "company_name": "Fallback Company"
    }
    
    # 3. Usuário sem empresa associada
    user_nc = {
        "id": test_user_no_company_id,
        "email": f"user_nc_{uuid.uuid4().hex[:6]}@test.com",
        "name": "User NC"
        # Sem company_id e sem documento em companies
    }
    
    # Propostas de teste
    prop_wc = {
        "id": f"prop-wc-{uuid.uuid4()}",
        "user_id": test_user_with_company_id,
        "title": "Proposal WC"
        # Sem company_id (legada)
    }
    
    prop_fb = {
        "id": f"prop-fb-{uuid.uuid4()}",
        "user_id": test_user_fallback_id,
        "title": "Proposal FB"
        # Sem company_id (legada)
    }
    
    prop_already_corrected = {
        "id": f"prop-corr-{uuid.uuid4()}",
        "user_id": test_user_with_company_id,
        "company_id": "already-corrected-company-id",
        "title": "Proposal Corrected"
    }
    
    prop_non_existent_user = {
        "id": f"prop-neu-{uuid.uuid4()}",
        "user_id": "non-existent-user-id-abc",
        "title": "Proposal NEU"
        # Sem company_id (legada)
    }
    
    prop_no_company = {
        "id": f"prop-nc-{uuid.uuid4()}",
        "user_id": test_user_no_company_id,
        "title": "Proposal NC"
        # Sem company_id (legada)
    }
    
    # Insere dados de teste
    loop.run_until_complete(db.users.insert_many([user_wc, user_fb, user_nc]))
    loop.run_until_complete(db.companies.insert_one(company_fb))
    loop.run_until_complete(db.proposals.insert_many([
        prop_wc,
        prop_fb,
        prop_already_corrected,
        prop_non_existent_user,
        prop_no_company
    ]))
    
    yield {
        "prop_wc_id": prop_wc["id"],
        "prop_fb_id": prop_fb["id"],
        "prop_already_corrected_id": prop_already_corrected["id"],
        "prop_non_existent_user_id": prop_non_existent_user["id"],
        "prop_no_company_id": prop_no_company["id"],
        "test_company_id": test_company_id,
        "test_fallback_company_id": test_fallback_company_id,
        "user_ids": [test_user_with_company_id, test_user_fallback_id, test_user_no_company_id],
        "company_ids": [test_fallback_company_id],
        "proposal_ids": [
            prop_wc["id"],
            prop_fb["id"],
            prop_already_corrected["id"],
            prop_non_existent_user["id"],
            prop_no_company["id"]
        ]
    }
    
    # Limpa dados de teste ao finalizar
    loop.run_until_complete(db.users.delete_many({"id": {"$in": [test_user_with_company_id, test_user_fallback_id, test_user_no_company_id]}}))
    loop.run_until_complete(db.companies.delete_many({"id": test_fallback_company_id}))
    loop.run_until_complete(db.proposals.delete_many({"id": {"$in": [
        prop_wc["id"],
        prop_fb["id"],
        prop_already_corrected["id"],
        prop_non_existent_user["id"],
        prop_no_company["id"]
    ]}}))

def test_legacy_proposals_backfill(setup_test_db):
    loop = asyncio.get_event_loop()
    data = setup_test_db
    
    # 1. Executa a migração (primeira vez)
    report = loop.run_until_complete(run_migration(db))
    
    # Validações dos cenários:
    
    # Cenário 1: Usuário com company_id
    p_wc = loop.run_until_complete(db.proposals.find_one({"id": data["prop_wc_id"]}))
    assert p_wc.get("company_id") == data["test_company_id"]
    assert p_wc.get("migrated_v11_backfill") is True
    
    # Cenário 2: Fallback company.user_id
    p_fb = loop.run_until_complete(db.proposals.find_one({"id": data["prop_fb_id"]}))
    assert p_fb.get("company_id") == data["test_fallback_company_id"]
    assert p_fb.get("migrated_v11_backfill") is True
    
    # Cenário 3: Proposta já corrigida (não deve ser modificada)
    p_corr = loop.run_until_complete(db.proposals.find_one({"id": data["prop_already_corrected_id"]}))
    assert p_corr.get("company_id") == "already-corrected-company-id"
    assert p_corr.get("migrated_v11_backfill") is not True
    
    # Cenário 4: Usuário inexistente (fica órfã)
    p_neu = loop.run_until_complete(db.proposals.find_one({"id": data["prop_non_existent_user_id"]}))
    assert "company_id" not in p_neu
    
    # Cenário 5: Empresa inexistente (fica órfã)
    p_nc = loop.run_until_complete(db.proposals.find_one({"id": data["prop_no_company_id"]}))
    assert "company_id" not in p_nc
    
    # Valida presença no relatório
    assert data["prop_non_existent_user_id"] in report["orphan_ids"]
    assert data["prop_no_company_id"] in report["orphan_ids"]
    
    # Cenário 6: Idempotência (rodar novamente não deve alterar mais nada)
    report2 = loop.run_until_complete(run_migration(db))
    assert report2["total_updated"] == 0
    
    # Propostas anteriormente atualizadas mantêm os valores corretos
    p_wc_2 = loop.run_until_complete(db.proposals.find_one({"id": data["prop_wc_id"]}))
    assert p_wc_2.get("company_id") == data["test_company_id"]
    
    # Valida Rollback
    rollback_count = loop.run_until_complete(run_rollback(db))
    assert rollback_count >= 2
    
    # Valida que as propostas atualizadas foram resetadas
    p_wc_rb = loop.run_until_complete(db.proposals.find_one({"id": data["prop_wc_id"]}))
    assert "company_id" not in p_wc_rb
    assert "migrated_v11_backfill" not in p_wc_rb
    
    p_fb_rb = loop.run_until_complete(db.proposals.find_one({"id": data["prop_fb_id"]}))
    assert "company_id" not in p_fb_rb
    assert "migrated_v11_backfill" not in p_fb_rb
    
    # Proposta já corrigida permanece inalterada
    p_corr_rb = loop.run_until_complete(db.proposals.find_one({"id": data["prop_already_corrected_id"]}))
    assert p_corr_rb.get("company_id") == "already-corrected-company-id"
