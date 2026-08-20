from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.requests import Request

from whatsapp_integration import parse_webhook_events, verify_webhook_challenge, verify_webhook_signature

pytestmark = pytest.mark.integration


@pytest.fixture
async def webhook_db():
    name = os.environ["TEST_DB_NAME"]
    if name != "proposta_ja_test":
        pytest.fail(f"SAFETY STOP: expected proposta_ja_test, got {name}")
    client = AsyncIOMotorClient(os.environ["TEST_MONGO_URL"], serverSelectionTimeoutMS=5000)
    try:
        await client[name].command("ping")
    except Exception as exc:
        client.close()
        pytest.skip(f"Mongo unavailable: {exc}")
    yield client[name]
    client.close()


def webhook_request(payload: dict, secret: str, valid=True) -> Request:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    signature = f"sha256={digest if valid else '0' * 64}"
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": raw, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/api/webhooks/whatsapp", "headers": [(b"x-hub-signature-256", signature.encode())], "query_string": b""}, receive)


def payload(status="delivered", provider_id="wamid.1", phone="5511999999999"):
    value = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": "phone-id"}}
    if status == "received":
        value.update({"contacts": [{"wa_id": phone, "profile": {"name": "Cliente"}}], "messages": [{"from": phone, "id": provider_id, "timestamp": "1750000000", "type": "text", "text": {"body": "Olá"}}]})
    else:
        value["statuses"] = [{"id": provider_id, "status": status, "timestamp": "1750000000", "recipient_id": phone}]
    return {"object": "whatsapp_business_account", "entry": [{"id": "waba-id", "changes": [{"field": "messages", "value": value}]}]}


def test_signature_challenge_and_event_parser():
    raw = b'{"object":"whatsapp_business_account"}'
    signature = "sha256=" + hmac.new(b"secret", raw, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(raw, signature, "secret") is True
    assert verify_webhook_signature(raw, "sha256=bad", "secret") is False
    assert verify_webhook_challenge("subscribe", "123", "verify", "verify") == "123"
    with pytest.raises(ValueError):
        verify_webhook_challenge("subscribe", "123", "wrong", "verify")
    assert parse_webhook_events(payload())[0]["event_type"] == "DELIVERED"
    assert parse_webhook_events(payload("received"))[0]["event_type"] == "RECEIVED"


@pytest.mark.asyncio
async def test_webhook_signature_replay_statuses_and_unknown_event(webhook_db, monkeypatch):
    import server

    company = "webhook-" + uuid.uuid4().hex
    monkeypatch.setenv("WHATSAPP_CONFIG_COMPANY_ID", company)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    monkeypatch.setenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "waba-id")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setattr(server, "db", webhook_db)
    try:
        message = {"company_id": company, "message_id": "wa-1", "provider_message_id": "wamid.1", "status": "SENT", "created_at": "2026-08-15T00:00:00+00:00"}
        await webhook_db.whatsapp_messages.insert_one(message)
        result = await server.receive_whatsapp_webhook(webhook_request(payload(), "app-secret"))
        replay = await server.receive_whatsapp_webhook(webhook_request(payload(), "app-secret"))
        stored = await webhook_db.whatsapp_messages.find_one({"message_id": "wa-1"}, {"_id": 0})
        assert result["processed"] == 1
        assert replay["duplicates"] == 1
        assert stored["status"] == "DELIVERED"
        unknown = payload("played", "wamid.2")
        parsed = parse_webhook_events(unknown)[0]
        assert parsed["event_type"] == "UNKNOWN"
        with pytest.raises(Exception):
            await server.receive_whatsapp_webhook(webhook_request(payload(), "app-secret", valid=False))
    finally:
        for collection in ["whatsapp_messages", "whatsapp_webhook_events", "audit_logs"]:
            await webhook_db[collection].delete_many({"company_id": company})


@pytest.mark.asyncio
async def test_inbound_correlation_and_opt_out_no_auto_reply(webhook_db, monkeypatch):
    import server

    company = "inbound-" + uuid.uuid4().hex
    client_id = "client-" + uuid.uuid4().hex
    monkeypatch.setenv("WHATSAPP_CONFIG_COMPANY_ID", company)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "app-secret")
    monkeypatch.setenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "waba-id")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setattr(server, "db", webhook_db)
    try:
        await webhook_db.clients.insert_one({"company_id": company, "id": client_id, "phone": "+55 11 99999-9999", "deleted": False})
        inbound = payload("received", "wamid.inbound")
        inbound["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"] = "PARAR"
        result = await server.receive_whatsapp_webhook(webhook_request(inbound, "app-secret"))
        consent = await webhook_db.whatsapp_recipient_consents.find_one({"company_id": company, "client_id": client_id}, {"_id": 0})
        conversation = await webhook_db.whatsapp_conversations.find_one({"company_id": company, "client_id": client_id}, {"_id": 0})
        messages = await webhook_db.whatsapp_messages.find({"company_id": company}, {"_id": 0}).to_list(None)
        assert result["processed"] == 1
        assert consent["status"] == "OPTED_OUT"
        assert conversation["last_received_at"]
        assert len(messages) == 1
        assert messages[0]["direction"] == "INBOUND"
        assert messages[0]["correlation"] == "MATCHED"
        assert not any(item.get("direction") == "OUTBOUND" for item in messages)
    finally:
        for collection in ["clients", "whatsapp_messages", "whatsapp_webhook_events", "whatsapp_recipient_consents", "whatsapp_conversations", "audit_logs"]:
            await webhook_db[collection].delete_many({"company_id": company})
