from datetime import datetime, timedelta, timezone

import pytest

from action_execution import (
    ACTION_EXECUTOR_VERSION,
    SimulationAdapter,
    build_execution_job,
    cancel_execution_job,
    compute_execution_snapshot_hash,
    simulate_execution_job,
)

pytestmark = pytest.mark.unit


def _documents(plan_status="APPROVED", action_status="PENDING_APPROVAL", channel="WHATSAPP"):
    company_id = "company-1"
    action = {
        "action_id": "action-1", "type": "FOLLOW_UP", "channel": channel,
        "objective": "Obter uma atualização objetiva da oportunidade.",
        "reason": "Follow-up overdue.", "evidence": [{"source": "sales_intelligence", "field": "followup_state", "value": "OVERDUE"}],
        "status": action_status,
    }
    plan = {
        "action_plan_id": "plan-1", "company_id": company_id, "opportunity_id": "opp-1",
        "sales_insight_id": "insight-1", "context_id": "ctx-1", "status": plan_status,
        "source_snapshot_hash": "plan-hash", "actions": [action],
    }
    opportunity = {"id": "opp-1", "company_id": company_id}
    insight = {"insight_id": "insight-1", "opportunity_id": "opp-1", "context_id": "ctx-1", "company_id": company_id}
    context = {"context_id": "ctx-1", "opportunity_id": "opp-1", "company_id": company_id}
    return company_id, plan, action, opportunity, insight, context


def _job(**overrides):
    documents = _documents()
    job = build_execution_job(*documents)
    job.update(overrides)
    return job


def test_fundamental_create_and_simulate_has_no_external_side_effect():
    job = _job()
    assert job["status"] == "CREATED"
    assert job["mode"] == "SIMULATION"
    assert job["policy"]["allow_external_side_effects"] is False
    assert "message" not in job["payload"]
    result = simulate_execution_job(job)
    assert result["status"] == "SIMULATED"
    assert result["result"]["external_side_effect"] is False
    assert result["result"]["result"] == "SIMULATED_SUCCESS"
    assert "sent" not in result["result"]["message"].lower()


@pytest.mark.parametrize("status", ["DRAFT", "PENDING_REVIEW", "REJECTED", "SUPERSEDED", "EXPIRED"])
def test_non_approved_plan_is_blocked(status):
    with pytest.raises(ValueError, match="PLAN_NOT_EXECUTABLE"):
        build_execution_job(*_documents(plan_status=status))


@pytest.mark.parametrize("status", ["REJECTED", "CANCELLED", "SUPERSEDED", "COMPLETED"])
def test_non_executable_action_status_is_blocked(status):
    with pytest.raises(ValueError, match="ACTION_NOT_EXECUTABLE"):
        build_execution_job(*_documents(action_status=status))


def test_live_and_external_side_effect_policy_are_rejected():
    with pytest.raises(ValueError, match="LIVE_MODE_FORBIDDEN"):
        build_execution_job(*_documents(), mode="LIVE")
    with pytest.raises(ValueError, match="EXTERNAL_SIDE_EFFECTS_FORBIDDEN"):
        build_execution_job(*_documents(), requested_policy={"allow_external_side_effects": True})
    with pytest.raises(ValueError, match="APPROVAL_REQUIRED"):
        build_execution_job(*_documents(), requested_policy={"requires_approval": False})


def test_payload_is_generic_and_channel_agnostic():
    for channel in ["WHATSAPP", "EMAIL", "PHONE", "IN_PERSON", "UNKNOWN"]:
        job = build_execution_job(*_documents(channel=channel))
        assert job["channel"] == channel
        assert job["payload"]["channel"] == channel
        assert set(job["payload"]) == {"action_type", "channel", "objective", "reason", "evidence", "context"}


def test_adapter_contract_and_health_are_offline():
    adapter = SimulationAdapter()
    health = adapter.health_check()
    assert health == {"adapter": "simulation", "healthy": True, "external_connectivity": False}
    prepared = adapter.prepare(_job())
    assert prepared["external_side_effect"] is False
    assert adapter.execute(prepared)["adapter"] == "simulation"


def test_snapshot_hash_and_job_id_are_deterministic_one_hundred_times():
    company_id, plan, action, opportunity, insight, context = _documents()
    policy = {"mode": "SIMULATION", "requires_approval": True, "allow_external_side_effects": False, "max_attempts": 1, "timeout_seconds": 30}
    hashes = [compute_execution_snapshot_hash(plan, action, "SIMULATION", policy) for _ in range(100)]
    jobs = [build_execution_job(company_id, plan, action, opportunity, insight, context) for _ in range(100)]
    assert len(set(hashes)) == 1
    assert len({job["execution_job_id"] for job in jobs}) == 1
    assert all(job["executor_version"] == ACTION_EXECUTOR_VERSION for job in jobs)


def test_tenant_stale_and_action_consistency_guards():
    company_id, plan, action, opportunity, insight, context = _documents()
    with pytest.raises(ValueError, match="TENANT_MISMATCH"):
        build_execution_job("other", plan, action, opportunity, insight, context)
    with pytest.raises(ValueError, match="STALE_INSIGHT"):
        build_execution_job(company_id, plan, action, opportunity, {**insight, "insight_id": "new"}, context)
    with pytest.raises(ValueError, match="ACTION_NOT_IN_PLAN"):
        build_execution_job(company_id, plan, {**action, "action_id": "other"}, opportunity, insight, context)


def test_expiration_and_max_attempts_block_simulation():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="EXECUTION_EXPIRED"):
        build_execution_job(*_documents(), expires_at=(now - timedelta(seconds=1)).isoformat(), now=now)
    expired = simulate_execution_job(_job(expires_at=(now - timedelta(seconds=1)).isoformat()), now=now)
    assert expired["status"] == "EXPIRED"
    with pytest.raises(ValueError, match="MAX_ATTEMPTS_EXCEEDED"):
        simulate_execution_job(_job(attempts=1))


def test_cancel_only_allowed_before_execution():
    assert cancel_execution_job(_job())["status"] == "CANCELLED"
    for status in ["RUNNING", "SIMULATED", "SUCCEEDED"]:
        with pytest.raises(ValueError, match="JOB_NOT_CANCELLABLE"):
            cancel_execution_job(_job(status=status))


def test_ten_thousand_jobs_and_simulations_under_twenty_seconds_without_network():
    import time
    import tracemalloc

    company_id, plan, action, opportunity, insight, context = _documents()
    tracemalloc.start()
    started = time.perf_counter()
    results = []
    for index in range(10000):
        current_action = {**action, "action_id": f"action-{index}"}
        current_plan = {**plan, "action_plan_id": f"plan-{index}", "actions": [current_action]}
        job = build_execution_job(company_id, current_plan, current_action, opportunity, insight, context)
        results.append(simulate_execution_job(job))
    elapsed = time.perf_counter() - started
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert elapsed < 20.0
    assert peak_memory < 128 * 1024 * 1024
    assert all(item["status"] == "SIMULATED" for item in results)
    assert all(item["result"]["external_side_effect"] is False for item in results)
    assert len({item["execution_job_id"] for item in results}) == 10000


def test_one_thousand_simulations_make_zero_http_smtp_or_socket_calls(monkeypatch):
    import http.client
    import smtplib
    import socket

    calls = []

    def blocked(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("external call attempted")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(smtplib.SMTP, "connect", blocked)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", blocked)
    job = _job()
    for _ in range(1000):
        assert simulate_execution_job(job)["status"] == "SIMULATED"
    assert calls == []
