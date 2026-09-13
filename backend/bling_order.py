"""Safe planning for an explicit Proposal Já -> Bling sales order export."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException


class BlingOrderValidationError(ValueError):
    """The current local proposal cannot safely become a Bling sales order."""


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _number(value: object, label: str, *, positive: bool = False) -> float:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BlingOrderValidationError(f"{label} inválido") from exc
    if not result.is_finite() or (result <= 0 if positive else result < 0):
        raise BlingOrderValidationError(f"{label} deve ser {'maior que zero' if positive else 'maior ou igual a zero'}")
    return float(result)


def _records(payload: dict) -> list[dict]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        data = [data]
    return [record for record in data if isinstance(record, dict)] if isinstance(data, list) else []


async def _contact_for_document(read, document: str) -> dict:
    records = _records(await read("/contatos", {"numeroDocumento": document, "limite": 100}))
    exact = [record for record in records if _digits(record.get("numeroDocumento")) == document and record.get("id")]
    if len(exact) != 1:
        raise BlingOrderValidationError("Cliente não encontrado de forma única no Bling pelo CNPJ/CPF")
    record = exact[0]
    return {"id": int(record["id"]), "name": str(record.get("nome") or "").strip(), "document": document}


async def _product_for_code(read, code: str, item_index: int) -> dict:
    records = _records(await read("/produtos", {"codigo": code, "limite": 100}))
    exact = [record for record in records if str(record.get("codigo") or "").strip() == code and record.get("id")]
    if len(exact) != 1:
        raise BlingOrderValidationError(f"Item {item_index}: produto com código '{code}' não encontrado de forma única no Bling")
    record = exact[0]
    return {"id": int(record["id"]), "code": code, "name": str(record.get("nome") or "").strip()}


def _fingerprint(value: dict) -> str:
    serial = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serial.encode()).hexdigest()


async def build_sales_order_plan(proposal: dict, read) -> dict:
    """Resolve exact Bling identities and return a confirmation-bound order plan.

    No remote mutation occurs here. Names are informational; document and product
    code are the sole matching keys, avoiding accidental registrations or fuzzy
    matches.
    """
    if proposal.get("deleted"):
        raise BlingOrderValidationError("Proposta não encontrada")
    if proposal.get("status") != "aprovado" and proposal.get("acceptance_status") != "accepted":
        raise BlingOrderValidationError("Apenas propostas aprovadas podem gerar pedido no Bling")
    document = _digits(proposal.get("client_document"))
    if len(document) not in (11, 14):
        raise BlingOrderValidationError("Informe o CNPJ/CPF do cliente antes de gerar o pedido")
    source_items = proposal.get("products")
    if not isinstance(source_items, list) or not source_items:
        raise BlingOrderValidationError("A proposta não possui itens")

    contact = await _contact_for_document(read, document)
    planned_items = []
    payload_items = []
    subtotal = 0.0
    for index, item in enumerate(source_items, start=1):
        if not isinstance(item, dict):
            raise BlingOrderValidationError(f"Item {index} inválido")
        code = str(item.get("code") or "").strip()
        if not code:
            raise BlingOrderValidationError(f"Item {index}: informe o código do produto cadastrado no Bling")
        product = await _product_for_code(read, code, index)
        quantity = _number(item.get("quantity"), f"Quantidade do item {index}", positive=True)
        price = _number(item.get("unit_price", item.get("price")), f"Preço do item {index}")
        unit = str(item.get("unit") or "UN").strip() or "UN"
        total = round(quantity * price, 2)
        subtotal += total
        planned_items.append({"local_name": str(item.get("name") or "").strip(), "code": code, "quantity": quantity,
                              "unit": unit, "unit_price": price, "total": total, "bling_product": product})
        payload_items.append({"quantidade": quantity, "valor": price, "codigo": code, "unidade": unit, "produto": {"id": product["id"]}})

    subtotal = round(subtotal, 2)
    discount = _number(proposal.get("discount") or 0, "Desconto")
    total = round(subtotal - discount, 2)
    proposal_total = _number(proposal.get("grand_total", proposal.get("total")), "Total da proposta")
    if total < 0 or round(total, 2) != round(proposal_total, 2):
        raise BlingOrderValidationError("O total da proposta não confere com itens e desconto; revise a proposta antes de gerar o pedido")

    notes = f"Criado pelo Proposta Já a partir da proposta {proposal.get('id')}."
    order_payload = {"contato": {"id": contact["id"]}, "itens": payload_items, "observacoes": notes}
    if discount:
        order_payload["desconto"] = {"valor": discount, "unidade": "REAL"}
    plan = {"proposal_id": str(proposal["id"]), "client": {"name": proposal.get("client_name"), "document": document, "bling_contact": contact},
            "items": planned_items, "subtotal": subtotal, "discount": discount, "total": total, "order_payload": order_payload}
    plan["fingerprint"] = _fingerprint(plan)
    return plan

