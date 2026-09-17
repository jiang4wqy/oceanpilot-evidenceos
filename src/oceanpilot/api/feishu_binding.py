"""Account-owned linking. No trusted role or merchant can be supplied by a browser."""

from importlib.resources import files

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from oceanpilot.adapters.channels.feishu.v2 import FeishuV2Error
from oceanpilot.api.dispute_identity import session_identity

router = APIRouter(prefix="/binding")


class Confirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    phrase: StrictStr = Field(min_length=8, max_length=8)


def call(request, method, *args):
    identity = session_identity(request)  # Mutations require CSRF + same origin.
    bot = getattr(request.app.state, "feishu_private", None)
    if bot is None:
        return JSONResponse(
            {"code": "PRIVATE_CASES_DISABLED"},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )
    try:
        result = getattr(bot, method)(identity["actor_id"], *args)
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except FeishuV2Error as exc:
        return JSONResponse(
            {"code": exc.code}, status_code=exc.status, headers={"Cache-Control": "no-store"}
        )


@router.get("")
def status(request: Request):
    return call(request, "binding_status")


@router.post("/pairs")
def create(request: Request):
    return call(request, "create_pair")


@router.get("/pairs/{pair_id}")
def pair(request: Request, pair_id: str):
    return call(request, "pair_status", pair_id)


@router.post("/pairs/{pair_id}/confirm")
def confirm(request: Request, pair_id: str, payload: Confirmation):
    return call(request, "confirm_pair", pair_id, payload.phrase)


@router.delete("")
def unlink(request: Request):
    return call(request, "unlink")


@router.get("/page", response_class=HTMLResponse, include_in_schema=False)
def page(request: Request):
    # Public shell only; every data/mutation endpoint above requires a session.
    # Its login form uses the existing session API and stays on this page.
    return HTMLResponse(
        files("oceanpilot.web").joinpath("v2/feishu-link.html").read_text(),
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
        },
    )
