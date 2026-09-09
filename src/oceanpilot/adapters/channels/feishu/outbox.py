"""Durable, explicitly authorized test-chat delivery. Never enabled by API input."""

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass, field

from oceanpilot.adapters.channels.feishu.v2 import FeishuV2Error, binding_key
from oceanpilot.adapters.feishu.client import FeishuReceiveIdType

_OPERATORS = {"OPERATOR", "RISK_OFFICER", "SUPERVISOR"}


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _identity(value):
    return {key: value.get(key) for key in ("role", "actor_id", "merchant_id")}


@dataclass(frozen=True)
class TestChatTarget:
    __test__ = False
    target_ref: str
    merchant_id: str
    authorization_reference: str
    label: str
    tenant_key: str = field(repr=False)
    chat_id: str = field(repr=False)
    allow_callback_replies: bool = False


def load_test_targets(raw, bindings):
    """Only deployment-owned configuration authorizes destinations, never JSON APIs."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        rows = data["targets"]
        if not isinstance(rows, list):
            raise ValueError
        targets = {}
        for row in rows:
            if row.get("authorized") is not True:
                raise ValueError
            for key in ("tenant_key", "chat_id", "merchant_id", "authorization_reference"):
                if not isinstance(row.get(key), str) or not 0 < len(row[key]) <= 200:
                    raise ValueError
            allow = row.get("allow_callback_replies", False)
            if type(allow) is not bool:
                raise ValueError
            ref = binding_key("chat", row["tenant_key"], row["chat_id"])
            if ref in targets or bindings.chats.get(ref) != row["merchant_id"]:
                raise ValueError
            targets[ref] = TestChatTarget(
                target_ref=ref,
                tenant_key=row["tenant_key"],
                chat_id=row["chat_id"],
                merchant_id=row["merchant_id"],
                authorization_reference=row["authorization_reference"],
                label=str(row.get("label", "已授权测试群"))[:100],
                allow_callback_replies=allow,
            )
        return targets
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("invalid authorized Feishu test targets") from None


class FeishuDisputeOutbox:
    def __init__(self, adapter, *, targets=None, client=None, now=time.time):
        self.adapter, self.store = adapter, adapter.store
        self.targets, self.client = targets or {}, client
        self.now = now
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        with self.store._connection() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS v21_feishu_outbox (
                    outbox_id TEXT PRIMARY KEY, command_id TEXT UNIQUE NOT NULL,
                    fingerprint TEXT NOT NULL, case_id TEXT NOT NULL, target_ref TEXT NOT NULL,
                    state TEXT NOT NULL, auto_send INTEGER NOT NULL,
                    message_id TEXT, updated_at REAL NOT NULL, snapshot TEXT NOT NULL
                )"""
            )

    @property
    def enabled(self):
        return self.client is not None and bool(self.targets)

    def _target(self, ref, case):
        target = self.targets.get(ref)
        if (
            target is None
            or target.merchant_id != case.get("merchant_id")
            or self.adapter.bindings.chats.get(ref) != target.merchant_id
        ):
            raise FeishuV2Error("FEISHU_TEST_TARGET_NOT_AUTHORIZED", 403)
        return target

    def _read(self, outbox_id):
        with self.store._connection() as db:
            row = db.execute(
                "SELECT snapshot FROM v21_feishu_outbox WHERE outbox_id = ?", (outbox_id,)
            ).fetchone()
        if row is None:
            raise FeishuV2Error("FEISHU_OUTBOX_NOT_FOUND", 404)
        return json.loads(row["snapshot"])

    @staticmethod
    def _public(row):
        return {key: value for key, value in row.items() if key not in {"identity", "reply_to"}}

    def _save(self, db, row):
        row["updated_at"] = self.now()
        db.execute(
            """UPDATE v21_feishu_outbox SET state=?, message_id=?, updated_at=?, snapshot=?
                WHERE outbox_id=?""",
            (row["state"], row.get("message_id"), row["updated_at"], _json(row), row["id"]),
        )

    def list_for_case(self, case_id, identity):
        case = self.adapter.service.get_case(case_id, identity)
        if identity["role"] not in _OPERATORS:
            raise FeishuV2Error("FORBIDDEN", 403)
        with self.store._connection() as db:
            rows = db.execute(
                "SELECT snapshot FROM v21_feishu_outbox WHERE case_id=? "
                "ORDER BY rowid DESC LIMIT 100",
                (case_id,),
            ).fetchall()
        return {
            "case_id": case_id,
            "enabled": self.enabled,
            "targets": [
                {
                    "target_ref": t.target_ref,
                    "label": t.label,
                    "callback_replies": t.allow_callback_replies,
                }
                for t in self.targets.values()
                if t.merchant_id == case["merchant_id"]
            ],
            "items": [self._public(json.loads(row["snapshot"])) for row in rows],
        }

    def preview(self, *, command_id, case_id, identity, target_ref, kind="NEW_DISPUTE"):
        if identity["role"] not in _OPERATORS:
            raise FeishuV2Error("FORBIDDEN", 403)
        return self._queue(command_id, case_id, identity, target_ref, kind, "SEND", None, False)

    def _queue(
        self, command_id, case_id, identity, target_ref, kind, operation, reply_to, automatic
    ):
        case = self.adapter.service.get_case(case_id, identity)
        target = self._target(target_ref, case)
        if not isinstance(command_id, str) or not 8 <= len(command_id) <= 200:
            raise FeishuV2Error("INVALID_COMMAND_ID", 422)
        fingerprint = hashlib.sha256(
            _json(
                [command_id, case_id, _identity(identity), target_ref, kind, operation, reply_to]
            ).encode()
        ).hexdigest()
        # Check immutable command ownership before rendering. INSERT OR IGNORE below also
        # serializes concurrent previews; all callers return the one persisted card.
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT fingerprint,snapshot FROM v21_feishu_outbox WHERE command_id=?",
                (command_id,),
            ).fetchone()
            if prior:
                if prior["fingerprint"] != fingerprint:
                    raise FeishuV2Error("IDEMPOTENCY_CONFLICT", 409)
                return {**self._public(json.loads(prior["snapshot"])), "replayed": True}
        # Rendering writes the opaque card binding using its own connection.
        card = self.adapter.render_case_card(
            case_id, identity, tenant_key=target.tenant_key, chat_id=target.chat_id, kind=kind
        )
        auto_send = automatic and target.allow_callback_replies and self.enabled
        row = {
            "id": "fout-" + uuid.uuid4().hex,
            "command_id": command_id,
            "case_id": case_id,
            "case_revision": case["revision"],
            "target_ref": target_ref,
            "authorization_reference": target.authorization_reference,
            "identity": _identity(identity),
            "operation": operation,
            "reply_to": reply_to,
            "kind": kind,
            "card": card,
            "state": "PENDING" if auto_send else "PREVIEW",
            "auto_send": bool(auto_send),
            "delivery_status": "NOT_SENT",
            "attempts": 0,
            "message_id": None,
            "idempotency_key": str(uuid.uuid4()),
            "created_at": self.now(),
            "updated_at": self.now(),
        }
        with self.store._connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO v21_feishu_outbox VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
                (
                    row["id"],
                    command_id,
                    fingerprint,
                    case_id,
                    target_ref,
                    row["state"],
                    int(auto_send),
                    row["updated_at"],
                    _json(row),
                ),
            )
            saved = db.execute(
                "SELECT fingerprint,snapshot FROM v21_feishu_outbox WHERE command_id=?",
                (command_id,),
            ).fetchone()
            if saved["fingerprint"] != fingerprint:
                raise FeishuV2Error("IDEMPOTENCY_CONFLICT", 409)
            row = json.loads(saved["snapshot"])
        if auto_send:
            self._wake.set()
        return {**self._public(row), "replayed": False}

    def message_case(self, message_id, target_ref):
        with self.store._connection() as db:
            row = db.execute(
                "SELECT case_id FROM v21_feishu_outbox WHERE message_id=? AND target_ref=? LIMIT 1",
                (message_id, target_ref),
            ).fetchone()
        return row["case_id"] if row else None

    def callback(self, *, event_ref, case_id, identity, target_ref, message_id=None, update=False):
        case = self.adapter.service.get_case(case_id, identity)
        self._target(target_ref, case)
        if not isinstance(message_id, str) or not message_id:
            return {"state": "NOT_QUEUED", "reason": "NO_VERIFIED_MESSAGE_ID"}
        if update and self.message_case(message_id, target_ref) != case_id:
            return {"state": "NOT_QUEUED", "reason": "MESSAGE_NOT_DELIVERED_BY_THIS_OUTBOX"}
        return self._queue(
            "callback-" + event_ref,
            case_id,
            identity,
            target_ref,
            "SUMMARY",
            "UPDATE" if update else "REPLY",
            message_id,
            True,
        )

    def send(self, outbox_id, identity, *, confirmed=False, automatic=False):
        row = self._read(outbox_id)
        case = self.adapter.service.get_case(row["case_id"], identity)
        target = self._target(row["target_ref"], case)
        if automatic:
            if (
                not row["auto_send"]
                or not target.allow_callback_replies
                or _identity(identity) != row["identity"]
            ):
                raise FeishuV2Error("FEISHU_AUTOMATIC_SEND_NOT_AUTHORIZED", 403)
        elif identity["role"] not in _OPERATORS or confirmed is not True:
            raise FeishuV2Error("FEISHU_SEND_CONFIRMATION_REQUIRED", 403)
        if row["state"] == "SENT":
            return {**self._public(row), "replayed": True}
        if not self.enabled:
            raise FeishuV2Error("FEISHU_OUTBOUND_DISABLED", 503)
        if row["operation"] == "UPDATE" and row["case_revision"] != case["revision"]:
            # PATCH has no provider UUID: retrying an old patch must never overwrite
            # a newer case card, even when the old network response was lost.
            raise FeishuV2Error("FEISHU_PREVIEW_STALE", 409)
        # Never silently refresh a reviewed card. After a lost receipt, its immutable UUID/content
        # must instead be retried as-is; changing business version cannot mint a second delivery.
        if row["state"] not in {"UNCERTAIN", "SENDING"} and (
            row["case_revision"] != case["revision"] or self.now() - row["created_at"] >= 3600
        ):
            raise FeishuV2Error("FEISHU_PREVIEW_STALE", 409)
        with self.store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT snapshot FROM v21_feishu_outbox WHERE outbox_id=?", (outbox_id,)
            ).fetchone()
            row = json.loads(current["snapshot"])
            if row["state"] == "SENT":
                return {**self._public(row), "replayed": True}
            if row["state"] == "SENDING" and self.now() - row["updated_at"] < 60:
                raise FeishuV2Error("FEISHU_SEND_IN_PROGRESS", 409)
            row.update(
                state="SENDING", attempts=row["attempts"] + 1, delivery_status="PENDING_RECEIPT"
            )
            row.setdefault("attempt_history", []).append(
                {
                    "attempt": row["attempts"],
                    "started_at": self.now(),
                    "actor_id": identity["actor_id"],
                }
            )
            self._save(db, row)
        try:
            common = {"card": row["card"], "idempotency_key": row["idempotency_key"]}
            if row["operation"] == "SEND":
                receipt = self.client.send_interactive_card(
                    receive_id=target.chat_id, receive_id_type=FeishuReceiveIdType.CHAT_ID, **common
                )
            elif row["operation"] == "REPLY":
                receipt = self.client.reply_interactive_card(message_id=row["reply_to"], **common)
            else:
                receipt = self.client.update_interactive_card(message_id=row["reply_to"], **common)
            if not receipt.message_id:
                raise ValueError("missing receipt")
        except Exception:
            row.update(
                state="UNCERTAIN",
                delivery_status="UNCONFIRMED",
                error_code="FEISHU_SEND_UNCONFIRMED",
            )
        else:
            row.update(
                state="SENT", delivery_status="DELIVERED_TO_FEISHU", message_id=receipt.message_id
            )
            row.pop("error_code", None)
        with self.store._connection() as db:
            row["attempt_history"][-1].update(
                completed_at=self.now(), state=row["state"], message_id=row.get("message_id")
            )
            self._save(db, row)
        return {**self._public(row), "replayed": False}

    def drain(self):
        """Only initially pending, locally authorized callback deliveries. No blind retry loop."""
        if not self.enabled:
            return []
        with self.store._connection() as db:
            rows = db.execute(
                "SELECT snapshot FROM v21_feishu_outbox WHERE auto_send=1 AND state='PENDING' "
                "ORDER BY rowid LIMIT 20"
            ).fetchall()
        results = []
        for raw in rows:
            row = json.loads(raw["snapshot"])
            try:
                results.append(self.send(row["id"], row["identity"], automatic=True))
            except Exception:
                # Permission revocation/stale case must fail closed and remain inspectable.
                with self.store._connection() as db:
                    fresh = db.execute(
                        "SELECT snapshot FROM v21_feishu_outbox WHERE outbox_id=?", (row["id"],)
                    ).fetchone()
                    row = json.loads(fresh["snapshot"])
                    if row["state"] == "PENDING":
                        row.update(
                            state="BLOCKED",
                            delivery_status="NOT_SENT",
                            error_code="FEISHU_DELIVERY_BLOCKED",
                        )
                        self._save(db, row)
        return results

    def start(self):
        if self.enabled and self._thread is None:
            self._thread = threading.Thread(target=self._run, name="v21-feishu-outbox", daemon=True)
            self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            self.drain()
            self._wake.wait(5)
            self._wake.clear()

    def close(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
