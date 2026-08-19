# Security Rules

## Tenant isolation

- Derive `company_id` from the authenticated session.
- Never accept frontend `company_id` as authority.
- Every read and write for pipeline documents includes tenant scope.
- Validate ownership across all upstream documents before projection or execution.

## Environment safety

- Integration tests use only `TEST_MONGO_URL` and `TEST_DB_NAME`.
- `TEST_DB_NAME` must equal `proposta_ja_test`; otherwise tests abort.
- Do not use production `MONGO_URL` or `DB_NAME` in tests.
- Do not commit or print secrets.

## External effects

- LIVE execution is disabled by default and requires explicit backend enablement.
- `allow_external_side_effects` defaults false; the global WhatsApp kill switch defaults true.
- Communication Gateway adapters remain offline simulations; the WhatsApp provider is a separate controlled boundary.
- Message Draft approval does not send or simulate communication.
- No SMTP, websocket, SMS, phone, unofficial WhatsApp, OpenAI or LLM integration exists.
- The only external HTTP integration is the official Meta WhatsApp Cloud API client, reachable only after all WhatsApp guards pass.
- WhatsApp tokens, App Secret, verify token, WABA ID and phone number ID must never be returned, logged or persisted.
- Multi-tenant credentials may use `WHATSAPP_TENANT_CONFIGS_JSON` in a secret manager; outbound selection is by authenticated tenant and webhook selection is by a unique valid signature.
- Webhook POST must validate `X-Hub-Signature-256` against the raw body before parsing or persistence.

## Data integrity

- Intelligence layers do not mutate Opportunity, Proposal, Client or Product.
- Deterministic snapshot hashes exclude timestamps, UUIDs and attempts.
- Regeneration preserves prior versions; human edits preserve generated originals.
