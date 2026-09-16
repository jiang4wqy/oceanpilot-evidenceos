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

from oceanpilot.adapters.channels.feishu.knowledge_bot import load_public_groups  # noqa: E402
from oceanpilot.adapters.channels.feishu.public_knowledge import PublicKnowledge  # noqa: E402
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
    base_url = os.getenv("OCEANPILOT_V2_BASE_URL", "")

    groups = {}
    knowledge = None
    with suppress(ValueError, KeyError, TypeError):
        groups = load_public_groups(os.getenv("OCEANPILOT_FEISHU_PUBLIC_GROUPS_JSON", ""))
    with suppress(ValueError, KeyError, TypeError, OSError):
        knowledge = PublicKnowledge.from_path(os.getenv("OCEANPILOT_FEISHU_PUBLIC_KNOWLEDGE_PATH"))

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
        ("authorized_public_groups", bool(groups)),
        ("approved_public_knowledge", bool(knowledge and knowledge.documents)),
        ("feishu_api_credentials", api_credentials and api_token_ok),
        ("public_https_health", _public_health(base_url)),
        (
            "authorized_outbound",
            bool(groups) and os.getenv("OCEANPILOT_FEISHU_PUBLIC_OUTBOUND") == "authorized-test",
        ),
    ]
    for name, ready in checks:
        print(f"{name}={_yes(ready)}")
    private_cases = os.getenv("OCEANPILOT_FEISHU_PRIVATE_CASES") == "enabled"
    print(
        "configured_bot_scope="
        + (
            "PUBLIC_KNOWLEDGE_AND_PAIRED_PRIVATE_CASES"
            if private_cases
            else "PUBLIC_KNOWLEDGE_ONLY"
        )
    )
    print("running_process_configuration_verified=NOT_CHECKED")
    print(f"authorized_group_count={len(groups)}")
    print(f"approved_public_document_count={len(knowledge.documents) if knowledge else 0}")
    print("legacy_case_bindings_used=NO")
    private_routes = private_cases and bool(app_id and token and encrypt_key)
    print(f"private_routes_configured={_yes(private_routes)}")
    print(
        "private_outbound_configured="
        + _yes(
            private_routes
            and api_credentials
            and api_token_ok
            and os.getenv("OCEANPILOT_FEISHU_PRIVATE_OUTBOUND") == "authorized-test"
        )
    )
    print("private_pairing_and_access_verified=NOT_CHECKED")
    print("fixed_host_hour_and_restart_acceptance=NOT_CHECKED")
    print("live_delivery_verified=NOT_CHECKED")
    print("credentials_printed=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
