"""Safe orchestration of registered provider capabilities and existing previews."""

from __future__ import annotations

from typing import Any, Mapping

from integration_hub import IntegrationValidationError, build_sync_preview, validate_connection_definition
from .adapters import ConnectionState, ProviderOperation, ProviderRegistry, connection_state


class IntegrationPreviewService:
    """Builds previews only; provider adapters are never asked to perform I/O."""

    def __init__(self, repository: Any, registry: ProviderRegistry):
        self._repository = repository
        self._registry = registry

    async def plan_preview(
        self,
        company_id: str,
        connection_id: str,
        event: Mapping[str, Any],
        *,
        direction: str = "IMPORT",
        approved: bool = False,
    ) -> dict[str, Any]:
        connection = await self._repository.get_connection(company_id, connection_id)
        if not connection:
            raise IntegrationValidationError("integration connection was not found for this tenant")
        if event.get("company_id") != company_id or event.get("connection_id") != connection_id:
            raise IntegrationValidationError("event does not belong to this tenant connection")
        state = connection_state(connection)
        adapter = self._registry.get(connection["provider"])
        operation = ProviderOperation(str(direction).upper())
        entity = str(event.get("entity") or "").upper()
        if not adapter.supports(entity, operation):
            raise IntegrationValidationError("provider does not support this entity and operation")
        definition = validate_connection_definition(connection)
        preview = build_sync_preview(definition, event, direction=operation.value, approved=approved)
        return {
            "mode": "PREVIEW",
            "will_perform_external_io": False,
            "connection_state": state.value,
            "provider": adapter.provider,
            "provider_operation": operation.value,
            "preview": preview,
        }
