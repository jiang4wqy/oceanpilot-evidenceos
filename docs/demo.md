# OceanPilot Demo Runbook

All demos are local, offline and synthetic. No Oceanpayment or bank production
data is touched, and no real payment, refund, risk-release, configuration,
ticketing or upstream representment action is executed. An explicitly approved
appeal only reaches the in-process mock connector.

## Recommended judge path: Web console

The 3–5 minute main walkthrough stays in the merchant-facing AI operations
workspace at `http://127.0.0.1:8002/demo`.

The main path is deliberately one synthetic case:

```text
AI operations hub
  → payment exception
  → original persisted case workspace
  → explicitly choose the Visa 10.4 synthetic template
  → Visa 10.4 synthetic case
  → internal evidence checklist
  → deterministic evidence readiness
  → card-scheme rule validation and package
  → human gate
  → in-process mock connector
  → case-handling audit + this-session mock receipt
```

The payment-exception card only navigates to the existing persisted case
workspace; it does not create a case or claim that transaction settlement and
issuer-notice provenance were validated. A failed 3DS challenge remains a
Foundation `PAYMENT_INCIDENT` support scenario outside this Web mainline. The
Web flow, direct create-case API and Chargeback Feishu seam are synthetic
collaboration interfaces rather than production intake gates.

Start with Docker:

```bash
docker build -t oceanpilot-evidenceos .
docker run --rm -p 127.0.0.1:8000:8000 oceanpilot-evidenceos
```

Open the client and follow this script:

1. On **AI 运营中枢**, identify the product capability map and click the only
   `LIVE DEMO · synthetic` payment-exception node. The other capability cards
   show their real implementation status and do not pretend to contain live
   product data.
2. The payment-exception node opens the original **案件中心** directly; it does
   not create or preselect a case. Open **新建案件**, choose the Visa 10.4
   synthetic template and explicitly click “确认创建案件”.
3. The clear “非本人交易” description enters the persisted Visa 10.4 synthetic
   case at `NEED_EVIDENCE`. The internal checklist starts with the transaction
   receipt and five missing items. Submit one item manually, then use the demo
   shortcut if needed; the shortcut still calls the existing `/evidence` API for
   every remaining item and uses each backend response rather than changing
   readiness in the browser.
4. At 100% evidence readiness, note that Fraud remains routed to human review.
   This score is checklist readiness, never a predicted win probability.
5. Explicitly choose the card network. The diagnosis or assessment reference
   uses the read-only `rule-reference` endpoint to resolve a concrete version;
   if no exact mapping exists, the UI shows no link. Open the matched rule detail and distinguish
   the two visible scopes: the
   six-item **internal case-preparation checklist** drives collection and
   readiness, while the four-item **card-scheme package summary** validates and
   orders the package. AVS/CVV are internal preparation items, not claimed as
   official Visa-mandated evidence.
6. Return to the same case, generate the package and use its rule citation to
   reopen the same `rule_version_id`. First preview the appeal without approval to show
   the deterministic block. Then enter the reviewer actor ID, approve, and send
   only to the in-process mock connector.
7. Finish on **案件处理审计 + 本次 mock 回执**. Package generation, approval and
   the mock receipt are not represented as Chargeback SQLite audit events.

The rule catalog contains nine `UNVERIFIED_SUMMARY` records. Diagnosis and
assessment can resolve an exact version for a read-only citation; only three
`DEMO_MAPPED` records can participate in package matching after generic
evidence collection. They are demo summaries that require production
verification by scheme, region, version and effective date.
`/docs` exposes the strict API contract and `/health` checks the local stores.

Docker is optional. To run from a Python 3.12 virtual environment instead:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
export OCEANPILOT_DB_PATH=work/oceanpilot.db
.venv/bin/python -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8002
```

On Windows, use `.\.venv\Scripts\python.exe` and set `OCEANPILOT_DB_PATH` in
PowerShell. The server examples bind `127.0.0.1` only.

## Cross-platform chargeback transcript

The Python transcript drives the same public HTTP surface in-process, creates
temporary SQLite files and prints the full synthetic chargeback loop. It needs
no running server, API key or network:

```bash
.venv/bin/python examples/chargeback_transcript.py
```

For a narrower direct Supervisor demonstration without HTTP/persistence:

```bash
.venv/bin/python examples/chargeback_demo.py
```

The offline evaluation harness measures intake classification and deterministic
readiness-score separation only on bundled synthetic fixtures. It is reproducible
engineering evidence, not a real-world accuracy or win-rate claim:

```bash
.venv/bin/python scripts/eval_chargeback.py
```

## Foundation support branch: 3DS/callback incident → diagnosis

`examples/demo.ps1` verifies the Foundation `PAYMENT_INCIDENT` chain against a
running service. In the product story this is the correct destination for a
3DS challenge failure or callback anomaly: diagnose the technical incident and
route support/human review, but do not create a chargeback case. It remains an
engineering regression path and is not the main Visa 10.4 walkthrough:

```powershell
# Local venv service on 8002:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\examples\demo.ps1 -BaseUrl http://127.0.0.1:8002
# Docker's default 8000 mapping may omit -BaseUrl.
```

The script checks `GET /health`; creates a synthetic Foundation case; appends
evidence; reads the case; and calls
`POST /api/v1/cases/{case_id}/diagnose`. The first diagnosis returns `201`; the
same identity replays the persisted snapshot with `200`. The deterministic
offline suites in `tests/e2e/` exercise the same public application/HTTP seams.

## Foundation Feishu signed-callback seam

The signed Feishu route test covers the Foundation chain: message → create/bind
`PAYMENT_INCIDENT` case → role-scoped need-info card → structured evidence →
diagnosis card → human confirmation → approval audit.

```bash
.venv/bin/python -m pytest tests/feishu tests/security -q
```

The exact end-to-end test is
`tests/feishu/test_feishu_routes.py::test_full_message_to_confirmation_flow`.
Feishu-submitted evidence is fixed to `MERCHANT / USER_REPORTED /
synthetic=true`; low source quality therefore routes Foundation diagnosis to
human review. Confirmation records a synthetic approval audit, does not change
case state and does not execute a business action.

The same signed event/card-action routes now also drive the chargeback mainline.
A text message beginning with `/chargeback ` opens a synthetic dispute; every
generated chargeback button carries `flow=chargeback`, so Foundation callbacks
remain unchanged. Card actions must match the hashed chat↔case binding created
by the opening message. Focused coverage is in
`tests/feishu/test_feishu_routes.py::test_signed_chargeback_message_and_card_action_use_shared_callback`.
Real tenant smoke remains deferred.

## Full local gate

```bash
.venv/bin/python -m pytest -p no:cacheprovider -q
ruff check src tests
ruff format --check src tests
.venv/bin/python -m compileall -q src tests
git diff --check
```
