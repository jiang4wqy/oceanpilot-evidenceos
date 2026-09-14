"""Signed public-group questions with durable, explicitly authorized replies.

This adapter has no business-service reference. Old card clicks are rejected.
"""

import hashlib
import json
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager, suppress

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from oceanpilot.adapters.channels.feishu.public_knowledge import knowledge_card, public_text
from oceanpilot.adapters.channels.feishu.v2 import FeishuV2Error, binding_key


def load_public_groups(raw):
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("groups"), list):
        raise ValueError("invalid public group manifest")
    groups = {}
    for item in data["groups"]:
        if not isinstance(item, dict):
            raise ValueError("invalid public group")
        if item.get("authorized") is not True or item.get("allow_replies") is not True:
            raise ValueError("group reply authorization required")
        for field in ("tenant_key", "chat_id", "authorization_reference"):
            if not isinstance(item.get(field), str) or not 0 < len(item[field]) <= 200:
                raise ValueError("invalid public group")
        ref = binding_key("chat", item["tenant_key"], item["chat_id"])
        if ref in groups:
            raise ValueError("duplicate public group")
        groups[ref] = dict(item)
    return groups


class KnowledgeBot:
    def __init__(
        self,
        db_path,
        knowledge,
        *,
        groups,
        secret,
        app_id,
        base_url,
        client=None,
        approval_revision=None,
        now=time.time,
    ):
        self.db_path, self.knowledge = db_path, knowledge
        self.groups, self.app_id, self.base_url = groups, app_id, base_url
        self.client, self.now = client, now
        self.approval_revision = approval_revision or (lambda: knowledge.revision)
        self._cipher = AESGCM(
            hashlib.sha256(b"public-knowledge-queue-v1" + secret.encode()).digest()
        )
        self._stop, self._wake = threading.Event(), threading.Event()
        self._thread = None
        # Validate the neutral entry without invoking any business service.
        knowledge_card({"text": "", "mode": "HELP", "sources": []}, base_url)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS feishu_public_questions (
                event_ref TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, group_ref TEXT NOT NULL,
                approval_ref TEXT NOT NULL, corpus_revision TEXT NOT NULL, state TEXT NOT NULL,
                encrypted_request BLOB NOT NULL, card TEXT, answer_mode TEXT,
                receipt TEXT, updated_at REAL NOT NULL)""")

    @contextmanager
    def _db(self):
        with sqlite3.connect(self.db_path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            yield db

    @property
    def enabled(self):
        return self.client is not None and bool(self.groups)

    def _allowed(self, row):
        group = self.groups.get(row["group_ref"])
        return (
            group is not None
            and group.get("authorized") is True
            and group.get("allow_replies") is True
            and group["authorization_reference"] == row["approval_ref"]
            and row["corpus_revision"] == self.approval_revision()
        )

    def _seal(self, event_ref, data):
        nonce = secrets.token_bytes(12)
        return nonce + self._cipher.encrypt(nonce, json.dumps(data).encode(), event_ref.encode())

    def _open(self, row):
        raw = row["encrypted_request"]
        return json.loads(self._cipher.decrypt(raw[:12], raw[12:], row["event_ref"].encode()))

    def handle(self, payload, *, mode):
        if mode == "card":
            raise FeishuV2Error("FEISHU_BUSINESS_ACTIONS_DISABLED", 403)
        header, event = payload.get("header", {}), payload.get("event", {})
        if not isinstance(header, dict) or not isinstance(event, dict):
            raise FeishuV2Error("INVALID_CALLBACK")
        if header.get("app_id") != self.app_id or not self.app_id:
            raise FeishuV2Error("UNTRUSTED_APPLICATION", 403)
        if header.get("event_type") != "im.message.receive_v1":
            return {"code": 0, "outcome": "IGNORED"}
        sender, message = event.get("sender", {}), event.get("message", {})
        if not isinstance(sender, dict) or not isinstance(message, dict):
            raise FeishuV2Error("INVALID_CALLBACK")
        if sender.get("sender_type") != "user":
            return {"code": 0, "outcome": "IGNORED"}
        tenant, chat, event_id = (
            header.get("tenant_key"),
            message.get("chat_id"),
            header.get("event_id"),
        )
        if not all(
            isinstance(value, str) and 0 < len(value) <= 200 for value in (tenant, chat, event_id)
        ):
            raise FeishuV2Error("INVALID_CALLBACK")
        group_ref = binding_key("chat", tenant, chat)
        group = self.groups.get(group_ref)
        if not group:
            raise FeishuV2Error("PUBLIC_GROUP_NOT_AUTHORIZED", 403)
        if message.get("chat_type") not in {"group", "p2p"}:
            raise FeishuV2Error("INVALID_CALLBACK")
        if message.get("message_type") == "text":
            import re

            content = json.loads(message.get("content", "{}"))
            if not isinstance(content, dict):
                raise FeishuV2Error("INVALID_CALLBACK")
            question = content.get("text", "")
            if not isinstance(question, str) or not 0 < len(question) <= 4000:
                raise FeishuV2Error("INVALID_CALLBACK")
            mention = re.match(r"^\s*(?:@OceanPilot|@_user_\d+)\s*", question)
            if message["chat_type"] == "group" and mention is None:
                return {"code": 0, "outcome": "IGNORED"}
            if mention:
                question = question[mention.end() :].strip()
            try:
                public_text(question)
            except ValueError:
                # Do not even persist rejected question text in the encrypted queue.
                question = "具体案件"
        else:
            # No attachment is downloaded, parsed, stored or forwarded to a model.
            question = "具体案件"
        message_id = message.get("message_id")
        if not isinstance(message_id, str) or not 0 < len(message_id) <= 128:
            raise FeishuV2Error("INVALID_CALLBACK")
        ref = binding_key("public-event", tenant, event_id)
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT * FROM feishu_public_questions WHERE event_ref=?", (ref,)
            ).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise FeishuV2Error("EVENT_PAYLOAD_CONFLICT", 409)
                if not self._allowed(old):
                    raise FeishuV2Error("PUBLIC_GROUP_OR_KNOWLEDGE_REVOKED", 403)
                return {"code": 0, "outcome": "REPLAYED", "delivery": old["state"]}
            pending = db.execute(
                "SELECT count(*) FROM feishu_public_questions WHERE group_ref=? "
                "AND state IN ('PENDING','PREPARING','SENDING')",
                (group_ref,),
            ).fetchone()[0]
            if pending >= 20:
                raise FeishuV2Error("PUBLIC_GROUP_QUEUE_FULL", 429)
            db.execute(
                "INSERT INTO feishu_public_questions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ref,
                    fingerprint,
                    group_ref,
                    group["authorization_reference"],
                    self.knowledge.revision,
                    "PENDING" if self.enabled else "DISABLED",
                    self._seal(ref, {"question": question, "message_id": message_id}),
                    None,
                    None,
                    None,
                    self.now(),
                ),
            )
        self._wake.set()
        return {"code": 0, "outcome": "QUEUED" if self.enabled else "OUTBOUND_DISABLED"}

    def _state(self, ref, state, **fields):
        permitted = {"card", "answer_mode", "receipt"}
        assert set(fields) <= permitted
        with self._db() as db:
            columns = ["state=?", "updated_at=?"] + [f"{key}=?" for key in fields]
            db.execute(
                "UPDATE feishu_public_questions SET " + ",".join(columns) + " WHERE event_ref=?",
                [state, self.now(), *fields.values(), ref],
            )

    def drain(self):
        if not self.enabled:
            return
        with self._db() as db:
            # Do not steal expired work: a slow original worker may still exist.
            # A crashed preparation blocks; an in-flight send remains uncertain.
            db.execute(
                "UPDATE feishu_public_questions SET state='UNCERTAIN' WHERE state='SENDING' "
                "AND updated_at<?",
                (self.now() - 120,),
            )
            db.execute(
                "UPDATE feishu_public_questions SET state='BLOCKED' WHERE state='PREPARING' "
                "AND updated_at<?",
                (self.now() - 120,),
            )
            rows = db.execute(
                "SELECT * FROM feishu_public_questions WHERE state='PENDING' "
                "ORDER BY rowid LIMIT 10"
            ).fetchall()
        for row in rows:
            ref = row["event_ref"]
            with self._db() as db:
                claim = db.execute(
                    "UPDATE feishu_public_questions SET state='PREPARING', updated_at=? "
                    "WHERE event_ref=? AND state='PENDING'",
                    (self.now(), ref),
                )
                if claim.rowcount != 1:
                    continue
            try:
                if not self._allowed(row):
                    self._state(ref, "BLOCKED")
                    continue
                request = self._open(row)
                answer = self.knowledge.answer(request["question"])
                card = knowledge_card(answer, self.base_url)
                if not self._allowed(row):
                    self._state(ref, "BLOCKED")
                    continue
                with self._db() as db:
                    transition = db.execute(
                        "UPDATE feishu_public_questions SET state='SENDING',updated_at=?,"
                        "card=?,answer_mode=? WHERE event_ref=? AND state='PREPARING'",
                        (self.now(), json.dumps(card, ensure_ascii=False), answer["mode"], ref),
                    )
                    if transition.rowcount != 1:
                        continue
            except Exception:
                self._state(ref, "BLOCKED")
                continue
            try:
                receipt = self.client.reply_interactive_card(
                    message_id=request["message_id"],
                    card=card,
                    idempotency_key=ref,
                    reply_in_thread=False,
                )
                if not isinstance(receipt.message_id, str) or not receipt.message_id:
                    raise ValueError("missing provider receipt")
                self._state(ref, "SENT", receipt=receipt.message_id)
            except Exception:
                self._state(ref, "UNCERTAIN")

    def start(self):
        if self.enabled and self._thread is None:
            self._thread = threading.Thread(
                target=self._run, name="feishu-public-knowledge", daemon=True
            )
            self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            with suppress(Exception):
                self.drain()
            self._wake.wait(2)
            self._wake.clear()

    def close(self):
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=2)
