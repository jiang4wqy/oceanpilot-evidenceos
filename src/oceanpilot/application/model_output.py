"""Strict JSON helpers for model-authored presentation fields."""

import json


def json_object(raw: str) -> dict[str, object] | None:
    try:
        value = json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def json_text(raw: str, field: str) -> str | None:
    value = json_object(raw)
    if value is None:
        return None
    text = value.get(field)
    return text.strip() if isinstance(text, str) and text.strip() else None
