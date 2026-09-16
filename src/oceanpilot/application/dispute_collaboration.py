"""Case-shared work, private OP notes and content-backed synthetic evidence.

Chat/read/handoff/timer events use an independent journal. Only evidence changes
enter the business command engine, preserving its approval and CAS invariants.
"""

import base64
import binascii
import json
import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import PurePath
from threading import Event, Thread
from uuid import uuid4

from oceanpilot.application.evidence_documents import (
    DOCUMENT_TYPES,
    MAX_BASE64_CHARS,
    STRUCTURED_TYPES,
    read_document,
    validate_file,
)
from oceanpilot.domain.dispute import DisputeError, fingerprint, require, text_field, timestamp
from oceanpilot.domain.dispute_rules import case_plan
from oceanpilot.domain.evidence_catalog import EVIDENCE_CONTENT_FIELDS

SCOPES = {"SHARED", "OP_INTERNAL"}
_INTERNAL_ROLES = {"OPERATOR", "SUPERVISOR", "AGENT"}
_SYSTEM = {"role": "AGENT", "actor_id": "oceanpilot-workflow-agent"}
_FILE_TYPES = STRUCTURED_TYPES
_FACTS = EVIDENCE_CONTENT_FIELDS


class DisputeCollaborationService:
    def __init__(self, store, disputes, agent=None, *, clock=None):
        self.store = store
        self.disputes = disputes
        self.agent = agent
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self):
        return self.clock().astimezone(UTC).isoformat()

    def _access(self, case_id, identity, scope="SHARED"):
        identity = self.disputes._identity(identity)
        case = self.disputes.get_case(case_id, identity)
        require(scope in SCOPES, "INVALID_SCOPE", "Choose SHARED or OP_INTERNAL", 422)
        require(
            identity["role"] in _INTERNAL_ROLES | {"MERCHANT"},
            "FORBIDDEN",
            "This identity cannot participate in a case thread",
            403,
        )
        require(
            scope != "OP_INTERNAL" or identity["role"] in _INTERNAL_ROLES,
            "NOT_FOUND",
            "Case thread not found",
            404,
        )
        return case, identity

    def participants(self, case):
        policy = getattr(self.disputes, "access_policy", None)
        if policy is not None and hasattr(policy, "case_participants"):
            return policy.case_participants(case)
        values = [dict(p) for p in case.get("participants", []) if isinstance(p, dict)]
        assigned = case.get("assigned_op_user_id")
        if assigned and not any(p.get("user_id") == assigned for p in values):
            values.append({"user_id": assigned, "role": "OPERATOR", "display_name": assigned})
        return values

    def activity(self, case_id, identity, scope="SHARED", after=0):
        case, identity = self._access(case_id, identity, scope)
        require(type(after) is int and after >= 0, "INVALID_CURSOR", "Invalid cursor", 422)
        events = self.store.events(case_id, scope, after=after)
        maximum = self.store.cursor(case_id, scope)
        cursor = events[-1]["cursor"] if events else maximum
        active_ids = {e.get("object_id") for e in case["evidence"] if e.get("active")}
        files = [o for o in self.store.objects(case_id) if o["id"] in active_ids]
        return {
            "case_id": case_id,
            "case_revision": case["revision"],
            "scope": scope,
            "cursor": cursor,
            "latest_cursor": maximum,
            "has_more": cursor < maximum,
            "messages": [e for e in events if e["kind"] in {"MESSAGE", "REMINDER"}],
            "handoffs": self.store.handoffs(case_id, scope),
            "files": files,
            "read_cursor": self.store.read_cursor(case_id, scope, identity["actor_id"]),
            "participants": self.participants(case),
            "read_receipts": self.store.read_receipts(case_id, scope),
            "reader_notice": (
                "本案商户、获授权 OceanPayment 人员和 OceanPilot 共同可见。"
                if scope == "SHARED"
                else "仅获授权 OceanPayment 人员可见。"
            ),
        }

    def observe_business(self, case, action):
        """Bridge already-public case notices into the same journal, once per source event.

        Legacy private Agent conversations are deliberately not consulted.
        """
        self.disputes.get_case(case["id"], _SYSTEM)
        notices = [
            dict(item)
            for item in case.get("collaboration", [])
            if item.get("type")
            in {"MESSAGE", "TASK_PUBLISHED", "MERCHANT_DECISION", "MERCHANT_NOTIFICATION"}
        ]
        for review in case.get("reviews", []):
            if review.get("decision") in {
                "REVISION",
                "ACCEPT",
                "RECOMMEND_ACCEPT",
                "RETURN_MATERIALS",
            }:
                notices.append(
                    {
                        "id": review["id"],
                        "type": "PUBLIC_REVIEW_FEEDBACK",
                        "role": review.get("role", "RISK_OFFICER"),
                        "actor_id": review.get("reviewer", ""),
                        "message": "审核反馈：" + review["reason"],
                        "at": review.get("at") or review.get("created_at"),
                    }
                )
        for item in notices:
            actor = {"actor_id": item["actor_id"], "role": item["role"]}
            event = self._event(
                case["id"],
                actor,
                "SHARED",
                "MESSAGE",
                message=item["message"],
                source="HUMAN" if item["role"] != "AGENT" else "DETERMINISTIC",
                source_event_id=item["id"],
                source_event_type=item["type"],
                delivery_status="AVAILABLE_IN_PORTAL",
                case_revision=case["revision"],
            )
            event["created_at"] = item.get("at") or event["created_at"]
            self._write(
                "case-notice-" + item["id"],
                _SYSTEM,
                {"case_id": case["id"], "source_event_id": item["id"], "message": item["message"]},
                lambda db, e=event: {"message": self.store.append(db, e)},
            )

    def _event(self, case_id, identity, scope, kind, **data):
        return {
            "id": str(uuid4()),
            "case_id": case_id,
            "scope": scope,
            "kind": kind,
            "actor_id": identity["actor_id"],
            "actor_role": identity["role"],
            "actor_type": (
                "MERCHANT"
                if identity["role"] == "MERCHANT"
                else "OCEANPILOT"
                if identity["role"] == "AGENT"
                else "OCEANPAYMENT"
            ),
            "created_at": self._now(),
            **data,
        }

    def _write(self, command_id, identity, payload, mutate):
        command_id = text_field({"command_id": command_id}, "command_id", limit=200)
        return self.store.execute(command_id, fingerprint([identity, payload]), mutate)

    def post_message(
        self,
        case_id,
        identity,
        command_id,
        message,
        scope="SHARED",
        ask_agent=False,
        *,
        metadata=None,
    ):
        case, identity = self._access(case_id, identity, scope)
        message = text_field({"message": message}, "message", limit=6000)
        self.disputes._screen_values({"message": message})
        require(type(ask_agent) is bool, "INVALID_INPUT", "ask_agent must be boolean", 422)
        metadata = metadata or {}
        require(
            set(metadata) <= {"channel", "external_event_id", "thread_id"},
            "INVALID_INPUT",
            "Unsupported message metadata",
            422,
        )
        self.disputes._screen_values(metadata)
        event = self._event(
            case_id,
            identity,
            scope,
            "MESSAGE",
            message=message,
            source="HUMAN",
            delivery_status="AVAILABLE_IN_PORTAL",
            case_revision=case["revision"],
            **metadata,
        )
        payload = {"case_id": case_id, "scope": scope, "message": message, "ask_agent": ask_agent}
        if metadata:
            payload["metadata"] = metadata
        result = self._write(
            command_id, identity, payload, lambda db: {"message": self.store.append(db, event)}
        )
        result["case_revision"] = case["revision"]
        result["scope"] = scope
        if ask_agent:
            if result["replayed"]:
                result["agent_status"] = "ALREADY_REQUESTED"
            else:
                result.update(
                    self.ask_agent(
                        case_id, identity, message, scope, parent_id=result["message"]["id"]
                    )
                )
        return result

    def ask_agent(
        self,
        case_id,
        identity,
        message,
        scope="SHARED",
        *,
        parent_id=None,
        trigger="SHARED_MESSAGE",
    ):
        case, identity = self._access(case_id, identity, scope)
        require(self.agent is not None, "AGENT_UNAVAILABLE", "Agent is unavailable", 503)
        try:
            answer = self.agent.converse(
                case_id, identity, message, case["revision"], audience=scope, trigger=trigger
            )
            reply = self.publish_agent_answer(case_id, answer, scope, parent_id=parent_id)
            if case["rule_snapshot"].get("conflict_status") != "VERIFIED":
                self.create_handoff(
                    case_id,
                    identity,
                    "agent-handoff-" + reply["id"],
                    "规则或权利尚待人工确认，请本案负责人接手。",
                    scope,
                )
            return {
                "agent_status": "COMPLETED",
                "agent_reply": reply,
                "provider": answer["provider"],
                "source": answer["source"],
                "model": answer["model"],
            }
        except DisputeError as exc:
            if exc.code != "REVISION_CONFLICT":
                raise
            return {"agent_status": "CASE_CHANGED", "message_preserved": True}

    def publish_agent_answer(self, case_id, answer, scope, *, parent_id=None):
        self._access(case_id, _SYSTEM, scope)
        event = self._event(
            case_id,
            _SYSTEM,
            scope,
            "MESSAGE",
            message=answer["answer"],
            parent_id=parent_id,
            source=answer["source"],
            provider=answer["provider"],
            model=answer["model"],
            source_citations=answer.get("source_citations", []),
            conversation_id=answer["conversation_id"],
            case_revision=answer["run"]["case_revision"],
            delivery_status="AVAILABLE_IN_PORTAL",
        )
        return self._write(
            "agent-reply-" + answer["conversation_id"],
            _SYSTEM,
            {"case_id": case_id, "scope": scope, "answer": answer["answer"]},
            lambda db: {"message": self.store.append(db, event)},
        )["message"]

    def mark_read(self, case_id, identity, scope, cursor):
        _, identity = self._access(case_id, identity, scope)
        require(type(cursor) is int and cursor >= 0, "INVALID_CURSOR", "Invalid read cursor", 422)
        value = self.store.mark_read(case_id, scope, identity["actor_id"], cursor)
        return {"scope": scope, "read_cursor": value}

    def create_handoff(
        self,
        case_id,
        identity,
        command_id,
        reason,
        scope="SHARED",
        assignee_id=None,
        follow_up_at=None,
    ):
        case, identity = self._access(case_id, identity, scope)
        reason = text_field({"reason": reason}, "reason", limit=2000)
        self.disputes._screen_values({"reason": reason})
        assignee = assignee_id or case.get("assigned_op_user_id")
        people = self.participants(case)
        require(
            assignee is None
            or any(
                p.get("user_id") == assignee and p.get("role") in _INTERNAL_ROLES for p in people
            ),
            "ASSIGNEE_FORBIDDEN",
            "Assignee must be an authorized case participant",
            403,
        )
        follow = timestamp(follow_up_at) if follow_up_at else self.clock() + timedelta(hours=4)
        event = self._event(
            case_id,
            identity,
            scope,
            "HANDOFF",
            reason=reason,
            status="OPEN",
            assignee_id=assignee,
            follow_up_at=follow.isoformat(),
            claimed_at=None,
            resolved_at=None,
            resolution=None,
        )

        def mutate(db):
            existing = next(
                (
                    h
                    for h in self.store.handoffs(case_id, scope, db)
                    if h["status"] != "RESOLVED" and h["reason"] == reason
                ),
                None,
            )
            return {"handoff": existing or self.store.append(db, event)}

        return self._write(
            command_id,
            identity,
            {
                "case_id": case_id,
                "scope": scope,
                "reason": reason,
                "assignee_id": assignee,
                "follow_up_at": follow_up_at,
            },
            mutate,
        )

    def update_handoff(
        self, case_id, identity, handoff_id, command_id, action, reason, follow_up_at=None
    ):
        case, identity = self._access(case_id, identity)
        require(
            identity["role"] in _INTERNAL_ROLES - {"AGENT"},
            "FORBIDDEN",
            "An authorized OP participant must handle the handoff",
            403,
        )
        require(action in {"CLAIM", "RESOLVE"}, "INVALID_ACTION", "Choose CLAIM or RESOLVE", 422)
        reason = text_field({"reason": reason}, "reason", limit=2000)
        self.disputes._screen_values({"reason": reason})
        follow = timestamp(follow_up_at).isoformat() if follow_up_at else None

        def mutate(db):
            matches = [
                h
                for scope in SCOPES
                for h in self.store.handoffs(case_id, scope, db)
                if h["id"] == handoff_id
            ]
            require(bool(matches), "NOT_FOUND", "Handoff not found", 404)
            current = matches[0]
            require(current["status"] != "RESOLVED", "HANDOFF_RESOLVED", "Handoff is resolved")
            require(
                current.get("assignee_id") in {None, identity["actor_id"]}
                or identity["role"] == "SUPERVISOR",
                "ASSIGNEE_FORBIDDEN",
                "Only the assignee or supervisor may handle this handoff",
                403,
            )
            if action == "RESOLVE":
                require(current["status"] == "CLAIMED", "CLAIM_REQUIRED", "Claim before resolving")
            event = current | {
                "status": "CLAIMED" if action == "CLAIM" else "RESOLVED",
                "actor_id": identity["actor_id"],
                "actor_role": identity["role"],
                "assignee_id": identity["actor_id"],
                "updated_at": self._now(),
                "update_reason": reason,
            }
            if action == "CLAIM":
                event.update(claimed_at=self._now(), follow_up_at=follow or current["follow_up_at"])
            else:
                event.update(resolved_at=self._now(), resolution=reason)
            event.pop("cursor", None)
            return {"handoff": self.store.append(db, event)}

        return self._write(
            command_id,
            identity,
            {
                "case_id": case["id"],
                "handoff_id": handoff_id,
                "action": action,
                "reason": reason,
                "follow_up_at": follow_up_at,
            },
            mutate,
        )

    @staticmethod
    def _parse_file(filename, mime_type, content):
        suffix = PurePath(filename).suffix.lower()
        require(
            suffix in _FILE_TYPES and _FILE_TYPES[suffix] == mime_type,
            "UNSUPPORTED_FILE_TYPE",
            "Use UTF-8 .txt, .json or .csv synthetic documents",
            415,
        )
        validate_file(filename, mime_type, content)
        try:
            text = content.decode("utf-8-sig")
        except UnicodeError as exc:
            raise DisputeError("UNREADABLE_FILE", "Upload readable UTF-8 text", 422) from exc
        require(
            bool(text.strip()) and "\x00" not in text,
            "EMPTY_FILE",
            "File has no readable text",
            422,
        )
        require(
            not re.search(r"<\s*(?:!doctype|html|script|iframe|svg)\b", text, re.I),
            "UNSUPPORTED_FILE_TYPE",
            "HTML and executable markup are not accepted",
            415,
        )
        values = {}
        if suffix == ".json":
            try:
                values = json.loads(text)
            except (ValueError, RecursionError) as exc:
                raise DisputeError("INVALID_FILE", "JSON document cannot be parsed", 422) from exc
            require(
                isinstance(values, dict), "INVALID_FILE", "JSON document must be an object", 422
            )
            values = {
                **values,
                **(values.get("facts", {}) if isinstance(values.get("facts"), dict) else {}),
            }
        elif suffix == ".csv":
            import csv
            import io

            try:
                rows = list(csv.DictReader(io.StringIO(text)))
            except csv.Error as exc:
                raise DisputeError("INVALID_FILE", "CSV document cannot be parsed", 422) from exc
            require(len(rows) == 1, "INVALID_FILE", "Use one synthetic transaction per CSV", 422)
            values = rows[0]
        else:
            for line in text.splitlines():
                match = re.match(r"^([a-z_]+)\s*[:=]\s*(.+)$", line.strip())
                if match:
                    values[match[1]] = match[2]
        values.pop("facts", None)
        require(
            len(values) <= 100
            and all(
                isinstance(value, (str, int, float, bool)) or value is None
                for value in values.values()
            ),
            "INVALID_FILE",
            "Use scalar synthetic document facts",
            422,
        )
        require(
            all(not isinstance(value, str) or len(value) <= 20000 for value in values.values()),
            "INVALID_FILE",
            "A document fact is too long",
            422,
        )
        return text, values

    @staticmethod
    def _assess(case, code, text, values):
        findings = []
        required = _FACTS.get(code)
        known_type = required is not None
        required = required or ()
        if str(values.get("transaction_id", "")) != case["transaction_id"]:
            findings.append("材料交易编号缺失或与本案不一致。")
        if values.get("currency") != case["currency"]:
            findings.append("材料币种缺失或与本案不一致。")
        raw_amount = values.get("amount_minor")
        amount = (
            int(raw_amount)
            if type(raw_amount) is int
            or (
                isinstance(raw_amount, str)
                and len(raw_amount) <= 15
                and re.fullmatch(r"[0-9]+", raw_amount)
            )
            else None
        )
        if amount != case["amount_minor"]:
            findings.append("材料争议交易金额缺失或与本案不一致。")
        for field in required:
            if not values.get(field):
                name = {
                    "delivered_at": "送达时间",
                    "recipient": "签收人",
                    "tracking_number": "物流单号",
                }.get(field, field)
                findings.append(f"缺少{name}；未提供支持当前证据要求的事实：{field}。")
        if str(values.get("status", "")).lower() in {"not_delivered", "cancelled", "disputed"}:
            findings.append("材料记录了未送达、已取消或存在争议，须人工解释矛盾。")
        locators = [
            f"line:{i}"
            for i, line in enumerate(text.splitlines(), 1)
            if any(field in line for field in ("transaction_id", *required))
        ][:20]
        return {
            "status": "INSUFFICIENT" if findings else "SUPPORTED" if known_type else "NEEDS_MANUAL",
            "findings": findings
            or ([] if known_type else ["本证据类型尚无内容检查合同，请人工核查。"]),
            "locators": locators or ["line:1"],
            "facts": {
                field: values.get(field)
                for field in ("transaction_id", "currency", "amount_minor", *required)
            },
            "method": "SYNTHETIC_STRUCTURED_CONTENT_CHECK_V1",
            "boundary": "已检查内容字段及本案关联，不代表文件真实性或人工审核通过。",
        }

    def sample_file(self, case_id, code, variant, identity):
        """Build an explicitly synthetic file that must still use the real upload path."""
        case, _ = self._access(case_id, identity)
        require(
            case.get("channel") == "MOCK"
            and case.get("rule_snapshot", {}).get("production_eligible") is False,
            "NOT_FOUND",
            "Synthetic material sample not found",
            404,
        )
        require(
            code in case.get("rule_snapshot", {}).get("required_evidence", []),
            "NOT_FOUND",
            "Evidence sample not found for this case",
            404,
        )
        required = _FACTS.get(code)
        require(required is not None, "NOT_FOUND", "No structured sample for this evidence", 404)
        example_values = {
            "ordered_at": "2026-09-01T08:00:00Z",
            "item_description": "Synthetic test order item",
            "tracking_number": "SYNTHETIC-TRACKING-001",
            "shipped_at": "2026-09-02T08:00:00Z",
            "delivered_at": "2026-09-04T10:30:00Z",
            "recipient_confirmation": "Synthetic recipient confirmation",
            "address_match_result": "SYNTHETIC_MATCH",
            "communicated_at": "2026-09-05T09:00:00Z",
            "customer_message": "Synthetic customer message for workflow testing",
            "merchant_reply": "Synthetic merchant response for workflow testing",
            "refunded_at": "2026-09-06T09:00:00Z",
            "refund_amount_minor": case["amount_minor"],
            "policy_text": "Synthetic refund policy accepted for workflow testing",
            "accepted_at": "2026-09-01T07:59:00Z",
            "cancellation_status": "SYNTHETIC_NOT_CANCELLED",
            "requested_at": "2026-09-05T12:00:00Z",
            "prior_transaction_count": 2,
            "comparison_result": "SYNTHETIC_NOT_DUPLICATE",
            "verification_result": "SYNTHETIC_MATCH",
            "authentication_result": "SYNTHETIC_AUTHENTICATED",
            "device_match_result": "SYNTHETIC_MATCH",
        }
        values = {
            "notice": "测试材料 / 合成数据；仅用于 OceanPilot 本地演练",
            "evidence_code": code,
            "transaction_id": case["transaction_id"],
            "currency": case["currency"],
            "amount_minor": case["amount_minor"],
            **{field: example_values[field] for field in required},
        }
        if variant == "missing_field":
            values.pop(required[0] if required else "currency")
        elif variant == "wrong_transaction":
            values["transaction_id"] = "synthetic-unrelated-transaction"
        filename = f"synthetic-{code.replace('.', '-')}-{variant}.json"
        return {
            "filename": filename,
            "mime_type": "application/json",
            "content": json.dumps(values, ensure_ascii=False, indent=2).encode(),
        }

    def upload_file(
        self,
        case_id,
        identity,
        *,
        command_id,
        expected_revision,
        code,
        title,
        filename,
        mime_type,
        content_base64,
        evidence_id=None,
    ):
        case, identity = self._access(case_id, identity)
        require(
            identity["role"] in {"MERCHANT", "OPERATOR", "SUPERVISOR"},
            "FORBIDDEN",
            "Cannot upload evidence",
            403,
        )
        filename = text_field({"filename": filename}, "filename", limit=180)
        require(
            "/" not in filename and "\\" not in filename,
            "INVALID_FILENAME",
            "Invalid filename",
            422,
        )
        code = text_field({"code": code}, "code", limit=100)
        title = text_field({"title": title}, "title", limit=180)
        require(
            isinstance(content_base64, str) and len(content_base64) <= MAX_BASE64_CHARS,
            "INVALID_FILE_SIZE",
            "File exceeds upload limit",
            422,
        )
        try:
            content = base64.b64decode(content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise DisputeError("INVALID_FILE", "Invalid file encoding", 422) from exc
        validate_file(filename, mime_type, content)
        digest = sha256(content).hexdigest()
        payload = {
            "case_id": case_id,
            "sha256": digest,
            "filename": filename,
            "code": code,
            "title": title,
            "expected_revision": expected_revision,
            "evidence_id": evidence_id,
            "mime_type": mime_type,
        }
        receipt = self.store.replay("file-store-" + command_id, fingerprint([identity, payload]))
        document_file = PurePath(filename).suffix.lower() in DOCUMENT_TYPES
        if receipt:
            obj = receipt["object"]
        else:
            document = None
            if document_file:
                extracted = read_document(
                    filename,
                    content,
                    code,
                    model=getattr(self.agent, "model", None),
                    synthetic=case.get("channel") == "MOCK"
                    and case.get("rule_snapshot", {}).get("production_eligible") is False,
                )
                text, values = extracted["text"], extracted["facts"]
                document = extracted["document"]
                assessment = self._assess(case, code, text, values)
                assessment.update(
                    extraction_check_status=assessment["status"],
                    status="NEEDS_MANUAL",
                    method="DOCUMENT_EXTRACTION_V1",
                    recognition=extracted["recognition"],
                    document=document,
                    boundary="AI/正文识别仅供核对；请独立人工检查原件、交易关联和事实，不代表真实性、授权或审核通过。",
                )
                assessment["findings"] = [
                    extracted["recognition"]["notice"],
                    *assessment["findings"],
                ]
            else:
                text, values = self._parse_file(filename, mime_type, content)
                assessment = self._assess(case, code, text, values)
            self.disputes._screen_values({"filename": filename, "title": title, "values": values})
            self.disputes._screen_values({"file_text": text})
            token = uuid4().hex
            object_id = "obj-" + "g".join(token[i : i + 8] for i in range(0, 32, 8))
            obj = {
                "id": object_id,
                "object_id": object_id,
                "case_id": case_id,
                "scope": "SHARED",
                "filename": filename,
                "mime_type": mime_type,
                "size": len(content),
                "sha256": digest,
                "uploaded_by": identity["actor_id"],
                "created_at": self._now(),
                "code": code,
                "content_check": assessment,
                "extracted_text": text[:40000],
                "source_type": "UPLOADED_DOCUMENT" if document else "SYNTHETIC_DEMO",
            }
        # An explicit replacement of the same original is a recognition retry.
        # It still creates a new evidence revision and invalidates prior approvals.
        active_objects = {
            e.get("object_id")
            for e in case["evidence"]
            if e.get("active") and not (document_file and evidence_id and e["id"] == evidence_id)
        }
        duplicates = [
            o
            for o in self.store.objects(case_id)
            if o["sha256"] == digest and o["id"] in active_objects
        ]
        object_id = obj["id"]

        def save(db):
            db.execute(
                "INSERT INTO v21_evidence_objects VALUES (?,?,?,?)",
                (object_id, case_id, json.dumps(obj, ensure_ascii=False), content),
            )
            return {"object": obj}

        stored = self._write("file-store-" + command_id, identity, payload, save)["object"]
        if duplicates and duplicates[0]["id"] != stored["id"]:
            raise DisputeError(
                "DUPLICATE_FILE", "This content is already registered; reuse its record"
            )
        result = self.disputes.execute(
            {
                "command_id": command_id,
                "case_id": case_id,
                "action": "REGISTER_EVIDENCE",
                "expected_revision": expected_revision,
                "confirmed": True,
                "data": {
                    "code": code,
                    "title": title,
                    "reference": "object:" + stored["id"],
                    "source_channel": "PORTAL",
                    "notes": "原文件已保存；识别与内容检查不替代人工审核。",
                    **({"evidence_id": evidence_id} if evidence_id else {}),
                },
            },
            identity,
        )
        return {**result, "file": stored}

    def get_evidence_object(self, case_id, object_id):
        obj = self.store.get_object(object_id)
        require(
            obj is not None and obj["case_id"] == case_id,
            "EVIDENCE_OBJECT_NOT_FOUND",
            "Evidence object not found",
            404,
        )
        return obj

    def download_file(self, case_id, object_id, identity):
        case, identity = self._access(case_id, identity)
        obj = self.get_evidence_object(case_id, object_id)
        require(
            any(
                (
                    e.get("object_id") == object_id
                    or any(
                        h.get("object_id") == object_id
                        and (
                            identity["role"] != "MERCHANT"
                            or h.get("visibility", "SHARED") == "SHARED"
                        )
                        for h in e.get("history", [])
                    )
                )
                for e in case["evidence"]
                if identity["role"] != "MERCHANT" or e.get("visibility", "SHARED") == "SHARED"
            ),
            "NOT_FOUND",
            "Evidence object is not registered on this case",
            404,
        )
        return obj | {"content": self.store.get_object(object_id, include_content=True)["content"]}

    def context(self, case_id, identity, scope):
        case, _ = self._access(case_id, identity, scope)
        events = self.store.events(
            case_id, scope, after=max(0, self.store.cursor(case_id, scope) - 200)
        )
        messages = [
            {k: e.get(k) for k in ("id", "actor_type", "message", "created_at", "source")}
            for e in events
            if e["kind"] in {"MESSAGE", "REMINDER"}
        ][-16:]
        if scope == "OP_INTERNAL":
            messages = self.context(case_id, identity, "SHARED")["messages"] + messages
        active = {e.get("object_id") for e in case["evidence"] if e.get("active")}
        evidence = [
            {
                "object_id": o["id"],
                "code": o["code"],
                "sha256": o["sha256"],
                "content_check": o["content_check"],
                "excerpt": o["extracted_text"][:4000],
            }
            for o in self.store.objects(case_id)
            if o["id"] in active
        ]
        return {
            "scope": scope,
            "messages": messages,
            "evidence_content": evidence,
            "handoffs": [
                {k: h.get(k) for k in ("id", "reason", "status", "follow_up_at")}
                for h in self.store.handoffs(case_id, scope)
            ],
        }

    def open_handoffs(self, case_id):
        return [
            h
            for scope in SCOPES
            for h in self.store.handoffs(case_id, scope)
            if h["status"] != "RESOLVED"
        ]

    def tick(self):
        """An injected clock can advance deadlines without changing business revisions."""
        emitted = []
        now = self.clock().astimezone(UTC)
        for case in self.disputes.list_cases(_SYSTEM):
            if case["work_status"] == "CLOSED":
                continue
            for thread_scope in SCOPES:
                for handoff in self.store.handoffs(case["id"], thread_scope):
                    if (
                        handoff["status"] == "RESOLVED"
                        or timestamp(handoff["follow_up_at"]) > now
                        or handoff.get("escalation_level", 0) >= 1
                    ):
                        continue
                    key = fingerprint([handoff["id"], handoff["follow_up_at"], "ESCALATE"])
                    event = handoff | {
                        "escalation_level": 1,
                        "escalated_at": self._now(),
                        "update_reason": "跟进目标已到期，请风控经理协调接手。",
                    }
                    event.pop("cursor", None)
                    self._write(
                        "handoff-escalate-" + key,
                        _SYSTEM,
                        {"key": key},
                        lambda db, e=event: {"handoff": self.store.append(db, e)},
                    )
            sla = case_plan(case, now=now)["sla"]
            deadline_type = sla["deadline_kind"]
            deadline = sla["deadline"]
            reminder_band = sla["reminder_band"]
            if not deadline_type or not deadline or not reminder_band:
                continue
            scope = "SHARED" if deadline_type == "merchant" else "OP_INTERNAL"
            key = fingerprint(
                [
                    case["id"],
                    sla["stage_number"],
                    deadline_type,
                    reminder_band,
                    sla["task_ids"],
                ]
            )
            overdue = reminder_band == "DUE"
            subject = {
                "merchant": "商户当前任务",
                "internal": "OceanPayment 当前审核任务",
                "external": "上游跟进任务",
            }[deadline_type]
            message = (
                f"{subject}已超过当前记录的期限，请人工核实剩余权利并安排跟进；"
                "逾期不代表接受争议或正式失权。"
                if overdue
                else f"{subject}进入 {reminder_band} 提醒档位，请责任人按当前任务跟进。"
            )
            event = self._event(
                case["id"],
                _SYSTEM,
                scope,
                "REMINDER",
                actor_type="SYSTEM",
                message=message,
                deadline_type=deadline_type,
                deadline=deadline,
                reminder_band=reminder_band,
                escalation_level=1 if overdue else 0,
                task_ids=sla["task_ids"],
                task_types=sla["task_types"],
                owner=sla["owner"],
                assignee_id=sla["assignee_ids"][0] if sla["assignee_ids"] else None,
                assignee_ids=sla["assignee_ids"],
                source="TIME_TICK",
                case_revision=case["revision"],
                boundary=sla["boundary"],
            )
            result = self._write(
                "deadline-" + key,
                _SYSTEM,
                {
                    "case_id": case["id"],
                    "stage_number": sla["stage_number"],
                    "deadline_type": deadline_type,
                    "reminder_band": reminder_band,
                    "task_ids": sla["task_ids"],
                },
                lambda db, e=event: {"event": self.store.append(db, e)},
            )
            if not result["replayed"]:
                emitted.append(result["event"])
            if deadline_type in {"merchant", "external"} and overdue:
                self.create_handoff(
                    case["id"],
                    _SYSTEM,
                    "deadline-handoff-" + key,
                    (
                        "商户任务已逾期，请运营核实未响应原因、剩余权利并安排跟进。"
                        if deadline_type == "merchant"
                        else "外部期限已到，请人工核实剩余权利及后续处理。"
                    ),
                    "OP_INTERNAL",
                    assignee_id=(
                        case.get("assigned_op_user_id")
                        if deadline_type == "merchant"
                        else sla["assignee_ids"][0]
                        if sla["assignee_ids"]
                        else None
                    ),
                )
        return {"observed_at": self._now(), "emitted": emitted}


class DisputeCollaborationScheduler:
    def __init__(self, service, interval=30):
        self.service, self.interval = service, interval
        self._stop = Event()
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = Thread(target=self._run, name="v21-deadline-monitor", daemon=True)
            self._thread.start()

    def _run(self):
        import logging

        while not self._stop.wait(self.interval):
            try:
                self.service.tick()
            except Exception:
                logging.getLogger(__name__).warning("V2.1 deadline scan unavailable")

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
