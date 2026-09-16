# Feishu local recovery — 2026-09-15

Historical record of the 14:47–14:48 recovery. Public knowledge was subsequently
approved/imported and private Merchant A binding was explicitly activated. Consult
the current checkpoints in `feishu-public-knowledge.md` and `feishu-private-cases.md`
for later status; the disabled-feature limitations below describe that earlier run.

## Verified outcome

The public-group bot was restored and real replies were observed in the authorized
test group at 14:47 and 14:48 China Standard Time. Both a mention without question
text and `你会什么` returned the structured HELP card. The Feishu API returned HTTP
200 / code 0 and the durable queue recorded a distinct provider receipt for each.
This is a local connectivity/help recovery, not private-case or fixed-host acceptance.

## Findings and scoped changes

- Before recovery, nothing was listening on local port 8002 and the tunnel process
  was absent. Feishu still pointed to obsolete temporary tunnel addresses.
- The message event and existing permissions were already configured; no new
  scopes, events, credentials, group authorizations, or knowledge approvals were added.
- Exact capability questions, including `你会什么`, now enter HELP after the existing
  public-content privacy check. A recognized mention with no following text becomes
  `帮助`. Questions containing private case content retain the website handoff.
- Six SQLite databases were backed up with SQLite's backup API, and every backup
  passed `integrity_check`. The original environment file was preserved privately.
- The current checkout was started against the existing database files. No database
  was cleared. Existing migrations therefore run as part of this startup.
- A new HTTP/2 Quick Tunnel was registered with TLS verification retained. Only the
  local base URL and the existing event/card callback addresses were updated.

## Acceptance evidence

- Event callback save completed; its incoming URL challenge returned HTTP 200.
- Card callback save completed; its incoming URL challenge returned HTTP 200.
- Subscription remains developer-server delivery, with `im.message.receive_v1` and
  the existing `card.action.trigger` callback retained.
- Local and public `/health` returned HTTP 200 with `status=ok`.
- Anonymous `/api/v2/cases` returned 401; `/v2/operations` redirected to login,
  including through HTTPS.
- Live mention-only reply: `SENT / HELP`, 2026-09-15 14:47:56 CST.
- Live capability-question reply: `SENT / HELP`, 2026-09-15 14:48:46 CST.
- Provider message IDs and transport logs are retained locally in the recovery
  record and runtime database, not copied into this potentially shared document.
- Regression: `tests/channels/test_feishu_public_knowledge.py`,
  `tests/channels/test_feishu_private_cases.py`, and `tests/api/test_four_roles.py`:
  **142 passed**. Scoped Ruff lint/format and `git diff --check` passed.

## Remaining limitations

- The first recovery test received an inbound event but no confirmed outbound
  receipt; its exact transport failure was not captured. It remains `UNCERTAIN`
  and was not replayed or marked successful. A temporary launcher now records only
  operation type, HTTP/provider status, and exception type, without credentials or
  request/response bodies. The two subsequent independent messages succeeded.
- Approved public knowledge document count is still zero. HELP is a deterministic
  capability explanation, not model reasoning. General knowledge answers may still
  report insufficient evidence until documents are explicitly approved and loaded.
- Private-case routes/outbound remain disabled. This does not accept the planned
  private binding, merchant decision, notification, or full business demo workflow.
- This is a temporary tunnel to the Mac, not a fixed HTTPS deployment. Sleep,
  process termination, network changes, or a tunnel restart can interrupt service.
  A new tunnel address would require another coordinated callback/base-URL update.
- The separate Feishu web-app launch setting was not modified. New reply cards use
  the restored base URL; an existing pinned application entry may still use an old URL.
- No commit, push, issue mutation, or fixed-host one-hour/restart acceptance was done.
