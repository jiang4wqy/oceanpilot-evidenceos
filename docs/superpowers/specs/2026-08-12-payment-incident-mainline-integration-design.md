# Payment Incident Mainline Integration Design

**Date:** 2026-08-12
**Status:** Approved direction; implementation not started
**Base:** `origin/master@a16fc65` (`v0.2.1`)
**Source evidence branch:** `feat/feishu-demo-task7-validated-90d7344@ab2e1b0`

## 1. Objective

Integrate the validated synthetic payment-incident showcase into the current v0.2.1
mainline without reverting the chargeback agent cluster, the redesigned evaluator console,
or later security and observability work.

The combined competition narrative is:

> OceanPilot is a comprehensive evidence-driven merchant-success agent. The current demo
> proves two vertical slices: payment-incident collaboration and chargeback appeal. Both
> use deterministic evidence gates, auditable decisions, and human confirmation; neither
> executes a payment, refund, risk release, fund movement, production configuration change,
> or real upstream submission.

The 16 August presentation may lead with payment incidents, while the repository and console
continue to present the broader multi-scenario system.

## 2. Decision and alternatives

### Selected: B — selective integration on current mainline

Start from v0.2.1, reuse its existing payment case/diagnosis/Feishu runtime, and add only the
missing payment-incident demo surface, repeatable signed fixture, release tests, and truthful
documentation.

This is selected because it preserves 59 later mainline commits and makes the payment slice a
peer of the chargeback slice instead of an older replacement application.

### Rejected: A — leave payment incidents on a standalone branch

This is safe but leaves judges with two repositories/branches and weakens the comprehensive-agent
story. The validated source branch remains as evidence and rollback reference, not the release
target.

### Rejected: C — merge or cherry-pick the complete source branch

The source branch and v0.2.1 diverge after `2eb7269`. A direct PR would reverse or conflict with
about 190 files, including the console, Feishu store, API routes, documentation, PDF, and tests.
It risks deleting newer chargeback and security work and is therefore prohibited.

## 3. Current facts

The v0.2.1 base already contains:

- persistent `PAYMENT_INCIDENT` cases, evidence readiness, four deterministic diagnosis rules,
  evidence references, responsibility routing, and diagnosis replay;
- signed Feishu event/card callback endpoints, message-to-case intake, role-aware evidence
  questions, automatic diagnosis when ready, action receipts, and one approval audit per
  diagnosis;
- a separate persistent chargeback agent cluster, evidence deadlines, packaging, appeal drafting,
  human gates, safety scanning, metrics, and the v0.2.1 `/demo` console;
- independent payment-core, chargeback, and Feishu callback SQLite stores.

The source branch additionally proves a stable signed payment fixture, a payment case cockpit,
cross-surface sentinels, a submission-PDF fact contract, and a Windows CI release workflow.
Those implementations must be evaluated concept by concept; their files are not copied wholesale.

The missing mainline capability is a clear, repeatable payment-incident presentation path inside
the current v0.2.1 evaluator experience.

## 4. Scope

### 4.1 In scope

1. Preserve `/demo` as the default chargeback evaluator console.
2. Add `/demo/payment-incident` as the payment-incident cockpit and link it from the current
   console navigation.
3. Drive the cockpit through existing public case/evidence/diagnosis APIs. Do not add an alternate
   in-memory decision path.
4. Provide one-click synthetic payment scenarios for:
   - 3DS authentication or callback incomplete;
   - risk decline;
   - merchant-side configuration mismatch;
   - PSP-side configuration mismatch.
5. Show evidence readiness, missing evidence, diagnosis confidence, review reasons, evidence
   references, responsible team, safe next action, and audit reference.
6. Adapt a signed local Feishu fixture to the current v0.2.1 callback contract. It must cover
   message intake, staged evidence, diagnosis, human confirmation, duplicate event replay, and
   duplicate action replay without network access.
7. Preserve the confirmation rule: confirmation records approval audit only; it never changes the
   payment case or executes a business action.
8. Add focused regression, E2E, security, packaging, and CI gates.
9. Update living documentation, runbook, competition facts, and submission PDF only after the
   corresponding capability passes.

### 4.2 Out of scope

- real Oceanpayment data or production adapters;
- actual payment, refund, retry, risk release, fund movement, account adjustment, configuration
  change, or chargeback submission;
- A2A or MCP network protocols;
- production authentication/authorization, rate limiting, SLA operations, or cloud deployment;
- claiming a real Feishu-group smoke test without public HTTPS callback evidence;
- combining the three SQLite stores into one database or adding distributed transactions;
- replacing the chargeback console or redesigning unrelated v0.2.1 screens;
- importing the source branch's old `demo_query`, static console, entire Feishu store, or entire
  workflow verbatim.

## 5. Architecture

### 5.1 Route and UI ownership

- `GET /` continues to redirect to `GET /demo`.
- `GET /demo` remains the chargeback console and default judge landing page.
- `GET /demo/payment-incident` serves the payment cockpit and is excluded from OpenAPI.
- The current console navigation gains one explicit link to the payment cockpit. The cockpit
  contains a reciprocal link back to the chargeback console and a visible `synthetic` boundary.
- The new page follows the existing console palette and interaction language but lives in a
  separately testable component. No shared-CSS extraction or console-wide refactor is required.

### 5.2 Payment data flow

```text
Payment cockpit / signed Feishu fixture
  -> existing HTTP or Feishu callback adapter
  -> existing CaseService
  -> existing evidence policy + deterministic diagnosis engine
  -> existing payment SQLite store
  -> diagnosis/evidence/audit response rendered by the cockpit or card
```

The cockpit may orchestrate a demo sequence client-side, but every displayed decision must come
from existing API responses or persisted reads. It may not hard-code a diagnosis result and label
it as runtime output.

### 5.3 Feishu ownership

The existing `/api/v1/integrations/feishu` endpoint and v0.2.1 schemas remain canonical. The
fixture signs requests with random runtime credentials, calls the real verifier and callback
routes through an in-process transport, and stores data in new empty temporary databases.

One callback chat remains bound to one payment case under the current store contract. Chargeback's
channel-neutral adapters are not routed through this payment binding as part of this milestone.
This avoids ambiguous chat classification and preserves existing production boundaries.

### 5.4 Persistence and consistency

- Payment cases/diagnoses: existing core SQLite database.
- Chargeback cases/audits: existing chargeback SQLite database.
- Feishu receipts/bindings/approval audits: existing Feishu SQLite database.

There is no cross-store transaction. Read-only combined presentation must label consistency as
best effort. Payment confirmation commits only the Feishu action receipt and approval audit and
does not mutate the payment-core case.

## 6. Component changes

### 6.1 New payment cockpit router

A dedicated router/component owns `/demo/payment-incident`. It must:

- render without a frontend build or external CDN;
- expose the four synthetic scenario buttons and a reset/re-run path;
- use canonical UUIDv4 values and public request fields only;
- never accept or fabricate source reliability, confidence, route, revision, or audit values;
- render API failures as a safe, actionable state without showing evidence bodies, credentials,
  exception text, or callback payloads;
- keep all prohibited-action boundaries visible.

### 6.2 Existing console link

The v0.2.1 console receives the smallest possible navigation addition. Existing chargeback DOM,
API calls, scenario behavior, bilingual copy, theme behavior, screenshots, and tests remain
unchanged unless a direct compatibility fix is required.

### 6.3 Signed fixture runner

The runner is a supported local demo command, not test-only hidden code. It must:

- fail closed when its output directory is non-empty;
- generate random credentials and synthetic external identifiers for each run;
- use the real signature verifier, schemas, route handlers, persistence, and card rendering;
- use an in-process outbound transport and no external network;
- exercise duplicate event/action replay;
- print one stable ASCII banner and a stable JSON summary;
- exit non-zero on any missing expected state;
- report `business_action_executed: false` and verify the core case is unchanged by confirmation.

### 6.4 Documentation and release evidence

README and runbook describe two runnable slices and lead with payment incidents for the planned
presentation. The submission PDF may be regenerated only from current combined facts. Historical
test counts, path counts, or deferred-capability statements must not survive if contradicted by
the final tree.

## 7. Security and privacy

- Credentials are environment-only for real configuration and random in fixtures.
- No raw actor, tenant, chat, thread, merchant, card, callback body, or credential may appear in
  logs, audits, serialized snapshots, static assets, or stored receipt summaries.
- Existing v0.2.1 identifier-handling behavior is not weakened. Any migration of source-branch
  hashing/sentinel concepts must be adapted to current schemas and independently reviewed.
- HTTP errors and UI errors remain evidence-body-free and exception-free.
- The final tracked tree, generated PDF, SQLite artifacts produced by fixtures, and fixture stdout
  receive a secret/sensitive-data scan.

## 8. Failure behavior

- Missing Feishu configuration keeps core payment and chargeback APIs available and returns the
  existing fixed safe Feishu-unavailable response.
- An invalid/expired signature, duplicate conflict, stale case revision, cross-case reference, or
  invalid card action fails under the existing contracts; no compensating business action runs.
- If the Feishu audit store is unavailable, the payment case remains readable and no confirmation
  is falsely shown as committed.
- If a one-click demo step fails, the cockpit stops the sequence, shows the failed stage and trace
  identifier, and does not manufacture downstream state.
- Running the fixture twice uses separate empty directories/databases; reusing a non-empty output
  directory fails before mutation.

## 9. Verification gates

### Gate A — baseline preservation

- Record the clean v0.2.1 baseline test/lint/format/compile results.
- Prove `/`, `/demo`, chargeback scenarios, safety scan, metrics, channel adapters, and current
  Feishu routes retain their existing contracts.

### Gate B — payment cockpit

- Page route, static truth boundaries, all four scenarios, error display, re-run, and API-derived
  fields pass focused tests.
- The page is visually checked at desktop and narrow widths; no overlap, clipping, or unreadable
  Chinese text.

### Gate C — signed fixture and safety

- Full message -> evidence -> diagnosis -> confirmation sequence passes from empty stores.
- Duplicate event and action are idempotent.
- Confirmation produces exactly one approval audit and no core-case mutation.
- Cross-surface sensitive-data sentinel passes.

### Gate D — combined release

- All mainline tests plus new tests pass on Python 3.12.
- Ruff lint, Ruff format, compileall, wheel/package checks, PDF fact contract, and clean-copy
  reproduction pass.
- GitHub Actions is green on the exact integration commit.
- The exact commit README is anonymously readable.
- A PR from the integration branch to `master` contains only additive/surgical integration changes
  and does not delete later v0.2.1 capabilities.

Real Feishu-group smoke remains a separate external gate. Until it has timestamped HTTPS callback
evidence, Gate D may be locally/CI complete while Gate 4 remains not fully complete.

## 10. Migration rules

For every source-branch concept, choose one of three dispositions and record it in the plan:

1. **Reuse mainline:** payment domain, diagnosis engine, public case API, canonical Feishu route,
   current stores, chargeback console, security scanner.
2. **Adapt selectively:** signed fixture orchestration, payment cockpit presentation, expanded
   sentinels, PDF fact checks, demo runbook.
3. **Do not migrate:** old full-page `/demo`, `demo_query`, old static asset bundle, whole Feishu
   store/API replacements, Windows-only workflow, obsolete test counts and facts.

No source-branch commit is cherry-picked wholesale. Each implementation commit has a narrow file
scope and an explicit verification command.

## 11. Acceptance criteria

The integration is complete when a judge can:

1. open the existing v0.2.1 console and use the chargeback demo unchanged;
2. enter the payment-incident cockpit from the same product navigation;
3. run any of the four payment scenarios and see persisted, evidence-backed diagnosis and safe
   responsibility routing;
4. run one command that proves the signed Feishu payment flow and idempotent human confirmation;
5. verify from visible copy and audit output that no real business action occurred;
6. reproduce all tests from a clean checkout and observe green CI on the exact PR head.

The project may then claim two verified synthetic vertical slices under one comprehensive-agent
vision. It still may not claim real Oceanpayment integration, real Feishu-group validation,
production readiness, or measured business impact.
