from typing import Annotated

from fastapi import APIRouter, Depends

from oceanpilot.api.cases import PROBLEM_RESPONSE
from oceanpilot.api.dependencies import get_store_factory
from oceanpilot.application.ports import CaseStoreFactory

router = APIRouter()


@router.get("/health", responses={503: PROBLEM_RESPONSE})
def health(
    store_factory: Annotated[CaseStoreFactory, Depends(get_store_factory)],
) -> dict[str, str]:
    with store_factory() as store:
        store.healthcheck()
    return {"status": "ok"}
