# Architecture

## Runtime

- Backend: Python 3.11, FastAPI, Motor, MongoDB.
- Frontend: Expo Router, React Native, TypeScript.
- Backend application entry point: `backend/server.py`.
- Pure deterministic engines live in individual modules under `backend/`.
- Incrementally extracted infrastructure lives under `backend/modules/`; only boundaries with measured coupling or latency are extracted.

## Incremental modules

- `modules/message_drafts/repository.py` owns tenant-scoped upstream reads for Message Draft generation and groups independent Mongo queries.
- `modules/startup/indexes.py` owns the complete Mongo index declaration set and creates independent indexes concurrently.

FastAPI route contracts remain in `server.py` in Phase 3.9. No broad router rewrite was performed.

## Commercial pipeline

1. Universal Import and structural analysis.
2. Candidate mapping and deterministic mapping decisions.
3. Mapping application into standard records.
4. Event-sourced company knowledge.
5. Commercial Context projection.
6. Sales Intelligence projection.
7. Action Planning into advisory Action Plans.
8. Action Execution into simulation-only Execution Jobs.
9. Communication Gateway into simulation-only Communication Requests.
10. Message Intelligence into human-reviewed Message Drafts.
11. Controlled WhatsApp integration into prepared messages, explicit confirmation, official Cloud API and signed webhook status tracking.

Each layer consumes persisted outputs from prior layers. Upstream Opportunity, Proposal, Client and Product documents are not mutated by the intelligence, planning, execution, gateway or message layers.

## Safety boundaries

- `action_execution.py` orchestrates jobs and does not contain channel integrations.
- `communication_gateway.py` routes to offline simulation adapters.
- `message_intelligence.py` composes deterministic template content and does not send it.
- No layer imports OpenAI or an LLM provider.
- Human approval of a draft does not send a message.
- WhatsApp external calls are isolated in `WhatsAppHttpClient` and are unreachable unless mode flags, kill switch, tenant, approval, opt-in, template/window, whitelist, rate and budget guards all pass.
- Webhook payloads are authenticated with Meta's `X-Hub-Signature-256` HMAC-SHA256 contract before persistence.
