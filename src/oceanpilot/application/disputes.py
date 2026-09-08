"""OceanPayment-owned dispute command service.

Commands are deterministic business operations. Agents may prepare drafts and
monitor, while distinct humans review evidence, approve packages and reconcile.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from oceanpilot.application.dispute_ports import DisputeStore
from oceanpilot.domain.dispute import (
    ACTION_ROLES,
    LOW_RISK_ACTIONS,
    ROLES,
    BusinessOutcome,
    CaseStage,
    DisputeError,
    MerchantDecision,
    close_blockers,
    currency_code,
    fingerprint,
    minor_units,
    missing_evidence,
    redact_knowledge,
    require,
    text_field,
    timestamp,
)
from oceanpilot.domain.dispute_rules import case_plan, match_rule
from oceanpilot.domain.errors import SensitiveDataRejected
from oceanpilot.domain.security import assert_no_sensitive_data

__all__ = ["DisputeService", "DisputeError"]


class DisputeService:
    def __init__(
        self,
        store: DisputeStore,
        *,
        rule_matcher=None,
        planner=None,
        clock=None,
        upstream_mode: str = "mock",
    ) -> None:
        require(
            upstream_mode in {"mock", "disabled"},
            "INVALID_UPSTREAM_MODE",
            "Only mock or disabled upstream is supported",
            422,
        )
        self.store = store
        self.rule_matcher = rule_matcher or match_rule
        self.planner = planner or case_plan
        self.clock = clock or (lambda: datetime.now(UTC))
        self.upstream_mode = upstream_mode

    @staticmethod
    def _identity(identity: dict) -> dict:
        require(isinstance(identity, dict), "UNAUTHORIZED", "Identity is required", 401)
        role = identity.get("role")
        require(isinstance(role, str) and role in ROLES, "FORBIDDEN", "Unknown role", 403)
        actor = text_field(identity, "actor_id", limit=200)
        merchant = identity.get("merchant_id")
        if role == "MERCHANT":
            merchant = text_field(identity, "merchant_id", limit=200)
        else:
            require(
                merchant is None or isinstance(merchant, str),
                "INVALID_INPUT",
                "merchant_id must be text",
                422,
            )
        result = {"role": role, "actor_id": actor, "merchant_id": merchant}
        DisputeService._screen_values(result)
        return result

    def list_cases(self, identity: dict) -> list[dict]:
        identity = self._identity(identity)
        return self.store.list_cases(
            identity["merchant_id"] if identity["role"] == "MERCHANT" else None,
        )

    def get_case(self, case_id: str, identity: dict) -> dict:
        identity = self._identity(identity)
        require(isinstance(case_id, str), "INVALID_INPUT", "case_id must be text", 422)
        case = self.store.get_case(case_id)
        require(case is not None, "NOT_FOUND", "Case not found", 404)
        if identity["role"] == "MERCHANT":
            require(
                case["merchant_id"] == identity["merchant_id"], "NOT_FOUND", "Case not found", 404
            )
        return case

    def execute(self, command: dict, identity: dict) -> dict:
        identity = self._identity(identity)
        require(isinstance(command, dict), "INVALID_INPUT", "Command must be an object", 422)
        fingerprint(command)
        command = deepcopy(command)
        action = text_field(command, "action", limit=80)
        require(action in ACTION_ROLES, "UNKNOWN_ACTION", "Unknown command action", 422)
        require(
            identity["role"] in ACTION_ROLES[action],
            "FORBIDDEN",
            f"Role {identity['role']} cannot execute {action}",
            403,
        )
        command_id = text_field(command, "command_id", limit=200)
        require(
            action in LOW_RISK_ACTIONS or command.get("confirmed") is True,
            "CONFIRMATION_REQUIRED",
            "An authorized human must confirm this command",
        )
        require(
            isinstance(command.get("data", {}), dict),
            "INVALID_INPUT",
            "Command data must be an object",
            422,
        )
        command["data"] = command.get("data", {})
        if action == "INTAKE":
            command["case_id"] = command.get("case_id") or f"OPV2-{fingerprint(command_id)[:16]}"
        else:
            require(
                type(command.get("expected_revision")) is int and command["expected_revision"] >= 1,
                "REVISION_REQUIRED",
                "Current expected_revision is required",
                422,
            )
        command["case_id"] = text_field(command, "case_id", limit=200)
        self._screen_values({"command_id": command_id, "case_id": command["case_id"]})
        fingerprint(command)
        event_key, event_digest, upstream_case_key = None, None, None
        if action in {"INTAKE", "RECORD_OUTCOME", "NEXT_STAGE", "RECORD_FINANCIAL"}:
            event_id = text_field(command["data"], "event_id", limit=200)
            source = (
                text_field(command["data"], "channel", limit=200)
                if action == "INTAKE"
                else text_field(command["data"], "source", limit=200)
            )
            event_key = fingerprint([action, source, event_id])
            event_digest = fingerprint(command["data"])
            if action == "INTAKE":
                upstream_case_id = text_field(
                    command["data"], "upstream_case_id", default=event_id, limit=200
                )
                upstream_case_key = fingerprint([source.upper(), upstream_case_id])
        return self.store.execute_atomic(
            command=command,
            identity=identity,
            mutate=lambda case: self._apply(case, command, identity),
            event_key=event_key,
            event_fingerprint=event_digest,
            upstream_case_key=upstream_case_key,
        )

    def _apply(self, case: dict | None, command: dict, identity: dict) -> dict:
        now = self.clock().astimezone(UTC).isoformat()
        action, data = command["action"], command["data"]
        scanned_data = data
        if action == "KNOWLEDGE_CANDIDATE":
            scanned_data = {
                key: redact_knowledge(value, case) if isinstance(value, str) else value
                for key, value in data.items()
            }
        self._screen_values(scanned_data)
        if action == "INTAKE":
            case = self._intake(command, identity, now, existing=case)
        else:
            require(
                case["work_status"] != "CLOSED"
                or action
                in {
                    "COMMENT",
                    "KNOWLEDGE_CANDIDATE",
                    "APPROVE_KNOWLEDGE",
                },
                "CASE_CLOSED",
                "Closed business records cannot be changed",
            )
            getattr(self, f"_on_{action.lower()}")(case, data, identity, now)
        case["updated_at"] = now
        case["audit"].append(
            {
                "id": uuid4().hex,
                "command_id": command["command_id"],
                "action": action,
                "revision": case["revision"] + 1,
                "actor_id": identity["actor_id"],
                "role": identity["role"],
                "confirmed": command.get("confirmed") is True,
                "at": now,
                "data_digest": fingerprint(data),
                "reason": data.get("reason") if isinstance(data.get("reason"), str) else None,
            }
        )
        return case

    @staticmethod
    def _screen_values(data):
        # Scan values, since legitimate authorization_reference metadata is not a credential.
        values = []

        identifiers = {
            "command_id",
            "case_id",
            "actor_id",
            "merchant_id",
            "event_id",
            "upstream_case_id",
            "transaction_id",
            "evidence_id",
            "package_id",
            "candidate_id",
            "external_event_id",
            "thread_id",
        }

        def visit(value, field=None):
            if isinstance(value, dict):
                for key, child in value.items():
                    visit(child, key)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
            elif isinstance(value, str):
                if field in identifiers:
                    try:
                        parsed = UUID(value)
                        if parsed.version == 4 and value.lower() in {parsed.hex, str(parsed)}:
                            return
                    except ValueError:
                        pass
                if (
                    field in {"external_event_id", "thread_id"}
                    and len(value) == 64
                    and all(char in "0123456789abcdef" for char in value)
                ):
                    return
                values.append(value)

        visit(data)
        try:
            assert_no_sensitive_data(values)
        except SensitiveDataRejected as exc:
            raise DisputeError(
                "SENSITIVE_DATA_REJECTED",
                "Remove payment card data and credentials before saving",
                422,
            ) from exc

    def _intake(self, command: dict, identity: dict, now: str, existing=None) -> dict:
        data = command["data"]
        merchant_id = text_field(data, "merchant_id", limit=200)
        amount = minor_units(data.get("amount_minor"))
        require(amount > 0, "INVALID_AMOUNT", "Disputed amount must be positive", 422)
        scheme = text_field(data, "scheme", limit=40).upper()
        channel = text_field(data, "channel", limit=100).upper()
        reason = text_field(data, "reason_code", limit=100)
        received_at = data.get("received_at", now)
        timestamp(received_at)
        rule = self.rule_matcher(scheme, channel, reason, "FORMAL_DISPUTE", received_at)
        transaction_id = text_field(data, "transaction_id", limit=200)
        currency = currency_code(data.get("currency"))
        if existing is not None:
            expected = {
                "merchant_id": merchant_id,
                "transaction_id": transaction_id,
                "scheme": scheme,
                "channel": channel,
                "reason_code": reason,
                "amount_minor": amount,
                "currency": currency,
            }
            require(
                all(existing[key] == value for key, value in expected.items()),
                "UPSTREAM_CASE_CONFLICT",
                "Upstream case notification conflicts with its existing transaction or merchant",
            )
            existing["upstream_events"].append(
                {
                    "id": data["event_id"],
                    "type": "DUPLICATE_NOTIFICATION",
                    "source": channel,
                    "at": received_at,
                    "actor_id": identity["actor_id"],
                }
            )
            return existing
        case = {
            "id": command["case_id"],
            "revision": 0,
            "merchant_id": merchant_id,
            "owner": "OCEANPAYMENT",
            "transaction_id": transaction_id,
            "upstream_case_id": data.get("upstream_case_id", data["event_id"]),
            "scheme": scheme,
            "channel": channel,
            "reason_code": reason,
            "amount_minor": amount,
            "currency": currency,
            "stage": "FORMAL_DISPUTE",
            "stage_number": 1,
            "work_status": "RECEIVED",
            "stage_history": [],
            "merchant_decision": "NONE",
            "business_outcome": "UNKNOWN",
            "finality": "NOT_FINAL",
            "financial_status": "PENDING",
            "rule_snapshot": deepcopy(rule),
            "deadlines": deepcopy(rule.get("deadlines", {})),
            "tasks": [],
            "evidence": [],
            "reviews": [],
            "packages": [],
            "submissions": [],
            "upstream_events": [
                {
                    "id": data["event_id"],
                    "type": "INTAKE",
                    "source": channel,
                    "at": received_at,
                    "actor_id": identity["actor_id"],
                }
            ],
            "financial_events": [],
            "collaboration": [],
            "audit": [],
            "knowledge_candidates": [],
            "evidence_version": 0,
            "financial_version": 0,
            "merchant_notification_completed": False,
            "pending_next_stage": False,
            "source_type": "SYNTHETIC_DEMO",
            "production_eligible": False,
            "created_at": now,
            "updated_at": now,
            "received_at": received_at,
        }
        if rule.get("conflict_status") == "VERIFIED":
            case["work_status"] = "TRIAGED"
        return case

    @staticmethod
    def _rule_ready(case: dict) -> None:
        require(
            case["rule_snapshot"].get("conflict_status") == "VERIFIED",
            "RULE_CONFIRMATION_REQUIRED",
            "Unknown or conflicting rule requires Risk confirmation",
        )
        require(
            case["deadlines"].get("status") == "CONFIRMED",
            "DEADLINE_CONFIRMATION_REQUIRED",
            "An explicit source and confirmed deadline are required",
        )
        require(
            not case.get("pending_next_stage"),
            "NEXT_STAGE_REQUIRED",
            "Create the next stage before continuing",
        )

    @staticmethod
    def _complete_tasks(case: dict, now: str, types: set[str] | None = None) -> None:
        for task in case["tasks"]:
            if task["status"] == "OPEN" and (types is None or task["type"] in types):
                task.update(status="COMPLETED", completed_at=now)

    @staticmethod
    def _task(case: dict, kind: str, message: str, now: str) -> None:
        if not any(t["type"] == kind and t["status"] == "OPEN" for t in case["tasks"]):
            case["tasks"].append(
                {
                    "id": uuid4().hex,
                    "type": kind,
                    "status": "OPEN",
                    "required": True,
                    "message": message,
                    "created_at": now,
                    "stage_number": case["stage_number"],
                }
            )

    @staticmethod
    def _collaboration(
        case: dict, data: dict, identity: dict, now: str, message: str, kind: str = "MESSAGE"
    ) -> None:
        channel = text_field(data, "channel", default="PORTAL", limit=30).upper()
        for key in ("external_event_id", "thread_id"):
            if data.get(key) is not None:
                text_field(data, key, limit=500)
        require(
            channel in {"PORTAL", "FEISHU", "EMAIL", "WEBHOOK"},
            "INVALID_CHANNEL",
            "Unsupported collaboration channel",
            422,
        )
        case["collaboration"].append(
            {
                "id": uuid4().hex,
                "case_id": case["id"],
                "type": kind,
                "channel": channel,
                "actor_id": identity["actor_id"],
                "role": identity["role"],
                "message": message,
                "at": now,
                "external_event_id": data.get("external_event_id"),
                "thread_id": data.get("thread_id"),
                "read_status": "UNREAD",
            }
        )

    def _on_confirm_rule(self, case, data, identity, now):
        require(
            case["work_status"]
            in {
                "RECEIVED",
                "TRIAGED",
                "MERCHANT_ACTION_REQUIRED",
                "EVIDENCE_COLLECTING",
                "MERCHANT_REVISION_REQUIRED",
                "OP_REVIEW",
            },
            "INVALID_STATE",
            "Rules cannot be replaced after package approval or submission",
        )
        source = text_field(data, "source_id", limit=200)
        locator = text_field(data, "source_locator", limit=1000)
        version = text_field(data, "rule_version", limit=200)
        reason = text_field(data, "reason")
        external = timestamp(data.get("external_deadline"))
        internal = timestamp(data.get("internal_deadline", data.get("external_deadline")))
        merchant = timestamp(
            data.get(
                "merchant_deadline", data.get("internal_deadline", data.get("external_deadline"))
            )
        )
        require(
            merchant <= internal <= external,
            "INVALID_DEADLINES",
            "Deadlines must follow merchant <= internal <= external",
            422,
        )
        required = data.get("required_evidence", case["rule_snapshot"].get("required_evidence", []))
        require(
            isinstance(required, list)
            and bool(required)
            and all(isinstance(code, str) and 0 < len(code) <= 100 for code in required),
            "INVALID_EVIDENCE_RULE",
            "Explicit required_evidence codes are required",
            422,
        )
        allowed = data.get("allowed_actions")
        require(
            isinstance(allowed, list)
            and bool(allowed)
            and all(
                isinstance(action, str) and action in {"ACCEPT", "CONTEST"} for action in allowed
            ),
            "ACTION_CONFIRMATION_REQUIRED",
            "Explicit allowed_actions must confirm ACCEPT and/or CONTEST",
            422,
        )
        case["rule_snapshot"].update(
            {
                "source_id": source,
                "source_locator": locator,
                "rule_version": version,
                "conflict_status": "VERIFIED",
                "production_eligible": False,
                "source_type": "HUMAN_CONFIRMED_DEMO",
                "required_evidence": sorted(set(required)),
                "critical_evidence": sorted(set(required)),
                "allowed_actions": sorted(set(allowed)),
                "confirmed_by": identity["actor_id"],
                "confirmed_at": now,
                "confirmation_reason": reason,
            }
        )
        case["deadlines"] = {
            "merchant": merchant.isoformat(),
            "internal": internal.isoformat(),
            "external": external.isoformat(),
            "status": "CONFIRMED",
            "source": source,
        }
        case["rule_snapshot"]["deadlines"] = deepcopy(case["deadlines"])
        self._invalidate(case, "Rule source or deadline changed", now)
        if case["merchant_decision"] == "NONE":
            case["work_status"] = "TRIAGED"

    def _on_publish_task(self, case, data, identity, now):
        self._rule_ready(case)
        require(
            case["work_status"]
            in {
                "TRIAGED",
                "RECEIVED",
                "MERCHANT_ACTION_REQUIRED",
                "EVIDENCE_COLLECTING",
                "MERCHANT_REVISION_REQUIRED",
            },
            "INVALID_STATE",
            "Merchant tasks are unavailable in this state",
        )
        message = text_field(
            data,
            "message",
            default=(
                "Confirmed available actions: "
                + ", ".join(case["rule_snapshot"].get("allowed_actions", []))
            ),
        )
        require(
            bool(case["rule_snapshot"].get("allowed_actions")),
            "ACTION_CONFIRMATION_REQUIRED",
            "No merchant action has been confirmed",
        )
        kind = "EVIDENCE" if case["merchant_decision"] == "CONTEST" else "DECISION"
        self._task(case, kind, message, now)
        if kind == "DECISION":
            case["work_status"] = "MERCHANT_ACTION_REQUIRED"
        self._collaboration(case, data, identity, now, message, "TASK_PUBLISHED")

    def _on_merchant_decision(self, case, data, identity, now):
        self._rule_ready(case)
        require(
            case["work_status"]
            in {"MERCHANT_ACTION_REQUIRED", "EVIDENCE_COLLECTING", "MERCHANT_REVISION_REQUIRED"},
            "INVALID_STATE",
            "No merchant decision task is active",
        )
        decision = text_field(data, "decision", limit=40)
        require(
            decision in {d.value for d in MerchantDecision} - {"NONE"},
            "INVALID_DECISION",
            "Unsupported merchant decision",
            422,
        )
        right = "ACCEPT" if decision == "AUTHORIZED_WAIVER" else decision
        require(
            right == "NO_RESPONSE" or right in case["rule_snapshot"].get("allowed_actions", []),
            "ACTION_NOT_ALLOWED",
            "This merchant decision is not allowed by the confirmed rule",
        )
        reason = text_field(data, "reason")
        if identity["role"] == "MERCHANT":
            require(
                decision in {"ACCEPT", "CONTEST"},
                "FORBIDDEN",
                "Merchant may choose Accept or Contest",
                403,
            )
        elif decision in {"ACCEPT", "CONTEST", "AUTHORIZED_WAIVER"}:
            text_field(data, "authorization_reference", limit=1000)
        if data.get("authorization_reference") is not None:
            text_field(data, "authorization_reference", limit=1000)
        if decision == "NO_RESPONSE":
            require(
                timestamp(now) > timestamp(case["deadlines"].get("merchant")),
                "DEADLINE_NOT_EXPIRED",
                "No response requires an expired merchant deadline",
            )
        case["merchant_decision"] = decision
        case["merchant_authorization"] = {
            "decision": decision,
            "reason": reason,
            "reference": data.get("authorization_reference"),
            "actor_id": identity["actor_id"],
            "role": identity["role"],
            "at": now,
        }
        self._invalidate(case, "Merchant decision changed", now)
        self._complete_tasks(case, now)
        if decision == "CONTEST":
            case["work_status"] = "EVIDENCE_COLLECTING"
            self._task(case, "EVIDENCE", "Provide the rule-linked evidence checklist", now)
        else:
            case["work_status"] = "WAITING_UPSTREAM"
            if decision == "NO_RESPONSE":
                self._task(
                    case, "SLA_ESCALATION", "Human follow-up: verify remaining rights upstream", now
                )
        self._collaboration(case, data, identity, now, f"{decision}: {reason}", "MERCHANT_DECISION")

    @staticmethod
    def _invalidate(case: dict, reason: str, now: str) -> None:
        case["evidence_version"] += 1
        for review in case["reviews"]:
            if review.get("valid"):
                review.update(valid=False, invalidation_reason=reason)
        for package in case["packages"]:
            if package["status"] in {"DRAFT", "FROZEN"}:
                package.update(status="INVALIDATED", invalidation_reason=reason, invalidated_at=now)
        if case["merchant_decision"] == "CONTEST":
            case["work_status"] = "EVIDENCE_COLLECTING"

    @staticmethod
    def _evidence_open(case):
        require(
            case["merchant_decision"] == "CONTEST",
            "CONTEST_REQUIRED",
            "Evidence collection requires a Contest decision",
        )
        require(
            case["work_status"]
            in {
                "EVIDENCE_COLLECTING",
                "MERCHANT_REVISION_REQUIRED",
                "OP_REVIEW",
                "EVIDENCE_SUBMITTED",
                "READY_TO_SUBMIT",
                "SUBMISSION_PENDING_CONFIRMATION",
            },
            "INVALID_STATE",
            "Evidence cannot change after submission or final outcome",
        )

    def _on_register_evidence(self, case, data, identity, now):
        self._evidence_open(case)
        code = text_field(data, "code", limit=100)
        title = text_field(data, "title", limit=500)
        reference = text_field(data, "reference", limit=2000)
        evidence_id = data.get("evidence_id")
        if evidence_id is not None:
            evidence_id = text_field(data, "evidence_id", limit=200)
        notes = data.get("notes", "")
        require(
            isinstance(notes, str) and len(notes) <= 12000,
            "INVALID_INPUT",
            "Evidence notes must be text of at most 12000 characters",
            422,
        )
        previous = next((e for e in case["evidence"] if e["id"] == evidence_id), None)
        require(
            evidence_id is None or previous is not None,
            "EVIDENCE_NOT_FOUND",
            "Evidence item does not exist",
            404,
        )
        self._invalidate(case, "Evidence registered or revised", now)
        item = {
            "id": evidence_id or uuid4().hex,
            "code": code,
            "title": title,
            "reference": reference,
            "source_channel": text_field(
                data, "source_channel", default=data.get("channel", "PORTAL"), limit=40
            ),
            "notes": notes,
            "revision": (previous["revision"] + 1) if previous else 1,
            "active": True,
            "registered_by": identity["actor_id"],
            "registered_at": now,
            "rule_version": case["rule_snapshot"].get("rule_version"),
            "content_verified": False,
            "source_type": "SYNTHETIC_DEMO",
        }
        if previous:
            item["history"] = previous.get("history", []) + [
                {k: v for k, v in previous.items() if k != "history"}
            ]
            case["evidence"][case["evidence"].index(previous)] = item
        else:
            case["evidence"].append(item)
        self._task(case, "EVIDENCE", "Submit revised evidence for Risk review", now)

    def _on_withdraw_evidence(self, case, data, identity, now):
        self._evidence_open(case)
        evidence_id = text_field(data, "evidence_id", limit=200)
        reason = text_field(data, "reason")
        item = next((e for e in case["evidence"] if e["id"] == evidence_id and e["active"]), None)
        require(item is not None, "EVIDENCE_NOT_FOUND", "Active evidence item not found", 404)
        item.update(active=False, withdrawn_at=now, withdrawal_reason=reason)
        self._invalidate(case, "Evidence withdrawn", now)
        self._task(case, "EVIDENCE", "Complete evidence and resubmit for review", now)

    def _on_submit_evidence(self, case, data, identity, now):
        self._rule_ready(case)
        self._evidence_open(case)
        missing = missing_evidence(case)
        require(not missing, "MISSING_EVIDENCE", "Missing evidence: " + ", ".join(missing))
        require(
            case["work_status"] in {"EVIDENCE_COLLECTING", "MERCHANT_REVISION_REQUIRED"},
            "INVALID_STATE",
            "Evidence is already submitted",
        )
        case["work_status"] = "OP_REVIEW"
        self._complete_tasks(case, now, {"EVIDENCE", "REVISION"})
        self._task(case, "OP_REVIEW", "Risk Officer must review evidence content", now)

    def _on_review(self, case, data, identity, now):
        self._rule_ready(case)
        require(case["work_status"] == "OP_REVIEW", "INVALID_STATE", "Evidence awaits Risk review")
        decision = text_field(data, "decision", limit=40)
        require(
            decision in {"PASS", "REVISION", "ACCEPT"},
            "INVALID_DECISION",
            "Review decision must be PASS, REVISION or ACCEPT",
            422,
        )
        reason = text_field(data, "reason")
        if decision == "PASS":
            require(not missing_evidence(case), "MISSING_EVIDENCE", "Required evidence is missing")
            case["work_status"] = "READY_TO_SUBMIT"
        else:
            # A reviewer can recommend acceptance; only the merchant/authorized OP decides.
            case["work_status"] = "MERCHANT_REVISION_REQUIRED"
            self._task(case, "REVISION", reason, now)
        case["reviews"].append(
            {
                "id": uuid4().hex,
                "type": "EVIDENCE",
                "decision": decision,
                "reason": reason,
                "reviewer": identity["actor_id"],
                "role": identity["role"],
                "evidence_version": case["evidence_version"],
                "case_revision": case["revision"],
                "valid": decision == "PASS",
                "at": now,
            }
        )
        self._complete_tasks(case, now, {"OP_REVIEW"})

    @staticmethod
    def _valid_review(case):
        review = next(
            (
                r
                for r in reversed(case["reviews"])
                if r["type"] == "EVIDENCE"
                and r["decision"] == "PASS"
                and r["valid"]
                and r["evidence_version"] == case["evidence_version"]
            ),
            None,
        )
        require(review is not None, "REVIEW_REQUIRED", "Current evidence requires Risk review")
        return review

    def _on_build_package(self, case, data, identity, now):
        self._rule_ready(case)
        require(
            case["work_status"] == "READY_TO_SUBMIT",
            "INVALID_STATE",
            "Package creation requires approved evidence",
        )
        self._valid_review(case)
        require(not missing_evidence(case), "MISSING_EVIDENCE", "Required evidence is missing")
        draft = text_field(
            data,
            "draft",
            default=(
                f"SYNTHETIC DEMO response for {case['scheme']} {case['reason_code']}. "
                "Evidence references require human content verification. "
                "No real upstream submission."
            ),
            limit=20000,
        )
        package = {
            "id": uuid4().hex,
            "version": len(case["packages"]) + 1,
            "status": "DRAFT",
            "evidence_version": case["evidence_version"],
            "stage_number": case["stage_number"],
            "evidence_index": deepcopy([e for e in case["evidence"] if e["active"]]),
            "rule_snapshot": deepcopy(case["rule_snapshot"]),
            "draft": draft,
            "citations": [
                {
                    "source_id": case["rule_snapshot"].get("source_id"),
                    "source_locator": case["rule_snapshot"].get("source_locator"),
                    "rule_version": case["rule_snapshot"].get("rule_version"),
                }
            ],
            "pii_checked": False,
            "created_at": now,
            "created_by": identity["actor_id"],
            "production_eligible": False,
        }
        package["digest"] = self._package_digest(package)
        case["packages"].append(package)
        case["work_status"] = "SUBMISSION_PENDING_CONFIRMATION"
        self._task(case, "FINAL_REVIEW", "Supervisor must review and freeze the package", now)

    @staticmethod
    def _package_digest(package):
        return fingerprint(
            {
                key: package[key]
                for key in (
                    "id",
                    "version",
                    "evidence_version",
                    "stage_number",
                    "evidence_index",
                    "rule_snapshot",
                    "draft",
                    "citations",
                )
            }
        )

    @staticmethod
    def _package(case, data):
        package_id = data.get("package_id")
        if package_id is not None:
            package_id = text_field(data, "package_id", limit=200)
        package = next(
            (p for p in reversed(case["packages"]) if package_id is None or p["id"] == package_id),
            None,
        )
        require(package is not None, "PACKAGE_REQUIRED", "Package not found")
        require(
            package["evidence_version"] == case["evidence_version"]
            and package["stage_number"] == case["stage_number"],
            "PACKAGE_STALE",
            "Package no longer reflects current evidence and stage",
        )
        return package

    def _on_approve_package(self, case, data, identity, now):
        require(
            case["work_status"] == "SUBMISSION_PENDING_CONFIRMATION",
            "INVALID_STATE",
            "No package is awaiting final approval",
        )
        review = self._valid_review(case)
        require(
            review["reviewer"] != identity["actor_id"],
            "REVIEWER_SEPARATION_REQUIRED",
            "Evidence review and final approval require two different people",
            403,
        )
        package = self._package(case, data)
        require(package["status"] == "DRAFT", "PACKAGE_NOT_DRAFT", "Only a draft may be approved")
        require(
            data.get("pii_checked") is True,
            "PII_REVIEW_REQUIRED",
            "Human PII and content review must be confirmed",
        )
        reason = text_field(data, "reason")
        require(
            self._package_digest(package) == package["digest"],
            "PACKAGE_INTEGRITY",
            "Package content has changed",
        )
        package.update(
            status="FROZEN",
            approved_by=identity["actor_id"],
            approved_at=now,
            pii_checked=True,
            approval_reason=reason,
        )
        case["reviews"].append(
            {
                "id": uuid4().hex,
                "type": "FINAL",
                "decision": "PASS",
                "reviewer": identity["actor_id"],
                "role": identity["role"],
                "reason": reason,
                "evidence_version": case["evidence_version"],
                "case_revision": case["revision"],
                "package_id": package["id"],
                "valid": True,
                "at": now,
            }
        )
        case["work_status"] = "READY_TO_SUBMIT"
        self._complete_tasks(case, now, {"FINAL_REVIEW"})

    def _on_submit(self, case, data, identity, now):
        require(
            self.upstream_mode == "mock", "UPSTREAM_DISABLED", "Upstream submission is disabled"
        )
        self._rule_ready(case)
        require(
            case["work_status"] == "READY_TO_SUBMIT",
            "INVALID_STATE",
            "Only an approved package is ready for submission",
        )
        self._valid_review(case)
        package = self._package(case, data)
        require(
            package["status"] == "FROZEN" and package["pii_checked"],
            "FINAL_REVIEW_REQUIRED",
            "Supervisor must approve and freeze the package",
        )
        require(
            self._package_digest(package) == package["digest"],
            "PACKAGE_INTEGRITY",
            "Frozen package integrity check failed",
        )
        require(
            timestamp(now) <= timestamp(case["deadlines"]["external"]),
            "EXTERNAL_DEADLINE_EXPIRED",
            "Confirmed external deadline has passed",
        )
        require(
            not any(s["package_id"] == package["id"] for s in case["submissions"]),
            "ALREADY_SUBMITTED",
            "Package has already been submitted; replay its original command",
        )
        case["submissions"].append(
            {
                "id": f"mock-{package['digest'][:20]}",
                "package_id": package["id"],
                "package_digest": package["digest"],
                "mode": "MOCK",
                "transport_state": "DELIVERED",
                "business_acceptance": "MOCK_ACCEPTED",
                "request_id": f"request-{package['id']}",
                "receipt_id": f"receipt-{package['id']}",
                "idempotency_key": f"{case['id']}:{package['id']}",
                "submitted_at": now,
                "submitted_by": identity["actor_id"],
                "production_eligible": False,
            }
        )
        case["work_status"] = "WAITING_UPSTREAM"

    def _on_record_outcome(self, case, data, identity, now):
        require(
            case["work_status"] == "WAITING_UPSTREAM",
            "INVALID_STATE",
            "An upstream outcome requires an active upstream response or merchant decision",
        )
        outcome = text_field(data, "outcome", limit=40)
        require(
            outcome in {o.value for o in BusinessOutcome},
            "INVALID_OUTCOME",
            "Record an explicit upstream business outcome",
            422,
        )
        require(type(data.get("final")) is bool, "INVALID_FINALITY", "final must be boolean", 422)
        if data.get("reason") is not None:
            text_field(data, "reason")
        if data.get("next_stage") is not None:
            text_field(data, "next_stage", limit=50)
            require(
                data["final"] is False and outcome != "UNKNOWN",
                "INVALID_STAGE",
                "Only a known nonterminal outcome can advance to a new stage",
                422,
            )
        require(
            outcome != "UNKNOWN" or data["final"] is False,
            "UNKNOWN_FINAL_OUTCOME",
            "An unknown outcome cannot be marked final",
        )
        source = text_field(data, "source", limit=200)
        case["upstream_events"].append(
            {
                "id": data["event_id"],
                "type": "OUTCOME",
                "source": source,
                "outcome": outcome,
                "final": data["final"],
                "reason": data.get("reason"),
                "at": now,
                "stage_number": case["stage_number"],
            }
        )
        case["business_outcome"] = outcome
        case["finality"] = "FINAL_CONFIRMED" if data["final"] else "NOT_FINAL"
        case["merchant_notification_completed"] = False
        if outcome == "UNKNOWN":
            self._task(
                case, "OUTCOME_CONFIRMATION", "Unknown outcome requires upstream confirmation", now
            )
            return
        self._complete_tasks(case, now)
        if data["final"]:
            case["work_status"] = "FINANCIAL_RECONCILIATION"
            case["financial_status"] = "PENDING"
            self._task(case, "FINANCIAL_RECONCILIATION", "Manually reconcile upstream ledger", now)
        else:
            case["pending_next_stage"] = True
            case["work_status"] = "TRIAGED"
            self._task(case, "NEXT_STAGE", "Confirm next stage and recalculate rule/SLA", now)
            if data.get("next_stage"):
                self._advance_stage(case, data["next_stage"], source, data["event_id"], now)

    def _on_next_stage(self, case, data, identity, now):
        require(
            case["finality"] == "NOT_FINAL" and case.get("pending_next_stage"),
            "NEXT_STAGE_NOT_ALLOWED",
            "A nonterminal upstream outcome must precede a new stage",
        )
        self._advance_stage(
            case,
            text_field(data, "stage", limit=50),
            text_field(data, "source", limit=200),
            data["event_id"],
            now,
        )

    def _advance_stage(self, case, stage, source, event_id, now):
        require(
            isinstance(stage, str)
            and stage in {s.value for s in CaseStage}
            and stage != case["stage"],
            "INVALID_STAGE",
            "Next stage must be an explicit different stage",
            422,
        )
        order = ["FORMAL_DISPUTE", "REPRESENTMENT", "PRE_ARBITRATION", "ARBITRATION"]
        require(
            stage == "OTHER"
            or case["stage"] == "OTHER"
            or order.index(stage) > order.index(case["stage"]),
            "INVALID_STAGE",
            "An upstream stage cannot move backwards",
            422,
        )
        case["stage_history"].append(
            {
                **deepcopy(
                    {
                        key: case[key]
                        for key in (
                            "stage",
                            "stage_number",
                            "rule_snapshot",
                            "deadlines",
                            "business_outcome",
                            "finality",
                            "merchant_decision",
                            "evidence",
                            "reviews",
                            "packages",
                            "submissions",
                        )
                    }
                ),
                "ended_at": now,
                "source": source,
                "event_id": event_id,
            }
        )
        case["stage"] = stage
        case["stage_number"] += 1
        case["pending_next_stage"] = False
        case["rule_snapshot"] = self.rule_matcher(
            case["scheme"],
            case["channel"],
            case["reason_code"],
            stage,
            now,
        )
        case["deadlines"] = deepcopy(case["rule_snapshot"].get("deadlines", {}))
        self._invalidate(case, "New upstream stage", now)
        case["merchant_decision"] = "NONE"
        case["work_status"] = (
            "TRIAGED" if case["rule_snapshot"].get("conflict_status") == "VERIFIED" else "RECEIVED"
        )
        self._complete_tasks(case, now)
        case["upstream_events"].append(
            {"id": event_id, "type": "NEXT_STAGE", "stage": stage, "source": source, "at": now}
        )

    def _on_record_financial(self, case, data, identity, now):
        kind = text_field(data, "kind", limit=40)
        require(
            kind in {"DEBIT", "CREDIT", "REFUND", "FEE", "ADJUSTMENT"},
            "INVALID_FINANCIAL_KIND",
            "Unsupported financial event kind",
            422,
        )
        amount = minor_units(data.get("amount_minor"), allow_negative=kind == "ADJUSTMENT")
        currency = currency_code(data.get("currency"))
        require(
            currency == case["currency"],
            "CURRENCY_MISMATCH",
            "Cross-currency reconciliation requires a separately confirmed FX workflow",
            422,
        )
        reference = text_field(data, "reference", limit=1000)
        # Net is the merchant settlement impact: debits, refunds and fees decrease it.
        net = -amount if kind in {"DEBIT", "REFUND", "FEE"} else amount
        case["financial_events"].append(
            {
                "id": data["event_id"],
                "kind": kind,
                "amount_minor": amount,
                "currency": currency,
                "net_minor": net,
                "source": data["source"],
                "reference": reference,
                "at": now,
                "recorded_by": identity["actor_id"],
            }
        )
        case["financial_version"] += 1
        case["financial_status"] = "PENDING"
        case["merchant_notification_completed"] = False
        if case["finality"] == "FINAL_CONFIRMED":
            self._task(
                case, "FINANCIAL_RECONCILIATION", "Reconcile newly recorded ledger event", now
            )

    def _on_reconcile(self, case, data, identity, now):
        require(
            case["finality"] == "FINAL_CONFIRMED",
            "FINALITY_REQUIRED",
            "Financial reconciliation requires a terminal upstream outcome",
        )
        status = text_field(data, "status", limit=40)
        require(
            status in {"RECONCILED", "DISCREPANCY", "NOT_APPLICABLE"},
            "INVALID_FINANCIAL_STATUS",
            "Unsupported reconciliation decision",
            422,
        )
        expected = minor_units(data.get("expected_net_minor"), allow_negative=True)
        reason = text_field(data, "reason")
        reference = text_field(data, "reference", limit=1000)
        net = sum(event["net_minor"] for event in case["financial_events"])
        if status == "RECONCILED":
            require(
                bool(case["financial_events"]),
                "LEDGER_REQUIRED",
                "Reconciled status requires upstream financial records",
            )
            require(
                net == expected,
                "FINANCIAL_MISMATCH",
                f"Ledger net {net} does not match human-confirmed expected net {expected}",
            )
        elif status == "NOT_APPLICABLE":
            require(
                not case["financial_events"] and expected == 0,
                "FINANCIAL_EVENTS_PRESENT",
                "Not applicable requires no financial events and zero net",
            )
        case["financial_status"] = status
        case["reconciliation"] = {
            "status": status,
            "expected_net_minor": expected,
            "actual_net_minor": net,
            "currency": case["currency"],
            "reason": reason,
            "reference": reference,
            "reviewer": identity["actor_id"],
            "at": now,
            "financial_version": case["financial_version"],
        }
        case["merchant_notification_completed"] = False
        if status in {"RECONCILED", "NOT_APPLICABLE"}:
            self._complete_tasks(case, now, {"FINANCIAL_RECONCILIATION"})
        else:
            self._task(case, "FINANCIAL_RECONCILIATION", "Resolve ledger discrepancy", now)

    def _on_notify_merchant(self, case, data, identity, now):
        message = text_field(
            data,
            "message",
            default=(
                f"Dispute outcome: {case['business_outcome']}; "
                f"financial status: {case['financial_status']}."
            ),
        )
        channel = text_field(data, "channel", default="PORTAL", limit=30).upper()
        if channel != "PORTAL":
            # External delivery must be evidenced; generating an event is not delivery.
            text_field(data, "reference", limit=1000)
        self._collaboration(case, data, identity, now, message, "MERCHANT_NOTIFICATION")
        case["collaboration"][-1]["delivery_status"] = (
            "AVAILABLE_IN_PORTAL" if channel == "PORTAL" else "HUMAN_CONFIRMED_DELIVERY"
        )
        case["collaboration"][-1]["delivery_reference"] = data.get("reference")
        case["merchant_notification_completed"] = case["finality"] == "FINAL_CONFIRMED"

    def _on_close(self, case, data, identity, now):
        blockers = close_blockers(case)
        require(not blockers, "CLOSE_BLOCKED", "; ".join(blockers))
        case["work_status"] = "CLOSED"
        case["closed_at"] = now
        case["closed_by"] = identity["actor_id"]

    def _on_comment(self, case, data, identity, now):
        self._collaboration(case, data, identity, now, text_field(data, "message", limit=12000))

    def _on_monitor_sla(self, case, data, identity, now):
        if case["finality"] == "FINAL_CONFIRMED":
            return
        if case["deadlines"].get("status") != "CONFIRMED":
            self._task(
                case, "RULE_CONFIRMATION", "Deadline unknown; request Risk confirmation", now
            )
            return
        merchant_deadline = timestamp(case["deadlines"]["merchant"])
        moment = timestamp(now)
        if moment + timedelta(days=1) >= merchant_deadline:
            overdue = moment > merchant_deadline
            self._task(
                case,
                "SLA_ESCALATION" if overdue else "SLA_REMINDER",
                "Merchant deadline expired; human decision required"
                if overdue
                else "Merchant deadline within 24 hours",
                now,
            )
            self._collaboration(
                case,
                {"channel": "PORTAL"},
                identity,
                now,
                "Deadline expired; verify remaining rights"
                if overdue
                else "Deadline approaching; evidence action needed",
                "SLA_ALERT",
            )

    def _on_knowledge_candidate(self, case, data, identity, now):
        require(
            case["work_status"] == "CLOSED",
            "CLOSE_REQUIRED",
            "Knowledge reuse begins after case closure",
        )
        summary = redact_knowledge(text_field(data, "summary", limit=6000), case)
        pattern = redact_knowledge(text_field(data, "pattern", limit=6000), case)
        case["knowledge_candidates"].append(
            {
                "id": uuid4().hex,
                "summary": summary,
                "pattern": pattern,
                "status": "PENDING_REVIEW",
                "redacted": True,
                "redaction_method": "PATTERN_FILTER_REQUIRES_HUMAN_REVIEW",
                "created_at": now,
                "created_by": identity["actor_id"],
                "source_type": "SYNTHETIC_DEMO",
                "production_eligible": False,
                "rule_version": case["rule_snapshot"].get("rule_version"),
            }
        )

    def _on_approve_knowledge(self, case, data, identity, now):
        candidate_id = text_field(data, "candidate_id", limit=200)
        candidate = next((k for k in case["knowledge_candidates"] if k["id"] == candidate_id), None)
        require(candidate is not None, "CANDIDATE_NOT_FOUND", "Knowledge candidate not found", 404)
        require(
            candidate["status"] == "PENDING_REVIEW",
            "ALREADY_REVIEWED",
            "Knowledge candidate has already been reviewed",
        )
        decision = text_field(data, "decision", limit=20)
        require(
            decision in {"APPROVE", "REJECT"},
            "INVALID_DECISION",
            "Knowledge decision must be APPROVE or REJECT",
            422,
        )
        reason = text_field(data, "reason")
        require(
            candidate["created_by"] != identity["actor_id"],
            "REVIEWER_SEPARATION_REQUIRED",
            "A knowledge author cannot approve their own candidate",
            403,
        )
        candidate.update(
            status="APPROVED" if decision == "APPROVE" else "REJECTED",
            reviewed_by=identity["actor_id"],
            reviewed_at=now,
            review_reason=reason,
            human_pii_review_confirmed=True,
            production_eligible=False,
        )
