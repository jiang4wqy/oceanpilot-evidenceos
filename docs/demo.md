# OceanPilot Demo Runbook

Two synthetic demos, both local and offline. No Oceanpayment or Feishu
production data is touched, and no payment, refund, risk-release, configuration,
or ticketing action is ever executed.

## Prerequisites

- Python 3.12
- A virtual environment with the project installed:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"      # Windows: .\.venv\Scripts\python.exe
```

## A. HTTP case → evidence → diagnosis (main chain)

Start the local service (binds `127.0.0.1` only):

```bash
export OCEANPILOT_DB_PATH=work/oceanpilot.db
.venv/bin/python -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8000
```

On Windows, `examples/demo.ps1` runs the whole chain against a running service
and exits non-zero on failure:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\examples\demo.ps1
```

The script verifies, in order: `GET /health`; create a synthetic
`PAYMENT_INCIDENT` case; append evidence; read the case; and call
`POST /api/v1/cases/{case_id}/diagnose`, which now returns a real strict
`DiagnosisResponse` (`201` first time, `200` on identity replay) — no longer the
old `501`.

The same flow through the public application/HTTP seams is exercised
deterministically by the offline suites in `tests/e2e/`.

## B. Feishu synthetic collaboration flow

The end-to-end Feishu chain (message → create/bind case → role-scoped need-info
card → structured evidence answers → readiness → real diagnosis card → human
confirmation → approval audit) is driven at the signed callback seam by
`tests/feishu/test_feishu_routes.py::test_full_message_to_confirmation_flow`.

Run just the Feishu and security suites:

```bash
.venv/bin/python -m pytest tests/feishu tests/security -q
```

Because Feishu-submitted evidence is fixed to `MERCHANT / USER_REPORTED /
synthetic=true` (low source quality), every Feishu-driven diagnosis routes to
human review, so the diagnosis card always carries a single `confirm_review`
button. Confirmation records one synthetic approval audit and does **not** change
case state; a re-clicked button (a new callback id for the same diagnosis) is
rejected with a fixed `409`.

To drive the flow from a real Feishu test group instead of fixtures, configure
the console and credentials per [feishu-setup.md](feishu-setup.md) and expose a
public HTTPS endpoint.

## Full local gate

```bash
.venv/bin/python -m pytest -p no:cacheprovider -q
ruff check src tests
ruff format --check src tests
.venv/bin/python -m compileall -q src tests
git diff --check
```
