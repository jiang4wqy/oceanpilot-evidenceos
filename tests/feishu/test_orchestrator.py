from datetime import UTC, datetime
from uuid import uuid4

import pytest

from oceanpilot.adapters.diagnosis.rules import RuleDiagnosisEngine
from oceanpilot.adapters.feishu.store import FeishuCallbackStoreFactory
from oceanpilot.adapters.persistence.sqlite import (
    SqliteCaseStoreFactory,
    initialize_schema,
)
from oceanpilot.application.case_service import CaseService
from oceanpilot.application.feishu_models import (
    CaseBindingMismatch,
    ConfirmationRequest,
    EvidenceAnswer,
    FeishuOutcomeKind,
    MessageEvent,
    UnboundChat,
)
from oceanpilot.application.feishu_orchestrator import FeishuOrchestrator
from oceanpilot.domain.enums import (
    CaseStatus,
    CaseType,
    EvidenceAvailability,
    EvidenceCode,
)

CHAT_ID = "oc_synthetic_chat_0001"
OCCURRED_AT = datetime(2026, 8, 5, 4, 0, tzinfo=UTC)
OTHER_CASE_ID = "00000000-0000-4000-8000-0000000000ff"

_THREEDS_FACTS = (
    (EvidenceCode.TRANSACTION_REFERENCE, "txn_threeds_001"),
    (EvidenceCode.TRANSACTION_OCCURRED_AT, OCCURRED_AT),
    (EvidenceCode.CONTEXT_ENVIRONMENT, "PROD"),
    (EvidenceCode.SYMPTOM_STATUS, "PENDING"),
    (EvidenceCode.INTEGRATION_TYPE, "API"),
    (EvidenceCode.AUTHENTICATION_STATUS, "REQUIRED"),
    (EvidenceCode.CALLBACK_DELIVERY_STATUS, "NOT_RECEIVED"),
)


def _answer(case_id, code, value):
    return EvidenceAnswer(
        chat_id=CHAT_ID,
        case_id=case_id,
        actor_id="ou_reporter",
        evidence_id=str(uuid4()),
        evidence_code=code,
        availability=EvidenceAvailability.AVAILABLE,
        source_ref=f"feishu:{code.value}",
        typed_value=value,
    )


def _submit_threeds(orchestrator, binding, case_id):
    outcome = None
    for code, value in _THREEDS_FACTS:
        outcome = orchestrator.handle_evidence(binding, _answer(case_id, code, value))
    return outcome


def _build_orchestrator(tmp_path):
    case_db = tmp_path / "cases.db"
    initialize_schema(case_db)
    case_service = CaseService(
        SqliteCaseStoreFactory(case_db),
        RuleDiagnosisEngine(),
        clock=lambda: OCCURRED_AT,
        uuid_factory=lambda: str(uuid4()),
    )
    feishu_factory = FeishuCallbackStoreFactory(tmp_path / "feishu.db")
    orchestrator = FeishuOrchestrator(
        case_service,
        clock=lambda: OCCURRED_AT,
        uuid_factory=lambda: str(uuid4()),
    )
    return orchestrator, case_service, feishu_factory


def test_message_without_binding_creates_and_binds_synthetic_case(tmp_path):
    orchestrator, case_service, feishu_factory = _build_orchestrator(tmp_path)

    with feishu_factory.session() as binding:
        outcome = orchestrator.handle_message(
            binding,
            MessageEvent(chat_id=CHAT_ID, text="跨境支付回调一直没有收到"),
        )
        bound_case_id = binding.get_chat_case(CHAT_ID)

    assert outcome.kind is FeishuOutcomeKind.NEED_INFO
    assert outcome.case_view is not None
    case = outcome.case_view.case
    assert case.case_type is CaseType.PAYMENT_INCIDENT
    assert case.synthetic is True
    assert case.status is CaseStatus.NEED_INFO
    assert case.summary == "跨境支付回调一直没有收到"
    assert bound_case_id == case.case_id
    assert case.readiness.next_question is not None


def test_message_with_existing_binding_reuses_case(tmp_path):
    orchestrator, _case_service, feishu_factory = _build_orchestrator(tmp_path)

    with feishu_factory.session() as binding:
        first = orchestrator.handle_message(
            binding, MessageEvent(chat_id=CHAT_ID, text="第一次描述")
        )
        second = orchestrator.handle_message(
            binding, MessageEvent(chat_id=CHAT_ID, text="第二次描述")
        )

    assert first.case_view.case.case_id == second.case_view.case.case_id
    assert second.case_view.case.summary == "第一次描述"


def test_bot_message_is_ignored_and_creates_no_case(tmp_path):
    orchestrator, _case_service, feishu_factory = _build_orchestrator(tmp_path)

    with feishu_factory.session() as binding:
        outcome = orchestrator.handle_message(
            binding, MessageEvent(chat_id=CHAT_ID, text="echo", from_bot=True)
        )
        assert binding.get_chat_case(CHAT_ID) is None

    assert outcome.kind is FeishuOutcomeKind.IGNORED
    assert outcome.case_view is None


def test_full_evidence_reaches_readiness_and_diagnoses(tmp_path):
    orchestrator, _case_service, feishu_factory = _build_orchestrator(tmp_path)

    with feishu_factory.session() as binding:
        created = orchestrator.handle_message(
            binding, MessageEvent(chat_id=CHAT_ID, text="3DS 回调缺失")
        )
        case_id = created.case_view.case.case_id
        outcome = _submit_threeds(orchestrator, binding, case_id)

    assert outcome.kind is FeishuOutcomeKind.DIAGNOSED
    view = outcome.diagnosis_view
    assert view is not None
    assert view.diagnosis.hypotheses
    # feishu evidence is USER_REPORTED (low source quality) -> human review
    assert view.diagnosis.requires_human is True
    assert view.case_status is CaseStatus.HUMAN_REVIEW


def test_partial_evidence_stays_need_info(tmp_path):
    orchestrator, _case_service, feishu_factory = _build_orchestrator(tmp_path)

    with feishu_factory.session() as binding:
        created = orchestrator.handle_message(
            binding, MessageEvent(chat_id=CHAT_ID, text="部分证据")
        )
        case_id = created.case_view.case.case_id
        outcome = orchestrator.handle_evidence(
            binding, _answer(case_id, EvidenceCode.TRANSACTION_REFERENCE, "txn_1")
        )

    assert outcome.kind is FeishuOutcomeKind.NEED_INFO
    assert outcome.case_view.case.status is CaseStatus.NEED_INFO


def test_evidence_for_unbound_chat_is_rejected(tmp_path):
    orchestrator, _case_service, feishu_factory = _build_orchestrator(tmp_path)

    with feishu_factory.session() as binding, pytest.raises(UnboundChat):
        orchestrator.handle_evidence(
            binding,
            EvidenceAnswer(
                chat_id="oc_unbound",
                case_id=OTHER_CASE_ID,
                actor_id="ou_reporter",
                evidence_id=str(uuid4()),
                evidence_code=EvidenceCode.CONTEXT_ENVIRONMENT,
                availability=EvidenceAvailability.AVAILABLE,
                source_ref="feishu:env",
                typed_value="PROD",
            ),
        )


def test_evidence_with_mismatched_case_is_rejected(tmp_path):
    orchestrator, _case_service, feishu_factory = _build_orchestrator(tmp_path)

    with feishu_factory.session() as binding:
        orchestrator.handle_message(binding, MessageEvent(chat_id=CHAT_ID, text="x"))
        with pytest.raises(CaseBindingMismatch):
            orchestrator.handle_evidence(
                binding,
                _answer(OTHER_CASE_ID, EvidenceCode.CONTEXT_ENVIRONMENT, "PROD"),
            )


def test_confirmation_of_current_requires_human_diagnosis(tmp_path):
    orchestrator, _case_service, feishu_factory = _build_orchestrator(tmp_path)

    with feishu_factory.session() as binding:
        created = orchestrator.handle_message(
            binding, MessageEvent(chat_id=CHAT_ID, text="3DS")
        )
        case_id = created.case_view.case.case_id
        diagnosed = _submit_threeds(orchestrator, binding, case_id)
        diagnosis_id = diagnosed.diagnosis_view.diagnosis.diagnosis_id
        outcome = orchestrator.evaluate_confirmation(
            binding,
            ConfirmationRequest(
                chat_id=CHAT_ID,
                case_id=case_id,
                diagnosis_id=diagnosis_id,
                actor_id="ou_reviewer",
            ),
        )

    assert outcome.kind is FeishuOutcomeKind.CONFIRMED
    assert outcome.diagnosis_view.diagnosis.diagnosis_id == diagnosis_id


def test_confirmation_with_stale_diagnosis_id_is_not_confirmable(tmp_path):
    orchestrator, _case_service, feishu_factory = _build_orchestrator(tmp_path)

    with feishu_factory.session() as binding:
        created = orchestrator.handle_message(
            binding, MessageEvent(chat_id=CHAT_ID, text="3DS")
        )
        case_id = created.case_view.case.case_id
        _submit_threeds(orchestrator, binding, case_id)
        outcome = orchestrator.evaluate_confirmation(
            binding,
            ConfirmationRequest(
                chat_id=CHAT_ID,
                case_id=case_id,
                diagnosis_id="00000000-0000-4000-8000-0000000000aa",
                actor_id="ou_reviewer",
            ),
        )

    assert outcome.kind is FeishuOutcomeKind.DIAGNOSIS_NOT_CONFIRMABLE
