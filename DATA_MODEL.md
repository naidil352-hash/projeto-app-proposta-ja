# Data Model

MongoDB documents use application-level string identifiers and tenant-scoped `company_id` fields.

## Pipeline collections

- `import_batches`, `raw_records`, `import_structure_profiles`
- `mapping_candidates`, `mapping_decisions`, `mapping_confirmations`, `mapping_templates`, `mapping_applications`
- `standard_records`, `application_errors`
- `learning_events`, `learning_observations`, `company_knowledge`, `learning_feedback`, `learning_versions`
- `commercial_contexts`
- `sales_insights`
- `action_plans`
- `execution_jobs`
- `communication_requests`
- `message_drafts`
- `whatsapp_messages`
- `whatsapp_webhook_events`
- `whatsapp_conversations`
- `whatsapp_usage`
- `whatsapp_recipient_consents`
- `whatsapp_templates`

## Message draft identity

A Message Draft records `message_draft_id`, tenant and upstream IDs, channel/action metadata, objective, strategy, tone, recipient, generated content, evidence, confidence, quality, assumptions, warnings, policy, template/provider versions, source snapshot hash, status and human review metadata.

The unique logical key is:

`company_id + communication_request_id + message_intelligence_version + source_snapshot_hash`

Generated content remains in `original_content`. Human changes are stored in `edited_content` and `edit_history`.

## WhatsApp records

`whatsapp_messages` tracks internal/provider IDs, upstream correlation, recipient normalization evidence, mode, template, opt-in/window state, status timestamps and safe provider errors. It never stores provider credentials.

`whatsapp_webhook_events.provider_event_id` is globally unique for replay protection. `whatsapp_recipient_consents` and `whatsapp_conversations` are unique per tenant/client. Usage is grouped by tenant, day, month, message type, template and status.
