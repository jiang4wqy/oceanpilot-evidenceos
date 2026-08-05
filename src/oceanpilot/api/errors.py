import re
from collections.abc import Awaitable, Callable, Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr
from starlette.exceptions import HTTPException as StarletteHTTPException

from oceanpilot.application.errors import (
    CaseNotFound,
    CaseNotReady,
    CaseTypeNotEnabled,
    ConcurrentCaseWrite,
    DatabaseUnavailable,
    DiagnosisInputStale,
    EvidenceConflict,
    PersistenceInvariantViolation,
)
from oceanpilot.domain.errors import InvalidTransition, SensitiveDataRejected
from oceanpilot.domain.models import Revision, UUID4Str

_SAFE_ALLOW = re.compile(r"[A-Z]+(?:, [A-Z]+)*")
_KNOWN_LOCATION_SEGMENTS = frozenset({
    "body",
    "path",
    "query",
    "case_id",
    "case_type",
    "summary",
    "merchant_ref",
    "synthetic",
    "evidence_id",
    "evidence_code",
    "availability",
    "typed_value",
    "observed_at",
    "source_ref",
})
_SAFE_VALIDATION_REASONS = {
    "extra_forbidden": "extra_field",
    "missing": "required_field",
    "uuid_parsing": "invalid_uuid",
    "uuid_version": "invalid_uuid",
    "enum": "invalid_choice",
    "bool_type": "invalid_type",
    "string_type": "invalid_type",
}


class SafeValidationError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: StrictStr
    reason: StrictStr


class ProblemDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    type: StrictStr
    title: StrictStr
    status: StrictInt
    detail: StrictStr
    instance: StrictStr
    code: StrictStr
    request_id: UUID4Str
    trace_id: UUID4Str
    case_id: UUID4Str | None = None
    missing_fields: tuple[StrictStr, ...] | None = None
    current_revision: Revision | None = None
    errors: tuple[SafeValidationError, ...] | None = None


def _problem(
    request: Request,
    status: int,
    code: str,
    title: str,
    detail: str,
    *,
    extensions: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    context = request.state.request_context
    content: dict[str, object] = {
        "type": f"urn:oceanpilot:problem:{code.lower().replace('_', '-')}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": f"urn:oceanpilot:request:{context.request_id}",
        "code": code,
        "request_id": context.request_id,
        "trace_id": context.trace_id,
    }
    if extensions is not None:
        content.update(extensions)
    body = ProblemDetails.model_validate(content).model_dump(mode="json", exclude_none=True)
    response_headers = {"X-Trace-ID": context.trace_id}
    if headers is not None:
        response_headers.update(headers)
    return JSONResponse(
        status_code=status,
        content=body,
        headers=response_headers,
        media_type="application/problem+json",
    )


def _fixed_handler(
    status: int,
    code: str,
    title: str,
    detail: str,
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        del exc
        return _problem(request, status, code, title, detail)

    return handler


def _safe_error_location(error: Mapping[str, object]) -> str:
    if error.get("type") == "extra_forbidden":
        return "body.<extra>"
    parts: list[str] = []
    location = error.get("loc")
    if not isinstance(location, (tuple, list)):
        return "<field>"
    for part in location:
        if isinstance(part, int):
            parts.append(str(part))
        elif part in _KNOWN_LOCATION_SEGMENTS:
            parts.append(part)
        else:
            parts.append("<field>")
    return ".".join(parts) or "<field>"


async def _validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    safe_errors = tuple(
        SafeValidationError(
            field=_safe_error_location(error),
            reason=_SAFE_VALIDATION_REASONS.get(error.get("type"), "invalid_value"),
        )
        for error in exc.errors()
    )
    return _problem(
        request,
        422,
        "INVALID_REQUEST",
        "Invalid request",
        "request validation failed",
        extensions={"errors": safe_errors},
    )


async def _case_not_ready_handler(request: Request, exc: CaseNotReady) -> JSONResponse:
    return _problem(
        request,
        409,
        "CASE_NOT_READY",
        "Case is not ready",
        "case is not ready for diagnosis",
        extensions={
            "case_id": exc.case_id,
            "missing_fields": exc.missing_fields,
            "current_revision": exc.current_revision,
        },
    )


async def _http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    headers = None
    if exc.status_code == 405 and exc.headers is not None:
        allow = exc.headers.get("Allow")
        if allow is not None and _SAFE_ALLOW.fullmatch(allow) is not None:
            headers = {"Allow": allow}
    return _problem(
        request,
        exc.status_code,
        "HTTP_ERROR",
        "HTTP request failed",
        "request could not be completed",
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        CaseNotFound,
        _fixed_handler(404, "CASE_NOT_FOUND", "Case not found", "case was not found"),
    )
    app.add_exception_handler(CaseNotReady, _case_not_ready_handler)
    app.add_exception_handler(
        CaseTypeNotEnabled,
        _fixed_handler(
            409,
            "CASE_TYPE_NOT_ENABLED",
            "Case type not enabled",
            "case type is not enabled",
        ),
    )
    app.add_exception_handler(
        EvidenceConflict,
        _fixed_handler(
            409,
            "EVIDENCE_CONFLICT",
            "Evidence conflict",
            "evidence id conflicts with existing content",
        ),
    )
    app.add_exception_handler(
        ConcurrentCaseWrite,
        _fixed_handler(
            409,
            "CONCURRENT_CASE_WRITE",
            "Concurrent case write",
            "case changed during write",
        ),
    )
    app.add_exception_handler(
        DiagnosisInputStale,
        _fixed_handler(
            409,
            "DIAGNOSIS_INPUT_STALE",
            "Diagnosis input stale",
            "diagnosis input is stale",
        ),
    )
    app.add_exception_handler(
        InvalidTransition,
        _fixed_handler(
            409,
            "INVALID_TRANSITION",
            "Invalid state transition",
            "case command is not allowed in the current state",
        ),
    )
    app.add_exception_handler(
        SensitiveDataRejected,
        _fixed_handler(
            422,
            "SENSITIVE_DATA_REJECTED",
            "Sensitive data rejected",
            "request contains disallowed sensitive data",
        ),
    )
    app.add_exception_handler(
        RequestValidationError,
        _validation_error_handler,
    )
    app.add_exception_handler(
        ValueError,
        _fixed_handler(
            422,
            "INVALID_REQUEST",
            "Invalid request",
            "request validation failed",
        ),
    )
    app.add_exception_handler(
        DatabaseUnavailable,
        _fixed_handler(
            503,
            "DATABASE_UNAVAILABLE",
            "Database unavailable",
            "database is unavailable",
        ),
    )
    app.add_exception_handler(
        PersistenceInvariantViolation,
        _fixed_handler(500, "INTERNAL_ERROR", "Internal error", "internal server error"),
    )
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(
        Exception,
        _fixed_handler(500, "INTERNAL_ERROR", "Internal error", "internal server error"),
    )
