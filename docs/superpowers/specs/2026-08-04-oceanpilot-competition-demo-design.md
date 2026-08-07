# OceanPilot Competition Demo Design

- Status: approved for implementation
- Date: 2026-08-04
- Target: competition demonstration, not production readiness

## 1. Outcome

OceanPilot will extend the existing case-and-evidence foundation into one controlled
demonstration flow:

```text
Feishu problem report
  -> case creation and evidence gap questions
  -> deterministic diagnosis after readiness
  -> evidence-cited responsibility routing
  -> explicit human confirmation
  -> immutable audit trail
```

The demonstration continues to use synthetic payment data. It must not execute payment,
refund, risk-release, configuration, or other money-moving actions.

## 2. Chosen Delivery Approach

Implementation is split into five dependency-gated pull requests. Each PR must pass its
acceptance gate before work begins on its dependent PR:

1. diagnosis persistence and Gate 2;
2. service orchestration and the diagnosis API;
3. three synthetic end-to-end scenarios;
4. Feishu bot and interactive cards;
5. security, CI, and release evidence.

This approach was chosen over a single large PR because persistence, orchestration, and
external integration have different failure boundaries. Parallel Feishu development was
also rejected because its message contract depends on the final diagnosis response.

## 3. Architecture and Invariants

The existing dependency direction remains unchanged:

```text
HTTP / Feishu adapters -> CaseService -> domain policies -> Store / Diagnosis ports
```

- Domain code does not import FastAPI, SQLite, or Feishu SDKs.
- The diagnosis identity is `(case_id, evidence_revision, policy_version)`.
- Repeating that identity returns the persisted snapshot without a new case revision,
  diagnosis record, or audit event.
- A diagnosis commit uses compare-and-swap against the evidence revision. Stale input
  never overwrites a newer evidence view.
- Every cited evidence ID belongs to the diagnosed case.
- Diagnosis, citations, routing output, and its audit event commit atomically.
- New evidence preserves old snapshots and makes the previous result historical; it does
  not mutate that result in place.
- High-risk, conflicting, low-confidence, low-source-quality, and no-rule outcomes require
  human review.
- Public callers cannot set source reliability, case revisions, routing decisions, or
  approval results.

SQLite schema changes are additive and preserve existing case/evidence rows. The project
continues to use the standard-library `sqlite3` adapter and one connection per unit of work.

## 4. Public Interfaces

### Repository seam

`CaseStoreSession` gains diagnosis operations that expose behavior rather than SQL details:

- read an existing snapshot by diagnosis identity;
- atomically append a new snapshot with citations, routing, and audit data;
- distinguish created, replayed, stale-revision, and invalid-reference outcomes;
- hydrate a complete diagnosis view after a database reopen.

### Service seam

`CaseService.diagnose(case_id)` loads the active evidence view, enforces readiness, invokes
the existing `DiagnosisEngine`, and persists the result. Evidence CAS conflicts may trigger
at most three complete reload/evaluate attempts. An existing diagnosis identity is replayed.

### HTTP seam

`POST /api/v1/cases/{case_id}/diagnose` no longer returns the foundation `501`. It returns a
strict diagnosis response containing outcome, identifiers, case/evidence revision,
policy version, candidates, confidence, review reasons, responsibility route, evidence
citations, and audit reference.

API failures use `application/problem+json` with stable type, title, status, code, detail,
request ID, and trace ID. Error bodies and logs never echo raw evidence or rejected secrets.

### Synthetic and Feishu seams

The internal synthetic adapter provides 3DS/callback, risk-decline, and configuration
mismatch scenarios without adding source-trust controls to HTTP DTOs.

Feishu exposes verified event and card-action callbacks. Events are idempotent by external
event ID. Cards show evidence-cited diagnosis and responsibility routing; confirmation
records approval only and never performs a payment-side action. Credentials are environment
variables and are absent from fixtures, logs, and repository files.

## 5. Failure Handling

- Missing evidence returns the current readiness gaps and does not create a diagnosis.
- A stale revision returns a stable conflict outcome after the retry budget is exhausted.
- Invalid or cross-case citations roll back the complete diagnosis transaction.
- Duplicate evidence, diagnosis, Feishu event, and card-action identifiers replay the
  original result; conflicting content is rejected.
- SQLite unavailable and unexpected failures use fixed safe responses and retain request/
  trace correlation without serializing sensitive inputs.
- If no reusable Feishu test application exists, create a minimum-permission enterprise
  test application with the user's logged-in authorization.

## 6. Test Seams and Acceptance

Tests exercise these approved public seams:

- Repository tests use a real temporary SQLite file through `CaseStoreSession`; they verify
  replay, CAS conflicts, stale priority, cross-case rejection, rollback, concurrency, and
  reopen hydration without asserting private SQL statements.
- Service tests call `CaseService`; they use port fakes only at Store/Diagnosis boundaries
  and verify observable outcomes rather than internal call counts.
- API tests use `TestClient` through the full FastAPI lifespan and assert diagnosis behavior,
  Problem Details, OpenAPI, and non-disclosure.
- E2E tests run the three scenario groups through public application/API seams.
- Feishu tests use signed event fixtures at the external callback seam; real credentials are
  reserved for the final test-tenant smoke test.

The release gate requires the complete pytest suite, Ruff checks, Python 3.12 CI, sensitive
data sentinels, a clean-clone demo, successful real-Feishu smoke evidence, Gate 2/3/4 review
reports, and anonymous access to the public README.

## 7. Pull Request Boundaries

| PR | Branch | Completion evidence |
|---|---|---|
| Persistence | `feat/diagnosis-persistence` | repository suite and Gate 2 PASS |
| Service/API | `feat/diagnosis-service-api` | domain/API suite and PASS_CHECKPOINT |
| Synthetic demo | `feat/synthetic-e2e-demo` | three scenario groups and repeatable script |
| Feishu demo | `feat/feishu-demo` | signed callbacks and one real test-group flow |
| Release | `chore/competition-release` | full CI, clean clone, Gate 3 and Gate 4 PASS |

Each PR contains only changes required by its milestone. Formatting-only baseline repairs
remain an isolated commit and are not mixed with functional changes.
