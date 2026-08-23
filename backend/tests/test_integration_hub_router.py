import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from integration_hub import build_sync_event, validate_connection_definition
from modules.integration_hub.adapters import create_default_registry
from modules.integration_hub.router import create_integration_hub_router


pytestmark = pytest.mark.unit


class Cursor:
    def __init__(self, docs): self.docs = docs
    def sort(self, *_): return self
    async def to_list(self, _): return [dict(doc) for doc in self.docs]


class Collection:
    def __init__(self): self.docs = []
    async def find_one(self, query, projection=None):
        return next(({k: v for k, v in doc.items() if k != "_id"} for doc in self.docs if all(doc.get(k) == v for k, v in query.items())), None)
    async def update_one(self, query, update, upsert=False):
        doc = await self.find_one(query)
        if doc is None and upsert:
            self.docs.append({**query, **update["$setOnInsert"], **update["$set"]})
    async def insert_one(self, doc): self.docs.append(dict(doc))
    def find(self, query, projection=None): return Cursor([doc for doc in self.docs if all(doc.get(k) == v for k, v in query.items())])


class Database:
    def __init__(self):
        self.integration_connections, self.integration_sync_events = Collection(), Collection()


def app_for(database, user=None):
    async def auth():
        if user is None: raise HTTPException(status_code=401, detail="unauthorized")
        return user
    app = FastAPI()
    app.include_router(create_integration_hub_router(lambda: database, auth, lambda current: current["company_id"], create_default_registry()))
    return app


def connection(company_id="tenant-a", enabled=True):
    return {"connection_id": "file-one", "provider": "generic_file", "authentication": "NONE", "source_of_truth": {"CLIENT": "EXTERNAL", "PROPOSAL": "PROPOSTA_JA"}, "enabled": enabled, "company_id": company_id}


@pytest.mark.asyncio
async def test_routes_require_auth_and_reject_body_tenant_or_secret():
    database = Database()
    async with AsyncClient(transport=ASGITransport(app=app_for(database)), base_url="http://test") as client:
        assert (await client.get("/integrations/connections")).status_code == 401
    async with AsyncClient(transport=ASGITransport(app=app_for(database, {"company_id": "tenant-a"})), base_url="http://test") as client:
        forbidden = await client.post("/integrations/connections", json={**connection(), "api_key": "no"})
        assert forbidden.status_code == 422
        crossing = await client.post("/integrations/connections", json=connection(company_id="tenant-b"))
        assert crossing.status_code == 422


@pytest.mark.asyncio
async def test_connections_previews_and_events_are_tenant_scoped_and_local_only():
    database = Database()
    app = app_for(database, {"company_id": "tenant-a"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/integrations/connections", json={k: v for k, v in connection().items() if k != "company_id"})
        assert created.status_code == 200
        assert created.json()["company_id"] == "tenant-a"
        assert len((await client.get("/integrations/connections")).json()) == 1
        event = build_sync_event(validate_connection_definition(connection()), entity="CLIENT", external_id="1", operation="UPSERT", fields={"name": "Ana"})
        preview = await client.post("/integrations/connections/file-one/preview", json={"event": event})
        assert preview.status_code == 200
        assert preview.json()["will_perform_external_io"] is False
        assert len((await client.get("/integrations/connections/file-one/events")).json()) == 1
    other = app_for(database, {"company_id": "tenant-b"})
    async with AsyncClient(transport=ASGITransport(app=other), base_url="http://test") as client:
        assert (await client.get("/integrations/connections")).json() == []
        assert (await client.get("/integrations/connections/file-one/events")).json() == []


@pytest.mark.asyncio
async def test_preview_blocks_disabled_and_unapproved_export_and_rejects_tenant_event():
    database = Database()
    app = app_for(database, {"company_id": "tenant-a"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/integrations/connections", json={k: v for k, v in connection(enabled=False).items() if k != "company_id"})
        event = build_sync_event(validate_connection_definition(connection(enabled=False)), entity="PROPOSAL", external_id="p1", operation="UPSERT", fields={"total": 10})
        result = await client.post("/integrations/connections/file-one/preview", json={"event": event, "direction": "EXPORT"})
        assert "CONNECTION_DISABLED" in result.json()["preview"]["blockers"]
        assert "HUMAN_APPROVAL_REQUIRED" in result.json()["preview"]["blockers"]
        foreign = dict(event); foreign["company_id"] = "tenant-b"
        assert (await client.post("/integrations/connections/file-one/preview", json={"event": foreign})).status_code == 400
