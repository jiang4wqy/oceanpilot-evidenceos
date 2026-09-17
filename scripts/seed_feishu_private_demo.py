"""Explicit local rehearsal reset; no network sends, no deletion, no real bank data."""

import argparse
import json
import os
import secrets
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values

from oceanpilot.adapters.channels.feishu.demo import FeishuDemoBatches
from oceanpilot.adapters.channels.feishu.private_cases import PrivateCaseBot
from oceanpilot.adapters.persistence.dispute_identity import SQLiteDisputeIdentity
from oceanpilot.adapters.persistence.dispute_intake import SQLiteDisputeIntakeStore
from oceanpilot.adapters.persistence.disputes import SQLiteDisputeStore
from oceanpilot.application.dispute_access import DisputeAccessPolicy
from oceanpilot.application.dispute_intake import DisputeIntakeService
from oceanpilot.application.disputes import DisputeService

MARKER = "oceanpilot-feishu-private-demo-v1"
MERCHANTS = ["feishu-demo-merchant-a", "feishu-demo-merchant-b"]
SPECS = [
    (MERCHANTS[0], "MERCHANT", [MERCHANTS[0]]),
    (MERCHANTS[1], "MERCHANT", [MERCHANTS[1]]),
    ("feishu-demo-operator-a", "OPERATOR", [MERCHANTS[0]]),
    ("feishu-demo-operator-b", "OPERATOR", [MERCHANTS[1]]),
    ("feishu-demo-supervisor", "SUPERVISOR", MERCHANTS),
    ("feishu-demo-administrator", "ADMIN", MERCHANTS),
]


def accounts(directory, destination):
    if destination.exists():
        data = json.loads(destination.read_text())
        if data.get("kind") != MARKER or set(data.get("accounts", {})) != {x[0] for x in SPECS}:
            raise ValueError("Not this demo's complete private account manifest")
        for name, role, merchants in SPECS:
            saved = data["accounts"][name]
            current = directory.get_user(saved["user"]["id"])
            if not current or current["disabled"] or current["username"] != name:
                raise ValueError("Demo account changed or disabled; use account governance")
            if current["role"] != role or set(current["merchant_ids"]) != set(merchants):
                raise ValueError("Demo grants changed; do not silently override")
        return data["accounts"]
    existing = {u["username"] for u in directory.list_users()}
    if existing.intersection(x[0] for x in SPECS):
        raise ValueError("Demo usernames already exist; recover the original manifest")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    data = {"kind": MARKER, "accounts": {}}
    with os.fdopen(fd, "w") as handle:
        for name, role, merchants in SPECS:
            password = secrets.token_urlsafe(24)
            user = directory.create_user(
                username=name,
                password=password,
                display_name=name,
                role=role,
                merchant_ids=merchants,
                merchant_id=merchants[0] if role == "MERCHANT" else None,
            )
            data["accounts"][name] = {"user": user, "password": password}
            handle.seek(0)
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
    return data["accounts"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="Same case DB used by website")
    parser.add_argument("--credentials", type=Path, required=True, help="Private untracked file")
    parser.add_argument("--env-file", type=Path, required=True, help="Existing local Feishu config")
    parser.add_argument("--batch-id", default=None, help="Reuse only to resume the SAME batch")
    parser.add_argument("--confirm-synthetic-reset", action="store_true")
    args = parser.parse_args()
    if not args.confirm_synthetic_reset:
        parser.error("Explicit --confirm-synthetic-reset is required")
    env = dotenv_values(args.env_file)
    if not env.get("FEISHU_ENCRYPT_KEY") or not env.get("FEISHU_APP_ID"):
        parser.error("Existing Feishu app/encryption configuration required")
    # Client is intentionally None: the website worker is the sole sender.
    directory = SQLiteDisputeIdentity(args.db)
    users = accounts(directory, args.credentials)
    disputes = DisputeService(
        SQLiteDisputeStore(args.db), access_policy=DisputeAccessPolicy(directory)
    )
    bot = PrivateCaseBot(
        args.db.with_name("feishu-private-cases.db"),
        directory=directory,
        disputes=disputes,
        app_id=env["FEISHU_APP_ID"],
        secret=env["FEISHU_ENCRYPT_KEY"],
        base_url=env.get("OCEANPILOT_V2_BASE_URL") or "http://127.0.0.1:8002",
    )
    batch_id = args.batch_id or str(uuid4())
    print("Synthetic batch (resume this ID after failure): " + batch_id, flush=True)
    result = FeishuDemoBatches(
        bot, DisputeIntakeService(SQLiteDisputeIntakeStore(args.db), disputes)
    ).begin(
        batch_id,
        administrator=users["feishu-demo-administrator"]["user"]["id"],
        operators=[
            users["feishu-demo-operator-a"]["user"]["id"],
            users["feishu-demo-operator-b"]["user"]["id"],
        ],
        merchants=MERCHANTS,
        confirmed=True,
    )
    print(json.dumps(result, ensure_ascii=False))
    print("Credentials remain in the private manifest; no Feishu delivery was attempted here.")


if __name__ == "__main__":
    main()
