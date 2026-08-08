# OceanPilot Demo Runbook

All demos are local, offline and synthetic. No Oceanpayment or bank production
data is touched, and no real payment, refund, risk-release, configuration,
ticketing or upstream representment action is executed. An explicitly approved
appeal only reaches the in-process mock connector.

## Recommended judge path: Web console

The shortest complete walkthrough is the self-contained console at `/demo`.
It covers prevention → intake → evidence collection with SLA → deterministic
assessment and provenance → bank-rule package → blocked/approved mock appeal →
audit and agent trace, plus the PII/card-number safety guard.

Start with Docker:

```bash
docker build -t oceanpilot-evidenceos .
docker run --rm -p 127.0.0.1:8000:8000 oceanpilot-evidenceos
```

Open `http://127.0.0.1:8000/` (redirects to `/demo`), choose a synthetic
scenario, then use the automatic evidence run. `/docs` exposes the strict API
contract and `/health` checks the local stores.

Docker is optional. To run from a Python 3.12 virtual environment instead:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
export OCEANPILOT_DB_PATH=work/oceanpilot.db
.venv/bin/python -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8000
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
win-likelihood separation only on bundled synthetic fixtures. It is reproducible
engineering evidence, not a real-world accuracy claim:

```bash
.venv/bin/python scripts/eval_chargeback.py
```

## Foundation HTTP case → evidence → diagnosis

`examples/demo.ps1` verifies the older Foundation `PAYMENT_INCIDENT` chain
against a running service. It is retained for engineering regression and is not
the main chargeback competition walkthrough:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\examples\demo.ps1
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

The chargeback `FeishuChannel` parser/renderer is separately tested in
`tests/channels/`; it is **not** wired into the signed event/card-action routes.
Configuring [feishu-setup.md](feishu-setup.md) and a public HTTPS endpoint can
exercise the Foundation callback flow in a test tenant, but does not turn the
chargeback cluster into a real Feishu integration. That wiring and real tenant
smoke remain deferred.

## Full local gate

```bash
.venv/bin/python -m pytest -p no:cacheprovider -q
ruff check src tests
ruff format --check src tests
.venv/bin/python -m compileall -q src tests
git diff --check
```
