from datetime import datetime
from hashlib import sha256
from uuid import UUID

from oceanpilot.application.case_service import CaseService
from oceanpilot.application.commands import (
    AddEvidenceCommand,
    CreateCaseCommand,
    DiagnoseCaseCommand,
)
from oceanpilot.application.feishu_models import (
    FeishuApprovalRecord,
    FeishuConfirmation,
    FeishuConfirmationReceipt,
    FeishuEvidenceSubmission,
    FeishuFlowOutcome,
    FeishuFlowResult,
    FeishuIncident,
)
from oceanpilot.application.feishu_ports import (
    FeishuApprovalPort,
    FeishuBindingOutcome,
    FeishuChatCasePort,
)
from oceanpilot.domain.enums import (
    CaseStatus,
    CaseType,
    DiagnosisStatus,
    EvidenceAvailability,
    EvidenceCode,
    SourceReliability,
    SourceType,
)
from oceanpilot.domain.evidence_policy import build_active_evidence_view
from oceanpilot.domain.models import (
    AwareDateTime,
    CaseView,
    DiagnosisView,
    EvidenceCreate,
    EvidenceOrigin,
)

FEISHU_EVIDENCE_ORIGIN = EvidenceOrigin(
    source_type=SourceType.MERCHANT,
    source_reliability=SourceReliability.USER_REPORTED,
    synthetic=True,
)


class FeishuEvidenceStale(RuntimeError):
    def __init__(self, case_view: CaseView) -> None:
        super().__init__()
        self.case_view = case_view


class FeishuBindingInProgress(RuntimeError):
    pass


class FeishuUnexpectedEvidence(RuntimeError):
    pass


class InvalidReviewConfirmation(RuntimeError):
    pass


_DIAGNOSTIC_QUESTIONS = {
    "symptom.signal": EvidenceCode.SYMPTOM_STATUS,
}
_FEISHU_EVIDENCE_VALUES = {
    EvidenceCode.TRANSACTION_REFERENCE: ("txn_threeds_001",),
    EvidenceCode.TRANSACTION_OCCURRED_AT: ("2026-08-05T04:00:00Z",),
    EvidenceCode.CONTEXT_ENVIRONMENT: ("PROD",),
    EvidenceCode.SYMPTOM_STATUS: ("PENDING", "DECLINED"),
    EvidenceCode.AUTHENTICATION_STATUS: ("REQUIRED",),
    EvidenceCode.CALLBACK_DELIVERY_STATUS: ("NOT_RECEIVED",),
    EvidenceCode.RISK_DECISION_CODE: ("RISK_DECLINE",),
    EvidenceCode.INTEGRATION_TYPE: ("API",),
}


def feishu_evidence_values(evidence_code: EvidenceCode) -> tuple[str, ...]:
    try:
        return _FEISHU_EVIDENCE_VALUES[evidence_code]
    except KeyError:
        raise ValueError("unsupported Feishu evidence code") from None


def _approved_evidence_value(submission: FeishuEvidenceSubmission) -> bool:
    if submission.availability is not EvidenceAvailability.AVAILABLE:
        return False
    approved = feishu_evidence_values(submission.evidence_code)
    if submission.evidence_code is EvidenceCode.TRANSACTION_OCCURRED_AT:
        expected = datetime.fromisoformat(approved[0].replace("Z", "+00:00"))
        return submission.typed_value == expected
    return type(submission.typed_value) is str and submission.typed_value in approved


def _answered(view: CaseView, code: EvidenceCode) -> bool:
    slot = build_active_evidence_view(view.evidence).slots[code]
    return slot.selected_evidence is not None or slot.known_unknown or slot.conflicting


def next_feishu_evidence_code(view: CaseView) -> EvidenceCode | None:
    if type(view) is not CaseView:
        raise TypeError("view must be a CaseView")
    readiness_question = view.case.readiness.next_question
    diagnostic_turn = view.case.readiness.ready or readiness_question == "integration.type"
    if diagnostic_turn:
        active = build_active_evidence_view(view.evidence)
        status = active.slots[EvidenceCode.SYMPTOM_STATUS].selected_evidence
        if status is not None and status.typed_value in {"PENDING", "FAILED"}:
            for code in (
                EvidenceCode.AUTHENTICATION_STATUS,
                EvidenceCode.CALLBACK_DELIVERY_STATUS,
            ):
                if not _answered(view, code):
                    return code
        if (
            status is not None
            and status.typed_value == "DECLINED"
            and not _answered(view, EvidenceCode.RISK_DECISION_CODE)
        ):
            return EvidenceCode.RISK_DECISION_CODE
    if readiness_question is None:
        return None
    selected = _DIAGNOSTIC_QUESTIONS.get(readiness_question)
    return selected if selected is not None else EvidenceCode(readiness_question)


def feishu_evidence_id(
    case_id: str,
    case_revision: int,
    evidence_code: EvidenceCode,
) -> str:
    digest = bytearray(
        sha256(
            f"FEISHU_EVIDENCE\0{case_id}\0{case_revision}\0{evidence_code.value}".encode()
        ).digest()[:16]
    )
    digest[6] = (digest[6] & 0x0F) | 0x40
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(UUID(bytes=bytes(digest)))


def feishu_approval_id(
    case_id: str,
    diagnosis_id: str,
    actor_hash: str,
) -> str:
    digest = sha256(
        f"FEISHU_APPROVAL\0{case_id}\0{diagnosis_id}\0{actor_hash}".encode()
    ).hexdigest()
    return f"opa_{digest[:60]}"


def _replayed_diagnosis(view: CaseView, evidence_id: str) -> DiagnosisView | None:
    diagnosis = view.current_diagnosis
    if (
        diagnosis is None
        or diagnosis.status is not DiagnosisStatus.CURRENT
        or view.case.current_diagnosis_id != diagnosis.diagnosis_id
        or diagnosis.evidence_revision != view.case.evidence_revision
        or not any(item.evidence_id == evidence_id for item in view.evidence)
    ):
        return None
    return DiagnosisView(
        case_id=view.case.case_id,
        case_status=view.case.status,
        case_revision=view.case.case_revision,
        evidence_revision=view.case.evidence_revision,
        diagnosis=diagnosis,
    )


class FeishuOrchestrator:
    def __init__(
        self,
        case_service: CaseService,
        chat_cases: FeishuChatCasePort,
        approvals: FeishuApprovalPort,
    ) -> None:
        self._case_service = case_service
        self._chat_cases = chat_cases
        self._approvals = approvals

    def _advance(
        self,
        view: CaseView,
        *,
        request_id: str,
        trace_id: str,
    ) -> FeishuFlowResult:
        if next_feishu_evidence_code(view) is not None:
            return FeishuFlowResult(
                outcome=FeishuFlowOutcome.NEED_INFO,
                case_view=view,
            )
        if not view.case.readiness.ready:
            raise FeishuUnexpectedEvidence()
        diagnosed = self._case_service.diagnose(
            DiagnoseCaseCommand(
                case_id=view.case.case_id,
                request_id=request_id,
                trace_id=trace_id,
            )
        )
        return FeishuFlowResult(
            outcome=FeishuFlowOutcome.DIAGNOSIS,
            diagnosis=diagnosed.value,
        )

    def start_incident(
        self,
        incident: FeishuIncident,
        *,
        claim_token: str,
        claimed_at: AwareDateTime,
        lease_expires_at: AwareDateTime,
    ) -> FeishuFlowResult:
        binding = self._chat_cases.claim_case_binding(
            incident.binding_key,
            incident.event_id,
            self._case_service.new_case_id(),
            claim_token=claim_token,
            now=claimed_at,
            lease_expires_at=lease_expires_at,
        )
        if binding.outcome is FeishuBindingOutcome.IN_PROGRESS:
            raise FeishuBindingInProgress()
        if binding.outcome is FeishuBindingOutcome.CLAIMED:
            view = self._case_service.find_case(binding.case_id)
            if view is None:
                view = self._case_service.create_case(
                    CreateCaseCommand(
                        case_id=binding.case_id,
                        case_type=CaseType.PAYMENT_INCIDENT,
                        summary=incident.summary,
                        merchant_ref=incident.merchant_ref,
                        synthetic=True,
                        request_id=incident.request_id,
                        trace_id=incident.trace_id,
                    )
                )
            self._chat_cases.complete_case_binding(
                incident.binding_key,
                incident.event_id,
                view.case.case_id,
                claim_token=claim_token,
                updated_at=view.case.updated_at,
            )
        else:
            view = self._case_service.get_case(binding.case_id)
        return self._advance(
            view,
            request_id=incident.request_id,
            trace_id=incident.trace_id,
        )

    def submit_evidence(
        self,
        submission: FeishuEvidenceSubmission,
    ) -> FeishuFlowResult:
        view = self._case_service.get_case(submission.case_id)
        if not view.case.synthetic or not _approved_evidence_value(submission):
            raise FeishuUnexpectedEvidence()
        evidence_id = feishu_evidence_id(
            view.case.case_id,
            submission.expected_case_revision,
            submission.evidence_code,
        )
        replayed = _replayed_diagnosis(view, evidence_id)
        if replayed is not None:
            return FeishuFlowResult(
                outcome=FeishuFlowOutcome.DIAGNOSIS,
                diagnosis=replayed,
            )
        if view.current_diagnosis is not None or view.case.status in (
            CaseStatus.DIAGNOSED,
            CaseStatus.HUMAN_REVIEW,
        ):
            raise FeishuUnexpectedEvidence()
        if view.case.case_revision != submission.expected_case_revision:
            raise FeishuEvidenceStale(view)
        expected_code = next_feishu_evidence_code(view)
        if expected_code is None or expected_code is not submission.evidence_code:
            raise FeishuUnexpectedEvidence()
        appended = self._case_service.add_evidence(
            AddEvidenceCommand(
                case_id=view.case.case_id,
                evidence=EvidenceCreate(
                    evidence_id=evidence_id,
                    evidence_code=expected_code,
                    availability=submission.availability,
                    typed_value=submission.typed_value,
                    observed_at=None,
                    source_ref=(
                        f"feishu:case:{view.case.case_id}:"
                        f"revision:{view.case.case_revision}:{expected_code.value}"
                    ),
                ),
                origin=FEISHU_EVIDENCE_ORIGIN,
                request_id=submission.request_id,
                trace_id=submission.trace_id,
            )
        )
        return self._advance(
            appended.case_view,
            request_id=submission.request_id,
            trace_id=submission.trace_id,
        )

    def confirm_review(
        self,
        confirmation: FeishuConfirmation,
    ) -> FeishuConfirmationReceipt:
        view = self._case_service.get_case(confirmation.case_id)
        diagnosis = view.current_diagnosis
        if (
            diagnosis is None
            or view.case.status is not CaseStatus.HUMAN_REVIEW
            or not view.case.synthetic
            or not diagnosis.synthetic
            or diagnosis.case_id != view.case.case_id
            or view.case.current_diagnosis_id != diagnosis.diagnosis_id
            or diagnosis.evidence_revision != view.case.evidence_revision
            or diagnosis.diagnosis_id != confirmation.diagnosis_id
            or diagnosis.status is not DiagnosisStatus.CURRENT
            or not diagnosis.requires_human
        ):
            raise InvalidReviewConfirmation()
        return self._approvals.record_confirmation(
            FeishuApprovalRecord(
                action_id=confirmation.action_id,
                claim_token=confirmation.claim_token,
                approval_id=feishu_approval_id(
                    confirmation.case_id,
                    confirmation.diagnosis_id,
                    confirmation.actor_hash,
                ),
                case_id=confirmation.case_id,
                diagnosis_id=confirmation.diagnosis_id,
                actor_hash=confirmation.actor_hash,
                request_id=confirmation.request_id,
                trace_id=confirmation.trace_id,
                occurred_at=confirmation.occurred_at,
                result="CONFIRMED",
                synthetic=True,
            )
        )
