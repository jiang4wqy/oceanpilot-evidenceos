from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr
from starlette.exceptions import HTTPException as StarletteHTTPException

from oceanpilot.application.errors import (
    CaseNotFound,
    CaseTypeNotEnabled,
    ConcurrentCaseWrite,
    DatabaseUnavailable,
    EvidenceConflict,
)
from oceanpilot.domain.errors import SensitiveDataRejected


class ProblemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    status: StrictInt
    code: StrictStr
    detail: StrictStr


class FeatureDeferred(Exception):
    pass


def _problem(status: int, code: str, detail: str) -> JSONResponse:
    content = ProblemResponse(status=status, code=code, detail=detail).model_dump()
    return JSONResponse(status_code=status, content=content)


def _fixed_handler(
    status: int,
    code: str,
    detail: str,
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        del request, exc
        return _problem(status, code, detail)

    return handler


async def _http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    del request
    return _problem(exc.status_code, "HTTP_ERROR", "request could not be completed")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        CaseNotFound,
        _fixed_handler(404, "CASE_NOT_FOUND", "case was not found"),
    )
    app.add_exception_handler(
        CaseTypeNotEnabled,
        _fixed_handler(409, "CASE_TYPE_NOT_ENABLED", "case type is not enabled"),
    )
    app.add_exception_handler(
        EvidenceConflict,
        _fixed_handler(
            409,
            "EVIDENCE_CONFLICT",
            "evidence id conflicts with existing content",
        ),
    )
    app.add_exception_handler(
        ConcurrentCaseWrite,
        _fixed_handler(409, "CONCURRENT_CASE_WRITE", "case changed during write"),
    )
    app.add_exception_handler(
        SensitiveDataRejected,
        _fixed_handler(
            422,
            "SENSITIVE_DATA_REJECTED",
            "request contains disallowed sensitive data",
        ),
    )
    app.add_exception_handler(
        RequestValidationError,
        _fixed_handler(422, "INVALID_REQUEST", "request validation failed"),
    )
    app.add_exception_handler(
        ValueError,
        _fixed_handler(422, "INVALID_REQUEST", "request validation failed"),
    )
    app.add_exception_handler(
        FeatureDeferred,
        _fixed_handler(
            501,
            "FEATURE_DEFERRED",
            "diagnosis is deferred in the foundation milestone",
        ),
    )
    app.add_exception_handler(
        DatabaseUnavailable,
        _fixed_handler(503, "DATABASE_UNAVAILABLE", "database is unavailable"),
    )
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(
        Exception,
        _fixed_handler(500, "INTERNAL_ERROR", "internal server error"),
    )
