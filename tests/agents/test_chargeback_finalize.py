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
from oceanpilot.domain.chargeback import required_evidence_for


def _supervisor(model):
    return ChargebackSupervisor(
        intake=IntakeAgent(model),
        evidence=EvidenceAgent(model),
        assess=ChargebackAssessAgent(model),
    )


def test_finalize_stops_the_loop_and_routes_to_human_review():
    model = ScriptedModelProvider(["PRODUCT_NOT_RECEIVED"], default_text="q")
    supervisor = _supervisor(model)
    state = ChargebackCaseState()
    supervisor.intake(state, "没收到货")  # confident -> auto-confirmed

    # Without finalization the case keeps asking for the missing critical items.
    assert supervisor.advance(state).phase is SupervisorPhase.NEED_EVIDENCE

    # The human declares they cannot provide more evidence.
    supervisor.finalize_evidence(state)
    step = supervisor.advance(state)
    assert step.phase is SupervisorPhase.ASSESSED
    assert step.assessment is not None
    assert step.assessment.assessment.ready_to_submit is False
    assert step.assessment.assessment.requires_human is True
    # The still-missing items are surfaced for the human reviewer.
    assert step.assessment.assessment.missing_critical


def test_finalize_still_lets_a_completed_case_be_ready():
    model = ScriptedModelProvider(["DUPLICATE_PROCESSING"], default_text="q")
    supervisor = _supervisor(model)
    state = ChargebackCaseState()
    supervisor.intake(state, "被重复扣款了")
    supervisor.finalize_evidence(state)

    # Even after finalizing, providing the full checklist yields a ready case.
    for code in required_evidence_for(state.reason_code):
        supervisor.submit_evidence(state, code)
    final = supervisor.advance(state)
    assert final.phase is SupervisorPhase.ASSESSED
    assert final.assessment.assessment.ready_to_submit is True
