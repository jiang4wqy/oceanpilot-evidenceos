from decimal import Decimal
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr

from oceanpilot.application.errors import CaseNotFound, DatabaseUnavailable
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
)
from oceanpilot.domain.evidence_policy import build_active_evidence_view
from oceanpilot.domain.models import (
    AuditEvent,
    AwareDateTime,
    CaseView,
    SyntheticTrue,
    UUID4Str,
)
from oceanpilot.domain.security import assert_no_sensitive_data


class DemoModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )


class DemoActiveState(StrEnum):
    SELECTED = "SELECTED"
    CONFLICTING = "CONFLICTING"
    KNOWN_UNKNOWN = "KNOWN_UNKNOWN"
    HISTORICAL = "HISTORICAL"


class DemoConfirmationState(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"


class DemoCaseSummary(DemoModel):
    case_id: UUID4Str
    case_type: CaseType
    summary: StrictStr
    merchant_ref: StrictStr
    status: CaseStatus
    case_revision: int
    evidence_revision: int
    created_at: AwareDateTime
    updated_at: AwareDateTime


class DemoReadiness(DemoModel):
    ready: StrictBool
    completion_ratio: Decimal
    missing_fields: tuple[StrictStr, ...]
    known_unknown_fields: tuple[StrictStr, ...]
    next_question: StrictStr | None
    question_reason: StrictStr | None
    target_role: TargetRole | None
    stop_reason: StopReason


class DemoEvidence(DemoModel):
    evidence_id: UUID4Str
    evidence_code: EvidenceCode
    availability: EvidenceAvailability
    value_type: EvidenceValueType
    typed_value: StrictStr | StrictBool | AwareDateTime | None
    source_type: SourceType
    source_reliability: SourceReliability
    observed_at: AwareDateTime | None
    collected_at: AwareDateTime
    active_state: DemoActiveState


class DemoCitation(DemoModel):
    evidence_id: UUID4Str
    evidence_code: EvidenceCode


class DemoHypothesis(DemoModel):
    hypothesis_id: UUID4Str
    cause_code: StrictStr
    explanation: StrictStr
    confidence_score: Decimal
    confidence_method: Literal["HEURISTIC_V1"]
    next_verification_action: StrictStr
    rule_id: StrictStr
    citations: tuple[DemoCitation, ...]


class DemoRouting(DemoModel):
    responsible_team: ResponsibleTeam
    priority: Priority
    reason: StrictStr
    requires_human: StrictBool
    review_reasons: frozenset[ReviewReason]
    citations: tuple[DemoCitation, ...]


class DemoDiagnosis(DemoModel):
    diagnosis_id: UUID4Str
    status: DiagnosisStatus
    evidence_revision: int
    policy_version: StrictStr
    engine_version: StrictStr
    created_at: AwareDateTime
    requires_human: StrictBool
    review_reasons: frozenset[ReviewReason]
    hypotheses: tuple[DemoHypothesis, ...]
    routing: DemoRouting | None
    next_action: StrictStr | None


class DemoConfirmation(DemoModel):
    state: DemoConfirmationState
    result: Literal["CONFIRMED"] | None = None
    occurred_at: AwareDateTime | None = None


class DemoTimelineEntry(DemoModel):
    event_type: AuditEventType
    actor_type: AuditActorType
    from_status: CaseStatus | None
    to_status: CaseStatus | None
    case_revision: int
    evidence_revision: int
    occurred_at: AwareDateTime
    result: StrictStr
    reason_code: StrictStr | None


class DemoCaseDetail(DemoModel):
    synthetic: SyntheticTrue = True
    read_only: SyntheticTrue = True
    data_consistency: Literal["READ_ONLY_BEST_EFFORT"] = "READ_ONLY_BEST_EFFORT"
    case: DemoCaseSummary
    readiness: DemoReadiness
    evidence: tuple[DemoEvidence, ...]
    diagnosis: DemoDiagnosis | None
    confirmation: DemoConfirmation
    timeline: tuple[DemoTimelineEntry, ...]
    audit_truncated: StrictBool


class DemoConfirmationRecord(DemoModel):
    result: Literal["CONFIRMED"]
    occurred_at: AwareDateTime
    synthetic: SyntheticTrue = True


class DemoCoreReadPort(Protocol):
    def get_case_history(
        self,
        case_id: str,
        *,
        limit: int = 200,
    ) -> tuple[CaseView | None, tuple[AuditEvent, ...], bool]: ...


class DemoConfirmationReadPort(Protocol):
    def find_confirmation(
        self,
        *,
        case_id: str,
        diagnosis_id: str,
    ) -> DemoConfirmationRecord | None: ...


def _citation(evidence_by_id, evidence_id: str) -> DemoCitation:
    item = evidence_by_id[evidence_id]
    return DemoCitation(evidence_id=item.evidence_id, evidence_code=item.evidence_code)


class DemoQuery:
    def __init__(
        self,
        core_store: DemoCoreReadPort,
        confirmation_reader: DemoConfirmationReadPort | None,
    ) -> None:
        self._core_store = core_store
        self._confirmation_reader = confirmation_reader

    def get_case_detail(self, case_id: str) -> DemoCaseDetail:
        view, audit_events, truncated = self._core_store.get_case_history(case_id)
        if view is None:
            raise CaseNotFound()
        active = build_active_evidence_view(view.evidence)
        selected_ids = {
            slot.selected_evidence.evidence_id
            for slot in active.slots.values()
            if slot.selected_evidence is not None
        }
        evidence_by_id = {item.evidence_id: item for item in view.evidence}
        demo_evidence = []
        for item in view.evidence:
            slot = active.slots[item.evidence_code]
            state = DemoActiveState.HISTORICAL
            if item.evidence_id in selected_ids:
                state = (
                    DemoActiveState.CONFLICTING if slot.conflicting else DemoActiveState.SELECTED
                )
            elif slot.known_unknown:
                state = DemoActiveState.KNOWN_UNKNOWN
            demo_evidence.append(
                DemoEvidence(
                    evidence_id=item.evidence_id,
                    evidence_code=item.evidence_code,
                    availability=item.availability,
                    value_type=item.value_type,
                    typed_value=item.typed_value,
                    source_type=item.source_type,
                    source_reliability=item.source_reliability,
                    observed_at=item.observed_at,
                    collected_at=item.collected_at,
                    active_state=state,
                )
            )

        snapshot = view.current_diagnosis
        diagnosis = None
        if snapshot is not None:
            hypotheses = tuple(
                DemoHypothesis(
                    hypothesis_id=item.hypothesis_id,
                    cause_code=item.cause_code,
                    explanation=item.explanation,
                    confidence_score=item.confidence_score,
                    confidence_method=item.confidence_method,
                    next_verification_action=item.next_verification_action,
                    rule_id=item.rule_id,
                    citations=tuple(_citation(evidence_by_id, ref) for ref in item.evidence_refs),
                )
                for item in snapshot.hypotheses
            )
            route = snapshot.routing_decision
            diagnosis = DemoDiagnosis(
                diagnosis_id=snapshot.diagnosis_id,
                status=snapshot.status,
                evidence_revision=snapshot.evidence_revision,
                policy_version=snapshot.policy_version,
                engine_version=snapshot.engine_version,
                created_at=snapshot.created_at,
                requires_human=snapshot.requires_human,
                review_reasons=snapshot.review_reasons,
                hypotheses=hypotheses,
                routing=(
                    DemoRouting(
                        responsible_team=route.responsible_team,
                        priority=route.priority,
                        reason=route.reason,
                        requires_human=route.requires_human,
                        review_reasons=route.review_reasons,
                        citations=tuple(
                            _citation(evidence_by_id, ref) for ref in route.evidence_refs
                        ),
                    )
                    if route is not None
                    else None
                ),
                next_action=(
                    snapshot.ticket_draft.next_action if snapshot.ticket_draft is not None else None
                ),
            )

        confirmation = self._confirmation(case_id, diagnosis)
        detail = DemoCaseDetail(
            case=DemoCaseSummary(
                case_id=view.case.case_id,
                case_type=view.case.case_type,
                summary=view.case.summary,
                merchant_ref=view.case.merchant_ref,
                status=view.case.status,
                case_revision=view.case.case_revision,
                evidence_revision=view.case.evidence_revision,
                created_at=view.case.created_at,
                updated_at=view.case.updated_at,
            ),
            readiness=DemoReadiness(**view.case.readiness.model_dump()),
            evidence=tuple(demo_evidence),
            diagnosis=diagnosis,
            confirmation=confirmation,
            timeline=tuple(
                DemoTimelineEntry(
                    event_type=event.event_type,
                    actor_type=event.actor_type,
                    from_status=event.from_status,
                    to_status=event.to_status,
                    case_revision=event.case_revision,
                    evidence_revision=event.evidence_revision,
                    occurred_at=event.occurred_at,
                    result=event.result,
                    reason_code=event.reason_code,
                )
                for event in audit_events
            ),
            audit_truncated=truncated,
        )
        assert_no_sensitive_data(detail)
        return detail

    def _confirmation(
        self,
        case_id: str,
        diagnosis: DemoDiagnosis | None,
    ) -> DemoConfirmation:
        if diagnosis is None:
            return DemoConfirmation(state=DemoConfirmationState.NOT_APPLICABLE)
        if not diagnosis.requires_human:
            return DemoConfirmation(state=DemoConfirmationState.NOT_REQUIRED)
        if self._confirmation_reader is None:
            return DemoConfirmation(state=DemoConfirmationState.UNAVAILABLE)
        try:
            audit = self._confirmation_reader.find_confirmation(
                case_id=case_id,
                diagnosis_id=diagnosis.diagnosis_id,
            )
        except DatabaseUnavailable:
            return DemoConfirmation(state=DemoConfirmationState.UNAVAILABLE)
        if audit is None:
            return DemoConfirmation(state=DemoConfirmationState.AWAITING_CONFIRMATION)
        return DemoConfirmation(
            state=DemoConfirmationState.CONFIRMED,
            result="CONFIRMED",
            occurred_at=audit.occurred_at,
        )
