# Independent API Safety Checkpoint

## Verdict

**PASS_CHECKPOINT** - no blocking API safety, contract, or thinness finding remains.

- Review timestamp: `2026-08-05T14:24:24+08:00`
- Reviewed commit: `23afa9bf53096b9e771928ad8ac2e2a52c4d2865`
- Reviewed subject: `feat: expose safe diagnosis API`
- Initial worktree state: clean
- Reviewed scope: `src/oceanpilot/main.py`, `src/oceanpilot/api/**`,
  `src/oceanpilot/application/case_service.py`, and `tests/api/**`

## Command evidence

All results below are actual results from the clean reviewed commit.

| Command or probe | Exit | Actual result |
|---|---:|---|
| `git status --short` | 0 | no output |
| `git rev-parse HEAD` | 0 | `23afa9bf53096b9e771928ad8ac2e2a52c4d2865` |
| `PYTHONPATH=src py -3.12 -B -m pytest -p no:cacheprovider tests/domain tests/repository tests/api -q` with unique workspace `--basetemp` | 0 | `732 passed in 16.53s` |
| pinned Ruff `0.15.22` check of `src tests` | 0 | `All checks passed!` |
| `PYTHONPATH=src py -3.12 -B -m compileall -q src tests` | 0 | no output |
| `git diff --check` | 0 | no output |
| independent adversarial TestClient probe | 0 | `adversarial_probes=PASS`; 11 problem responses checked; evidence statuses `201,200,409` |
| independent OpenAPI probe | 0 | `openapi_contract=PASS` |
| narrowed API thinness scan | 0 | no domain evaluation, SQLite access, revision mutation, or route selection in `src/oceanpilot/api` |

The frozen broad thinness pattern also matched two occurrences of
`case_revision=view.case_revision` in response-schema construction. Manual inspection
confirmed both are passive DTO field mapping, not revision calculation or mutation.

## Adversarial HTTP review

The independent probe used `TestClient(app, raise_server_exceptions=False)` and a temporary
real-file SQLite database. It verified:

- unknown route returns safe RFC 9457-style 404;
- wrong method returns safe 405 and preserves only `Allow: GET`;
- invalid UUID and an unknown body field return sanitized 422 responses without echoing the
  attacker-controlled field name or value;
- a legal-field authorization sentinel returns exactly 422
  `SENSITIVE_DATA_REJECTED` without echo;
- disabled case type returns 409 `CASE_TYPE_NOT_ENABLED`;
- a missing valid UUID returns 404 `CASE_NOT_FOUND` without echoing the identifier;
- evidence creation, replay, and conflicting reuse return 201, 200, and safe 409
  `EVIDENCE_CONFLICT` respectively;
- a not-ready diagnosis returns 409 `CASE_NOT_READY`;
- a forced runtime exception returns fixed 500 `INTERNAL_ERROR` without the exception
  sentinel;
- a forced `sqlite3.OperationalError` after successful startup returns fixed 503
  `DATABASE_UNAVAILABLE` without the database sentinel.

Every probed 4xx/5xx response used `application/problem+json`, its body status matched the
HTTP status, and `X-Trace-ID` equaled the body `trace_id`, including the unexpected-500 path.
No sentinel, SQL error, exception text, or traceback was returned.

## API and OpenAPI findings

- Request middleware creates server UUIDv4 request and trace context without reading the
  request body. Error handlers explicitly emit the trace header, including outer 500
  handling.
- Validation conversion copies only approved field locations and reason codes; it does not
  serialize Pydantic `msg`, `input`, `ctx`, `url`, or arbitrary exception attributes.
- `CASE_NOT_READY` exposes only the approved case ID, missing fields, and current revision
  extensions. Persistence invariant and unexpected failures share the fixed safe 500 shape.
- Case routes call `CaseService` and perform DTO mapping only. They contain no readiness
  evaluation, rule execution, SQLite access, revision mutation, or responsibility selection.
- Dependency overrides in diagnosis adapter tests are cleared in `finally`; production and
  adversarial tests enter application lifespan through `with TestClient(...)`.
- The actual OpenAPI document contains exactly:
  - `/api/v1/cases`
  - `/api/v1/cases/{case_id}`
  - `/api/v1/cases/{case_id}/diagnose`
  - `/api/v1/cases/{case_id}/evidence`
  - `/health`
- Diagnosis creation and replay document 201 and 200 with `DiagnosisResponse`; create
  documents its required `Location` header.
- Every documented 404, 409, 422, 500, and 503 response uses only
  `application/problem+json` and references the shared `ProblemDetails` schema. Its
  `case_id`, `missing_fields`, and `current_revision` properties are optional.

## Residual limitations

- This checkpoint approves the application/API boundary only; it is not formal Gate 3.
- The system still uses synthetic data and local SQLite. It does not connect to Oceanpayment
  or Feishu and does not execute payment, refund, risk-release, or other funds-moving actions.
- `audit_reference` is a structured locator for the atomic diagnosis audit batch, not a
  public audit-read endpoint or a list of audit event IDs.
- Three-scenario synthetic E2E coverage, broader security sentinels, CI, and release review
  remain downstream work.

## Authorization

Tasks 15–16 synthetic/security work is allowed; formal Gate 3 remains closed.
