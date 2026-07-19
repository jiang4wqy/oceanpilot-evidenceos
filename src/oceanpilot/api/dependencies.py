from fastapi import Request

from oceanpilot.application.case_service import CaseService
from oceanpilot.application.ports import CaseStoreFactory


def get_store_factory(request: Request) -> CaseStoreFactory:
    return request.app.state.store_factory


def get_case_service(request: Request) -> CaseService:
    return request.app.state.case_service
