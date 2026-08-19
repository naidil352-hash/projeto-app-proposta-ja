# Current State

The repository implements the commercial pipeline through Phase 3.8 plus Phase 3.9 incremental performance and modularization hardening.

## Implemented

- Import, structure analysis, candidate mapping and mapping decisions.
- Mapping confirmation, templates, application plans and standard records.
- Learning events, company knowledge and bounded Knowledge-to-Decision evidence.
- Commercial Context and Sales Intelligence.
- Action Plans with human approval/rejection.
- Simulation-only Execution Jobs.
- Simulation-only Communication Requests and channel adapters.
- Deterministic Message Drafts with human edit, approval and rejection.
- Fail-closed WhatsApp SIMULATION/SANDBOX/LIVE provider, signed webhooks, status tracking, inbound recording, opt-out, budgets and rate guards.
- Concurrent startup index setup, parallel Message Draft repository reads and local frontend mutation updates.

## Safety state

- WhatsApp Cloud API support exists but all external effects are disabled by default and the global kill switch defaults to active.
- SANDBOX/LIVE require explicit backend configuration and human confirmation; no bulk or automatic send exists.
- No real email, SMS, telephone, scheduler or automatic reply integration exists.
- No OpenAI, LLM, RAG or embeddings exist.
- Production deployment and production database changes are outside these phases.

## Validation

Integration tests use `TEST_MONGO_URL` and require `TEST_DB_NAME=proposta_ja_test`. Frontend validation uses `npx tsc --noEmit`.

Default pytest execution runs marked unit/integration tests only. Legacy tests that require an external server or unsafe historical environment assumptions require explicit `--run-legacy-external` opt-in.
