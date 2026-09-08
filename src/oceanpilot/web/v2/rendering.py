"""Render self-contained V2 workspaces from packaged local resources."""

import json
from functools import cache
from importlib.resources import files


@cache
def render_v2_page(role: str = "operations") -> str:
    """Compose a workspace; page selection never grants API authority."""
    surface = role.lower()
    if surface in {"operator", "risk_officer", "supervisor"}:
        surface = "operations"
    if surface == "admin":
        surface = "governance"
    if surface not in {"operations", "merchant", "governance"}:
        raise ValueError("Unknown V2 workspace")
    resources = files("oceanpilot.web")
    return (
        resources.joinpath("v2/shell.html")
        .read_text(encoding="utf-8")
        .replace("__V2_STYLES__", resources.joinpath("v2/styles.css").read_text("utf-8"))
        .replace("__V2_SCRIPT__", resources.joinpath("v2/app.js").read_text("utf-8"))
        .replace("__V2_CONFIG__", json.dumps({"surface": surface}))
        .replace("__V2_LOGO__", resources.joinpath("assets/logo.data-uri").read_text("utf-8"))
    )
