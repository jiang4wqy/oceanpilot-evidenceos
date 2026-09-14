#!/usr/bin/env python3
"""一次性工具 查询飞书租户信息与机器人所在群 生成 OceanPilot 绑定模板

用途:
    应用创建并发布后 运行本脚本获取 tenant_key chat_id open_id
    输出可直接粘贴到 .env 的 bindings / targets 模板

用法:
    PYTHONPATH=src .venv/bin/python scripts/fetch_feishu_ids.py \
        --app-id cli_xxx --app-secret xxx
    # 或复用 .env 中的 FEISHU_APP_ID / FEISHU_APP_SECRET
    PYTHONPATH=src .venv/bin/python scripts/fetch_feishu_ids.py
    # 顺带拉取群成员 open_id 需要 im:chat.member 权限
    PYTHONPATH=src .venv/bin/python scripts/fetch_feishu_ids.py --members

前置:
    1 已在 open.feishu.cn 创建企业自建应用
    2 应用已发布 机器人可被拉入群
    3 机器人已在目标测试群中
    4 已开通权限 im:chat（群信息） 如需成员再开 im:chat.member

安全:
    本脚本只读取开放平台公开信息 不发送任何消息
    App Secret 仅用于换取 tenant_access_token 不会打印
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

# 允许直接运行脚本时也能找到项目包
SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from oceanpilot.adapters.channels.feishu.v2 import binding_key  # noqa: E402

BASE_URL = "https://open.feishu.cn"


class FeishuApiError(RuntimeError):
    pass


def _request(client: httpx.Client, token: str, method: str, path: str, *, params: dict | None = None, payload: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    response = client.request(method, f"{BASE_URL}{path}", params=params, json=payload, headers=headers, timeout=15)
    try:
        body = response.json()
    except ValueError as exc:
        raise FeishuApiError(f"响应不是 JSON HTTP {response.status_code}") from exc
    if body.get("code") != 0:
        hint = _permission_hint(path, body.get("code"))
        raise FeishuApiError(f"接口 {path} 返回 code={body.get('code')} msg={body.get('msg')}{hint}")
    return body.get("data") or {}


def _permission_hint(path: str, code) -> str:
    if code in (99991668, 99991661, 99991663):
        if path.startswith("/open-apis/im/v1/chats/"):
            return " 提示 请确认已开通 im:chat.member 权限 并已发布应用"
        if path.startswith("/open-apis/im/v1/chats"):
            return " 提示 请确认已开通 im:chat 权限 应用已发布 且机器人已被拉入群"
        if path.startswith("/open-apis/tenant/v2"):
            return " 提示 请确认应用已创建并发布 且使用正确的 App ID / Secret"
    return ""


def get_tenant_access_token(client: httpx.Client, app_id: str, app_secret: str) -> str:
    response = client.post(
        f"{BASE_URL}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=15,
    )
    try:
        body = response.json()
    except ValueError as exc:
        raise FeishuApiError(f"获取 token 失败 HTTP {response.status_code}") from exc
    if body.get("code") != 0 or not body.get("tenant_access_token"):
        raise FeishuApiError(f"获取 tenant_access_token 失败 code={body.get('code')} msg={body.get('msg')} 请检查 App ID 与 App Secret")
    return body["tenant_access_token"]


def fetch_tenant(client: httpx.Client, token: str) -> dict:
    data = _request(client, token, "GET", "/open-apis/tenant/v2/tenant/query")
    return {"name": data.get("name"), "tenant_key": data.get("tenant_key")}


def fetch_chats(client: httpx.Client, token: str) -> list[dict]:
    items: list[dict] = []
    page_token: str | None = None
    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        data = _request(client, token, "GET", "/open-apis/im/v1/chats", params=params)
        for chat in data.get("items") or []:
            if chat.get("chat_id") and chat.get("chat_mode") == "group":
                items.append({"chat_id": chat["chat_id"], "name": chat.get("name") or "(未命名群)"})
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
    return items


def fetch_members(client: httpx.Client, token: str, chat_id: str) -> list[str]:
    members: list[str] = []
    page_token: str | None = None
    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        data = _request(client, token, "GET", f"/open-apis/im/v1/chats/{chat_id}/members", params=params)
        for item in data.get("items") or []:
            member_id = item.get("member_id")
            if member_id:
                members.append(member_id)
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
    return members


def build_bindings_template(tenant_key: str, chats: list[dict]) -> dict:
    return {
        "actors": {
            # 把每个 open_id 替换成真实值 并从下面注释里选角色
            binding_key("actor", tenant_key, "用户的open_id_占位"): {
                "role": "MERCHANT",
                "actor_id": "系统账号ID_占位",
                "merchant_id": "商户ID_占位",
            }
        },
        "chats": {binding_key("chat", tenant_key, c["chat_id"]): "商户ID_占位" for c in chats},
    }


def build_targets_template(tenant_key: str, chats: list[dict]) -> dict:
    return {
        "targets": [
            {
                "tenant_key": tenant_key,
                "chat_id": c["chat_id"],
                "merchant_id": "商户ID_占位",
                "authorized": True,
                "authorization_reference": "owner-approved-test-space",
                "label": c["name"],
                "allow_callback_replies": False,
            }
            for c in chats
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="查询飞书租户与机器人所在群 生成绑定模板")
    parser.add_argument("--app-id", help="飞书应用 App ID 缺省读环境变量 FEISHU_APP_ID")
    parser.add_argument("--app-secret", help="飞书应用 App Secret 缺省读环境变量 FEISHU_APP_SECRET")
    parser.add_argument("--members", action="store_true", help="同时拉取各群成员 open_id")
    parser.add_argument("--out", help="把 bindings 与 targets 模板写入文件 缺省只打印")
    args = parser.parse_args()

    app_id = args.app_id or os.getenv("FEISHU_APP_ID", "")
    app_secret = args.app_secret or os.getenv("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        print("缺少 App ID 或 App Secret")
        print("请传 --app-id / --app-secret 或在 .env 中配置 FEISHU_APP_ID / FEISHU_APP_SECRET")
        return 2

    try:
        with httpx.Client() as client:
            token = get_tenant_access_token(client, app_id, app_secret)
            print("token 获取成功 tenant_access_token 已换取 不打印明文")

            tenant = fetch_tenant(client, token)
            if not tenant.get("tenant_key"):
                print("tenant_key 为空 请检查接口返回")
                return 1
            print(f"\n== 租户信息 ==")
            print(f"企业名      {tenant.get('name')}")
            print(f"tenant_key  {tenant['tenant_key']}")

            chats = fetch_chats(client, token)
            print(f"\n== 机器人所在群 共 {len(chats)} 个 ==")
            for i, chat in enumerate(chats, 1):
                print(f"{i}. {chat['name']}  chat_id={chat['chat_id']}")
            if not chats:
                print("没有找到机器人所在的群 请确认应用已发布 且机器人已被拉入测试群")

            if args.members:
                for chat in chats:
                    try:
                        members = fetch_members(client, token, chat["chat_id"])
                    except FeishuApiError as exc:
                        print(f"\n群 {chat['name']} 拉成员失败 {exc}")
                        continue
                    print(f"\n群 {chat['name']} 成员 {len(members)} 人")
                    for member in members:
                        print(f"  open_id={member}")
    except FeishuApiError as exc:
        print(f"执行失败 {exc}")
        return 1

    bindings = build_bindings_template(tenant["tenant_key"], chats)
    targets = build_targets_template(tenant["tenant_key"], chats)

    print("\n== 可粘贴到 .env 的配置 ==")
    print(f"OCEANPILOT_V2_FEISHU_BINDINGS_JSON={json.dumps(bindings, ensure_ascii=False, indent=2)}")
    print(f"\nOCEANPILOT_V21_FEISHU_TEST_TARGETS_JSON={json.dumps(targets, ensure_ascii=False, indent=2)}")

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(
            json.dumps({"bindings": bindings, "targets": targets}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\n模板已写入 {out_path}")

    print("\n下一步")
    print("1 把 actors 里的 open_id 占位 替换成商户真实 open_id 并填写系统账号与商户ID")
    print("2 把 chats 和 targets 里的 商户ID_占位 替换成案件使用的 merchant_id")
    print("3 替换完成后 将两行配置复制进 .env 重启服务")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
