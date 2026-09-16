# Public knowledge iteration — 2026-09-15

## Scope and implementation

This iteration follows the owner's request to continue improving the public bot.
No private-case flag, application permission, business authorization, or upstream
connector was enabled. No commit or push was performed.

- Normalize a small, explicit set of Chinese product-query synonyms, such as
  `材料怎么传`, `怎么补交文件`, `如何登录`, and `私聊能查进度吗`.
- Prefer specific title matches, ignore the product name as relevance evidence,
  require meaningful query coverage, and remove weak secondary hits. Retrieval
  remains lexical, not semantic/vector search.
- Route explicit business requests to the website before invoking the public
  model. The bot still has no business-service reference or execution tools.
  This query check is an additional guard, not proof of comprehensive redaction.
- Give HELP and NO_MATCH concrete supported questions instead of a dead end.
- Treat a valid model abstention (empty source list) as NO_MATCH, rather than
  displaying unrelated source excerpts. Invalid responses and model failures
  still receive an explicitly labeled retrieval fallback.
- Ask for short, direct answers while retaining source limitations and Mock labels.
- Render citations as numbered human-readable titles. Original source IDs remain
  in answer/audit structures; display formatting does not mutate them.
- Clarify the already-existing product terminology: the operations surface is the
  staff workspace, not a separate permission role. Merchant, operator and
  supervisor responsibilities remain subject to the existing account/case policy.
  Only the login/roles document changes to `public-v2`; the other five remain v1.

## Validation evidence

- Expanded release-corpus tests cover 26 supported natural questions and unrelated
  questions with misleading product-name or single-keyword overlap.
- Real configured DeepSeek calls returned MODEL_WITH_RETRIEVAL with approved source
  IDs for material upload, private-chat availability and merchant/staff distinctions.
  The roles question was rechecked after clarifying the operations terminology.
- A repeated channel regression exposed a pre-existing random-fixture failure:
  a free-form `tx-` + UUID hex reference can contain a Luhn-valid digit sequence.
  Only private-case test fixture references were changed to an entropy-preserving
  alphabetic encoding. A deterministic regression proves PAN-shaped raw input is
  still rejected while the safe synthetic identifier is accepted. No production
  sensitive-data rule was weakened.
- Final channel/Feishu suite after the fixture correction: **415 passed** in
  38.24 seconds, with two existing deprecation warnings. Scoped Ruff lint/format
  and `git diff --check` passed.
- Local service was restarted with the final corpus. `/health` returned 200;
  anonymous `/api/v2/cases` still returned 401. Existing SENT and UNCERTAIN records
  were not replayed, cleared or rewritten.

## Earlier live acceptance blocker (resolved for the subsequent public-QA test)

The previously configured Quick Tunnel expired after connection failures.
A fresh tunnel attempt also failed its automatic connectivity pre-check: both
QUIC/UDP and HTTP/2/TCP to the Cloudflare edge were unavailable. It exited with
`context deadline exceeded`, including `TLS handshake with edge error: EOF` and
timeout diagnostics. Cloudflare documents the required outbound 7844 connectivity
in its [network requirements](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/).
This does not identify which local proxy, network device or upstream path caused
the failure, and no system proxy/firewall changes were made.

The newly allocated but unusable hostname was NOT saved into Feishu or `.env`.
No live sourced-answer message was sent this turn, and no receipt was invented.
The unsent agent-created test draft in the authorized group was cleared.

At the end of that iteration, delivery status was **local iteration complete; public transport and live
group acceptance blocked**. The prior callback hostname is unchanged but offline.
Restore an authorized network path or provide an explicitly authorized fixed
server/domain before resuming real group tests. Private-case and fixed-host
one-hour acceptance are still separate unfinished work.

## Network recovery and real group answer, 2026-09-15 16:44 CST

- Read-only network probes showed port 7844 connectivity had recovered. A fresh
  HTTP/2 Quick Tunnel registered at 16:39:50; its official DNS, TCP, UDP and API
  pre-checks all passed. No system proxy, DNS, route, firewall or trust settings
  were changed, and TLS verification was not disabled. The previous intermittent
  failure's exact upstream cause remains unproven.
- Public `/health` returned 200. The app was gracefully restarted to load the new
  base URL, using the existing database and approved corpus. Both existing Feishu
  callbacks were updated once and passed their URL challenges with HTTP 200.
  Developer-server subscription and existing event/callback subscriptions remain.
- In the authorized group, an actual mention plus `材料怎么传` received a visible
  AI answer citing the approved material-upload guide (`public-v1`). The answer
  explains website login, authorized-case upload and review feedback, and warns
  against sharing business attachments or personal information in the group.
- The persisted result at 16:44:23 is `SENT / MODEL_WITH_RETRIEVAL`, with a real
  provider message receipt and provider response code 0. Exact receipt, URL and
  process details are kept only in the ignored private recovery directory.
- The answer's website button points to the new `/v2/login` URL. Two historical
  `UNCERTAIN` records were neither replayed nor rewritten. Private cases remain
  disabled. This network-only recovery made no business-code or corpus changes;
  the earlier 415-test result remains the code regression evidence, not a new run.

Status: **public transport and one sourced-answer group smoke test passed**.
This is still a Mac-hosted Quick Tunnel, not fixed deployment or a one-hour
stability guarantee. Full negative-path tenant tests and independent C acceptance
remain separate outstanding work. No commit or push was made.
