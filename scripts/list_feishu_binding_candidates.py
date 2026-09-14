#!/usr/bin/env python3
"""List opaque user/chat pairs observed from verified Feishu callbacks."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def default_db_path() -> Path:
    explicit = os.getenv("OCEANPILOT_CHARGEBACK_DB_PATH")
    if explicit:
        return Path(explicit)
    core = Path(os.getenv("OCEANPILOT_DB_PATH", "work/oceanpilot.db"))
    return core.parent / "oceanpilot-chargeback.db"


def candidates(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """SELECT actor_ref, chat_ref, first_seen_at, last_seen_at, seen_count
                   FROM dispute_feishu_binding_candidates
                   ORDER BY last_seen_at DESC LIMIT 100"""
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(row) for row in rows]


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="列出签名校验通过、但尚未配置的飞书用户和会话哈希")
    parser.add_argument("--db", type=Path, help="飞书 SQLite 路径")
    parser.add_argument("--select", type=int, help="输出第 N 个候选的可信绑定模板")
    parser.add_argument("--role", default="MERCHANT")
    parser.add_argument("--actor-id", help="OceanPilot 本地账号 ID")
    parser.add_argument("--merchant-id", help="OceanPilot 商户 ID")
    parser.add_argument(
        "--target",
        action="store_true",
        help="同时输出使用加密投递地址生成的出站目标模板",
    )
    args = parser.parse_args()

    rows = candidates(args.db or default_db_path())
    if not rows:
        print("暂无绑定候选。请先让目标用户给机器人发送一条测试消息。")
        return 0
    for index, row in enumerate(rows, 1):
        print(
            f"{index}. actor_ref={row['actor_ref']} chat_ref={row['chat_ref']} "
            f"seen={row['seen_count']} last_seen={row['last_seen_at']}"
        )

    if args.select is None:
        return 0
    if not 1 <= args.select <= len(rows):
        parser.error("--select 超出候选范围")
    if not args.actor_id or not args.merchant_id:
        parser.error("生成模板时必须同时提供 --actor-id 与 --merchant-id")
    selected = rows[args.select - 1]
    template = {
        "actors": {
            selected["actor_ref"]: {
                "role": args.role,
                "actor_id": args.actor_id,
                "merchant_id": args.merchant_id,
            }
        },
        "chats": {selected["chat_ref"]: args.merchant_id},
    }
    print("\nOCEANPILOT_V2_FEISHU_BINDINGS_JSON=" + json.dumps(template, ensure_ascii=False))
    if args.target:
        from oceanpilot.adapters.channels.feishu.v2 import FeishuV2Store

        vault_key = os.getenv("FEISHU_ENCRYPT_KEY", "")
        if not vault_key:
            parser.error("--target 需要环境变量 FEISHU_ENCRYPT_KEY")
        address = FeishuV2Store(args.db or default_db_path()).binding_delivery_address(
            str(selected["actor_ref"]), str(selected["chat_ref"]), vault_key=vault_key
        )
        target = {
            "targets": [
                {
                    "tenant_key": address["tenant_key"],
                    "chat_id": address["chat_id"],
                    "merchant_id": args.merchant_id,
                    "authorized": True,
                    "authorization_reference": "owner-approved-feishu-space",
                    "label": "OceanPilot 已授权飞书会话",
                    "allow_callback_replies": False,
                }
            ]
        }
        print("OCEANPILOT_V21_FEISHU_TEST_TARGETS_JSON=" + json.dumps(target, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
