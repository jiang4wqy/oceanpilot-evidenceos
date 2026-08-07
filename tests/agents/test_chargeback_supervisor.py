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
from oceanpilot.domain.chargeback import DisputeReasonCode, required_evidence_for


def _supervisor(model):
    return ChargebackSupervisor(
        intake=IntakeAgent(model),
        evidence=EvidenceAgent(model),
        assess=ChargebackAssessAgent(model),
    )


def test_advance_needs_intake_before_a_reason_is_set():
    supervisor = _supervisor(ScriptedModelProvider(default_text="x"))
    step = supervisor.advance(ChargebackCaseState())
    assert step.phase is SupervisorPhase.NEEDS_INTAKE


def test_synthetic_chargeback_closed_loop_offline():
    # intake classifies from the model label; every later call uses default text.
    model = ScriptedModelProvider(["PRODUCT_NOT_RECEIVED"], default_text="（合成提示）")
    supervisor = _supervisor(model)
    state = ChargebackCaseState()

    intake = supervisor.intake(state, "下单后一直没收到货")
    assert state.reason_code is DisputeReasonCode.PRODUCT_NOT_RECEIVED
    assert intake.reason_code is DisputeReasonCode.PRODUCT_NOT_RECEIVED

    steps = 0
    step = supervisor.advance(state)
    while step.phase is SupervisorPhase.NEED_EVIDENCE:
        assert step.evidence_request is not None
        supervisor.submit_evidence(state, step.evidence_request.next_evidence)
        steps += 1
        assert steps <= 20  # must terminate
        step = supervisor.advance(state)

    assert step.phase is SupervisorPhase.ASSESSED
    assert step.assessment is not None
    assert step.assessment.assessment.ready_to_submit is True
    assert set(state.collected) == set(
        required_evidence_for(DisputeReasonCode.PRODUCT_NOT_RECEIVED)
    )
    assert step.assessment.assessment.win_likelihood == 1


def test_loop_collects_exactly_the_required_evidence_count():
    model = ScriptedModelProvider(["DUPLICATE_PROCESSING"], default_text="q")
    supervisor = _supervisor(model)
    state = ChargebackCaseState()
    supervisor.intake(state, "被重复扣款了")

    required = required_evidence_for(DisputeReasonCode.DUPLICATE_PROCESSING)
    step = supervisor.advance(state)
    seen = 0
    while step.phase is SupervisorPhase.NEED_EVIDENCE:
        supervisor.submit_evidence(state, step.evidence_request.next_evidence)
        seen += 1
        step = supervisor.advance(state)
    assert seen == len(required)
