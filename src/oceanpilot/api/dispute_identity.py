"""Trusted session endpoints and the isolated demonstration director's account tools."""

from importlib.resources import files
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from oceanpilot.adapters.persistence.dispute_identity import SESSION_COOKIE, SQLiteDisputeIdentity
from oceanpilot.api.cases import COMMON_PROBLEMS, PROBLEM_RESPONSE
from oceanpilot.application.dispute_access import DisputeAccessPolicy
from oceanpilot.domain.dispute import DisputeError, require

router = APIRouter(
    tags=["OceanPilot accounts"],
    responses={
        **COMMON_PROBLEMS,
        403: PROBLEM_RESPONSE,
        404: PROBLEM_RESPONSE,
        409: PROBLEM_RESPONSE,
    },
)


class LoginData(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    username: StrictStr = Field(min_length=1, max_length=80)
    password: StrictStr = Field(min_length=1, max_length=128)


class AccountData(LoginData):
    display_name: StrictStr = Field(min_length=1, max_length=80)
    role: StrictStr = Field(min_length=1, max_length=30)
    merchant_id: StrictStr | None = None
    merchant_ids: list[StrictStr] = Field(default_factory=list, max_length=100)


class AccountStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disabled: StrictBool


def initialize_dispute_identity(app, db_path):
    app.state.v21_auth = SQLiteDisputeIdentity(db_path)
    app.state.disputes.access_policy = DisputeAccessPolicy(app.state.v21_auth)


def _same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        require(
            parsed.scheme == request.url.scheme and parsed.netloc == request.url.netloc,
            "CROSS_ORIGIN_REJECTED",
            "请从当前应用页面提交。",
            403,
        )
    require(
        request.headers.get("sec-fetch-site") not in {"cross-site"},
        "CROSS_ORIGIN_REJECTED",
        "请从当前应用页面提交。",
        403,
    )


def session_identity(request: Request) -> dict:
    _same_origin(request)
    return request.app.state.v21_auth.authenticate(
        request.cookies.get(SESSION_COOKIE),
        csrf=request.headers.get("x-csrf-token"),
        write=request.method not in {"GET", "HEAD", "OPTIONS"},
    )


def surface_for(user: dict) -> str:
    return {"MERCHANT": "merchant", "ADMIN": "governance", "DIRECTOR": "director"}.get(
        user["role"], "operations"
    )


def _session_payload(auth, token: str, user: dict):
    return {"user": user, "csrf_token": auth.csrf_token(token), "surface": surface_for(user)}


@router.post("/api/v2/session/login")
def login(payload: LoginData, request: Request, response: Response) -> dict:
    _same_origin(request)
    require(
        request.headers.get("content-type", "").split(";", 1)[0] == "application/json",
        "INVALID_CONTENT_TYPE",
        "登录请求必须为 JSON。",
        415,
    )
    auth = request.app.state.v21_auth
    token, user = auth.login(
        payload.username,
        payload.password,
        remote=request.client.host if request.client else "local",
    )
    auth.logout(request.cookies.get(SESSION_COOKIE))
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        path="/",
        max_age=8 * 3600,
        secure=request.app.state.settings.v21_secure_cookies,
    )
    response.headers["Cache-Control"] = "no-store"
    return _session_payload(auth, token, user)


@router.get("/api/v2/session")
def session(request: Request, response: Response) -> dict:
    identity = session_identity(request)
    response.headers["Cache-Control"] = "no-store"
    return _session_payload(
        request.app.state.v21_auth, request.cookies[SESSION_COOKIE], identity["user"]
    )


@router.get("/api/v2/runtime")
def runtime(request: Request, response: Response) -> dict:
    session_identity(request)
    response.headers["Cache-Control"] = "no-store"
    return request.app.state.v21_runtime | {
        "model": request.app.state.agent_runtime,
        "upstream": request.app.state.disputes.upstream_mode.upper(),
        "case_library": request.app.state.dispute_case_library.manifest(),
        "feishu_configured": getattr(request.app.state, "dispute_feishu", None) is not None,
    }


@router.post("/api/v2/session/logout")
def logout(request: Request, response: Response) -> dict:
    session_identity(request)
    request.app.state.v21_auth.logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="strict", path="/")
    return {"logged_out": True}


def _director(request: Request) -> dict:
    identity = session_identity(request)
    require(identity["role"] == "DIRECTOR", "FORBIDDEN", "需要独立的演示导演账号。", 403)
    return identity


@router.get("/api/v2/director/accounts")
def accounts(request: Request) -> dict:
    _director(request)
    return {"users": request.app.state.v21_auth.list_users()}


@router.post("/api/v2/director/accounts")
def create_account(payload: AccountData, request: Request) -> dict:
    _director(request)
    require(payload.role != "DIRECTOR", "FORBIDDEN", "导演账号仅由本机维护命令创建。", 403)
    return request.app.state.v21_auth.create_user(**payload.model_dump())


@router.post("/api/v2/director/accounts/{user_id}/status")
def account_status(user_id: str, payload: AccountStatus, request: Request) -> dict:
    identity = _director(request)
    require(user_id != identity["actor_id"], "FORBIDDEN", "不能停用当前导演账号。", 403)
    request.app.state.v21_auth.set_disabled(user_id, payload.disabled)
    return {"user": request.app.state.v21_auth.get_user(user_id)}


def page_access(request: Request, roles: set[str]):
    try:
        identity = session_identity(request)
    except DisputeError as exc:
        if exc.status == 401:
            return RedirectResponse(
                "/v2/login?" + urlencode({"next": request.url.path}), status_code=303
            )
        raise
    if identity["role"] not in roles:
        home = "/v2/" + surface_for(identity["user"])
        return HTMLResponse(
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>无访问权限</title>'
            "<main><h1>此账号无权进入这个工作区</h1><p>访问地址不会改变你的身份。</p>"
            f'<a href="{home}">返回我的工作区</a></main></html>',
            status_code=403,
            headers={"Cache-Control": "no-store"},
        )
    return None


@router.get("/v2/login", response_class=HTMLResponse, include_in_schema=False)
def login_page() -> HTMLResponse:
    return HTMLResponse(
        files("oceanpilot.web").joinpath("v2/login.html").read_text("utf-8"),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/v2/director", response_class=HTMLResponse, include_in_schema=False)
def director_page(request: Request) -> HTMLResponse:
    denied = page_access(request, {"DIRECTOR"})
    if denied is not None:
        return denied
    return HTMLResponse(
        files("oceanpilot.web").joinpath("v2/director.html").read_text("utf-8"),
        headers={"Cache-Control": "no-store"},
    )
