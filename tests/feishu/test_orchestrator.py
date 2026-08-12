from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from oceanpilot.application.feishu_models import (
    FeishuConfirmation,
    FeishuConfirmationReceipt,
    FeishuEvidenceSubmission,
    FeishuFlowOutcome,
    FeishuFlowResult,
    FeishuIncident,
)
from oceanpilot.application.feishu_orchestrator import (
    FeishuBindingInProgress,
    FeishuCaseNotBound,
    FeishuOrchestrator,
    InvalidReviewConfirmation,
)
from oceanpilot.application.feishu_ports import (
    FeishuBindingClaim,
    FeishuBindingOutcome,
)
from oceanpilot.domain.enums import (
    CaseStatus,
    CaseType,
    DiagnosisStatus,
    EvidenceAvailability,
    ReviewReason,
    SourceReliability,
    SourceType,
    StopReason,
    TargetRole,
    WriteOutcome,
)
from oceanpilot.domain.models import (
    AppendEvidenceResult,
    CaseView,
    CommandResult,
    DiagnosisSnapshot,
    DiagnosisView,
    MerchantSuccessCase,
    ReadinessAssessment,
)

NOW = datetime(2026, 8, 5, 4, 0, tzinfo=UTC)
LEASE_EXPIRES_AT = datetime(2026, 8, 5, 4, 0, 30, tzinfo=UTC)
CLAIM_TOKEN = "c" * 64
CASE_ID = "00000000-0000-4000-8000-000000000010"
OTHER_CASE_ID = "00000000-0000-4000-8000-000000000011"
DIAGNOSIS_ID = "00000000-0000-4000-8000-000000000050"
OTHER_DIAGNOSIS_ID = "00000000-0000-4000-8000-000000000051"
EVIDENCE_ID = "00000000-0000-4000-8000-000000000101"
REQUEST_ID = "00000000-0000-4000-8000-000000000030"
TRACE_ID = "00000000-0000-4000-8000-000000000040"
ACTOR_HASH = "a" * 64


def _case_view(*, ready: bool, diagnosis: DiagnosisSnapshot | None = None) -> CaseView:
    readiness = ReadinessAssessment(
        ready=ready,
        missing_fields=() if ready else ("transaction.reference",),
        known_unknown_fields=(),
        next_question=None if ready else "transaction.reference",
        question_reason=None if ready else "Locate the transaction",
        target_role=None if ready else TargetRole.MERCHANT_TECH,
        completion_ratio="1" if ready else "0.8",
        stop_reason=StopReason.READY if ready else StopReason.NEED_MORE_EVIDENCE,
    )
    status = (
        CaseStatus.HUMAN_REVIEW
        if diagnosis is not None
        else CaseStatus.EVIDENCE_READY
        if ready
        else CaseStatus.NEED_INFO
    )
    case = MerchantSuccessCase(
        case_id=CASE_ID,
        case_type=CaseType.PAYMENT_INCIDENT,
        status=status,
        schema_version="1",
        case_revision=7 if diagnosis is not None else 6,
        evidence_revision=5,
        synthetic=True,
        summary="Synthetic Feishu incident",
        merchant_ref="merchant_feishu_001",
        created_at=NOW,
        updated_at=NOW,
        current_diagnosis_id=diagnosis.diagnosis_id if diagnosis is not None else None,
        readiness=readiness,
    )
    return CaseView(case=case, evidence=(), current_diagnosis=diagnosis)


def _human_diagnosis() -> DiagnosisSnapshot:
    return DiagnosisSnapshot(
        diagnosis_id=DIAGNOSIS_ID,
        case_id=CASE_ID,
        evidence_revision=5,
        policy_version="POLICY_V1",
        engine_version="RULES_V1",
        status=DiagnosisStatus.CURRENT,
        hypotheses=(),
        routing_decision=None,
        ticket_draft=None,
        requires_human=True,
        review_reasons=frozenset({ReviewReason.POLICY_GAP}),
        synthetic=True,
        created_at=NOW,
    )


class _CaseService:
    def __init__(self) -> None:
        self.created_command = None
        self.evidence_command = None
        self.diagnose_command = None
        self.create_result = _case_view(ready=False)
        self.get_result = self.create_result
        self.evidence_result = AppendEvidenceResult(
            outcome=WriteOutcome.CREATED,
            case_view=_case_view(ready=False),
        )
        diagnosis = _human_diagnosis()
        self.diagnosis_result = CommandResult(
            outcome=WriteOutcome.CREATED,
            value=DiagnosisView(
                case_id=CASE_ID,
                case_status=CaseStatus.HUMAN_REVIEW,
                case_revision=7,
                evidence_revision=5,
                diagnosis=diagnosis,
            ),
        )
        self.create_error = None
        self.recovery_result = None

    def new_case_id(self):
        return CASE_ID

    def create_case(self, command):
        self.created_command = command
        if self.create_error is not None:
            raise self.create_error
        return self.create_result

    def get_case(self, case_id):
        assert case_id == CASE_ID
        return self.get_result

    def find_case(self, case_id):
        assert case_id == CASE_ID
        return self.recovery_result

    def add_evidence(self, command):
        self.evidence_command = command
        return self.evidence_result

    def diagnose(self, command):
        self.diagnose_command = command
        return self.diagnosis_result


class _Chats:
    def __init__(self, case_id=None, *, reserved_case_id=None) -> None:
        self.case_id = case_id
        self.reserved_case_id = reserved_case_id
        self.bindings = []
        self.binding_in_progress = False

    def get_case_id(self, binding_key):
        assert binding_key == "tenant:chat:thread"
        return self.case_id

    def claim_case_binding(
        self,
        binding_key,
        event_id,
        case_id,
        *,
        claim_token,
        now,
        lease_expires_at,
    ):
        assert binding_key == "tenant:chat:thread"
        if self.case_id is not None:
            return FeishuBindingClaim(
                outcome=FeishuBindingOutcome.BOUND,
                case_id=self.case_id,
            )
        if self.binding_in_progress:
            return FeishuBindingClaim(
                outcome=FeishuBindingOutcome.IN_PROGRESS,
                case_id=self.reserved_case_id or case_id,
            )
        self.binding_in_progress = True
        reserved_case_id = self.reserved_case_id or case_id
        self.bindings.append(
            (
                "CLAIMED",
                binding_key,
                event_id,
                reserved_case_id,
                claim_token,
                now,
                lease_expires_at,
            )
        )
        return FeishuBindingClaim(
            outcome=FeishuBindingOutcome.CLAIMED,
            case_id=reserved_case_id,
        )

    def complete_case_binding(
        self,
        binding_key,
        event_id,
        case_id,
        *,
        claim_token,
        updated_at,
    ):
        self.bindings.append(
            ("BOUND", binding_key, event_id, case_id, claim_token, updated_at)
        )
        self.case_id = case_id
        return FeishuBindingClaim(
            outcome=FeishuBindingOutcome.BOUND,
            case_id=case_id,
        )

    def release_case_binding(self, binding_key, event_id, *, claim_token):
        self.bindings.append(("RELEASED", binding_key, event_id, claim_token))
        self.binding_in_progress = False


class _Approvals:
    def __init__(self) -> None:
        self.records = []

    def record_confirmation(self, record):
        self.records.append(record)
        return FeishuConfirmationReceipt(
            approval_id=record.approval_id,
            action_id=record.action_id,
            replayed=False,
        )


def _incident(**changes) -> FeishuIncident:
    values = {
        "binding_key": "tenant:chat:thread",
        "event_id": "event-create-001",
        "summary": "3DS callback was not received",
        "merchant_ref": "merchant_feishu_001",
        "occurred_at": NOW,
        "request_id": REQUEST_ID,
        "trace_id": TRACE_ID,
    }
    values.update(changes)
    return FeishuIncident(**values)


def _start_incident(orchestrator: FeishuOrchestrator) -> FeishuFlowResult:
    return orchestrator.start_incident(
        _incident(),
        claim_token=CLAIM_TOKEN,
        claimed_at=NOW,
        lease_expires_at=LEASE_EXPIRES_AT,
    )


def _evidence() -> FeishuEvidenceSubmission:
    return FeishuEvidenceSubmission(
        binding_key="tenant:chat:thread",
        event_id="event-evidence-001",
        evidence_id=EVIDENCE_ID,
        evidence_code="transaction.reference",
        availability=EvidenceAvailability.AVAILABLE,
        typed_value="txn_feishu_001",
        observed_at=NOW,
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
    )


def test_incident_model_does_not_allow_callers_to_set_trust_or_synthetic_flags():
    with pytest.raises(ValidationError):
        _incident(synthetic=False)
    with pytest.raises(ValidationError):
        FeishuEvidenceSubmission(
            **_evidence().model_dump(),
            source_reliability="SYSTEM_OF_RECORD",
        )


def test_start_incident_creates_one_synthetic_payment_case_and_binds_chat():
    service = _CaseService()
    chats = _Chats()
    orchestrator = FeishuOrchestrator(service, chats, _Approvals())

    result = _start_incident(orchestrator)

    assert result.outcome is FeishuFlowOutcome.NEED_INFO
    assert result.case_view == service.create_result
    assert result.diagnosis is None
    command = service.created_command
    assert command.case_type is CaseType.PAYMENT_INCIDENT
    assert command.summary == "3DS callback was not received"
    assert command.merchant_ref == "merchant_feishu_001"
    assert command.synthetic is True
    assert command.request_id == REQUEST_ID
    assert command.trace_id == TRACE_ID
    assert chats.bindings == [
        (
            "CLAIMED",
            "tenant:chat:thread",
            "event-create-001",
            CASE_ID,
            CLAIM_TOKEN,
            NOW,
            LEASE_EXPIRES_AT,
        ),
        (
            "BOUND",
            "tenant:chat:thread",
            "event-create-001",
            CASE_ID,
            CLAIM_TOKEN,
            NOW,
        ),
    ]


def test_start_incident_reuses_case_already_bound_to_chat():
    service = _CaseService()
    chats = _Chats(CASE_ID)
    orchestrator = FeishuOrchestrator(service, chats, _Approvals())

    result = _start_incident(orchestrator)

    assert result.outcome is FeishuFlowOutcome.NEED_INFO
    assert service.created_command is None
    assert chats.bindings == []


def test_start_incident_does_not_create_when_same_thread_binding_is_in_progress():
    service = _CaseService()
    chats = _Chats()
    chats.binding_in_progress = True
    orchestrator = FeishuOrchestrator(service, chats, _Approvals())

    with pytest.raises(FeishuBindingInProgress):
        _start_incident(orchestrator)

    assert service.created_command is None


def test_start_incident_preserves_reserved_binding_when_case_creation_fails():
    service = _CaseService()
    service.create_error = RuntimeError("synthetic failure")
    chats = _Chats()
    orchestrator = FeishuOrchestrator(service, chats, _Approvals())

    with pytest.raises(RuntimeError, match="synthetic failure"):
        _start_incident(orchestrator)

    assert chats.bindings == [
        (
            "CLAIMED",
            "tenant:chat:thread",
            "event-create-001",
            CASE_ID,
            CLAIM_TOKEN,
            NOW,
            LEASE_EXPIRES_AT,
        ),
    ]


def test_start_incident_recovers_created_reserved_case_before_completing_binding():
    service = _CaseService()
    service.recovery_result = service.create_result
    chats = _Chats(reserved_case_id=CASE_ID)
    orchestrator = FeishuOrchestrator(service, chats, _Approvals())

    result = _start_incident(orchestrator)

    assert result.case_view == service.create_result
    assert service.created_command is None
    assert chats.bindings[-1] == (
        "BOUND",
        "tenant:chat:thread",
        "event-create-001",
        CASE_ID,
        CLAIM_TOKEN,
        NOW,
    )


def test_submit_evidence_uses_fixed_merchant_origin_and_returns_next_question():
    service = _CaseService()
    orchestrator = FeishuOrchestrator(service, _Chats(CASE_ID), _Approvals())

    result = orchestrator.submit_evidence(_evidence())

    assert result.outcome is FeishuFlowOutcome.NEED_INFO
    assert result.diagnosis is None
    command = service.evidence_command
    assert command.case_id == CASE_ID
    assert command.evidence.evidence_id == EVIDENCE_ID
    assert command.evidence.source_ref == "feishu:event:event-evidence-001"
    assert command.origin.source_type is SourceType.MERCHANT
    assert command.origin.source_reliability is SourceReliability.USER_REPORTED
    assert command.origin.synthetic is True
    assert service.diagnose_command is None


def test_submit_evidence_diagnoses_immediately_when_readiness_is_reached():
    service = _CaseService()
    service.evidence_result = AppendEvidenceResult(
        outcome=WriteOutcome.CREATED,
        case_view=_case_view(ready=True),
    )
    orchestrator = FeishuOrchestrator(service, _Chats(CASE_ID), _Approvals())

    result = orchestrator.submit_evidence(_evidence())

    assert result.outcome is FeishuFlowOutcome.DIAGNOSIS
    assert result.diagnosis == service.diagnosis_result.value
    assert service.diagnose_command.case_id == CASE_ID
    assert service.diagnose_command.request_id == REQUEST_ID
    assert service.diagnose_command.trace_id == TRACE_ID


def test_submit_evidence_requires_a_case_bound_to_the_chat():
    service = _CaseService()
    orchestrator = FeishuOrchestrator(service, _Chats(), _Approvals())

    with pytest.raises(FeishuCaseNotBound):
        orchestrator.submit_evidence(_evidence())
    assert service.evidence_command is None


def test_confirm_review_checks_current_diagnosis_and_delegates_safe_audit():
    diagnosis = _human_diagnosis()
    service = _CaseService()
    service.get_result = _case_view(ready=True, diagnosis=diagnosis)
    approvals = _Approvals()
    orchestrator = FeishuOrchestrator(service, _Chats(CASE_ID), approvals)
    confirmation = FeishuConfirmation(
        action_id="action-confirm-001",
        approval_id="approval-001",
        case_id=CASE_ID,
        diagnosis_id=DIAGNOSIS_ID,
        actor_hash=ACTOR_HASH,
        occurred_at=NOW,
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
    )

    receipt = orchestrator.confirm_review(confirmation)

    assert receipt.approval_id == "approval-001"
    assert receipt.replayed is False
    record = approvals.records[0]
    assert record.case_id == CASE_ID
    assert record.diagnosis_id == DIAGNOSIS_ID
    assert record.actor_hash == ACTOR_HASH
    assert record.request_id == REQUEST_ID
    assert record.trace_id == TRACE_ID
    assert record.result == "CONFIRMED"
    assert record.synthetic is True


def test_confirmation_rejects_raw_actor_identifier():
    with pytest.raises(ValidationError):
        FeishuConfirmation(
            action_id="action-confirm-001",
            approval_id="approval-001",
            case_id=CASE_ID,
            diagnosis_id=DIAGNOSIS_ID,
            actor_id="ou_synthetic_operator",
            occurred_at=NOW,
            request_id=REQUEST_ID,
            trace_id=TRACE_ID,
        )


@pytest.mark.parametrize(
    ("case_status", "case_synthetic", "diagnosis_synthetic"),
    (
        (CaseStatus.DIAGNOSED, True, True),
        (CaseStatus.HUMAN_REVIEW, False, True),
        (CaseStatus.HUMAN_REVIEW, True, False),
    ),
)
def test_confirm_review_requires_a_synthetic_human_review_case(
    case_status,
    case_synthetic,
    diagnosis_synthetic,
):
    diagnosis = _human_diagnosis().model_copy(update={"synthetic": diagnosis_synthetic})
    view = _case_view(ready=True, diagnosis=diagnosis)
    view = view.model_copy(
        update={
            "case": view.case.model_copy(
                update={"status": case_status, "synthetic": case_synthetic}
            )
        }
    )
    service = _CaseService()
    service.get_result = view
    approvals = _Approvals()
    orchestrator = FeishuOrchestrator(service, _Chats(CASE_ID), approvals)

    with pytest.raises(InvalidReviewConfirmation):
        orchestrator.confirm_review(
            FeishuConfirmation(
                action_id="action-confirm-001",
                approval_id="approval-001",
                case_id=CASE_ID,
                diagnosis_id=DIAGNOSIS_ID,
                actor_hash=ACTOR_HASH,
                occurred_at=NOW,
                request_id=REQUEST_ID,
                trace_id=TRACE_ID,
            )
        )
    assert approvals.records == []


@pytest.mark.parametrize("diagnosis_id", (OTHER_DIAGNOSIS_ID, DIAGNOSIS_ID))
def test_confirm_review_rejects_stale_or_non_reviewable_diagnosis(diagnosis_id):
    service = _CaseService()
    diagnosis = _human_diagnosis()
    if diagnosis_id == DIAGNOSIS_ID:
        diagnosis = diagnosis.model_copy(
            update={"requires_human": False, "review_reasons": frozenset()}
        )
    service.get_result = _case_view(ready=True, diagnosis=diagnosis)
    approvals = _Approvals()
    orchestrator = FeishuOrchestrator(service, _Chats(CASE_ID), approvals)
    confirmation = FeishuConfirmation(
        action_id="action-confirm-001",
        approval_id="approval-001",
        case_id=CASE_ID,
        diagnosis_id=diagnosis_id,
        actor_hash=ACTOR_HASH,
        occurred_at=NOW,
        request_id=REQUEST_ID,
        trace_id=TRACE_ID,
    )

    with pytest.raises(InvalidReviewConfirmation):
        orchestrator.confirm_review(confirmation)
    assert approvals.records == []
