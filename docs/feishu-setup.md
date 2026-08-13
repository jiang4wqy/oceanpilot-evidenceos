# Feishu (Lark) Integration Setup

OceanPilot exposes two locally verified callbacks under `/api/v1/integrations/feishu`.
The signed local fixture already exercises their verifier, schemas, routes, stores,
orchestrator and card rendering without network access. This guide describes the
separate, still-unverified real test-group setup for a **minimum-permission enterprise
self-built app**. The bot only creates synthetic `PAYMENT_INCIDENT` cases and records
advisory approvals; it never executes payment, refund, risk release, fund movement,
production configuration change, ticket dispatch or real upstream submission.

## 0. Prove the local signed path first

Use a new empty directory:

```bash
.venv/bin/python -B examples/signed_fixture_demo.py --work-dir work/signed-feishu-run
```

This generates random runtime credentials/identifiers, signs exact callback bytes,
drives message intake, seven evidence actions, diagnosis, confirmation, event replay
and action replay, and uses an in-process outbound transport. A non-empty directory
fails before mutation. Passing this command is local synthetic evidence only; it is
not proof of a real Feishu group.

## 1. Credentials are environment variables only

The app reads four values from the environment. **Never** commit them, print
them, or place them in fixtures — the repository and its logs contain none of
them.

| Variable | Feishu console field |
|---|---|
| `FEISHU_APP_ID` | App ID (`cli_...`) |
| `FEISHU_APP_SECRET` | App Secret |
| `FEISHU_VERIFICATION_TOKEN` | Event Subscription → Verification Token |
| `FEISHU_ENCRYPT_KEY` | Event Subscription → Encrypt Key |

Optional: `OCEANPILOT_FEISHU_DB_PATH` selects the separate callback database file
(defaults to `oceanpilot-feishu.db` next to the core case DB). Feishu tables are
never added to the core case database.

If any of the four are missing, `create_app()` still succeeds, `/health` and the
case API keep working, and the Feishu routes return a fixed safe `503` — no
partial config is echoed.

```bash
export FEISHU_APP_ID=cli_xxxxxxxxxxxx
export FEISHU_APP_SECRET=********           # from the console; do not log
export FEISHU_VERIFICATION_TOKEN=********
export FEISHU_ENCRYPT_KEY=********
export OCEANPILOT_DB_PATH=work/oceanpilot.db
export OCEANPILOT_FEISHU_DB_PATH=work/oceanpilot-feishu.db
```

## 2. Console configuration (minimum permissions)

In the Feishu Open Platform console for the test app:

1. **Add the bot capability** (机器人).
2. **Permissions** — grant only what the demo needs: send messages as the bot
   (`im:message`, e.g. `im:message:send_as_bot`). No contact, file, or
   admin scopes.
3. **Event subscription** — subscribe to `im.message.receive_v1` and set the
   request URL to your public HTTPS endpoint:
   `https://<your-host>/api/v1/integrations/feishu/events`.
   Prefer the **unencrypted** callback payload; do not enable body AES
   encryption (the service verifies the `X-Lark-Signature` over the raw body and
   does not decrypt an AES envelope).
4. **Card callback** — set the interactive-card action URL to:
   `https://<your-host>/api/v1/integrations/feishu/card-actions`.
5. **Create and publish a test version**, then add the bot to a dedicated test
   group.

The Verification Token and Encrypt Key shown in the Event Subscription page are
exactly the values you export as `FEISHU_VERIFICATION_TOKEN` and
`FEISHU_ENCRYPT_KEY`.

## 3. Public HTTPS is required

Feishu delivers callbacks to a public HTTPS URL; `localhost` will not work.
For a demo, expose the local service through a tunnel (e.g. `cloudflared`,
`ngrok`) or deploy it. During the URL verification handshake Feishu POSTs a
`url_verification` payload and the service echoes the `challenge`.

## 4. What a verified callback goes through

Each request is checked in this fixed order **before** any store, orchestrator,
or messenger call: content-type, content-length, capped raw-body stream
(≤ 64 KiB), timestamp window (±300 s), SHA256 signature over the raw bytes,
JSON parse, constant-time verification-token check, DTO validation,
event/action allowlist, then an idempotent callback claim. Blocking work runs in
a threadpool.

## 5. Real test-group smoke (not yet verified)

Once a public HTTPS endpoint exists, use this fixed rehearsal in a dedicated test group:

1. Send `3DS 验证后支付一直停在处理中，回调也没有收到` once. The bot must return one
   role-scoped need-info card and create exactly one case.
2. Click **提交当前合成示例** on each new card. Seven controlled clicks submit, in order,
   callback status, authentication status, transaction reference, occurrence time, environment,
   symptom status and integration type. The button is a synthetic-demo aid; it does not represent
   Oceanpayment data or allow a user to set source reliability, confidence or routing.
3. The seventh click must produce a diagnosis card showing `THREEDS_INCOMPLETE_V1`, cited
   evidence, confidence, responsibility and a human-review action.
4. Click **确认人工复核**. This must add exactly one approval audit and leave the payment-core
   case unchanged; it must not execute a payment, refund, risk release or configuration change.
5. Re-send the original event or repeat a card click. The same callback bytes must replay, and a
   second event ID carrying the same evidence button must not increase the evidence revision.

Capture the group screen, callback access timestamps, final diagnosis card and approval-audit
count. Also verify that the SQLite files and logs contain no Feishu credentials or raw external
identifiers. This smoke run needs a live tenant and public endpoint and is intentionally out of
scope for the offline test suite.

Until that evidence exists, documentation and presentation must say **signed local
fixture verified / real Feishu test group not verified**. It must not claim production
integration or Gate 4 PASS.
