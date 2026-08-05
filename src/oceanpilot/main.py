from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi

from oceanpilot.adapters.diagnosis.rules import RuleDiagnosisEngine
from oceanpilot.adapters.persistence.sqlite import (
    SqliteCaseStoreFactory,
    initialize_schema,
)
from oceanpilot.api.cases import router as cases_router
from oceanpilot.api.dependencies import RequestContext
from oceanpilot.api.errors import ProblemDetails, register_exception_handlers
from oceanpilot.api.health import router as health_router
from oceanpilot.application.case_service import CaseService
from oceanpilot.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()
    store_factory = SqliteCaseStoreFactory(resolved.db_path)
    case_service = CaseService(
        store_factory,
        RuleDiagnosisEngine(),
        clock=lambda: datetime.now(UTC),
        uuid_factory=lambda: str(uuid4()),
        policy_version=resolved.policy_version,
        engine_version=resolved.engine_version,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        initialize_schema(resolved.db_path)
        with store_factory() as store:
            store.healthcheck()
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.settings = resolved
    app.state.store_factory = store_factory
    app.state.case_service = case_service

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        context = RequestContext(request_id=str(uuid4()), trace_id=str(uuid4()))
        request.state.request_context = context
        response = await call_next(request)
        response.headers["X-Trace-ID"] = context.trace_id
        return response

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(cases_router)

    def openapi_schema() -> dict[str, object]:
        if app.openapi_schema is None:
            schema = get_openapi(
                title=app.title,
                version=app.version,
                routes=app.routes,
            )
            components = schema.setdefault("components", {}).setdefault("schemas", {})
            problem_schema = ProblemDetails.model_json_schema(
                ref_template="#/components/schemas/{model}"
            )
            components.update(problem_schema.pop("$defs", {}))
            components["ProblemDetails"] = problem_schema
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi_schema
    return app
