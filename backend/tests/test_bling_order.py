from unittest.mock import AsyncMock
from datetime import date

import pytest

from bling_order import BlingOrderValidationError, build_sales_order_plan


def proposal(**changes):
    base = {
        "id": "proposal-1", "status": "aprovado", "acceptance_status": "pending", "deleted": False,
        "client_name": "Cliente", "client_document": "12.345.678/0001-99", "discount": 5,
        "grand_total": 15, "products": [{"name": "Peça", "code": "SKU-1", "quantity": 2, "unit_price": 10, "unit": "UN"}],
    }
    base.update(changes)
    return base


async def test_plan_matches_document_and_code_exactly_and_never_writes():
    read = AsyncMock(side_effect=[
        {"data": [{"id": 9, "nome": "Cliente", "numeroDocumento": "12345678000199"}]},
        {"data": [{"id": 7, "nome": "Peça Bling", "codigo": "SKU-1"}]},
    ])
    plan = await build_sales_order_plan(proposal(), read)
    assert plan["client"]["bling_contact"]["id"] == 9
    assert plan["items"][0]["bling_product"]["id"] == 7
    assert plan["order_payload"] == {
        "data": date.today().isoformat(),
        "contato": {"id": 9},
        "itens": [{"quantidade": 2.0, "valor": 10.0, "codigo": "SKU-1", "unidade": "UN", "produto": {"id": 7}}],
        "observacoes": "Criado pelo Proposta Já a partir da proposta proposal-1.",
        "desconto": {"valor": 5.0, "unidade": "REAL"},
    }
    assert [call.args[0] for call in read.call_args_list] == ["/contatos", "/produtos"]


@pytest.mark.parametrize("changes", [
    {"status": "aberto"},
    {"client_document": ""},
    {"products": [{"name": "Peça", "code": "", "quantity": 1, "unit_price": 1}]},
    {"products": [{"name": "Peça", "code": "SKU", "quantity": 0, "unit_price": 1}]},
    {"grand_total": 999},
])
async def test_plan_blocks_unsafe_local_proposals_before_any_write(changes):
    read = AsyncMock(return_value={"data": []})
    with pytest.raises(BlingOrderValidationError):
        await build_sales_order_plan(proposal(**changes), read)


async def test_plan_rejects_non_unique_contact_or_product_matches():
    read = AsyncMock(return_value={"data": [
        {"id": 1, "numeroDocumento": "12345678000199"},
        {"id": 2, "numeroDocumento": "12345678000199"},
    ]})
    with pytest.raises(BlingOrderValidationError, match="Cliente não encontrado"):
        await build_sales_order_plan(proposal(), read)
