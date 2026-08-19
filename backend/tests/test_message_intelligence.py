from copy import deepcopy
from datetime import datetime, timezone

import pytest

from message_intelligence import (
    MESSAGE_INTELLIGENCE_VERSION,
    DeterministicMessageProvider,
    MessageProviderFactory,
    build_message_draft,
)

pytestmark = pytest.mark.unit


def _documents(action_type="FOLLOW_UP", channel="WHATSAPP", days=7, with_proposal=True, confidence=0.85):
    company_id = "company-1"
    opportunity = {"id": "opp-1", "company_id": company_id, "client_id": "client-1"}
    client = {"id": "client-1", "company_id": company_id, "name": "João", "phone": "5511999999999", "email": "joao@example.com"}
    proposal = {"id": "proposal-1", "company_id": company_id, "grand_total": 1250.75, "products": [{"description": "Produto existente"}]}
    context_proposal = {"proposal_id": "proposal-1", "proposal_value": 1250.75} if with_proposal else None
    context = {
        "context_id": "ctx-1", "company_id": company_id, "opportunity_id": "opp-1", "snapshot_version": "1.0.0",
        "context": {
            "opportunity": {"days_since_last_activity": days}, "proposal": context_proposal,
            "products": [{"description": "Produto existente"}] if with_proposal else [],
            "seller": {"seller_name": "Maria"}, "data_quality": "PARTIAL",
        },
    }
    insight = {
        "insight_id": "insight-1", "company_id": company_id, "opportunity_id": "opp-1", "context_id": "ctx-1",
        "confidence": confidence, "insight": {"price_signal": {"status": "UNKNOWN", "type": "UNKNOWN"}},
        "evidence": [{"source": "commercial_context", "field": "followup_state", "value": "OVERDUE", "calculation": "days=7"}],
    }
    action = {"action_id": "action-1", "type": action_type, "channel": channel, "reason": "Ação aprovada.", "status": "PENDING_APPROVAL"}
    plan = {
        "action_plan_id": "plan-1", "company_id": company_id, "opportunity_id": "opp-1", "sales_insight_id": "insight-1",
        "context_id": "ctx-1", "status": "APPROVED", "actions": [action],
    }
    job = {
        "execution_job_id": "job-1", "company_id": company_id, "action_plan_id": "plan-1", "action_id": "action-1",
        "opportunity_id": "opp-1", "channel": channel, "action_type": action_type, "mode": "SIMULATION",
        "policy": {"allow_external_side_effects": False},
    }
    communication = {
        "request_id": "comm-1", "company_id": company_id, "execution_job_id": "job-1", "action_plan_id": "plan-1",
        "action_id": "action-1", "opportunity_id": "opp-1", "channel": channel, "action_type": action_type,
        "recipient": {"client_id": "client-1", "name": "João", "phone": "5511999999999", "email": "joao@example.com"},
        "content": {"subject": None, "body": None, "template_id": None, "variables": {}},
        "context": {}, "policy": {"allow_external_side_effects": False}, "mode": "SIMULATION", "status": "PREPARED",
    }
    return company_id, job, communication, plan, opportunity, client, proposal, insight, context


def _draft(**kwargs):
    documents = list(_documents(**kwargs))
    return build_message_draft(*documents)


def test_follow_up_draft_is_review_only_and_explainable():
    draft = _draft()
    assert draft["status"] == "READY_FOR_REVIEW"
    assert draft["objective"] == "FOLLOW_UP"
    assert draft["strategy"] == "GENTLE_REACTIVATION"
    assert draft["tone"] == "PROFESSIONAL"
    assert draft["content"]["subject"] is None
    assert draft["content"]["body"]
    assert draft["evidence"]
    assert draft["policy"]["requires_human_approval"] is True
    assert draft["policy"]["allow_external_side_effects"] is False
    assert draft["policy"]["allow_live_channel"] is False
    assert draft["result"] is None


def test_false_certainty_is_never_generated():
    body = " ".join(str(value) for value in _draft()["content"].values() if value).lower()
    assert "sabemos que você ainda está avaliando" not in body
    assert "sei que você está avaliando" not in body
    assert "cliente está interessado" not in body
    assert "conseguiu avaliar" in body


@pytest.mark.parametrize("action_type,objective,strategy", [
    ("FOLLOW_UP", "FOLLOW_UP", "GENTLE_REACTIVATION"),
    ("CONTACT_CLIENT", "CONFIRM_NEXT_STEP", "NEXT_STEP_CONFIRMATION"),
    ("REQUEST_INFORMATION", "REQUEST_INFORMATION", "INFORMATION_REQUEST"),
    ("REVIEW_PROPOSAL", "REVIEW_PROPOSAL", "VALUE_REINFORCEMENT"),
])
def test_objective_and_strategy_mapping(action_type, objective, strategy):
    draft = _draft(action_type=action_type)
    assert draft["objective"] == objective
    assert draft["strategy"] == strategy


def test_direct_follow_up_for_recent_activity():
    draft = _draft(days=2)
    assert draft["strategy"] == "DIRECT_FOLLOW_UP"
    assert draft["tone"] == "DIRECT"


def test_missing_name_contact_price_and_product_are_not_invented():
    documents = list(_documents(with_proposal=False))
    documents[5] = {"id": "client-1", "company_id": "company-1", "name": None, "phone": None, "email": None}
    draft = build_message_draft(*documents)
    text = json_text(draft["content"])
    assert "joão" not in text.lower()
    assert "produto existente" not in text.lower()
    assert "1250" not in text
    assert draft["recipient"]["name"] is None
    assert {"MISSING_RECIPIENT", "MISSING_PROPOSAL"} <= set(draft["warnings"])


def test_price_review_requires_explicit_price_evidence_and_never_offers_discount():
    documents = list(_documents(action_type="REVIEW_PRICE"))
    blocked = build_message_draft(*documents)
    assert blocked["status"] == "BLOCKED"
    documents[7]["insight"]["price_signal"] = {"status": "PRICE_REVIEW_POSSIBLE", "type": "FACT", "value": "preço"}
    allowed = build_message_draft(*documents)
    assert allowed["status"] == "READY_FOR_REVIEW"
    assert allowed["strategy"] == "PRICE_REVIEW"
    assert "desconto" not in json_text(allowed["content"]).lower()


def test_competitor_without_evidence_is_never_mentioned():
    draft = _draft()
    assert "concorrente" not in json_text(draft["content"]).lower()


@pytest.mark.parametrize("action_type", ["WAIT", "HUMAN_REVIEW", "NO_ACTION"])
def test_non_communication_actions_are_blocked(action_type):
    draft = _draft(action_type=action_type)
    assert draft["status"] == "BLOCKED"
    assert "NO_COMMUNICATION_ACTION" in draft["warnings"]
    assert draft["content"]["body"] is None


def test_stale_superseded_blocked_live_and_external_side_effect_are_blocked():
    documents = list(_documents())
    stale = deepcopy(documents)
    stale[8]["context_id"] = "new-context"
    assert build_message_draft(*stale)["status"] == "BLOCKED"
    assert "STALE_CONTEXT" in build_message_draft(*stale)["warnings"]
    superseded = deepcopy(documents)
    superseded[3]["status"] = "SUPERSEDED"
    assert build_message_draft(*superseded)["status"] == "BLOCKED"
    blocked_request = deepcopy(documents)
    blocked_request[2]["status"] = "BLOCKED"
    assert build_message_draft(*blocked_request)["status"] == "BLOCKED"
    live = deepcopy(documents)
    live[2]["mode"] = "LIVE"
    assert build_message_draft(*live)["status"] == "BLOCKED"
    unsafe = deepcopy(documents)
    unsafe[2]["policy"]["allow_external_side_effects"] = True
    assert build_message_draft(*unsafe)["status"] == "BLOCKED"


def test_low_confidence_and_missing_context_require_human_review():
    documents = list(_documents(confidence=0.2))
    documents[8]["context"]["data_quality"] = "INSUFFICIENT"
    draft = build_message_draft(*documents)
    assert "LOW_CONFIDENCE" in draft["warnings"]
    assert "MISSING_CONTEXT" in draft["warnings"]
    assert "HUMAN_REVIEW_REQUIRED" in draft["warnings"]


def test_phone_and_in_person_have_no_body():
    for channel in ["PHONE", "IN_PERSON"]:
        draft = _draft(channel=channel)
        assert draft["content"]["body"] is None


def test_email_subject_and_channel_length_contracts():
    email = _draft(channel="EMAIL")
    assert email["content"]["subject"] == "Acompanhamento comercial"
    assert email["policy"]["max_message_length"] == 5000
    assert _draft(channel="SMS")["policy"]["max_message_length"] == 300
    assert _draft(channel="WHATSAPP")["policy"]["max_message_length"] == 1000


def test_provider_factory_rejects_llm_without_fallback():
    assert isinstance(MessageProviderFactory.create("DETERMINISTIC"), DeterministicMessageProvider)
    assert MessageProviderFactory.create("DETERMINISTIC").health_check()["network_access"] is False
    with pytest.raises(ValueError, match="LLM_PROVIDER_NOT_AVAILABLE"):
        MessageProviderFactory.create("LLM")


def test_determinism_one_hundred_runs_ignores_timestamps():
    documents = list(_documents())
    results = [build_message_draft(*documents) for _ in range(100)]
    keys = ["content", "objective", "strategy", "tone", "confidence", "source_snapshot_hash"]
    for key in keys:
        assert all(result[key] == results[0][key] for result in results)
    assert results[0]["message_intelligence_version"] == MESSAGE_INTELLIGENCE_VERSION


def test_version_change_produces_new_logical_version(monkeypatch):
    import message_intelligence

    first = build_message_draft(*_documents())
    monkeypatch.setattr(message_intelligence, "MESSAGE_INTELLIGENCE_VERSION", "2.0.0")
    second = message_intelligence.build_message_draft(*_documents())
    assert second["message_intelligence_version"] == "2.0.0"
    assert second["message_draft_id"] != first["message_draft_id"]
    assert second["source_snapshot_hash"] != first["source_snapshot_hash"]


def test_tenant_validation():
    documents = list(_documents())
    documents[5]["company_id"] = "other"
    with pytest.raises(ValueError, match="TENANT_MISMATCH_CLIENT"):
        build_message_draft(*documents)


def test_quality_scores_are_bounded_and_confidence_is_not_probability():
    draft = _draft()
    assert all(0 <= value <= 1 for value in draft["message_quality"].values())
    assert 0 <= draft["message_confidence"] <= 1
    assert "probability" not in draft


def test_performance_ten_thousand_drafts_under_limits():
    import time
    import tracemalloc

    tracemalloc.start()
    started = time.perf_counter()
    drafts = []
    for index in range(10000):
        documents = list(_documents())
        documents[1]["execution_job_id"] = f"job-{index}"
        documents[2]["execution_job_id"] = f"job-{index}"
        documents[2]["request_id"] = f"comm-{index}"
        drafts.append(build_message_draft(*documents))
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert elapsed < 20.0
    assert peak < 128 * 1024 * 1024
    assert len({draft["message_draft_id"] for draft in drafts}) == 10000


def test_network_guard_for_one_thousand_drafts(monkeypatch):
    import http.client
    import smtplib
    import socket
    import urllib.request

    calls = []

    def blocked(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("network access attempted")

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
        assert build_message_draft(*_documents())["status"] == "READY_FOR_REVIEW"
    assert calls == []


def json_text(value):
    import json
    return json.dumps(value, ensure_ascii=False)
