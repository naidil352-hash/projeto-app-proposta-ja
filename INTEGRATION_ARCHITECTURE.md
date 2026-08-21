# CRM and ERP Integration Architecture

## Phase 4.0

The Integration Hub is provider-neutral and tenant-scoped. It validates
connection metadata, produces canonical synchronization events and returns
preview plans only. It does not persist data, call a provider API, receive a
webhook, write to a CRM/ERP or alter commercial records.

## Canonical entities

The initial vocabulary is `CLIENT`, `CONTACT`, `PRODUCT`, `OPPORTUNITY`,
`PROPOSAL`, `ORDER`, `INVOICE` and `STOCK`. Every tenant must explicitly set
the source of truth for each entity to either `EXTERNAL` or `PROPOSTA_JA`.

## Safety contract

- Connection metadata rejects tokens, API keys and passwords.
- Every event receives a deterministic idempotency key.
- The only output in this phase is `PREVIEW`; external I/O is always false.
- Export is blocked unless Proposta Ja owns the entity and a human approves it.
- Disabled connections remain blocked.

## Next phases

Provider adapters will remain outside `server.py`. CSV/XLSX, RD Station CRM
and Omie can later implement the same contract. Credentials must be stored in
an encrypted secret store. Webhooks must verify the provider signature,
persist the event and enqueue idempotent work before any synchronization.

## Phase 4.1: normalized tabular preview

`tabular_preview_adapter.py` accepts only already-parsed, in-memory tables.
It supports the labels `CSV`, `XLSX` and `TABULAR`, but it never opens a file.
An explicit header mapping converts each row into a canonical Integration Hub
event and preview. Duplicate headers, unknown mapped headers and a header
mapped to more than one canonical field are rejected.

## Phase 4.2: local persistence boundary

`modules/integration_hub/repository.py` receives an injected database and does
not create a Mongo client. It persists only non-secret connection metadata and
tenant-scoped canonical events. A connection is unique per company and an
event is unique per company, connection and idempotency key. Routes, workers
and provider adapters remain out of scope.

## Phase 4.3: provider contract and registry

`modules/integration_hub/adapters.py` declares static provider capabilities;
it contains no transport, credentials or network code. The registry permits
only explicitly registered providers. `service.py` combines a persisted
tenant-scoped connection, a registered capability and an existing canonical
event into a preview. It never calls an adapter for external I/O.
