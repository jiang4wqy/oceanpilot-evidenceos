import sqlite3
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi

from oceanpilot.adapters.diagnosis.rules import RuleDiagnosisEngine
from oceanpilot.adapters.feishu.client import (
    FeishuHttpRequest,
    FeishuHttpResponse,
    FeishuOutboundClient,
)
from oceanpilot.adapters.feishu.security import FeishuRequestVerifier
from oceanpilot.adapters.feishu.store import FeishuCallbackStoreFactory
from oceanpilot.adapters.persistence.sqlite import (
    SqliteCaseStoreFactory,
    initialize_schema,
)
from oceanpilot.api.cases import router as cases_router
from oceanpilot.api.dependencies import FeishuRuntime, RequestContext
from oceanpilot.api.errors import ProblemDetails, register_exception_handlers
from oceanpilot.api.feishu import router as feishu_router
from oceanpilot.api.health import router as health_router
from oceanpilot.application.case_service import CaseService
from oceanpilot.application.feishu_orchestrator import FeishuOrchestrator
from oceanpilot.config import Settings


def create_app(
    settings: Settings | None = None,
    *,
    feishu_transport: Callable[[FeishuHttpRequest], FeishuHttpResponse] | None = None,
) -> FastAPI:
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
        initialize_schema(resolved.db_path)
        with store_factory() as store:
            store.healthcheck()
        app.state.feishu_runtime = None
        if resolved.feishu is not None and resolved.feishu.is_complete:
            try:
                callback_db_path = Path(resolved.feishu.callback_db_path)
                if callback_db_path.resolve() != resolved.db_path.resolve():
                    callback_store = FeishuCallbackStoreFactory(callback_db_path)
                    app.state.feishu_runtime = FeishuRuntime(
                        verifier=FeishuRequestVerifier(
                            encrypt_key=resolved.feishu.encrypt_key,
                            verification_token=resolved.feishu.verification_token,
                            now=lambda: int(datetime.now(UTC).timestamp()),
                        ),
                        store_factory=callback_store,
                        outbound_client=FeishuOutboundClient(
                            app_id=resolved.feishu.app_id,
                            app_secret=resolved.feishu.app_secret,
                            transport=feishu_transport,
                        ),
                        orchestrator=FeishuOrchestrator(
                            case_service,
                            callback_store,
                            callback_store,
                        ),
                        app_id=resolved.feishu.app_id,
                        demo_chat_id=(
                            resolved.feishu.demo_chat_id
                            if resolved.feishu.business_demo_is_complete
                            else None
                        ),
                        demo_merchant_ref=(
                            resolved.feishu.demo_merchant_ref
                            if resolved.feishu.business_demo_is_complete
                            else None
                        ),
                    )
            except (OSError, sqlite3.Error, TypeError, ValueError):
                app.state.feishu_runtime = None
        try:
            yield
        finally:
            app.state.feishu_runtime = None

    app = FastAPI(lifespan=lifespan)
    app.state.settings = resolved
    app.state.store_factory = store_factory
    app.state.case_service = case_service
    app.state.feishu_runtime = None

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
    app.include_router(feishu_router)

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
