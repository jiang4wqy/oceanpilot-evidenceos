# OceanPilot Payment Incident Showcase Implementation Plan

> Implement the approved August 16 showcase one vertical slice at a time. Every Python
> behavior follows red-green TDD at the public seams approved in the design specification.

**Goal:** Deliver one truthful Feishu payment-incident flow plus a read-only case cockpit
and clearly labelled merchant-success concept shell.

**Approved specification:**
`docs/superpowers/specs/2026-08-11-payment-incident-showcase-design.md` at commit `b2923e0`.

**Tech stack:** Python 3.12, FastAPI, Pydantic, standard-library SQLite and HTTPS,
pytest, Ruff, static HTML/CSS/JavaScript.

## Global Constraints

- Preserve the current dependency direction and existing diagnosis/evidence semantics.
- Preserve and review the four existing untracked application/orchestrator files; do not
  discard or overwrite them wholesale.
- Keep core and Feishu databases separate.
- Use only synthetic `PAYMENT_INCIDENT` cases and execute no payment-side action.
- Credentials come from environment variables and never enter repository files, fixtures,
  logs, exceptions, SQLite, or UI output.
- Do not begin concept-module backends. Concept previews are static product descriptions.
- Test only the five public seams approved in the specification.
- Work in vertical slices: one failing public behavior, minimal production change, green
  focused test, then the next behavior.
- Run every test with a unique existing `--basetemp` parent under the Windows temp folder.
- Each task has a narrow commit. Do not mix repository-wide formatting with functional work.

## Task 1 — Align Feishu Application and Persistence Contracts

**Files:**

- Modify: `src/oceanpilot/application/feishu_models.py`
- Modify: `src/oceanpilot/application/feishu_ports.py`
- Modify: `src/oceanpilot/application/feishu_orchestrator.py`
- Modify: `src/oceanpilot/adapters/feishu/store.py`
- Modify: `tests/feishu/test_orchestrator.py`
- Modify: `tests/feishu/test_store.py`

**Public behaviors:**

- a chat/thread binding port can be implemented by the existing Feishu SQLite adapter;
- confirmation carries server request/trace identifiers into persisted approval audit;
- the actor identifier is stored as a stable hash, not raw Feishu identity;
- confirmation uniqueness covers the semantic `(case_id, diagnosis_id, action_kind)` even
  when Feishu generates a new callback event;
- existing databases migrate additively without dropping callback rows.

**TDD sequence:**

1. Add one failing real-file Store test for request/trace hydration and semantic duplicate
   confirmation.
2. Add the smallest additive schema and hydrator changes to pass.
3. Add one failing application seam test proving confirmation context reaches the port.
4. Align the port/adapter names and mapping without moving SQL into application code.
5. Run all Feishu Store/orchestrator tests, import-boundary tests, Ruff, and compileall.

**Commit:** `feat: align Feishu orchestration persistence`

## Task 2 — Add Optional Feishu Runtime and Signed Callback Boundary

**Files:**

- Modify: `src/oceanpilot/config.py`
- Modify: `src/oceanpilot/main.py`
- Modify: `src/oceanpilot/api/dependencies.py`
- Modify: `src/oceanpilot/api/errors.py`
- Create: `src/oceanpilot/api/feishu_schemas.py`
- Create: `src/oceanpilot/api/feishu.py`
- Create: `tests/feishu/fixtures/url_verification.json`
- Create: `tests/feishu/fixtures/message_received.json`
- Create: `tests/feishu/fixtures/evidence_action.json`
- Create: `tests/feishu/fixtures/confirmation_action.json`
- Create/Modify: `tests/feishu/conftest.py`, `tests/feishu/test_routes.py`
- Modify: `tests/api/test_lifespan_openapi.py`

**Public behaviors:**

- core app startup and health work with no or partial Feishu configuration;
- both Feishu routes return fixed safe 503 when runtime is unavailable;
- URL verification succeeds only after size, time, signature, JSON, and token validation;
- raw fixture bytes reach the verifier unchanged;
- invalid/expired/oversized callbacks never enter Store or orchestrator;
- the router remains present in OpenAPI with safe problem schemas.

**TDD sequence:**

1. RED: unavailable runtime does not break core lifespan and routes return safe 503.
2. GREEN: add secret-safe optional settings and lifespan-only runtime initialization.
3. RED: signed URL verification and exact raw-byte tests.
4. GREEN: implement bounded streaming and thin route/security mapping.
5. RED/GREEN one validation and error mapping at a time.
6. Run route, existing API, OpenAPI, Ruff, and compileall checks.

**Commit:** `feat: expose verified Feishu callbacks`

## Task 3 — Complete Message Intake and Question Card Slice

**Files:**

- Modify: `src/oceanpilot/application/feishu_models.py`
- Modify: `src/oceanpilot/application/feishu_orchestrator.py`
- Modify: `src/oceanpilot/adapters/feishu/store.py`
- Modify: `src/oceanpilot/adapters/feishu/cards.py`
- Modify: `src/oceanpilot/api/feishu.py`, `feishu_schemas.py`
- Modify/Create: `tests/feishu/test_message_flow.py`

**Public behaviors:**

- one signed user message in the configured demo group creates and binds one case;
- binding identity includes tenant, chat, and root/thread context;
- a repeated event or a second delivery in the same thread reuses the case;
- a different thread in the same group can create another case;
- robot messages are ignored;
- the first role-labelled readiness question is sent with a stable idempotency key.

**TDD sequence:**

1. RED/GREEN first signed message through HTTP to one outbound card.
2. RED/GREEN duplicate event replay.
3. RED/GREEN same-thread and different-thread binding.
4. RED/GREEN robot suppression and safe summaries.
5. Run message-flow, core service, Ruff, compileall, and diff checks.

**Commit:** `feat: intake Feishu payment incidents`

## Task 4 — Complete Evidence Actions and Automatic Diagnosis

**Files:**

- Modify: `src/oceanpilot/application/feishu_models.py`
- Modify: `src/oceanpilot/application/feishu_orchestrator.py`
- Modify: `src/oceanpilot/adapters/feishu/cards.py`
- Modify: `src/oceanpilot/api/feishu.py`, `feishu_schemas.py`
- Create/Modify: `tests/feishu/test_evidence_card_flow.py`

**Public behaviors:**

- action cards expose only server-selected evidence code plus availability/value fields;
- the server fixes origin, evidence identity, collection metadata, and synthetic state;
- each accepted answer advances the real readiness view;
- no diagnosis runs before readiness;
- the final required evidence triggers the real persisted diagnosis and diagnosis card;
- duplicate callback and command identities do not duplicate evidence or diagnosis.

**TDD sequence:**

1. RED/GREEN one valid evidence action through the HTTP seam.
2. RED/GREEN closed caller-controlled field rejection.
3. RED/GREEN next-question progression.
4. RED/GREEN final evidence to real diagnosis card.
5. RED/GREEN replay and conflict behavior.
6. Run focused and existing synthetic E2E gates.

**Commit:** `feat: diagnose Feishu evidence flows`

## Task 5 — Complete Safe Human Confirmation

**Files:**

- Modify: `src/oceanpilot/application/feishu_models.py`
- Modify: `src/oceanpilot/application/feishu_orchestrator.py`
- Modify: `src/oceanpilot/adapters/feishu/cards.py`, `store.py`
- Modify: `src/oceanpilot/api/feishu.py`, `feishu_schemas.py`
- Create/Modify: `tests/feishu/test_confirmation_action.py`

**Public behaviors:**

- only the current synthetic human-review diagnosis can be confirmed;
- confirmation writes one correlated approval audit and leaves case state unchanged;
- stale cards return a safe refresh message without audit;
- repeated callback IDs and new-event repeated clicks produce one approval;
- no payment, refund, release, configuration, or work-order executor is called.

**Commit:** `feat: record Feishu review confirmations`

## Task 6 — Add the Read-Only Cockpit and Concept Shell

**Files:**

- Create: `src/oceanpilot/api/demo.py`
- Create: `src/oceanpilot/application/demo_query.py` if an aggregation seam is required
- Modify: only narrow read ports/hydrators required for safe audit/confirmation reads
- Create: `src/oceanpilot/static/demo/index.html`
- Create: `src/oceanpilot/static/demo/case.html`
- Create: `src/oceanpilot/static/demo/styles.css`
- Create: `src/oceanpilot/static/demo/app.js`
- Modify: `src/oceanpilot/main.py`
- Create: `tests/demo/test_demo_pages.py`

**Public behaviors:**

- `/demo` distinguishes live synthetic payment incidents from three concept previews;
- `/demo/cases/{case_id}` displays the persisted case, evidence, diagnosis, responsibility,
  review reasons, safe audit timeline, and confirmation state;
- the UI has no mutation controls and concept previews cause no Store writes;
- no credential or raw Feishu identity is serialized.

**Implementation rule:** Prefer existing case responses and the smallest safe read query.
Do not build list/search/analytics unless required by the approved pages.

**Commit:** `feat: add payment incident demo cockpit`

## Task 7 — Security, Fallbacks, Documentation, and Release Gate

**Files:**

- Create/Modify: signed fixture runner under `examples/`
- Create/Modify: narrow security sentinels under `tests/security/`
- Modify: README, architecture, demo runbook, and competition factual status
- Create: PR4 checkpoint/review report

**Public behaviors and gates:**

- signed fixture flow independently demonstrates callback orchestration;
- existing PowerShell four-rule demo remains repeatable;
- credentials and sensitive callback values are absent from HTTP, logs, audit, SQLite bytes,
  snapshots, and static assets;
- full pytest, Ruff, compileall, formatting baseline audit, and diff check pass;
- a clean temporary worktree reproduces the demo;
- one real Feishu test-group flow succeeds when public HTTPS callback configuration is
  available;
- capability statements are updated to actual verified behavior only.

**Commit:** `chore: prepare payment incident showcase`

## Final Acceptance Commands

```powershell
$env:PYTHONPATH = 'src'
py -3.12 -B -m pytest -p no:cacheprovider -q --basetemp `
  'C:/Users/lenovo/AppData/Local/Temp/oceanpilot-showcase-final'
C:/Users/lenovo/Documents/Codex/2026-08-04/zhao/work/python-tools-user/bin/ruff.exe `
  check src tests
py -3.12 -B -m compileall -q src tests
git diff --check
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./examples/demo.ps1
```

The real Feishu smoke test and anonymous GitHub verification are recorded separately because
they depend on external network and test-tenant state.
