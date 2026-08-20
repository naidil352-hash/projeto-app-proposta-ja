"""Provider-neutral, no-I/O foundation for CRM and ERP synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping

INTEGRATION_HUB_VERSION = "1.0.0"
CANONICAL_ENTITIES = frozenset({"CLIENT", "CONTACT", "PRODUCT", "OPPORTUNITY", "PROPOSAL", "ORDER", "INVOICE", "STOCK"})
AUTHENTICATION_TYPES = frozenset({"OAUTH2", "API_KEY", "NONE"})
SOURCES_OF_TRUTH = frozenset({"PROPOSTA_JA", "EXTERNAL"})
SENSITIVE_KEYS = frozenset({"access_token", "api_key", "authorization", "client_secret", "password", "refresh_token", "token"})
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


class IntegrationValidationError(ValueError):
    """The integration contract cannot be satisfied safely."""


@dataclass(frozen=True)
class ConnectionDefinition:
    connection_id: str
    company_id: str
    provider: str
    authentication: str
    source_of_truth: Mapping[str, str]
    enabled: bool = False


def _text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise IntegrationValidationError(f"{field} is required")
    return text


def _slug(value: Any, field: str) -> str:
    text = _text(value, field).lower()
    if not _SLUG.fullmatch(text):
        raise IntegrationValidationError(f"{field} must be a lowercase slug")
    return text


def _has_secret(value: Mapping[str, Any]) -> bool:
    for key, nested_value in value.items():
        normalized_key = str(key).lower().replace("-", "_")
        if normalized_key in SENSITIVE_KEYS:
            return True
        if isinstance(nested_value, Mapping) and _has_secret(nested_value):
            return True
    return False


def validate_connection_definition(value: Mapping[str, Any]) -> ConnectionDefinition:
    """Validate metadata only; credentials must live in an encrypted store."""
    if _has_secret(value):
        raise IntegrationValidationError("connection metadata must not contain credentials")
    authentication = _text(value.get("authentication"), "authentication").upper()
    if authentication not in AUTHENTICATION_TYPES:
        raise IntegrationValidationError("unsupported authentication type")
    raw_sources = value.get("source_of_truth")
    if not isinstance(raw_sources, Mapping) or not raw_sources:
        raise IntegrationValidationError("source_of_truth is required")
    sources: dict[str, str] = {}
    for entity, source in raw_sources.items():
        entity, source = _text(entity, "source entity").upper(), _text(source, "source value").upper()
        if entity not in CANONICAL_ENTITIES:
            raise IntegrationValidationError(f"unsupported canonical entity: {entity}")
        if source not in SOURCES_OF_TRUTH:
            raise IntegrationValidationError("source_of_truth value must be PROPOSTA_JA or EXTERNAL")
        sources[entity] = source
    return ConnectionDefinition(_slug(value.get("connection_id"), "connection_id"), _text(value.get("company_id"), "company_id"), _slug(value.get("provider"), "provider"), authentication, sources, bool(value.get("enabled", False)))


def build_sync_event(connection: ConnectionDefinition, *, entity: str, external_id: str, operation: str, fields: Mapping[str, Any], source_updated_at: str | None = None, event_id: str | None = None) -> dict[str, Any]:
    """Create a canonical event with a deterministic idempotency key; never sends it."""
    entity, operation = _text(entity, "entity").upper(), _text(operation, "operation").upper()
    if entity not in CANONICAL_ENTITIES or operation not in {"UPSERT", "DELETE"}:
        raise IntegrationValidationError("unsupported entity or operation")
    if not isinstance(fields, Mapping) or _has_secret(fields):
        raise IntegrationValidationError("fields must be an object without credentials")
    external_id = _text(external_id, "external_id")
    identity = {"company_id": connection.company_id, "connection_id": connection.connection_id, "provider": connection.provider, "entity": entity, "external_id": external_id, "operation": operation, "source_updated_at": source_updated_at or "", "event_id": event_id or "", "fields": dict(fields)}
    idempotency_key = sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    identity["event_id"] = event_id or idempotency_key
    return {"integration_hub_version": INTEGRATION_HUB_VERSION, "idempotency_key": idempotency_key, "observed_at": datetime.now(timezone.utc).isoformat(), **identity}


def build_sync_preview(connection: ConnectionDefinition, event: Mapping[str, Any], *, direction: str = "IMPORT", approved: bool = False) -> dict[str, Any]:
    """Return a non-mutating plan; exports require a matching owner and approval."""
    direction = _text(direction, "direction").upper()
    if direction not in {"IMPORT", "EXPORT"}:
        raise IntegrationValidationError("direction must be IMPORT or EXPORT")
    if event.get("company_id") != connection.company_id or event.get("connection_id") != connection.connection_id:
        raise IntegrationValidationError("event does not belong to this connection")
    entity = _text(event.get("entity"), "event entity").upper()
    if entity not in connection.source_of_truth:
        raise IntegrationValidationError(f"source_of_truth is not configured for {entity}")
    source = connection.source_of_truth[entity]
    blockers = []
    if not connection.enabled:
        blockers.append("CONNECTION_DISABLED")
    if direction != ("IMPORT" if source == "EXTERNAL" else "EXPORT"):
        blockers.append(f"SOURCE_OF_TRUTH_IS_{source}")
    if direction == "EXPORT" and not approved:
        blockers.append("HUMAN_APPROVAL_REQUIRED")
    return {"integration_hub_version": INTEGRATION_HUB_VERSION, "mode": "PREVIEW", "will_perform_external_io": False, "connection_id": connection.connection_id, "company_id": connection.company_id, "provider": connection.provider, "entity": entity, "direction": direction, "source_of_truth": source, "event_id": event.get("event_id"), "idempotency_key": event.get("idempotency_key"), "action": "BLOCKED" if blockers else "READY_FOR_REVIEW", "blockers": blockers}
