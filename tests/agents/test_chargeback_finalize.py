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
from oceanpilot.domain.chargeback import ChargebackEvidenceCode, MaterialGate, required_evidence_for


def _supervisor(model):
    return ChargebackSupervisor(
        intake=IntakeAgent(model),
        evidence=EvidenceAgent(model),
        assess=ChargebackAssessAgent(model),
    )


def test_finalize_cannot_bypass_critical_material_gap():
    model = ScriptedModelProvider(["PRODUCT_NOT_RECEIVED"], default_text="q")
    supervisor = _supervisor(model)
    state = ChargebackCaseState()
    supervisor.intake(state, "没收到货")  # confident -> auto-confirmed

    # Without finalization the case keeps asking for the missing critical items.
    assert supervisor.advance(state).phase is SupervisorPhase.NEED_EVIDENCE

    # The human declares they cannot provide more evidence.
    supervisor.finalize_evidence(state)
    step = supervisor.advance(state)
    assert step.phase is SupervisorPhase.NEED_EVIDENCE
    assert step.assessment is None
    assert step.evidence_request.missing
    assert all(request.task.kind != "chargeback_assess_explanation" for request in model.requests)


def test_finalize_allows_only_limited_analysis_when_only_ordinary_items_are_missing():
    model = ScriptedModelProvider(["PRODUCT_NOT_RECEIVED"], default_text="有限分析，待人工复核。")
    supervisor = _supervisor(model)
    state = ChargebackCaseState()
    supervisor.intake(state, "没收到货")
    for code in (
        ChargebackEvidenceCode.DELIVERY_TRACKING,
        ChargebackEvidenceCode.PROOF_OF_DELIVERY,
    ):
        supervisor.submit_evidence(state, code)
    assert supervisor.snapshot(state).phase is SupervisorPhase.NEED_EVIDENCE
    supervisor.finalize_evidence(state)
    step = supervisor.advance(state)
    assert step.phase is SupervisorPhase.ASSESSED
    assert step.assessment.assessment.material_gate is MaterialGate.LIMITED
    assert step.assessment.assessment.requires_human is True
    assert step.assessment.assessment.ready_to_submit is False
    assert any(request.task.kind == "chargeback_assess_explanation" for request in model.requests)


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
