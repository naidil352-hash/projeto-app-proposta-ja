import pytest

from integration_hub import (
    INTEGRATION_HUB_VERSION,
    IntegrationValidationError,
    build_sync_event,
    build_sync_preview,
    validate_connection_definition,
)


pytestmark = pytest.mark.unit


def _connection(**overrides):
    value = {
        "connection_id": "omie-principal",
        "company_id": "company-1",
        "provider": "omie",
        "authentication": "API_KEY",
        "source_of_truth": {
            "CLIENT": "EXTERNAL",
            "PRODUCT": "EXTERNAL",
            "PROPOSAL": "PROPOSTA_JA",
        },
        "enabled": True,
    }
    value.update(overrides)
    return validate_connection_definition(value)


def test_connection_is_tenant_scoped_and_rejects_credentials_in_metadata():
    connection = _connection()
    assert connection.company_id == "company-1"
    assert connection.source_of_truth["CLIENT"] == "EXTERNAL"
    with pytest.raises(IntegrationValidationError, match="credentials"):
        _connection(access_token="must-not-be-stored-here")
    with pytest.raises(IntegrationValidationError, match="credentials"):
        build_sync_event(connection, entity="CLIENT", external_id="42", operation="UPSERT", fields={"oauth": {"refresh-token": "secret"}})


def test_invalid_entity_and_source_of_truth_are_rejected():
    with pytest.raises(IntegrationValidationError, match="unsupported canonical entity"):
        _connection(source_of_truth={"LEAD_SCORE": "EXTERNAL"})
    with pytest.raises(IntegrationValidationError, match="must be PROPOSTA_JA or EXTERNAL"):
        _connection(source_of_truth={"CLIENT": "BOTH"})


def test_event_has_stable_idempotency_key_without_external_io():
    connection = _connection()
    first = build_sync_event(connection, entity="CLIENT", external_id="42", operation="UPSERT", fields={"name": "Ana"})
    second = build_sync_event(connection, entity="CLIENT", external_id="42", operation="UPSERT", fields={"name": "Ana"})
    assert first["integration_hub_version"] == INTEGRATION_HUB_VERSION
    assert first["idempotency_key"] == second["idempotency_key"]
    assert first["event_id"] == first["idempotency_key"]


def test_import_preview_is_safe_when_external_is_source_of_truth():
    connection = _connection()
    event = build_sync_event(connection, entity="CLIENT", external_id="42", operation="UPSERT", fields={"name": "Ana"})
    preview = build_sync_preview(connection, event)
    assert preview["action"] == "READY_FOR_REVIEW"
    assert preview["mode"] == "PREVIEW"
    assert preview["will_perform_external_io"] is False


def test_export_requires_approval_and_respects_source_of_truth():
    connection = _connection()
    proposal = build_sync_event(connection, entity="PROPOSAL", external_id="p-1", operation="UPSERT", fields={"total": 100})
    preview = build_sync_preview(connection, proposal, direction="EXPORT")
    assert preview["action"] == "BLOCKED"
    assert preview["blockers"] == ["HUMAN_APPROVAL_REQUIRED"]

    client = build_sync_event(connection, entity="CLIENT", external_id="42", operation="UPSERT", fields={"name": "Ana"})
    invalid = build_sync_preview(connection, client, direction="EXPORT", approved=True)
    assert "SOURCE_OF_TRUTH_IS_EXTERNAL" in invalid["blockers"]


def test_disabled_connection_and_cross_tenant_event_are_not_accepted():
    disabled = _connection(enabled=False)
    event = build_sync_event(disabled, entity="CLIENT", external_id="42", operation="UPSERT", fields={"name": "Ana"})
    assert "CONNECTION_DISABLED" in build_sync_preview(disabled, event)["blockers"]
    other_tenant = _connection(company_id="company-2")
    with pytest.raises(IntegrationValidationError, match="does not belong"):
        build_sync_preview(other_tenant, event)
