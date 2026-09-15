"""Build proposal candidates from mapped standard import records."""
from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def parse_decimal(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(Decimal(text))
    except (InvalidOperation, ValueError):
        return default


def date_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value).strip()


def _group_key(record: dict[str, Any]) -> str:
    data = record.get("data") or {}
    explicit = data.get("proposal_id") or data.get("proposal_code")
    return str(explicit).strip() if explicit not in (None, "") else str(record.get("id") or record.get("source_record_id"))


def build_proposal_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for record in records:
        groups.setdefault(_group_key(record), []).append(record)

    candidates = []
    for key, grouped_records in groups.items():
        first = grouped_records[0].get("data") or {}
        items = []
        errors = []
        for record in grouped_records:
            data = record.get("data") or {}
            quantity = parse_decimal(data.get("item_quantity"), 1.0)
            item_total = parse_decimal(data.get("item_total"))
            unit_price = parse_decimal(data.get("item_unit_price") or data.get("product_price"))
            if not unit_price and item_total and quantity:
                unit_price = round(item_total / quantity, 2)
            name = str(data.get("item_description") or data.get("product_description") or first.get("proposal_description") or "Item importado").strip()
            if quantity <= 0:
                errors.append("Quantidade inválida")
            if unit_price < 0:
                errors.append("Preço unitário inválido")
            items.append({
                "product_id": "",
                "name": name or "Item importado",
                "description": str(data.get("item_description") or data.get("product_description") or "").strip(),
                "unit": str(data.get("item_unit") or data.get("product_unit") or "UN").strip() or "UN",
                "quantity": quantity,
                "unit_price": unit_price,
            })

        client_name = str(first.get("client_name") or first.get("client_legal_name") or "").strip()
        if not client_name:
            errors.append("Cliente não identificado")
        client_document = str(first.get("client_document") or "").strip()
        if not client_document:
            errors.append("Documento do cliente não identificado")
        proposal_total = parse_decimal(first.get("proposal_net_total") or first.get("proposal_total") or first.get("financial_total"))
        if proposal_total and len(items) == 1 and not items[0]["unit_price"]:
            items[0]["unit_price"] = round(proposal_total / items[0]["quantity"], 2) if items[0]["quantity"] else 0
        calculated_total = round(sum(item["quantity"] * item["unit_price"] for item in items), 2)
        if calculated_total <= 0:
            errors.append("Valor da proposta não identificado")

        candidates.append({
            "group_key": key,
            "source_record_ids": [record.get("id") for record in grouped_records],
            "proposal_code": str(first.get("proposal_code") or first.get("proposal_id") or key),
            "proposal_date": date_text(first.get("proposal_date")),
            "client_name": client_name,
            "client_document": client_document,
            "client_phone": str(first.get("client_phone") or "").strip(),
            "client_email": str(first.get("client_email") or "").strip(),
            "client_company": str(first.get("client_legal_name") or "").strip(),
            "client_city": str(first.get("client_city") or "").strip(),
            "client_state": str(first.get("client_state") or "").strip(),
            "client_address": str(first.get("client_address") or "").strip(),
            "description": str(first.get("proposal_description") or "").strip(),
            "discount": parse_decimal(first.get("proposal_discount")),
            "payment_terms": str(first.get("payment_condition") or first.get("payment_method") or "").strip(),
            "items": items,
            "calculated_total": calculated_total,
            "errors": sorted(set(errors)),
            "ready": not errors,
        })
    return candidates
