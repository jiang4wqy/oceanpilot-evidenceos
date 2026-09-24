"""Idempotent first-run initialization for the distributable Docker bundle."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from oceanpilot.adapters.knowledge.rule_repository import initialize_rule_database
from oceanpilot.adapters.persistence import database
from oceanpilot.adapters.persistence.chargeback_sqlite import initialize_chargeback_schema
from oceanpilot.adapters.persistence.dispute_identity import SQLiteDisputeIdentity
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.adapters.persistence.migrations import upgrade_database
from oceanpilot.adapters.persistence.sqlite import initialize_schema
from oceanpilot.adapters.persistence.workspace_sqlite import initialize_workspace_schema
from oceanpilot.application.disputes import DisputeService
from oceanpilot.config import Settings
from oceanpilot.domain.dispute_rules import case_plan, match_rule
from oceanpilot.v21_accounts import provision


def wait_for_database(timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            connection = database.connect(":memory:")
            connection.execute("SELECT 1")
            connection.close()
            return
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError("database did not become ready") from None
            time.sleep(1)


def _seed_cases(path: Path) -> int:
    store = SQLiteDisputeStore(path)
    service = DisputeService(
        store,
        rule_matcher=match_rule,
        planner=case_plan,
        upstream_mode=os.getenv("OCEANPILOT_V2_UPSTREAM_MODE", "mock"),
    )
    seeds = (
        ("golden-a", "merchant-a", "VISA", "13.1", 12500, "USD"),
        ("golden-b", "merchant-a", "VISA", "10.4", 9800, "USD"),
        ("golden-c", "merchant-b", "MASTERCARD", "4837", 6400, "EUR"),
        ("golden-d", "merchant-b", "VISA", "13.3", 22100, "USD"),
    )
    created = 0
    for seed_id, merchant, scheme, reason, amount, currency in seeds:
        result = service.execute(
            {
                "command_id": f"distribution-seed:{seed_id}",
                "action": "INTAKE",
                "confirmed": True,
                "data": {
                    "merchant_id": merchant,
                    "transaction_id": f"synthetic-{seed_id}",
                    "scheme": scheme,
                    "channel": "MOCK",
                    "reason_code": reason,
                    "amount_minor": amount,
                    "currency": currency,
                    "event_id": f"synthetic-event-{seed_id}",
                },
            },
            {"role": "OPERATOR", "actor_id": "distribution-bootstrap"},
        )
        created += 0 if result.get("replayed") else 1
    return created


def initialize() -> dict[str, object]:
    settings = Settings.from_env()
    wait_for_database()
    upgrade_database()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    chargeback_path = settings.resolved_chargeback_db_path()
    rules_path = settings.resolved_rules_db_path()
    initialize_schema(settings.db_path)
    initialize_chargeback_schema(chargeback_path)
    initialize_workspace_schema(chargeback_path)
    initialize_rule_database(rules_path)
    identity = SQLiteDisputeIdentity(chargeback_path)
    accounts_file = Path(os.getenv("OCEANPILOT_DEMO_ACCOUNTS", "/app/data/demo-accounts.json"))
    accounts_file.parent.mkdir(parents=True, exist_ok=True)
    account_count = 0
    if not accounts_file.exists() and not identity.list_users():
        account_count = provision(chargeback_path, accounts_file)
    case_count = _seed_cases(chargeback_path)
    return {
        "database_backend": settings.database_backend,
        "accounts_created": account_count,
        "cases_created": case_count,
        "credentials": str(accounts_file),
    }


def main() -> None:
    result = initialize()
    print("OceanPilot initialization: " + json.dumps(result, ensure_ascii=False), flush=True)
    if "--initialize-only" in sys.argv:
        return
    os.execvp(
        "python",
        [
            "python",
            "-m",
            "uvicorn",
            "oceanpilot.main:create_app",
            "--factory",
            "--host",
            "0.0.0.0",
            "--port",
            os.getenv("OCEANPILOT_PORT", "8000"),
        ],
    )


if __name__ == "__main__":
    main()
