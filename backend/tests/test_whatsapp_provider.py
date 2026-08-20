from datetime import datetime, timedelta, timezone

import pytest

from whatsapp_integration import (
    WhatsAppConfiguration,
    WhatsAppProviderFactory,
    build_internal_payload,
    customer_window_state,
    idempotency_key,
    normalize_brazil_phone,
    prepare_whatsapp_message,
    to_meta_payload,
    transition_status,
    validate_template,
)

pytestmark = pytest.mark.unit


def config(**overrides):
    values = {"enabled": False, "sandbox_enabled": False, "live_enabled": False, "require_human_approval": True, "allow_external_side_effects": False, "global_kill_switch": True}
    values.update(overrides)
    return WhatsAppConfiguration(**values)


def documents(mode="SIMULATION", phone="+55 11 99999-9999", draft_status="APPROVED"):
    company = "company-1"
    draft = {"company_id": company, "message_draft_id": "draft-1", "communication_request_id": "comm-1", "execution_job_id": "job-1", "opportunity_id": "opp-1", "status": draft_status, "human_approved": draft_status == "APPROVED", "source_snapshot_hash": "hash-1", "content": {"opening": "Olá.", "body": "Mensagem aprovada.", "call_to_action": "Pode responder?", "closing": "Obrigado."}, "edited_content": None}
    communication = {"company_id": company, "request_id": "comm-1", "status": "PREPARED"}
    job = {"company_id": company, "execution_job_id": "job-1", "status": "CREATED"}
    client = {"company_id": company, "id": "client-1", "phone": phone}
    consent = {"status": "OPTED_IN", "blocked": False}
    return company, draft, communication, job, client, mode, consent


def approved_template():
    return {"name": "hello_world", "version": "1", "language": "en_US", "category": "UTILITY", "status": "APPROVED", "variables": [], "resolved_variables": {}}


def test_configuration_defaults_are_fail_closed_and_secrets_not_public():
    cfg = WhatsAppConfiguration.from_env({})
    assert cfg.enabled is False
    assert cfg.sandbox_enabled is False
    assert cfg.live_enabled is False
    assert cfg.require_human_approval is True
    assert cfg.allow_external_side_effects is False
    assert cfg.global_kill_switch is True
    assert "access_token" not in cfg.public_state()
    assert "app_secret" not in cfg.public_state()


def test_configuration_rejects_partial_sandbox_and_live():
    with pytest.raises(ValueError, match="KILL_SWITCH"):
        config(enabled=True, sandbox_enabled=True).validate("SANDBOX", "company-1")
    cfg = config(enabled=True, sandbox_enabled=True, global_kill_switch=False, allow_external_side_effects=True, configured_company_id="company-1")
    with pytest.raises(ValueError, match="CONFIGURATION_INCOMPLETE"):
        cfg.validate("SANDBOX", "company-1")
    with pytest.raises(ValueError, match="LIVE_DISABLED"):
        cfg.validate("LIVE", "company-1")


def test_brazil_phone_normalization_never_adds_country_code_silently():
    valid = normalize_brazil_phone("+55 (11) 99999-9999")
    assert valid.normalized_phone == "+5511999999999"
    assert valid.normalization_rule == "REMOVED_FORMATTING_ONLY"
    local = normalize_brazil_phone("11999999999")
    assert local.valid is False
    assert local.normalized_phone is None
    assert local.normalization_rule == "COUNTRY_CODE_REQUIRED"


def test_customer_window_and_template_contract():
    now = datetime.now(timezone.utc)
    assert customer_window_state(None, now)["template_required"] is True
    conversation = {"last_received_at": (now - timedelta(hours=2)).isoformat()}
    assert customer_window_state(conversation, now)["template_required"] is False
    validate_template(approved_template(), True)
    with pytest.raises(ValueError, match="TEMPLATE_REQUIRED"):
        validate_template(None, True)
    bad = {**approved_template(), "status": "PAUSED"}
    with pytest.raises(ValueError, match="NOT_APPROVED"):
        validate_template(bad, True)


def test_prepare_message_is_deterministic_and_requires_opt_in_template():
    company, draft, communication, job, client, mode, consent = documents()
    first = prepare_whatsapp_message(company, draft, communication, job, client, mode, consent, None, approved_template())
    second = prepare_whatsapp_message(company, draft, communication, job, client, mode, consent, None, approved_template())
    assert first["message_id"] == second["message_id"]
    assert first["idempotency_key"] == second["idempotency_key"]
    assert first["status"] == "PREPARED"
    blocked = prepare_whatsapp_message(company, draft, communication, job, client, mode, {"status": "UNKNOWN"}, None, approved_template())
    assert blocked["status"] == "BLOCKED"
    assert blocked["reason"] == "OPT_IN_REQUIRED"


def test_internal_payload_and_meta_translation_are_separated():
    company, draft, communication, job, client, mode, consent = documents()
    message = prepare_whatsapp_message(company, draft, communication, job, client, mode, consent, None, approved_template())
    internal = message["payload"]
    assert set(internal) == {"recipient", "message_type", "content", "template", "variables"}
    meta = to_meta_payload(internal, message["idempotency_key"])
    assert meta["messaging_product"] == "whatsapp"
    assert meta["type"] == "template"
    assert meta["biz_opaque_callback_data"] == message["idempotency_key"]


def test_factory_has_simulation_sandbox_live_without_silent_fallback():
    cfg = config()
    assert WhatsAppProviderFactory.create("SIMULATION", cfg).name == "whatsapp_simulation"
    assert WhatsAppProviderFactory.create("SANDBOX", cfg).name == "meta_whatsapp_cloud_api"
    assert WhatsAppProviderFactory.create("LIVE", cfg).name == "meta_whatsapp_cloud_api"
    with pytest.raises(ValueError, match="INVALID_WHATSAPP_MODE"):
        WhatsAppProviderFactory.create("OTHER", cfg)


def test_status_transitions_reject_impossible_paths():
    assert transition_status("PREPARED", "APPROVED") == "APPROVED"
    assert transition_status("APPROVED", "SENDING") == "SENDING"
    assert transition_status("SENDING", "SENT") == "SENT"
    assert transition_status("SENT", "DELIVERED") == "DELIVERED"
    assert transition_status("DELIVERED", "READ") == "READ"
    with pytest.raises(ValueError, match="INVALID_STATUS_TRANSITION"):
        transition_status("PREPARED", "SENT")


def test_ten_thousand_payloads_under_twenty_seconds():
    import time

    company, draft, communication, job, client, mode, consent = documents()
    started = time.perf_counter()
    keys = set()
    for index in range(10000):
        current = {**draft, "message_draft_id": f"draft-{index}", "source_snapshot_hash": f"hash-{index}"}
        message = prepare_whatsapp_message(company, current, communication, job, client, mode, consent, None, approved_template())
        keys.add(message["idempotency_key"])
    assert time.perf_counter() - started < 20
    assert len(keys) == 10000
