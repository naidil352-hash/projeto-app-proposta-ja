# PROPOSTA JÁ - PRD

## Vision
Mobile-first sales CRM for Brazilian salespeople that turns quotes (orçamentos) from lost WhatsApp messages into organized, trackable proposals with one-tap PDF + WhatsApp follow-ups.

## MVP Features
1. **Auth** — Email/password JWT registration & login (Bearer token via SecureStore).
2. **Company Profile** — Name, CNPJ, phone, email, address, logo (base64). Editable anytime.
3. **Proposal Creation** — Fast form: client name, CNPJ/CPF, phone, dynamic product list (name/qty/price), shipping deadline, notes. Auto totals.
4. **Proposal List & Filters** — All / Aberto / Realizado / Perdido. Stale flag on open >=3 days. Multi-select for bulk PDF share / follow-up.
5. **Proposal Detail** — Full info, share PDF, print, WhatsApp share, follow-up message, status updates (realizado / perdido with required reason / reopen). Delete.
6. **PDF Generation** — On-device via `expo-print`; share via `expo-sharing`.
7. **WhatsApp Integration** — `wa.me` deep-link with pre-filled AI follow-up message *"Passando pra confirmar contigo se podemos dar sequência no seu pedido"*.
8. **Clients History** — Aggregated list from proposals, total value, count, quick WhatsApp follow-up.
9. **Dashboard** — Month won value, open/won/lost counts, stale alert CTA.

## Tech Stack
- FastAPI + MongoDB (motor)
- Expo Router (React Native, Expo SDK 54)
- JWT Bearer + bcrypt + SecureStore
- expo-print, expo-sharing, expo-image-picker, expo-linking

## Business Growth Hook
Every shared PDF carries a "Gerado em PROPOSTA JÁ" footer → viral referral loop from every sent quote to client inboxes.
