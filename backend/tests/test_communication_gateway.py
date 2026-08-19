from datetime import datetime, timezone

import pytest

from communication_gateway import (
    COMMUNICATION_GATEWAY_VERSION,
    CommunicationAdapterFactory,
    build_communication_request,
    cancel_communication_request,
    communication_request_hash,
    simulate_communication_request,
)

pytestmark = pytest.mark.unit


def _documents(channel="WHATSAPP", action_type="FOLLOW_UP", mode="SIMULATION", phone="5511999999999", email="client@example.com"):
    company_id = "company-1"
    action = {"action_id": "action-1", "type": action_type, "channel": channel}
    plan = {"action_plan_id": "plan-1", "company_id": company_id, "opportunity_id": "opp-1", "status": "APPROVED", "actions": [action]}
    opportunity = {"id": "opp-1", "company_id": company_id, "client_id": "client-1"}
    client = {"id": "client-1", "company_id": company_id, "name": "Cliente", "phone": phone, "email": email}
    job = {
        "execution_job_id": "job-1", "company_id": company_id, "action_plan_id": "plan-1",
        "action_id": "action-1", "opportunity_id": "opp-1", "channel": channel,
        "action_type": action_type, "mode": mode, "status": "CREATED",
        "policy": {"requires_approval": True, "allow_external_side_effects": False, "max_attempts": 1},
        "payload": {"context": {"opportunity_id": "opp-1"}},
    }
    return company_id, job, plan, opportunity, client


def test_prepare_and_simulate_whatsapp_without_message_generation():
    request = build_communication_request(*_documents())
    assert request["status"] == "PREPARED"
    assert request["content"] == {"subject": None, "body": None, "template_id": None, "variables": {}}
    assert request["adapter"] == "whatsapp_simulation"
    simulated = simulate_communication_request(request)
    assert simulated["status"] == "SIMULATED"
    assert simulated["result"]["external_side_effect"] is False
    assert simulated["result"]["sent"] is False
    assert simulated["result"]["delivered"] is False


@pytest.mark.parametrize("channel,adapter", [
    ("WHATSAPP", "whatsapp_simulation"), ("EMAIL", "email_simulation"),
    ("PHONE", "phone_simulation"), ("SMS", "sms_simulation"),
    ("IN_PERSON", "in_person_simulation"),
])
def test_factory_returns_simulation_only_channel_adapters(channel, adapter):
    instance = CommunicationAdapterFactory.create(channel, "SIMULATION")
    assert instance.name == adapter
    assert instance.health_check()["external_connectivity"] is False


def test_dry_run_prepares_but_does_not_execute():
    request = build_communication_request(*_documents(mode="DRY_RUN"))
    result = simulate_communication_request(request)
    assert result["status"] == "PREPARED"
    assert result["result"]["details"] == {"dry_run": True}
    assert result["result"]["external_side_effect"] is False


def test_live_and_external_side_effects_are_explicitly_rejected():
    live = build_communication_request(*_documents(mode="LIVE"))
    assert live["status"] == "REJECTED"
    assert live["reason"] == "LIVE_MODE_NOT_AVAILABLE"
    documents = list(_documents())
    documents[1]["policy"]["allow_external_side_effects"] = True
    unsafe = build_communication_request(*documents)
    assert unsafe["status"] == "REJECTED"
    assert unsafe["reason"] == "EXTERNAL_SIDE_EFFECTS_FORBIDDEN"
    with pytest.raises(ValueError, match="LIVE_MODE_NOT_AVAILABLE"):
        CommunicationAdapterFactory.create("WHATSAPP", "LIVE")


@pytest.mark.parametrize("channel,phone,email", [
    ("WHATSAPP", None, "client@example.com"),
    ("PHONE", None, "client@example.com"),
    ("SMS", None, "client@example.com"),
    ("EMAIL", "5511999999999", None),
])
def test_missing_contact_is_blocked_without_invention(channel, phone, email):
    request = build_communication_request(*_documents(channel=channel, phone=phone, email=email))
    assert request["status"] == "BLOCKED"
    assert request["reason"] == "MISSING_RECIPIENT_CONTACT"
    assert request["recipient"]["phone"] == phone
    assert request["recipient"]["email"] == email


def test_in_person_needs_no_contact_and_unknown_is_blocked():
    in_person = build_communication_request(*_documents(channel="IN_PERSON", phone=None, email=None))
    assert in_person["status"] == "PREPARED"
    unknown = build_communication_request(*_documents(channel="UNKNOWN"))
    assert unknown["status"] == "BLOCKED"
    assert unknown["reason"] == "UNKNOWN_CHANNEL"


@pytest.mark.parametrize("action_type", ["NO_ACTION", "WAIT", "HUMAN_REVIEW"])
def test_non_communication_actions_are_blocked_without_internal_error(action_type):
    request = build_communication_request(*_documents(action_type=action_type))
    assert request["status"] == "BLOCKED"
    assert request["reason"] == "NOT_COMMUNICATION_ACTION"


@pytest.mark.parametrize("action_type", ["FOLLOW_UP", "CONTACT_CLIENT", "REQUEST_INFORMATION", "REVIEW_PROPOSAL", "REVIEW_PRICE"])
def test_communication_actions_are_accepted(action_type):
    request = build_communication_request(*_documents(action_type=action_type))
    assert request["status"] == "PREPARED"


@pytest.mark.parametrize("status", ["CANCELLED", "EXPIRED", "BLOCKED", "FAILED"])
def test_final_execution_job_states_are_not_communicable(status):
    documents = list(_documents())
    documents[1]["status"] = status
    request = build_communication_request(*documents)
    assert request["status"] == "BLOCKED"
    assert request["reason"] == "EXECUTION_JOB_NOT_COMMUNICABLE"


def test_tenant_and_required_field_validation():
    documents = list(_documents())
    documents[4]["company_id"] = "other"
    with pytest.raises(ValueError, match="TENANT_MISMATCH_CLIENT"):
        build_communication_request(*documents)
    documents = list(_documents())
    documents[1]["execution_job_id"] = None
    with pytest.raises(ValueError, match="MISSING_REQUIRED_FIELDS"):
        build_communication_request(*documents)


def test_hash_adapter_channel_and_status_are_deterministic_one_hundred_times():
    requests = [build_communication_request(*_documents(), now=datetime(2026, 1, 1, tzinfo=timezone.utc)) for _ in range(100)]
    assert len({item["communication_request_hash"] for item in requests}) == 1
    assert len({item["request_id"] for item in requests}) == 1
    assert {item["adapter"] for item in requests} == {"whatsapp_simulation"}
    assert {item["channel"] for item in requests} == {"WHATSAPP"}
    assert {item["status"] for item in requests} == {"PREPARED"}
    assert all(item["gateway_version"] == COMMUNICATION_GATEWAY_VERSION for item in requests)


def test_hash_ignores_timestamp_and_cancel_is_pre_simulation_only():
    first = build_communication_request(*_documents(), now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    second = build_communication_request(*_documents(), now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert first["communication_request_hash"] == second["communication_request_hash"]
    assert cancel_communication_request(first)["reason"] == "CANCELLED_BY_USER"
    with pytest.raises(ValueError, match="NOT_CANCELLABLE"):
        cancel_communication_request(simulate_communication_request(first))


def test_performance_ten_thousand_requests_under_limits_and_deterministic():
    import time
    import tracemalloc

    tracemalloc.start()
    started = time.perf_counter()
    results = []
    for index in range(10000):
        documents = list(_documents())
        documents[1]["execution_job_id"] = f"job-{index}"
        request = build_communication_request(*documents)
        results.append(simulate_communication_request(request))
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert elapsed < 20.0
    assert peak < 128 * 1024 * 1024
    assert all(item["status"] == "SIMULATED" for item in results)
    assert all(item["result"]["external_side_effect"] is False for item in results)
    assert len({item["communication_request_hash"] for item in results}) == 10000


def test_network_guard_intercepts_all_common_clients(monkeypatch):
    import http.client
    import smtplib
    import socket
    import urllib.request

    calls = []

    def blocked(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("external access attempted")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(smtplib.SMTP, "connect", blocked)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", blocked)
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    try:
        import requests
        monkeypatch.setattr(requests.sessions.Session, "request", blocked)
    except ImportError:
        pass
    try:
        import httpx
        monkeypatch.setattr(httpx.Client, "request", blocked)
        monkeypatch.setattr(httpx.AsyncClient, "request", blocked)
    except ImportError:
        pass
    try:
        import aiohttp
        monkeypatch.setattr(aiohttp.ClientSession, "_request", blocked)
    except ImportError:
        pass
    try:
        import websocket
        monkeypatch.setattr(websocket.WebSocket, "connect", blocked)
    except ImportError:
        pass
    for _ in range(1000):
        assert simulate_communication_request(build_communication_request(*_documents()))["status"] == "SIMULATED"
    assert calls == []
