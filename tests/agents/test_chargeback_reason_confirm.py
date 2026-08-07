from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.chargeback_agents import (
    ChargebackAssessAgent,
    EvidenceAgent,
    IntakeAgent,
)
from oceanpilot.application.chargeback_supervisor import (
    ChargebackCaseState,
    ChargebackSupervisor,
    SupervisorPhase,
)
from oceanpilot.domain.chargeback import DisputeReasonCode

# A description that matches no intake heuristic keyword, so classification is
# unconfident and must wait for a human to confirm.
_UNCLEAR = "这是一段用于测试的中性内容"


def _supervisor(model):
    return ChargebackSupervisor(
        intake=IntakeAgent(model),
        evidence=EvidenceAgent(model),
        assess=ChargebackAssessAgent(model),
    )


def test_confident_intake_is_auto_confirmed_and_proceeds():
    model = ScriptedModelProvider(["PRODUCT_NOT_RECEIVED"], default_text="q")
    supervisor = _supervisor(model)
    state = ChargebackCaseState()

    outcome = supervisor.intake(state, "客户下单后一直没收到货")
    assert outcome.confident is True
    assert state.reason_confirmed is True
    assert supervisor.advance(state).phase is SupervisorPhase.NEED_EVIDENCE


def test_unconfident_intake_waits_at_reason_proposed():
    model = ScriptedModelProvider(default_text="无法识别")
    supervisor = _supervisor(model)
    state = ChargebackCaseState()

    outcome = supervisor.intake(state, _UNCLEAR)
    assert outcome.confident is False
    assert state.reason_confirmed is False
    assert supervisor.advance(state).phase is SupervisorPhase.REASON_PROPOSED

    supervisor.confirm_reason(state)
    assert state.reason_confirmed is True
    assert supervisor.advance(state).phase is SupervisorPhase.NEED_EVIDENCE


def test_human_can_correct_the_reason_at_confirmation():
    model = ScriptedModelProvider(default_text="无法识别")
    supervisor = _supervisor(model)
    state = ChargebackCaseState()

    supervisor.intake(state, _UNCLEAR)  # defaults to AUTHORIZATION_ERROR, unconfident
    assert state.reason_code is DisputeReasonCode.AUTHORIZATION_ERROR

    supervisor.confirm_reason(state, DisputeReasonCode.FRAUD_CARD_NOT_PRESENT)
    assert state.reason_code is DisputeReasonCode.FRAUD_CARD_NOT_PRESENT
    assert state.reason_confirmed is True
    assert supervisor.advance(state).phase is SupervisorPhase.NEED_EVIDENCE
