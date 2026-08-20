"""Tenant-scoped reads required to build a Message Draft."""
from __future__ import annotations

import asyncio
from typing import Any


class MessageDraftInputsNotFound(LookupError):
    pass


class MessageDraftInputsIncomplete(LookupError):
    pass


async def load_message_draft_inputs(
    database: Any,
    company_id: str,
    communication_request_id: str,
) -> tuple[dict, dict, dict, dict, dict | None, dict | None, dict, dict]:
    communication = await database.communication_requests.find_one(
        {"company_id": company_id, "request_id": communication_request_id}, {"_id": 0}
    )
    if not communication:
        raise MessageDraftInputsNotFound("Communication Request não encontrada")

    opportunity_id = communication.get("opportunity_id")
    job, plan, opportunity, insight, context = await asyncio.gather(
        database.execution_jobs.find_one(
            {"company_id": company_id, "execution_job_id": communication.get("execution_job_id")}, {"_id": 0}
        ),
        database.action_plans.find_one(
            {"company_id": company_id, "action_plan_id": communication.get("action_plan_id")}, {"_id": 0}
        ),
        database.opportunities.find_one(
            {"company_id": company_id, "id": opportunity_id, "deleted": {"$ne": True}}, {"_id": 0}
        ),
        database.sales_insights.find_one(
            {"company_id": company_id, "opportunity_id": opportunity_id}, {"_id": 0}, sort=[("created_at", -1)]
        ),
        database.commercial_contexts.find_one(
            {"company_id": company_id, "opportunity_id": opportunity_id}, {"_id": 0}, sort=[("created_at", -1)]
        ),
    )
    if not all([job, plan, opportunity, insight, context]):
        raise MessageDraftInputsIncomplete("Message Draft blocked: cadeia de contexto incompleta")

    client_query = (
        database.clients.find_one(
            {"company_id": company_id, "id": opportunity["client_id"], "deleted": {"$ne": True}}, {"_id": 0}
        )
        if opportunity.get("client_id")
        else _none()
    )
    proposal_query = (
        database.proposals.find_one(
            {"company_id": company_id, "id": opportunity["proposal_id"]}, {"_id": 0}
        )
        if opportunity.get("proposal_id")
        else _none()
    )
    client, proposal = await asyncio.gather(client_query, proposal_query)
    return job, communication, plan, opportunity, client, proposal, insight, context


async def _none() -> None:
    return None
