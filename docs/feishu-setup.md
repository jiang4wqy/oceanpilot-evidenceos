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

Once a public HTTPS endpoint exists, capture timestamped evidence in a real test group that: one
message creates exactly one case; evidence answers advance readiness item by
item; a real diagnosis card appears at the threshold; confirmation adds exactly
one approval audit; repeated events/actions/clicks create no duplicate data; the
SQLite files and logs contain no Feishu credentials; and the UI clearly marks
the flow as synthetic with no business action executed. This smoke run needs a
live tenant and public endpoint and is intentionally out of scope for the
offline test suite.

Until that evidence exists, documentation and presentation must say **signed local
fixture verified / real Feishu test group not verified**. It must not claim production
integration or Gate 4 PASS.
