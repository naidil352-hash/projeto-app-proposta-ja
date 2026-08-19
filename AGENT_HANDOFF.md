# Agent Handoff

## Product objective

Proposta Já manages commercial data and proposals, then derives deterministic context, sales intelligence, advisory plans and human-reviewed communication drafts. The current system must not perform real communication.

## Architecture

Backend logic is in `backend/server.py` plus pure engine modules. MongoDB persistence and audit are handled by server routes. The Expo/React Native frontend uses file routes under `frontend/app/`.

Pipeline:

`Import -> Mapping -> Standard Records -> Learning -> Commercial Context -> Sales Intelligence -> Action Plan -> Execution Job -> Communication Request -> Message Draft -> Human Review`

## Completed phases

Phases through 3.9 are implemented: the Phase 3.8 pipeline plus measured startup/query/frontend performance corrections and two incremental module extractions.

## Current phase

Phase 3.9 centralizes startup indexes, extracts Message Draft repository reads and removes redundant frontend post-mutation reloads. Commercial semantics and API routes are unchanged. Metrics are recorded in `PERFORMANCE_BASELINE.md`.

## Engines

Relevant modules:

- `backend/commercial_context.py`
- `backend/sales_intelligence.py`
- `backend/action_planning.py`
- `backend/action_execution.py`
- `backend/communication_gateway.py`
- `backend/message_intelligence.py`
- `backend/whatsapp_integration.py`
- `backend/modules/message_drafts/repository.py`
- `backend/modules/startup/indexes.py`

Each exports a `1.0.0` version constant. Pure engines must remain free of database and network I/O.

## Collections

Pipeline collections include `commercial_contexts`, `sales_insights`, `action_plans`, `execution_jobs`, `communication_requests` and `message_drafts`. Earlier import/mapping/learning collections are listed in `DATA_MODEL.md`.

## Message contracts and states

Message Draft normal status is `READY_FOR_REVIEW`. Other contract states are CREATED, APPROVED, REJECTED, SUPERSEDED, EXPIRED, BLOCKED and SIMULATED.

Objectives, strategies, tones, warnings, templates, policies and provider contracts are closed sets in `backend/message_intelligence.py`. Only the deterministic provider is available. Generated content is preserved in `original_content`; human edits use `edited_content` and `edit_history`.

## APIs

Current pipeline APIs are documented in `API_CONTRACTS.md`. Message Draft routes support generate, get/list, regenerate, edit, approve and reject.

## Security restrictions

- Always derive tenant from the authenticated user.
- Never use frontend company IDs as authority.
- Never connect real WhatsApp, email, SMS, telephone or webhooks without a separately approved future phase.
- Never enable LIVE, disable the kill switch or enable external effects without an explicit controlled operation.
- Use only official Meta Cloud API; never use browser/WhatsApp Web automation or unofficial clients.
- Never add LLM/OpenAI fallback to deterministic message generation.
- Never mutate upstream commercial entities from projection layers.

## Test database

Use only `TEST_MONGO_URL` and `TEST_DB_NAME=proposta_ja_test`. The safety guard aborts other database names.

## Validation commands

```powershell
cd backend
.\.venv\Scripts\python -m pytest -m unit -q
.\.venv\Scripts\python -m pytest -m integration -q
.\.venv\Scripts\python -m pytest -q

cd ..\frontend
npx tsc --noEmit
```

Focused tests are named `test_<engine>.py` and `test_<engine>_integration.py` under `backend/tests/`.

Tests without `unit` or `integration` markers are classified as `legacy_external` and skipped by default because they may reload production environment values or call external servers. Run them only in a separately provisioned safe environment with `--run-legacy-external`.

## Relevant frontend files

The opportunity pipeline screens are under `frontend/app/opportunity/[id]/`, including commercial context, sales intelligence, action plan, execution, communication and message intelligence screens.

## Repository practices

Do not deploy, push, commit, modify secrets or touch production unless explicitly requested. Preserve unrelated worktree changes. Use deterministic IDs/hashes and add tenant-scoped tests for every persisted pipeline layer.

## WhatsApp operations

Read `WHATSAPP_INTEGRATION.md` before changing configuration or running the optional real sandbox test. Never place credentials in source, MongoDB, logs, documentation or frontend state.

Single-tenant deployments use the documented individual environment variables plus `WHATSAPP_CONFIG_COMPANY_ID`. Multi-tenant deployments may use secret-managed `WHATSAPP_TENANT_CONFIGS_JSON`; never commit its value.

## Remaining engineering work

The monolithic import path remains the largest structural limitation. Any future router extraction must be one domain at a time and justified by a concrete change or measurement. Do not add caches that bypass snapshot-based stale protection.

## Next phase

No Phase 4 is authorized. Do not add campaigns, bulk sending, schedulers, automatic replies, additional real channels or remove human approval.
