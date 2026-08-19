# API Contracts

All routes use the `/api` prefix and derive `company_id` from the authenticated user.

## Commercial intelligence

- `POST /commercial-context/{opportunity_id}/refresh`
- `GET /commercial-context/{opportunity_id}`
- `POST /sales-intelligence/{opportunity_id}/analyze`
- `GET /sales-intelligence/{opportunity_id}`

## Action plans

- `POST /action-plans/{opportunity_id}/generate`
- `GET /action-plans/{opportunity_id}`
- `POST /action-plans/{plan_id}/approve`
- `POST /action-plans/{plan_id}/reject`

Approval changes plan status only.

## Execution jobs

- `POST /execution-jobs/{action_plan_id}/create`
- `POST /execution-jobs/{job_id}/simulate`
- `GET /execution-jobs/{job_id}`
- `GET /execution-jobs`
- `POST /execution-jobs/{job_id}/cancel`

Only SIMULATION and DRY_RUN modes are accepted. LIVE is rejected.

## Communication requests

- `POST /communication-requests/{execution_job_id}/prepare`
- `POST /communication-requests/{request_id}/simulate`
- `GET /communication-requests/{request_id}`
- `GET /communication-requests`
- `POST /communication-requests/{request_id}/cancel`

No endpoint sends communication.

## Message drafts

- `POST /message-drafts/{communication_request_id}/generate`
- `GET /message-drafts/{draft_id}`
- `GET /message-drafts`
- `POST /message-drafts/{draft_id}/regenerate`
- `POST /message-drafts/{draft_id}/approve`
- `POST /message-drafts/{draft_id}/reject`
- `POST /message-drafts/{draft_id}/edit`

Approval changes draft status only. Edit preserves `original_content` and appends edit history.

## Controlled WhatsApp

- `POST /whatsapp/test/health` (no send and no network probe)
- `POST /whatsapp/consents/{client_id}`
- `POST /whatsapp/messages/{draft_id}/prepare`
- `POST /whatsapp/messages/{draft_id}/send`
- `GET /whatsapp/messages/{message_id}`
- `GET /whatsapp/messages`
- `GET /whatsapp/conversations/{client_id}`
- `GET /webhooks/whatsapp`
- `POST /webhooks/whatsapp`

Prepare never sends. Send accepts only `confirm_send`; mode, recipient, content, token, provider identifiers and policy cannot be overridden at send time. Webhook POST requires a valid Meta HMAC signature.
