# Performance Baseline

Measured on 2026-08-19 on the local Windows development environment with Python 3.11, Motor and MongoDB. Database measurements used only `TEST_MONGO_URL` with `TEST_DB_NAME=proposta_ja_test`. External APIs were not called.

## Method

- Cold import: five separate Python processes loading `.env.test` before importing `server`.
- Startup: `server.db` was replaced with the test database before invoking `on_startup`; three consecutive measurements were taken.
- Endpoint operations: a PyMongo `CommandListener` counted Mongo commands and documents returned. Synthetic tenant-scoped documents were inserted into the test database and removed afterward.
- Response size: compact JSON byte length of the returned Python object.
- Frontend calls: static inspection of the opportunity pipeline screens and their post-mutation reload paths.

## Before

### Backend structure

- `backend/server.py`: 7,923 lines.
- API route decorators: 151.
- Top-level functions: 215.

### Import and startup

- Cold import samples: 3,443.57 ms, 2,164.19 ms, 2,125.93 ms, 2,190.81 ms, 2,181.19 ms.
- Cold import median: 2,181.19 ms.
- Full startup samples: 2,221.21 ms, 54.71 ms, 61.65 ms.
- First startup: 2,221.21 ms.
- Warm idempotent startup median: 58.68 ms.

The first startup creates indexes serially. Later starts are faster because the indexes already exist.

### Endpoint operations

| Operation | Time | Mongo commands | Commands | Documents returned | Response bytes |
| --- | ---: | ---: | --- | ---: | ---: |
| Sales Intelligence, new | 80.58 ms | 11 | 5 find, 5 insert, 1 aggregate | 2 | 2,773 |
| Sales Intelligence, same snapshot | 8.89 ms | 6 | 5 find, 1 insert | 4 | 2,740 |
| Action Plan, new | 11.77 ms | 8 | 4 find, 3 insert, 1 update | 3 | 1,972 |
| Action Plan, same snapshot | 6.45 ms | 5 | 4 find, 1 insert | 4 | 1,939 |
| Message Draft, new | 80.72 ms | 13 | 10 find, 3 insert | 8 | 2,821 |
| Message Draft, same snapshot | 17.02 ms | 10 | 9 find, 1 insert | 9 | 2,788 |
| Message Draft list, one item | 2.08 ms | 1 | 1 find | 1 | 2,790 |
| WhatsApp health | 6.52 ms | 3 | 3 find | 0 | 623 |

### Frontend request amplification

- Message Intelligence initial load: 2 GET requests in parallel.
- Every Message Intelligence mutation: 1 POST followed by the same 2 GET requests, for 3 requests total.
- WhatsApp Control initial load: 3 requests in parallel.
- Every WhatsApp prepare/send mutation: 1 POST followed by the same 3 requests, for 4 requests total.
- The mutation responses already contain the updated draft/message, so these immediate full reloads are redundant for the successful path.

## Top 3 bottlenecks

### 1. Serial startup index creation

- Cause: independent `create_index` calls are awaited one at a time in `server.on_startup`.
- Evidence: first startup 2,221.21 ms versus 54.71-61.65 ms after indexes exist.
- Impact: cold starts and fresh test/development databases pay cumulative network round trips.
- Proposed solution: group independent index creation with `asyncio.gather`, preserving prerequisite ordering for index migration operations.
- Files involved: `backend/server.py` and one focused startup-index module if extraction reduces coupling.
- Risk: concurrent index builds can increase temporary database load.
- Rollback: restore sequential awaits; index definitions remain unchanged.

### 2. Sequential Message Draft repository reads

- Cause: after loading Communication Request, five independent upstream documents are read serially, followed by optional Client and Proposal reads serially.
- Evidence: new generation takes 80.72 ms and uses 10 finds; cached generation still takes 17.02 ms and reads the full chain.
- Impact: request latency accumulates Mongo round trips even though the documents are independent after IDs are known.
- Proposed solution: extract a focused Message Draft repository and use `asyncio.gather` for independent reads. Preserve all query filters and engine inputs.
- Files involved: `backend/server.py`, `backend/modules/message_drafts/repository.py`, focused tests.
- Risk: error ordering can change if multiple documents are absent; public HTTP behavior remains the same generic incomplete-chain response.
- Rollback: restore serial loader in `server.py`.

### 3. Frontend post-mutation full reloads

- Cause: mutation handlers discard returned documents and call complete screen loaders.
- Evidence: Message Intelligence uses 3 requests per mutation and WhatsApp Control uses 4 requests per mutation although POST responses contain updated state.
- Impact: redundant backend work, extra response bytes and visible latency on every human review/control action.
- Proposed solution: merge successful POST responses into local state. Keep focus reloads for cross-screen freshness.
- Files involved: `frontend/app/opportunity/[id]/message-intelligence.tsx`, `frontend/app/opportunity/[id]/whatsapp-control.tsx`.
- Risk: local lists can become stale if a mutation has undocumented side effects; current endpoint contracts return the complete affected document.
- Rollback: restore `await load()` after mutations.

## Cache assessment

Existing snapshot-hash idempotency already acts as a persistent deterministic cache for Sales Intelligence, Action Plans and Message Drafts. No new in-memory or external cache is justified. Message Draft same-snapshot generation still must verify current upstream snapshots; parallel reads reduce latency without weakening invalidation or tenant isolation.

## Background processing assessment

Measured operations complete below 100 ms locally and produce small responses. No operation currently justifies adding PROCESSING state or background infrastructure in this phase.

## After

### Backend structure

- `backend/server.py`: 7,745 lines, down from 7,923 (-178 lines; -2.2%).
- API route decorators: 151 before and after.
- Top-level functions: 215 before and after; endpoint contracts were not removed or renamed.
- Extracted modules:
	- `backend/modules/message_drafts/repository.py`
	- `backend/modules/startup/indexes.py`

### Import and startup

- Cold import after samples: 2,663.23 ms, 2,164.66 ms, 2,329.32 ms.
- Cold import after median: 2,329.32 ms. This is within process/environment variability and is not considered an improvement over the 2,181.19 ms baseline.
- Full startup after samples in separate cold processes: 66.22 ms, 53.91 ms, 57.15 ms, 70.22 ms, 106.51 ms.
- Full startup after median: 66.22 ms.
- First-startup comparison: 2,221.21 ms to 66.22 ms (-97.0%).

All 78 index declarations are preserved in one module. The obsolete Client index is dropped before concurrent index creation. User migration and company backfills remain ordered after index setup.

### Message Draft generation

| Operation | Before | After | Change | Mongo commands | Documents returned | Response bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| New draft | 80.72 ms | 46.45 ms | -42.5% | 13 before/after | 8 before/after | 2,821 / 2,822 |
| Same snapshot | 17.02 ms | 12.61 ms | -25.9% | 10 before/after | 9 before/after | 2,788 / 2,789 |

The correction reduces round-trip latency by running independent reads concurrently. It deliberately does not remove upstream reads because snapshot invalidation and stale protection require current documents.

### Frontend request amplification

- Message Intelligence mutation: 3 requests before, 1 after (-66.7%).
- WhatsApp prepare/send mutation: 4 requests before, 1 after (-75.0%).
- Initial focus loads remain unchanged and parallel: 2 requests for Message Intelligence and 3 for WhatsApp Control.
- Successful mutation responses are merged into local state. Focus reload still reconciles cross-screen changes.

### Validation

- `pytest -m unit -q`: 263 passed.
- `pytest -m integration -q`: 41 passed, 1 real WhatsApp sandbox test skipped.
- `pytest -q`: 302 passed, 94 skipped.
- `npx tsc --noEmit`: zero errors.

Unmarked legacy tests were found to reload production `.env`, use `server.db` directly, or call an external HTTP server. They are now explicitly classified as `legacy_external` and skipped unless `--run-legacy-external` is provided. This prevents accidental production/network access in the default suite. The safe marked suite is fully executed by `pytest -q`.

## Remaining risks and next bottlenecks

- Cold Python import remains approximately 2.2-2.3 seconds because the monolithic entry point imports all domains and external SDKs. No broad router extraction was attempted in this phase.
- Same-snapshot Message Draft generation still performs nine finds plus one audit insert to verify current upstream snapshots. An early cache would weaken stale detection unless supplied with a trusted aggregate version.
- WhatsApp health performs three small tenant-scoped reads (6.52 ms baseline). This is below the threshold for a new cache or aggregate endpoint.
- Concurrent first-time index creation can temporarily increase MongoDB load. Rollback is to restore sequential creation while retaining the centralized declarations.
- Legacy external tests remain available only by explicit opt-in and require a separately provisioned safe environment.
