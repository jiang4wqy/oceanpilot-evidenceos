"""Opt-in account-linked private chats. Public groups never enter this adapter.

All private records are encrypted. Business decisions use the existing command
service and its atomic receipts; channel delivery never fabricates success.
"""

import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager, suppress
from pathlib import Path
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from oceanpilot.adapters.channels.feishu.case_explanations import (
    focused_card,
    merchant_answer,
    merchant_deadline,
    merchant_next_step,
    query_intent,
)
from oceanpilot.adapters.channels.feishu.v2 import FeishuV2Error, binding_key
from oceanpilot.adapters.feishu.client import FeishuReceiveIdType
from oceanpilot.adapters.redaction import RegexRedactor
from oceanpilot.application.dispute_views import merchant_case_view
from oceanpilot.domain.dispute import DisputeError
from oceanpilot.domain.dispute_rules import case_plan
from oceanpilot.domain.errors import SensitiveDataRejected
from oceanpilot.domain.security import assert_no_sensitive_data


def checked(value, limit=200):
    if not isinstance(value, str) or not 0 < len(value) <= limit:
        raise FeishuV2Error("INVALID_PRIVATE_CALLBACK")
    return value


def mapping(value):
    if not isinstance(value, dict):
        raise FeishuV2Error("INVALID_PRIVATE_CALLBACK")
    return value


class PrivateCaseBot:
    def __init__(
        self,
        path,
        *,
        directory,
        disputes,
        app_id,
        secret,
        base_url,
        client=None,
        model=None,
        now=time.time,
    ):
        self.path, self.directory, self.disputes = path, directory, disputes
        self.app_id, self.base_url, self.client, self.now = (
            app_id,
            base_url.rstrip("/"),
            client,
            now,
        )
        self.cipher = AESGCM(hashlib.sha256(b"feishu-private-v1" + secret.encode()).digest())
        self.stop = threading.Event()
        self.model = model
        self.thread = None
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS fp_records (
                    kind TEXT NOT NULL, ref TEXT NOT NULL, owner TEXT NOT NULL,
                    state TEXT NOT NULL, updated REAL NOT NULL, body BLOB NOT NULL,
                    PRIMARY KEY(kind,ref));
                CREATE INDEX IF NOT EXISTS fp_pending ON fp_records(kind,state,updated);
                CREATE TABLE IF NOT EXISTS fp_links (
                    version TEXT PRIMARY KEY, account TEXT NOT NULL,
                    actor_ref TEXT NOT NULL, chat_ref TEXT NOT NULL, active INTEGER NOT NULL,
                    address BLOB NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS fp_account_active
                    ON fp_links(account) WHERE active=1;
                CREATE UNIQUE INDEX IF NOT EXISTS fp_actor_active
                    ON fp_links(actor_ref) WHERE active=1;
                CREATE UNIQUE INDEX IF NOT EXISTS fp_chat_active
                    ON fp_links(chat_ref) WHERE active=1;
            """)
            try:
                meta, value = self.record(db, "meta", "vault")
                if meta and value != {"app_id": self.app_id, "schema": 1}:
                    raise ValueError("Private vault application/schema mismatch")
                if not meta:
                    # Existing pre-release records must use this key as well.
                    first = db.execute("SELECT * FROM fp_records LIMIT 1").fetchone()
                    if first:
                        self.unseal(first["kind"] + first["ref"], first["body"])
                    self.put(db, "meta", "vault", "", "READY", {"app_id": self.app_id, "schema": 1})
            except InvalidTag:
                raise ValueError("Private vault encryption key mismatch") from None
        Path(path).chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def seal(self, ref, data):
        nonce = secrets.token_bytes(12)
        return nonce + self.cipher.encrypt(nonce, json.dumps(data).encode(), ref.encode())

    def unseal(self, ref, data):
        return json.loads(self.cipher.decrypt(data[:12], data[12:], ref.encode()))

    def put(self, db, kind, ref, owner, state, data):
        db.execute(
            "INSERT INTO fp_records VALUES (?,?,?,?,?,?) ON CONFLICT(kind,ref) "
            "DO UPDATE SET state=excluded.state,updated=excluded.updated,body=excluded.body",
            (kind, ref, owner, state, self.now(), self.seal(kind + ref, data)),
        )

    def record(self, db, kind, ref):
        row = db.execute("SELECT * FROM fp_records WHERE kind=? AND ref=?", (kind, ref)).fetchone()
        return (row, self.unseal(kind + ref, row["body"])) if row else (None, None)

    def identity(self, account):
        user = self.directory.get_user(account)
        if not user or user["disabled"]:
            raise FeishuV2Error("PRIVATE_ACCOUNT_UNAVAILABLE", 403)
        return {
            "actor_id": user["id"],
            "role": user["role"],
            "merchant_id": user.get("merchant_id"),
        }

    def link(self, db, *, actor=None, version=None, account=None):
        field, value = (
            ("actor_ref", actor)
            if actor
            else ("version", version)
            if version
            else ("account", account)
        )
        return db.execute(
            f"SELECT * FROM fp_links WHERE {field}=? AND active=1", (value,)
        ).fetchone()

    def create_pair(self, account):
        self.identity(account)
        code, ref = secrets.token_urlsafe(24), str(uuid4())
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.link(db, account=account):
                raise FeishuV2Error("UNLINK_BEFORE_REBIND", 409)
            db.execute(
                "UPDATE fp_records SET state='REVOKED' WHERE kind='pair' AND owner=?", (account,)
            )
            self.put(
                db,
                "pair",
                ref,
                account,
                "PENDING",
                {
                    "digest": hashlib.sha256(code.encode()).hexdigest(),
                    "expires": self.now() + 600,
                },
            )
        return {
            "pair_id": ref,
            "code": code,
            "expires_in": 600,
            "instruction": "私聊机器人发送：绑定 " + code,
        }

    def pair_status(self, account, ref):
        self.identity(account)
        with self.db() as db:
            row, data = self.record(db, "pair", ref)
            if not row or row["owner"] != account:
                raise FeishuV2Error("PAIR_NOT_FOUND", 404)
            state = row["state"] if data["expires"] > self.now() else "EXPIRED"
            return {
                "pair_id": ref,
                "state": state,
            }

    def claim_pair(self, db, code, address):
        digest = hashlib.sha256(code.encode()).hexdigest()
        for row in db.execute("SELECT * FROM fp_records WHERE kind='pair' AND state='PENDING'"):
            data = self.unseal("pair" + row["ref"], row["body"])
            if secrets.compare_digest(data["digest"], digest) and data["expires"] > self.now():
                self.identity(row["owner"])
                if self.link(db, actor=address["actor_ref"]):
                    raise FeishuV2Error("UNLINK_BEFORE_REBIND", 409)
                phrase = secrets.token_hex(4)
                self.put(
                    db,
                    "pair",
                    row["ref"],
                    row["owner"],
                    "CLAIMED",
                    data | {"address": address, "phrase": phrase},
                )
                return (
                    "配对验证短语："
                    + phrase
                    + "。请回到已登录网站，核对短语后确认绑定；请勿确认他人提供的短语。"
                )
        raise FeishuV2Error("PAIR_INVALID_OR_EXPIRED", 403)

    def confirm_pair(self, account, ref, phrase):
        self.identity(account)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row, data = self.record(db, "pair", ref)
            if (
                not row
                or row["owner"] != account
                or row["state"] != "CLAIMED"
                or data["expires"] <= self.now()
            ):
                raise FeishuV2Error("PAIR_INVALID_OR_EXPIRED", 409)
            if not secrets.compare_digest(data["phrase"], phrase):
                raise FeishuV2Error("PAIR_CONFIRMATION_MISMATCH", 403)
            a = data["address"]
            version = str(uuid4())
            try:
                db.execute(
                    "INSERT INTO fp_links VALUES (?,?,?,?,1,?)",
                    (version, account, a["actor_ref"], a["chat_ref"], self.seal(version, a)),
                )
            except sqlite3.IntegrityError:
                raise FeishuV2Error("UNLINK_BEFORE_REBIND", 409) from None
            self.put(db, "pair", ref, account, "CONFIRMED", data)
            self.put(db, "audit", str(uuid4()), account, "BOUND", {"version": version})
        return {"bound": True, "version": version}

    def unlink(self, account):
        self.identity(account)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE fp_links SET active=0 WHERE account=?", (account,))
            db.execute(
                "UPDATE fp_records SET state='REVOKED' WHERE owner=? AND kind IN ('pair','card')",
                (account,),
            )
            db.execute(
                "UPDATE fp_records SET state='BLOCKED' "
                "WHERE owner=? AND kind='job' AND state='PENDING'",
                (account,),
            )
            self.put(db, "audit", str(uuid4()), account, "UNBOUND", {})
        return {"bound": False}

    def binding_status(self, account):
        self.identity(account)
        with self.db() as db:
            row = self.link(db, account=account)
            return {"bound": bool(row), "version": row["version"] if row else None}

    def card(self, text, actions=()):
        return {
            "config": {"wide_screen_mode": True, "enable_forward": False},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "OceanPilot · 私聊案件助手"},
            },
            "elements": [
                {"tag": "div", "text": {"tag": "plain_text", "content": text[:7000]}},
                *[
                    {"tag": "action", "actions": list(actions)[i : i + 5]}
                    for i in range(0, len(actions), 5)
                ],
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "打开 OceanPilot"},
                            "url": self.base_url + "/api/v2/integrations/feishu/binding/page",
                            "type": "default",
                        }
                    ],
                },
            ],
        }

    def token_button(
        self,
        db,
        link,
        case,
        kind,
        label,
        decision=None,
        *,
        action="MERCHANT_DECISION",
        intent="summary",
    ):
        ref = secrets.token_urlsafe(24)
        data = {
            "version": link["version"],
            "case_id": case["id"],
            "revision": case["revision"],
            "kind": kind,
            "decision": decision,
            "action": action,
            "intent": intent,
            "expires": self.now() + (300 if kind == "CONFIRM" else 1800),
            "command_id": str(uuid4()),
        }
        self.put(db, "card", ref, link["account"], "READY", data)
        return {
            "tag": "button",
            "type": "default",
            "text": {"tag": "plain_text", "content": label},
            "value": {"private_ref": ref},
        }

    def visible_case(self, case_id, identity):
        with self.db() as db:
            old, _ = self.record(db, "retired", case_id)
            if old:
                raise FeishuV2Error("DEMO_BATCH_RETIRED", 409)
        return self.disputes.get_case(case_id, identity)

    def summary(self, db, link, case, *, intent="summary"):
        identity = self.identity(link["account"])
        # Projection first: internal notes, strategy, staff-only evidence never enter text.
        view = merchant_case_view(case)
        # Material presence must not reveal staff-only evidence. Restore only
        # the public requirement classification omitted by the generic projection.
        rule = view.get("rule_snapshot", {})
        plan = case_plan(
            view
            | {
                "rule_snapshot": rule
                | {
                    "critical_evidence": case.get("rule_snapshot", {}).get(
                        "critical_evidence", rule.get("required_evidence", [])
                    )
                }
            }
        )
        text = (
            "合成案例 / Mock 上游；不代表真实银行结果"
            f"\n案件：{case['id']} · 版本 {case['revision']}"
            f"\n当前状态：{case['work_status']}\n商户决定：{case['merchant_decision']}"
        )
        answer = merchant_answer(view, plan, intent, self.now())
        if answer:
            text += "\n答复：" + answer
        # Review feedback is the next-action basis, not a footnote after a long
        # checklist. Keep the latest shared feedback visible on the first screen.
        for feedback in reversed(view.get("public_feedback", [])):
            text += "\n审核反馈：" + RegexRedactor().redact(
                str(feedback.get("reason", "未提供理由"))
            )
        returned = case["work_status"] == "MERCHANT_REVISION_REQUIRED"
        next_step = merchant_next_step(view)
        text += "\n下一步：" + next_step
        text += (
            f"\n争议原因：{case['scheme']} {case['reason_code']}"
            f"\n商户期限：{merchant_deadline(view, self.now())}"
        )
        text += f"\n来源：{rule.get('source_id', '待核实')} / {rule.get('rule_version', '待核实')}"
        text += "\n说明：结构化规则结果（未调用语言模型，不冒充 AI 推理）。"
        if case["merchant_decision"] == "CONTEST" and intent not in {"progress", "deadline"}:
            missing = [item["label"] for item in plan.get("checklist", []) if not item["present"]]
            unchecked = any(
                item["upload_status"] != "SUPPORTED" for item in plan.get("checklist", [])
            )
            text += (
                "\n当前缺少可核实的材料清单，请联系工作人员确认；不能认定材料齐全。"
                if not plan.get("checklist")
                else f"\n当前仍需完善 {len(missing)} 项：" + "、".join(missing)
                if missing
                else "\n清单中已有材料记录，但审核要求补正；已有记录不等于本次审核通过。"
                if returned
                else "\n材料尚未全部通过内容检查，请查看各项状态；已上传待核验不等于需要重复上传。"
                if unchecked
                else "\n当前规则清单全部就绪；仍以提交门禁为准。"
            )
            text += "\n抗辩材料清单（实际规则快照）："
            for item in plan.get("checklist", []):
                status = {
                    "SUPPORTED": "内容检查就绪",
                    "NEEDS_MANUAL": "已上传，待独立人工核验",
                    "INSUFFICIENT": "材料内容不足",
                    "MISSING": "待补充",
                    "REGISTERED": "已登记，待核对",
                }.get(item["upload_status"], "待核对")
                text += f"\n• {item['label']}：{status}"
                text += "（关键）" if item["critical"] else "（必需）"
                text += "\n  用途：" + item["why"]
            text += "\n登记不等于内容合格；上传、核查和审核仍在网站完成。"
        elif case["merchant_decision"] == "ACCEPT":
            text += "\n已选择接受，请等待 OceanPayment 按业务流程处理；不再要求提交抗辩材料。"
        elif case["merchant_decision"] != "CONTEST":
            text += "\n请在允许的范围内选择接受拒付或发起抗辩；抗辩不代表拒付已撤销。"
        gate = self.disputes.action_gate(case, "MERCHANT_DECISION", identity)
        actions = []
        if (
            identity["role"] == "MERCHANT"
            and case["merchant_decision"] == "NONE"
            and gate["enabled"]
        ):
            for decision, label in [("ACCEPT", "接受拒付"), ("CONTEST", "发起抗辩")]:
                if decision in gate.get("choices", []):
                    actions.append(self.token_button(db, link, case, "PREPARE", label, decision))
        elif case["merchant_decision"] == "NONE":
            text += "\n待工作人员核实：" + str(gate.get("blocked_reason") or "当前不允许商户决定")
        if identity["role"] == "MERCHANT" and case["merchant_decision"] == "CONTEST":
            submit = self.disputes.action_gate(case, "SUBMIT_EVIDENCE", identity)
            if submit["enabled"]:
                text += (
                    "\n当前提交门禁允许再次送审；请先处理退回反馈，尚未提交上游。"
                    if returned
                    else "\n材料已核验，可以提交给 OceanPayment 人工审核；尚未提交上游。"
                )
                actions.append(
                    self.token_button(
                        db,
                        link,
                        case,
                        "PREPARE",
                        "提交材料给 OceanPayment",
                        action="SUBMIT_EVIDENCE",
                    )
                )
            else:
                text += "\n提交门禁：" + str(submit.get("blocked_reason") or "当前不可提交")
        text += "\n案件状态、清单和业务门禁：确定性规则；语言模型不执行业务决定。"
        card = self.card(text, actions)
        card["elements"][-1]["actions"].insert(
            0,
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "打开本案 / 上传材料"},
                "url": self.base_url + "/v2/merchant/cases/" + case["id"] + "?stage=1",
                "type": "default",
            },
        )
        return card

    def query(self, db, link, text):
        identity = self.identity(link["account"])
        intent = query_intent(text)
        ids = re.findall(r"OPV2-[A-Za-z0-9_-]+", text)
        if len(ids) > 1:
            return self.card("请一次选择一个案件。"), None, None
        if ids:
            try:
                case = self.visible_case(ids[0], identity)
            except (DisputeError, FeishuV2Error) as exc:
                if not (
                    isinstance(exc, DisputeError)
                    and exc.code == "NOT_FOUND"
                    and exc.status == 404
                    or isinstance(exc, FeishuV2Error)
                    and exc.code == "DEMO_BATCH_RETIRED"
                ):
                    raise
                # Do not distinguish missing, another merchant, or retired cases.
                # The normal verified-message enqueue/event receipt makes this
                # reply durable and idempotent; errors on card mutations still fail.
                return (
                    self.card(
                        "无法访问该案件。请发送“我的案件”从当前获授权列表中选择，"
                        "或登录网站核对；本次未执行任何业务操作。"
                    ),
                    None,
                    None,
                )
            if intent != "staff_action":
                return self.summary(db, link, case, intent=intent), case["id"], case["revision"]
        if intent == "staff_action":
            return (
                self.card(
                    "我不能替代工作人员审核通过材料或提交银行／上游。"
                    "请在网站查看审核反馈，由有权限的工作人员办理审核与提交；"
                    "商户接受或抗辩仍需使用获授权卡片二次确认。本次未执行任何业务操作。"
                ),
                None,
                None,
            )
        cases = self.disputes.list_cases(identity)
        cases = [c for c in cases if not self.record(db, "retired", c["id"])[0]]
        if len(cases) == 1:
            c = cases[0]
            return self.summary(db, link, c, intent=intent), c["id"], c["revision"]
        actions = [
            self.token_button(
                db, link, c, "SELECT", f"{c['id']} · {c['work_status']}", intent=intent
            )
            for c in cases[:10]
        ]
        return (
            self.card("请选择本人获授权的案件。" if cases else "当前没有获授权的案件。", actions),
            None,
            None,
        )

    def enqueue(
        self,
        db,
        ref,
        address,
        card,
        *,
        link=None,
        case_id=None,
        revision=None,
        parent=None,
        intent="summary",
        business_event=None,
    ):
        row, _ = self.record(db, "job", ref)
        if row:
            return
        self.put(
            db,
            "job",
            ref,
            link["account"] if link else "",
            "PENDING",
            {
                "address": address,
                "card": card,
                "version": link["version"] if link else None,
                "case_id": case_id,
                "revision": revision,
                "parent": parent,
                "intent": intent,
                "business_event": business_event,
            },
        )

    def handle(self, payload, *, mode):
        header, event = mapping(payload).get("header", {}), payload.get("event", {})
        if not isinstance(header, dict) or not isinstance(event, dict):
            raise FeishuV2Error("INVALID_PRIVATE_CALLBACK")
        if header.get("app_id") != self.app_id:
            raise FeishuV2Error("UNTRUSTED_APPLICATION", 403)
        tenant = checked(header.get("tenant_key"))
        if mode == "card":
            if header.get("event_type") != "card.action.trigger":
                raise FeishuV2Error("PRIVATE_CARD_REQUIRED", 403)
            sender = mapping(event.get("operator", {}))
            context = mapping(event.get("context", {}))
            actor = checked(sender.get("open_id"))
            chat = checked(context.get("open_chat_id"))
            event_id = checked(event.get("token") or header.get("event_id"))
        else:
            if header.get("event_type") != "im.message.receive_v1":
                return {"code": 0, "outcome": "IGNORED"}
            message = mapping(event.get("message", {}))
            sender = mapping(event.get("sender", {}))
            if message.get("chat_type") != "p2p" or sender.get("sender_type") != "user":
                raise FeishuV2Error("PRIVATE_CHAT_REQUIRED", 403)
            actor = checked(mapping(sender.get("sender_id", {})).get("open_id"))
            chat = checked(message.get("chat_id"))
            event_id = checked(header.get("event_id"))
        if sender.get("tenant_key", tenant) != tenant:
            raise FeishuV2Error("UNTRUSTED_TENANT", 403)
        address = {
            "tenant": tenant,
            "actor": actor,
            "chat": chat,
            "actor_ref": binding_key("actor", tenant, actor),
            "chat_ref": binding_key("chat", tenant, chat),
        }
        ref = binding_key("private-event", tenant, event_id)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old, data = self.record(db, "event", ref)
            if old:
                if data["digest"] != digest:
                    raise FeishuV2Error("EVENT_PAYLOAD_CONFLICT", 409)
                return {"code": 0, "outcome": "REPLAYED"}
            link = self.link(db, actor=address["actor_ref"])
            if link and link["chat_ref"] != address["chat_ref"]:
                raise FeishuV2Error("PRIVATE_CHAT_MISMATCH", 403)
            if mode == "card":
                if not link:
                    raise FeishuV2Error("PRIVATE_BINDING_REQUIRED", 403)
                card, case_id, revision = self.click(db, link, event)
                parent = None
            else:
                parent = checked(message.get("message_id"))
                try:
                    content = json.loads(message.get("content", "{}"))
                    if not isinstance(content, dict):
                        raise ValueError()
                    text = content.get("text", "") if message.get("message_type") == "text" else ""
                except (ValueError, TypeError):
                    raise FeishuV2Error("INVALID_PRIVATE_CALLBACK") from None
                if not isinstance(text, str) or len(text) > 4000:
                    raise FeishuV2Error("INVALID_PRIVATE_CALLBACK")
                if text.startswith("绑定 "):
                    card = self.card(self.claim_pair(db, text[3:].strip(), address))
                    case_id = revision = None
                elif not link:
                    card = self.card(
                        "请先点击下方按钮登录网站，在飞书绑定页生成配对码，"
                        "再私聊发送“绑定 配对码”。"
                    )
                    case_id = revision = None
                elif not text:
                    card = self.card("材料附件请登录网站上传；此处不下载或保存附件。")
                    case_id = revision = None
                else:
                    try:
                        assert_no_sensitive_data(text)
                        card, case_id, revision = self.query(db, link, text)
                    except SensitiveDataRejected:
                        card = self.card("请勿发送敏感个人或支付信息，请登录网站处理。")
                        case_id = revision = None
            self.enqueue(
                db,
                ref,
                address,
                card,
                link=link,
                case_id=case_id,
                revision=revision,
                parent=parent,
                intent=query_intent(text) if mode != "card" else "summary",
            )
            self.put(
                db, "event", ref, link["account"] if link else "", "RECORDED", {"digest": digest}
            )
        return {"code": 0, "outcome": "QUEUED"}

    def click(self, db, link, event):
        identity = self.identity(link["account"])
        value = mapping(event.get("action", {})).get("value", {})
        if not isinstance(value, dict) or set(value) != {"private_ref"}:
            raise FeishuV2Error("PRIVATE_CARD_REQUIRED", 403)
        ref = checked(value.get("private_ref"))
        row, data = self.record(db, "card", ref)
        if (
            not row
            or row["owner"] != link["account"]
            or data["version"] != link["version"]
            or row["state"] == "REVOKED"
        ):
            raise FeishuV2Error("PRIVATE_CARD_FORBIDDEN", 403)
        message_id = event.get("context", {}).get("open_message_id")
        if not message_id or message_id not in data.get("message_ids", []):
            raise FeishuV2Error("PRIVATE_CARD_MESSAGE_MISMATCH", 403)
        case = self.visible_case(data["case_id"], identity)
        if data["kind"] == "CONFIRM" and row["state"] == "DONE":
            return self.summary(db, link, case), case["id"], case["revision"]
        if data["expires"] <= self.now():
            raise FeishuV2Error("PRIVATE_CARD_EXPIRED", 409)
        if data["kind"] == "SELECT":
            if case["revision"] != data["revision"]:
                raise FeishuV2Error("REVISION_CONFLICT", 409)
            return (
                self.summary(db, link, case, intent=data.get("intent", "summary")),
                case["id"],
                case["revision"],
            )
        if identity["role"] != "MERCHANT":
            raise FeishuV2Error("MERCHANT_AUTHORIZATION_REQUIRED", 403)
        action = data.get("action", "MERCHANT_DECISION")
        if action not in {"MERCHANT_DECISION", "SUBMIT_EVIDENCE"}:
            raise FeishuV2Error("PRIVATE_CARD_REQUIRED", 403)
        if data["kind"] == "PREPARE":
            if case["revision"] != data["revision"]:
                raise FeishuV2Error("REVISION_CONFLICT", 409)
            gate = self.disputes.action_gate(case, action, identity)
            if not gate["enabled"] or (
                action == "MERCHANT_DECISION" and data["decision"] not in gate.get("choices", [])
            ):
                raise FeishuV2Error("PRIVATE_ACTION_BLOCKED", 409)
            if row["state"] == "PREPARED":
                return data["confirmation_card"], case["id"], case["revision"]
            decision = data["decision"]
            label = (
                "提交材料给 OceanPayment"
                if action == "SUBMIT_EVIDENCE"
                else "接受拒付"
                if decision == "ACCEPT"
                else "发起抗辩"
            )
            button = self.token_button(
                db,
                link,
                case,
                "CONFIRM",
                "确认" + label,
                decision,
                action=action,
            )
            card = self.card(
                f"请再次确认案件 {case['id']}：{label}。\n"
                + (
                    "将锁定当前材料进入 OceanPayment 人工审核，不提交银行、不代表胜诉或结案。"
                    if action == "SUBMIT_EVIDENCE"
                    else "将进入接受处理流程。"
                    if decision == "ACCEPT"
                    else "将开始准备抗辩材料，不代表银行已撤销拒付。"
                )
                + "\n确认有效期 5 分钟；未确认不改变案件。",
                [button],
            )
            self.put(
                db, "card", ref, link["account"], "PREPARED", data | {"confirmation_card": card}
            )
            return card, case["id"], case["revision"]
        if data["kind"] != "CONFIRM":
            raise FeishuV2Error("PRIVATE_CARD_REQUIRED", 403)
        # Stable command ID closes the crash window after a business commit but
        # before the separate private-channel transaction commits. execute checks
        # current access and its atomic receipt before applying the revision gate.
        result = self.disputes.execute(
            {
                "command_id": data["command_id"],
                "case_id": case["id"],
                "expected_revision": data["revision"],
                "action": action,
                "confirmed": True,
                "data": (
                    {
                        "decision": data["decision"],
                        "reason": "商户通过绑定的飞书私聊二次确认。",
                    }
                    if action == "MERCHANT_DECISION"
                    else {}
                ),
            },
            identity,
        )
        self.put(db, "card", ref, link["account"], "DONE", data)
        case = self.disputes.get_case(result["case"]["id"], identity)
        return self.summary(db, link, case), case["id"], case["revision"]

    def observe(self):
        """Recover notifications from committed aggregate/audit revisions, not an ephemeral hook."""
        with self.db() as db:
            links = db.execute("SELECT * FROM fp_links WHERE active=1").fetchall()
        for link in links:
            try:
                identity = self.identity(link["account"])
                # Merchant notices only; staff keep existing website responsibilities.
                if identity["role"] != "MERCHANT":
                    continue
                cases = self.disputes.list_cases(identity)
                address = self.unseal(link["version"], link["address"])
                with self.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    if not self.link(db, version=link["version"]):
                        continue
                    for case in cases:
                        if self.record(db, "retired", case["id"])[0]:
                            continue
                        ref = binding_key(
                            "private-notice",
                            link["version"],
                            case["id"] + ":" + str(case["revision"]),
                        )
                        if self.record(db, "job", ref)[0]:
                            continue
                        self.enqueue(
                            db,
                            ref,
                            address,
                            self.summary(db, link, case),
                            link=link,
                            case_id=case["id"],
                            revision=case["revision"],
                            business_event={
                                key: case.get("audit", [{}])[-1].get(key)
                                for key in ("command_id", "action", "revision")
                            },
                        )
            except Exception:
                continue

    def validate_delivery(self, db, data):
        """Check every dependency, including list/confirmation cards, at send time."""
        if not data["version"]:
            return  # Unbound pairing/help replies contain no case information.
        link = self.link(db, version=data["version"])
        if not link:
            raise FeishuV2Error("BINDING_REVOKED", 403)
        identity = self.identity(link["account"])
        if data["case_id"]:
            case = self.visible_case(data["case_id"], identity)
            if case["revision"] != data["revision"]:
                raise FeishuV2Error("STALE_NOTICE", 409)
        # A case-selection job has no single case_id. Its buttons still disclose
        # case identifiers/status, so each target needs the same fresh check.
        for element in data["card"]["elements"]:
            for button in element.get("actions", []):
                token = button.get("value", {}).get("private_ref")
                if not token:
                    continue
                row, capability = self.record(db, "card", token)
                if (
                    not row
                    or row["owner"] != link["account"]
                    or capability["version"] != link["version"]
                    or row["state"] == "REVOKED"
                    or capability["expires"] <= self.now()
                ):
                    raise FeishuV2Error("STALE_NOTICE", 409)
                target = self.visible_case(capability["case_id"], identity)
                if target["revision"] != capability["revision"]:
                    raise FeishuV2Error("STALE_NOTICE", 409)

    def drain(self):
        if self.client is None:
            return
        with self.db() as db:
            db.execute(
                "UPDATE fp_records SET state='UNCERTAIN' "
                "WHERE kind='job' AND state='SENDING' AND updated<?",
                (self.now() - 120,),
            )
            rows = db.execute(
                "SELECT ref FROM fp_records WHERE kind='job' AND state='PENDING' "
                "ORDER BY updated LIMIT 10"
            ).fetchall()
        for item in rows:
            ref = item["ref"]
            with self.db() as db:
                db.execute("BEGIN IMMEDIATE")
                row, data = self.record(db, "job", ref)
                if row["state"] != "PENDING":
                    continue
                try:
                    self.validate_delivery(db, data)
                    self.put(db, "job", ref, row["owner"], "SENDING", data)
                except Exception:
                    self.put(db, "job", ref, row["owner"], "BLOCKED", data)
                    continue
            attempted = False
            try:
                data["card"] = focused_card(data["card"], data.get("intent", "summary"), self.model)
                # Model latency is outside the transaction. Revalidate access
                # and the case version immediately before the external send.
                with self.db() as db:
                    self.validate_delivery(db, data)
                attempted = True
                if data["parent"]:
                    receipt = self.client.reply_interactive_card(
                        message_id=data["parent"],
                        card=data["card"],
                        idempotency_key=ref,
                        reply_in_thread=False,
                    )
                else:
                    receipt = self.client.send_interactive_card(
                        receive_id=data["address"]["chat"],
                        receive_id_type=FeishuReceiveIdType.CHAT_ID,
                        card=data["card"],
                        idempotency_key=ref,
                    )
                checked(receipt.message_id)
                state = "SENT"
                data["receipt"] = receipt.message_id
            except FeishuV2Error:
                state = "UNCERTAIN" if attempted else "BLOCKED"
            except Exception:
                state = "UNCERTAIN" if attempted else "BLOCKED"
            with self.db() as db:
                db.execute("BEGIN IMMEDIATE")
                if state == "SENT":
                    for element in data["card"]["elements"]:
                        for button in element.get("actions", []):
                            token = button.get("value", {}).get("private_ref")
                            if token:
                                card_row, card_data = self.record(db, "card", token)
                                if card_row and card_row["state"] != "REVOKED":
                                    card_data["message_ids"] = list(
                                        set(card_data.get("message_ids", []) + [receipt.message_id])
                                    )
                                    self.put(
                                        db,
                                        "card",
                                        token,
                                        card_row["owner"],
                                        card_row["state"],
                                        card_data,
                                    )
                self.put(db, "job", ref, row["owner"], state, data)

    def start(self):
        if self.client is not None and self.thread is None:
            self.thread = threading.Thread(
                target=self.run, daemon=True, name="feishu-private-cases"
            )
            self.thread.start()

    def run(self):
        while not self.stop.is_set():
            with suppress(Exception):
                self.observe()
                self.drain()
            self.stop.wait(2)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
