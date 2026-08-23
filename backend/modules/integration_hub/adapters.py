"""Provider contracts and an in-memory registry for Integration Hub.

Adapters in this phase only describe capabilities. They have no credentials,
transport clients or provider-specific I/O methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from integration_hub import CANONICAL_ENTITIES, IntegrationValidationError


class ProviderOperation(str, Enum):
    IMPORT = "IMPORT"
    PREVIEW = "PREVIEW"
    EXPORT = "EXPORT"


class ConnectionState(str, Enum):
    DRAFT = "DRAFT"
    DISABLED = "DISABLED"
    READY_FOR_PREVIEW = "READY_FOR_PREVIEW"


class ProviderNotRegistered(LookupError):
    """A connection references a provider absent from the local registry."""


def _operation(value: ProviderOperation | str) -> ProviderOperation:
    return value if isinstance(value, ProviderOperation) else ProviderOperation(str(value).upper())


@dataclass(frozen=True)
class ProviderAdapter:
    """Static declaration of the safe operations available for a provider."""

    provider: str
    capabilities: frozenset[tuple[str, ProviderOperation]]

    @classmethod
    def from_capabilities(
        cls, provider: str, capabilities: Iterable[tuple[str, ProviderOperation | str]]
    ) -> "ProviderAdapter":
        normalized = set()
        for entity, operation in capabilities:
            entity = str(entity).upper()
            if entity not in CANONICAL_ENTITIES:
                raise IntegrationValidationError(f"unsupported adapter entity: {entity}")
            normalized.add((entity, _operation(operation)))
        if not normalized:
            raise IntegrationValidationError("provider requires at least one capability")
        return cls(provider=str(provider).strip().lower(), capabilities=frozenset(normalized))

    def supports(self, entity: str, operation: ProviderOperation | str) -> bool:
        return (str(entity).upper(), _operation(operation)) in self.capabilities


class ProviderRegistry:
    """Explicit registry; an unregistered provider is never implicitly allowed."""

    def __init__(self):
        self._providers: dict[str, ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> None:
        provider = adapter.provider.strip().lower()
        if not provider:
            raise IntegrationValidationError("provider is required")
        if provider in self._providers:
            raise IntegrationValidationError(f"provider already registered: {provider}")
        self._providers[provider] = adapter

    def get(self, provider: str) -> ProviderAdapter:
        adapter = self._providers.get(str(provider).strip().lower())
        if not adapter:
            raise ProviderNotRegistered(f"provider is not registered: {provider}")
        return adapter

    def registered_providers(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


def connection_state(connection: dict) -> ConnectionState:
    """Derive a non-live state solely from persisted non-secret metadata."""
    if not connection.get("connection_id") or not connection.get("company_id"):
        return ConnectionState.DRAFT
    if not connection.get("enabled"):
        return ConnectionState.DISABLED
    return ConnectionState.READY_FOR_PREVIEW


def create_default_registry() -> ProviderRegistry:
    """Return the only local-only provider available before real adapters exist."""
    registry = ProviderRegistry()
    registry.register(ProviderAdapter.from_capabilities("generic_file", [
        (entity, operation)
        for entity in CANONICAL_ENTITIES
        for operation in ProviderOperation
    ]))
    return registry
