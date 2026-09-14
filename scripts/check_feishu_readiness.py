#!/usr/bin/env python3
"""Report Feishu runtime readiness without printing credentials or raw IDs."""

from __future__ import annotations

import json
import os
import sys
from contextlib import suppress
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from dotenv import load_dotenv

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from oceanpilot.adapters.channels.feishu.outbox import load_test_targets  # noqa: E402
from oceanpilot.adapters.channels.feishu.v2 import TrustedBindings  # noqa: E402
from oceanpilot.adapters.feishu.client import (  # noqa: E402
    FeishuOutboundClient,
    FeishuOutboundError,
)


def _yes(value: bool) -> str:
    return "READY" if value else "NOT_READY"


def _public_health(base_url: str) -> bool:
    if not base_url.startswith("https://"):
        return False
    try:
        with urlopen(base_url.rstrip("/") + "/health", timeout=6) as response:  # noqa: S310
            return response.status == 200 and json.loads(response.read()).get("status") == "ok"
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False


def main() -> int:
    load_dotenv()
    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")
    token = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
    encrypt_key = os.getenv("FEISHU_ENCRYPT_KEY", "")
    raw_bindings = os.getenv("OCEANPILOT_V2_FEISHU_BINDINGS_JSON", "")
    raw_targets = os.getenv("OCEANPILOT_V21_FEISHU_TEST_TARGETS_JSON", "")
    base_url = os.getenv("OCEANPILOT_V2_BASE_URL", "")

    bindings = None
    with suppress(ValueError):
        bindings = TrustedBindings.from_json(raw_bindings)
    placeholders = bool(bindings) and any(
        value.startswith("pending-")
        for identity in bindings.actors.values()
        for value in identity.values()
    )
    try:
        targets = load_test_targets(raw_targets, bindings) if bindings else {}
    except ValueError:
        targets = {}

    api_credentials = bool(app_id and app_secret)
    api_token_ok = False
    if api_credentials:
        try:
            FeishuOutboundClient(app_id=app_id, app_secret=app_secret).get_tenant_access_token()
            api_token_ok = True
        except FeishuOutboundError:
            pass

    checks = [
        ("callback_credentials", bool(token and encrypt_key)),
        ("trusted_bindings", bool(bindings) and not placeholders),
        ("feishu_api_credentials", api_credentials and api_token_ok),
        ("public_https_health", _public_health(base_url)),
        (
            "authorized_outbound",
            bool(targets) and os.getenv("OCEANPILOT_V21_FEISHU_OUTBOUND") == "authorized-test",
        ),
    ]
    for name, ready in checks:
        print(f"{name}={_yes(ready)}")
    print(f"binding_actor_count={len(bindings.actors) if bindings else 0}")
    print(f"binding_chat_count={len(bindings.chats) if bindings else 0}")
    print(f"authorized_target_count={len(targets)}")
    print("credentials_printed=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
