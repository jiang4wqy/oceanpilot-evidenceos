from pathlib import Path
from typing import Annotated, Final

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from oceanpilot.api.cases import COMMON_PROBLEMS, PROBLEM_RESPONSE
from oceanpilot.api.dependencies import get_demo_query
from oceanpilot.application.demo_query import DemoCaseDetail, DemoQuery
from oceanpilot.domain.models import UUID4Str

router = APIRouter()
_STATIC_ROOT: Final = Path(__file__).resolve().parent.parent / "static" / "demo"


@router.get("/demo", include_in_schema=False, response_class=FileResponse)
def demo_home() -> FileResponse:
    return FileResponse(_STATIC_ROOT / "index.html", media_type="text/html")


@router.get("/demo/assets/styles.css", include_in_schema=False, response_class=FileResponse)
def demo_styles() -> FileResponse:
    return FileResponse(_STATIC_ROOT / "styles.css", media_type="text/css")


@router.get("/demo/assets/app.js", include_in_schema=False, response_class=FileResponse)
def demo_script() -> FileResponse:
    return FileResponse(_STATIC_ROOT / "app.js", media_type="application/javascript")


@router.get("/demo/cases/{case_id}", include_in_schema=False, response_class=FileResponse)
def demo_case_page(case_id: UUID4Str) -> FileResponse:
    del case_id
    return FileResponse(_STATIC_ROOT / "case.html", media_type="text/html")


@router.get(
    "/api/v1/demo/cases/{case_id}",
    response_model=DemoCaseDetail,
    responses={404: PROBLEM_RESPONSE, **COMMON_PROBLEMS},
)
def demo_case_detail(
    case_id: UUID4Str,
    query: Annotated[DemoQuery, Depends(get_demo_query)],
) -> DemoCaseDetail:
    return query.get_case_detail(case_id)
