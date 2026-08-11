# OceanPilot Payment Incident Showcase Design

- Date: 2026-08-11
- Target: 2026-08-16 competition demonstration
- Status: approved in conversation; pending written-spec review
- Product position: cross-border merchant-success agent platform
- Implemented showcase wedge: synthetic payment-incident collaboration

## 1. Outcome and Product Boundary

OceanPilot is presented as a cross-border merchant-success agent platform built around a
shared case, evidence, diagnosis, responsibility, and collaboration protocol. The long-term
product surface includes merchant onboarding, payment incidents, refunds and chargebacks,
and reconciliation operations.

The August 16 demonstration implements one truthful vertical slice only:

```text
Feishu payment-incident report
  -> case creation and thread binding
  -> evidence-gap questions
  -> structured evidence submission
  -> deterministic diagnosis after readiness
  -> evidence-cited responsibility recommendation
  -> explicit human confirmation
  -> audit record and read-only case cockpit
```

Payment incidents are the first product wedge, not the final market definition. Onboarding,
refund and chargeback, and reconciliation modules are concept previews. They do not call a
business backend, produce diagnoses, or claim completed Oceanpayment integration.

The demonstration remains synthetic. It never executes payment, refund, risk-release,
funds movement, production configuration changes, or automatic work-order execution.

## 2. Experience Architecture

The existing dependency direction remains unchanged:

```text
Feishu callbacks / HTTP / demo UI
  -> application orchestration and CaseService
  -> evidence policies, state machine, and diagnosis rules
  -> store ports
  -> core SQLite and separate Feishu SQLite
```

The real experience has three surfaces:

1. A dedicated Feishu payment-incident group handles conversational intake, evidence
   questions, structured card actions, diagnosis results, and human confirmation.
2. `/demo` presents the broader merchant-success agent platform. Payment incidents are
   labelled `LIVE / SYNTHETIC`; the other three modules are labelled `CONCEPT PREVIEW`.
3. `/demo/cases/{case_id}` is a read-only cockpit backed by the same persisted case used by
   Feishu and the public case API.

The demo UI uses FastAPI and static HTML, CSS, and JavaScript. It does not add a JavaScript
framework, ORM, or separate UI service. The cockpit does not mutate cases.

## 3. Intake and Case Binding

The demo operates in a dedicated incident-intake group. The group context represents the
user's intent to open a payment-incident case, avoiding a false claim of general-purpose
intent classification.

A synthetic merchant reference is configured for the demo group. The first user text in a
new thread becomes the case summary but is not treated as trusted diagnostic evidence.
Evidence enters the case only through the existing typed evidence contract.

The binding identity includes tenant, chat, and thread/root context. It permits multiple
incident threads in one group while ensuring that repeated delivery of the same thread does
not create a second case. Robot-authored messages are ignored to prevent reply loops.

For every callback, processing order is fixed:

1. validate content type and the 64 KiB declared and actual body limits;
2. validate timestamp presence and the five-minute window;
3. verify the signature against the original request bytes;
4. parse JSON and compare the verification token in constant time;
5. validate the external DTO and event/action allowlist;
6. claim the callback idempotency key;
7. enter application orchestration and send any resulting card.

No Store, CaseService, or outbound client is accessed before successful verification.

## 4. Evidence and Diagnosis Flow

An empty payment-incident case starts in `NEED_INFO`. Existing domain readiness logic asks
for transaction reference, occurrence time, environment, a symptom signal, and integration
type. Plugin incidents additionally require platform and plugin version.

Question cards display the case identifier, revision, completion ratio, missing evidence,
the next question, the reason for the question, and the target role. Card callers may submit
only evidence availability and the typed answer for the server-selected evidence code.

The server generates the evidence identifier, observation metadata, and safe source
reference and fixes the public Feishu origin to:

```text
source_type = MERCHANT
source_reliability = USER_REPORTED
synthetic = true
```

Callers cannot set trust, confidence, policy, revision, route, responsible team, status,
or approval result. Each submission calls the real `CaseService.add_evidence()` and
recalculates the active evidence view and readiness.

When readiness reaches `EVIDENCE_READY`, the existing `CaseService.diagnose()` and
`RuleDiagnosisEngine` run. The result card includes the rule, candidate cause, explanation,
confidence, evidence references, responsibility team, priority, next action, case and
evidence revisions, and human-review reasons.

No matching rule produces `POLICY_GAP` and human review. Conflicting evidence produces
`CONFLICTING_EVIDENCE` and human review. Risk-decline diagnoses force human review. The
system never invents a fallback diagnosis.

## 5. Human Confirmation and Audit

A confirmation is valid only when all conditions remain true at action time:

- the case is synthetic;
- the referenced diagnosis is the current diagnosis;
- the diagnosis status is `CURRENT`;
- `requires_human` is true;
- the case status is `HUMAN_REVIEW`.

The confirmation record contains a stable confirmation and approval identity, case and
diagnosis identifiers, a hashed actor identifier, server request and trace identifiers,
timestamp, `CONFIRMED`, and the synthetic flag. A semantic uniqueness constraint prevents
different callback events for the same confirmation from producing multiple approvals.

Confirmation records acknowledgement only. The case remains `HUMAN_REVIEW`, and the UI
states: "Recommendation confirmed and recorded; no business action was executed."

## 6. Idempotency and Failure Semantics

The integration prevents duplicate cases, evidence, diagnosis snapshots, outbound cards,
and approvals across normal Feishu retries and repeated clicks:

- callback identity plus payload hash detects replay and conflicting reuse;
- tenant/chat/thread binding reuses an existing case;
- evidence identity and content hash use the existing evidence replay contract;
- diagnosis identity remains `(case_id, evidence_revision, policy_version)`;
- outbound messages use a stable idempotency key;
- confirmation identity and case/diagnosis/action semantics prevent duplicate approval.

The core and Feishu databases remain separate and do not claim distributed exactly-once
transactions. A retry after case creation reloads the thread binding and reuses the original
case. Retryable callback claims are released only before an irreversible business-side
effect; otherwise replay and stable binding prevent duplication.

Stable errors are:

| Condition | Result |
|---|---|
| callback body too large | `413 FEISHU_CALLBACK_TOO_LARGE` |
| invalid signature, token, or time window | `401 FEISHU_CALLBACK_UNAUTHORIZED` |
| invalid event, action, or form | `422 FEISHU_INVALID_CALLBACK` |
| same idempotency key with different content | `409 FEISHU_IDEMPOTENCY_CONFLICT` |
| Feishu or SQLite unavailable | safe `503` Problem Details |
| unexpected failure | fixed `500 INTERNAL_ERROR` |
| stale diagnosis card | `200` safe refresh message and no approval |

Problem responses and logs never include callback bodies, form answers, evidence contents,
credentials, signatures, tokens, SQL, tracebacks, or raw Feishu user identifiers.

## 7. Optional Feishu Runtime

Feishu credentials are read only from environment variables:

```text
FEISHU_APP_ID
FEISHU_APP_SECRET
FEISHU_VERIFICATION_TOKEN
FEISHU_ENCRYPT_KEY
```

They are absent from code, fixtures, logs, SQLite, exceptions, and UI output. Test secrets
are generated at runtime.

Incomplete or missing configuration does not prevent the core application from starting.
Health, case, diagnosis, and local demo routes continue to work. Registered Feishu routes
return fixed `503 FEISHU_UNAVAILABLE` responses without consuming or reflecting the body.
The Feishu runtime and separate callback database are initialized only inside FastAPI
lifespan.

## 8. Demo Pages

### Merchant-success agent home

`GET /demo` displays the full lifecycle and four module cards:

- payment-incident collaboration: `LIVE / SYNTHETIC`;
- merchant onboarding: `CONCEPT PREVIEW`;
- refunds and chargebacks: `CONCEPT PREVIEW`;
- reconciliation operations: `CONCEPT PREVIEW`.

Concept cards contain future inputs, evidence contracts, expected outputs, and business
value only. They do not invoke Store or diagnosis operations.

### Read-only case cockpit

`GET /demo/cases/{case_id}` displays the persisted summary, merchant reference, status,
case and evidence revisions, readiness, missing evidence, evidence provenance, conflicts,
current diagnosis, confidence, citations, responsibility recommendation, priority, next
action, review reasons, audit timeline, confirmation state, and persistent synthetic notice.

The cockpit aggregates read-only data from the core case store and Feishu confirmation
store. It does not imply a distributed transaction between them and exposes no business
mutation controls.

## 9. Public Test Seams

TDD covers only approved public seams:

1. Signed Feishu event callback: verification, message intake, case creation and binding,
   question cards, duplicate delivery, multiple threads, and robot-message suppression.
2. Signed card-action callback: server-owned evidence properties, readiness progression,
   automatic diagnosis, callback/command replay, stale cards, and semantic confirmation
   uniqueness.
3. Outbound messenger: tenant-token request, interactive-card send, stable idempotency key,
   and fixed safe failures.
4. Read-only cockpit HTTP surface: consistency with the public case view, safe citations,
   absence of mutation controls and credentials, and concept modules with no Store writes.
5. Synthetic end-to-end flow: message, case, questions, evidence, diagnosis, route,
   confirmation, audit, and cockpit for 3DS/callback and risk-decline scenarios.

Existing merchant-configuration and PSP-configuration scenarios remain covered through the
API and PowerShell demo but are not mandatory live-stage interactions.

## 10. Demonstration Fallbacks

The stage has three verified levels:

1. Real Feishu test group through a public HTTPS callback.
2. Locally signed event fixtures through the same HTTP callbacks and business orchestration.
3. Existing `examples/demo.ps1` synthetic API demonstration.

A recording of a successful real-Feishu run is a final visual backup and is identified as a
recording rather than live execution.

All surfaces use consistent labels:

- `LIVE` for currently running interaction;
- `SYNTHETIC` for real code operating on test data;
- `CONCEPT PREVIEW` for future product surfaces.

## 11. Acceptance Criteria

The August 16 build is accepted only when:

1. one signed Feishu message creates exactly one case;
2. the bot sends a role-labelled evidence question;
3. structured submissions advance the real completion ratio;
4. diagnosis is unavailable before readiness;
5. the last required evidence triggers the real persisted diagnosis;
6. the result shows rule, confidence, citations, responsibility, and next action;
7. risk and low-source-quality results require human review;
8. confirmation creates one correlated approval audit and executes no business action;
9. the read-only cockpit displays the same persisted case;
10. duplicate events, actions, diagnoses, and clicks create no duplicate records;
11. credentials are absent from repository, logs, responses, audit, SQLite bytes, and UI;
12. signed-fixture and PowerShell fallback paths run independently;
13. full pytest, Ruff, compileall, and `git diff --check` pass;
14. one real test-group smoke run succeeds before the competition demonstration.

## 12. Implementation Priority

The dependency order is:

```text
P0 Feishu application/store contract and correlated approval audit
  -> P0 signed callback routes and runtime wiring
  -> P0 complete message/evidence/diagnosis/confirmation E2E
  -> P0 real Feishu test-group smoke
  -> P1 read-only case cockpit
  -> P1 merchant-success agent home and concept previews
  -> P1 local signed-fixture fallback
  -> P2 visual motion and polish
```

Visual polish may be removed if time is constrained. Main-chain truthfulness, idempotency,
security, correlated audit, and fallback verification are not optional.
