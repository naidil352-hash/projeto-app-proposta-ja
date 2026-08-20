"""Tenant-scoped persistence for Integration Hub metadata and audit events.

The database dependency is injected. This module never constructs a Mongo
client, reads credentials, calls a provider or performs synchronization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from integration_hub import (
    ConnectionDefinition,
    IntegrationValidationError,
    SENSITIVE_KEYS,
    validate_connection_definition,
)


class IntegrationConnectionNotFound(LookupError):
    """A tenant cannot persist an event for an unknown connection."""


def _has_secret(value: Mapping[str, Any]) -> bool:
    for key, nested_value in value.items():
        if str(key).lower().replace("-", "_") in SENSITIVE_KEYS:
            return True
        if isinstance(nested_value, Mapping) and _has_secret(nested_value):
            return True
    return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IntegrationHubRepository:
    """Repository with company_id on every read and write boundary."""

    def __init__(self, database: Any):
        self._connections = database.integration_connections
        self._events = database.integration_sync_events

    async def ensure_indexes(self) -> None:
        await self._connections.create_index(
            [("company_id", 1), ("connection_id", 1)], unique=True,
            name="integration_connection_per_tenant",
        )
        await self._events.create_index(
            [("company_id", 1), ("connection_id", 1), ("idempotency_key", 1)], unique=True,
            name="integration_event_idempotency_per_tenant",
        )

    async def save_connection(self, definition: Mapping[str, Any]) -> dict[str, Any]:
        connection = validate_connection_definition(definition)
        document = self._connection_document(connection)
        await self._connections.update_one(
            {"company_id": connection.company_id, "connection_id": connection.connection_id},
            {"$set": document, "$setOnInsert": {"created_at": _now()}},
            upsert=True,
        )
        return document

    async def get_connection(self, company_id: str, connection_id: str) -> dict[str, Any] | None:
        return await self._connections.find_one(
            {"company_id": company_id, "connection_id": connection_id}, {"_id": 0}
        )

    async def record_event(self, event: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        required = ("company_id", "connection_id", "idempotency_key", "event_id", "entity", "operation")
        if not isinstance(event, Mapping) or any(not str(event.get(field) or "").strip() for field in required):
            raise IntegrationValidationError("event is missing tenant or idempotency metadata")
        if _has_secret(event):
            raise IntegrationValidationError("sync event must not contain credentials")
        tenant_query = {"company_id": event["company_id"], "connection_id": event["connection_id"]}
        if not await self._connections.find_one(tenant_query, {"_id": 0}):
            raise IntegrationConnectionNotFound("integration connection was not found for this tenant")
        event_query = {**tenant_query, "idempotency_key": event["idempotency_key"]}
        existing = await self._events.find_one(event_query, {"_id": 0})
        if existing:
            return existing, False
        document = {**dict(event), "persisted_at": _now()}
        await self._events.insert_one(document)
        return document, True

    @staticmethod
    def _connection_document(connection: ConnectionDefinition) -> dict[str, Any]:
        return {
            "company_id": connection.company_id,
            "connection_id": connection.connection_id,
            "provider": connection.provider,
            "authentication": connection.authentication,
            "source_of_truth": dict(connection.source_of_truth),
            "enabled": connection.enabled,
            "updated_at": _now(),
        }
