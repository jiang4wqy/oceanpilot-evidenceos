from dataclasses import dataclass

from fastapi import Request

from oceanpilot.application.case_service import CaseService
from oceanpilot.application.ports import CaseStoreFactory
from oceanpilot.domain.models import UUID4Str


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: UUID4Str
    trace_id: UUID4Str


def get_request_context(request: Request) -> RequestContext:
    return request.state.request_context


def get_store_factory(request: Request) -> CaseStoreFactory:
    return request.app.state.store_factory


def get_case_service(request: Request) -> CaseService:
    return request.app.state.case_service
