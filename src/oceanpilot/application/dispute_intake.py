"""Normalized synthetic upstream intake, with durable validation and command replay.

This inbox is a mock boundary, not an upstream authentication claim. Transactions
are entered by a distinct director/local seed; operators cannot approve their own
invented transaction facts. The domain command remains the sole business writer.
"""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from oceanpilot.domain.dispute import (
    DisputeError,
    currency_code,
    fingerprint,
    minor_units,
    require,
    text_field,
    timestamp,
)

EVENT_TYPES = {"FORMAL_DISPUTE", "ALERT", "INQUIRY", "WITHDRAWAL", "CORRECTION"}
MATCH_FIELDS = ("merchant_id", "transaction_id", "channel", "scheme", "amount_minor", "currency")
ENVELOPE_FIELDS = set(MATCH_FIELDS) | {
    "event_type",
    "source_event_id",
    "received_at",
    "occurred_at",
    "reason_code",
    "upstream_case_id",
    "target_case_id",
    "stage_number",
    "outcome",
    "final",
    "corrects_event_id",
    "basis_reference",
    "reason",
    "supported_minor",
    "liable_minor",
    "mapped_outcome",
    "authorization_reference",
    "case_template_id",
}


class DisputeIntakeService:
    def __init__(self, store, disputes, *, clock=None):
        self.store = store
        self.disputes = disputes
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self):
        return self.clock().astimezone(UTC).isoformat()

    def _operator(self, identity, merchant_id=None):
        identity = self.disputes._identity(identity)
        require(
            identity["role"] == "OPERATOR",
            "FORBIDDEN",
            "Normalized source intake requires an authorized Operator",
            403,
        )
        if merchant_id:
            if self.disputes.access_policy:
                self.disputes.access_policy.require_intake(merchant_id, identity)
            else:
                require(
                    identity.get("merchant_id") in {None, merchant_id},
                    "FORBIDDEN",
                    "Merchant scope does not authorize this event",
                    403,
                )
        return identity

    def _director(self, identity):
        require(
            isinstance(identity, dict) and identity.get("role") == "DIRECTOR",
            "FORBIDDEN",
            "Synthetic registry changes require the separate Director account",
            403,
        )
        text_field(identity, "actor_id", limit=200)
        policy = self.disputes.access_policy
        if policy:
            user = policy.directory.get_user(identity["actor_id"])
            require(
                user and user["role"] == "DIRECTOR" and not user["disabled"],
                "FORBIDDEN",
                "Active Director account is required",
                403,
            )
        return identity

    def _can_read(self, record, identity):
        merchant = record["envelope"]["merchant_id"]
        policy = self.disputes.access_policy
        if policy:
            case_id = record.get("case_id")
            if not case_id and record.get("attempts"):
                case_id = (record["attempts"][-1].get("command") or {}).get("case_id")
            if case_id:
                case = self.disputes.store.get_case(case_id)
                return case is not None and policy.can_access(case, identity)
            return policy.can_access({"merchant_id": merchant}, identity)
        return identity.get("merchant_id") in {None, merchant}

    def register_transaction(self, data, identity):
        identity = self._director(identity)
        require(
            isinstance(data, dict) and set(data) <= set(MATCH_FIELDS) | {"reference"},
            "INVALID_INPUT",
            "Registry fields do not match the synthetic transaction contract",
            422,
        )
        self.disputes._screen_values(data)
        record = {
            key: text_field(data, key, limit=200)
            for key in ("channel", "transaction_id", "merchant_id", "scheme")
        }
        record.update(
            amount_minor=minor_units(data.get("amount_minor")),
            currency=currency_code(data.get("currency")),
            reference=text_field(data, "reference", limit=500),
            source_type="DIRECTOR_SYNTHETIC_REGISTRY",
            production_eligible=False,
            created_at=self._now(),
            created_by=identity["actor_id"],
        )
        require(
            record["amount_minor"] > 0, "INVALID_AMOUNT", "Registry amount must be positive", 422
        )
        return self.store.register(record)

    def list_transactions(self, identity):
        self._director(identity)
        return self.store.list_transactions()

    def _envelope(self, data):
        require(
            isinstance(data, dict) and set(data) <= ENVELOPE_FIELDS,
            "INVALID_INPUT",
            "Unexpected normalized event fields",
            422,
        )
        fingerprint(data)
        screened = {
            ("event_id" if k == "source_event_id" else "case_id" if k == "target_case_id" else k): v
            for k, v in data.items()
        }
        self.disputes._screen_values(screened)
        result = {
            key: text_field(data, key, limit=200)
            for key in (
                "event_type",
                "source_event_id",
                "channel",
                "merchant_id",
                "transaction_id",
                "scheme",
                "reason_code",
            )
        }
        require(
            result["event_type"] in EVENT_TYPES,
            "INVALID_EVENT_TYPE",
            "Unsupported source event type",
            422,
        )
        result.update(
            amount_minor=minor_units(data.get("amount_minor")),
            currency=currency_code(data.get("currency")),
            received_at=timestamp(data.get("received_at")).isoformat(),
            occurred_at=timestamp(data.get("occurred_at")).isoformat(),
        )
        require(result["amount_minor"] > 0, "INVALID_AMOUNT", "Event amount must be positive", 422)
        require(
            timestamp(result["occurred_at"]) <= timestamp(result["received_at"]),
            "INVALID_EVENT_TIMES",
            "Source occurrence cannot follow OceanPayment receipt",
            422,
        )
        for key in ENVELOPE_FIELDS - set(result):
            if key in data and data[key] is not None:
                if key in {"stage_number", "supported_minor", "liable_minor"}:
                    value = minor_units(data[key])
                    require(
                        key != "stage_number" or value > 0,
                        "INVALID_STAGE",
                        "Stage number must be positive",
                        422,
                    )
                elif key == "final":
                    require(
                        type(data[key]) is bool, "INVALID_FINALITY", "final must be boolean", 422
                    )
                else:
                    text_field(data, key, limit=1000)
                result[key] = data[key]
        if result["event_type"] == "WITHDRAWAL":
            require(
                result.get("outcome", "WITHDRAWN") == "WITHDRAWN"
                and result.get("final", True) is True,
                "EVENT_TYPE_CONFLICT",
                "Withdrawal must describe a terminal withdrawal event",
                422,
            )
        return result

    def receive(self, envelope, identity, *, confirmed):
        identity = self._operator(identity)
        require(
            confirmed is True,
            "CONFIRMATION_REQUIRED",
            "A human Operator must confirm normalized source intake",
        )
        envelope = self._envelope(envelope)
        self._operator(identity, envelope["merchant_id"])
        record, replayed = self.store.remember(
            {
                "id": uuid4().hex,
                "envelope": envelope,
                "status": "RECEIVED",
                "reason": None,
                "attempts": [],
                "created_by": identity["actor_id"],
                "created_at": self._now(),
                "updated_at": self._now(),
                "source_type": "NORMALIZED_SYNTHETIC_EVENT",
                "production_eligible": False,
            }
        )
        require(self._can_read(record, identity), "NOT_FOUND", "Source event not found", 404)
        if record["status"] in {"PROCESSED", "RECORDED", "QUARANTINED"}:
            return self._public(record, replayed)
        return self._process(record, identity, replayed=replayed)

    def list_events(self, identity, status=None):
        identity = self._operator(identity)
        return [
            self._public(r, False)["event"]
            for r in self.store.list_events()
            if self._can_read(r, identity) and (status is None or r["status"] == status)
        ]

    def retry_event(self, event_id, identity, *, confirmed, reason):
        identity = self._operator(identity)
        require(
            confirmed is True, "CONFIRMATION_REQUIRED", "A human must confirm event revalidation"
        )
        reason = text_field({"reason": reason}, "reason", limit=1000)
        self.disputes._screen_values({"reason": reason})
        record = self.store.get_event(event_id)
        require(
            record is not None and self._can_read(record, identity),
            "NOT_FOUND",
            "Source event not found",
            404,
        )
        self._operator(identity, record["envelope"]["merchant_id"])
        if record["status"] in {"PROCESSED", "RECORDED"}:
            return self._public(record, True)
        return self._process(record, identity, replayed=True, retry_reason=reason)

    def _validate(self, envelope, identity):
        registered = self.store.transaction(envelope["channel"], envelope["transaction_id"])
        if not registered:
            return "TRANSACTION_NOT_REGISTERED", None, None
        if any(registered[key] != envelope[key] for key in MATCH_FIELDS):
            return "TRANSACTION_FACTS_MISMATCH", None, registered
        if envelope["event_type"] in {"ALERT", "INQUIRY", "FORMAL_DISPUTE"}:
            return None, None, registered
        cases = self.disputes.list_cases(identity)
        matching = [
            case
            for case in cases
            if all(case.get(key) == envelope.get(key) for key in MATCH_FIELDS)
            and case.get("reason_code") == envelope["reason_code"]
        ]
        if envelope.get("target_case_id"):
            matching = [case for case in matching if case["id"] == envelope["target_case_id"]]
        elif envelope.get("upstream_case_id"):
            matching = [
                case
                for case in matching
                if case.get("upstream_case_id") == envelope["upstream_case_id"]
            ]
        if len(matching) != 1:
            return "CASE_ASSOCIATION_REQUIRES_VERIFICATION", None, registered
        target = matching[0]
        if target["work_status"] == "CLOSED" or target["finality"] == "FINAL_CONFIRMED":
            return "AUTHORIZED_REOPEN_REQUIRED", target, registered
        if envelope["event_type"] == "CORRECTION" and not envelope.get("corrects_event_id"):
            return "CORRECTION_REFERENCE_REQUIRED", target, registered
        return None, target, registered

    def _command(self, record, identity, target, attempt):
        event = record["envelope"]
        command_id = (
            "inbox:"
            + record["id"][:8]
            + "g"
            + record["id"][8:16]
            + "g"
            + record["id"][16:24]
            + "g"
            + record["id"][24:]
            + ":"
            + str(attempt)
        )
        result = {"command_id": command_id, "confirmed": True}
        if event["event_type"] == "FORMAL_DISPUTE":
            result.update(
                action="INTAKE",
                data={
                    key: event[key]
                    for key in (
                        "merchant_id",
                        "transaction_id",
                        "scheme",
                        "channel",
                        "reason_code",
                        "amount_minor",
                        "currency",
                        "received_at",
                    )
                }
                | {
                    "event_id": event["source_event_id"],
                    "upstream_case_id": event.get("upstream_case_id", event["source_event_id"]),
                },
            )
            if event.get("case_template_id"):
                result["data"]["case_template_id"] = event["case_template_id"]
        else:
            data = {
                "event_id": event["source_event_id"],
                "source": event["channel"],
                "currency": event["currency"],
                "outcome": "WITHDRAWN"
                if event["event_type"] == "WITHDRAWAL"
                else event.get("outcome", "UNKNOWN"),
                "final": True if event["event_type"] == "WITHDRAWAL" else event.get("final", False),
                "disposition": "VERIFY",
                "occurred_at": event["occurred_at"],
                "received_at": event["received_at"],
                "stage_number": event.get("stage_number", target["stage_number"]),
                "reason": event.get("reason", "Normalized source event awaits Risk verification"),
                "basis_reference": event.get(
                    "basis_reference",
                    self.disputes._safe_reference("normalized-inbox", record["id"]),
                ),
            }
            data.update(
                {
                    k: event[k]
                    for k in (
                        "corrects_event_id",
                        "supported_minor",
                        "liable_minor",
                        "mapped_outcome",
                        "authorization_reference",
                    )
                    if k in event
                }
            )
            result.update(
                action="RECORD_OUTCOME",
                case_id=target["id"],
                expected_revision=target["revision"],
                data=data,
            )
        return result

    def _process(self, record, identity, *, replayed, retry_reason=None):
        # A prepared command remains byte-for-byte stable across process crashes.
        if record["status"] == "PROCESSING":
            pending = record["attempts"][-1]
            require(
                pending["actor_id"] == identity["actor_id"],
                "EVENT_PROCESSING_OWNER",
                "The original Operator must resume this prepared event command",
            )
        else:
            reason, target, registered = self._validate(record["envelope"], identity)
            status = (
                "QUARANTINED"
                if reason
                else "RECORDED"
                if record["envelope"]["event_type"] in {"ALERT", "INQUIRY"}
                else "PROCESSING"
            )
            attempt = len(record["attempts"]) + 1
            prepared = {
                "number": attempt,
                "actor_id": identity["actor_id"],
                "created_at": self._now(),
                "status": status,
                "reason": reason,
                "retry_reason": retry_reason,
                "registry_snapshot": deepcopy(registered),
                "command": self._command(record, identity, target, attempt)
                if status == "PROCESSING"
                else None,
            }
            record = self.store.prepare(record["id"], len(record["attempts"]), prepared)
            if record["status"] != "PROCESSING":
                return self._public(record, replayed)
            pending = record["attempts"][-1]
            require(
                pending["actor_id"] == identity["actor_id"],
                "EVENT_PROCESSING_OWNER",
                "The original Operator must resume this prepared event command",
            )
        try:
            result = self.disputes.execute(pending["command"], identity)
        except DisputeError as exc:
            record = self.store.finish(
                record["id"],
                pending["number"],
                status="QUARANTINED",
                reason=exc.code,
                at=self._now(),
            )
            return self._public(record, replayed)
        try:
            record = self.store.finish(
                record["id"],
                pending["number"],
                status="PROCESSED",
                reason=None,
                at=self._now(),
                result=result,
            )
        except Exception:
            # Business commit succeeded. The durable prepared command safely resumes on retry.
            return self._public(
                record | {"status": "PENDING_RECEIPT", "case_id": result["case"]["id"]}, replayed
            )
        return self._public(record, replayed or result["replayed"])

    @staticmethod
    def _public(record, replayed):
        event = {
            k: deepcopy(v) for k, v in record.items() if k not in {"attempts", "command_receipt"}
        }
        event["attempts"] = [
            {
                k: deepcopy(v)
                for k, v in attempt.items()
                if k not in {"command", "registry_snapshot"}
            }
            for attempt in record["attempts"]
        ]
        return {
            "event": event,
            "case_id": record.get("case_id"),
            "command_receipt": deepcopy(record.get("command_receipt")),
            "replayed": replayed,
        }
