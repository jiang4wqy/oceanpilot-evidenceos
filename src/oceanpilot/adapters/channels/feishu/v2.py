"""Verified Feishu callbacks into the case engine and V2.1 shared thread.

External identities are resolved only through operator-managed bindings. Opaque
card references bind the case and revision on the server, never in card input.
"""

import base64
import hashlib
import json
import re
import secrets
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from oceanpilot.adapters.persistence import database as sqlite3
from oceanpilot.domain.errors import SensitiveDataRejected
from oceanpilot.domain.security import assert_no_sensitive_data


class FeishuV2Error(ValueError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def binding_key(kind: str, tenant_key: str, external_id: str) -> str:
    """Domain-separated stable key; no raw tenant/user/chat ID is persisted."""
    raw = json.dumps(["oceanpilot-feishu-v2", kind, tenant_key, external_id])
    return hashlib.sha256(raw.encode()).hexdigest()


_BINDING_VAULT_AAD = b"oceanpilot-feishu-binding-candidate-v1"


def _binding_vault_key(secret: str) -> bytes:
    return hashlib.sha256(_BINDING_VAULT_AAD + secret.encode()).digest()


def _seal_binding_address(tenant: str, actor: str, chat: str, secret: str) -> str:
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps([tenant, actor, chat], separators=(",", ":")).encode()
    ciphertext = AESGCM(_binding_vault_key(secret)).encrypt(nonce, plaintext, _BINDING_VAULT_AAD)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def _open_binding_address(value: str, secret: str) -> tuple[str, str, str]:
    try:
        raw = base64.b64decode(value, altchars=b"-_", validate=True)
        plaintext = AESGCM(_binding_vault_key(secret)).decrypt(
            raw[:12], raw[12:], _BINDING_VAULT_AAD
        )
        decoded = json.loads(plaintext)
        if (
            not isinstance(decoded, list)
            or len(decoded) != 3
            or not all(isinstance(item, str) and item for item in decoded)
        ):
            raise ValueError
        return decoded[0], decoded[1], decoded[2]
    except (ValueError, InvalidTag, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeishuV2Error("BINDING_CANDIDATE_UNAVAILABLE", 404) from exc


def _event_command_id(event_ref: str) -> str:
    """Format new derived IDs without card-number-like digit runs.

    Receipt indexes keep the original digest. Remembered commands and their
    authorization references are immutable and are replayed in their old format;
    this helper does not migrate previously rejected callback commands.
    """
    return "feishu:" + "g".join(
        event_ref[index : index + 8] for index in range(0, len(event_ref), 8)
    )


def _text(value: object, *, limit: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise FeishuV2Error("INVALID_CALLBACK")
    return value


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FeishuV2Error("INVALID_CALLBACK")
    return value


def _case_id(case: dict[str, Any]) -> str:
    return _text(case.get("id") or case.get("case_id"))


@dataclass(frozen=True)
class TrustedBindings:
    actors: dict[str, dict[str, str]]
    chats: dict[str, str]

    @classmethod
    def from_json(cls, raw: str) -> "TrustedBindings":
        try:
            data = _mapping(json.loads(raw))
            actors = _mapping(data.get("actors"))
            chats = _mapping(data.get("chats"))
            if not actors or not chats:
                raise ValueError("empty bindings")
            for key in [*actors, *chats]:
                if not re.fullmatch(r"[0-9a-f]{64}", key):
                    raise ValueError("binding keys must be SHA-256 digests")
            normalized_actors = {}
            for key, raw_identity in actors.items():
                identity = _mapping(raw_identity)
                role = _text(identity.get("role"))
                if role not in {"MERCHANT", "OPERATOR", "SUPERVISOR", "ADMIN"}:
                    raise ValueError("unsupported role")
                normalized_actors[key] = {
                    "role": role,
                    "actor_id": _text(identity.get("actor_id")),
                    "merchant_id": _text(identity.get("merchant_id")),
                }
            return cls(normalized_actors, {k: _text(v) for k, v in chats.items()})
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid V2 Feishu trusted binding configuration") from exc

    def resolve(self, tenant: str, actor: str, chat: str) -> tuple[dict[str, str], str]:
        identity = self.actors.get(binding_key("actor", tenant, actor))
        chat_ref = binding_key("chat", tenant, chat)
        merchant = self.chats.get(chat_ref)
        if identity is None or merchant is None or identity["merchant_id"] != merchant:
            raise FeishuV2Error("UNTRUSTED_BINDING", 403)
        return dict(identity), chat_ref


class FeishuV2Store:
    """Durable immutable callback commands and response replay across restarts."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS dispute_feishu_cards (
                    card_ref TEXT PRIMARY KEY, case_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, chat_ref TEXT NOT NULL,
                    merchant_id TEXT NOT NULL, expires_at INTEGER NOT NULL,
                    kind TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dispute_feishu_receipts (
                    event_ref TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                    command_json TEXT NOT NULL, response_json TEXT
                );
                CREATE TABLE IF NOT EXISTS dispute_feishu_binding_candidates (
                    actor_ref TEXT NOT NULL, chat_ref TEXT NOT NULL,
                    first_seen_at INTEGER NOT NULL, last_seen_at INTEGER NOT NULL,
                    seen_count INTEGER NOT NULL, delivery_ciphertext TEXT,
                    PRIMARY KEY (actor_ref, chat_ref)
                );
                """
            )
            columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(dispute_feishu_binding_candidates)"
                ).fetchall()
            }
            if "delivery_ciphertext" not in columns:
                conn.execute(
                    "ALTER TABLE dispute_feishu_binding_candidates "
                    "ADD COLUMN delivery_ciphertext TEXT"
                )

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def issue_card(self, values: dict[str, Any]) -> str:
        ref = secrets.token_urlsafe(24)
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO dispute_feishu_cards VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    ref,
                    *(
                        values[k]
                        for k in (
                            "case_id",
                            "revision",
                            "chat_ref",
                            "merchant_id",
                            "expires_at",
                            "kind",
                        )
                    ),
                ),
            )
        return ref

    def observe_binding_candidate(
        self,
        tenant: str,
        actor: str,
        chat: str,
        now: int,
        *,
        vault_key: str | None = None,
    ) -> None:
        """Remember opaque refs and an optional encrypted reply address."""
        actor_ref = binding_key("actor", tenant, actor)
        chat_ref = binding_key("chat", tenant, chat)
        ciphertext = _seal_binding_address(tenant, actor, chat, vault_key) if vault_key else None
        with self._connection() as conn:
            conn.execute(
                """INSERT INTO dispute_feishu_binding_candidates
                       (actor_ref, chat_ref, first_seen_at, last_seen_at, seen_count,
                        delivery_ciphertext)
                   VALUES (?, ?, ?, ?, 1, ?)
                   ON CONFLICT(actor_ref, chat_ref) DO UPDATE SET
                       last_seen_at=excluded.last_seen_at,
                       seen_count=dispute_feishu_binding_candidates.seen_count + 1,
                       delivery_ciphertext=COALESCE(
                           excluded.delivery_ciphertext,
                           dispute_feishu_binding_candidates.delivery_ciphertext
                       )""",
                (actor_ref, chat_ref, now, now, ciphertext),
            )

    def binding_candidates(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT actor_ref, chat_ref, first_seen_at, last_seen_at, seen_count
                   FROM dispute_feishu_binding_candidates
                   ORDER BY last_seen_at DESC LIMIT 100"""
            ).fetchall()
        return [dict(row) for row in rows]

    def binding_delivery_address(
        self, actor_ref: str, chat_ref: str, *, vault_key: str
    ) -> dict[str, str]:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT delivery_ciphertext
                   FROM dispute_feishu_binding_candidates
                   WHERE actor_ref=? AND chat_ref=?""",
                (actor_ref, chat_ref),
            ).fetchone()
        if row is None or not row["delivery_ciphertext"]:
            raise FeishuV2Error("BINDING_CANDIDATE_UNAVAILABLE", 404)
        tenant, actor, chat = _open_binding_address(row["delivery_ciphertext"], vault_key)
        if (
            binding_key("actor", tenant, actor) != actor_ref
            or binding_key("chat", tenant, chat) != chat_ref
        ):
            raise FeishuV2Error("BINDING_CANDIDATE_UNAVAILABLE", 404)
        return {"tenant_key": tenant, "open_id": actor, "chat_id": chat}

    def card(self, ref: str) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM dispute_feishu_cards WHERE card_ref = ?", (ref,)
            ).fetchone()
        if row is None:
            raise FeishuV2Error("UNKNOWN_CARD", 403)
        return dict(row)

    def receipt(self, ref: str, fingerprint: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM dispute_feishu_receipts WHERE event_ref = ?", (ref,)
            ).fetchone()
        if row is None:
            return None
        if row["fingerprint"] != fingerprint:
            raise FeishuV2Error("EVENT_REUSE_CONFLICT", 409)
        return {
            "command": json.loads(row["command_json"]),
            "response": json.loads(row["response_json"]) if row["response_json"] else None,
        }

    def remember(self, ref: str, fingerprint: str, command: dict[str, Any]) -> dict[str, Any]:
        with self._connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO dispute_feishu_receipts VALUES (?, ?, ?, NULL)",
                (ref, fingerprint, json.dumps(command, sort_keys=True)),
            )
        return self.receipt(ref, fingerprint)  # type: ignore[return-value]

    def complete(self, ref: str, response: dict[str, Any]) -> None:
        with self._connection() as conn:
            conn.execute(
                "UPDATE dispute_feishu_receipts SET response_json = ? WHERE event_ref = ?",
                (json.dumps(response, sort_keys=True), ref),
            )


_CARD_TITLES = {
    "NEW_DISPUTE": "OceanPilot · 新争议任务",
    "MISSING_EVIDENCE": "OceanPilot · 待补充材料",
    "SLA_REMINDER": "OceanPilot · 时限提醒",
    "REVIEW_FEEDBACK": "OceanPilot · OceanPayment 审核反馈",
    "SUMMARY": "OceanPilot · 案件摘要",
}


def _plan_text(plan: dict[str, Any]) -> str:
    lines = [f"案件版本：{plan['revision']}"] if "revision" in plan else []
    if plan.get("summary"):
        lines.append(str(plan["summary"]))
    missing = [
        item.get("label", item.get("code", ""))
        for item in plan.get("checklist", [])
        if not item.get("present")
    ]
    if missing:
        lines.append("待补材料：" + "、".join(missing))
    for label, key in (("商户截止", "merchant"),):
        lines.append(f"{label}：{plan.get('deadlines', {}).get(key) or '待确认'}")
    next_action = plan.get("next_action", {})
    if isinstance(next_action, dict) and next_action.get("reason"):
        lines.append("下一步：" + str(next_action["reason"]))
    lines.extend(str(item) for item in plan.get("blockers", []))
    for source in plan.get("source_citations", []):
        lines.append(
            f"规则来源：{source.get('source_id')} · {source.get('rule_version')}"
            f" · {source.get('source_locator')}"
        )
    return "\n".join(lines)[:3500]


class FeishuV2Adapter:
    def __init__(
        self,
        service: Any,
        bindings: TrustedBindings,
        store: FeishuV2Store,
        *,
        base_url: str,
        plan: Callable[[dict[str, Any]], dict[str, Any]],
        binding_vault_key: str | None = None,
        now: Callable[[], int] = lambda: int(time.time()),
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username:
            raise ValueError("base_url must be an absolute http(s) application URL")
        self.service, self.bindings, self.store = service, bindings, store
        self.base_url, self.plan, self.now = base_url.rstrip("/"), plan, now
        self.binding_vault_key = binding_vault_key
        self.outbox = None

    def shared_plan(self, case):
        from oceanpilot.application.dispute_views import merchant_plan_view

        return merchant_plan_view(self.plan(case))

    def render_help_card(self, identity: dict[str, str] | None = None) -> dict[str, Any]:
        role = (identity or {}).get("role")
        content = (
            "**可用命令**\n"
            "- `帮助`：显示本说明\n"
            "- `案件列表`：查看当前账号可访问的案件\n"
            "- `案件 CASE_ID 还缺什么？`：查看摘要、材料缺口和下一步\n"
        )
        role_commands = {
            "MERCHANT": (
                "- `案件 CASE_ID 确认接受责任`：明确接受责任\n"
                "- `案件 CASE_ID 确认提出抗辩`：明确提出抗辩\n"
                "- `案件 CASE_ID 确认提交证据`：材料齐全后提交审核\n"
            ),
            "OPERATOR": (
                "- `案件 CASE_ID 检查时限`：运行一次 SLA 检查\n"
                "- `案件 CASE_ID 构建材料包`：基于已审核材料生成草稿\n"
                "- `案件 CASE_ID 确认发布商户任务`：发布下一项商户任务\n"
                "- `案件 CASE_ID 确认审核通过：理由`：通过证据审核\n"
                "- `案件 CASE_ID 确认退回补件：理由`：退回商户补件\n"
            ),
            "SUPERVISOR": ("- `案件 CASE_ID 确认已完成PII检查并批准材料包：理由`：冻结材料包\n"),
        }
        if role == "SUPERVISOR":
            content += role_commands["OPERATOR"] + role_commands["SUPERVISOR"]
        else:
            content += role_commands.get(role, "")
        content += (
            "\n群聊中请把 `案件` 换成 `@OceanPilot`。涉及决定、审核或提交的命令必须包含“确认”。"
        )
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "OceanPilot · 飞书助手"},
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content}},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "打开商户工作台"},
                            "url": f"{self.base_url}/v2/merchant",
                        }
                    ],
                },
            ],
        }

    def render_case_list_card(
        self, identity: dict[str, str], cases: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        visible = [
            case
            for case in (cases if cases is not None else self.service.list_cases(identity))
            if case.get("merchant_id") == identity.get("merchant_id")
        ][:10]
        elements: list[dict[str, Any]] = []
        for case in visible:
            case_id = _case_id(case)
            amount = case.get("amount_minor", case.get("amount", "—"))
            text = (
                f"**{case_id}**\n"
                f"状态：{case.get('work_status', '—')}｜"
                f"决定：{case.get('merchant_decision', '—')}\n"
                f"金额：{amount} {case.get('currency', '')}｜原因：{case.get('reason_code', '—')}"
            )
            case_url = f"{self.base_url}/v2/merchant/cases/{quote(case_id, safe='')}"
            elements.extend(
                [
                    {"tag": "div", "text": {"tag": "lark_md", "content": text}},
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "查看案件"},
                                "url": case_url,
                            }
                        ],
                    },
                    {"tag": "hr"},
                ]
            )
        if not elements:
            elements.append(
                {
                    "tag": "div",
                    "text": {"tag": "plain_text", "content": "当前账号暂无可访问案件。"},
                }
            )
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "OceanPilot · 我的案件"},
            },
            "elements": elements,
        }

    def _case(self, case_id: str, identity: dict[str, str]) -> dict[str, Any]:
        case = self.service.get_case(case_id, identity)
        if identity.get("merchant_id") and case.get("merchant_id") != identity["merchant_id"]:
            raise FeishuV2Error("CASE_BINDING_MISMATCH", 403)
        return case

    def render_case_card(
        self,
        case_id: str,
        identity: dict[str, str],
        *,
        tenant_key: str,
        chat_id: str,
        kind: str = "NEW_DISPUTE",
    ) -> dict[str, Any]:
        """Render locally for a trusted chat; this method never sends messages."""
        if kind not in _CARD_TITLES:
            raise FeishuV2Error("INVALID_CARD_KIND")
        chat_ref = binding_key("chat", tenant_key, chat_id)
        case = self._case(case_id, identity)
        if self.bindings.chats.get(chat_ref) != case.get("merchant_id"):
            raise FeishuV2Error("UNTRUSTED_BINDING", 403)
        plan = self.shared_plan(case)
        ref = self.store.issue_card(
            {
                "case_id": case_id,
                "revision": case["revision"],
                "chat_ref": chat_ref,
                "merchant_id": case["merchant_id"],
                "expires_at": self.now() + 3600,
                "kind": kind,
            }
        )
        amount = (
            f"争议金额：{case['amount_minor']}（最小货币单位）"
            if "amount_minor" in case
            else f"争议金额：{case.get('amount', '')}"
        )
        text = (
            f"案件 {case_id}\n{amount} {case.get('currency', '')}"
            f"\n状态：{case.get('work_status', 'NEEDS_CONFIRMATION')}"
            f"\n原因：{case.get('reason_code', 'NEEDS_CONFIRMATION')}"
            f"\n数据：{case.get('source_type', 'SYNTHETIC_DEMO')}"
            "\n上游：Mock；卡片：本地预览，投递状态以消息回执为准"
        )
        elements: list[dict[str, Any]] = [
            {"tag": "div", "text": {"tag": "plain_text", "content": text}},
            {
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": _plan_text(plan),
                },
            },
        ]
        actions = []
        rule = case.get("rule_snapshot") or {}
        allowed = rule.get("allowed_actions")
        if rule.get("conflict_status") != "VERIFIED" or not isinstance(allowed, list):
            allowed = []
        if kind == "NEW_DISPUTE" and case.get("merchant_decision") == "NONE":
            for decision, label in (("ACCEPT", "接受责任"), ("CONTEST", "提出抗辩")):
                if decision not in allowed:
                    continue
                actions.append(
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": label},
                        "value": {
                            "action": "MERCHANT_DECISION",
                            "card_ref": ref,
                            "decision": decision,
                            "confirmed": True,
                        },
                        "confirm": {
                            "title": {"tag": "plain_text", "content": "确认商户决定"},
                            "text": {
                                "tag": "plain_text",
                                "content": f"确认案件 {case_id}：{label}？",
                            },
                        },
                    }
                )
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看案件"},
                "url": f"{self.base_url}/v2/merchant/cases/{quote(case_id, safe='')}",
            }
        )
        elements.append({"tag": "action", "actions": actions})
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": _CARD_TITLES[kind]},
            },
            "elements": elements,
        }

    def handle(self, payload: dict[str, Any], *, mode: str) -> dict[str, Any]:
        """Call only after FeishuRequestVerifier has authenticated the raw body."""
        header, event = _mapping(payload.get("header")), _mapping(payload.get("event"))
        tenant, event_id = _text(header.get("tenant_key")), _text(header.get("event_id"))
        event_type = header.get("event_type")
        if mode == "card":
            if event_type != "card.action.trigger":
                raise FeishuV2Error("INVALID_CALLBACK")
            actor = _text(_mapping(event.get("operator")).get("open_id"))
            chat = _text(_mapping(event.get("context")).get("open_chat_id"))
        else:
            if event_type != "im.message.receive_v1":
                return {"code": 0, "outcome": "IGNORED"}
            sender = _mapping(event.get("sender"))
            if sender.get("sender_type") == "app":
                return {"code": 0, "outcome": "IGNORED_BOT"}
            if sender.get("sender_type") != "user":
                raise FeishuV2Error("INVALID_CALLBACK")
            actor = _text(_mapping(sender.get("sender_id")).get("open_id"))
            chat = _text(_mapping(event.get("message")).get("chat_id"))
        try:
            identity, chat_ref = self.bindings.resolve(tenant, actor, chat)
        except FeishuV2Error as exc:
            if exc.code == "UNTRUSTED_BINDING":
                self.store.observe_binding_candidate(
                    tenant,
                    actor,
                    chat,
                    self.now(),
                    vault_key=self.binding_vault_key,
                )
            raise
        event_ref = binding_key("event", tenant, event_id)
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        receipt = self.store.receipt(event_ref, fingerprint)
        if receipt is None:
            command = self._command(event, mode, identity, chat_ref, event_ref)
            if command is None:
                return {"code": 0, "outcome": "IGNORED"}
            receipt = self.store.remember(event_ref, fingerprint, command)
        command = receipt["command"]
        if command["action"] in {"FEISHU_HELP", "FEISHU_LIST_CASES"}:
            # Re-read through the service on every replay so disabled/revoked local
            # accounts cannot receive a previously frozen query response.
            cases = self.service.list_cases(identity)
            if receipt["response"] is not None:
                return receipt["response"]
            card = (
                self.render_help_card(identity)
                if command["action"] == "FEISHU_HELP"
                else self.render_case_list_card(identity, cases)
            )
            response = {
                "code": 0,
                "outcome": "QUERY_RECORDED",
                "query": "HELP" if command["action"] == "FEISHU_HELP" else "CASE_LIST",
                "channel": "FEISHU",
                "outbound_delivery": "DISABLED",
            }
            if self.outbox is not None:
                message_id = _mapping(event.get("message")).get("message_id")
                try:
                    queued = self.outbox.static_callback(
                        event_ref=event_ref,
                        identity=identity,
                        target_ref=chat_ref,
                        message_id=message_id,
                        card=card,
                        kind=response["query"],
                    )
                    response["outbound_delivery"] = queued["state"]
                    response["outbox_id"] = queued.get("id")
                except Exception:
                    response["outbound_delivery"] = "NOT_QUEUED"
            self.store.complete(event_ref, response)
            return response
        case = self._case(command["case_id"], identity)
        if receipt["response"] is not None:
            return receipt["response"]
        collaboration = getattr(self.service, "collaboration", None)
        if command["action"] == "COLLABORATION_MESSAGE":
            if collaboration is None:
                raise FeishuV2Error("SHARED_THREAD_UNAVAILABLE", 503)
            message_id = _mapping(event.get("message")).get("message_id")
            root_id = _mapping(event.get("message")).get("root_id")
            if root_id and self.outbox is not None:
                linked_case = self.outbox.message_case(root_id, chat_ref)
                if linked_case is not None and linked_case != command["case_id"]:
                    raise FeishuV2Error("CASE_BINDING_MISMATCH", 403)
            shared = collaboration.post_message(
                command["case_id"],
                identity,
                command["command_id"],
                command["data"]["message"],
                "SHARED",
                False,
                metadata={
                    key: command["data"][key]
                    for key in ("channel", "external_event_id", "thread_id")
                },
            )
            case = self._case(command["case_id"], identity)
            # The first verified event freezes its deterministic answer. If receipt
            # completion is interrupted, later business changes cannot mutate the replay.
            public_plan = command["data"]["reply_plan"]
            collaboration.publish_agent_answer(
                command["case_id"],
                {
                    "answer": _plan_text(public_plan),
                    "source": "DETERMINISTIC",
                    "provider": "DETERMINISTIC",
                    "model": "case-plan",
                    "source_citations": public_plan.get("source_citations", []),
                    "conversation_id": command["command_id"],
                    "run": {"case_revision": command["expected_revision"]},
                },
                "SHARED",
                parent_id=shared["message"]["id"],
            )
        else:
            result = self.service.execute(command, identity)
            case = result["case"]
            message_id = _mapping(event.get("context") or {}).get("open_message_id")
        response = {
            "code": 0,
            "outcome": "RECORDED",
            "case_id": _case_id(case),
            "revision": case["revision"],
            "case_plan": self.shared_plan(case),
            "channel": "FEISHU",
            "outbound_delivery": "DISABLED",
        }
        if self.outbox is not None:
            try:
                queued = self.outbox.callback(
                    event_ref=event_ref,
                    case_id=_case_id(case),
                    identity=identity,
                    target_ref=chat_ref,
                    message_id=message_id,
                    update=mode == "card",
                )
                response["outbound_delivery"] = queued["state"]
                response["outbox_id"] = queued.get("id")
            except Exception:
                # A committed decision/shared message stays successful when delivery is disabled.
                response["outbound_delivery"] = "NOT_QUEUED"
        self.store.complete(event_ref, response)
        return response

    def _command(self, event, mode, identity, chat_ref, event_ref):
        metadata = {"channel": "FEISHU", "external_event_id": event_ref, "thread_id": chat_ref}
        if mode == "card":
            value = _mapping(_mapping(event.get("action")).get("value"))
            if value.get("action") != "MERCHANT_DECISION":
                raise FeishuV2Error("ACTION_NOT_ALLOWED", 403)
            if identity["role"] != "MERCHANT":
                raise FeishuV2Error("MERCHANT_AUTHORIZATION_REQUIRED", 403)
            if value.get("confirmed") is not True:
                raise FeishuV2Error("HUMAN_CONFIRMATION_REQUIRED", 409)
            if value.get("decision") not in {"ACCEPT", "CONTEST"}:
                raise FeishuV2Error("INVALID_DECISION")
            card = self.store.card(_text(value.get("card_ref")))
            if card["chat_ref"] != chat_ref or card["merchant_id"] != identity["merchant_id"]:
                raise FeishuV2Error("CASE_BINDING_MISMATCH", 403)
            if card["expires_at"] < self.now():
                raise FeishuV2Error("CARD_EXPIRED", 409)
            if card["kind"] != "NEW_DISPUTE":
                raise FeishuV2Error("ACTION_NOT_ALLOWED", 403)
            if "case_id" in value and value["case_id"] != card["case_id"]:
                raise FeishuV2Error("CASE_BINDING_MISMATCH", 403)
            self._case(card["case_id"], identity)
            return {
                "command_id": _event_command_id(event_ref),
                "case_id": card["case_id"],
                "action": "MERCHANT_DECISION",
                "expected_revision": card["revision"],
                "confirmed": True,
                "data": {
                    **metadata,
                    "decision": value["decision"],
                    "reason": "Merchant confirmed this decision in the Feishu case card.",
                    "authorization_reference": _event_command_id(event_ref),
                },
            }
        message = _mapping(event.get("message"))
        if message.get("message_type") != "text":
            return None
        try:
            content = _mapping(json.loads(_text(message.get("content"), limit=16000)))
        except json.JSONDecodeError as exc:
            raise FeishuV2Error("INVALID_CALLBACK") from exc
        text = _text(content.get("text"), limit=4000).strip()
        try:
            assert_no_sensitive_data(text)
        except SensitiveDataRejected as exc:
            raise FeishuV2Error("SENSITIVE_DATA_REJECTED", 422) from exc
        query_match = re.fullmatch(
            r"(?:@OceanPilot|@_user_\d+)\s*(帮助|案件列表|/help)", text, re.I
        )
        if query_match is None and message.get("chat_type") == "p2p":
            query_match = re.fullmatch(r"(帮助|案件列表|/help)", text, re.I)
        if query_match is not None:
            query = query_match[1].lower()
            return {
                "command_id": _event_command_id(event_ref),
                "action": "FEISHU_LIST_CASES" if query == "案件列表" else "FEISHU_HELP",
                "confirmed": False,
                "data": metadata,
            }
        # Explicit case selection is required; a merchant chat can contain many cases.
        # Group callbacks must contain the bot mention. A p2p chat may use the shorter
        # `案件 CASE_ID ...` form because every received message is addressed to the bot.
        match = re.fullmatch(r"(?:@OceanPilot|@_user_\d+)\s+([\w-]{1,128})\s*(.*)", text, re.S)
        if match is None and message.get("chat_type") == "p2p":
            match = re.fullmatch(r"(?:案件\s+)?([\w-]{1,128})\s+(.+)", text, re.S)
        if match is None:
            return None
        case = self._case(match[1], identity)
        instruction = match[2].strip()
        decision = {
            "确认接受责任": "ACCEPT",
            "确认提出抗辩": "CONTEST",
        }.get(instruction)
        if decision is not None:
            if identity["role"] != "MERCHANT":
                raise FeishuV2Error("MERCHANT_AUTHORIZATION_REQUIRED", 403)
            return {
                "command_id": _event_command_id(event_ref),
                "case_id": _case_id(case),
                "action": "MERCHANT_DECISION",
                "expected_revision": case["revision"],
                "confirmed": True,
                "data": {
                    **metadata,
                    "decision": decision,
                    "reason": f"Merchant typed the explicit Feishu command: {instruction}",
                    "authorization_reference": _event_command_id(event_ref),
                },
            }
        if instruction == "确认提交证据":
            if identity["role"] not in {"MERCHANT", "OPERATOR", "SUPERVISOR"}:
                raise FeishuV2Error("MERCHANT_AUTHORIZATION_REQUIRED", 403)
            return {
                "command_id": _event_command_id(event_ref),
                "case_id": _case_id(case),
                "action": "SUBMIT_EVIDENCE",
                "expected_revision": case["revision"],
                "confirmed": True,
                "data": metadata,
            }
        role_actions = {
            ("OPERATOR", "检查时限"): ("MONITOR_SLA", False, {}),
            ("OPERATOR", "构建材料包"): ("BUILD_PACKAGE", False, {}),
            ("OPERATOR", "确认发布商户任务"): ("PUBLISH_TASK", True, {}),
        }
        command_role = "OPERATOR" if identity["role"] == "SUPERVISOR" else identity["role"]
        role_action = role_actions.get((command_role, instruction))
        if role_action is not None:
            action, confirmed, data = role_action
            return {
                "command_id": _event_command_id(event_ref),
                "case_id": _case_id(case),
                "action": action,
                "expected_revision": case["revision"],
                "confirmed": confirmed,
                "data": {**metadata, **data},
            }
        review_match = re.fullmatch(
            r"确认(审核通过|退回补件)[：:]\s*(.{1,1000})", instruction, re.S
        )
        if review_match is not None and command_role == "OPERATOR":
            return {
                "command_id": _event_command_id(event_ref),
                "case_id": _case_id(case),
                "action": "REVIEW",
                "expected_revision": case["revision"],
                "confirmed": True,
                "data": {
                    **metadata,
                    "decision": "PASS" if review_match[1] == "审核通过" else "REVISION",
                    "reason": review_match[2].strip(),
                },
            }
        approval_match = re.fullmatch(
            r"确认已完成PII检查并批准材料包[：:]\s*(.{1,1000})", instruction, re.S
        )
        if approval_match is not None and identity["role"] == "SUPERVISOR":
            return {
                "command_id": _event_command_id(event_ref),
                "case_id": _case_id(case),
                "action": "APPROVE_PACKAGE",
                "expected_revision": case["revision"],
                "confirmed": True,
                "data": {
                    **metadata,
                    "pii_checked": True,
                    "reason": approval_match[1].strip(),
                },
            }
        shared = bool(getattr(self.service, "collaboration", None))
        return {
            "command_id": _event_command_id(event_ref),
            "case_id": _case_id(case),
            "action": "COLLABORATION_MESSAGE" if shared else "COMMENT",
            "expected_revision": case["revision"],
            "confirmed": False,
            "data": {
                **metadata,
                "message": text,
                **({"reply_plan": self.shared_plan(case)} if shared else {}),
            },
        }
