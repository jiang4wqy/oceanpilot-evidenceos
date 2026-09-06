"""Self-contained chargeback console served at the existing public page routes."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from oceanpilot.web.rendering import render_merchant_page

router = APIRouter()


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/demo")


@router.get("/demo", include_in_schema=False, response_class=HTMLResponse)
def demo_page() -> HTMLResponse:
    return HTMLResponse(render_merchant_page())
