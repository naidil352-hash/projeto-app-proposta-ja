"""Authenticated, local-only Integration Hub API routes."""
from __future__ import annotations

from typing import Any, Callable, Mapping

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from integration_hub import IntegrationValidationError
from .adapters import ProviderNotRegistered, ProviderRegistry
from .repository import IntegrationConnectionNotFound, IntegrationHubRepository
from .service import IntegrationPreviewService


class ConnectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: str
    provider: str
    authentication: str
    source_of_truth: dict[str, str]
    enabled: bool = False


class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: dict[str, Any]
    direction: str = "IMPORT"
    approved: bool = False


def create_integration_hub_router(
    get_database: Callable[[], Any],
    auth_dependency: Callable[..., Any],
    company_id_resolver: Callable[[dict], str],
    registry: ProviderRegistry,
) -> APIRouter:
    router = APIRouter(prefix="/integrations", tags=["integrations"])

    def repository() -> IntegrationHubRepository:
        return IntegrationHubRepository(get_database())

    @router.post("/connections")
    async def create_connection(payload: ConnectionIn, user=Depends(auth_dependency)):
        company_id = company_id_resolver(user)
        try:
            return await repository().save_connection({**payload.model_dump(), "company_id": company_id})
        except IntegrationValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/connections")
    async def list_connections(user=Depends(auth_dependency)):
        return await repository().list_connections(company_id_resolver(user))

    @router.post("/connections/{connection_id}/preview")
    async def create_preview(connection_id: str, payload: PreviewIn, user=Depends(auth_dependency)):
        company_id = company_id_resolver(user)
        try:
            service = IntegrationPreviewService(repository(), registry)
            result = await service.plan_preview(company_id, connection_id, payload.event, direction=payload.direction, approved=payload.approved)
            event, _ = await repository().record_event(payload.event)
            return {**result, "event": event}
        except IntegrationConnectionNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ProviderNotRegistered as exc:
            raise HTTPException(status_code=400, detail="integration provider is not available") from exc
        except (IntegrationValidationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/connections/{connection_id}/events")
    async def list_events(connection_id: str, user=Depends(auth_dependency)):
        return await repository().list_events(company_id_resolver(user), connection_id)

    return router
