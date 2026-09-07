"""Self-contained chargeback console served at the existing public page routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from oceanpilot.web.rendering import render_business_page, render_merchant_page

router = APIRouter()


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/demo")


@router.get("/demo", include_in_schema=False, response_class=HTMLResponse)
def demo_page(request: Request) -> HTMLResponse:
    return HTMLResponse(render_merchant_page(request.app.state.settings.admin_origin))


@router.get("/business", include_in_schema=False, response_class=HTMLResponse)
def business_page(request: Request) -> HTMLResponse:
    return HTMLResponse(render_business_page(request.app.state.settings.admin_origin))
