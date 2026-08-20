import pytest

from integration_hub import IntegrationValidationError, build_sync_event, validate_connection_definition
from modules.integration_hub.repository import IntegrationConnectionNotFound, IntegrationHubRepository


pytestmark = pytest.mark.unit


class FakeCollection:
    def __init__(self):
        self.documents = []
        self.indexes = []

    async def create_index(self, keys, **options):
        self.indexes.append((keys, options))

    async def find_one(self, query, projection=None):
        for document in self.documents:
            if all(document.get(key) == value for key, value in query.items()):
                return {key: value for key, value in document.items() if key != "_id"}
        return None

    async def update_one(self, query, update, upsert=False):
        for document in self.documents:
            if all(document.get(key) == value for key, value in query.items()):
                document.update(update["$set"])
                return
        if upsert:
            self.documents.append({**query, **update["$setOnInsert"], **update["$set"]})

    async def insert_one(self, document):
        self.documents.append(dict(document))


class FakeDatabase:
    def __init__(self):
        self.integration_connections = FakeCollection()
        self.integration_sync_events = FakeCollection()


def _definition(company_id="company-1", **overrides):
    value = {
        "connection_id": "omie-principal",
        "company_id": company_id,
        "provider": "omie",
        "authentication": "API_KEY",
        "source_of_truth": {"CLIENT": "EXTERNAL", "PROPOSAL": "PROPOSTA_JA"},
        "enabled": True,
    }
    value.update(overrides)
    return value


@pytest.mark.asyncio
async def test_save_connection_is_tenant_scoped_and_never_persists_credentials():
    database = FakeDatabase()
    repository = IntegrationHubRepository(database)
    saved = await repository.save_connection(_definition())
    assert saved["company_id"] == "company-1"
    assert "api_key" not in saved
    assert await repository.get_connection("company-2", "omie-principal") is None
    with pytest.raises(IntegrationValidationError, match="credentials"):
        await repository.save_connection(_definition(access_token="forbidden"))


@pytest.mark.asyncio
async def test_event_is_persisted_once_by_tenant_scoped_idempotency_key():
    database = FakeDatabase()
    repository = IntegrationHubRepository(database)
    definition = _definition()
    await repository.save_connection(definition)
    event = build_sync_event(validate_connection_definition(definition), entity="CLIENT", external_id="42", operation="UPSERT", fields={"name": "Ana"})
    first, inserted = await repository.record_event(event)
    second, inserted_again = await repository.record_event(event)
    assert inserted is True
    assert inserted_again is False
    assert first["idempotency_key"] == second["idempotency_key"]
    assert len(database.integration_sync_events.documents) == 1


@pytest.mark.asyncio
async def test_event_cannot_cross_tenant_or_use_an_unknown_connection():
    database = FakeDatabase()
    repository = IntegrationHubRepository(database)
    definition = _definition()
    event = build_sync_event(validate_connection_definition(definition), entity="CLIENT", external_id="42", operation="UPSERT", fields={"name": "Ana"})
    with pytest.raises(IntegrationConnectionNotFound):
        await repository.record_event(event)
    await repository.save_connection(_definition(company_id="company-2"))
    with pytest.raises(IntegrationConnectionNotFound):
        await repository.record_event(event)


@pytest.mark.asyncio
async def test_repository_declares_unique_tenant_indexes():
    database = FakeDatabase()
    repository = IntegrationHubRepository(database)
    await repository.ensure_indexes()
    assert database.integration_connections.indexes[0][1]["unique"] is True
    assert database.integration_sync_events.indexes[0][1]["unique"] is True
