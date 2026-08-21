import pytest

from integration_hub import IntegrationValidationError, build_sync_event, validate_connection_definition
from modules.integration_hub.adapters import (
    ConnectionState,
    ProviderAdapter,
    ProviderNotRegistered,
    ProviderOperation,
    ProviderRegistry,
    connection_state,
)
from modules.integration_hub.service import IntegrationPreviewService


pytestmark = pytest.mark.unit


class FakeRepository:
    def __init__(self, connections):
        self.connections = connections

    async def get_connection(self, company_id, connection_id):
        return self.connections.get((company_id, connection_id))


def _connection(company_id="company-1", enabled=True):
    return {
        "connection_id": "generic-file",
        "company_id": company_id,
        "provider": "generic_file",
        "authentication": "NONE",
        "source_of_truth": {"CLIENT": "EXTERNAL", "PROPOSAL": "PROPOSTA_JA"},
        "enabled": enabled,
    }


def _registry():
    registry = ProviderRegistry()
    registry.register(ProviderAdapter.from_capabilities("generic_file", [
        ("CLIENT", "IMPORT"), ("CLIENT", "PREVIEW"), ("CLIENT", "EXPORT"),
        ("PROPOSAL", "EXPORT"), ("PROPOSAL", "PREVIEW"),
    ]))
    return registry


def _event(connection, entity="CLIENT"):
    return build_sync_event(validate_connection_definition(connection), entity=entity, external_id="record-1", operation="UPSERT", fields={"name": "Ana"})


def test_registry_tracks_capabilities_and_rejects_missing_or_duplicate_provider():
    registry = _registry()
    assert registry.registered_providers() == ("generic_file",)
    assert registry.get("generic_file").supports("CLIENT", ProviderOperation.IMPORT)
    with pytest.raises(ProviderNotRegistered):
        registry.get("omie")
    with pytest.raises(IntegrationValidationError, match="already registered"):
        registry.register(ProviderAdapter.from_capabilities("generic_file", [("CLIENT", "IMPORT")]))


def test_connection_states_are_non_live_and_fail_closed():
    assert connection_state({}) == ConnectionState.DRAFT
    assert connection_state(_connection(enabled=False)) == ConnectionState.DISABLED
    assert connection_state(_connection()) == ConnectionState.READY_FOR_PREVIEW


@pytest.mark.asyncio
async def test_service_returns_import_preview_without_io_for_external_source():
    connection = _connection()
    service = IntegrationPreviewService(FakeRepository({("company-1", "generic-file"): connection}), _registry())
    result = await service.plan_preview("company-1", "generic-file", _event(connection))
    assert result["mode"] == "PREVIEW"
    assert result["will_perform_external_io"] is False
    assert result["preview"]["action"] == "READY_FOR_REVIEW"


@pytest.mark.asyncio
async def test_service_blocks_disabled_export_without_approval():
    connection = _connection(enabled=False)
    service = IntegrationPreviewService(FakeRepository({("company-1", "generic-file"): connection}), _registry())
    result = await service.plan_preview("company-1", "generic-file", _event(connection, "PROPOSAL"), direction="EXPORT")
    assert result["connection_state"] == "DISABLED"
    assert result["preview"]["blockers"] == ["CONNECTION_DISABLED", "HUMAN_APPROVAL_REQUIRED"]


@pytest.mark.asyncio
async def test_service_preserves_source_of_truth_even_when_provider_can_export():
    connection = _connection()
    service = IntegrationPreviewService(FakeRepository({("company-1", "generic-file"): connection}), _registry())
    result = await service.plan_preview("company-1", "generic-file", _event(connection), direction="EXPORT", approved=True)
    assert "SOURCE_OF_TRUTH_IS_EXTERNAL" in result["preview"]["blockers"]


@pytest.mark.asyncio
async def test_service_enforces_tenant_and_provider_capability_boundaries():
    connection = _connection()
    service = IntegrationPreviewService(FakeRepository({("company-1", "generic-file"): connection}), _registry())
    with pytest.raises(IntegrationValidationError, match="tenant connection"):
        await service.plan_preview("company-1", "generic-file", _event(_connection(company_id="company-2")))
    with pytest.raises(IntegrationValidationError, match="does not support"):
        await service.plan_preview("company-1", "generic-file", _event(connection, "PROPOSAL"), direction="IMPORT")
