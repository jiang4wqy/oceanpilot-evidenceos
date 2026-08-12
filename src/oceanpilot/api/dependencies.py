from dataclasses import dataclass

from fastapi import Request

from oceanpilot.adapters.feishu.client import FeishuOutboundClient
from oceanpilot.adapters.feishu.security import FeishuRequestVerifier
from oceanpilot.adapters.feishu.store import FeishuCallbackStoreFactory
from oceanpilot.api.errors import FeishuUnavailable
from oceanpilot.application.case_service import CaseService
from oceanpilot.application.feishu_orchestrator import FeishuOrchestrator
from oceanpilot.application.ports import CaseStoreFactory
from oceanpilot.domain.models import UUID4Str


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: UUID4Str
    trace_id: UUID4Str


@dataclass(frozen=True, slots=True)
class FeishuRuntime:
    verifier: FeishuRequestVerifier
    store_factory: FeishuCallbackStoreFactory
    outbound_client: FeishuOutboundClient
    orchestrator: FeishuOrchestrator
    app_id: str
    demo_chat_id: str | None
    demo_merchant_ref: str | None


def get_request_context(request: Request) -> RequestContext:
    return request.state.request_context


def get_store_factory(request: Request) -> CaseStoreFactory:
    return request.app.state.store_factory


def get_case_service(request: Request) -> CaseService:
    return request.app.state.case_service


def get_feishu_runtime(request: Request) -> FeishuRuntime:
    runtime = getattr(request.app.state, "feishu_runtime", None)
    if runtime is None:
        raise FeishuUnavailable()
    return runtime
