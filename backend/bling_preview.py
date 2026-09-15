"""Read-only Bling preview; only encrypted OAuth credentials may be updated."""
import asyncio
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

from bling_oauth import BlingApiError, BlingOAuthError


def external_id(value):
    value = str(value)
    if not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise HTTPException(422, "Identificador Bling inválido")
    return value


async def read_preview(credentials, configuration, company_id, path, params=None):
    if not re.fullmatch(r"/(propostas-comerciais(?:/[1-9][0-9]{0,19})?|contatos(?:/[1-9][0-9]{0,19})?|produtos)", path):
        raise HTTPException(422, "Consulta Bling não permitida")
    scope = {"company_id": company_id, "provider": "bling"}
    credential = await credentials.find_one(scope)
    if not credential:
        raise HTTPException(409, "Conecte sua conta Bling")

    async def get(token):
        return await asyncio.to_thread(configuration.get_json, path, token, params)

    try:
        try:
            return await get(configuration.decrypt(credential["access_token_encrypted"]))
        except BlingApiError as exc:
            if exc.status_code != 401:
                raise
        # A database lease also protects refresh-token rotation across workers.
        now = datetime.now(timezone.utc)
        lease = uuid.uuid4().hex
        claim = await credentials.update_one(
            {**scope, "access_token_encrypted": credential["access_token_encrypted"],
             "$or": [{"refresh_lease_until": {"$exists": False}}, {"refresh_lease_until": {"$lt": now.isoformat()}}]},
            {"$set": {"refresh_lease": lease, "refresh_lease_until": (now + timedelta(seconds=60)).isoformat()}},
        )
        if not claim.modified_count:
            latest = await credentials.find_one(scope)
            if latest and latest["access_token_encrypted"] != credential["access_token_encrypted"]:
                return await get(configuration.decrypt(latest["access_token_encrypted"]))
            raise HTTPException(409, "Autorização Bling em renovação. Tente consultar novamente.")
        try:
            tokens = await asyncio.to_thread(configuration.refresh_access_token, configuration.decrypt(credential["refresh_token_encrypted"]))
            saved = await credentials.update_one(
                {**scope, "refresh_lease": lease, "access_token_encrypted": credential["access_token_encrypted"]},
                {"$set": {"access_token_encrypted": configuration.encrypt(tokens["access_token"]),
                          "refresh_token_encrypted": configuration.encrypt(tokens["refresh_token"]),
                          "expires_in": tokens.get("expires_in"), "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            if not saved.modified_count:
                raise HTTPException(409, "A conexão Bling mudou. Consulte novamente.")
        finally:
            await credentials.update_one({**scope, "refresh_lease": lease}, {"$unset": {"refresh_lease": "", "refresh_lease_until": ""}})
        return await get(tokens["access_token"])
    except BlingApiError as exc:
        messages = {401: "Reconecte sua conta Bling", 403: "O aplicativo Bling não possui permissão de leitura", 404: "Registro não encontrado no Bling", 429: "Limite de consultas do Bling atingido. Tente novamente em instantes."}
        raise HTTPException(exc.status_code if exc.status_code in messages else 502, messages.get(exc.status_code, "Não foi possível consultar a prévia do Bling")) from exc
    except BlingOAuthError as exc:
        raise HTTPException(502, "Não foi possível consultar o Bling. Tente novamente ou reconecte sua conta.") from exc


async def write_sales_order(credentials, configuration, company_id, payload, *, path="/pedidos/vendas", entity_name="pedido"):
    """Write one Bling resource, refreshing only after a 401.

    A transport error is intentionally surfaced to the caller without a retry: the
    provider may have received the request even when its response was lost.
    """
    scope = {"company_id": company_id, "provider": "bling"}
    credential = await credentials.find_one(scope)
    if not credential:
        raise HTTPException(409, "Conecte sua conta Bling")

    async def post(token):
        return await asyncio.to_thread(configuration.post_json, path, token, payload)

    try:
        try:
            return await post(configuration.decrypt(credential["access_token_encrypted"]))
        except BlingApiError as exc:
            if exc.status_code != 401:
                raise

        now = datetime.now(timezone.utc)
        lease = uuid.uuid4().hex
        claim = await credentials.update_one(
            {**scope, "access_token_encrypted": credential["access_token_encrypted"],
             "$or": [{"refresh_lease_until": {"$exists": False}}, {"refresh_lease_until": {"$lt": now.isoformat()}}]},
            {"$set": {"refresh_lease": lease, "refresh_lease_until": (now + timedelta(seconds=60)).isoformat()}},
        )
        if not claim.modified_count:
            latest = await credentials.find_one(scope)
            if latest and latest["access_token_encrypted"] != credential["access_token_encrypted"]:
                return await post(configuration.decrypt(latest["access_token_encrypted"]))
            raise HTTPException(409, "Autorização Bling em renovação. Tente criar o pedido novamente.")
        try:
            tokens = await asyncio.to_thread(configuration.refresh_access_token, configuration.decrypt(credential["refresh_token_encrypted"]))
            saved = await credentials.update_one(
                {**scope, "refresh_lease": lease, "access_token_encrypted": credential["access_token_encrypted"]},
                {"$set": {"access_token_encrypted": configuration.encrypt(tokens["access_token"]),
                          "refresh_token_encrypted": configuration.encrypt(tokens["refresh_token"]),
                          "expires_in": tokens.get("expires_in"), "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            if not saved.modified_count:
                raise HTTPException(409, "A conexão Bling mudou. Revise a prévia novamente.")
        finally:
            await credentials.update_one({**scope, "refresh_lease": lease}, {"$unset": {"refresh_lease": "", "refresh_lease_until": ""}})
        return await post(tokens["access_token"])
    except BlingApiError as exc:
        messages = {401: "Reconecte sua conta Bling", 403: f"O aplicativo Bling não possui permissão para criar {entity_name}", 404: "Registro não encontrado no Bling", 429: "Limite do Bling atingido. Tente novamente em instantes."}
        if exc.status_code in {400, 422}:
            raise HTTPException(422, f"O Bling recusou os dados de {entity_name}: {exc}") from exc
        raise HTTPException(exc.status_code if exc.status_code in messages else 502, messages.get(exc.status_code, f"Não foi possível criar {entity_name} no Bling")) from exc


def number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def proposal_detail(record, contact):
    items = record.get("itens", [])
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise HTTPException(502, "O Bling retornou itens inválidos")
    normalized = []
    for item in items:
        product = item.get("produto") if isinstance(item.get("produto"), dict) else {}
        quantity, price = number(item.get("quantidade")), number(item.get("valor"))
        normalized.append({"description": product.get("descricao") or item.get("descricaoDetalhada") or item.get("codigo") or "Item sem descrição",
                           "code": item.get("codigo") or product.get("codigo"), "quantity": quantity, "unit": item.get("unidade"),
                           "unit_price": price, "gross_total": quantity * price if quantity is not None and price is not None else None})
    return {"external_id": str(record.get("id", "")), "number": str(record.get("numero") or record.get("id", "")),
            "client_name": contact.get("nome") or "Cliente não informado", "document": contact.get("numeroDocumento") or None,
            "items": normalized, "total": number(record.get("total"))}


async def fetch_detail(read, proposal_id):
    payload = await read("/propostas-comerciais/" + external_id(proposal_id))
    record = payload.get("data")
    if not isinstance(record, dict) or str(record.get("id")) != str(proposal_id):
        raise HTTPException(502, "O Bling retornou uma proposta inválida")
    contact = record.get("contato") if isinstance(record.get("contato"), dict) else {}
    if contact.get("id"):
        contact_id = external_id(contact["id"])
        contact_payload = await read("/contatos/" + contact_id)
        contact = contact_payload.get("data")
        if not isinstance(contact, dict) or str(contact.get("id")) != contact_id:
            raise HTTPException(502, "O Bling retornou um cliente inválido")
    return {"mode": "PREVIEW", "read_only": True, "proposal": proposal_detail(record, contact)}
