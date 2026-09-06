"""Strict JSON helpers for model-authored presentation fields."""

import json


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate model output key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite model output value")


def json_object(raw: str) -> dict[str, object] | None:
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(
            raw.strip(), object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
    except (json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def json_text(raw: str, field: str) -> str | None:
    value = json_object(raw)
    if value is None:
        return None
    text = value.get(field)
    return text.strip() if isinstance(text, str) and text.strip() else None
