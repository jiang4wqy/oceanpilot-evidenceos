from collections.abc import Callable
from datetime import datetime

from oceanpilot.application.commands import (
    AddEvidenceCommand,
    CreateCaseCommand,
    DiagnoseCaseCommand,
)
from oceanpilot.application.feishu_models import (
    CaseBindingMismatch,
    ConfirmationRequest,
    EvidenceAnswer,
    FeishuOutcomeKind,
    MessageEvent,
    OrchestrationOutcome,
    UnboundChat,
)
from oceanpilot.application.feishu_ports import CaseCommandPort, FeishuBindingPort
from oceanpilot.domain.enums import (
    CaseStatus,
    CaseType,
    DiagnosisStatus,
    SourceReliability,
    SourceType,
)
from oceanpilot.domain.models import (
    CaseView,
    DiagnosisView,
    EvidenceCreate,
    EvidenceOrigin,
)

_SUMMARY_FALLBACK = "飞书上报的支付异常（合成）"
_MERCHANT_REF = "synthetic-merchant"
_SUMMARY_MAX = 500

_FEISHU_ORIGIN = EvidenceOrigin(
    source_type=SourceType.MERCHANT,
    source_reliability=SourceReliability.USER_REPORTED,
    synthetic=True,
)


class FeishuOrchestrator:
    def __init__(
        self,
        cases: CaseCommandPort,
        *,
        clock: Callable[[], datetime],
        uuid_factory: Callable[[], str],
    ) -> None:
        self._cases = cases
        self._clock = clock
        self._uuid = uuid_factory

    def _timestamp(self) -> str:
        return self._clock().isoformat()

    @staticmethod
    def _diagnosis_view(case_view: CaseView) -> DiagnosisView:
        assert case_view.current_diagnosis is not None
        return DiagnosisView(
            case_id=case_view.case.case_id,
            case_status=case_view.case.status,
            case_revision=case_view.case.case_revision,
            evidence_revision=case_view.case.evidence_revision,
            diagnosis=case_view.current_diagnosis,
        )

    def _reflect(self, case_view: CaseView) -> OrchestrationOutcome:
        diagnosis = case_view.current_diagnosis
        if diagnosis is not None and diagnosis.status is DiagnosisStatus.CURRENT:
            return OrchestrationOutcome(
                kind=FeishuOutcomeKind.ALREADY_DIAGNOSED,
                diagnosis_view=self._diagnosis_view(case_view),
            )
        return OrchestrationOutcome(kind=FeishuOutcomeKind.NEED_INFO, case_view=case_view)

    def _require_bound_case(
        self,
        binding: FeishuBindingPort,
        *,
        chat_id: str,
        expected_case_id: str,
    ) -> str:
        case_id = binding.get_chat_case(chat_id)
        if case_id is None:
            raise UnboundChat()
        if case_id != expected_case_id:
            raise CaseBindingMismatch()
        return case_id

    def _resolve_case(
        self,
        binding: FeishuBindingPort,
        *,
        chat_id: str,
        summary: str,
    ) -> CaseView:
        case_id = binding.get_chat_case(chat_id)
        if case_id is not None:
            return self._cases.get_case(case_id)
        command = CreateCaseCommand(
            case_type=CaseType.PAYMENT_INCIDENT,
            summary=summary,
            merchant_ref=_MERCHANT_REF,
            synthetic=True,
            request_id=self._uuid(),
            trace_id=self._uuid(),
        )
        case_view = self._cases.create_case(command)
        binding.bind_chat_case(
            chat_id,
            case_view.case.case_id,
            updated_at=self._timestamp(),
        )
        return case_view

    def handle_message(
        self,
        binding: FeishuBindingPort,
        event: MessageEvent,
    ) -> OrchestrationOutcome:
        if event.from_bot:
            return OrchestrationOutcome(kind=FeishuOutcomeKind.IGNORED)
        summary = event.text.strip()[:_SUMMARY_MAX] or _SUMMARY_FALLBACK
        case_view = self._resolve_case(binding, chat_id=event.chat_id, summary=summary)
        return self._reflect(case_view)

    def handle_evidence(
        self,
        binding: FeishuBindingPort,
        answer: EvidenceAnswer,
    ) -> OrchestrationOutcome:
        case_id = self._require_bound_case(
            binding, chat_id=answer.chat_id, expected_case_id=answer.case_id
        )
        evidence = EvidenceCreate(
            evidence_id=answer.evidence_id,
            evidence_code=answer.evidence_code,
            availability=answer.availability,
            typed_value=answer.typed_value,
            observed_at=answer.observed_at,
            source_ref=answer.source_ref,
        )
        self._cases.add_evidence(
            AddEvidenceCommand(
                case_id=case_id,
                evidence=evidence,
                origin=_FEISHU_ORIGIN,
                request_id=self._uuid(),
                trace_id=self._uuid(),
            )
        )
        case_view = self._cases.get_case(case_id)
        if case_view.case.status is CaseStatus.EVIDENCE_READY:
            result = self._cases.diagnose(
                DiagnoseCaseCommand(
                    case_id=case_id,
                    request_id=self._uuid(),
                    trace_id=self._uuid(),
                )
            )
            return OrchestrationOutcome(
                kind=FeishuOutcomeKind.DIAGNOSED, diagnosis_view=result.value
            )
        return self._reflect(case_view)

    def evaluate_confirmation(
        self,
        binding: FeishuBindingPort,
        confirmation: ConfirmationRequest,
    ) -> OrchestrationOutcome:
        case_id = self._require_bound_case(
            binding, chat_id=confirmation.chat_id, expected_case_id=confirmation.case_id
        )
        case_view = self._cases.get_case(case_id)
        diagnosis = case_view.current_diagnosis
        if (
            diagnosis is None
            or diagnosis.status is not DiagnosisStatus.CURRENT
            or diagnosis.diagnosis_id != confirmation.diagnosis_id
            or not diagnosis.requires_human
            or case_view.case.current_diagnosis_id != diagnosis.diagnosis_id
        ):
            return OrchestrationOutcome(
                kind=FeishuOutcomeKind.DIAGNOSIS_NOT_CONFIRMABLE, case_view=case_view
            )
        return OrchestrationOutcome(
            kind=FeishuOutcomeKind.CONFIRMED,
            diagnosis_view=self._diagnosis_view(case_view),
        )
