"""Mongo index declarations executed concurrently during backend startup."""
from __future__ import annotations

import asyncio
from typing import Any


INDEX_SPECS: tuple[tuple[str, Any, dict[str, Any]], ...] = (
    ("users", "email", {"unique": True}),
    ("users", "referral_code", {"unique": True, "sparse": True}),
    ("users", "company_id", {"sparse": True}),
    ("users", "role", {"sparse": True}),
    ("users", "active", {"sparse": True}),
    ("proposals", "id", {"unique": True}),
    ("proposals", [("company_id", 1), ("created_at", -1)], {}),
    ("proposals", [("company_id", 1), ("user_id", 1), ("status", 1), ("created_at", -1)], {}),
    ("proposals", [("company_id", 1), ("status", 1), ("created_at", -1)], {}),
    ("proposals", [("user_id", 1), ("created_at", -1)], {}),
    ("subscriptions", "user_id", {"unique": True}),
    ("payment_transactions", "session_id", {"unique": True}),
    ("products", "company_id", {}),
    ("products", [("company_id", 1), ("code", 1)], {"unique": True}),
    ("clients", "company_id", {}),
    ("clients", "owner_user_id", {}),
    ("clients", "created_by", {}),
    ("clients", [("company_id", 1), ("document", 1)], {"unique": True}),
    ("opportunities", "id", {"unique": True}),
    ("opportunities", [("company_id", 1), ("created_at", -1)], {}),
    ("opportunities", [("company_id", 1), ("user_id", 1), ("status", 1), ("created_at", -1)], {}),
    ("opportunities", [("user_id", 1), ("created_at", -1)], {}),
    ("rate_limits", "key", {}),
    ("commercial_templates", "company_id", {}),
    ("commercial_templates", "id", {"unique": True}),
    ("rate_limits", "timestamp", {}),
    ("audit_logs", "company_id", {}),
    ("audit_logs", "user_id", {}),
    ("audit_logs", "created_at", {}),
    ("import_structure_profiles", [("company_id", 1), ("import_batch_id", 1), ("analyzer_version", 1)], {"unique": True}),
    ("import_structure_profiles", [("company_id", 1), ("created_at", -1)], {}),
    ("mapping_candidates", [("company_id", 1), ("import_batch_id", 1), ("mapping_engine_version", 1)], {"unique": True}),
    ("mapping_candidates", [("company_id", 1), ("created_at", -1)], {}),
    ("mapping_decisions", [("company_id", 1), ("import_batch_id", 1), ("source_field.sheet_name", 1), ("source_field.source_index", 1), ("source_field.source_name", 1), ("decision_engine_version", 1)], {"unique": True}),
    ("mapping_decisions", [("company_id", 1), ("import_batch_id", 1), ("created_at", -1)], {}),
    ("mapping_confirmations", [("company_id", 1), ("import_batch_id", 1), ("source_field.sheet_name", 1), ("source_field.source_index", 1)], {}),
    ("mapping_templates", [("company_id", 1), ("template_id", 1), ("template_version", 1)], {"unique": True}),
    ("mapping_templates", [("company_id", 1), ("created_at", -1)], {}),
    ("mapping_applications", [("company_id", 1), ("import_batch_id", 1), ("template_id", 1), ("template_version", 1), ("run_number", 1)], {"unique": True}),
    ("standard_records", [("company_id", 1), ("import_batch_id", 1), ("source_record_id", 1), ("application_id", 1)], {"unique": True}),
    ("application_errors", [("company_id", 1), ("application_id", 1)], {}),
    ("learning_events", [("company_id", 1), ("event_id", 1)], {"unique": True}),
    ("learning_events", [("company_id", 1), ("created_at", -1)], {}),
    ("learning_observations", [("company_id", 1), ("observation_id", 1)], {"unique": True}),
    ("learning_observations", [("company_id", 1), ("status", 1)], {}),
    ("company_knowledge", [("company_id", 1), ("observation_id", 1)], {"unique": True}),
    ("company_knowledge", [("company_id", 1), ("pattern_signature", 1)], {}),
    ("learning_feedback", [("company_id", 1), ("feedback_id", 1)], {"unique": True}),
    ("learning_versions", [("company_id", 1), ("learning_version", 1)], {"unique": True}),
    ("commercial_contexts", [("company_id", 1), ("opportunity_id", 1), ("created_at", -1)], {}),
    ("commercial_contexts", [("company_id", 1), ("opportunity_id", 1), ("snapshot_version", 1), ("source_snapshot_hash", 1)], {"unique": True}),
    ("sales_insights", [("company_id", 1), ("opportunity_id", 1), ("created_at", -1)], {}),
    ("sales_insights", [("company_id", 1), ("opportunity_id", 1), ("engine_version", 1), ("source_snapshot_hash", 1)], {"unique": True}),
    ("action_plans", [("company_id", 1), ("opportunity_id", 1), ("updated_at", -1)], {}),
    ("action_plans", "action_plan_id", {"unique": True}),
    ("action_plans", [("company_id", 1), ("opportunity_id", 1), ("engine_version", 1), ("source_snapshot_hash", 1)], {"unique": True}),
    ("execution_jobs", "execution_job_id", {"unique": True}),
    ("execution_jobs", [("company_id", 1), ("created_at", -1)], {}),
    ("execution_jobs", [("company_id", 1), ("action_plan_id", 1), ("action_id", 1), ("mode", 1), ("executor_version", 1), ("source_snapshot_hash", 1)], {"unique": True}),
    ("communication_requests", "request_id", {"unique": True}),
    ("communication_requests", [("company_id", 1), ("created_at", -1)], {}),
    ("communication_requests", [("company_id", 1), ("execution_job_id", 1), ("communication_request_hash", 1), ("gateway_version", 1)], {"unique": True}),
    ("message_drafts", "message_draft_id", {"unique": True}),
    ("message_drafts", [("company_id", 1), ("created_at", -1)], {}),
    ("message_drafts", [("company_id", 1), ("communication_request_id", 1), ("message_intelligence_version", 1), ("source_snapshot_hash", 1)], {"unique": True}),
    ("whatsapp_messages", "message_id", {"unique": True}),
    ("whatsapp_messages", [("company_id", 1), ("idempotency_key", 1)], {"unique": True, "sparse": True}),
    ("whatsapp_messages", [("company_id", 1), ("client_id", 1), ("created_at", -1)], {}),
    ("whatsapp_messages", [("company_id", 1), ("provider_message_id", 1)], {"sparse": True}),
    ("whatsapp_webhook_events", "provider_event_id", {"unique": True}),
    ("whatsapp_webhook_events", [("company_id", 1), ("created_at", -1)], {}),
    ("whatsapp_conversations", [("company_id", 1), ("client_id", 1)], {"unique": True}),
    ("whatsapp_recipient_consents", [("company_id", 1), ("client_id", 1)], {"unique": True}),
    ("whatsapp_templates", [("company_id", 1), ("name", 1), ("language", 1), ("version", 1)], {"unique": True}),
    ("whatsapp_usage", [("company_id", 1), ("day", 1), ("month", 1), ("message_type", 1), ("template_name", 1), ("status", 1)], {"unique": True}),
    ("users", "verification_token", {"sparse": True}),
    ("users", "reset_token", {"sparse": True}),
    ("users", "session_id", {"sparse": True}),
)


async def ensure_indexes(database: Any) -> None:
    try:
        await database.clients.drop_index("company_id_1_client_document_1")
    except Exception:
        pass
    await asyncio.gather(*(
        database[collection_name].create_index(keys, **options)
        for collection_name, keys, options in INDEX_SPECS
    ))
