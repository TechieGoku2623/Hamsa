# Hamsa architecture (v0.1, as built)

This describes the code in this repository. Where v0.1 deliberately differs from the target design in
[`phase-0/research-memo.md`](phase-0/research-memo.md), the difference and the path to the target are stated.

## 1. Components

```
                 ┌──────────────────────────── apps/web (React 19, Vite 8) ───────────────────────────┐
                 │  Personal & group chat UI     Shop page /b/:handle     Owner dashboard /business   │
                 │  crypto.ts  (WebCrypto E2EE)  store.ts (IndexedDB history)  realtime.ts (WS)       │
                 └──────────────┬──────────────────────────────┬──────────────────────────────────────┘
                     HTTPS /api │                         WSS /api/ws
                 ┌──────────────▼──────────────────────────────▼──────────────────────────────────────┐
                 │ services/api (FastAPI 0.142, SQLAlchemy 2.1)                                        │
                 │  routes/auth      OTP sign-up, guests, contact lookup, guest→user merge             │
                 │  routes/chat      devices, conversations, E2EE envelope relay, business messages    │
                 │  routes/business  businesses, catalog, inbox, AI toggle, orders                     │
                 │  realtime.Hub     per-user/per-device socket fan-out, call signalling relay         │
                 │  agent/           business agent cascade (below)                                    │
                 │  payments.py      UPI intent links (money goes payer → merchant VPA directly)       │
                 └──────────────┬──────────────────────────────┬──────────────────────────────────────┘
                                │ SQL                          │ OpenAI-compatible HTTP (optional)
                      SQLite (dev) / Postgres            vLLM / SGLang serving Hamsa-LM
```

| Concern | v0.1 | Target (memo) | Why the gap is safe for now |
|---|---|---|---|
| E2EE protocol | P-256 ECDH + HKDF + AES-256-GCM, per-message key wrapped per recipient device | MLS (RFC 9420) via OpenMLS, Rust core over UniFFI/WASM | Same server contract (opaque per-device envelopes, device-set check). Swapping the payload format doesn't change the relay. v0 lacks forward secrecy. |
| Message store | `envelopes` table, row deleted on ack | Cassandra store-and-forward with TTL | Same semantics: no server history for personal chats. |
| Fan-out | In-process `Hub` | NATS JetStream subject per user, gateway nodes | `Hub` is the only stateful piece, behind a 4-method interface. |
| DB | SQLite via `aiosqlite` | Postgres 18 (+pgvector) | Set `HAMSA_DATABASE_URL=postgresql+asyncpg://…`. Models use only portable types. |
| LLM | Optional; rules tier answers most turns | Sarvam-30B → Hamsa-LM on vLLM | `HAMSA_LLM_BASE_URL` points at any OpenAI-compatible server. |
| Calls | WS signalling relay for WebRTC (server side) | LiveKit SFU + SFrame for groups, coturn | Client call UI isn't built yet. |
| SMS OTP | Dev mode returns the code | DLT-registered SMS (MSG91 etc.) | `HAMSA_DEV_OTP=0` disables the dev code. The provider hook is in `routes/auth.py`. |
| SIM binding | Not applicable to web | Android/iOS native SIM binding | Needs native apps (memo R13). |

## 2. Trust boundaries

* **Personal and group chats are end-to-end encrypted.** Each browser/device generates a non-extractable
  P-256 key pair (`crypto.ts`). Only the public JWK is uploaded (the API rejects JWKs containing `d`). A message is
  encrypted once with a random AES-256-GCM key. That key is wrapped for each recipient device with
  `HKDF-SHA256(ECDH(sender, recipient), salt=message_id, info=alg|from|to)`. The AAD binds conversation, message and
  sender device, so ciphertext can't be replayed into another chat. The server stores one envelope per
  recipient device and deletes it on ack. `GET /conversations/{id}/messages` refuses personal chats.
* **Device-set check.** A send must target exactly the current set of active devices of all members (minus the
  sending device). Otherwise the API returns `409 device_mismatch` with the fresh list and the client re-encrypts. A
  device can't be silently skipped or added.
* **Security codes.** Both sides can compare a 60-digit code derived from all device keys in the chat.
* **Business chats are not E2EE, and the UI says so.** The business's endpoint is its AI agent running in Hamsa
  ("<Business> uses Hamsa AI to reply…" banner). Hamsa processes these messages as the business's data processor
  under DPDP. The server keeps history so the owner can read and take over.
* **Payments never touch Hamsa.** Orders produce a UPI intent `upi://pay?pa=<merchant VPA>&am=…&tr=<order code>`.
  The customer pays the merchant directly. "Payment done" moves the order to `payment_claimed`, and only the owner marks it
  `paid`. This keeps Hamsa outside RBI payment-aggregator scope (memo R6).
* **Age gate.** Sign-up with a birth year under 18 is refused until verifiable parental consent (DPDP Rules) is
  built. The web UI requires an 18+ confirmation.

## 3. Business agent (`services/api/hamsa/agent`)

Cascade, cheapest first. Each tier either answers or passes the turn on:

1. **Language ID** (`lang.py`): Unicode-block script detection plus romanized-Indic function words.
   Output: `en, hi, hi_latn, mr, ta, ta_latn, te, te_latn, bn, bn_latn, kn, …`. A message with no language evidence
   ("1 kg basmati", "confirm") keeps the conversation's previous language.
2. **FAQ match**: owner-written Q&A, fuzzy token-set match ≥ 80.
3. **Rules tier** (`nlu.py`, `lexicon.py`):
   * Intent keywords in six languages, each in native script and romanized. Latin keywords match on word
     boundaries, so "bas" doesn't fire inside "basmati".
   * Catalog matching on name, owner aliases, single name words and a built-in grocery lexicon ("cheeni", "चीनी",
     "சர்க்கரை", "చక్కెర" and "চিনি" all mean sugar). Typos are tolerated within a Damerau-Levenshtein bound.
   * When two items match equally ("rice"), the agent asks which one ("Basmati / Sona Masoori").
   * Quantities and units come from digits (including Indic digits), number words ("do kilo", "இரண்டு") and unit
     words (g→kg conversion). Verb-like numbers are handled ("cheeni de do" means "give sugar", not 2).
4. **LLM tier** (`llm.py`): only when no rule fires and an endpoint is configured. The system prompt carries the
   catalog, FAQ, hours and cart. Tools: `add_to_cart`, `remove_from_cart`, `view_cart`, `place_order`, `order_status`,
   `handoff_to_owner`. Up to 4 tool rounds.
5. **Verifier**: every state change goes through `tools.py`, which owns SKUs, prices, quantity bounds and stock. After an
   LLM turn, every ₹ amount in the reply must equal a catalog price, line total, cart total or order total.
   Otherwise the reply is replaced by a deterministic template. An LLM outage falls back to a template.
6. **Templates** (`templates.py`): replies in en, hi, hi_latn, mr, ta, ta_latn, te, bn. Item names are shown in
   the customer's script when an alias exists.

Handoff ("owner se baat karni hai", or missing info) sets `needs_human` and pauses the AI for that chat. The owner is
notified over WebSocket and the chat moves to the top of the inbox. The owner re-enables AI with one toggle.

Order lifecycle: `pending_payment → payment_claimed → paid → preparing → ready → delivered`, with `cancelled`
reachable before delivery. Stock is reserved at order time and released on cancel. Each status change posts a system
message to the chat in the customer's language.

## 4. API surface

All routes are under `/api`. Interactive docs are at `/docs` when the API is running.

| Area | Routes |
|---|---|
| Auth | `POST /auth/otp/request`, `POST /auth/otp/verify` (merges an active guest session), `POST /auth/guest`, `GET/PATCH /me`, `POST /contacts/lookup` |
| Devices | `POST/GET /devices`, `DELETE /devices/{id}`, `GET /conversations/{id}/devices` |
| Conversations | `POST/GET /conversations`, `GET /conversations/{id}`, `POST /conversations/{id}/members`, `POST /conversations/{id}/leave` |
| E2EE relay | `POST /conversations/{id}/envelopes`, `GET /devices/{id}/envelopes`, `POST /envelopes/ack` |
| Business chat | `GET/POST /conversations/{id}/messages`, `POST /conversations/{id}/ai` |
| Business | `POST /businesses`, `GET /businesses/mine`, `PATCH /businesses/{id}`, `GET/POST /businesses/{id}/items`, `PATCH/DELETE /items/{id}`, `GET /businesses/{id}/conversations`, `GET /businesses/{id}/orders`, `PATCH /orders/{id}`, `GET /orders/mine` |
| Public | `GET /public/b/{handle}`, `POST /public/b/{handle}/chat` |
| Realtime | `WS /ws?token=&device_id=` → events `envelope`, `business_message`, `order`, `conversation`, `devices_changed`, `needs_human`, `typing`, `signal`. Client sends `ping`, `typing`, `signal`. |

## 5. Next steps, in dependency order

1. Native Android app (Kotlin) with a Rust core (OpenMLS + storage) over UniFFI. It brings SIM binding, push and
   contacts sync. The web app becomes the linked companion.
2. Swap the v0 envelope payload for MLS. Add KeyPackage upload/claim endpoints and keep the envelope relay.
3. Postgres + NATS + Cassandra deployment, and horizontal gateway nodes.
4. Voice and video calls: 1:1 WebRTC client on the existing signalling relay, then LiveKit + SFrame for groups.
5. Serve Sarvam-30B on vLLM behind `HAMSA_LLM_BASE_URL`. Log cascade traces (`meta.trace`) for the Phase 5
   distillation set.
6. Voice notes → ASR (IndicConformer) into the same agent, then catalog photo ingestion (Qwen3.5-VL).
