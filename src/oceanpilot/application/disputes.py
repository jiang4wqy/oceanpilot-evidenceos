"""OceanPayment-owned dispute command service.

Commands are deterministic business operations. Agents may prepare drafts and
monitor, while distinct humans review evidence, approve packages and reconcile.
"""

import logging
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
        on_change=None,
        case_library=None,
        access_policy=None,
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
        self.on_change = on_change
        self.case_library = case_library
        self.access_policy = access_policy

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
        cases = self.store.list_cases(
            identity["merchant_id"] if identity["role"] == "MERCHANT" else None,
        )
        return [
            case
            for case in cases
            if self.access_policy is None or self.access_policy.can_access(case, identity)
        ]

    def get_case(self, case_id: str, identity: dict) -> dict:
        identity = self._identity(identity)
        require(isinstance(case_id, str), "INVALID_INPUT", "case_id must be text", 422)
        case = self.store.get_case(case_id)
        require(case is not None, "NOT_FOUND", "Case not found", 404)
        if self.access_policy is not None:
            self.access_policy.require_case(case, identity)
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
        if self.access_policy is not None:
            if action == "INTAKE":
                self.access_policy.require_intake(command["data"].get("merchant_id"), identity)
            else:
                self.get_case(command.get("case_id"), identity)
        if action == "INTAKE":
            if not command.get("case_id"):
                digest = fingerprint(command_id)[:16]
                legacy_id = f"OPV2-{digest}"
                # Duplicate notices can have a receipt without their own case row.
                # Reuse the old derivation only for an exact saved command; the
                # atomic store still verifies actor identity and the fingerprint.
                legacy_digest = fingerprint(command | {"case_id": legacy_id})
                command["case_id"] = (
                    legacy_id
                    if self.store.get_command_fingerprint(command_id) == legacy_digest
                    # New derived hashes cannot contain card-number digit runs.
                    else f"OPV2-{digest[:8]}g{digest[8:]}"
                )
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
        result = self.store.execute_atomic(
            command=command,
            identity=identity,
            mutate=lambda case: self._authorized_apply(case, command, identity),
            event_key=event_key,
            event_fingerprint=event_digest,
            upstream_case_key=upstream_case_key,
        )
        # Observe only after the business transaction commits. The independent
        # Agent journal must never turn a committed command into a failed HTTP
        # response or require a user to repeat a financial/business operation.
        if self.on_change is not None:
            try:
                current = self.store.get_case(result["case"]["id"])
                self.on_change(current, action, result["replayed"])
            except Exception:
                logging.getLogger(__name__).warning("V2 agent observation unavailable")
                result["agent_observation_status"] = "UNAVAILABLE"
        return result

    def _authorized_apply(self, case: dict | None, command: dict, identity: dict) -> dict:
        if case is not None and self.access_policy is not None:
            self.access_policy.require_case(case, identity)
        origin = command.get("proposal_origin")
        validated_origin = None
        if origin is not None:
            validator = getattr(self, "proposal_validator", None)
            require(callable(validator), "PROPOSAL_UNAVAILABLE", "提案验证服务暂不可用。", 503)
            validated_origin = validator(
                command["case_id"],
                identity,
                **origin,
                expected_revision=command["expected_revision"],
                action=command["action"],
                actual_data=command["data"],
            )
        result = self._apply(case, command, identity)
        if validated_origin is not None:
            result["audit"][-1]["proposal_origin"] = validated_origin
        if case is None and self.access_policy is not None:
            return self.access_policy.initialize_case(result, identity)
        return result

    def action_gate(self, case: dict, action: str, identity: dict, now=None) -> dict:
        from oceanpilot.application.dispute_messages import localize_gate
        from oceanpilot.domain.dispute_actions import action_gate

        gate = localize_gate(action_gate(case, action, identity, now or self.clock()))
        collaboration = getattr(self, "collaboration", None)
        if (
            action == "CLOSE"
            and collaboration is not None
            and collaboration.open_handoffs(case["id"])
        ):
            return gate | {
                "enabled": False,
                "code": "OPEN_HANDOFF",
                "blocked_reason": "还有未解决的人工接手事项，请先由负责人处理。",
            }
        return gate

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
            self._upgrade_case(case)
        else:
            self._upgrade_case(case)
            gate = self.action_gate(case, action, identity, now)
            require(
                gate["enabled"],
                gate["code"] or "INVALID_STATE",
                gate["blocked_reason"] or "Action unavailable",
                403 if gate["code"] in {"FORBIDDEN", "REVIEWER_SEPARATION_REQUIRED"} else 409,
            )
            case["_command_context"] = {
                "actor_id": identity["actor_id"],
                "role": identity["role"],
                "action": action,
                "reason": data.get("reason") or action,
                "revision": case["revision"] + 1,
            }
            getattr(self, f"_on_{action.lower()}")(case, data, identity, now)
        case.pop("_command_context", None)
        self._financial_summary(case)
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
    def _upgrade_case(case):
        # Lazy additive migration inside the existing CAS transaction; no historical rewrite.
        defaults = {
            "schema_version": "2.1",
            "decision_response_status": "RESPONDED"
            if case["merchant_decision"] in {"ACCEPT", "CONTEST", "AUTHORIZED_WAIVER"}
            else "NO_RESPONSE"
            if case["merchant_decision"] == "NO_RESPONSE"
            else "PENDING",
            "evidence_task_status": "PENDING",
            "eligibility_status": "CONFIRMED",
            "current_stage_outcome": case["business_outcome"],
            "last_known_outcome": case["business_outcome"],
            "outcome_version": 0,
            "outcome_verification_required": False,
            "response_history": [],
            "rule_history": [],
            "outcome_history": [],
            "closure_history": [],
            "acceptances": [],
            "reconciliation_history": [],
            "notification_history": [],
        }
        for key, value in defaults.items():
            case.setdefault(key, deepcopy(value))

    @staticmethod
    def _financial_summary(case):
        amounts = case.get("outcome_amounts", {})
        events = case.get("financial_events", [])
        case["financial_summary"] = {
            "source_type": "SYNTHETIC_LEDGER",
            "production_eligible": False,
            "currency": case["currency"],
            "disputed_minor": case["amount_minor"],
            "supported_minor": amounts.get("supported_minor"),
            "liable_minor": amounts.get("liable_minor"),
            "fee_minor": sum(e["amount_minor"] for e in events if e["kind"] == "FEE"),
            "refund_minor": sum(e["amount_minor"] for e in events if e["kind"] == "REFUND"),
            "debit_minor": sum(e["amount_minor"] for e in events if e["kind"] == "DEBIT"),
            "credit_minor": sum(e["amount_minor"] for e in events if e["kind"] == "CREDIT"),
            "adjustment_minor": sum(e["amount_minor"] for e in events if e["kind"] == "ADJUSTMENT"),
            "net_minor": sum(e["net_minor"] for e in events),
            "net_direction": "POSITIVE_INCREASES_MERCHANT_SETTLEMENT",
            "outcome_version": case.get("outcome_version", 0),
            "financial_version": case.get("financial_version", 0),
            "basis_reference": amounts.get("basis_reference"),
            "boundary": (
                "Synthetic event reconciliation; outcome allocation is not a second ledger entry"
            ),
        }

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
            "evidence_ids",
            "task_id",
            "replacement_task_id",
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
                    visit(child, field)
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
        library_reference = None
        if data.get("case_template_id") is not None:
            template_id = text_field(data, "case_template_id", limit=100)
            require(
                self.case_library is not None,
                "LIBRARY_UNAVAILABLE",
                "Case library unavailable",
                503,
            )
            preview = self.case_library.get_template(template_id)
            require(preview is not None, "TEMPLATE_NOT_FOUND", "Sandbox template not found", 404)
            require(
                channel == "MOCK", "INVALID_TEMPLATE_CHANNEL", "Templates use the Mock channel", 422
            )
            require(
                scheme in {"VISA", "MASTERCARD"},
                "UNSUPPORTED_TEMPLATE_SCHEME",
                "This rehearsal flow supports Visa and Mastercard templates",
                422,
            )
            matches = self.case_library.search(scheme=scheme, reason_code=reason, limit=100)
            require(
                any(item["template_id"] == template_id for item in matches),
                "TEMPLATE_SCOPE_MISMATCH",
                "Scheme and reason must match the chosen template",
                422,
            )
            library_reference = deepcopy(preview["reference"])
            library_reference["sandbox_inputs"] = {
                "transaction_id": transaction_id,
                "amount_minor": amount,
                "currency": currency,
                "received_at": received_at,
                "origin": "HUMAN_CONFIRMED_REHEARSAL_INPUT",
            }
            # Guideline scenarios do not contain a verified transaction-specific deadline.
            # A source-backed rehearsal must not silently inherit the six Mock fixtures' SLA.
            rule = self.rule_matcher(
                scheme, "CURATED_REFERENCE", reason, "FORMAL_DISPUTE", received_at
            )
            rule.update(
                {
                    "channel": channel,
                    "source_id": "CASE-LIBRARY:" + template_id,
                    "source_locator": str(library_reference.get("source_locators", []))[:500],
                    "rule_version": str(library_reference.get("rule_versions", []))[:100],
                    "source_type": "CURATED_CASE_LIBRARY",
                    "production_eligible": False,
                    "conflict_status": "NEEDS_CONFIRMATION",
                    "allowed_actions": [],
                    "required_evidence": [],
                    "critical_evidence": [],
                    "deadlines": {
                        "merchant": None,
                        "internal": None,
                        "external": None,
                        "status": "NEEDS_CONFIRMATION",
                        "source": "CASE-LIBRARY:" + template_id,
                    },
                    "limitation": (
                        "源案例用于参考；请人工确认本次演练的适用权利、证据要求及明确期限。"
                    ),
                }
            )
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
            require(
                (existing.get("library_reference") or {}).get("template_id")
                == (library_reference or {}).get("template_id"),
                "UPSTREAM_CASE_CONFLICT",
                "Case template cannot change on duplicate intake",
                409,
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
        if library_reference is not None:
            case["library_reference"] = library_reference
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
        # Deliberately never interpret omitted types as "complete everything".
        DisputeService._resolve_tasks(case, now, types or set(), "COMPLETED")

    @staticmethod
    def _resolve_tasks(case, now, types, status, reason=None):
        context = case.get("_command_context", {})
        for task in case["tasks"]:
            if (
                task["status"] == "OPEN"
                and task["type"] in types
                and task.get("stage_number", 1) == case["stage_number"]
            ):
                task.update(
                    status=status,
                    resolved_at=now,
                    resolution={
                        "status": status,
                        "at": now,
                        "actor_id": context.get("actor_id", "SYSTEM"),
                        "role": context.get("role", "SYSTEM"),
                        "reason": reason or context.get("reason", "Business transition"),
                        "revision": case["revision"] + 1,
                    },
                )
                if status == "COMPLETED":
                    task["completed_at"] = now

    @staticmethod
    def _task(case: dict, kind: str, message: str, now: str) -> None:
        if any(
            t["type"] == kind
            and t["status"] == "OPEN"
            and t.get("stage_number", 1) == case["stage_number"]
            for t in case["tasks"]
        ):
            return
        merchant_types = {"DECISION", "EVIDENCE", "REVISION", "ACCEPT_DECISION"}
        risk_types = {
            "OP_REVIEW",
            "RULE_CONFIRMATION",
            "RESPONSE_RIGHTS",
            "OUTCOME_CONFIRMATION",
            "EVIDENCE_APPLICABILITY",
            "CONTENT_REVIEW",
        }
        owner = (
            "MERCHANT"
            if kind in merchant_types
            else "RISK_OFFICER"
            if kind in risk_types
            else "SUPERVISOR"
            if kind in {"FINAL_REVIEW", "ESCALATION_HOLD", "FINANCIAL_RECONCILIATION"}
            else "OPERATOR"
        )
        deadline = case.get("deadlines", {}).get(
            "merchant"
            if owner == "MERCHANT"
            else "internal"
            if owner in {"RISK_OFFICER", "SUPERVISOR"}
            else "external"
        )
        case["tasks"].append(
            {
                "id": uuid4().hex,
                "type": kind,
                "status": "OPEN",
                "required": True,
                "message": message,
                "created_at": now,
                "stage_number": case["stage_number"],
                "owner": owner,
                "assignee": DisputeService._task_assignee(case, owner),
                "deadline": deadline,
                "created_revision": case["revision"] + 1,
            }
        )

    @staticmethod
    def _task_assignee(case, owner):
        if owner == "OPERATOR" and case.get("assigned_op_user_id"):
            return case["assigned_op_user_id"]
        people = case.get("participants", [])
        risk_actor = next(
            (
                r.get("reviewer")
                for r in reversed(case.get("reviews", []))
                if r.get("type") == "EVIDENCE" and r.get("valid")
            ),
            None,
        )
        return next(
            (
                p.get("user_id", p.get("actor_id"))
                for p in people
                if p.get("role") == owner
                and (owner != "SUPERVISOR" or p.get("user_id", p.get("actor_id")) != risk_actor)
            ),
            None,
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
                "READY_TO_SUBMIT",
                "SUBMISSION_PENDING_CONFIRMATION",
                "RESPONSE_REVIEW_REQUIRED",
                "ACCEPT_RECOMMENDATION",
                "DOCUMENT_REVISION_REQUIRED",
                "ON_HOLD",
            },
            "INVALID_STATE",
            "Rules cannot be replaced after submission or a terminal outcome",
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
            and len(required) <= 30
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
        require(
            "CONTEST" not in allowed or bool(required),
            "INVALID_EVIDENCE_RULE",
            "Contest requires an explicit evidence checklist",
            422,
        )
        case["rule_history"].append(
            {
                "snapshot": deepcopy(case["rule_snapshot"]),
                "deadlines": deepcopy(case["deadlines"]),
                "superseded_at": now,
                "actor_id": identity["actor_id"],
            }
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
        self._complete_tasks(case, now, {"RULE_CONFIRMATION"})
        self._resolve_tasks(
            case,
            now,
            {"EVIDENCE", "REVISION", "DECISION", "FINAL_REVIEW", "OP_REVIEW"},
            "SUPERSEDED",
            "Rule and deadlines replaced",
        )
        if case["merchant_decision"] == "CONTEST" and "CONTEST" not in allowed:
            case["eligibility_status"] = "REQUIRES_RECONFIRMATION"
            case["work_status"] = "RESPONSE_REVIEW_REQUIRED"
            self._task(
                case,
                "RESPONSE_RIGHTS",
                (
                    "Contest is no longer permitted; confirm remaining rights "
                    "and obtain a new authorized decision"
                ),
                now,
            )
        else:
            case["eligibility_status"] = "CONFIRMED"
            if case["merchant_decision"] == "NONE":
                case["work_status"] = "TRIAGED"
            elif case["merchant_decision"] == "CONTEST":
                self._task(case, "EVIDENCE", "Revalidate evidence against the confirmed rule", now)

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
        reason = text_field(data, "reason", limit=1000)
        if identity["role"] == "MERCHANT":
            require(
                decision in {"ACCEPT", "CONTEST"},
                "FORBIDDEN",
                "Merchant may choose Accept or Contest",
                403,
            )
        elif decision in {"ACCEPT", "CONTEST", "AUTHORIZED_WAIVER"}:
            text_field(data, "authorization_reference", limit=1000)
        if decision == "NO_RESPONSE":
            require(
                case["merchant_decision"] == "NONE"
                and case["decision_response_status"] == "PENDING",
                "ALREADY_RESPONDED",
                "A valid merchant response cannot be overwritten as no response",
            )
            require(
                timestamp(now) > timestamp(case["deadlines"].get("merchant")),
                "DEADLINE_NOT_EXPIRED",
                "No response requires an expired merchant deadline",
            )
        if decision == "CONTEST":
            require(
                case.get("eligibility_status") not in {"REQUIRES_RECONFIRMATION", "RIGHTS_LOST"},
                "CONTEST_NOT_ELIGIBLE",
                "Remaining Contest rights require Risk confirmation",
            )
            require(
                timestamp(now) <= timestamp(case["deadlines"]["external"]),
                "EXTERNAL_DEADLINE_EXPIRED",
                "Confirmed external deadline has passed",
            )
        case["response_history"].append(
            {
                "decision": case["merchant_decision"],
                "authorization": deepcopy(case.get("merchant_authorization")),
                "at": now,
                "stage_number": case["stage_number"],
            }
        )
        case["merchant_decision"] = decision
        case["decision_response_status"] = (
            "NO_RESPONSE" if decision == "NO_RESPONSE" else "RESPONDED"
        )
        case["merchant_authorization"] = {
            "decision": decision,
            "reason": reason,
            "reference": data.get("authorization_reference"),
            "actor_id": identity["actor_id"],
            "role": identity["role"],
            "at": now,
            "stage_number": case["stage_number"],
            "rule_version": case["rule_snapshot"].get("rule_version"),
            "amount_minor": case["amount_minor"],
            "currency": case["currency"],
        }
        self._invalidate(case, "Merchant decision changed", now)
        self._complete_tasks(case, now, {"DECISION", "ACCEPT_DECISION"})
        self._resolve_tasks(
            case,
            now,
            {"EVIDENCE", "REVISION", "OP_REVIEW", "FINAL_REVIEW"},
            "SUPERSEDED",
            "Merchant decision replaced the previous work",
        )
        if decision == "CONTEST":
            case["work_status"] = "EVIDENCE_COLLECTING"
            case["evidence_task_status"] = "PENDING"
            self._task(case, "EVIDENCE", "Provide the current rule-linked evidence checklist", now)
        elif decision == "NO_RESPONSE":
            case["work_status"] = "RESPONSE_REVIEW_REQUIRED"
            self._task(
                case,
                "RESPONSE_RIGHTS",
                (
                    "No decision received; verify remaining rights "
                    "before recovery or loss confirmation"
                ),
                now,
            )
        else:
            case["work_status"] = "ACCEPT_PROCESSING"
            case["eligibility_status"] = "CONFIRMED"
            self._complete_tasks(case, now, {"RESPONSE_RIGHTS"})
            self._task(
                case,
                "ACCEPT_PROCESSING",
                "Verify authorization, existing ledger effects and channel acceptance requirements",
                now,
            )
        self._collaboration(case, data, identity, now, f"{decision}: {reason}", "MERCHANT_DECISION")

    def _on_resolve_response(self, case, data, identity, now):
        resolution = text_field(data, "resolution", limit=40)
        require(
            resolution in {"RESTORE_DECISION", "RESTORE_EVIDENCE", "CONFIRM_LOSS", "FOLLOW_UP"},
            "INVALID_RESOLUTION",
            "Unsupported response resolution",
            422,
        )
        reason = text_field(data, "reason", limit=1000)
        reference = text_field(data, "authorization_reference", limit=1000)
        if resolution.startswith("RESTORE"):
            deadline = timestamp(data.get("external_deadline", case["deadlines"].get("external")))
            require(
                deadline > timestamp(now),
                "EXTERNAL_DEADLINE_EXPIRED",
                "Restoration requires explicitly verified remaining external rights",
            )
            if resolution == "RESTORE_EVIDENCE":
                require(
                    case["merchant_decision"] == "CONTEST"
                    and "CONTEST" in case["rule_snapshot"].get("allowed_actions", []),
                    "CONTEST_NOT_ELIGIBLE",
                    "Restoring evidence requires the existing authorized Contest decision",
                )
            case["deadlines"]["external"] = deadline.isoformat()
            case["rule_snapshot"]["deadlines"] = deepcopy(case["deadlines"])
            case["eligibility_status"] = "CONFIRMED"
            self._invalidate(case, "Remaining rights reviewed", now)
            if resolution == "RESTORE_DECISION":
                case["response_history"].append(
                    {
                        "decision": case["merchant_decision"],
                        "authorization": deepcopy(case.get("merchant_authorization")),
                        "at": now,
                        "stage_number": case["stage_number"],
                    }
                )
                case["merchant_decision"] = "NONE"
                case["decision_response_status"] = "PENDING"
                case["work_status"] = "MERCHANT_ACTION_REQUIRED"
                self._task(
                    case, "DECISION", "Remaining rights confirmed; make an authorized decision", now
                )
            else:
                case["work_status"] = "EVIDENCE_COLLECTING"
                self._task(
                    case, "EVIDENCE", "Remaining rights confirmed; complete the evidence task", now
                )
        else:
            case["work_status"] = "WAITING_UPSTREAM"
            case["eligibility_status"] = (
                "RIGHTS_LOST" if resolution == "CONFIRM_LOSS" else "REQUIRES_RECONFIRMATION"
            )
            self._task(
                case,
                "UPSTREAM_FOLLOWUP",
                "Follow up upstream; confirmed loss of rights does not imply a terminal result",
                now,
            )
        case["response_history"].append(
            {
                "resolution": resolution,
                "reason": reason,
                "authorization_reference": reference,
                "actor_id": identity["actor_id"],
                "at": now,
                "stage_number": case["stage_number"],
            }
        )
        self._complete_tasks(
            case, now, {"RESPONSE_RIGHTS", "SLA_ESCALATION", "EVIDENCE_OVERDUE", "ESCALATION_HOLD"}
        )

    @staticmethod
    def _invalidate(case: dict, reason: str, now: str) -> None:
        case["evidence_version"] += 1
        DisputeService._resolve_tasks(
            case, now, {"OP_REVIEW", "FINAL_REVIEW", "DOCUMENT_REVISION"}, "SUPERSEDED", reason
        )
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
                "DOCUMENT_REVISION_REQUIRED",
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
        object_metadata = None
        provider = getattr(self, "evidence_objects", None)
        # A production-composed file provider makes new/revised evidence content-backed.
        # Old metadata-only snapshots remain readable; genuine command replays return
        # their original atomic receipt before this new-write requirement is evaluated.
        require(
            provider is None or reference.startswith("object:"),
            "EVIDENCE_FILE_REQUIRED",
            "Upload an actual case-bound file before registering new evidence",
            422,
        )
        if reference.startswith("object:"):
            object_id = reference.removeprefix("object:")
            require(
                provider is not None,
                "EVIDENCE_OBJECT_UNAVAILABLE",
                "Evidence object verification is unavailable",
                422,
            )
            object_metadata = provider.get_evidence_object(case["id"], object_id)
            require(
                isinstance(object_metadata, dict) and object_metadata.get("case_id") == case["id"],
                "EVIDENCE_OBJECT_NOT_FOUND",
                "Evidence object does not belong to this case",
                404,
            )
            require(
                object_metadata.get("code", object_metadata.get("content_check", {}).get("code"))
                == code,
                "EVIDENCE_OBJECT_CODE_MISMATCH",
                "File content was checked against a different evidence code",
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
        item.update(
            stage_number=case["stage_number"],
            applicable_stages=[case["stage_number"]],
            content_status="METADATA_ONLY",
        )
        if object_metadata:
            item.update(
                object_id=object_metadata.get("object_id", object_metadata.get("id")),
                sha256=object_metadata["sha256"],
                content_check=deepcopy(object_metadata["content_check"]),
                content_status=object_metadata["content_check"]["status"],
                uploaded_by=object_metadata.get("uploaded_by"),
            )
        if previous:
            item["history"] = previous.get("history", []) + [
                {k: v for k, v in previous.items() if k != "history"}
            ]
            case["evidence"][case["evidence"].index(previous)] = item
        else:
            case["evidence"].append(item)
        self._sync_content_review_task(case, now)
        self._task(case, "EVIDENCE", "Submit revised evidence for Risk review", now)

    def _sync_content_review_task(self, case, now):
        from oceanpilot.domain.dispute import evidence_applicable

        if any(
            evidence_applicable(case, item)
            and item.get("content_check", {}).get("status") == "NEEDS_MANUAL"
            for item in case["evidence"]
        ):
            self._task(case, "CONTENT_REVIEW", "人工核对真实文件正文、位置与本案适用事实", now)
        else:
            self._complete_tasks(case, now, {"CONTENT_REVIEW"})

    def _on_review_evidence_content(self, case, data, identity, now):
        from oceanpilot.domain.dispute import evidence_applicable

        self._evidence_open(case)
        evidence_id = text_field(data, "evidence_id", limit=100)
        item = next((e for e in case["evidence"] if e["id"] == evidence_id), None)
        require(
            item is not None and evidence_applicable(case, item) and item.get("object_id"),
            "EVIDENCE_OBJECT_NOT_FOUND",
            "A current case-bound file is required",
            404,
        )
        provider = getattr(self, "evidence_objects", None)
        require(
            provider is not None,
            "EVIDENCE_OBJECT_UNAVAILABLE",
            "File verification unavailable",
            422,
        )
        obj = provider.get_evidence_object(case["id"], item["object_id"])
        require(
            obj.get("case_id") == case["id"]
            and obj.get("sha256") == item.get("sha256")
            and obj.get("code") == item["code"],
            "EVIDENCE_OBJECT_MISMATCH",
            "The reviewed file must match the registered object",
            409,
        )
        require(
            obj.get("content_check", {}).get("status") == "NEEDS_MANUAL",
            "CONTENT_REVIEW_NOT_REQUIRED",
            "Known content-check failures require corrected evidence, not an override",
            409,
        )
        source_facts = obj["content_check"].get("facts", {})
        source_amount = str(source_facts.get("amount_minor", ""))
        require(
            source_facts.get("transaction_id") == case["transaction_id"]
            and source_facts.get("currency") == case["currency"]
            and len(source_amount) <= 30
            and source_amount.isdecimal()
            and int(source_amount) == case["amount_minor"],
            "CONTENT_ASSOCIATION_REQUIRED",
            "Re-upload a document with verified transaction, currency and amount association",
            409,
        )
        require(
            obj.get("uploaded_by") != identity["actor_id"],
            "REVIEWER_SEPARATION_REQUIRED",
            "File uploader cannot approve their own content",
            403,
        )
        decision = text_field(data, "decision", limit=30)
        require(
            decision in {"SUPPORTED", "INSUFFICIENT"},
            "INVALID_DECISION",
            "Choose content support",
            422,
        )
        reason = text_field(data, "reason", limit=1000)
        facts, locators = data.get("applicable_facts"), data.get("locators")
        require(
            isinstance(facts, list)
            and 1 <= len(facts) <= 20
            and all(isinstance(fact, str) and 1 <= len(fact.strip()) <= 1000 for fact in facts)
            and isinstance(locators, list)
            and 1 <= len(locators) <= 20
            and all(isinstance(locator, str) and len(locator) <= 20 for locator in locators),
            "INVALID_CONTENT_REVIEW",
            "Provide bounded source excerpts and line locators",
            422,
        )
        lines = obj.get("extracted_text", "").splitlines()
        selected = []
        for locator in locators:
            index = locator.removeprefix("line:")
            require(
                locator.startswith("line:")
                and index.isascii()
                and index.isdecimal()
                and 1 <= int(index) <= len(lines),
                "INVALID_CONTENT_LOCATOR",
                "Select an actual line of the stored document",
                422,
            )
            selected.append(lines[int(index) - 1])
        require(
            all(any(fact.strip() in line for line in selected) for fact in facts),
            "CONTENT_EXCERPT_MISMATCH",
            "Each cited fact must occur in the selected document lines",
            422,
        )
        self._invalidate(case, "Independent manual content assessment changed", now)
        review = {
            "decision": decision,
            "reason": reason,
            "applicable_facts": deepcopy(facts),
            "locators": deepcopy(locators),
            "reviewer": identity["actor_id"],
            "at": now,
            "object_id": item["object_id"],
            "sha256": item["sha256"],
            "evidence_revision": item["revision"],
            "stage_number": case["stage_number"],
        }
        item.setdefault("content_reviews", []).append(review)
        item["content_check"] = {
            "status": decision,
            "method": "INDEPENDENT_HUMAN_CONTENT_REVIEW",
            "automatic_check": deepcopy(obj["content_check"]),
            "manual_review": review,
            "locators": deepcopy(locators),
            "findings": [reason],
            "boundary": (
                "Human applicability review does not replace evidence or final package approval"
            ),
        }
        item["content_status"] = decision
        item["content_verified"] = decision == "SUPPORTED"
        self._sync_content_review_task(case, now)
        self._task(
            case, "EVIDENCE", "Submit current content-assessed evidence for Risk review", now
        )

    def _on_withdraw_evidence(self, case, data, identity, now):
        self._evidence_open(case)
        evidence_id = text_field(data, "evidence_id", limit=200)
        reason = text_field(data, "reason")
        item = next((e for e in case["evidence"] if e["id"] == evidence_id and e["active"]), None)
        require(item is not None, "EVIDENCE_NOT_FOUND", "Active evidence item not found", 404)
        item.update(active=False, withdrawn_at=now, withdrawal_reason=reason)
        self._invalidate(case, "Evidence withdrawn", now)
        self._sync_content_review_task(case, now)
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
        case["evidence_task_status"] = "SUBMITTED"
        self._complete_tasks(case, now, {"EVIDENCE", "REVISION", "EVIDENCE_OVERDUE"})
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
            from oceanpilot.domain.dispute import evidence_applicable

            require(
                not any(
                    evidence_applicable(case, e)
                    and e.get("object_id")
                    and e.get("content_check", {}).get("status") != "SUPPORTED"
                    for e in case["evidence"]
                ),
                "CONTENT_CHECK_REQUIRED",
                "Active file content requires review before evidence approval",
            )
            case["work_status"] = "READY_TO_SUBMIT"
        elif decision == "REVISION":
            case["work_status"] = "MERCHANT_REVISION_REQUIRED"
            self._task(case, "REVISION", reason, now)
        else:
            case["work_status"] = "ACCEPT_RECOMMENDATION"
            self._task(
                case,
                "ACCEPT_DECISION",
                (
                    f"Recommendation only: {reason}. Proposed responsibility "
                    f"{case['amount_minor']} {case['currency']} minor units; "
                    "merchant or authorized operator must decide."
                ),
                now,
            )
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
            case["work_status"] in {"READY_TO_SUBMIT", "DOCUMENT_REVISION_REQUIRED"},
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
            limit=10000,
        )
        from oceanpilot.domain.dispute import evidence_applicable

        self._complete_tasks(case, now, {"DOCUMENT_REVISION"})
        package = {
            "id": uuid4().hex,
            "version": len(case["packages"]) + 1,
            "status": "DRAFT",
            "evidence_version": case["evidence_version"],
            "stage_number": case["stage_number"],
            "evidence_index": deepcopy(
                [e for e in case["evidence"] if evidence_applicable(case, e)]
            ),
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

    def _on_final_review(self, case, data, identity, now):
        decision = text_field(data, "decision", limit=40)
        require(
            decision
            in {"APPROVE", "RETURN_MATERIALS", "RETURN_DOCUMENT", "RECOMMEND_ACCEPT", "HOLD"},
            "INVALID_DECISION",
            "Unsupported final review decision",
            422,
        )
        reason = text_field(data, "reason", limit=1000)
        if decision == "APPROVE":
            require(
                case["work_status"] == "SUBMISSION_PENDING_CONFIRMATION",
                "INVALID_STATE",
                "A held package must be rebuilt before approval",
            )
            self._on_approve_package(case, data, identity, now)
            return
        package = self._package(case, data)
        package.update(status="INVALIDATED", invalidation_reason=reason, invalidated_at=now)
        self._complete_tasks(case, now, {"FINAL_REVIEW", "ESCALATION_HOLD"})
        if decision == "RETURN_MATERIALS":
            self._invalidate(case, reason, now)
            case["work_status"] = "MERCHANT_REVISION_REQUIRED"
            self._task(case, "REVISION", reason, now)
        elif decision == "RETURN_DOCUMENT":
            case["work_status"] = "DOCUMENT_REVISION_REQUIRED"
            self._task(case, "DOCUMENT_REVISION", reason, now)
        elif decision == "RECOMMEND_ACCEPT":
            case["work_status"] = "ACCEPT_RECOMMENDATION"
            self._task(
                case,
                "ACCEPT_DECISION",
                f"Recommendation only: {reason}; obtain explicit merchant liability authorization",
                now,
            )
        else:
            case["work_status"] = "ON_HOLD"
            self._task(case, "ESCALATION_HOLD", reason, now)
        case["reviews"].append(
            {
                "id": uuid4().hex,
                "type": "FINAL",
                "decision": decision,
                "reviewer": identity["actor_id"],
                "role": identity["role"],
                "reason": reason,
                "package_id": package["id"],
                "evidence_version": case["evidence_version"],
                "case_revision": case["revision"],
                "valid": False,
                "at": now,
            }
        )

    def _on_reuse_evidence(self, case, data, identity, now):
        ids = data.get("evidence_ids")
        require(
            isinstance(ids, list)
            and bool(ids)
            and len(ids) <= 100
            and all(isinstance(i, str) for i in ids),
            "INVALID_INPUT",
            "Select evidence ids for applicability review",
            422,
        )
        reason = text_field(data, "reason", limit=1000)
        selected = [e for e in case["evidence"] if e["id"] in ids and e["active"]]
        require(
            len(selected) == len(set(ids)),
            "EVIDENCE_NOT_FOUND",
            "Selected active evidence does not exist",
            404,
        )
        self._invalidate(case, "Evidence applicability changed", now)
        for item in selected:
            item.setdefault("applicable_stages", [item.get("stage_number", 1)])
            if case["stage_number"] not in item["applicable_stages"]:
                item["applicable_stages"].append(case["stage_number"])
            item.setdefault("applicability_reviews", []).append(
                {
                    "stage_number": case["stage_number"],
                    "actor_id": identity["actor_id"],
                    "reason": reason,
                    "at": now,
                }
            )
        self._complete_tasks(case, now, {"EVIDENCE_APPLICABILITY"})

    def _on_submit(self, case, data, identity, now):
        require(
            self.upstream_mode == "mock", "UPSTREAM_DISABLED", "Upstream submission is disabled"
        )
        self._rule_ready(case)
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
        previous = next(
            (item for item in case["submissions"] if item["package_id"] == package["id"]), None
        )
        if previous:
            require(
                previous.get("retry_authorized") is True,
                "ALREADY_SUBMITTED",
                "Query the existing business request before any retry",
            )
        receipt = previous or {
            "id": f"mock-{package['id']}",
            "package_id": package["id"],
            "package_digest": package["digest"],
            "mode": "MOCK",
            "request_id": self._safe_reference("request", package["id"]),
            "receipt_id": self._safe_reference("receipt", package["id"]),
            "idempotency_key": f"{case['id']}:{package['id']}",
            "submitted_by": identity["actor_id"],
            "production_eligible": False,
            "attempts": [],
        }
        self._mock_attempt(receipt, data, identity, now)
        if not previous:
            case["submissions"].append(receipt)
        case["work_status"] = (
            "WAITING_UPSTREAM"
            if receipt["business_acceptance"] == "MOCK_ACCEPTED"
            else "SUBMISSION_UNCERTAIN"
        )
        if case["work_status"] == "SUBMISSION_UNCERTAIN":
            self._task(
                case,
                "SUBMISSION_QUERY",
                "Query this business request identity before deciding whether to retry",
                now,
            )

    @staticmethod
    def _safe_reference(prefix, token):
        # Derived identifiers must not accidentally resemble payment-card digit runs.
        return prefix + ":" + "g".join(token[i : i + 8] for i in range(0, len(token), 8))

    @staticmethod
    def _mock_attempt(receipt, data, identity, now):
        scenario = text_field(data, "mock_scenario", default="ACCEPTED", limit=40)
        require(
            scenario
            in {"ACCEPTED", "TECHNICAL_FAILURE", "BUSINESS_REJECTED", "TIMEOUT", "RESPONSE_LOST"},
            "INVALID_MOCK_SCENARIO",
            "Unsupported mock transport scenario",
            422,
        )
        receipt.update(
            transport_state="DELIVERED"
            if scenario in {"ACCEPTED", "BUSINESS_REJECTED"}
            else "FAILED"
            if scenario == "TECHNICAL_FAILURE"
            else "UNKNOWN",
            business_acceptance="MOCK_ACCEPTED"
            if scenario == "ACCEPTED"
            else "MOCK_REJECTED"
            if scenario == "BUSINESS_REJECTED"
            else "UNKNOWN",
            submitted_at=now,
            retry_authorized=False,
        )
        receipt["attempts"].append(
            {
                "number": len(receipt["attempts"]) + 1,
                "scenario": scenario,
                "at": now,
                "actor_id": identity["actor_id"],
                "request_id": receipt["request_id"],
            }
        )

    def _on_query_submission(self, case, data, identity, now):
        request_id = text_field(data, "request_id", limit=200)
        result = text_field(data, "result", limit=40)
        require(
            result in {"ACCEPTED", "NOT_ACCEPTED", "UNKNOWN"},
            "INVALID_QUERY_RESULT",
            "Unsupported mock query result",
            422,
        )
        reason = text_field(data, "reason", limit=1000)
        receipt = next(
            (r for r in case["submissions"] + case["acceptances"] if r["request_id"] == request_id),
            None,
        )
        require(
            receipt is not None,
            "SUBMISSION_NOT_FOUND",
            "Business request does not belong to this case",
            404,
        )
        require(
            receipt.get("business_acceptance") != "MOCK_ACCEPTED",
            "ALREADY_ACCEPTED",
            "Accepted business requests cannot be retried",
        )
        scenario = receipt["attempts"][-1]["scenario"]
        if scenario == "RESPONSE_LOST":
            require(
                result in {"ACCEPTED", "UNKNOWN"},
                "QUERY_RESULT_CONFLICT",
                "The synthetic channel already accepted this request",
            )
        if scenario in {"TECHNICAL_FAILURE", "BUSINESS_REJECTED"}:
            require(
                result in {"NOT_ACCEPTED", "UNKNOWN"},
                "QUERY_RESULT_CONFLICT",
                "The synthetic channel did not accept this request",
            )
        receipt.setdefault("queries", []).append(
            {"result": result, "reason": reason, "actor_id": identity["actor_id"], "at": now}
        )
        receipt["retry_authorized"] = result == "NOT_ACCEPTED"
        if result == "ACCEPTED":
            receipt.update(business_acceptance="MOCK_ACCEPTED", transport_state="DELIVERED")
            case["work_status"] = "WAITING_UPSTREAM"
            self._complete_tasks(case, now, {"SUBMISSION_QUERY", "ACCEPT_PROCESSING"})
        elif result == "NOT_ACCEPTED":
            receipt["business_acceptance"] = "MOCK_NOT_ACCEPTED"
            case["work_status"] = (
                "ACCEPT_PROCESSING" if receipt.get("action") == "ACCEPT" else "READY_TO_SUBMIT"
            )
            self._complete_tasks(case, now, {"SUBMISSION_QUERY"})

    def _on_process_accept(self, case, data, identity, now):
        require(
            case["merchant_decision"] in {"ACCEPT", "AUTHORIZED_WAIVER"},
            "ACCEPT_AUTHORIZATION_REQUIRED",
            "An explicit authorized acceptance is required",
        )
        require(
            "ACCEPT" in case["rule_snapshot"].get("allowed_actions", []),
            "ACTION_NOT_ALLOWED",
            "Current rule does not permit acceptance",
        )
        authorization = case.get("merchant_authorization", {})
        require(
            authorization.get("decision") == case["merchant_decision"],
            "ACCEPT_AUTHORIZATION_REQUIRED",
            "Current acceptance authorization is missing",
        )
        reason = text_field(data, "reason", limit=1000)
        reference = text_field(data, "reference", limit=1000)
        mode = text_field(data, "mode", default="MOCK", limit=40)
        require(
            mode in {"MOCK", "NO_ACTION_REQUIRED"},
            "INVALID_CHANNEL_ACTION",
            "Choose mock channel processing or a verified no-action basis",
            422,
        )
        previous = next(
            (
                r
                for r in case["acceptances"]
                if r["stage_number"] == case["stage_number"]
                and r["authorization_at"] == authorization["at"]
            ),
            None,
        )
        require(
            previous is None or previous.get("retry_authorized"),
            "ALREADY_PROCESSED",
            "Acceptance already has a channel request; query its receipt",
        )
        token = uuid4().hex
        receipt = previous or {
            "id": token,
            "action": "ACCEPT",
            "stage_number": case["stage_number"],
            "authorization_at": authorization["at"],
            "authorization": deepcopy(authorization),
            "amount_minor": case["amount_minor"],
            "currency": case["currency"],
            "request_id": self._safe_reference("accept", token),
            "receipt_id": self._safe_reference("accept-receipt", token),
            "mode": "MOCK",
            "production_eligible": False,
            "attempts": [],
        }
        receipt.update(
            reason=reason,
            reference=reference,
            ledger_check={
                "financial_version": case["financial_version"],
                "existing_event_ids": [e["id"] for e in case["financial_events"]],
                "net_minor": sum(e["net_minor"] for e in case["financial_events"]),
                "checked_by": identity["actor_id"],
                "at": now,
            },
        )
        if mode == "MOCK":
            require(
                self.upstream_mode == "mock", "UPSTREAM_DISABLED", "Upstream processing is disabled"
            )
            self._mock_attempt(receipt, data, identity, now)
        else:
            receipt.update(
                mode="NO_ACTION_REQUIRED",
                transport_state="NOT_REQUIRED",
                business_acceptance="NO_ACTION_REQUIRED",
                basis_reference=reference,
                confirmed_by=identity["actor_id"],
                confirmed_at=now,
            )
        if not previous:
            case["acceptances"].append(receipt)
        if receipt["business_acceptance"] in {"MOCK_ACCEPTED", "NO_ACTION_REQUIRED"}:
            case["work_status"] = "WAITING_UPSTREAM"
            self._complete_tasks(case, now, {"ACCEPT_PROCESSING"})
        else:
            case["work_status"] = "SUBMISSION_UNCERTAIN"
            self._task(
                case,
                "SUBMISSION_QUERY",
                "Query the acceptance request before repeating channel processing",
                now,
            )

    def _on_record_outcome(self, case, data, identity, now):
        outcome = text_field(data, "outcome", limit=40)
        require(
            outcome in {o.value for o in BusinessOutcome},
            "INVALID_OUTCOME",
            "Record an explicit upstream business outcome",
            422,
        )
        require(type(data.get("final")) is bool, "INVALID_FINALITY", "final must be boolean", 422)
        require(
            outcome != "UNKNOWN" or not data["final"],
            "UNKNOWN_FINAL_OUTCOME",
            "An unknown outcome cannot be marked final",
        )
        if data.get("reason") is not None:
            require(
                isinstance(data["reason"], str) and len(data["reason"]) <= 1000,
                "INVALID_INPUT",
                "reason must be text of at most 1000 characters",
                422,
            )
        if data.get("next_stage") is not None:
            text_field(data, "next_stage", limit=50)
        if data.get("disposition") is not None:
            text_field(data, "disposition", limit=40)
        if data.get("mapped_outcome") is not None:
            text_field(data, "mapped_outcome", limit=40)
        disposition = data.get("disposition") or (
            "FINAL"
            if data["final"]
            else "NEXT_STAGE"
            if data.get("next_stage")
            else "VERIFY"
            if outcome in {"UNKNOWN", "OTHER"}
            else "WAIT"
        )
        require(
            disposition in {"WAIT", "VERIFY", "ACTION", "NEXT_STAGE", "FINAL"},
            "INVALID_DISPOSITION",
            "Choose how the current stage should proceed",
            422,
        )
        require(
            not data["final"] or disposition in {"FINAL", "VERIFY"},
            "INVALID_FINALITY",
            "A terminal outcome must be finalized or verified",
            422,
        )
        require(
            data["final"] or disposition != "FINAL",
            "INVALID_FINALITY",
            "Nonterminal events cannot use final disposition",
            422,
        )
        if data.get("next_stage"):
            require(
                not data["final"]
                and disposition == "NEXT_STAGE"
                and outcome not in {"UNKNOWN", "OTHER"},
                "INVALID_STAGE",
                "Only a verified nonterminal next-stage event may advance",
                422,
            )
        if outcome == "OTHER" and data["final"]:
            require(
                data.get("mapped_outcome")
                in {"WON", "LOST", "PARTIAL", "ACCEPTED_RESPONSIBILITY", "WITHDRAWN"}
                and bool(data.get("basis_reference"))
                and bool(data.get("authorization_reference")),
                "OUTCOME_MAPPING_REQUIRED",
                "Custom terminal outcomes require a mapped type, source basis and authorization",
            )
        if data.get("mapped_outcome") is not None:
            require(
                data["mapped_outcome"]
                in {"WON", "LOST", "PARTIAL", "ACCEPTED_RESPONSIBILITY", "WITHDRAWN"},
                "OUTCOME_MAPPING_REQUIRED",
                "Unsupported custom terminal mapping",
                422,
            )
        source = text_field(data, "source", limit=200)
        event_id = text_field(data, "event_id", limit=200)
        stage_number = data.get("stage_number", case["stage_number"])
        require(
            type(stage_number) is int and stage_number > 0,
            "INVALID_STAGE",
            "stage_number must be positive",
            422,
        )
        for key in ("occurred_at", "received_at"):
            if data.get(key) is not None:
                timestamp(data[key])
        for key in ("basis_reference", "authorization_reference", "corrects_event_id"):
            if data.get(key) is not None:
                text_field(data, key, limit=1000)
        if case.get("reopened_for_correction"):
            require(
                bool(data.get("corrects_event_id")) and bool(data.get("basis_reference")),
                "CORRECTION_BASIS_REQUIRED",
                "A reopened record requires a source-backed correction to its original outcome",
                422,
            )
        if data.get("corrects_event_id"):
            prior = next(
                (
                    e
                    for e in case["upstream_events"]
                    if e.get("event_id", e.get("id")) == data["corrects_event_id"]
                    and e.get("type") == "OUTCOME"
                ),
                None,
            )
            require(
                prior is not None,
                "CORRECTION_TARGET_NOT_FOUND",
                "Correction must reference a persisted outcome event",
                422,
            )
            require(
                prior.get("stage_number") == stage_number,
                "CORRECTION_STAGE_MISMATCH",
                "Correction must cover the same source stage",
                422,
            )
        self._validate_outcome_amounts(case, data)
        needs_verification = (
            disposition == "VERIFY"
            or outcome in {"UNKNOWN", "OTHER"}
            or bool(data.get("corrects_event_id"))
            or stage_number != case["stage_number"]
            or case["work_status"] not in {"WAITING_UPSTREAM", "UPSTREAM_ACTION_REQUIRED"}
        )
        event = {
            "id": event_id,
            "event_id": event_id,
            "type": "OUTCOME",
            "source": source,
            "outcome": outcome,
            "final": data["final"],
            "disposition": disposition,
            "reason": data.get("reason"),
            "at": now,
            "occurred_at": data.get("occurred_at"),
            "received_at": data.get("received_at"),
            "stage_number": stage_number,
            "verification": "PENDING" if needs_verification else "CONFIRMED",
            "payload": deepcopy(data),
            "previous_work_status": case["work_status"],
        }
        case["upstream_events"].append(event)
        if needs_verification:
            case.setdefault("verification_resume_status", case["work_status"])
            case["outcome_verification_required"] = True
            case["work_status"] = "OUTCOME_VERIFICATION"
            self._task(
                case,
                "OUTCOME_CONFIRMATION",
                (
                    "Verify source, case association, stage, terminal basis "
                    "and any correction coverage"
                ),
                now,
            )
        else:
            self._apply_outcome(case, event, identity, now)

    @staticmethod
    def _validate_outcome_amounts(case, data):
        effective = data.get("mapped_outcome") if data["outcome"] == "OTHER" else data["outcome"]
        # A supplied currency validates the source unit; it does not declare an
        # explicit allocation. Full WON/LOST outcomes infer their allocation in
        # _apply_outcome, while PARTIAL still requires both amounts and currency.
        if data.get("currency") is not None:
            require(
                currency_code(data["currency"]) == case["currency"],
                "CURRENCY_MISMATCH",
                "Outcome allocation must use the dispute currency",
                422,
            )
        has_amounts = any(data.get(k) is not None for k in ("supported_minor", "liable_minor"))
        if has_amounts or (effective == "PARTIAL" and data["final"]):
            supported = minor_units(data.get("supported_minor"))
            liable = minor_units(data.get("liable_minor"))
            require(
                currency_code(data.get("currency")) == case["currency"],
                "CURRENCY_MISMATCH",
                "Outcome allocation must use the dispute currency",
                422,
            )
            require(
                supported + liable == case["amount_minor"],
                "INVALID_OUTCOME_ALLOCATION",
                "Supported plus liable amounts must equal disputed amount",
                422,
            )
            if effective == "PARTIAL":
                require(
                    supported > 0 and liable > 0,
                    "INVALID_OUTCOME_ALLOCATION",
                    "Partial support requires positive supported and liable amounts",
                    422,
                )

    def _on_verify_outcome(self, case, data, identity, now):
        event_id = text_field(data, "event_id", limit=200)
        decision = text_field(data, "decision", limit=40)
        require(
            decision in {"CONFIRM", "REJECT"}, "INVALID_DECISION", "Choose confirm or reject", 422
        )
        reason = text_field(data, "reason", limit=1000)
        reference = text_field(data, "authorization_reference", limit=1000)
        event = next(
            (
                e
                for e in reversed(case["upstream_events"])
                if e.get("event_id", e.get("id")) == event_id and e.get("verification") == "PENDING"
            ),
            None,
        )
        require(
            event is not None, "OUTCOME_EVENT_NOT_FOUND", "A pending source event is required", 404
        )
        if decision == "CONFIRM":
            require(
                event["stage_number"] == case["stage_number"],
                "EVENT_STAGE_MISMATCH",
                "An event for another stage cannot decide the current stage",
            )
            require(
                event["outcome"] != "UNKNOWN"
                and (event["outcome"] != "OTHER" or event["payload"].get("mapped_outcome")),
                "OUTCOME_MAPPING_REQUIRED",
                "Unknown or unmapped outcomes require source clarification",
            )
            require(
                bool(event["source"]), "SOURCE_REQUIRED", "Verified upstream source is required"
            )
            self._apply_outcome(case, event, identity, now)
        else:
            case["work_status"] = case.get(
                "verification_resume_status", event["previous_work_status"]
            )
        event.update(
            verification="CONFIRMED" if decision == "CONFIRM" else "REJECTED",
            verified_by=identity["actor_id"],
            verified_at=now,
            verification_reason=reason,
            authorization_reference=reference,
        )
        pending = any(e.get("verification") == "PENDING" for e in case["upstream_events"])
        case["outcome_verification_required"] = pending
        if pending:
            case["work_status"] = "OUTCOME_VERIFICATION"
        else:
            case.pop("verification_resume_status", None)
            self._complete_tasks(case, now, {"OUTCOME_CONFIRMATION"})

    def _apply_outcome(self, case, event, identity, now):
        data = event["payload"]
        outcome = data["outcome"]
        case["outcome_history"].append(
            {
                "business_outcome": case["business_outcome"],
                "current_stage_outcome": case.get("current_stage_outcome"),
                "finality": case["finality"],
                "outcome_version": case.get("outcome_version", 0),
                "amounts": deepcopy(case.get("outcome_amounts")),
                "at": now,
                "stage_number": case["stage_number"],
                "replaced_by_event_id": event["event_id"],
            }
        )
        case["outcome_version"] += 1
        case["business_outcome"] = outcome
        case["current_stage_outcome"] = outcome
        case["last_known_outcome"] = outcome
        case["finality"] = "FINAL_CONFIRMED" if data["final"] else "NOT_FINAL"
        case["merchant_notification_completed"] = False
        case["outcome_verification_required"] = False
        case["pending_next_stage"] = False
        case["reopened_for_correction"] = False
        if outcome == "OTHER":
            case["outcome_mapping"] = {
                "mapped_outcome": data["mapped_outcome"],
                "basis_reference": data["basis_reference"],
                "authorization_reference": data["authorization_reference"],
                "verified_by": identity["actor_id"],
                "event_id": event["event_id"],
            }
        else:
            case.pop("outcome_mapping", None)
        effective = data.get("mapped_outcome", outcome)
        supported = data.get("supported_minor")
        liable = data.get("liable_minor")
        if (
            data["final"]
            and supported is None
            and effective in {"WON", "LOST", "ACCEPTED_RESPONSIBILITY", "WITHDRAWN"}
        ):
            liable = case["amount_minor"] if effective in {"LOST", "ACCEPTED_RESPONSIBILITY"} else 0
            supported = case["amount_minor"] - liable
        case["outcome_amounts"] = {
            "supported_minor": supported,
            "liable_minor": liable,
            "currency": case["currency"],
            "event_id": event["event_id"],
            "basis_reference": data.get("basis_reference") or event["source"],
            "source_type": "SYNTHETIC_OUTCOME",
        }
        if data["final"]:
            self._resolve_tasks(
                case,
                now,
                {
                    "DECISION",
                    "EVIDENCE",
                    "REVISION",
                    "OP_REVIEW",
                    "FINAL_REVIEW",
                    "DOCUMENT_REVISION",
                    "ACCEPT_DECISION",
                    "ACCEPT_PROCESSING",
                    "RESPONSE_RIGHTS",
                    "SLA_ESCALATION",
                    "SLA_REMINDER",
                    "EVIDENCE_OVERDUE",
                    "NEXT_STAGE",
                    "UPSTREAM_FOLLOWUP",
                    "UPSTREAM_ACTION",
                    "EVIDENCE_APPLICABILITY",
                    "CONTENT_REVIEW",
                },
                "CANCELLED",
                "Confirmed terminal source event supersedes pending dispute work",
            )
            self._invalidate(case, "Confirmed terminal upstream outcome", now)
            case["work_status"] = "FINANCIAL_RECONCILIATION"
            case["financial_status"] = "PENDING"
            self._task(
                case,
                "FINANCIAL_RECONCILIATION",
                "Reconcile synthetic ledger against the current confirmed outcome",
                now,
            )
        elif event["disposition"] == "NEXT_STAGE":
            case["pending_next_stage"] = True
            case["work_status"] = "TRIAGED"
            self._task(
                case, "NEXT_STAGE", "Confirm the actual next-stage event and source time", now
            )
            if data.get("next_stage"):
                self._advance_stage(
                    case, data["next_stage"], event["source"], event["event_id"], now, data
                )
        elif event["disposition"] == "ACTION":
            case["work_status"] = "UPSTREAM_ACTION_REQUIRED"
            self._task(
                case, "UPSTREAM_ACTION", "Resolve the source-required action within this stage", now
            )
        else:
            case["work_status"] = "WAITING_UPSTREAM"
        if "verification_resume_status" in case:
            case["verification_resume_status"] = case["work_status"]

    def _on_reopen_case(self, case, data, identity, now):
        reason = text_field(data, "reason", limit=1000)
        authorization = text_field(data, "authorization_reference", limit=1000)
        event_reference = text_field(data, "event_reference", limit=1000)
        require(
            case["finality"] == "FINAL_CONFIRMED",
            "FINALITY_REQUIRED",
            "Only a terminal record can be reopened for correction",
        )
        case["closure_history"].append(
            {
                "work_status": case["work_status"],
                "closed_at": case.get("closed_at"),
                "closed_by": case.get("closed_by"),
                "outcome": case["business_outcome"],
                "outcome_version": case["outcome_version"],
                "reconciliation": deepcopy(case.get("reconciliation")),
                "notification": deepcopy(case.get("merchant_notification")),
                "reopened_at": now,
                "reopened_by": identity["actor_id"],
                "reason": reason,
                "authorization_reference": authorization,
                "event_reference": event_reference,
            }
        )
        case["reopened_for_correction"] = True
        case["work_status"] = "WAITING_UPSTREAM"
        case["finality"] = "NOT_FINAL"
        case["financial_status"] = "PENDING"
        case["merchant_notification_completed"] = False
        self._task(
            case,
            "OUTCOME_CONFIRMATION",
            "Verify the authorized source correction before issuing a replacement terminal result",
            now,
        )

    def _on_next_stage(self, case, data, identity, now):
        require(
            case["finality"] == "NOT_FINAL" and case.get("pending_next_stage"),
            "NEXT_STAGE_NOT_ALLOWED",
            "A confirmed next-stage disposition must precede a new stage",
        )
        self._advance_stage(
            case,
            text_field(data, "stage", limit=50),
            text_field(data, "source", limit=200),
            text_field(data, "event_id", limit=200),
            now,
            data,
        )

    def _advance_stage(self, case, stage, source, event_id, now, source_data=None):
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
                            "current_stage_outcome",
                            "outcome_version",
                            "finality",
                            "merchant_decision",
                            "evidence",
                            "reviews",
                            "packages",
                            "submissions",
                        )
                    }
                ),
                "outcome_amounts": deepcopy(case.get("outcome_amounts", {})),
                "ended_at": now,
                "source": source,
                "event_id": event_id,
            }
        )
        self._resolve_tasks(
            case,
            now,
            {
                "DECISION",
                "EVIDENCE",
                "REVISION",
                "OP_REVIEW",
                "FINAL_REVIEW",
                "DOCUMENT_REVISION",
                "ACCEPT_DECISION",
                "RESPONSE_RIGHTS",
                "SLA_ESCALATION",
                "SLA_REMINDER",
                "EVIDENCE_OVERDUE",
                "UPSTREAM_ACTION",
                "UPSTREAM_FOLLOWUP",
                "EVIDENCE_APPLICABILITY",
                "CONTENT_REVIEW",
            },
            "SUPERSEDED",
            "Confirmed new stage supersedes prior-stage work",
        )
        self._complete_tasks(case, now, {"NEXT_STAGE"})
        source_data = source_data or {}
        occurred = source_data.get("occurred_at")
        received = source_data.get("received_at")
        if occurred:
            timestamp(occurred)
        if received:
            timestamp(received)
        candidate_time = received or occurred or now
        matching_channel = "CURATED_REFERENCE" if case.get("library_reference") else case["channel"]
        next_rule = self.rule_matcher(
            case["scheme"], matching_channel, case["reason_code"], stage, candidate_time
        )
        policy = next_rule.get("deadline_policy", {})
        basis = policy.get("anchor_field") or policy.get("basis")
        anchor = (
            occurred if basis == "occurred_at" else received if basis == "received_at" else None
        )
        if anchor and anchor != candidate_time:
            next_rule = self.rule_matcher(
                case["scheme"], matching_channel, case["reason_code"], stage, anchor
            )
        case["last_known_outcome"] = case["business_outcome"]
        case["current_stage_outcome"] = "UNKNOWN"
        case["business_outcome"] = "UNKNOWN"
        case["outcome_amounts"] = {}
        case["merchant_notification_completed"] = False
        case["stage"] = stage
        case["stage_number"] += 1
        case["pending_next_stage"] = False
        case["rule_snapshot"] = next_rule
        case["deadlines"] = deepcopy(case["rule_snapshot"].get("deadlines", {}))
        case["stage_time_basis"] = {
            "occurred_at": occurred,
            "received_at": received,
            "anchor": anchor,
            "basis": basis,
            "recorded_at": now,
            "source": source,
            "event_id": event_id,
        }
        if not anchor:
            case["rule_snapshot"]["conflict_status"] = "NEEDS_CONFIRMATION"
            case["deadlines"] = {
                "merchant": None,
                "internal": None,
                "external": None,
                "status": "NEEDS_CONFIRMATION",
                "source": source,
            }
        if source_data.get("external_deadline"):
            external = timestamp(source_data["external_deadline"]).isoformat()
            case["deadlines"]["external"] = external
            # Explicit channel deadline never turns unknown source policy into confirmed rights.
            for key in ("merchant", "internal"):
                if case["deadlines"].get(key) and timestamp(case["deadlines"][key]) > timestamp(
                    external
                ):
                    case["deadlines"][key] = external
        case["rule_snapshot"]["deadlines"] = deepcopy(case["deadlines"])
        self._invalidate(case, "New upstream stage", now)
        case["merchant_decision"] = "NONE"
        case["decision_response_status"] = "PENDING"
        case["evidence_task_status"] = "PENDING"
        case["eligibility_status"] = "CONFIRMED"
        case["work_status"] = (
            "TRIAGED" if case["rule_snapshot"].get("conflict_status") == "VERIFIED" else "RECEIVED"
        )
        if any(e.get("active") for e in case["evidence"]):
            self._task(
                case,
                "EVIDENCE_APPLICABILITY",
                (
                    "Review prior-stage evidence applicability; old evidence "
                    "does not automatically satisfy this stage"
                ),
                now,
            )
        case["upstream_events"].append(
            {
                "id": event_id,
                "event_id": event_id,
                "type": "NEXT_STAGE",
                "stage": stage,
                "stage_number": case["stage_number"],
                "source": source,
                "at": now,
                "occurred_at": occurred,
                "received_at": received,
            }
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
        if case.get("reconciliation"):
            case["reconciliation_history"].append(deepcopy(case["reconciliation"]))
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
            "outcome_version": case.get("outcome_version", 0),
            "source_type": "SYNTHETIC_LEDGER_RECONCILIATION",
            "production_eligible": False,
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
        if case.get("merchant_notification"):
            case["notification_history"].append(deepcopy(case["merchant_notification"]))
        case["merchant_notification"] = {
            "outcome_version": case.get("outcome_version", 0),
            "financial_version": case["financial_version"],
            "at": now,
            "actor_id": identity["actor_id"],
            "message": message,
            "delivery_status": case["collaboration"][-1]["delivery_status"],
        }
        case["merchant_notification_completed"] = case[
            "finality"
        ] == "FINAL_CONFIRMED" and not case.get("outcome_verification_required")

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
        deadline = timestamp(case["deadlines"]["merchant"])
        current = timestamp(now)
        if current > deadline:
            if case["merchant_decision"] == "CONTEST" and case["work_status"] in {
                "EVIDENCE_COLLECTING",
                "MERCHANT_REVISION_REQUIRED",
            }:
                case["evidence_task_status"] = "OVERDUE"
                self._task(
                    case,
                    "EVIDENCE_OVERDUE",
                    (
                        "Merchant already contested; evidence is late. Verify remaining rights "
                        "without changing that decision."
                    ),
                    now,
                )
            elif case["merchant_decision"] == "NONE":
                self._task(
                    case,
                    "SLA_ESCALATION",
                    (
                        "Decision deadline expired; verify whether any valid "
                        "merchant response was received"
                    ),
                    now,
                )
        elif current + timedelta(days=1) >= deadline and case["merchant_decision"] in {
            "NONE",
            "CONTEST",
        }:
            self._task(case, "SLA_REMINDER", "Merchant task deadline within 24 hours", now)

    def _on_resolve_task(self, case, data, identity, now):
        task_id = text_field(data, "task_id", limit=200)
        status = text_field(data, "resolution", limit=40)
        require(
            status in {"CANCELLED", "WAIVED", "SUPERSEDED"},
            "INVALID_TASK_RESOLUTION",
            "Use a truthful cancellation, waiver or replacement",
            422,
        )
        reason = text_field(data, "reason", limit=1000)
        task = next(
            (t for t in case["tasks"] if t["id"] == task_id and t["status"] == "OPEN"), None
        )
        require(task is not None, "TASK_NOT_FOUND", "An open task is required", 404)
        protected = {
            "CONTENT_REVIEW",
            "OP_REVIEW",
            "FINAL_REVIEW",
            "OUTCOME_CONFIRMATION",
            "FINANCIAL_RECONCILIATION",
            "RESPONSE_RIGHTS",
            "ACCEPT_PROCESSING",
        }
        require(
            task["type"] not in protected,
            "TASK_REQUIRES_BUSINESS_ACTION",
            "Required authority and financial gates must be resolved by their business command",
        )
        replacement = None
        if status == "SUPERSEDED":
            replacement = text_field(data, "replacement_task_id", limit=200)
            require(
                any(
                    t["id"] == replacement and t["status"] == "OPEN" and t["id"] != task_id
                    for t in case["tasks"]
                ),
                "REPLACEMENT_TASK_REQUIRED",
                "An existing open replacement task is required",
                422,
            )
        task.update(
            status=status,
            resolved_at=now,
            resolution={
                "status": status,
                "reason": reason,
                "actor_id": identity["actor_id"],
                "role": identity["role"],
                "revision": case["revision"] + 1,
                "at": now,
                "replacement_task_id": replacement,
            },
        )

    def _on_assign_case(self, case, data, identity, now):
        user_id = text_field(data, "user_id", limit=200)
        reason = text_field(data, "reason", limit=1000)
        policy = getattr(self, "access_policy", None)
        participants = policy.case_participants(case) if policy else case.get("participants", [])
        if isinstance(participants, dict):
            participants = participants.get("participants", list(participants.values()))
        person = next(
            (
                p
                for p in participants
                if isinstance(p, dict)
                and p.get("user_id", p.get("actor_id")) == user_id
                and p.get("role") == "OPERATOR"
            ),
            None,
        )
        require(
            person is not None,
            "INVALID_ASSIGNEE",
            "Select an Operator from the authoritative case participant directory",
            422,
        )
        case["assigned_op_user_id"] = user_id
        case["assigned_op"] = deepcopy(person)
        case.setdefault("assignment_history", []).append(
            {"user_id": user_id, "reason": reason, "actor_id": identity["actor_id"], "at": now}
        )
        for task in case["tasks"]:
            if task["status"] == "OPEN" and task.get("owner") == "OPERATOR":
                task["assignee"] = user_id

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
