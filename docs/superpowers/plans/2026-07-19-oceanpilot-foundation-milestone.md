# OceanPilot Foundation Milestone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a GitHub-ready FastAPI foundation where health, case creation/read, and evidence append work end to end, while diagnosis is an explicit safe `501 FEATURE_DEFERRED` endpoint.

**Architecture:** Add a thin `CaseService` over the already committed domain policies and SQLite atomic case/evidence Store. Add a small FastAPI composition layer with lifespan-owned schema initialization, fixed safe errors, strict request DTOs, and exactly five public paths. Preserve the approved diagnosis boundary by exposing its route without executing rules or storing fake results.

**Tech Stack:** Python 3.12, FastAPI 0.139.2, Pydantic 2.13.4, Uvicorn 0.51.0, standard-library `sqlite3`, pytest 9.1.1, Ruff 0.15.22, PowerShell.

## Global Constraints

- Approved specification: `docs/superpowers/specs/2026-07-19-oceanpilot-foundation-milestone-design.md` at commit `f485d03`.
- Start from the clean shared checkout at `C:\Users\lenovo\Documents\飞书比赛`; the user explicitly approved continuing on its current `master` branch.
- Freeze Python to `>=3.12,<3.13`; add no dependencies and do not modify `pyproject.toml`.
- Do not modify domain rules, state machine, persistence schema, existing repository tests, or the original competition specification/plan.
- Reuse `SqliteCaseStoreFactory`, `create_case_atomic()`, `get_case_view()`, `load_case_snapshot()`, and `append_evidence_atomic()`; no SQL in application/API modules.
- Only synthetic `PAYMENT_INCIDENT` cases are enabled. `synthetic` must be exact boolean `true`.
- Diagnosis must never execute rules, write a snapshot, or return a fabricated result. It always returns safe HTTP `501` with code `FEATURE_DEFERRED`.
- Error bodies contain only fixed safe fields `status`, `code`, and `detail`; never copy validation `input`, exception text, SQL, or sensitive caller values.
- API paths are exactly `/health`, `/api/v1/cases`, `/api/v1/cases/{case_id}`, `/api/v1/cases/{case_id}/evidence`, and `/api/v1/cases/{case_id}/diagnose`.
- Use TDD for every Python behavior. Tests use real files under pytest `tmp_path`; never ordinary `:memory:` SQLite.
- The machine's default `pytest-of-lenovo` directory has a verified ACL failure. Use a unique repository-local `--basetemp .superpowers/sdd/pytest-foundation-<task>` for every pytest command.
- Each task stages only its exact file list, runs `git diff --cached --check`, verifies the cached names, commits, and leaves no tracked/unignored working-tree changes.

## File Map

| File | Responsibility |
|---|---|
| `src/oceanpilot/application/case_service.py` | Create/read/evidence command orchestration only |
| `src/oceanpilot/config.py` | Frozen local settings and environment loading |
| `src/oceanpilot/api/errors.py` | Fixed safe problem response and exception handlers |
| `src/oceanpilot/api/dependencies.py` | Resolve Store factory and CaseService from `app.state` |
| `src/oceanpilot/api/health.py` | Read-only health route |
| `src/oceanpilot/api/schemas.py` | Strict request DTOs and command mapping |
| `src/oceanpilot/api/cases.py` | Four case routes, including deferred diagnosis |
| `src/oceanpilot/main.py` | `create_app()` and lifespan composition root |
| `tests/foundation/**` | Reduced-milestone unit and API contract tests |
| `README.md` | Honest public overview and quick start |
| `docs/architecture.md` | Component/data-flow boundaries |
| `docs/roadmap/incomplete-work.md` | Detailed deferred-work register |
| `examples/demo.ps1` | Local health/case/evidence/deferred-diagnosis demo |

---

### Task 1: Add the Minimal CaseService

**Files:**
- Create: `src/oceanpilot/application/case_service.py`
- Create: `tests/foundation/test_case_service.py`

**Interfaces:**
- Consumes: `CreateCaseCommand`, `AddEvidenceCommand`, `CaseStoreFactory`, existing evidence policies/state machine, and Store atomic methods.
- Produces: `CaseService(store_factory, *, clock, uuid_factory)`, `create_case(command) -> CaseView`, `get_case(case_id) -> CaseView`, and `add_evidence(command) -> AppendEvidenceResult`.

- [ ] **Step 1: Write deterministic failing service tests**

Create `tests/foundation/test_case_service.py` with a small fake session/factory and these exact behaviors:

```python
def test_create_case_builds_revision_one_and_case_created_audit():
    service, fake, ids = make_service()
    view = service.create_case(create_command())
    assert view.case.case_revision == 1
    assert view.case.evidence_revision == 0
    assert fake.created_audit.event_type is AuditEventType.CASE_CREATED
    assert ids.consumed == 2  # case ID, event ID


def test_get_case_raises_stable_not_found():
    service, _, _ = make_service(case_view=None)
    with pytest.raises(CaseNotFound):
        service.get_case(CASE_ID)


def test_create_rejects_disabled_case_type_without_store_call():
    service, fake, _ = make_service()
    with pytest.raises(CaseTypeNotEnabled):
        service.create_case(create_command(case_type=CaseType.ONBOARDING_RECOMMENDATION))
    assert fake.calls == []


def test_add_evidence_recomputes_readiness_and_emits_exact_audits():
    service, fake, _ = make_service(case_view=empty_case_view())
    result = service.add_evidence(add_environment_command())
    assert result.outcome is WriteOutcome.CREATED
    assert fake.appended_readiness == assess_readiness(
        build_active_evidence_view((fake.appended_evidence,))
    )
    assert {event.event_type for event in fake.appended_audits} == {
        AuditEventType.EVIDENCE_ADDED,
    }


def test_existing_evidence_uses_store_replay_without_allocating_audit_ids():
    service, fake, ids = make_service(case_view=case_view_with_environment())
    result = service.add_evidence(add_environment_command())
    assert result.outcome is WriteOutcome.REPLAY
    assert fake.appended_audits == ()
    assert ids.consumed == 0


def test_foundation_service_does_not_retry_concurrent_write():
    service, fake, _ = make_service(
        case_view=empty_case_view(), append_error=ConcurrentCaseWrite()
    )
    with pytest.raises(ConcurrentCaseWrite):
        service.add_evidence(add_environment_command())
    assert fake.load_count == 1
```

The fake must record every call and return caller-independent model objects. Use fixed aware UTC timestamps and canonical UUIDv4 strings. Do not import SQLite into this test.

- [ ] **Step 2: Run RED and verify the missing module is the cause**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/foundation/test_case_service.py -q --basetemp .superpowers/sdd/pytest-foundation-task1-red
```

Expected: collection fails only with `ModuleNotFoundError: No module named 'oceanpilot.application.case_service'`.

- [ ] **Step 3: Implement the minimal service**

Create `src/oceanpilot/application/case_service.py` with these fixed helpers and flows:

```python
from collections.abc import Callable, Sequence
from datetime import datetime

from oceanpilot.application.commands import AddEvidenceCommand, CreateCaseCommand
from oceanpilot.application.errors import CaseNotFound, CaseTypeNotEnabled
from oceanpilot.application.ports import CaseStoreFactory
from oceanpilot.domain.enums import (
    AuditActorType,
    AuditEventType,
    CaseStatus,
    CaseType,
    SourceType,
)
from oceanpilot.domain.evidence_policy import (
    assess_readiness,
    build_active_evidence_view,
    create_evidence_item,
)
from oceanpilot.domain.models import (
    AppendEvidenceResult,
    AuditEvent,
    CaseView,
    MerchantSuccessCase,
)
from oceanpilot.domain.security import assert_no_sensitive_data
from oceanpilot.domain.state_machine import status_after_creation, status_after_evidence

CASE_SCHEMA_VERSION = "1"
AUDIT_EVENT_VERSION = "1"


class CaseService:
    def __init__(
        self,
        store_factory: CaseStoreFactory,
        *,
        clock: Callable[[], datetime],
        uuid_factory: Callable[[], str],
    ) -> None:
        self._store_factory = store_factory
        self._clock = clock
        self._uuid_factory = uuid_factory

    def _audit_events(
        self,
        *,
        event_types: Sequence[AuditEventType],
        command: AddEvidenceCommand,
        from_status: CaseStatus,
        to_status: CaseStatus,
        case_revision: int,
        evidence_revision: int,
        occurred_at: datetime,
    ) -> tuple[AuditEvent, ...]:
        actor = (
            AuditActorType.SYNTHETIC_ADAPTER
            if command.origin.source_type is SourceType.SYNTHETIC_ADAPTER
            else AuditActorType.MERCHANT
        )
        return tuple(
            AuditEvent(
                event_id=self._uuid_factory(),
                event_type=event_type,
                event_version=AUDIT_EVENT_VERSION,
                case_id=command.case_id,
                request_id=command.request_id,
                trace_id=command.trace_id,
                actor_type=actor,
                action="add_evidence",
                from_status=from_status,
                to_status=to_status,
                case_revision=case_revision,
                evidence_revision=evidence_revision,
                occurred_at=occurred_at,
                result="CREATED",
                reason_code=None,
                sanitized_metadata={"event_type": event_type.value},
                synthetic=True,
            )
            for event_type in event_types
        )
```

Implement `create_case()` in this order: `assert_no_sensitive_data(command)`; require `PAYMENT_INCIDENT`; compute empty readiness and status; allocate `now`, case ID, then audit ID; construct `MerchantSuccessCase` with revisions `1/0`, equal timestamps, no pointer, and schema version `1`; construct exactly one `CASE_CREATED` merchant audit with command request/trace IDs; open one Store session and call `create_case_atomic()`.

Implement `get_case()` with one Store session and `get_case_view()`; `None` raises `CaseNotFound()`.

Implement `add_evidence()` in this order: scan command; open one session; load one snapshot or raise `CaseNotFound`; create the canonical `EvidenceItem` using one `now`; if the evidence ID already exists, call `append_evidence_atomic()` with current revisions/readiness/status and `audit_events=()` so the Store decides replay/conflict; otherwise append in memory, recompute readiness and `status_after_evidence`, build event types `EVIDENCE_ADDED`, optional `DIAGNOSIS_SUPERSEDED` when reopening, and optional `STATE_TRANSITIONED` when status changes; then call `append_evidence_atomic()` once with post-state audits. Do not catch `ConcurrentCaseWrite`.

- [ ] **Step 4: Run GREEN and focused static checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/foundation/test_case_service.py -q --basetemp .superpowers/sdd/pytest-foundation-task1-green
.\.venv\Scripts\python.exe -m ruff check src/oceanpilot/application/case_service.py tests/foundation/test_case_service.py
.\.venv\Scripts\python.exe -m compileall -q src/oceanpilot/application/case_service.py tests/foundation/test_case_service.py
```

Expected: all commands exit `0`; tests prove one session and one CAS attempt per command.

- [ ] **Step 5: Commit exact Task 1 scope**

```powershell
git add -- src/oceanpilot/application/case_service.py tests/foundation/test_case_service.py
git diff --cached --check
git diff --cached --name-status
git commit -m "feat: add foundation case service"
git status --short
```

Expected cached paths: exactly the two files above; post-commit tracked status is clean.

---

### Task 2: Add FastAPI Lifespan, Health, Dependencies, and Safe Errors

**Files:**
- Create: `src/oceanpilot/config.py`
- Create: `src/oceanpilot/api/__init__.py`
- Create: `src/oceanpilot/api/errors.py`
- Create: `src/oceanpilot/api/dependencies.py`
- Create: `src/oceanpilot/api/health.py`
- Create: `src/oceanpilot/main.py`
- Create: `tests/foundation/test_app_foundation.py`

**Interfaces:**
- Consumes: Task 1 `CaseService` and existing SQLite factory/schema initializer.
- Produces: `Settings`, `ProblemResponse`, `FeatureDeferred`, `get_store_factory()`, `get_case_service()`, `create_app()`, and `GET /health`.

- [ ] **Step 1: Write failing lifespan/health/error tests**

Create `tests/foundation/test_app_foundation.py` with these tests:

```python
def test_lifespan_initializes_real_file_and_health_is_ok(tmp_path):
    db_path = tmp_path / "foundation.db"
    app = create_app(Settings(db_path=db_path))
    assert not db_path.exists()
    with TestClient(app) as client:
        assert db_path.is_file()
        assert client.get("/health").json() == {"status": "ok"}


def test_unknown_path_uses_fixed_safe_error(tmp_path):
    with TestClient(create_app(Settings(db_path=tmp_path / "foundation.db"))) as client:
        response = client.get("/unknown")
    assert response.status_code == 404
    assert response.json() == {
        "status": 404,
        "code": "HTTP_ERROR",
        "detail": "request could not be completed",
    }


def test_unexpected_exception_does_not_echo_sentinel(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "foundation.db"))
    app.get("/boom")(lambda: (_ for _ in ()).throw(RuntimeError("SECRET-SENTINEL")))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    assert "SECRET-SENTINEL" not in response.text
    assert response.json()["code"] == "INTERNAL_ERROR"
```

Also assert `POST /health` returns the fixed safe 405 body. Do not test routes from Task 3 yet.

- [ ] **Step 2: Run RED and verify app modules are absent**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/foundation/test_app_foundation.py -q --basetemp .superpowers/sdd/pytest-foundation-task2-red
```

Expected: collection fails for missing `oceanpilot.config` or `oceanpilot.main`.

- [ ] **Step 3: Implement settings and composition root**

Create `src/oceanpilot/config.py`:

```python
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    db_path: Path
    host: str = "127.0.0.1"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(db_path=Path(os.getenv("OCEANPILOT_DB_PATH", "work/oceanpilot.db")))
```

Create `src/oceanpilot/api/dependencies.py` with `get_store_factory(request)` and `get_case_service(request)` returning the exact objects stored on `request.app.state`.

Create `src/oceanpilot/api/health.py` with a synchronous `/health` route that opens one Store session, calls `healthcheck()`, closes it, and returns `{"status": "ok"}`.

Create `src/oceanpilot/main.py` so `create_app(settings: Settings | None = None) -> FastAPI`:

1. resolves settings without opening SQLite;
2. constructs `store_factory = SqliteCaseStoreFactory(resolved.db_path)` and `CaseService(store_factory, clock=lambda: datetime.now(UTC), uuid_factory=lambda: str(uuid4()))`;
3. assigns settings/factory/service to `app.state` immediately;
4. uses only an `asynccontextmanager` lifespan to call `initialize_schema()`, open a session, call `healthcheck()`, close it, then yield;
5. registers safe handlers and the health router;
6. contains no `@on_event`, import-time connection, or global app singleton.

- [ ] **Step 4: Implement fixed safe errors**

Create `src/oceanpilot/api/errors.py`:

```python
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr


class ProblemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    status: StrictInt
    code: StrictStr
    detail: StrictStr


class FeatureDeferred(Exception):
    pass
```

Add `register_exception_handlers(app)` with fixed mappings:

```text
CaseNotFound -> 404 CASE_NOT_FOUND / "case was not found"
CaseTypeNotEnabled -> 409 CASE_TYPE_NOT_ENABLED / "case type is not enabled"
EvidenceConflict -> 409 EVIDENCE_CONFLICT / "evidence id conflicts with existing content"
ConcurrentCaseWrite -> 409 CONCURRENT_CASE_WRITE / "case changed during write"
SensitiveDataRejected -> 422 SENSITIVE_DATA_REJECTED / "request contains disallowed sensitive data"
RequestValidationError or ValueError -> 422 INVALID_REQUEST / "request validation failed"
FeatureDeferred -> 501 FEATURE_DEFERRED / "diagnosis is deferred in the foundation milestone"
DatabaseUnavailable -> 503 DATABASE_UNAVAILABLE / "database is unavailable"
Starlette HTTPException -> original status, HTTP_ERROR / "request could not be completed"
all remaining Exception -> 500 INTERNAL_ERROR / "internal server error"
```

Every handler returns only `ProblemResponse(...).model_dump()` via `JSONResponse`. All details are fixed phrases; never use `str(exc)`, `exc.errors()`, `exc.__dict__`, or request body values.

- [ ] **Step 5: Run GREEN and Task 2 verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/foundation/test_app_foundation.py -q --basetemp .superpowers/sdd/pytest-foundation-task2-green
.\.venv\Scripts\python.exe -m ruff check src/oceanpilot/config.py src/oceanpilot/api src/oceanpilot/main.py tests/foundation/test_app_foundation.py
.\.venv\Scripts\python.exe -m compileall -q src/oceanpilot tests/foundation/test_app_foundation.py
rg -n "@.*on_event|sqlite3|str\(exc\)|exc\.errors|__dict__" src/oceanpilot/api src/oceanpilot/main.py
```

Expected: tests/Ruff/compileall exit `0`; `rg` exits `1` with no output.

- [ ] **Step 6: Commit exact Task 2 scope**

Stage only the six production files and `tests/foundation/test_app_foundation.py`, verify the cached name list, then:

```powershell
git commit -m "feat: add foundation FastAPI lifecycle"
git show --check --oneline HEAD
git status --short
```

---

### Task 3: Expose Case/Evidence Routes and Deferred Diagnosis

**Files:**
- Create: `src/oceanpilot/api/schemas.py`
- Create: `src/oceanpilot/api/cases.py`
- Modify: `src/oceanpilot/main.py`
- Create: `tests/foundation/test_foundation_api.py`

**Interfaces:**
- Consumes: Task 1 service and Task 2 dependencies/errors/composition root.
- Produces: four case routes and an OpenAPI document with exactly five approved paths.

- [ ] **Step 1: Write failing end-to-end API tests**

Create `tests/foundation/test_foundation_api.py` using real `tmp_path` SQLite and `with TestClient(app)`:

```python
def test_case_and_evidence_happy_path(client):
    created = client.post("/api/v1/cases", json={
        "case_type": "PAYMENT_INCIDENT",
        "summary": "Synthetic checkout failure",
        "merchant_ref": "merchant_demo_001",
        "synthetic": True,
    })
    assert created.status_code == 201
    case_id = created.json()["case"]["case_id"]
    evidence = client.post(f"/api/v1/cases/{case_id}/evidence", json={
        "evidence_id": "00000000-0000-4000-8000-000000000011",
        "evidence_code": "context.environment",
        "availability": "AVAILABLE",
        "typed_value": "PROD",
        "observed_at": "2026-07-18T12:00:00+08:00",
        "source_ref": "synthetic:demo",
    })
    assert evidence.status_code == 201
    loaded = client.get(f"/api/v1/cases/{case_id}")
    assert loaded.status_code == 200
    assert loaded.json()["case"]["evidence_revision"] == 1
    assert len(loaded.json()["evidence"]) == 1


def test_evidence_replay_is_200_and_conflict_is_409(client, created_case):
    first = post_environment(client, created_case, "PROD")
    replay = post_environment(client, created_case, "PROD")
    conflict = post_environment(client, created_case, "SANDBOX")
    assert first.status_code == 201
    assert replay.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "EVIDENCE_CONFLICT"


def test_diagnosis_is_explicitly_deferred(client, created_case):
    response = client.post(f"/api/v1/cases/{created_case}/diagnose")
    assert response.status_code == 501
    assert response.json() == {
        "status": 501,
        "code": "FEATURE_DEFERRED",
        "detail": "diagnosis is deferred in the foundation milestone",
    }


def test_unknown_or_sensitive_input_is_not_echoed(client):
    sentinel = "authorization=Bearer-SECRET-SENTINEL"
    response = client.post("/api/v1/cases", json={"unknown": sentinel})
    assert response.status_code == 422
    assert sentinel not in response.text


def test_openapi_has_exact_foundation_paths(app):
    assert set(app.openapi()["paths"]) == {
        "/health",
        "/api/v1/cases",
        "/api/v1/cases/{case_id}",
        "/api/v1/cases/{case_id}/evidence",
        "/api/v1/cases/{case_id}/diagnose",
    }
```

- [ ] **Step 2: Run RED and verify routes are absent**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/foundation/test_foundation_api.py -q --basetemp .superpowers/sdd/pytest-foundation-task3-red
```

Expected: approved case requests return `404`; health continues to pass.

- [ ] **Step 3: Implement strict DTOs**

Create `src/oceanpilot/api/schemas.py` with a shared `FoundationRequest` using `ConfigDict(extra="forbid", hide_input_in_errors=True, allow_inf_nan=False)`.

Define:

```python
class CreateCaseRequest(FoundationRequest):
    case_type: CaseType
    summary: Annotated[StrictStr, Field(min_length=1, max_length=500)]
    merchant_ref: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    synthetic: SyntheticTrue


class EvidenceCreateRequest(FoundationRequest):
    evidence_id: UUID4Str
    evidence_code: EvidenceCode
    availability: EvidenceAvailability
    typed_value: StrictStr | StrictBool | None = None
    observed_at: StrictStr | None = None
    source_ref: Annotated[StrictStr, Field(min_length=1, max_length=128)]
```

`CreateCaseRequest.to_command(request_id: UUID4Str, trace_id: UUID4Str) -> CreateCaseCommand` accepts server-created request/trace UUIDs. `EvidenceCreateRequest.to_command(case_id: UUID4Str, request_id: UUID4Str, trace_id: UUID4Str) -> AddEvidenceCommand` parses `observed_at` only with `datetime.fromisoformat(value.replace("Z", "+00:00"))` and requires timezone; when `evidence_code` is `TRANSACTION_OCCURRED_AT`, it parses the string `typed_value` the same way. It constructs the server-owned origin exactly as `MERCHANT`, `USER_REPORTED`, `synthetic=True`. Any parse failure raises `ValueError` and is mapped to the fixed 422 response.

- [ ] **Step 4: Implement thin routes and register the router**

Create `src/oceanpilot/api/cases.py`:

```python
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Response, status

from oceanpilot.api.dependencies import get_case_service
from oceanpilot.api.errors import FeatureDeferred
from oceanpilot.api.schemas import CreateCaseRequest, EvidenceCreateRequest
from oceanpilot.application.case_service import CaseService
from oceanpilot.domain.enums import WriteOutcome
from oceanpilot.domain.models import CaseView, UUID4Str


router = APIRouter(prefix="/api/v1/cases")


@router.post("", response_model=CaseView, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CreateCaseRequest,
    response: Response,
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseView:
    view = service.create_case(payload.to_command(str(uuid4()), str(uuid4())))
    response.headers["Location"] = f"/api/v1/cases/{view.case.case_id}"
    return view


@router.get("/{case_id}", response_model=CaseView)
def get_case(
    case_id: UUID4Str,
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseView:
    return service.get_case(case_id)


@router.post(
    "/{case_id}/evidence",
    response_model=CaseView,
    status_code=status.HTTP_201_CREATED,
)
def add_evidence(
    case_id: UUID4Str,
    payload: EvidenceCreateRequest,
    response: Response,
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseView:
    result = service.add_evidence(payload.to_command(case_id, str(uuid4()), str(uuid4())))
    response.status_code = (
        status.HTTP_201_CREATED
        if result.outcome is WriteOutcome.CREATED
        else status.HTTP_200_OK
    )
    return result.case_view


@router.post("/{case_id}/diagnose", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def diagnose(case_id: UUID4Str) -> None:
    del case_id
    raise FeatureDeferred()
```

Modify `create_app()` to include this router after the health router.

- [ ] **Step 5: Run GREEN, full API checks, and path audit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/foundation -q --basetemp .superpowers/sdd/pytest-foundation-task3-green
.\.venv\Scripts\python.exe -m ruff check src/oceanpilot tests/foundation
.\.venv\Scripts\python.exe -m compileall -q src/oceanpilot tests/foundation
.\.venv\Scripts\python.exe -c "from oceanpilot.main import create_app; print('\n'.join(sorted(create_app().openapi()['paths'])))"
rg -n "assess_readiness|sqlite3|case_revision\s*[+=]|evaluate\(" src/oceanpilot/api
```

Expected: tests/Ruff/compileall exit `0`; exactly five paths print; `rg` exits `1`.

- [ ] **Step 6: Commit exact Task 3 scope**

Stage only `schemas.py`, `cases.py`, `main.py`, and `test_foundation_api.py`; verify cached scope, then:

```powershell
git commit -m "feat: expose foundation case API"
git show --check --oneline HEAD
git status --short
```

---

### Task 4: Add Public Documentation, Deferred-Work Register, and Demo

**Files:**
- Create: `README.md`
- Create: `docs/architecture.md`
- Create: `docs/roadmap/incomplete-work.md`
- Create: `examples/demo.ps1`

**Interfaces:**
- Consumes: the actual five Task 3 paths and verified behavior.
- Produces: an honest GitHub landing page, architecture explanation, actionable continuation map, and local demonstration.

- [ ] **Step 1: Write the public README**

Create `README.md` with these exact sections: `What OceanPilot Is`, `Current Foundation Scope`, `Architecture`, `Quick Start`, `API Walkthrough`, `What Is Deliberately Deferred`, `Verification`, and `Competition Context`.

The capability table must label health/create/read/evidence as `Available`, diagnosis as `Deferred (HTTP 501)`, and production readiness as `Not claimed`. Quick start uses:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:OCEANPILOT_DB_PATH = "work/oceanpilot.db"
.\.venv\Scripts\python.exe -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8000
```

- [ ] **Step 2: Write architecture and incomplete-work documents**

`docs/architecture.md` must describe HTTP → CaseService → domain → SQLite, identify the existing Task 0–8 foundations, show why diagnosis returns 501, and state that API never owns readiness/SQL/revisions.

`docs/roadmap/incomplete-work.md` must contain one row for each of: diagnosis persistence, Persistence Gate 2, full service orchestration, full API safety contract, three synthetic E2E cases, security/CI, and final release. Every row must contain current assets, missing work, user impact, dependency/task number, priority, expected files, an independently assignable work track, and an executable acceptance command. Do not use unresolved placeholder markers or estimates presented as facts.

- [ ] **Step 3: Write the PowerShell demo**

Create `examples/demo.ps1` with `Set-StrictMode -Version Latest` and `$ErrorActionPreference = "Stop"`. It accepts `$BaseUrl = "http://127.0.0.1:8000"`, then calls health, creates one synthetic case, posts `context.environment=PROD`, reads the case, calls diagnose while accepting HTTP 501, and prints a final summary. It must not start/stop a server, access external services, or contain credentials.

- [ ] **Step 4: Verify documentation against the real app**

```powershell
rg -n "Available|Deferred \(HTTP 501\)|Not claimed" README.md
rg -n "diagnosis persistence|Gate 2|synthetic E2E|security|release" docs/roadmap/incomplete-work.md
rg -n -i "T[B]D|T[O]DO|production ready|fully implemented" README.md docs/architecture.md docs/roadmap/incomplete-work.md
.\.venv\Scripts\python.exe -c "from oceanpilot.main import create_app; assert len(create_app().openapi()['paths']) == 5"
git diff --check
```

Expected: first two searches find all required labels; the prohibited-claim search exits `1`; OpenAPI assertion and diff check exit `0`.

- [ ] **Step 5: Run the complete milestone gate**

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest -q --basetemp .superpowers/sdd/pytest-foundation-final
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
git status --short
```

Expected: Python `3.12.x`; all tests including the original 641 pass; Ruff/format/compileall/diff exit `0`; before staging, only the four Task 4 documentation/demo files are untracked.

- [ ] **Step 6: Commit exact Task 4 scope and stop**

```powershell
git add -- README.md docs/architecture.md docs/roadmap/incomplete-work.md examples/demo.ps1
git diff --cached --check
git diff --cached --name-status
git commit -m "docs: publish foundation milestone"
git show --check --oneline HEAD
git status --short
```

Expected: exact four-file commit, clean tracked/unignored tree. Do not resume original Task 9 without a new user instruction.
