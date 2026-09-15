"""Tenant-scoped outbound proposal webhooks with signed, auditable delivery."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from ipaddress import ip_address
from urllib.parse import urlparse

import requests
from cryptography.fernet import Fernet


EVENTS = frozenset({"proposal.created", "proposal.accepted", "bling.sales_order.created"})


class WebhookValidationError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fernet() -> Fernet:
    # A deterministic encryption key keeps webhook secrets out of MongoDB
    # plaintext without introducing a new mandatory Render variable.
    seed = hashlib.sha256(os.environ["JWT_SECRET"].encode()).digest()
    return Fernet(base64.urlsafe_b64encode(seed))


def validate_url(value: str) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise WebhookValidationError("A URL do webhook deve usar HTTPS e não pode conter credenciais")
    hostname = parsed.hostname or ""
    if hostname.lower() == "localhost":
        raise WebhookValidationError("A URL do webhook não pode apontar para localhost")
    try:
        address = ip_address(hostname)
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise WebhookValidationError("A URL do webhook não pode apontar para um endereço interno")
    except ValueError:
        pass
    return url


def validate_events(values: list[str]) -> list[str]:
    events = sorted({str(value).strip() for value in values if str(value).strip()})
    if not events or any(event not in EVENTS for event in events):
        raise WebhookValidationError("Selecione ao menos um evento suportado")
    return events


def public_config(record: dict, *, secret: str | None = None) -> dict:
    result = {key: record.get(key) for key in ("id", "url", "events", "enabled", "created_at", "updated_at")}
    result["has_secret"] = bool(record.get("secret_encrypted"))
    if secret:
        result["secret"] = secret
    return result


def new_webhook_secret() -> tuple[str, str]:
    """Return a plaintext secret once and its encrypted value for storage."""
    secret = secrets.token_urlsafe(32)
    return secret, _fernet().encrypt(secret.encode()).decode()


def proposal_payload(event: str, proposal: dict, company: dict) -> dict:
    event_id = str(uuid.uuid4())
    items = [
        {
            "sku": item.get("code") or "",
            "description": item.get("description") or item.get("name") or "",
            "quantity": item.get("quantity"),
            "unit_price": item.get("unit_price", item.get("price")),
        }
        for item in proposal.get("products", []) if isinstance(item, dict)
    ]
    code = proposal.get("public_code") or proposal.get("id")
    return {
        "schema_version": "1.0",
        "event": event,
        "event_id": event_id,
        "occurred_at": _now(),
        "company_id": proposal.get("company_id"),
        "proposal": {
            "id": proposal.get("id"),
            "number": code,
            "status": proposal.get("acceptance_status") if event == "proposal.accepted" else proposal.get("status"),
            "proposal_url": f"https://app.propostaapp.com.br/p/{code}",
            "pdf_url": f"{os.getenv('PUBLIC_API_URL', 'https://projeto-app-proposta-ja.onrender.com').rstrip('/')}/api/public/proposals/code/{code}/pdf",
        },
        "client": {
            "name": proposal.get("client_name") or "",
            "document": proposal.get("client_document") or "",
            "phone": proposal.get("client_phone") or "",
            "email": proposal.get("client_email") or "",
        },
        "financial": {"total": proposal.get("grand_total", proposal.get("total", 0)), "discount": proposal.get("discount", 0), "currency": proposal.get("currency") or "BRL"},
        "items": items,
        "commercial_terms": {"lead_time": proposal.get("shipping_deadline") or proposal.get("delivery_days") or "", "freight": proposal.get("incoterm") or proposal.get("shipping_type") or "", "warranty_months": proposal.get("warranty") or ""},
        "company": {"name": company.get("company_name") or "", "document": company.get("cnpj") or ""},
        "bling": {"sales_order_id": proposal.get("bling_order_id") or None},
    }


def _n8n_json_bytes(payload: dict) -> bytes:
    """Serialize JSON in the same numeric form produced by JavaScript JSON.stringify.

    The n8n webhook node parses JSON before the Code node verifies it. JavaScript
    serializes integral floats as ``0`` while Python's json.dumps emits ``0.0``.
    Normalizing them before both sending and signing keeps the HMAC reproducible.
    """
    def normalize(value):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    return json.dumps(normalize(payload), ensure_ascii=False, separators=(",", ":")).encode()


async def emit_proposal_event(database, event: str, proposal: dict, company: dict) -> None:
    """Persist every delivery before sending it; failures stay visible for retry."""
    if event not in EVENTS:
        return
    configs = await database.outbound_webhooks.find({"company_id": proposal["company_id"], "enabled": True, "events": event}, {"_id": 0}).to_list(100)
    for config in configs:
        payload = proposal_payload(event, proposal, company)
        delivery = {"id": str(uuid.uuid4()), "company_id": proposal["company_id"], "webhook_id": config["id"], "event": event, "event_id": payload["event_id"], "proposal_id": proposal["id"], "status": "PENDING", "attempts": 0, "payload": payload, "created_at": _now(), "updated_at": _now()}
        await database.outbound_webhook_deliveries.insert_one(delivery)
        asyncio.create_task(deliver(database, delivery, config))


async def deliver(database, delivery: dict, config: dict) -> None:
    body = _n8n_json_bytes(delivery["payload"])
    secret = _fernet().decrypt(config["secret_encrypted"].encode()).decode()
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    signature = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    try:
        response = await asyncio.to_thread(requests.post, config["url"], data=body, headers={"Content-Type": "application/json", "User-Agent": "PropostaJa-Webhooks/1.0", "X-PropostaJa-Event": delivery["event"], "X-PropostaJa-Event-Id": delivery["event_id"], "X-PropostaJa-Timestamp": timestamp, "X-PropostaJa-Signature": f"sha256={signature}"}, timeout=12, allow_redirects=False)
        status = "DELIVERED" if 200 <= response.status_code < 300 else "FAILED"
        update = {"status": status, "attempts": int(delivery.get("attempts", 0)) + 1, "response_status": response.status_code, "last_error": None if status == "DELIVERED" else f"HTTP {response.status_code}", "updated_at": _now()}
    except requests.RequestException as exc:
        update = {"status": "FAILED", "attempts": int(delivery.get("attempts", 0)) + 1, "response_status": None, "last_error": str(exc)[:300], "updated_at": _now()}
    await database.outbound_webhook_deliveries.update_one({"id": delivery["id"]}, {"$set": update})


async def retry_delivery(database, company_id: str, delivery_id: str) -> dict:
    delivery = await database.outbound_webhook_deliveries.find_one({"id": delivery_id, "company_id": company_id}, {"_id": 0})
    if not delivery:
        raise WebhookValidationError("Entrega não encontrada")
    config = await database.outbound_webhooks.find_one({"id": delivery["webhook_id"], "company_id": company_id}, {"_id": 0})
    if not config:
        raise WebhookValidationError("Webhook da entrega não encontrado")
    await deliver(database, delivery, config)
    return await database.outbound_webhook_deliveries.find_one({"id": delivery_id, "company_id": company_id}, {"_id": 0})


def new_webhook_record(company_id: str, url: str, events: list[str]) -> tuple[dict, str]:
    secret, secret_encrypted = new_webhook_secret()
    now = _now()
    return ({"id": "wh_" + uuid.uuid4().hex, "company_id": company_id, "url": validate_url(url), "events": validate_events(events), "enabled": True, "secret_encrypted": secret_encrypted, "created_at": now, "updated_at": now}, secret)
