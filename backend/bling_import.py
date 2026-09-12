"""Validation and normalization for explicitly confirmed Bling proposal imports."""
from decimal import Decimal, InvalidOperation


class BlingImportValidationError(ValueError):
    """Raised when a read-only Bling detail is not safe to materialize."""


def _amount(value, field: str, *, positive: bool = False) -> float:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BlingImportValidationError(f"{field} não informado") from exc
    if not number.is_finite() or (number <= 0 if positive else number < 0):
        qualifier = "maior que zero" if positive else "maior ou igual a zero"
        raise BlingImportValidationError(f"{field} deve ser {qualifier}")
    return float(number)


def build_proposal_input(detail: dict) -> dict:
    """Turn a provider-whitelisted detail into a ProposalIn-compatible payload.

    This intentionally accepts only the normalized result of ``fetch_detail``;
    provider response fields never flow directly into a local proposal.
    """
    external_id = str(detail.get("external_id") or "").strip()
    if not external_id:
        raise BlingImportValidationError("Identificador Bling não informado")
    client_name = str(detail.get("client_name") or "").strip()
    if not client_name or client_name == "Cliente não informado":
        raise BlingImportValidationError("Cliente não informado pelo Bling")

    source_items = detail.get("items")
    if not isinstance(source_items, list) or not source_items:
        raise BlingImportValidationError("A proposta não possui itens para importar")

    products: list[dict] = []
    subtotal = 0.0
    for index, item in enumerate(source_items, start=1):
        if not isinstance(item, dict):
            raise BlingImportValidationError(f"Item {index} inválido")
        name = str(item.get("description") or "").strip()
        if not name or name == "Item sem descrição":
            raise BlingImportValidationError(f"Item {index} sem descrição")
        quantity = _amount(item.get("quantity"), f"Quantidade do item {index}", positive=True)
        unit_price = _amount(item.get("unit_price"), f"Preço unitário do item {index}")
        subtotal += quantity * unit_price
        products.append({
            "name": name,
            "description": "",
            "quantity": quantity,
            "unit_price": unit_price,
            "unit": str(item.get("unit") or "UN").strip() or "UN",
        })

    total = _amount(detail.get("total"), "Total da proposta")
    # Proposal Já supports discounts but not an import surcharge. Preserve a
    # Bling discount when calculable; record any other total difference as a note.
    discount = round(max(subtotal - total, 0.0), 2)
    number = str(detail.get("number") or external_id).strip()
    note = f"Importada do Bling · proposta {number} · ID externo {external_id}."
    if round(subtotal - discount, 2) != round(total, 2):
        note += f" Total informado pelo Bling: R$ {total:.2f}."

    return {
        "client_name": client_name,
        "client_document": str(detail.get("document") or "").strip(),
        "client_phone": "",
        "products": products,
        "shipping_deadline": "A combinar",
        "notes": note,
        "discount": discount,
        "source": {
            "provider": "bling",
            "external_id": external_id,
            "external_number": number,
            "provider_total": total,
        },
    }
