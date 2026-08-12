import json
import re
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from oceanpilot.adapters.persistence.schema import REQUIRED_TABLES, SCHEMA_SQL
from oceanpilot.application.errors import (
    CaseNotFound,
    ConcurrentCaseWrite,
    DatabaseUnavailable,
    DiagnosisInputStale,
    EvidenceConflict,
    PersistenceInvariantViolation,
)
from oceanpilot.domain.enums import (
    AuditActorType,
    AuditEventType,
    CaseStatus,
    CaseType,
    DiagnosisStatus,
    EvidenceAvailability,
    EvidenceCode,
    EvidenceValueType,
    Priority,
    ResponsibleTeam,
    ReviewReason,
    SourceReliability,
    SourceType,
    StopReason,
    TargetRole,
    WriteOutcome,
)
from oceanpilot.domain.errors import InvalidTransition, SensitiveDataRejected
from oceanpilot.domain.evidence_policy import (
    assess_readiness,
    build_active_evidence_view,
    create_evidence_item,
)
from oceanpilot.domain.models import (
    AppendEvidenceResult,
    AuditEvent,
    CaseInputSnapshot,
    CaseView,
    CommitDiagnosisResult,
    DiagnosisSnapshot,
    EvidenceCreate,
    EvidenceItem,
    EvidenceOrigin,
    Hypothesis,
    HypothesisDraft,
    MerchantSuccessCase,
    ReadinessAssessment,
    RoutingDecision,
    TicketDraft,
)
from oceanpilot.domain.security import assert_no_sensitive_data
from oceanpilot.domain.state_machine import (
    status_after_creation,
    status_after_evidence,
)

_RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)


def _call_with_error_mapping[T](operation: Callable[[], T]) -> T:
    mapped: DatabaseUnavailable | PersistenceInvariantViolation
    try:
        return operation()
    except (CaseNotFound, DiagnosisInputStale, EvidenceConflict, ConcurrentCaseWrite):
        raise
    except (
        sqlite3.IntegrityError,
        sqlite3.DataError,
        sqlite3.ProgrammingError,
        sqlite3.InterfaceError,
        sqlite3.NotSupportedError,
    ):
        mapped = PersistenceInvariantViolation()
    except (sqlite3.OperationalError, sqlite3.InternalError):
        mapped = DatabaseUnavailable()
    except sqlite3.DatabaseError:
        mapped = DatabaseUnavailable()
    except sqlite3.Error:
        mapped = PersistenceInvariantViolation()
    except (
        SensitiveDataRejected,
        ValidationError,
        InvalidTransition,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OverflowError,
        UnicodeError,
        InvalidOperation,
    ):
        mapped = PersistenceInvariantViolation()
    raise mapped


def _invariant_call[T](operation: Callable[[], T]) -> T:
    mapped: PersistenceInvariantViolation
    try:
        return operation()
    except (
        SensitiveDataRejected,
        ValidationError,
        InvalidTransition,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OverflowError,
        UnicodeError,
        InvalidOperation,
    ):
        mapped = PersistenceInvariantViolation()
    raise mapped


def decode_sqlite_bool(name: str, raw: object) -> bool:
    del name
    if type(raw) is not int or raw not in (0, 1):
        raise PersistenceInvariantViolation()
    return raw == 1


def _require_text(raw: object) -> str:
    if type(raw) is not str:
        raise PersistenceInvariantViolation()
    return raw


def _require_int(raw: object) -> int:
    if type(raw) is not int:
        raise PersistenceInvariantViolation()
    return raw


def _decode_uuid(raw: object) -> str:
    value = _require_text(raw)

    def normalize() -> str:
        parsed = UUID(value)
        if parsed.version != 4:
            raise ValueError("version")
        return str(parsed)

    normalized = _invariant_call(normalize)
    if normalized != value:
        raise PersistenceInvariantViolation()
    return value


def _encode_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PersistenceInvariantViolation()
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _decode_datetime(raw: object) -> datetime:
    value = _require_text(raw)
    if _RFC3339_PATTERN.fullmatch(value) is None:
        raise PersistenceInvariantViolation()

    def parse() -> datetime:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed

    return _invariant_call(parse)


def _encode_json(value: object) -> str:
    return _invariant_call(
        lambda: json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
    )


def _decode_json(raw: object) -> object:
    value = _require_text(raw)
    return _invariant_call(lambda: json.loads(value))


def _exact_keys(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != keys:
        raise PersistenceInvariantViolation()
    return value


def _string_tuple(raw: object) -> tuple[str, ...]:
    if type(raw) is not list or any(type(value) is not str for value in raw):
        raise PersistenceInvariantViolation()
    return tuple(raw)


def _uuid_tuple(raw: object) -> tuple[str, ...]:
    return tuple(_decode_uuid(value) for value in _string_tuple(raw))


def _review_reasons(raw: object) -> frozenset[ReviewReason]:
    values = _string_tuple(raw)
    if len(set(values)) != len(values):
        raise PersistenceInvariantViolation()
    return frozenset(_invariant_call(lambda value=value: ReviewReason(value)) for value in values)


_READINESS_KEYS = frozenset(
    {
        "ready",
        "missing_fields",
        "known_unknown_fields",
        "next_question",
        "question_reason",
        "target_role",
        "completion_ratio",
        "stop_reason",
    }
)


def _encode_readiness(value: ReadinessAssessment) -> str:
    return _encode_json(value.model_dump(mode="json"))


def _decode_readiness(raw: object) -> ReadinessAssessment:
    data = _exact_keys(_decode_json(raw), _READINESS_KEYS)
    ready = data["ready"]
    if type(ready) is not bool:
        raise PersistenceInvariantViolation()
    next_question = data["next_question"]
    question_reason = data["question_reason"]
    if next_question is not None and type(next_question) is not str:
        raise PersistenceInvariantViolation()
    if question_reason is not None and type(question_reason) is not str:
        raise PersistenceInvariantViolation()
    role_raw = data["target_role"]
    if role_raw is not None and type(role_raw) is not str:
        raise PersistenceInvariantViolation()
    stop_raw = _require_text(data["stop_reason"])
    completion_raw = data["completion_ratio"]
    if type(completion_raw) not in (str, int, float):
        raise PersistenceInvariantViolation()
    return _invariant_call(
        lambda: ReadinessAssessment(
            ready=ready,
            missing_fields=_string_tuple(data["missing_fields"]),
            known_unknown_fields=_string_tuple(data["known_unknown_fields"]),
            next_question=next_question,
            question_reason=question_reason,
            target_role=TargetRole(role_raw) if role_raw is not None else None,
            completion_ratio=Decimal(str(completion_raw)),
            stop_reason=StopReason(stop_raw),
        )
    )


def _canonicalize_evidence(item: EvidenceItem) -> EvidenceItem:
    recreated = _invariant_call(
        lambda: create_evidence_item(
            EvidenceCreate(
                evidence_id=item.evidence_id,
                evidence_code=item.evidence_code,
                availability=item.availability,
                typed_value=item.typed_value,
                observed_at=item.observed_at,
                source_ref=item.source_ref,
            ),
            case_id=item.case_id,
            origin=EvidenceOrigin(
                source_type=item.source_type,
                source_reliability=item.source_reliability,
                synthetic=item.synthetic,
            ),
            collected_at=item.collected_at,
        )
    )
    if recreated != item:
        raise PersistenceInvariantViolation()
    return recreated


def _decode_typed_value(
    *,
    availability: EvidenceAvailability,
    value_type: EvidenceValueType,
    raw: object,
) -> str | bool | datetime | None:
    if availability is EvidenceAvailability.CONFIRMED_UNAVAILABLE:
        if raw is not None:
            raise PersistenceInvariantViolation()
        return None
    decoded = _decode_json(raw)
    if value_type is EvidenceValueType.DATETIME:
        return _decode_datetime(decoded)
    if value_type is EvidenceValueType.BOOLEAN:
        if type(decoded) is not bool:
            raise PersistenceInvariantViolation()
        return decoded
    if type(decoded) is not str:
        raise PersistenceInvariantViolation()
    return decoded


def _decode_evidence_row(row: sqlite3.Row) -> EvidenceItem:
    availability = _invariant_call(lambda: EvidenceAvailability(_require_text(row["availability"])))
    value_type = _invariant_call(lambda: EvidenceValueType(_require_text(row["value_type"])))
    observed_raw = row["observed_at"]
    synthetic = decode_sqlite_bool("evidence.synthetic", row["synthetic"])
    if synthetic is not True:
        raise PersistenceInvariantViolation()
    item = _invariant_call(
        lambda: EvidenceItem(
            case_id=_decode_uuid(row["case_id"]),
            evidence_id=_decode_uuid(row["evidence_id"]),
            schema_version=_require_text(row["schema_version"]),
            evidence_code=EvidenceCode(_require_text(row["evidence_code"])),
            availability=availability,
            value_type=value_type,
            typed_value=_decode_typed_value(
                availability=availability,
                value_type=value_type,
                raw=row["typed_value_json"],
            ),
            source_type=SourceType(_require_text(row["source_type"])),
            source_ref=_require_text(row["source_ref"]),
            source_reliability=SourceReliability(_require_text(row["source_reliability"])),
            observed_at=(_decode_datetime(observed_raw) if observed_raw is not None else None),
            collected_at=_decode_datetime(row["collected_at"]),
            synthetic=synthetic,
            content_hash=_require_text(row["content_hash"]),
        )
    )
    return _canonicalize_evidence(item)


_HYPOTHESIS_DRAFT_KEYS = frozenset(
    {
        "cause_code",
        "explanation",
        "evidence_refs",
        "confidence_score",
        "confidence_method",
        "next_verification_action",
        "rule_id",
    }
)


def _decimal(raw: object) -> Decimal:
    if type(raw) not in (str, int, float):
        raise PersistenceInvariantViolation()
    return _invariant_call(lambda: Decimal(str(raw)))


def _decode_hypothesis_draft(raw: object) -> HypothesisDraft:
    data = _exact_keys(raw, _HYPOTHESIS_DRAFT_KEYS)
    return _invariant_call(
        lambda: HypothesisDraft(
            cause_code=_require_text(data["cause_code"]),
            explanation=_require_text(data["explanation"]),
            evidence_refs=_uuid_tuple(data["evidence_refs"]),
            confidence_score=_decimal(data["confidence_score"]),
            confidence_method=_require_text(data["confidence_method"]),
            next_verification_action=_require_text(data["next_verification_action"]),
            rule_id=_require_text(data["rule_id"]),
        )
    )


_ROUTING_KEYS = frozenset(
    {
        "responsible_team",
        "priority",
        "reason",
        "evidence_refs",
        "requires_human",
        "review_reasons",
    }
)


def _decode_routing(raw: object) -> RoutingDecision | None:
    if raw is None:
        return None
    data = _exact_keys(_decode_json(raw), _ROUTING_KEYS)
    requires_human = data["requires_human"]
    if type(requires_human) is not bool:
        raise PersistenceInvariantViolation()
    return _invariant_call(
        lambda: RoutingDecision(
            responsible_team=ResponsibleTeam(_require_text(data["responsible_team"])),
            priority=Priority(_require_text(data["priority"])),
            reason=_require_text(data["reason"]),
            evidence_refs=_uuid_tuple(data["evidence_refs"]),
            requires_human=requires_human,
            review_reasons=_review_reasons(data["review_reasons"]),
        )
    )


_TICKET_KEYS = frozenset(
    {
        "title",
        "summary",
        "evidence_summary",
        "missing_material",
        "hypotheses",
        "next_action",
        "responsible_team",
        "synthetic",
    }
)


def _decode_ticket(raw: object) -> TicketDraft | None:
    if raw is None:
        return None
    data = _exact_keys(_decode_json(raw), _TICKET_KEYS)
    hypotheses_raw = data["hypotheses"]
    if type(hypotheses_raw) is not list:
        raise PersistenceInvariantViolation()
    synthetic = data["synthetic"]
    if synthetic is not True:
        raise PersistenceInvariantViolation()
    return _invariant_call(
        lambda: TicketDraft(
            title=_require_text(data["title"]),
            summary=_require_text(data["summary"]),
            evidence_summary=_string_tuple(data["evidence_summary"]),
            missing_material=_string_tuple(data["missing_material"]),
            hypotheses=tuple(_decode_hypothesis_draft(value) for value in hypotheses_raw),
            next_action=_require_text(data["next_action"]),
            responsible_team=ResponsibleTeam(_require_text(data["responsible_team"])),
            synthetic=synthetic,
        )
    )


def _validate_case_graph(view: CaseView) -> CaseView:
    case = view.case
    if case.status is CaseStatus.NEW:
        raise PersistenceInvariantViolation()
    if case.evidence_revision != len(view.evidence):
        raise PersistenceInvariantViolation()
    if case.case_revision < case.evidence_revision + 1:
        raise PersistenceInvariantViolation()
    if case.created_at > case.updated_at:
        raise PersistenceInvariantViolation()
    recalculated = assess_readiness(build_active_evidence_view(view.evidence))
    if recalculated != case.readiness:
        raise PersistenceInvariantViolation()
    evidence_ids = frozenset(item.evidence_id for item in view.evidence)
    if len(evidence_ids) != len(view.evidence):
        raise PersistenceInvariantViolation()

    if case.status in (CaseStatus.NEED_INFO, CaseStatus.EVIDENCE_READY):
        if case.current_diagnosis_id is not None or view.current_diagnosis is not None:
            raise PersistenceInvariantViolation()
        if case.status is not status_after_creation(case.readiness):
            raise PersistenceInvariantViolation()
    else:
        diagnosis = view.current_diagnosis
        if not case.readiness.ready or case.current_diagnosis_id is None:
            raise PersistenceInvariantViolation()
        if diagnosis is None:
            raise PersistenceInvariantViolation()
        if (
            diagnosis.case_id != case.case_id
            or diagnosis.diagnosis_id != case.current_diagnosis_id
            or diagnosis.status is not DiagnosisStatus.CURRENT
            or diagnosis.evidence_revision != case.evidence_revision
            or diagnosis.requires_human is not (case.status is CaseStatus.HUMAN_REVIEW)
        ):
            raise PersistenceInvariantViolation()
        referenced = {
            evidence_id
            for hypothesis in diagnosis.hypotheses
            for evidence_id in hypothesis.evidence_refs
        }
        if diagnosis.routing_decision is not None:
            if (
                diagnosis.routing_decision.requires_human is not diagnosis.requires_human
                or diagnosis.routing_decision.review_reasons != diagnosis.review_reasons
            ):
                raise PersistenceInvariantViolation()
            referenced.update(diagnosis.routing_decision.evidence_refs)
        if diagnosis.ticket_draft is not None:
            referenced.update(
                evidence_id
                for hypothesis in diagnosis.ticket_draft.hypotheses
                for evidence_id in hypothesis.evidence_refs
            )
        if not referenced.issubset(evidence_ids):
            raise PersistenceInvariantViolation()
    assert_no_sensitive_data(view)
    return view


def _validate_diagnosis_snapshot(snapshot: DiagnosisSnapshot) -> DiagnosisSnapshot:
    if snapshot.requires_human is not bool(snapshot.review_reasons):
        raise PersistenceInvariantViolation()

    route = snapshot.routing_decision
    ticket = snapshot.ticket_draft
    if (route is None) is not (ticket is None):
        raise PersistenceInvariantViolation()

    if route is None:
        if snapshot.hypotheses or snapshot.review_reasons not in (
            frozenset({ReviewReason.POLICY_GAP}),
            frozenset({ReviewReason.CONFLICTING_EVIDENCE}),
        ):
            raise PersistenceInvariantViolation()
        return snapshot

    if (
        ticket is None
        or len(snapshot.hypotheses) != 1
        or not snapshot.review_reasons.isdisjoint(
            {ReviewReason.POLICY_GAP, ReviewReason.CONFLICTING_EVIDENCE}
        )
    ):
        raise PersistenceInvariantViolation()
    hypothesis = snapshot.hypotheses[0]
    expected_draft = _invariant_call(
        lambda: HypothesisDraft(
            cause_code=hypothesis.cause_code,
            explanation=hypothesis.explanation,
            evidence_refs=hypothesis.evidence_refs,
            confidence_score=hypothesis.confidence_score,
            confidence_method=hypothesis.confidence_method,
            next_verification_action=hypothesis.next_verification_action,
            rule_id=hypothesis.rule_id,
        )
    )
    if (
        route.requires_human is not snapshot.requires_human
        or route.review_reasons != snapshot.review_reasons
        or route.evidence_refs != hypothesis.evidence_refs
        or ticket.responsible_team is not route.responsible_team
        or ticket.summary != hypothesis.explanation
        or ticket.missing_material != ()
        or ticket.hypotheses != (expected_draft,)
        or ticket.next_action != hypothesis.next_verification_action
    ):
        raise PersistenceInvariantViolation()
    return snapshot


def _canonicalize_case(case: MerchantSuccessCase) -> MerchantSuccessCase:
    canonical = _invariant_call(
        lambda: MerchantSuccessCase.model_validate(
            case.model_dump(mode="python"),
            strict=True,
        )
    )
    if canonical != case:
        raise PersistenceInvariantViolation()
    return canonical


def _canonicalize_audit(event: AuditEvent) -> AuditEvent:
    canonical = _invariant_call(
        lambda: AuditEvent.model_validate(
            event.model_dump(mode="python"),
            strict=True,
        )
    )
    if canonical != event:
        raise PersistenceInvariantViolation()
    return canonical


def _decode_audit_row(row: sqlite3.Row) -> AuditEvent:
    from_status_raw = row["from_status"]
    to_status_raw = row["to_status"]
    reason_code = row["reason_code"]
    metadata = _decode_json(row["sanitized_metadata_json"])
    if type(metadata) is not dict or (reason_code is not None and type(reason_code) is not str):
        raise PersistenceInvariantViolation()
    event = _invariant_call(
        lambda: AuditEvent(
            event_id=_decode_uuid(row["event_id"]),
            event_type=AuditEventType(_require_text(row["event_type"])),
            event_version=_require_text(row["event_version"]),
            case_id=_decode_uuid(row["case_id"]),
            request_id=_decode_uuid(row["request_id"]),
            trace_id=_decode_uuid(row["trace_id"]),
            actor_type=AuditActorType(_require_text(row["actor_type"])),
            action=_require_text(row["action"]),
            from_status=(
                CaseStatus(_require_text(from_status_raw)) if from_status_raw is not None else None
            ),
            to_status=(
                CaseStatus(_require_text(to_status_raw)) if to_status_raw is not None else None
            ),
            case_revision=_require_int(row["case_revision"]),
            evidence_revision=_require_int(row["evidence_revision"]),
            occurred_at=_decode_datetime(row["occurred_at"]),
            result=_require_text(row["result"]),
            reason_code=reason_code,
            sanitized_metadata=metadata,
            synthetic=decode_sqlite_bool("audit.synthetic", row["synthetic"]),
        )
    )
    if event.synthetic is not True:
        raise PersistenceInvariantViolation()
    assert_no_sensitive_data(event)
    return _canonicalize_audit(event)


def _canonicalize_diagnosis(snapshot: DiagnosisSnapshot) -> DiagnosisSnapshot:
    canonical = _invariant_call(
        lambda: DiagnosisSnapshot.model_validate(
            snapshot.model_dump(mode="python"),
            strict=True,
        )
    )
    if canonical != snapshot:
        raise PersistenceInvariantViolation()
    hypotheses = tuple(
        hypothesis.model_copy(update={"evidence_refs": tuple(sorted(hypothesis.evidence_refs))})
        for hypothesis in canonical.hypotheses
    )
    route = canonical.routing_decision
    if route is not None:
        route = route.model_copy(update={"evidence_refs": tuple(sorted(route.evidence_refs))})
    ticket = canonical.ticket_draft
    if ticket is not None:
        ticket = ticket.model_copy(
            update={
                "hypotheses": tuple(
                    hypothesis.model_copy(
                        update={"evidence_refs": tuple(sorted(hypothesis.evidence_refs))}
                    )
                    for hypothesis in ticket.hypotheses
                )
            }
        )
    normalized = _invariant_call(
        lambda: DiagnosisSnapshot.model_validate(
            canonical.model_copy(
                update={
                    "hypotheses": hypotheses,
                    "routing_decision": route,
                    "ticket_draft": ticket,
                }
            ).model_dump(mode="python"),
            strict=True,
        )
    )
    return _validate_diagnosis_snapshot(normalized)


def _validate_audit_batch(
    events: Sequence[AuditEvent],
    *,
    case_id: str,
    required_types: frozenset[AuditEventType],
    from_status: CaseStatus | None,
    to_status: CaseStatus,
    case_revision: int,
    evidence_revision: int,
) -> tuple[AuditEvent, ...]:
    canonical = tuple(_canonicalize_audit(event) for event in events)
    if len(canonical) != len(required_types):
        raise PersistenceInvariantViolation()
    if frozenset(event.event_type for event in canonical) != required_types:
        raise PersistenceInvariantViolation()
    if len({event.event_type for event in canonical}) != len(canonical):
        raise PersistenceInvariantViolation()
    if len({event.event_id for event in canonical}) != len(canonical):
        raise PersistenceInvariantViolation()
    if len({event.request_id for event in canonical}) != 1:
        raise PersistenceInvariantViolation()
    if len({event.trace_id for event in canonical}) != 1:
        raise PersistenceInvariantViolation()
    if any(
        event.case_id != case_id
        or event.from_status is not from_status
        or event.to_status is not to_status
        or event.case_revision != case_revision
        or event.evidence_revision != evidence_revision
        or event.synthetic is not True
        for event in canonical
    ):
        raise PersistenceInvariantViolation()
    return canonical


def _insert_case(
    connection: sqlite3.Connection,
    case: MerchantSuccessCase,
) -> None:
    cursor = connection.execute(
        """
        INSERT INTO cases (
            case_id, case_type, status, schema_version, case_revision,
            evidence_revision, synthetic, summary, merchant_ref, created_at,
            updated_at, current_diagnosis_id, readiness_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case.case_id,
            case.case_type.value,
            case.status.value,
            case.schema_version,
            case.case_revision,
            case.evidence_revision,
            1,
            case.summary,
            case.merchant_ref,
            _encode_datetime(case.created_at),
            _encode_datetime(case.updated_at),
            case.current_diagnosis_id,
            _encode_readiness(case.readiness),
        ),
    )
    if cursor.rowcount != 1:
        raise PersistenceInvariantViolation()


def _insert_audit(connection: sqlite3.Connection, event: AuditEvent) -> None:
    cursor = connection.execute(
        """
        INSERT INTO audit_events (
            case_id, event_id, event_type, event_version, request_id, trace_id,
            actor_type, action, from_status, to_status, case_revision,
            evidence_revision, occurred_at, result, reason_code,
            sanitized_metadata_json, synthetic
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.case_id,
            event.event_id,
            event.event_type.value,
            event.event_version,
            event.request_id,
            event.trace_id,
            event.actor_type.value,
            event.action,
            event.from_status.value if event.from_status is not None else None,
            event.to_status.value if event.to_status is not None else None,
            event.case_revision,
            event.evidence_revision,
            _encode_datetime(event.occurred_at),
            event.result,
            event.reason_code,
            _encode_json(event.sanitized_metadata),
            1,
        ),
    )
    if cursor.rowcount != 1:
        raise PersistenceInvariantViolation()


def _insert_diagnosis(
    connection: sqlite3.Connection,
    snapshot: DiagnosisSnapshot,
) -> None:
    routing_json: str | None = None
    if snapshot.routing_decision is not None:
        routing_payload = snapshot.routing_decision.model_dump(mode="json")
        routing_payload["review_reasons"] = sorted(
            reason.value for reason in snapshot.routing_decision.review_reasons
        )
        routing_json = _encode_json(routing_payload)
    cursor = connection.execute(
        """
        INSERT INTO diagnosis_snapshots (
            case_id, diagnosis_id, evidence_revision, policy_version,
            engine_version, status, routing_json, ticket_json, requires_human,
            review_reasons_json, synthetic, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot.case_id,
            snapshot.diagnosis_id,
            snapshot.evidence_revision,
            snapshot.policy_version,
            snapshot.engine_version,
            snapshot.status.value,
            routing_json,
            (
                _encode_json(snapshot.ticket_draft.model_dump(mode="json"))
                if snapshot.ticket_draft is not None
                else None
            ),
            int(snapshot.requires_human),
            _encode_json(sorted(reason.value for reason in snapshot.review_reasons)),
            1,
            _encode_datetime(snapshot.created_at),
        ),
    )
    if cursor.rowcount != 1:
        raise PersistenceInvariantViolation()

    for hypothesis in snapshot.hypotheses:
        cursor = connection.execute(
            """
            INSERT INTO hypotheses (
                case_id, hypothesis_id, diagnosis_id, cause_code, explanation,
                confidence_score, confidence_method, next_verification_action,
                rule_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.case_id,
                hypothesis.hypothesis_id,
                snapshot.diagnosis_id,
                hypothesis.cause_code,
                hypothesis.explanation,
                str(hypothesis.confidence_score),
                hypothesis.confidence_method,
                hypothesis.next_verification_action,
                hypothesis.rule_id,
            ),
        )
        if cursor.rowcount != 1:
            raise PersistenceInvariantViolation()
        for evidence_id in hypothesis.evidence_refs:
            cursor = connection.execute(
                """
                INSERT INTO hypothesis_evidence_refs (
                    case_id, hypothesis_id, evidence_id
                ) VALUES (?, ?, ?)
                """,
                (snapshot.case_id, hypothesis.hypothesis_id, evidence_id),
            )
            if cursor.rowcount != 1:
                raise PersistenceInvariantViolation()


def _canonicalize_readiness(
    readiness: ReadinessAssessment,
) -> ReadinessAssessment:
    canonical = _invariant_call(
        lambda: ReadinessAssessment.model_validate(
            readiness.model_dump(mode="python"),
            strict=True,
        )
    )
    if canonical != readiness:
        raise PersistenceInvariantViolation()
    return canonical


def _encode_typed_value(item: EvidenceItem) -> str | None:
    if item.availability is EvidenceAvailability.CONFIRMED_UNAVAILABLE:
        if item.typed_value is not None:
            raise PersistenceInvariantViolation()
        return None
    value: object = item.typed_value
    if isinstance(value, datetime):
        value = _encode_datetime(value)
    return _encode_json(value)


def _insert_evidence(
    connection: sqlite3.Connection,
    item: EvidenceItem,
) -> None:
    cursor = connection.execute(
        """
        INSERT INTO evidence_items (
            case_id, evidence_id, schema_version, evidence_code, availability,
            value_type, typed_value_json, source_type, source_ref,
            source_reliability, observed_at, collected_at, synthetic, content_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item.case_id,
            item.evidence_id,
            item.schema_version,
            item.evidence_code.value,
            item.availability.value,
            item.value_type.value,
            _encode_typed_value(item),
            item.source_type.value,
            item.source_ref,
            item.source_reliability.value,
            _encode_datetime(item.observed_at) if item.observed_at is not None else None,
            _encode_datetime(item.collected_at),
            1,
            item.content_hash,
        ),
    )
    if cursor.rowcount != 1:
        raise PersistenceInvariantViolation()


@contextmanager
def _deferred_read_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    if connection.in_transaction:
        yield
        return
    connection.execute("BEGIN")
    try:
        yield
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def connect_sqlite(path: Path) -> sqlite3.Connection:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            str(path),
            timeout=5.0,
            isolation_level=None,
            autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        foreign_keys_row = connection.execute("PRAGMA foreign_keys").fetchone()
        journal_mode_row = connection.execute("PRAGMA journal_mode").fetchone()
        if (
            foreign_keys_row is None
            or foreign_keys_row[0] != 1
            or journal_mode_row is None
            or journal_mode_row[0] != "delete"
        ):
            connection.close()
            raise DatabaseUnavailable()
        return connection
    except sqlite3.Error:
        if connection is not None:
            connection.close()
        raise DatabaseUnavailable() from None


def initialize_schema(path: Path) -> None:
    connection: sqlite3.Connection | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect_sqlite(path)
        connection.executescript(f"BEGIN IMMEDIATE;\n{SCHEMA_SQL}\nCOMMIT;")
        table_names = frozenset(
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_schema
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        )
        if table_names != REQUIRED_TABLES:
            raise DatabaseUnavailable()
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise DatabaseUnavailable()
    except (OSError, sqlite3.Error, DatabaseUnavailable):
        raise DatabaseUnavailable() from None
    finally:
        if connection is not None:
            connection.close()


@contextmanager
def immediate_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


class SqliteCaseStoreSession:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def healthcheck(self) -> None:
        try:
            table_names = frozenset(
                row["name"]
                for row in self._connection.execute(
                    """
                    SELECT name
                    FROM sqlite_schema
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                )
            )
            if not REQUIRED_TABLES.issubset(table_names):
                raise DatabaseUnavailable()
            self._connection.execute("SELECT case_id FROM cases LIMIT 0")
            if self._connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise DatabaseUnavailable()
        except sqlite3.Error:
            raise DatabaseUnavailable() from None

    def create_case_atomic(
        self,
        *,
        case: MerchantSuccessCase,
        audit: AuditEvent,
    ) -> CaseView:
        assert_no_sensitive_data(case)
        assert_no_sensitive_data(audit)
        canonical_case = _canonicalize_case(case)
        canonical_audit = _canonicalize_audit(audit)

        def operation() -> CaseView:
            with immediate_transaction(self._connection):
                empty_readiness = assess_readiness(build_active_evidence_view(()))
                if (
                    canonical_case.case_type is not CaseType.PAYMENT_INCIDENT
                    or canonical_case.case_revision != 1
                    or canonical_case.evidence_revision != 0
                    or canonical_case.current_diagnosis_id is not None
                    or canonical_case.created_at != canonical_case.updated_at
                    or canonical_case.readiness != empty_readiness
                    or canonical_case.status is not status_after_creation(canonical_case.readiness)
                ):
                    raise PersistenceInvariantViolation()
                validated_audits = _validate_audit_batch(
                    (canonical_audit,),
                    case_id=canonical_case.case_id,
                    required_types=frozenset({AuditEventType.CASE_CREATED}),
                    from_status=None,
                    to_status=canonical_case.status,
                    case_revision=1,
                    evidence_revision=0,
                )
                existing = self._load_case_graph(canonical_case.case_id)
                if existing is not None:
                    stored_case = existing.case
                    same_creation_identity = (
                        existing.evidence == ()
                        and existing.current_diagnosis is None
                        and stored_case.case_id == canonical_case.case_id
                        and stored_case.case_type is canonical_case.case_type
                        and stored_case.status is canonical_case.status
                        and stored_case.schema_version == canonical_case.schema_version
                        and stored_case.case_revision == canonical_case.case_revision
                        and stored_case.evidence_revision == canonical_case.evidence_revision
                        and stored_case.synthetic is canonical_case.synthetic
                        and stored_case.summary == canonical_case.summary
                        and stored_case.merchant_ref == canonical_case.merchant_ref
                        and stored_case.current_diagnosis_id is None
                        and stored_case.readiness == canonical_case.readiness
                    )
                    if not same_creation_identity:
                        raise PersistenceInvariantViolation()
                    return existing
                _insert_case(self._connection, canonical_case)
                _insert_audit(self._connection, validated_audits[0])
                view = self._load_case_graph(canonical_case.case_id)
                if view is None:
                    raise PersistenceInvariantViolation()
            return view

        return _call_with_error_mapping(operation)

    def append_evidence_atomic(
        self,
        *,
        expected_case_revision: int,
        expected_evidence_revision: int,
        evidence: EvidenceItem,
        readiness: ReadinessAssessment,
        target_status: CaseStatus,
        audit_events: Sequence[AuditEvent],
    ) -> AppendEvidenceResult:
        events = tuple(audit_events)
        assert_no_sensitive_data(evidence)
        assert_no_sensitive_data(readiness)
        assert_no_sensitive_data(target_status)
        for event in events:
            assert_no_sensitive_data(event)
        canonical_evidence = _canonicalize_evidence(evidence)

        def operation() -> AppendEvidenceResult:
            with immediate_transaction(self._connection):
                existing_row = self._connection.execute(
                    """
                    SELECT case_id, evidence_id, schema_version, evidence_code,
                           availability, value_type, typed_value_json, source_type,
                           source_ref, source_reliability, observed_at, collected_at,
                           synthetic, content_hash
                    FROM evidence_items
                    WHERE case_id = ? AND evidence_id = ?
                    """,
                    (canonical_evidence.case_id, canonical_evidence.evidence_id),
                ).fetchone()
                if existing_row is not None:
                    stored = _decode_evidence_row(existing_row)
                    assert_no_sensitive_data(stored)
                    if stored.content_hash != canonical_evidence.content_hash:
                        raise EvidenceConflict()
                    current = self._load_case_graph(canonical_evidence.case_id)
                    if current is None:
                        raise PersistenceInvariantViolation()
                    return AppendEvidenceResult(
                        outcome=WriteOutcome.REPLAY,
                        case_view=current,
                    )

                current = self._load_case_graph(canonical_evidence.case_id)
                if current is None:
                    raise CaseNotFound()
                case = current.case
                if (
                    type(expected_case_revision) is not int
                    or expected_case_revision < 0
                    or type(expected_evidence_revision) is not int
                    or expected_evidence_revision < 0
                ):
                    raise PersistenceInvariantViolation()
                if (
                    case.case_revision != expected_case_revision
                    or case.evidence_revision != expected_evidence_revision
                ):
                    raise ConcurrentCaseWrite()

                canonical_readiness = _canonicalize_readiness(readiness)
                recomputed = assess_readiness(
                    build_active_evidence_view((*current.evidence, canonical_evidence))
                )
                if canonical_readiness != recomputed:
                    raise PersistenceInvariantViolation()
                if type(target_status) is not CaseStatus:
                    raise PersistenceInvariantViolation()
                expected_target = status_after_evidence(case.status, recomputed)
                if target_status is not expected_target:
                    raise PersistenceInvariantViolation()

                reopening = case.status in (
                    CaseStatus.DIAGNOSED,
                    CaseStatus.HUMAN_REVIEW,
                )
                required_types = {AuditEventType.EVIDENCE_ADDED}
                if reopening:
                    required_types.add(AuditEventType.DIAGNOSIS_SUPERSEDED)
                if target_status is not case.status:
                    required_types.add(AuditEventType.STATE_TRANSITIONED)
                validated_audits = _validate_audit_batch(
                    events,
                    case_id=case.case_id,
                    required_types=frozenset(required_types),
                    from_status=case.status,
                    to_status=target_status,
                    case_revision=expected_case_revision + 1,
                    evidence_revision=expected_evidence_revision + 1,
                )

                _insert_evidence(self._connection, canonical_evidence)
                if reopening:
                    diagnosis = current.current_diagnosis
                    if diagnosis is None or case.current_diagnosis_id is None:
                        raise PersistenceInvariantViolation()
                    cursor = self._connection.execute(
                        """
                        UPDATE diagnosis_snapshots
                        SET status = 'SUPERSEDED'
                        WHERE case_id = ? AND diagnosis_id = ? AND status = 'CURRENT'
                              AND evidence_revision = ?
                        """,
                        (
                            case.case_id,
                            case.current_diagnosis_id,
                            case.evidence_revision,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise PersistenceInvariantViolation()

                updated_at = max(case.updated_at, canonical_evidence.collected_at)
                cursor = self._connection.execute(
                    """
                    UPDATE cases
                    SET status = ?, case_revision = ?, evidence_revision = ?,
                        readiness_json = ?, updated_at = ?, current_diagnosis_id = NULL
                    WHERE case_id = ? AND case_revision = ? AND evidence_revision = ?
                    """,
                    (
                        target_status.value,
                        expected_case_revision + 1,
                        expected_evidence_revision + 1,
                        _encode_readiness(canonical_readiness),
                        _encode_datetime(updated_at),
                        case.case_id,
                        expected_case_revision,
                        expected_evidence_revision,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ConcurrentCaseWrite()
                for event in validated_audits:
                    _insert_audit(self._connection, event)
                fresh = self._load_case_graph(case.case_id)
                if fresh is None:
                    raise PersistenceInvariantViolation()
            return AppendEvidenceResult(
                outcome=WriteOutcome.CREATED,
                case_view=fresh,
            )

        return _call_with_error_mapping(operation)

    def get_case_view(self, case_id: str) -> CaseView | None:
        def operation() -> CaseView | None:
            normalized_case_id = _decode_uuid(case_id)
            with _deferred_read_transaction(self._connection):
                return self._load_case_graph(normalized_case_id)

        return _call_with_error_mapping(operation)

    def load_case_snapshot(self, case_id: str) -> CaseInputSnapshot | None:
        def operation() -> CaseInputSnapshot | None:
            normalized_case_id = _decode_uuid(case_id)
            with _deferred_read_transaction(self._connection):
                view = self._load_case_graph(normalized_case_id)
                if view is None:
                    return None
                return CaseInputSnapshot(
                    case=view.case,
                    evidence=view.evidence,
                    current_diagnosis=view.current_diagnosis,
                )

        return _call_with_error_mapping(operation)

    def find_diagnosis(
        self,
        *,
        case_id: str,
        evidence_revision: int,
        policy_version: str,
    ) -> DiagnosisSnapshot | None:
        def operation() -> DiagnosisSnapshot | None:
            normalized_case_id = _decode_uuid(case_id)
            if (
                type(evidence_revision) is not int
                or evidence_revision < 0
                or type(policy_version) is not str
                or not policy_version
            ):
                raise PersistenceInvariantViolation()
            with _deferred_read_transaction(self._connection):
                row = self._connection.execute(
                    """
                    SELECT diagnosis_id
                    FROM diagnosis_snapshots
                    WHERE case_id = ? AND evidence_revision = ? AND policy_version = ?
                    """,
                    (normalized_case_id, evidence_revision, policy_version),
                ).fetchone()
                if row is None:
                    return None
                snapshot = self._load_diagnosis_snapshot_by_id(
                    normalized_case_id,
                    _decode_uuid(row["diagnosis_id"]),
                )
                if snapshot is None:
                    raise PersistenceInvariantViolation()
                assert_no_sensitive_data(snapshot)
                return snapshot

        return _call_with_error_mapping(operation)

    def commit_diagnosis_atomic(
        self,
        *,
        expected_case_revision: int,
        expected_evidence_revision: int,
        snapshot: DiagnosisSnapshot,
        target_status: CaseStatus,
        audit_events: Sequence[AuditEvent],
    ) -> CommitDiagnosisResult:
        events = tuple(audit_events)
        assert_no_sensitive_data(snapshot)
        assert_no_sensitive_data(target_status)
        for event in events:
            assert_no_sensitive_data(event)
        canonical_snapshot = _canonicalize_diagnosis(snapshot)

        def operation() -> CommitDiagnosisResult:
            if (
                type(expected_case_revision) is not int
                or expected_case_revision < 0
                or type(expected_evidence_revision) is not int
                or expected_evidence_revision < 0
                or canonical_snapshot.evidence_revision != expected_evidence_revision
                or canonical_snapshot.status is not DiagnosisStatus.CURRENT
                or type(target_status) is not CaseStatus
                or target_status
                is not (
                    CaseStatus.HUMAN_REVIEW
                    if canonical_snapshot.requires_human
                    else CaseStatus.DIAGNOSED
                )
            ):
                raise PersistenceInvariantViolation()

            with immediate_transaction(self._connection):
                current = self._load_case_graph(canonical_snapshot.case_id)
                if current is None:
                    raise CaseNotFound()
                case = current.case
                if case.evidence_revision != expected_evidence_revision:
                    raise DiagnosisInputStale()
                replay_row = self._connection.execute(
                    """
                    SELECT diagnosis_id
                    FROM diagnosis_snapshots
                    WHERE case_id = ? AND evidence_revision = ? AND policy_version = ?
                    """,
                    (
                        canonical_snapshot.case_id,
                        expected_evidence_revision,
                        canonical_snapshot.policy_version,
                    ),
                ).fetchone()
                if replay_row is not None:
                    replayed = self._load_diagnosis_snapshot_by_id(
                        canonical_snapshot.case_id,
                        _decode_uuid(replay_row["diagnosis_id"]),
                    )
                    if (
                        replayed is None
                        or replayed.status is not DiagnosisStatus.CURRENT
                        or case.current_diagnosis_id != replayed.diagnosis_id
                        or current.current_diagnosis != replayed
                    ):
                        raise PersistenceInvariantViolation()
                    return CommitDiagnosisResult(
                        outcome=WriteOutcome.REPLAY,
                        case_view=current,
                        diagnosis=replayed,
                    )
                if case.case_revision != expected_case_revision:
                    raise ConcurrentCaseWrite()
                if case.status is not CaseStatus.EVIDENCE_READY:
                    raise PersistenceInvariantViolation()

                required_types = {
                    AuditEventType.DIAGNOSIS_CREATED,
                    AuditEventType.STATE_TRANSITIONED,
                }
                if canonical_snapshot.routing_decision is not None:
                    required_types.add(AuditEventType.ROUTING_PROPOSED)
                validated_audits = _validate_audit_batch(
                    events,
                    case_id=case.case_id,
                    required_types=frozenset(required_types),
                    from_status=case.status,
                    to_status=target_status,
                    case_revision=expected_case_revision + 1,
                    evidence_revision=expected_evidence_revision,
                )

                _insert_diagnosis(self._connection, canonical_snapshot)
                cursor = self._connection.execute(
                    """
                    UPDATE cases
                    SET status = ?, case_revision = ?, updated_at = ?,
                        current_diagnosis_id = ?
                    WHERE case_id = ? AND case_revision = ? AND evidence_revision = ?
                    """,
                    (
                        target_status.value,
                        expected_case_revision + 1,
                        _encode_datetime(max(case.updated_at, canonical_snapshot.created_at)),
                        canonical_snapshot.diagnosis_id,
                        case.case_id,
                        expected_case_revision,
                        expected_evidence_revision,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ConcurrentCaseWrite()
                for event in validated_audits:
                    _insert_audit(self._connection, event)
                fresh = self._load_case_graph(case.case_id)
                if fresh is None or fresh.current_diagnosis is None:
                    raise PersistenceInvariantViolation()

            return CommitDiagnosisResult(
                outcome=WriteOutcome.CREATED,
                case_view=fresh,
                diagnosis=fresh.current_diagnosis,
            )

        return _call_with_error_mapping(operation)

    def _load_case_graph(self, case_id: str) -> CaseView | None:
        case_row = self._connection.execute(
            """
            SELECT case_id, case_type, status, schema_version, case_revision,
                   evidence_revision, synthetic, summary, merchant_ref, created_at,
                   updated_at, current_diagnosis_id, readiness_json
            FROM cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()
        if case_row is None:
            return None

        evidence = tuple(
            _decode_evidence_row(row)
            for row in self._connection.execute(
                """
                SELECT case_id, evidence_id, schema_version, evidence_code,
                       availability, value_type, typed_value_json, source_type,
                       source_ref, source_reliability, observed_at, collected_at,
                       synthetic, content_hash
                FROM evidence_items
                WHERE case_id = ?
                ORDER BY evidence_id
                """,
                (case_id,),
            ).fetchall()
        )
        if any(item.case_id != case_id for item in evidence):
            raise PersistenceInvariantViolation()

        pointer_raw = case_row["current_diagnosis_id"]
        pointer = _decode_uuid(pointer_raw) if pointer_raw is not None else None
        diagnosis = (
            self._load_diagnosis_snapshot_by_id(case_id, pointer) if pointer is not None else None
        )
        synthetic = decode_sqlite_bool("case.synthetic", case_row["synthetic"])
        if synthetic is not True:
            raise PersistenceInvariantViolation()
        case = _invariant_call(
            lambda: MerchantSuccessCase(
                case_id=_decode_uuid(case_row["case_id"]),
                case_type=CaseType(_require_text(case_row["case_type"])),
                status=CaseStatus(_require_text(case_row["status"])),
                schema_version=_require_text(case_row["schema_version"]),
                case_revision=_require_int(case_row["case_revision"]),
                evidence_revision=_require_int(case_row["evidence_revision"]),
                synthetic=synthetic,
                summary=_require_text(case_row["summary"]),
                merchant_ref=_require_text(case_row["merchant_ref"]),
                created_at=_decode_datetime(case_row["created_at"]),
                updated_at=_decode_datetime(case_row["updated_at"]),
                current_diagnosis_id=pointer,
                readiness=_decode_readiness(case_row["readiness_json"]),
            )
        )
        if case.case_id != case_id:
            raise PersistenceInvariantViolation()
        view = _invariant_call(
            lambda: CaseView(
                case=case,
                evidence=evidence,
                current_diagnosis=diagnosis,
            )
        )
        return _validate_case_graph(view)

    def _load_diagnosis_snapshot_by_id(
        self,
        case_id: str,
        diagnosis_id: str,
    ) -> DiagnosisSnapshot | None:
        row = self._connection.execute(
            """
            SELECT case_id, diagnosis_id, evidence_revision, policy_version,
                   engine_version, status, routing_json, ticket_json, requires_human,
                   review_reasons_json, synthetic, created_at
            FROM diagnosis_snapshots
            WHERE case_id = ? AND diagnosis_id = ?
            """,
            (case_id, diagnosis_id),
        ).fetchone()
        if row is None:
            return None

        hypotheses: list[Hypothesis] = []
        for hypothesis_row in self._connection.execute(
            """
            SELECT case_id, hypothesis_id, diagnosis_id, cause_code, explanation,
                   confidence_score, confidence_method, next_verification_action,
                   rule_id
            FROM hypotheses
            WHERE case_id = ? AND diagnosis_id = ?
            ORDER BY hypothesis_id
            """,
            (case_id, diagnosis_id),
        ).fetchall():
            hypothesis_id = _decode_uuid(hypothesis_row["hypothesis_id"])
            refs = tuple(
                _decode_uuid(ref_row["evidence_id"])
                for ref_row in self._connection.execute(
                    """
                    SELECT evidence_id
                    FROM hypothesis_evidence_refs
                    WHERE case_id = ? AND hypothesis_id = ?
                    ORDER BY evidence_id
                    """,
                    (case_id, hypothesis_id),
                ).fetchall()
            )
            hypothesis = _invariant_call(
                lambda hypothesis_id=hypothesis_id, hypothesis_row=hypothesis_row, refs=refs: (
                    Hypothesis(
                        hypothesis_id=hypothesis_id,
                        cause_code=_require_text(hypothesis_row["cause_code"]),
                        explanation=_require_text(hypothesis_row["explanation"]),
                        evidence_refs=refs,
                        confidence_score=_decimal(hypothesis_row["confidence_score"]),
                        confidence_method=_require_text(hypothesis_row["confidence_method"]),
                        next_verification_action=_require_text(
                            hypothesis_row["next_verification_action"]
                        ),
                        rule_id=_require_text(hypothesis_row["rule_id"]),
                    )
                )
            )
            if (
                _decode_uuid(hypothesis_row["case_id"]) != case_id
                or _decode_uuid(hypothesis_row["diagnosis_id"]) != diagnosis_id
            ):
                raise PersistenceInvariantViolation()
            hypotheses.append(hypothesis)

        requires_human = decode_sqlite_bool("diagnosis.requires_human", row["requires_human"])
        synthetic = decode_sqlite_bool("diagnosis.synthetic", row["synthetic"])
        if synthetic is not True:
            raise PersistenceInvariantViolation()
        review_reasons = _review_reasons(_decode_json(row["review_reasons_json"]))
        snapshot = _invariant_call(
            lambda: DiagnosisSnapshot(
                diagnosis_id=_decode_uuid(row["diagnosis_id"]),
                case_id=_decode_uuid(row["case_id"]),
                evidence_revision=_require_int(row["evidence_revision"]),
                policy_version=_require_text(row["policy_version"]),
                engine_version=_require_text(row["engine_version"]),
                status=DiagnosisStatus(_require_text(row["status"])),
                hypotheses=tuple(hypotheses),
                routing_decision=_decode_routing(row["routing_json"]),
                ticket_draft=_decode_ticket(row["ticket_json"]),
                requires_human=requires_human,
                review_reasons=review_reasons,
                synthetic=synthetic,
                created_at=_decode_datetime(row["created_at"]),
            )
        )
        if snapshot.case_id != case_id or snapshot.diagnosis_id != diagnosis_id:
            raise PersistenceInvariantViolation()
        return _validate_diagnosis_snapshot(snapshot)


class SqliteCaseStoreFactory:
    def __init__(self, path: Path) -> None:
        self._path = path

    @contextmanager
    def __call__(self) -> Iterator[SqliteCaseStoreSession]:
        connection = connect_sqlite(self._path)
        try:
            yield SqliteCaseStoreSession(connection)
        finally:
            connection.close()

    def get_case_history(
        self,
        case_id: str,
        *,
        limit: int = 200,
    ) -> tuple[CaseView | None, tuple[AuditEvent, ...], bool]:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")

        def operation() -> tuple[CaseView | None, tuple[AuditEvent, ...], bool]:
            normalized_case_id = _decode_uuid(case_id)
            with self() as store, _deferred_read_transaction(store._connection):
                view = store._load_case_graph(normalized_case_id)
                if view is None:
                    return None, (), False
                rows = store._connection.execute(
                    """
                    SELECT case_id, event_id, event_type, event_version, request_id,
                           trace_id, actor_type, action, from_status, to_status,
                           case_revision, evidence_revision, occurred_at, result,
                           reason_code, sanitized_metadata_json, synthetic
                    FROM audit_events
                    WHERE case_id = ?
                    ORDER BY occurred_at,
                        CASE event_type
                            WHEN 'CASE_CREATED' THEN 10
                            WHEN 'EVIDENCE_ADDED' THEN 20
                            WHEN 'DIAGNOSIS_SUPERSEDED' THEN 30
                            WHEN 'DIAGNOSIS_CREATED' THEN 40
                            WHEN 'ROUTING_PROPOSED' THEN 50
                            WHEN 'STATE_TRANSITIONED' THEN 60
                            ELSE 100
                        END,
                        event_id
                    LIMIT ?
                    """,
                    (normalized_case_id, limit + 1),
                ).fetchall()
                events = tuple(_decode_audit_row(row) for row in rows[:limit])
                if any(event.case_id != normalized_case_id for event in events):
                    raise PersistenceInvariantViolation()
                return view, events, len(rows) > limit

        return _call_with_error_mapping(operation)
