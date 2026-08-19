# Engine Contracts

Pure engines do not perform MongoDB or HTTP I/O. `backend/server.py` owns authentication, tenant scoping, persistence and audit logging.

## Versions

- Structure Analyzer: `ANALYZER_VERSION`
- Mapping Engine: `MAPPING_ENGINE_VERSION`
- Decision Engine: `DECISION_ENGINE_VERSION`
- Learning Engine: `LEARNING_VERSION`
- Knowledge Adapter: `KNOWLEDGE_ADAPTER_VERSION`
- Commercial Context: `COMMERCIAL_CONTEXT_VERSION`
- Sales Intelligence: `SALES_INTELLIGENCE_VERSION`
- Action Planning: `ACTION_PLANNING_VERSION`
- Action Execution: `ACTION_EXECUTOR_VERSION`
- Communication Gateway: `COMMUNICATION_GATEWAY_VERSION`
- Message Intelligence: `MESSAGE_INTELLIGENCE_VERSION`
- WhatsApp provider: `WHATSAPP_PROVIDER_VERSION`

Current versions are `1.0.0`.

## Message Intelligence

`build_message_draft` receives a tenant ID and the persisted upstream Execution Job, Communication Request, Action Plan, Opportunity, optional Client/Proposal, Sales Insight and Commercial Context.

It returns deterministic objective, strategy, tone, content, evidence, assumptions, warnings, quality, confidence, policy, template/provider metadata and snapshot hash.

`MessageGenerationProvider` defines `generate`, `validate` and `health_check`. Only `DeterministicMessageProvider` is implemented. `MessageProviderFactory.create("LLM")` rejects the request; there is no fallback.

## Dominance and safety

- Knowledge cannot create an action by itself.
- Communication adapters cannot enable external effects.
- Message templates omit missing variables and cannot treat inference as fact.
- LIVE mode and external side effects remain unavailable.
- WhatsApp defaults are fail-closed. `WhatsAppConfiguration` reads backend environment only, `WhatsAppProviderFactory` has explicit SIMULATION/SANDBOX/LIVE modes, and no fallback changes a requested mode.
- `WhatsAppHttpClient` is the only Cloud API HTTP boundary. It performs one request with explicit timeouts and no automatic retry.
