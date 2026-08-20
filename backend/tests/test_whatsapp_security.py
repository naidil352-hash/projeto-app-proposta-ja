import inspect
import logging

import pytest

import whatsapp_integration
from whatsapp_integration import WhatsAppConfiguration, WhatsAppProviderFactory, validate_send_guards, whatsapp_configuration_for_company

pytestmark = pytest.mark.unit


def secure_configuration(**overrides):
    values = {
        "enabled": True, "sandbox_enabled": True, "live_enabled": False,
        "require_human_approval": True, "allow_external_side_effects": True,
        "global_kill_switch": False, "access_token": "secret-token", "phone_number_id": "phone-id",
        "business_account_id": "waba-id", "app_id": "app-id", "app_secret": "app-secret",
        "verify_token": "verify-secret", "configured_company_id": "company-1",
        "test_recipients": ("+5511999999999",),
    }
    values.update(overrides)
    return WhatsAppConfiguration(**values)


def guard_documents():
    message = {"status": "APPROVED", "recipient": {"normalized_phone": "+5511999999999"}}
    draft = {"status": "APPROVED", "human_approved": True}
    communication = {"status": "PREPARED"}
    job = {"status": "CREATED"}
    consent = {"status": "OPTED_IN", "blocked": False}
    usage = {"daily_count": 0, "monthly_count": 0, "daily_cost": 0, "monthly_cost": 0, "last_sent_at": None}
    template = {"name": "hello_world", "version": "1", "language": "en_US", "category": "UTILITY", "status": "APPROVED", "variables": [], "resolved_variables": {}}
    return message, draft, communication, job, consent, usage, template


def test_kill_switch_live_disabled_and_missing_approval_block():
    args = guard_documents()
    with pytest.raises(ValueError, match="KILL_SWITCH"):
        validate_send_guards("SANDBOX", secure_configuration(global_kill_switch=True), "company-1", *args[:4], args[4], args[5], args[6], None, True, 0)
    with pytest.raises(ValueError, match="LIVE_DISABLED"):
        validate_send_guards("LIVE", secure_configuration(), "company-1", *args[:4], args[4], args[5], args[6], None, True, 0)
    bad_draft = {**args[1], "status": "READY_FOR_REVIEW", "human_approved": False}
    with pytest.raises(ValueError, match="MISSING_APPROVAL"):
        validate_send_guards("SANDBOX", secure_configuration(), "company-1", args[0], bad_draft, args[2], args[3], args[4], args[5], args[6], None, True, 0)


def test_sandbox_whitelist_and_tenant_are_enforced():
    args = guard_documents()
    with pytest.raises(ValueError, match="SANDBOX_RECIPIENT_NOT_ALLOWED"):
        validate_send_guards("SANDBOX", secure_configuration(test_recipients=()), "company-1", *args[:4], args[4], args[5], args[6], None, True, 0)
    with pytest.raises(ValueError, match="TENANT_CONFIGURATION_MISMATCH"):
        validate_send_guards("SANDBOX", secure_configuration(), "other", *args[:4], args[4], args[5], args[6], None, True, 0)


def test_token_is_not_in_repr_public_state_or_source_logs(caplog):
    cfg = secure_configuration()
    assert "secret-token" not in repr(cfg)
    assert "secret-token" not in str(cfg.public_state())
    with caplog.at_level(logging.INFO):
        logging.info("health=%s", cfg.public_state())
    assert "secret-token" not in caplog.text


def test_frontend_style_values_cannot_override_configuration():
    cfg = WhatsAppConfiguration.from_env({"WHATSAPP_ENABLED": "false", "WHATSAPP_GLOBAL_KILL_SWITCH": "true"})
    assert cfg.enabled is False
    assert cfg.global_kill_switch is True
    assert not hasattr(cfg, "frontend_token")


def test_tenant_registry_keeps_tokens_and_phone_ids_separate():
    import json

    registry = {
        "company-a": {"WHATSAPP_ACCESS_TOKEN": "token-a", "WHATSAPP_PHONE_NUMBER_ID": "phone-a"},
        "company-b": {"WHATSAPP_ACCESS_TOKEN": "token-b", "WHATSAPP_PHONE_NUMBER_ID": "phone-b"},
    }
    env = {"WHATSAPP_TENANT_CONFIGS_JSON": json.dumps(registry)}
    config_a = whatsapp_configuration_for_company("company-a", env)
    config_b = whatsapp_configuration_for_company("company-b", env)
    assert config_a.access_token == "token-a"
    assert config_b.access_token == "token-b"
    assert config_a.phone_number_id != config_b.phone_number_id
    with pytest.raises(ValueError, match="CONFIGURATION_NOT_FOUND"):
        whatsapp_configuration_for_company("company-c", env)


@pytest.mark.asyncio
async def test_prepare_rejects_frontend_token_before_database_access():
    import json
    import server
    from starlette.requests import Request

    body = json.dumps({"mode": "SANDBOX", "access_token": "attacker-token"}).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b""}, receive)
    with pytest.raises(Exception) as exc:
        await server.prepare_whatsapp_send("draft-x", request, {"id": "user", "company_id": "company-1"})
    assert "Parâmetros de preparação não permitidos" in str(exc.value)


def test_provider_source_has_no_unofficial_whatsapp_clients_or_browser_automation():
    source = inspect.getsource(whatsapp_integration).lower()
    for forbidden in ["selenium", "puppeteer", "playwright", "whatsapp web", "qr code", "twilio"]:
        assert forbidden not in source
    assert "graph.facebook.com" in source


def test_unit_suite_network_guard(monkeypatch):
    import http.client
    import smtplib
    import socket
    import urllib.request

    calls = []

    def blocked(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(smtplib.SMTP, "connect", blocked)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", blocked)
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    provider = WhatsAppProviderFactory.create("SIMULATION", WhatsAppConfiguration())
    for _ in range(1000):
        result = provider.execute({"mode": "SIMULATION", "payload": {}})
        assert result["external_side_effect"] is False
    assert calls == []
