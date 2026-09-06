"""Compose packaged page resources without a build step or additional HTTP routes.

Scripts deliberately share one classic-script scope: the existing inline event
handlers and independent page-language preferences remain supported. Only the
source files are modular; deployed pages still contain all their own assets.
"""

import json
from functools import cache, lru_cache
from importlib.resources import files

from oceanpilot.web_i18n import ADMIN_I18N_SCRIPT, CLIENT_I18N_SCRIPT

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
    "merchant/support.js",
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


@lru_cache(maxsize=1)
def render_merchant_page() -> str:
    return _compose("merchant", MERCHANT_SCRIPTS).replace("__CLIENT_I18N__", CLIENT_I18N_SCRIPT)


def render_operations_page(client_base_url: str) -> str:
    return (
        _compose("operations", OPERATIONS_SCRIPTS)
        .replace("__CLIENT_BASE__", json.dumps(client_base_url.rstrip("/")))
        .replace("__ADMIN_I18N__", ADMIN_I18N_SCRIPT)
    )
