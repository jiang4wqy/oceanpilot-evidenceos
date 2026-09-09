"""Provision explicit local demonstration accounts, never implicit HTTP identities.

Run with --db (the V2 dispute database) and --output (an untracked local JSON file).
Existing usernames are preserved; no password or account is silently overwritten.
"""

import argparse
import json
import os
import secrets
from pathlib import Path

from oceanpilot.adapters.persistence.dispute_identity import SQLiteDisputeIdentity

DEFAULT_ACCOUNTS = (
    ("merchant-a", "商户 A 协作人", "MERCHANT", ["merchant-a"]),
    ("merchant-b", "商户 B 协作人", "MERCHANT", ["merchant-b"]),
    ("operator-a", "运营专员 A", "OPERATOR", ["merchant-a"]),
    ("operator-b", "运营专员 B", "OPERATOR", ["merchant-b"]),
    ("risk-reviewer", "独立风控审核员", "RISK_OFFICER", ["merchant-a", "merchant-b"]),
    ("supervisor", "独立主管", "SUPERVISOR", ["merchant-a", "merchant-b"]),
    ("administrator", "知识管理员", "ADMIN", ["merchant-a", "merchant-b"]),
    ("director", "演示导演", "DIRECTOR", []),
)


def provision(db_path, output_path):
    output_path = Path(output_path)
    if output_path.exists():
        raise ValueError("凭据文件已存在；不会覆盖现有账号或密码。")
    store = SQLiteDisputeIdentity(db_path)
    existing = {user["username"] for user in store.list_users()}
    if existing.intersection(name for name, *_ in DEFAULT_ACCOUNTS):
        raise ValueError("部分默认账号已存在；请使用导演账号管理，不会静默重置密码。")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Reserve a private output file before mutating the directory.
    descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        records = []
        for username, display_name, role, merchants in DEFAULT_ACCOUNTS:
            password = secrets.token_urlsafe(20)
            user = store.create_user(
                username=username,
                password=password,
                display_name=display_name,
                role=role,
                merchant_ids=merchants,
                merchant_id=merchants[0] if role == "MERCHANT" else None,
            )
            records.append({"user": user, "password": password})
            stream.seek(0)
            json.dump(
                {"synthetic_only": True, "accounts": records}, stream, ensure_ascii=False, indent=2
            )
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
    return len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="V2 dispute SQLite path")
    parser.add_argument("--output", required=True, help="Private, untracked credentials JSON")
    args = parser.parse_args()
    count = provision(args.db, args.output)
    print(f"已创建 {count} 个独立账号。凭据仅保存在指定的本地文件。")


if __name__ == "__main__":
    main()
