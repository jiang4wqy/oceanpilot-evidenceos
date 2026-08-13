# Payment Incident Mainline Integration Implementation Plan

**Goal:** Preserve OceanPilot v0.2.1 and add a second, fully reproducible synthetic
payment-incident presentation path beside the existing chargeback agent cluster.

**Base:** `origin/master@a16fc65`

**Design:**
`docs/superpowers/specs/2026-08-12-payment-incident-mainline-integration-design.md`

**Source evidence:**
`feat/feishu-demo-task7-validated-90d7344@ab2e1b0`

## Fixed constraints

- `/demo` remains the v0.2.1 chargeback console and `GET /` continues to redirect there.
- The payment cockpit is additive at `/demo/payment-incident`.
- Existing payment domain, CaseService, diagnosis engine, case API, canonical Feishu routes, and
  three SQLite stores are reused.
- No source-branch commit is cherry-picked wholesale.
- No real Oceanpayment or Feishu network is used in tests or fallback demos.
- Confirmation writes one approval audit only; it does not mutate the core case or execute a
  business action.
- Each task follows RED -> GREEN -> focused regression. A task may not start its dependent task
  until its verification gate passes.
- Existing unrelated files and v0.2.1 behavior are preserved.

## Task 1 — Record the v0.2.1 baseline

**Writes:** none initially; final results go to the combined checkpoint in Task 7.

1. Create a clean Python 3.12 virtual environment outside the repository.
2. Install `.[dev]` and run:

```powershell
python -B -m pytest -p no:cacheprovider -q
ruff check src tests examples scripts
ruff format --check src tests examples scripts
python -B -m compileall -q src tests examples scripts
python -m pip check
```

3. Record the actual test count, skips, warnings, and current OpenAPI path count.
4. Verify `/`, `/demo`, chargeback scenarios, safety scan, metrics, channel tests, and existing
   Feishu tests are included in the passing baseline.

**Gate A:** clean worktree; all baseline commands pass. Any existing failure is diagnosed before
feature work.

## Task 2 — Add the payment-incident cockpit

**Files:**

- add `src/oceanpilot/api/payment_demo.py`
- modify `src/oceanpilot/api/demo.py`
- modify `src/oceanpilot/main.py`
- add `tests/api/test_payment_incident_demo.py`
- modify `tests/api/test_demo_page.py`

### Slice 2.1 — Route and navigation shell

1. RED: add tests requiring:
   - `GET /demo` still returns the chargeback console;
   - `GET /demo/payment-incident` returns HTML and is excluded from OpenAPI;
   - both pages link to each other;
   - the payment page visibly says `synthetic` and lists prohibited actions.
2. GREEN: add a dedicated router and the smallest ordinary link in the current console.
3. Run:

```powershell
python -B -m pytest -q tests/api/test_demo_page.py tests/api/test_payment_incident_demo.py
```

### Slice 2.2 — Four real API scenarios

1. RED: page-contract tests require client calls to only the public endpoints:
   - `POST /api/v1/cases`
   - `POST /api/v1/cases/{case_id}/evidence`
   - `POST /api/v1/cases/{case_id}/diagnose`
2. Require four one-click scenarios:
   - 3DS/callback incomplete;
   - risk decline;
   - merchant configuration mismatch;
   - PSP configuration mismatch.
3. Require rendered fields to be populated from response data: readiness, rule, confidence,
   review reasons, responsible team, evidence references, next action, and audit reference.
4. Require failure to stop the sequence and show only stage, HTTP status, safe error code, and
   trace ID.
5. GREEN: implement inline HTML/CSS/JS without a frontend build or external CDN.
6. Focused gate plus visual inspection at desktop and narrow widths.

**Gate B:** payment cockpit tests pass; current chargeback demo tests remain unchanged and pass;
OpenAPI path count is unchanged.

## Task 3 — Hash Feishu external identifiers and bind receipt payloads

**Files:**

- modify `src/oceanpilot/adapters/feishu/store.py`
- modify `src/oceanpilot/api/feishu.py`
- modify `tests/feishu/test_store.py`
- modify `tests/feishu/test_feishu_routes.py`
- modify `tests/security/test_no_sensitive_data_leak.py`

### Slice 3.1 — Identifier hashing at the store boundary

1. RED tests prove raw chat and actor identifiers do not appear in the Feishu database after
   binding, action completion, or confirmation.
2. Implement one namespaced SHA-256 representation for chat keys and one for actor values.
3. Keep public store method signatures unchanged. `bind_chat_case()` and `get_chat_case()` apply
   the same chat transformation; action/approval writes transform actors.
4. Recognize the digest prefix so database reopen and repeated calls are idempotent.
5. Add a non-destructive initialization migration for legacy raw values and verify reopen/lookup.

### Slice 3.2 — Receipt payload hash

1. RED tests require same receipt ID plus identical raw payload to replay, and the same ID with a
   different payload to conflict.
2. Add nullable payload-hash columns non-destructively and backfill only when a request is safely
   claimable under the existing contract.
3. Compute the hash from exact verified callback bytes in the API adapter; never persist the body.
4. Keep duplicate in-progress behavior and existing response contracts stable.

Run:

```powershell
python -B -m pytest -q tests/feishu/test_store.py tests/feishu/test_feishu_routes.py \
  tests/security/test_no_sensitive_data_leak.py
```

**Gate C1:** raw external identifiers and callback bodies are absent from SQLite and sidecars;
identical replay is idempotent; divergent replay conflicts; all existing Feishu tests pass.

## Task 4 — Add the mainline signed Feishu fixture

**Files:**

- add `examples/signed_fixture_demo.py`
- add `tests/e2e/test_signed_fixture_demo.py`

1. RED process tests require fail-closed behavior for a non-empty work directory and non-zero exit
   on a failed assertion.
2. Generate random runtime signing credentials, tenant token, chat, reporter, reviewer, message,
   event, and action identifiers.
3. Create empty `core.db`, `feishu.db`, and `chargeback.db` under the requested directory.
4. Inject an in-process outbound transport; make no external network calls.
5. Call canonical mainline routes with signed exact bytes:
   - message intake;
   - identical message replay;
   - seven staged evidence actions;
   - diagnosis card verification;
   - confirmation;
   - identical confirmation replay.
6. Assert one case, one current diagnosis, one approval audit, no duplicate outbound card on replay,
   and byte-equivalent CaseView before/after confirmation.
7. Print an ASCII banner and stable JSON without random identifiers or credentials.
8. Assert `business_action_executed: false`.

Run:

```powershell
python -B -m pytest -q tests/e2e/test_signed_fixture_demo.py tests/feishu
python -B examples/signed_fixture_demo.py --work-dir <new-empty-directory>
```

**Gate C2:** full signed callback flow and both replay paths pass from empty stores; stdout is
stable and safe.

## Task 5 — Add combined cross-surface sentinels

**Files:**

- add `tests/security/test_surface_sentinels.py`
- preserve and extend `tests/security/test_no_sensitive_data_leak.py` only where needed

1. Exercise actual random signing material and external identifiers through the fixture/runtime.
2. Scan:
   - HTTP success and problem responses;
   - captured logs;
   - hydrated payment case/diagnosis and chargeback views;
   - approval audit serialization;
   - core, Feishu, and chargeback SQLite files and `-journal/-wal/-shm` sidecars;
   - `/demo` and `/demo/payment-incident` HTML;
   - fixture stdout/stderr.
3. Require zero occurrence of credentials, raw actor/chat/thread identifiers, and callback body
   canaries.
4. Keep deliberate test/sentinel canaries explicitly synthetic and reviewable.

Run:

```powershell
python -B -m pytest -q tests/security tests/feishu tests/e2e/test_signed_fixture_demo.py
```

**Gate C3:** all runtime surfaces pass; no secret or raw external identifier is persisted or
returned.

## Task 6 — Extend combined CI and packaging gates

**Files:**

- modify `.github/workflows/ci.yml`
- modify `pyproject.toml`
- add `tests/foundation/test_ci_contract.py`

1. Add only current secure PDF dependencies (`pypdf`, `reportlab`) while preserving v0.2.1,
   Anthropic, chargeback dependencies, and Ruff configuration.
2. Preserve the Ubuntu job and add:
   - Ruff over `src tests examples scripts`;
   - Ruff format over the same relevant Python paths;
   - compileall;
   - full pytest;
   - `pip check`;
   - signed fixture;
   - wheel/package smoke;
   - diff check.
3. Add a Windows release job after Ubuntu for:
   - PDF rebuild and PDF contract;
   - four-rule PowerShell demo against a local API;
   - signed fixture on Windows;
   - generated-artifact diff check.
4. Contract tests check capabilities, not brittle YAML quoting.

**Gate D1:** CI contract tests pass locally and the workflow remains least-privilege/read-only.

## Task 7 — Update combined documentation and PDF

**Files:**

- modify `README.md`
- modify `docs/architecture.md`
- modify `docs/demo.md`
- modify `docs/feishu-setup.md`
- modify `docs/roadmap/incomplete-work.md`
- modify `docs/submission/opening-report-supplement.md`
- modify `docs/submission/registration-copy.md`
- modify `scripts/build_submission_pdf.py`
- regenerate `artifacts/OceanPilot-开题报告补充材料.pdf`
- add `docs/reviews/checkpoint-payment-incident-mainline.md`
- add `tests/foundation/test_submission_pdf_contract.py`

1. Present the comprehensive merchant-success-agent vision with two verified synthetic vertical
   slices: payment incident and chargeback appeal.
2. Lead the runbook with payment incidents for the 16 August presentation, then show chargeback.
3. State the actual final OpenAPI count. Do not embed a volatile total test count in the PDF.
4. The PDF contract rejects stale claims: `717`, `1035 tests`, `5 API`, `8 OpenAPI`, `HTTP 501`,
   `FEATURE_DEFERRED`, or claims that diagnosis/Feishu callbacks are unimplemented.
5. Preserve explicit boundaries: no real Oceanpayment, no real Feishu-group evidence, no production
   readiness, no measured business outcome, and no prohibited action.
6. Visually render and inspect both PDF pages.

**Gate D2:** documentation, PDF, README, checkpoint, code, and OpenAPI tell the same story.

## Task 8 — Final reproduction, publication, and PR

1. Run the final local suite:

```powershell
python -B -m pytest -p no:cacheprovider -q
ruff check src tests examples scripts
ruff format --check src tests examples scripts
python -B -m compileall -q src tests examples scripts
python -m pip check
pip-audit --progress-spinner off
detect-secrets scan --all-files
git diff --check
```

2. Export the exact Git index/commit to a clean directory; create a new Python 3.12 environment;
   install, rebuild the PDF, run all tests, both demos, packaging smoke, scans, and diff checks.
3. Independently review UI truthfulness, Feishu transaction/privacy behavior, security surfaces,
   and documentation/PDF facts.
4. Push only to `feat/payment-incident-mainline-integration`; never force-push or overwrite another
   branch.
5. Require GitHub Actions green on the exact PR head.
6. Fetch the exact commit README without authentication and require HTTP 200.
7. Compare the PR with current `master`; require no deletion/regression of chargeback, console,
   metrics, model, safety, or observability capabilities.
8. Create the PR but do not merge it automatically.

**Final status boundary:** combined local and CI gates may pass while the real Feishu-group smoke
and formal Gate 4 remain not run. Only timestamped public-HTTPS callback evidence can close that
external gate.
