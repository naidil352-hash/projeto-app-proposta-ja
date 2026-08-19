# Test Strategy

## Safety guard

`backend/tests/conftest.py` loads the test environment. Integration fixtures additionally verify `TEST_DB_NAME == proposta_ja_test` before connecting through `TEST_MONGO_URL`.

## Test layers

- Unit tests exercise pure deterministic engines without MongoDB.
- Integration tests monkeypatch `server.db` to the dedicated test database and call route functions directly.
- Adversarial tests cover missing data, stale documents, tenant mismatches, unsafe modes, false certainty and unsupported claims.
- Network guards intercept socket, DNS, HTTP/HTTPS, SMTP, urllib, requests, httpx, aiohttp and websocket primitives.
- Performance tests process 10,000 synthetic records with time and memory bounds.
- TypeScript is validated separately.
- WhatsApp unit tests intercept network primitives. The real sandbox test is skipped unless every documented flag, whitelist and test-template confirmation is explicit.

## Commands (Windows PowerShell)

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m pytest -m unit -q
.\.venv\Scripts\python -m pytest -m integration -q

cd ..\frontend
npx tsc --noEmit
```

Focused Message Intelligence validation:

```powershell
cd backend
.\.venv\Scripts\python -m pytest tests/test_message_intelligence.py tests/test_message_intelligence_integration.py -q
```

Focused WhatsApp validation:

```powershell
cd backend
.\.venv\Scripts\python -m pytest tests/test_whatsapp_provider.py tests/test_whatsapp_integration.py tests/test_whatsapp_webhooks.py tests/test_whatsapp_security.py tests/test_whatsapp_cost_guard.py -q
```
