import logging
import os
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi

from oceanpilot.adapters.channels.feishu.channel import FeishuChannel
from oceanpilot.adapters.clock import SystemClock
from oceanpilot.adapters.diagnosis.rules import RuleDiagnosisEngine
from oceanpilot.adapters.feishu.client import (
    FeishuHttpRequest,
    FeishuHttpResponse,
    FeishuOutboundClient,
)
from oceanpilot.adapters.feishu.security import FeishuRequestVerifier
from oceanpilot.adapters.feishu.store import FeishuCallbackStoreFactory
from oceanpilot.adapters.knowledge.bank_rules import InMemoryBankRules
from oceanpilot.adapters.model.composition import build_chargeback_model_provider
from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.adapters.persistence.chargeback_sqlite import (
    SqliteChargebackCaseStore,
    initialize_chargeback_schema,
)
from oceanpilot.adapters.persistence.sqlite import (
    SqliteCaseStoreFactory,
    initialize_schema,
)
from oceanpilot.adapters.upstream.mock import MockUpstreamConnector
from oceanpilot.api.cases import router as cases_router
from oceanpilot.api.chargeback import router as chargeback_router
from oceanpilot.api.demo import router as demo_router
from oceanpilot.api.dependencies import RequestContext
from oceanpilot.api.errors import ProblemDetails, register_exception_handlers
from oceanpilot.api.feishu import router as feishu_router
from oceanpilot.api.health import router as health_router
from oceanpilot.application.case_service import CaseService
from oceanpilot.application.chargeback_agents import (
    ChargebackAssessAgent,
    EvidenceAgent,
    IntakeAgent,
    PreventionAgent,
)
from oceanpilot.application.chargeback_appeal import AppealAgent
from oceanpilot.application.chargeback_channel_service import ChargebackChannelService
from oceanpilot.application.chargeback_deadline import DeadlineTracker
from oceanpilot.application.chargeback_packager import PackagerAgent
from oceanpilot.application.chargeback_supervisor import ChargebackSupervisor
from oceanpilot.application.feishu_orchestrator import FeishuOrchestrator
from oceanpilot.application.metrics import DecisionMetrics
from oceanpilot.application.model_provider import ModelProvider
from oceanpilot.config import FeishuSettings, Settings

_request_logger = logging.getLogger("oceanpilot.request")


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in ("1", "true", "yes", "on")


def _configure_feishu(
    app: FastAPI,
    feishu: FeishuSettings,
    case_service: CaseService,
    transport: Callable[[FeishuHttpRequest], FeishuHttpResponse] | None,
) -> None:
    app.state.feishu_settings = feishu
    app.state.feishu_verifier = FeishuRequestVerifier(
        encrypt_key=feishu.encrypt_key,
        verification_token=feishu.verification_token,
        now=lambda: int(time.time()),
    )
    app.state.feishu_client = FeishuOutboundClient(
        app_id=feishu.app_id,
        app_secret=feishu.app_secret,
        transport=transport,
    )
    app.state.feishu_orchestrator = FeishuOrchestrator(
        case_service,
        clock=lambda: datetime.now(UTC),
        uuid_factory=lambda: str(uuid4()),
    )


def create_app(
    settings: Settings | None = None,
    *,
    feishu_transport: Callable[[FeishuHttpRequest], FeishuHttpResponse] | None = None,
    chargeback_model: ModelProvider | None = None,
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

    chargeback_db_path = resolved.resolved_chargeback_db_path()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        initialize_schema(resolved.db_path)
        with store_factory() as store:
            store.healthcheck()
        initialize_chargeback_schema(chargeback_db_path)
        if resolved.feishu is not None:
            app.state.feishu_store_factory = FeishuCallbackStoreFactory(resolved.feishu.db_path)
        yield

    application = FastAPI(lifespan=lifespan)
    application.state.settings = resolved
    application.state.store_factory = store_factory
    application.state.case_service = case_service

    # Chargeback agent cluster. Offline by default (no API key). An explicit
    # switch (OCEANPILOT_CHARGEBACK_LIVE_MODEL) opts into the live tiered provider
    # so tests/CI stay deterministic even when an ANTHROPIC_API_KEY is present;
    # `chargeback_model` injection always wins.
    chargeback_provider: ModelProvider | None = chargeback_model
    if chargeback_provider is None and _truthy(os.getenv("OCEANPILOT_CHARGEBACK_LIVE_MODEL")):
        chargeback_provider = build_chargeback_model_provider()
    if chargeback_provider is None:
        chargeback_provider = ScriptedModelProvider(default_text="（合成模型输出，仅用于离线演示）")
    application.state.chargeback_supervisor = ChargebackSupervisor(
        intake=IntakeAgent(chargeback_provider),
        evidence=EvidenceAgent(chargeback_provider),
        assess=ChargebackAssessAgent(chargeback_provider),
    )
    # Durable store: chargeback cases survive across requests/restarts with an
    # atomic audit trail and optimistic CAS. Its own file, initialized in lifespan.
    application.state.chargeback_store = SqliteChargebackCaseStore(
        chargeback_db_path,
        clock=lambda: datetime.now(UTC),
    )
    # SLA / evidence-window deadline tracker, surfaced on every delivery.
    application.state.chargeback_deadline = DeadlineTracker(SystemClock())
    # Representment packaging + appeal drafting (appeal submits only behind a
    # human-approval gate; the upstream connector is a synthetic mock).
    application.state.chargeback_packager = PackagerAgent(chargeback_provider, InMemoryBankRules())
    application.state.chargeback_appeal = AppealAgent(chargeback_provider, MockUpstreamConnector())
    # Pre-dispute prevention advisor (purely advisory; never acts on a payment).
    application.state.chargeback_prevention = PreventionAgent(chargeback_provider)
    # Decision metrics (human-review rate, model-vs-fallback, appeal/prevention mix).
    application.state.chargeback_metrics = DecisionMetrics()
    application.state.chargeback_channel_service = ChargebackChannelService(
        application.state.chargeback_supervisor,
        application.state.chargeback_store,
        deadline=application.state.chargeback_deadline,
        metrics=application.state.chargeback_metrics,
    )
    application.state.chargeback_feishu_channel = FeishuChannel()

    if resolved.feishu is not None:
        _configure_feishu(application, resolved.feishu, case_service, feishu_transport)

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        context = RequestContext(request_id=str(uuid4()), trace_id=str(uuid4()))
        request.state.request_context = context
        response = await call_next(request)
        response.headers["X-Trace-ID"] = context.trace_id
        # Structured, PII-free request line (method/path/status + correlation ids).
        _request_logger.info(
            "request method=%s path=%s status=%s request_id=%s trace_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            context.request_id,
            context.trace_id,
        )
        return response

    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(cases_router)
    application.include_router(feishu_router)
    application.include_router(chargeback_router)
    application.include_router(demo_router)

    def openapi_schema() -> dict[str, object]:
        if application.openapi_schema is None:
            schema = get_openapi(
                title=application.title,
                version=application.version,
                routes=application.routes,
            )
            components = schema.setdefault("components", {}).setdefault("schemas", {})
            problem_schema = ProblemDetails.model_json_schema(
                ref_template="#/components/schemas/{model}"
            )
            components.update(problem_schema.pop("$defs", {}))
            components["ProblemDetails"] = problem_schema
            application.openapi_schema = schema
        return application.openapi_schema

    application.openapi = openapi_schema
    return application
