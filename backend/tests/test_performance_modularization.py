from __future__ import annotations

import asyncio
import time

import pytest

from modules.message_drafts.repository import load_message_draft_inputs
from modules.startup.indexes import INDEX_SPECS, ensure_indexes

pytestmark = pytest.mark.unit


class IndexCollection:
    def __init__(self, tracker):
        self.tracker = tracker

    async def create_index(self, keys, **options):
        assert self.tracker["obsolete_dropped"] is True
        self.tracker["active"] += 1
        self.tracker["max_active"] = max(self.tracker["max_active"], self.tracker["active"])
        await asyncio.sleep(0.002)
        self.tracker["active"] -= 1
        self.tracker["created"].append((keys, options))

    async def drop_index(self, name):
        assert name == "company_id_1_client_document_1"
        self.tracker["obsolete_dropped"] = True


class IndexDatabase:
    def __init__(self):
        self.tracker = {"active": 0, "max_active": 0, "created": [], "obsolete_dropped": False}
        self.collections = {}

    def __getattr__(self, name):
        return self[name]

    def __getitem__(self, name):
        return self.collections.setdefault(name, IndexCollection(self.tracker))


@pytest.mark.asyncio
async def test_all_index_specs_are_started_concurrently_after_obsolete_index_drop():
    database = IndexDatabase()
    await ensure_indexes(database)
    assert len(INDEX_SPECS) == 78
    assert len(database.tracker["created"]) == len(INDEX_SPECS)
    assert database.tracker["max_active"] > 1


class FindCollection:
    def __init__(self, name, documents, calls):
        self.name = name
        self.documents = documents
        self.calls = calls

    async def find_one(self, query, projection, **kwargs):
        self.calls.append((self.name, query, projection, kwargs))
        await asyncio.sleep(0.01)
        return self.documents.get(self.name)


class FindDatabase:
    def __init__(self, documents):
        self.calls = []
        self.collections = {
            name: FindCollection(name, documents, self.calls)
            for name in [
                "communication_requests", "execution_jobs", "action_plans", "opportunities",
                "sales_insights", "commercial_contexts", "clients", "proposals",
            ]
        }

    def __getattr__(self, name):
        return self.collections[name]


@pytest.mark.asyncio
async def test_message_draft_repository_preserves_contract_and_parallelizes_independent_reads():
    company_id = "company-a"
    documents = {
        "communication_requests": {"request_id": "comm-1", "execution_job_id": "job-1", "action_plan_id": "plan-1", "opportunity_id": "opp-1"},
        "execution_jobs": {"execution_job_id": "job-1"},
        "action_plans": {"action_plan_id": "plan-1"},
        "opportunities": {"id": "opp-1", "client_id": "client-1", "proposal_id": "proposal-1"},
        "sales_insights": {"insight_id": "insight-1"},
        "commercial_contexts": {"context_id": "context-1"},
        "clients": {"id": "client-1"},
        "proposals": {"id": "proposal-1"},
    }
    database = FindDatabase(documents)
    started = time.perf_counter()
    result = await load_message_draft_inputs(database, company_id, "comm-1")
    elapsed = time.perf_counter() - started

    assert result == (
        documents["execution_jobs"], documents["communication_requests"], documents["action_plans"],
        documents["opportunities"], documents["clients"], documents["proposals"],
        documents["sales_insights"], documents["commercial_contexts"],
    )
    assert len(database.calls) == 8
    assert all(call[1]["company_id"] == company_id for call in database.calls)
    assert elapsed < 0.06
