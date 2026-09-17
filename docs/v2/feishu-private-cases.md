# Feishu private-case assistant — implementation and acceptance handoff

## Scope and status

One application, two isolated channels. Public groups retain only explicitly approved public knowledge. Private chats use fresh website-account pairing; legacy binding JSON never grants private-case access.

The private feature is opt-in and is not part of the deployment snapshot commit 222e754. This document describes local implementation, not completed tenant/fixed-host acceptance. Real bank connectivity is absent. All seeded cases and upstream events are synthetic / Mock.

### Runtime recovery — 2026-09-16 evening

The prior local app and Quick Tunnel processes were absent; the old tunnel's final
log entries reported TLS handshake EOF. The exact exit cause is not proven. Both
were restored against the same databases without system-network/security changes.
Only the local base URL and the two existing callback addresses changed; both
Feishu URL saves passed their actual challenges (HTTP 200). Subscription remains
developer-server delivery. No scopes, keys, bindings or corpus were replaced.

HTTPS website APIs confirm the preserved Merchant A binding and version-3 ACCEPT
case. The anonymous binding page was visually checked in Chrome: login required,
no private information displayed. Queues remain 20 private SENT and public 9 SENT
/ 2 historical UNCERTAIN, with no blind replay. Today's native receive/reply and
card-to-website navigation test await an available test window while the owner is
using Feishu. Yesterday's genuine receipts are not evidence of today's round trip.
This outage/recovery further demonstrates why fixed hosting remains a release gate.

### Current checkpoint — 2026-09-15 18:55 CST

After manual unlock, real native Feishu acceptance advanced beyond the earlier checkpoint:

- Private “为什么退回” and “当前进度，为什么退回” returned the same version-10 website case, actual review reason and rule-snapshot materials. The latter succeeded after service restart. Re-clicking the previously completed CONTEST confirmation returned the current case without a second business decision or version increment.
- Fixed a presentation defect revealed by this test: review feedback was buried below the checklist and a returned case was described as ready to submit. Shared feedback now appears first (newest first), followed by an explicit correct-materials-then-resubmit instruction. Existing file records are distinguished from review approval. Business gates are unchanged; B owns their policy.
- A NEW synthetic batch preserved the preceding case/audit and retired its private capabilities. The actual new-task DM arrived. First ACCEPT click kept the website at version 2 / NONE; the second changed the same case to version 3 / ACCEPT_PROCESSING. The native reply and automatic notice explicitly say no further contest materials are required. Both have genuine provider receipts.
- The bound user asked “我的案件进度” in the authorized group: native UI showed WEBSITE_HANDOFF only, with no case information. A separate public question about the synthetic demo returned MODEL_WITH_RETRIEVAL with the approved `public-v2` flow citation. Feishu's separately displayed “related knowledge” is not the OceanPilot bot's answer or acceptance evidence.
- Private queue: 20 SENT jobs, no uncertain/pending private jobs at this checkpoint. Public queue: 9 SENT and the same 2 historical UNCERTAIN jobs, untouched. Counts include pairing, queries and notifications, not 20 independent business operations.
- Final full pytest after the presentation fix: **2496 passed, 6 skipped, 2 dependency warnings**, 140.69 seconds. Focused private/stage/card security run: 77 passed. Source/tests Ruff and format (299 files) plus diff check pass. The pre-existing broader script lint failures described below remain.

Website mutation evidence remains authenticated HTTP, not independent browser upload acceptance. A native login-button click did not establish a visible destination before the owner switched chats; link-navigation acceptance remains unverified. No attempt was made to operate the owner's unrelated chat.

Remaining gates: second real Feishu identity, independent browser/recording acceptance by C, live forwarded/revoked/disabled/unknown identity checks and complete failure matrix, plus fixed HTTPS hosting/one-hour restart acceptance and an authorized real upstream contract. Local post-restart receive/reply is proven, but does not satisfy fixed-host acceptance. No commit, push, issue closure, bank connection or production completion is claimed.

### Earlier checkpoint — 2026-09-15 17:56 CST

The local 8002 service now enables private routes and authorized-test outbound. The owner explicitly approved binding their verified Feishu identity to isolated demo Merchant A. No other merchant was bound and no case was published to a group. Six approved public product guides remain separate; generic private-feature instructions were updated to reflect local activation.

Real tenant verification completed so far:

- Pair code was exchanged in the actual Feishu private chat, followed by owner-approved confirmation through the authenticated HTTPS website API with CSRF. Final binding survives a service restart. This is not browser-UI acceptance of the pairing page.
- A normalized synthetic notice created a fresh batch through the existing business intake and task-publication gates. Its new-task private notice has a genuine provider receipt.
- Actual Feishu clicks exercised CONTEST: first click generated a confirmation without changing case version 2; second click changed the same website case to version 3 / EVIDENCE_COLLECTING. The private result contained five requirements from the actual rule snapshot.
- Authenticated website APIs uploaded five synthetic JSON materials (using the proper merchant/operator roles), submitted for review, and recorded an operator return. The same case is version 10 / MERCHANT_REVISION_REQUIRED. Its private notification includes the actual return reason and a genuine receipt, but the Mac locked before client-side viewing and a new progress-query round trip could be checked. HTTP evidence is not a browser-upload recording.
- Merchant B's separate authenticated website session receives 404 for A's case; anonymous case access returns 401. B has not yet bound a second real Feishu identity.
- Thirteen private jobs have genuine SENT receipts. No private pending/sending jobs remained before the final service restart. Two historical public UNCERTAIN jobs were not retried or relabeled. Post-restart website binding/case state and public HTTPS health were checked; post-restart Feishu receive/reply remains pending manual unlock.

Two defects were fixed during live acceptance. Selection-card dependencies now receive a second access/revision/expiry check immediately before sending, after card preparation. Actual signed card callbacks used a Go wall-clock timestamp instead of Unix seconds; the card route now accepts that strictly bounded format only after verifying the exact SHA-256 signature, retaining the five-minute window, decryption, token and event-type checks. The event route still rejects this card-only format. No verification bypass was introduced.

Final automated regression: **2496 passed, 6 skipped, 2 dependency deprecation warnings**, 137.82 seconds. Skips require unavailable live-model credentials or PowerShell. `ruff check src tests`, `ruff format --check src tests` (299 files), and `git diff --check` passed. Broader `src tests scripts` Ruff remains blocked by ten pre-existing issues and formatting in `build_final_proposal_docx.py` / `fetch_feishu_ids.py`; these unrelated scripts were not changed.

Still NOT accepted: real ACCEPT branch, live private-query/version agreement after review return, second real Feishu identity, real negative/forward/revoke/restart checks, independent C browser/recording acceptance, and fixed-host one-hour/restart acceptance. The current Mac Quick Tunnel is not fixed hosting. No authorized bank/OceanPayment API contract or fixed server/domain has been supplied. Private answers currently use labeled structured results, not live model reasoning. See the checklist below; previous counts and disabled-feature statements are historical checkpoints.

Ownership: A owns the new Feishu modules, binding page/API, demo integration wrapper and tests. B #64 owns normalized intake, business commands, rules/deadlines, evidence/review and website workflows. This acceptance pass did not change B's business logic or app.js; it added only a binding-page link to the shared shell, which B should preserve during integration. C #66 owns independent real-device acceptance, recordings and presentation claims.

Concurrent Demo integration (2026-09-14): the separately approved task `制定项目Demo展示计划` owns its extensions to private_cases.py and case_explanations.py, plus the new test_feishu_stage_submission.py. Those extensions add two-step SUBMIT_EVIDENCE and stage presentation; they do not authorize chat uploads, evidence approval, package approval or bank submission. A retains ownership of pairing/routing, the base private test suite, initial-refusal demo wrapper and this handoff. The Demo task separately owns its website/business presentation changes. Both tasks leave the 8002 deployment, private flags and live sender unchanged until coordinated integration.

## Configuration

Existing callback paths are unchanged:

- POST /api/v2/integrations/feishu/events
- POST /api/v2/integrations/feishu/card

Both still require the existing signature, timestamp, decryption and verification-token checks. Group messages never enter the private adapter. Old business cards cannot invoke legacy commands.

New explicit settings (disabled when absent):

- OCEANPILOT_FEISHU_PRIVATE_CASES=enabled
- OCEANPILOT_FEISHU_PRIVATE_OUTBOUND=authorized-test
- OCEANPILOT_FEISHU_PRIVATE_MODEL=enabled (optional)

App ID, app secret, Encrypt Key and Verification Token remain private environment configuration. Never put them, actual user/chat IDs or generated account passwords in GitHub or recordings. Keep the encryption key stable; mismatched vault key/application fails closed.

Private persistence is additive: feishu-private-cases.db beside the configured dispute database. fp_links stores immutable binding versions and encrypted verified addresses; fp_records stores encrypted pair requests, opaque card capabilities, jobs, delivery receipts, demo batches and audit records. Public knowledge remains in separate tables/database and receives no private identity/case records.

## Account pairing

Open /api/v2/integrations/feishu/binding/page. It uses the existing website login/session API, or the already authenticated session.

1. Generate a pairing request; the 192-bit code expires in 10 minutes. Only its digest is stored.
2. Send "绑定 CODE" in the bot's private chat, never a group.
3. Read the verification phrase in that private chat.
4. Enter the phrase on the website and explicitly confirm.

The status API returns only the pair ID and state: it never returns the pairing code, DM verification phrase or raw Feishu address. Read the phrase from the private message; website polling cannot substitute for this step.

Creation, confirmation and unlink require a live session, same-origin checks and CSRF. Status queries are owner-scoped and no-store. One active account / Feishu identity / verified private address per binding. An existing binding must be unlinked, never overwritten. Unlink retains audit and revokes old cards and pending notifications.

The public page shell contains no account information. Every data or mutation route is authenticated.

## Case queries and decisions

Private chat supports 我的案件 / 当前进度 / 缺什么材料 / 为什么退回 / 下一步做什么. With multiple authorized cases it presents selection cards instead of choosing the first. A supplied case ID still goes through the live access policy. Lists, callbacks and send-time checks use current account status, role, assignment/merchant grants and case version.

Cards show actual rule-snapshot requirements, purpose, material status, shared review feedback, source identity/version and next step. Uploads use the authenticated case page, not chat attachments. Registration is not proof of sufficient evidence. ACCEPT does not continue requesting contest materials.

The first ACCEPT/CONTEST button stores a 5-minute confirmation capability. Only a second verified click can execute the existing MERCHANT_DECISION command. A capability binds account, private chat through immutable binding version, case/revision, choice, expiry and the original provider message receipt. Client-supplied confirmed=true is rejected. Business command IDs are stable for crash recovery; repeated clicks cannot execute another decision. Forwarded, expired, revoked and stale cards fail closed.

Rule/deadline/state gates remain authoritative. Intake alone is not permission to decide: an authorized Operator must publish the task through the existing PUBLISH_TASK gate. Unverified cases are presented as awaiting staff verification.

## AI truthfulness

Default replies are structured rule/case results explicitly labeled "not a model response". Optional model assistance can select relevant fact IDs from redacted allowlisted facts only. No account/chat/case identifiers, raw files, database tools or command tools are supplied. Only the original selected fact text can be rendered; arbitrary generated requirements or promised outcomes cannot enter the answer. Model failure/invalid citations/tool calls produce a labeled structured fallback.

This bounded fact-focus mode is not an unconstrained generative case agent.

## Durable delivery

A worker reconstructs notifications from committed case/audit revisions. Jobs are deduplicated by case revision (the committed business event), recipient binding version and recipient. Snapshots coalesce intermediate obsolete revisions: a stale job is blocked, never sent as current. A job retains the originating business audit metadata. New tasks, decision results, review returns and progress revisions use this path.

Callbacks enqueue replies; remote sends do not run inside business transactions. Before delivery, account/binding/case access and version are rechecked. Selection-card dependencies are also checked. Model work is outside the transaction and followed by another permission/version check. Only a genuine provider message ID becomes SENT. Timeout, malformed/missing receipt and abandoned SENDING leases become UNCERTAIN with no blind automatic retry. Existing provider UUID length normalization is retained.

The system does not guarantee exactly-once remote delivery during an unknown network outcome; it deliberately preserves uncertainty. Diagnose against provider records before any human-authorized reconciliation.

## Safe synthetic reset

Use scripts/seed_feishu_private_demo.py with the SAME case database and existing private environment configuration:

    PYTHONPATH=src:. python scripts/seed_feishu_private_demo.py \
      --db work/oceanpilot-chargeback.db \
      --credentials work/member-a/private-demo-accounts.json \
      --env-file .env --confirm-synthetic-reset

It provisions separate feishu-demo merchant A/B, scoped Operators, a Supervisor and IT administrator without overwriting existing usernames/passwords. Credentials stay in an exclusive mode-0600 local manifest.

A new batch UUID creates two new VISA 13.1 non-delivery cases through the existing synthetic registry and normalized intake. Operators publish tasks only after normal rule/deadline validation. There is no automatic merchant choice, evidence approval or upstream submission. A fresh invocation retires the preceding Feishu demo batch for private-bot use, invalidates its capabilities/jobs and preserves all old business audit records. Other pre-existing cases are untouched. Old cases remain available as history on the website; direct website operations still use its normal business policy.

If interrupted, reuse the printed --batch-id to resume THAT batch. A new ID means a new reset. Do not rerun with a new ID merely to retry an unknown external delivery. A partial account-creation failure requires recovering the saved manifest/actual accounts; never silently replace passwords.

## Local verification versus C acceptance

Run:

    PYTHONPATH=src:. python -m pytest -q tests/channels/test_feishu_private_cases.py
    PYTHONPATH=src:. python -m pytest -q
    ruff check src tests
    ruff format --check src tests

The private suite uses real website sessions/access services, normalized intake and command persistence, but a fake outbound transport. It covers pairing/CSRF, two-merchant isolation, multi-case selection, both decision branches, stale/forwarded/revoked cards, duplicate/crash recovery, persisted uncertainty, demo reset, website upload/review-return consistency, encrypted records, and safe model fallback. Fake message IDs are NOT real Feishu receipts.

The initial private-feature regression completed with 2355 passed and 6 skipped. Concurrent Demo changes were arriving during that run, so that result must not be treated as a frozen-build acceptance of the combined worktree. Re-run the base private and separate Demo suites after file ownership is stable, followed by the full regression before release. The temporary 8003 HTTP preview was stopped after its smoke checks; no visual browser acceptance or real private-message delivery was completed.

Subsequent combined local check: 52 passed (42 base private cases, 2 readiness diagnostics, 8 stage submission checks). The base suite now obtains pairing phrases from synthetic DM receipts and checks status non-disclosure, expired/regenerated/unlinked/disabled pairing claims, one-time confirmation and cross-tenant isolation. Run all three modules together; a fake transport result is still not tenant evidence. At this checkpoint the Demo task was finishing its own formatting and broader frontend work, so complete-worktree release checks remain necessary.

Final local integration check (supersedes the provisional test counts above): **2375 passed, 6 skipped, 2 dependency deprecation warnings**, in one full pytest run with isolated loopback test ports permitted. The 6 skips cover live-model credentials not supplied and unavailable PowerShell, not passed live checks. The `src/tests/scripts` content fingerprint was identical before and after: `478d029acd96447621b38d2004161cd42b12927cd1673aec275aa61fc4dd5471`. Ruff check, format check (297 files) and `git diff --check` passed. The 94-test focused integration run includes the 9 stage submission checks, original-page access checks and exact OpenAPI snapshots. The new original-page preview path is GET-only and continues to use authenticated case/file access; it adds no business command. Local source consistency is verified, but the source is still uncommitted and this is not deployment, real Feishu delivery or independent C acceptance.

C must independently record on the fixed HTTPS deployment:

1. Merchant A and B each bind their OWN Feishu identity using their own website account. Neither may share browser cookies or pairing codes.
2. Seed a fresh batch; A receives only A's actual private notice. Capture real provider receipt, case ID/revision and website state privately.
3. First contest click does not change the website; second changes the SAME case. The returned material checklist matches the actual rule snapshot.
4. Upload a real synthetic sample in the website; exercise a review return and verify private feedback/version/next step match.
5. In another fresh batch choose ACCEPT. Verify ACCEPT_PROCESSING and no further contest-material request.
6. Test unknown user, merchant B targeting A, forged case ID, group question by a bound user, forwarded card, disabled user, unbinding and prior-batch cards. No cross-user data or decision.
7. Exercise repeated callbacks, repeated confirmation, process restart and uncertain delivery. Preserve real receipts and failures.
8. Keep the fixed environment running at least one hour, then restart the service and repeat receive/reply tests. Preserve a continuous source recording plus website proof.

## Fixed deployment gate

No server/domain has been provided. Do not create paid resources, operate unknown hosts, or claim this gate passed.

Once approved, use the existing Docker Compose deployment and persistent /app/work volume. Website and both callbacks must point at the same running version and case DB. Set the fixed HTTPS OCEANPILOT_V2_BASE_URL, secure website cookies, and explicitly trusted reverse-proxy forwarded headers. Confirm Feishu event/card URL challenges separately; a health check is not a challenge or message receipt.

Reuse scripts/update_server.sh and its SQLite integrity-checked backups. Its *.db backup includes the new private vault automatically. Preserve the encryption key through an approved secret-backup process. Quiesce writes/workers for a cross-database restore point; per-database online backups are not an atomic multi-database snapshot. Do not restore one database independently and claim consistent decisions/delivery state. After restore, reconcile command receipts and uncertain jobs before allowing new decisions.

Release/recording blockers remain: fixed server/domain, Merchant B's second real identity, remaining live negative/failure checks, one-hour fixed-host acceptance, and C's independent test/recording sign-off. Merchant A pairing, both decision branches, review-return query, group isolation, approved public corpus replies and local post-restart receive/reply are evidenced as described in the current checkpoint; they do not complete the remaining gates. Do not close #64/#65/#66 merely because local tests pass.
