"""Separate management-console application, intended for port 8003."""

import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

from oceanpilot.web.rendering import render_operations_page


def create_admin_app(client_base_url: str | None = None) -> FastAPI:
    base_url = client_base_url or os.getenv("OCEANPILOT_CLIENT_BASE_URL", "http://127.0.0.1:8002")
    page = render_operations_page(base_url)
    application = FastAPI(
        title="Oceanpayment Operations Console",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @application.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/admin")

    @application.get("/admin", include_in_schema=False, response_class=HTMLResponse)
    def admin_page() -> HTMLResponse:
        return HTMLResponse(page)

    @application.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok", "client_base_url": base_url.rstrip("/")}

    return application
