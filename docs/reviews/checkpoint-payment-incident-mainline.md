# Payment Incident Mainline Integration Checkpoint

**Date:** 2026-08-13  
**Branch:** `feat/payment-incident-mainline-integration`  
**Base:** `origin/master@a16fc65` (`v0.2.1`)

## Status

**LOCAL IMPLEMENTATION CHECKPOINT — PASS FOR DOCUMENTATION FACTS**

This checkpoint records the facts available in the local integration branch. It is not Gate 4,
does not claim a real Feishu test-group smoke, and does not claim the exact branch head has green
remote GitHub Actions or anonymous public-read evidence.

## Preserved mainline capability

- `GET /` still redirects to `/demo`.
- `/demo` remains the v0.2.1 chargeback evaluator console.
- The chargeback agent cluster, safety scan, metrics, model composition, persistence and mock
  upstream remain present.

## Added payment-incident presentation path

- `/demo/payment-incident` is additive, excluded from OpenAPI and linked bidirectionally with
  `/demo`.
- It runs four synthetic scenarios only through the public case/evidence/diagnose APIs.
- Displayed readiness, rule, confidence, review reasons, responsibility, evidence references,
  next action and audit reference come from runtime responses.
- Failure stops the sequence and exposes only stage, HTTP status, safe code and trace ID.
- The page visibly says synthetic and prohibits payment, refund, risk release, fund movement and
  production configuration changes.

## Signed local Feishu evidence

`examples/signed_fixture_demo.py` uses random runtime credentials and identifiers, exact signed
bytes, the canonical verifier/routes/schemas/stores/orchestrator/card renderer, and an in-process
outbound transport. It exercises message replay, seven evidence actions, diagnosis, confirmation
and confirmation replay from empty stores. Its stable summary requires:

- one approval audit;
- no duplicate replay side effects;
- `case_unchanged_by_confirmation: true`;
- `business_action_executed: false`.

The fixture fails closed on a non-empty work directory and makes no external Feishu call.

## Privacy and release facts

- External Feishu chat/actor values are hashed at the store boundary.
- Receipt identity is bound to the verified payload hash without persisting callback bodies.
- Combined surface sentinels cover HTTP, logs, hydrated/serialized state, SQLite files/sidecars,
  demo HTML and fixture output.
- Python 3.12 CI is configured for tests, Ruff lint/format, compileall, signed fixture, packaging,
  PowerShell demo, PDF smoke and diff checks.
- The application currently exposes 19 OpenAPI paths. `/`, `/demo` and
  `/demo/payment-incident` are intentionally outside OpenAPI.
- Living documentation intentionally avoids a fixed total test count.

## Prohibited claims

This branch does not prove or perform:

- real Oceanpayment data or production integration;
- a real Feishu test-group callback flow;
- payment, refund, risk release, fund movement or production configuration change;
- a real bank/card-scheme/Oceanpayment chargeback submission;
- measured business impact or production readiness;
- Gate 4 PASS.

## Remaining release gates

1. Final exact-tree full suite, clean-copy reproduction, dependency and secret scans.
2. GitHub Actions green on the exact integration/PR head.
3. Anonymous HTTP 200 for the exact commit README.
4. PR diff review proving no v0.2.1 chargeback/console/security regression.
5. Separate timestamped real Feishu test-group smoke over public HTTPS.

Until all applicable evidence exists, formal Gate 4 remains **NOT RUN / NOT PASSED**.
