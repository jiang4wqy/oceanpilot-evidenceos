"""Compose packaged page resources without a build step or additional HTTP routes.

Scripts deliberately share one classic-script scope: the existing inline event
handlers and independent page-language preferences remain supported. Only the
source files are modular; deployed pages still contain all their own assets.
"""

import json
from functools import cache
from html import escape
from importlib.resources import files

from oceanpilot.web_i18n import ADMIN_I18N_SCRIPT, BUSINESS_I18N_SCRIPT, CLIENT_I18N_SCRIPT

MERCHANT_SCRIPTS = (
    "shared/request.js",
    "merchant/case-state.js",
    "merchant/state.js",
    "merchant/api.js",
    "merchant/materials.js",
    "merchant/agent-review.js",
    "merchant/cases.js",
    "merchant/assessment.js",
    "merchant/rules.js",
    "merchant/concerns.js",
    "merchant/bootstrap.js",
)
OPERATIONS_SCRIPTS = ("shared/request.js", "operations/console.js")


@cache
def resource_text(path: str) -> str:
    """Read a developer-owned resource from source installs or built wheels."""

    return files("oceanpilot.web").joinpath(path).read_text(encoding="utf-8")


def _compose(page: str, scripts: tuple[str, ...]) -> str:
    return (
        resource_text(f"{page}/shell.html")
        .replace("__PAGE_STYLES__", resource_text(f"{page}/styles.css").rstrip())
        .replace("__PAGE_SCRIPT__", "\n".join(resource_text(path).rstrip() for path in scripts))
        .replace("__OCEANPAYMENT_LOGO__", resource_text("assets/logo.data-uri"))
    )


@cache
def _render_workspace(role: str, admin_origin: str) -> str:
    business = role == "BUSINESS"
    values = {
        "__WORKSPACE_ROLE__": role,
        "__WORKSPACE_TITLE__": (
            "Oceanpayment · 企业争议运营" if business else "Oceanpayment · 商户工作台"
        ),
        "__ROLE_LABEL__": "企业争议运营区" if business else "商户材料提交区",
        "__OTHER_ROLE_LABEL__": "商户材料提交区" if business else "企业争议运营区",
        "__OTHER_WORKSPACE_PATH__": "/demo" if business else "/business",
        "__DEMO_ACTOR__": "synthetic-business" if business else "synthetic-merchant",
        "__LIST_TITLE__": "争议运营工作台" if business else "我的争议案件",
        "__LIST_DESCRIPTION__": (
            "查看当前阻断、材料缺口与待办，在同一案件版本完成登记复核与摘要导出。"
            if business
            else "登记合成案件与材料，了解当前缺口、下一步及企业运营方的复核结果。"
        ),
        "__OPERATIONS_URL__": admin_origin.rstrip("/") + "/admin",
    }
    body = _compose("merchant", MERCHANT_SCRIPTS)
    for marker, value in values.items():
        body = body.replace(marker, escape(value, quote=True))
    return body.replace(
        "__WORKSPACE_CONFIG__", json.dumps({"role": role}, separators=(",", ":"))
    ).replace("__CLIENT_I18N__", BUSINESS_I18N_SCRIPT if business else CLIENT_I18N_SCRIPT)


def render_merchant_page(admin_origin: str = "http://127.0.0.1:8003") -> str:
    return _render_workspace("MERCHANT", admin_origin)


def render_business_page(admin_origin: str = "http://127.0.0.1:8003") -> str:
    return _render_workspace("BUSINESS", admin_origin)


def render_operations_page(client_base_url: str) -> str:
    return (
        _compose("operations", OPERATIONS_SCRIPTS)
        .replace("__CLIENT_BASE__", json.dumps(client_base_url.rstrip("/")))
        .replace("__ADMIN_I18N__", ADMIN_I18N_SCRIPT)
    )
