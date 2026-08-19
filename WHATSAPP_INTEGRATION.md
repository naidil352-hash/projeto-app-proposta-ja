# WhatsApp Business Controlled Integration

Research verified on 2026-08-15 against official Meta/WhatsApp documentation.

## Official references

- Platform and Cloud API overview: https://developers.facebook.com/docs/whatsapp/cloud-api/overview
- Cloud API setup: https://developers.facebook.com/docs/whatsapp/cloud-api/get-started
- Sending messages and 24-hour customer service window: https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages
- Message templates: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview
- Template guidelines and status: https://developers.facebook.com/docs/whatsapp/message-templates/guidelines
- Webhook overview: https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks
- Webhook endpoint and HMAC validation: https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint
- Graph API webhook validation: https://developers.facebook.com/docs/graph-api/webhooks/getting-started
- Messages webhook payloads: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components
- Status webhook reference: https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/status
- Opt-in requirements: https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in
- Messaging limits: https://developers.facebook.com/docs/whatsapp/messaging-limits
- Error codes: https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes
- Pricing: https://developers.facebook.com/docs/whatsapp/pricing
- WhatsApp Business Messaging Policy: https://business.whatsapp.com/policy

## Verified current rules

- Cloud API uses Graph API over HTTPS and OAuth access tokens.
- The Messages API endpoint is `POST /<PHONE_NUMBER_ID>/messages`.
- A customer message opens or resets a 24-hour customer service window. Free-form service messages are permitted only while that window is open.
- Outside the customer service window, a pre-approved template is required.
- Templates require a category (`MARKETING`, `UTILITY`, or `AUTHENTICATION`), language and `APPROVED` status.
- Opt-in is required before messaging a person. The business identity and communication intent must be clear, and applicable law must be followed.
- API acceptance does not prove delivery. `sent`, `delivered`, `read`, and `failed` are received by webhook.
- Webhook GET verification compares `hub.verify_token` and returns `hub.challenge`.
- Webhook POST authenticity uses `X-Hub-Signature-256`, calculated as HMAC-SHA256 of the raw body using the Meta App Secret.
- Meta retries failed webhook delivery and duplicate events can occur; provider event IDs must be deduplicated.
- As of July 1, 2025, template pricing is per delivered message. Rates depend on category and recipient country calling code. Non-template messages inside an open customer service window are free. Utility templates in that window are free.
- Official pricing publishes BRL rate cards and can change on quarterly boundaries. The application does not hardcode a Meta rate; approved template records carry a conservative `estimated_cost` reviewed by an operator.
- Brazil billing localization started July 1, 2026 for eligible customers. The official BRL rate card remains the source of truth.
- Official messaging and pair limits are higher than this application's defaults. Proposta Já deliberately applies lower internal limits.

## Architecture

`Approved Message Draft -> WhatsApp prepare -> explicit send confirmation -> guard evaluation -> provider factory -> official Cloud API -> signed webhook -> message status`

The Communication Gateway remains independent from Graph API details. Meta-specific payload conversion and HTTP live only in `backend/whatsapp_integration.py`.

## Modes

- `SIMULATION`: no network.
- `SANDBOX`: real Cloud API allowed only with every guard passing and recipient in `WHATSAPP_TEST_RECIPIENTS`.
- `LIVE`: implemented but disabled by default. It requires all normal guards plus explicit live enablement.

There is no fallback from LIVE or SANDBOX to SIMULATION.

## Environment configuration

Secrets are backend-only and must be supplied by environment or a production secret manager:

- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_BUSINESS_ACCOUNT_ID`
- `WHATSAPP_APP_ID`
- `WHATSAPP_APP_SECRET`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_WEBHOOK_SECRET` (reserved; Meta POST signature validation uses `WHATSAPP_APP_SECRET`)
- `WHATSAPP_CONFIG_COMPANY_ID`

For deployments serving multiple configured tenants, `WHATSAPP_TENANT_CONFIGS_JSON` may contain an environment-style object keyed by `company_id`. It is a secret-manager payload, not an application setting. Example key names inside each tenant object are the same `WHATSAPP_*` names listed above. Tokens remain in process memory only.

When the registry is present, outbound operations select exactly one configuration by authenticated `company_id`. Webhook POST selects exactly one configuration whose App Secret validates the raw-body signature, then verifies WABA and phone number IDs. Payload IDs are never trusted to select credentials.

Safety flags default to fail-closed:

- `WHATSAPP_ENABLED=false`
- `WHATSAPP_SANDBOX_ENABLED=false`
- `WHATSAPP_LIVE_ENABLED=false`
- `WHATSAPP_REQUIRE_HUMAN_APPROVAL=true`
- `WHATSAPP_ALLOW_EXTERNAL_SIDE_EFFECTS=false`
- `WHATSAPP_GLOBAL_KILL_SWITCH=true`
- `WHATSAPP_TEST_RECIPIENTS=`

Conservative limits:

- `WHATSAPP_DAILY_MESSAGE_LIMIT=10`
- `WHATSAPP_MONTHLY_MESSAGE_LIMIT=100`
- `WHATSAPP_DAILY_COST_LIMIT=5.0`
- `WHATSAPP_MONTHLY_COST_LIMIT=25.0`
- `WHATSAPP_MIN_SEND_INTERVAL_SECONDS=6`

Timeouts:

- `WHATSAPP_CONNECT_TIMEOUT=3`
- `WHATSAPP_READ_TIMEOUT=7`
- `WHATSAPP_TOTAL_TIMEOUT=10`

No token, App Secret, verify token, phone number ID or WABA ID is persisted in application collections or returned to the frontend.

## Sandbox setup

1. Create or select the Meta App and WhatsApp Business Account in the official dashboard.
2. Obtain the test phone number ID, WABA ID and system-user token using official Meta flows.
3. Configure the signed webhook callback and subscribe to the `messages` field.
4. Register an approved test template in the tenant's `whatsapp_templates` collection only after verifying it in WhatsApp Manager.
5. Record explicit recipient opt-in in `whatsapp_recipient_consents`.
6. Add only the authorized test number to `WHATSAPP_TEST_RECIPIENTS`.
7. Keep LIVE disabled.
8. Disable the kill switch only for the controlled test period, then restore it immediately.

## Real integration test

The real test is skipped unless every condition is explicit:

- `WHATSAPP_REAL_TEST_ENABLED=true`
- `WHATSAPP_GLOBAL_KILL_SWITCH=false`
- `WHATSAPP_SANDBOX_ENABLED=true`
- `WHATSAPP_ALLOW_EXTERNAL_SIDE_EFFECTS=true`
- recipient belongs to `WHATSAPP_TEST_RECIPIENTS`
- `WHATSAPP_REAL_TEST_TEMPLATE_NAME` is set
- `WHATSAPP_REAL_TEST_TEMPLATE_CONFIRMED_TEST_ONLY=true`

The test creates one isolated chain and makes at most one send call. There is no loop, batch, retry or scheduler.

## Webhooks and inbound messages

- Invalid signatures are rejected before persistence.
- `provider_event_id` is unique in `whatsapp_webhook_events`.
- Statuses update matching outbound messages only within the configured tenant.
- Inbound messages are stored and correlated only when exactly one client phone matches.
- Insufficient correlation remains `UNKNOWN`.
- Inbound messages never trigger an automatic reply.
- Exact configured opt-out terms update `whatsapp_recipient_consents` to `OPTED_OUT` and block future sends.

## Cost control

Budget checks run immediately before every external call. Daily/monthly message counts and conservative estimated costs are tenant-scoped. Provider webhook pricing metadata is retained with the webhook event for future reconciliation; official Meta billing remains authoritative.

## Data retention and LGPD

This phase does not automatically delete records because no approved retention duration exists yet.

Stored PII is limited to what is required for recipient validation, correlation, audit and status tracking: client ID, normalized/original phone evidence, message content already approved by a human, provider message ID, status timestamps and inbound text. Tokens and provider secrets are never stored.

Before production enablement, the data controller must approve retention periods for:

- `whatsapp_messages`
- `whatsapp_webhook_events`
- `whatsapp_conversations`
- `whatsapp_usage`
- audit and provider errors

Deletion must preserve legal/audit requirements, tenant isolation and access control. No automated deletion is implemented in this phase.

## Rollback and emergency stop

1. Set `WHATSAPP_GLOBAL_KILL_SWITCH=true`.
2. Set `WHATSAPP_ALLOW_EXTERNAL_SIDE_EFFECTS=false`.
3. Disable SANDBOX and LIVE flags.
4. Revoke the access token in Meta Business settings when compromise is suspected.
5. Preserve audit, message and webhook records for investigation.
6. Do not retry failed sends automatically.
