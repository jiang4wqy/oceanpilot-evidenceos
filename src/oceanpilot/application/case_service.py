from collections.abc import Callable, Sequence
from datetime import datetime

from oceanpilot.application.commands import (
    AddEvidenceCommand,
    CreateCaseCommand,
    DiagnoseCaseCommand,
)
from oceanpilot.application.errors import (
    CaseNotFound,
    CaseNotReady,
    CaseTypeNotEnabled,
    DiagnosisInputStale,
    PersistenceInvariantViolation,
)
from oceanpilot.application.ports import CaseStoreFactory
from oceanpilot.domain.diagnosis import DiagnosisEngine
from oceanpilot.domain.enums import (
    AuditActorType,
    AuditEventType,
    CaseStatus,
    CaseType,
    DiagnosisStatus,
    SourceType,
    WriteOutcome,
)
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
    CommandResult,
    DiagnosisDraft,
    DiagnosisSnapshot,
    DiagnosisView,
    Hypothesis,
    MerchantSuccessCase,
)
from oceanpilot.domain.security import assert_no_sensitive_data
from oceanpilot.domain.state_machine import (
    status_after_creation,
    status_after_diagnosis,
    status_after_evidence,
)

CASE_SCHEMA_VERSION = "1"
AUDIT_EVENT_VERSION = "1"
DIAGNOSIS_ATTEMPTS = 3


class CaseService:
    def __init__(
        self,
        store_factory: CaseStoreFactory,
        diagnosis_engine: DiagnosisEngine,
        *,
        clock: Callable[[], datetime],
        uuid_factory: Callable[[], str],
        policy_version: str = "POLICY_V1",
        engine_version: str = "RULES_V1",
    ) -> None:
        self._store_factory = store_factory
        self._diagnosis_engine = diagnosis_engine
        self._clock = clock
        self._uuid_factory = uuid_factory
        self._policy_version = policy_version
        self._engine_version = engine_version

    def _audit_events(
        self,
        *,
        event_types: Sequence[AuditEventType],
        command: AddEvidenceCommand,
        from_status: CaseStatus,
        to_status: CaseStatus,
        case_revision: int,
        evidence_revision: int,
        occurred_at: datetime,
    ) -> tuple[AuditEvent, ...]:
        actor = (
            AuditActorType.SYNTHETIC_ADAPTER
            if command.origin.source_type is SourceType.SYNTHETIC_ADAPTER
            else AuditActorType.MERCHANT
        )
        return tuple(
            AuditEvent(
                event_id=self._uuid_factory(),
                event_type=event_type,
                event_version=AUDIT_EVENT_VERSION,
                case_id=command.case_id,
                request_id=command.request_id,
                trace_id=command.trace_id,
                actor_type=actor,
                action="add_evidence",
                from_status=from_status,
                to_status=to_status,
                case_revision=case_revision,
                evidence_revision=evidence_revision,
                occurred_at=occurred_at,
                result="CREATED",
                reason_code=None,
                sanitized_metadata={"event_type": event_type.value},
                synthetic=True,
            )
            for event_type in event_types
        )

    def create_case(self, command: CreateCaseCommand) -> CaseView:
        assert_no_sensitive_data(command)
        if command.case_type is not CaseType.PAYMENT_INCIDENT:
            raise CaseTypeNotEnabled()

        readiness = assess_readiness(build_active_evidence_view(()))
        status = status_after_creation(readiness)
        now = self._clock()
        case_id = self._uuid_factory()
        audit_id = self._uuid_factory()
        case = MerchantSuccessCase(
            case_id=case_id,
            case_type=command.case_type,
            status=status,
            schema_version=CASE_SCHEMA_VERSION,
            case_revision=1,
            evidence_revision=0,
            synthetic=command.synthetic,
            summary=command.summary,
            merchant_ref=command.merchant_ref,
            created_at=now,
            updated_at=now,
            current_diagnosis_id=None,
            readiness=readiness,
        )
        audit = AuditEvent(
            event_id=audit_id,
            event_type=AuditEventType.CASE_CREATED,
            event_version=AUDIT_EVENT_VERSION,
            case_id=case_id,
            request_id=command.request_id,
            trace_id=command.trace_id,
            actor_type=AuditActorType.MERCHANT,
            action="create_case",
            from_status=None,
            to_status=status,
            case_revision=1,
            evidence_revision=0,
            occurred_at=now,
            result="CREATED",
            reason_code=None,
            sanitized_metadata={},
            synthetic=True,
        )
        with self._store_factory() as store:
            return store.create_case_atomic(case=case, audit=audit)

    def get_case(self, case_id: str) -> CaseView:
        with self._store_factory() as store:
            view = store.get_case_view(case_id)
        if view is None:
            raise CaseNotFound()
        return view

    def add_evidence(self, command: AddEvidenceCommand) -> AppendEvidenceResult:
        assert_no_sensitive_data(command)
        with self._store_factory() as store:
            snapshot = store.load_case_snapshot(command.case_id)
            if snapshot is None:
                raise CaseNotFound()

            now = self._clock()
            evidence = create_evidence_item(
                command.evidence,
                case_id=command.case_id,
                origin=command.origin,
                collected_at=now,
            )
            if any(item.evidence_id == evidence.evidence_id for item in snapshot.evidence):
                return store.append_evidence_atomic(
                    expected_case_revision=snapshot.case.case_revision,
                    expected_evidence_revision=snapshot.case.evidence_revision,
                    evidence=evidence,
                    readiness=snapshot.case.readiness,
                    target_status=snapshot.case.status,
                    audit_events=(),
                )

            readiness = assess_readiness(build_active_evidence_view((*snapshot.evidence, evidence)))
            target_status = status_after_evidence(snapshot.case.status, readiness)
            event_types = [AuditEventType.EVIDENCE_ADDED]
            if snapshot.case.status in (CaseStatus.DIAGNOSED, CaseStatus.HUMAN_REVIEW):
                event_types.append(AuditEventType.DIAGNOSIS_SUPERSEDED)
            if target_status is not snapshot.case.status:
                event_types.append(AuditEventType.STATE_TRANSITIONED)
            audit_events = self._audit_events(
                event_types=event_types,
                command=command,
                from_status=snapshot.case.status,
                to_status=target_status,
                case_revision=snapshot.case.case_revision + 1,
                evidence_revision=snapshot.case.evidence_revision + 1,
                occurred_at=now,
            )
            return store.append_evidence_atomic(
                expected_case_revision=snapshot.case.case_revision,
                expected_evidence_revision=snapshot.case.evidence_revision,
                evidence=evidence,
                readiness=readiness,
                target_status=target_status,
                audit_events=audit_events,
            )

    @staticmethod
    def _diagnosis_result(
        *,
        outcome: WriteOutcome,
        case_view: CaseView,
        diagnosis: DiagnosisSnapshot,
    ) -> CommandResult[DiagnosisView]:
        return CommandResult(
            outcome=outcome,
            value=DiagnosisView(
                case_id=case_view.case.case_id,
                case_status=case_view.case.status,
                case_revision=case_view.case.case_revision,
                evidence_revision=case_view.case.evidence_revision,
                diagnosis=diagnosis,
            ),
        )

    def _diagnosis_audit_events(
        self,
        *,
        command: DiagnoseCaseCommand,
        snapshot: CaseInputSnapshot,
        draft: DiagnosisDraft,
        target_status: CaseStatus,
        occurred_at: datetime,
    ) -> tuple[AuditEvent, ...]:
        event_types = [AuditEventType.DIAGNOSIS_CREATED]
        if draft.routing_decision is not None:
            event_types.append(AuditEventType.ROUTING_PROPOSED)
        event_types.append(AuditEventType.STATE_TRANSITIONED)
        return tuple(
            AuditEvent(
                event_id=self._uuid_factory(),
                event_type=event_type,
                event_version=AUDIT_EVENT_VERSION,
                case_id=snapshot.case.case_id,
                request_id=command.request_id,
                trace_id=command.trace_id,
                actor_type=AuditActorType.INTERNAL_SYSTEM,
                action="diagnose",
                from_status=snapshot.case.status,
                to_status=target_status,
                case_revision=snapshot.case.case_revision + 1,
                evidence_revision=snapshot.case.evidence_revision,
                occurred_at=occurred_at,
                result="CREATED",
                reason_code=None,
                sanitized_metadata={"event_type": event_type.value},
                synthetic=True,
            )
            for event_type in event_types
        )

    def _replay_diagnosis(
        self,
        snapshot: CaseInputSnapshot,
        diagnosis: DiagnosisSnapshot,
    ) -> CommandResult[DiagnosisView]:
        if (
            diagnosis.status is not DiagnosisStatus.CURRENT
            or snapshot.current_diagnosis != diagnosis
            or snapshot.case.current_diagnosis_id != diagnosis.diagnosis_id
        ):
            raise PersistenceInvariantViolation()
        return self._diagnosis_result(
            outcome=WriteOutcome.REPLAY,
            case_view=CaseView(
                case=snapshot.case,
                evidence=snapshot.evidence,
                current_diagnosis=diagnosis,
            ),
            diagnosis=diagnosis,
        )

    def diagnose(
        self,
        command: DiagnoseCaseCommand,
    ) -> CommandResult[DiagnosisView]:
        assert_no_sensitive_data(command)
        with self._store_factory() as store:
            for attempt in range(DIAGNOSIS_ATTEMPTS):
                case_input = store.load_case_snapshot(command.case_id)
                if case_input is None:
                    raise CaseNotFound()

                if case_input.case.status in (
                    CaseStatus.DIAGNOSED,
                    CaseStatus.HUMAN_REVIEW,
                ):
                    existing = store.find_diagnosis(
                        case_id=case_input.case.case_id,
                        evidence_revision=case_input.case.evidence_revision,
                        policy_version=self._policy_version,
                    )
                    if existing is not None:
                        return self._replay_diagnosis(case_input, existing)

                if case_input.case.status is not CaseStatus.EVIDENCE_READY:
                    raise CaseNotReady(
                        case_id=case_input.case.case_id,
                        missing_fields=case_input.case.readiness.missing_fields,
                        current_revision=case_input.case.case_revision,
                    )

                existing = store.find_diagnosis(
                    case_id=case_input.case.case_id,
                    evidence_revision=case_input.case.evidence_revision,
                    policy_version=self._policy_version,
                )
                if existing is not None:
                    fresh = store.load_case_snapshot(command.case_id)
                    if fresh is None:
                        raise CaseNotFound()
                    if fresh.case.evidence_revision != case_input.case.evidence_revision:
                        if attempt + 1 == DIAGNOSIS_ATTEMPTS:
                            raise DiagnosisInputStale()
                        continue
                    return self._replay_diagnosis(fresh, existing)

                active_view = build_active_evidence_view(case_input.evidence)
                draft = self._diagnosis_engine.evaluate(
                    case_input.case,
                    active_view,
                    policy_version=self._policy_version,
                )
                target_status = status_after_diagnosis(draft)
                now = self._clock()
                diagnosis_id = self._uuid_factory()
                hypotheses = tuple(
                    Hypothesis(
                        hypothesis_id=self._uuid_factory(),
                        **hypothesis.model_dump(mode="python"),
                    )
                    for hypothesis in draft.hypotheses
                )
                diagnosis = DiagnosisSnapshot(
                    diagnosis_id=diagnosis_id,
                    case_id=case_input.case.case_id,
                    evidence_revision=case_input.case.evidence_revision,
                    policy_version=self._policy_version,
                    engine_version=self._engine_version,
                    status=DiagnosisStatus.CURRENT,
                    hypotheses=hypotheses,
                    routing_decision=draft.routing_decision,
                    ticket_draft=draft.ticket_draft,
                    requires_human=draft.requires_human,
                    review_reasons=draft.review_reasons,
                    synthetic=case_input.case.synthetic,
                    created_at=now,
                )
                audits = self._diagnosis_audit_events(
                    command=command,
                    snapshot=case_input,
                    draft=draft,
                    target_status=target_status,
                    occurred_at=now,
                )
                try:
                    committed = store.commit_diagnosis_atomic(
                        expected_case_revision=case_input.case.case_revision,
                        expected_evidence_revision=case_input.case.evidence_revision,
                        snapshot=diagnosis,
                        target_status=target_status,
                        audit_events=audits,
                    )
                except DiagnosisInputStale:
                    if attempt + 1 == DIAGNOSIS_ATTEMPTS:
                        raise
                    continue
                return self._diagnosis_result(
                    outcome=committed.outcome,
                    case_view=committed.case_view,
                    diagnosis=committed.diagnosis,
                )
        raise PersistenceInvariantViolation()
