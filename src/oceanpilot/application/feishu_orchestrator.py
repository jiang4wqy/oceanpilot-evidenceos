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
    FeishuChatCasePort,
)
from oceanpilot.domain.enums import (
    CaseStatus,
    CaseType,
    DiagnosisStatus,
    SourceReliability,
    SourceType,
)
from oceanpilot.domain.models import CaseView, EvidenceCreate, EvidenceOrigin

FEISHU_EVIDENCE_ORIGIN = EvidenceOrigin(
    source_type=SourceType.MERCHANT,
    source_reliability=SourceReliability.USER_REPORTED,
    synthetic=True,
)


class FeishuCaseNotBound(RuntimeError):
    pass


class InvalidReviewConfirmation(RuntimeError):
    pass


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
        if not view.case.readiness.ready:
            return FeishuFlowResult(
                outcome=FeishuFlowOutcome.NEED_INFO,
                case_view=view,
            )
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

    def start_incident(self, incident: FeishuIncident) -> FeishuFlowResult:
        case_id = self._chat_cases.get_case_id(incident.binding_key)
        if case_id is None:
            view = self._case_service.create_case(
                CreateCaseCommand(
                    case_type=CaseType.PAYMENT_INCIDENT,
                    summary=incident.summary,
                    merchant_ref=incident.merchant_ref,
                    synthetic=True,
                    request_id=incident.request_id,
                    trace_id=incident.trace_id,
                )
            )
            self._chat_cases.bind_case(
                incident.binding_key,
                view.case.case_id,
                updated_at=view.case.updated_at,
            )
        else:
            view = self._case_service.get_case(case_id)
        return self._advance(
            view,
            request_id=incident.request_id,
            trace_id=incident.trace_id,
        )

    def submit_evidence(
        self,
        submission: FeishuEvidenceSubmission,
    ) -> FeishuFlowResult:
        case_id = self._chat_cases.get_case_id(submission.binding_key)
        if case_id is None:
            raise FeishuCaseNotBound()
        appended = self._case_service.add_evidence(
            AddEvidenceCommand(
                case_id=case_id,
                evidence=EvidenceCreate(
                    evidence_id=submission.evidence_id,
                    evidence_code=submission.evidence_code,
                    availability=submission.availability,
                    typed_value=submission.typed_value,
                    observed_at=submission.observed_at,
                    source_ref=f"feishu:event:{submission.event_id}",
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
            or diagnosis.diagnosis_id != confirmation.diagnosis_id
            or diagnosis.status is not DiagnosisStatus.CURRENT
            or not diagnosis.requires_human
        ):
            raise InvalidReviewConfirmation()
        return self._approvals.record_confirmation(
            FeishuApprovalRecord(
                action_id=confirmation.action_id,
                approval_id=confirmation.approval_id,
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
