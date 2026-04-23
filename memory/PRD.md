# PROPOSTA JÁ - PRD

## Vision
Mobile-first sales CRM for Brazilian salespeople that turns quotes (orçamentos) from lost WhatsApp messages into organized, trackable proposals with one-tap PDF + WhatsApp follow-ups, monetized via freemium Pro subscription.

## Implemented Features

### Core (v1)
1. **Auth** — Email/password JWT (Bearer via SecureStore / localStorage on web)
2. **Company Profile** — CNPJ, phone, email, address, base64 logo
3. **Proposal Creation** — Fast form with dynamic products, BR input masks (CNPJ/CPF/phone/currency)
4. **Proposal Detail** — Status (aberto/realizado/perdido), perdido requires reason, reopen, delete, duplicate
5. **PDF Generation** — On-device via expo-print, includes logo, subtotal/discount/total, payment terms, validity date
6. **WhatsApp Integration** — wa.me deep-link with AI follow-up message
7. **Multi-select Bulk Actions** — Share PDFs or follow-up from list
8. **Clients History** — Aggregated, quick WhatsApp follow-up
9. **Dashboard** — Monthly won value, open/won/lost counts, 3-day stale alert
10. **Local Push Notifications** — Auto-scheduled every 3 days reminding open proposals

### Advanced (v2)
11. **Discount / Payment Terms / Validity Days** on every proposal, reflected in PDF
12. **Duplicate Proposal** — One-tap clone, resets status to aberto
13. **Freemium Monetization**
   - Free: 10 propostas/month (402 quota enforced server-side)
   - Pro Mensal: R$ 29,90
   - Pro Anual: R$ 299 (2 months free)
14. **Stripe Checkout** (emergentintegrations) with BRL, opens in WebBrowser, polling + webhook-based activation
15. **Store-ready** — app.json configured with bundleIdentifier, permissions, plugins for expo-secure-store, expo-image-picker, expo-notifications

## Tech Stack
- **Backend**: FastAPI + Motor/MongoDB, Stripe via emergentintegrations, bcrypt/PyJWT, HTML success/cancel pages
- **Frontend**: Expo Router SDK 54, TypeScript, expo-print, expo-sharing, expo-image-picker, expo-notifications, expo-secure-store, expo-web-browser, axios

## Business Growth Hook
Every shared PDF carries "Gerado em PROPOSTA JÁ · propostaja.app" → viral referral from every sent quote.

## Publishing
- See `/app/memory/PUBLISHING.md` for step-by-step store submission guide
- See `/app/memory/STORE_COPY.md` for ready-to-paste store descriptions + keywords
