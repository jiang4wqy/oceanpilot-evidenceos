"""Chargeback supervisor: sequences the agent cluster over a shared case state.

The supervisor is the A2A "bus": agents coordinate through one mutable
``ChargebackCaseState`` (reason code + collected evidence), not by talking to
each other. It drives phases intake -> need-evidence (loop) -> assessed, and
returns a step the channel/UI renders. Pure application layer — depends on the
agents (injected) and the domain, never on adapters.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from oceanpilot.application.chargeback_agents import (
    AssessOutcome,
    ChargebackAssessAgent,
    EvidenceAgent,
    EvidenceRequest,
    IntakeAgent,
    IntakeOutcome,
)
from oceanpilot.domain.chargeback import ChargebackEvidenceCode, DisputeReasonCode


@dataclass
class ChargebackCaseState:
    reason_code: DisputeReasonCode | None = None
    collected: set[ChargebackEvidenceCode] = field(default_factory=set)
    # The kernel/intake proposes a reason; a human confirms it before the case
    # proceeds. A confident classification is auto-confirmed; a low-confidence
    # one waits at REASON_PROPOSED for an explicit human confirm/correction.
    reason_confident: bool = False
    reason_confirmed: bool = False


class SupervisorPhase(StrEnum):
    NEEDS_INTAKE = "NEEDS_INTAKE"
    REASON_PROPOSED = "REASON_PROPOSED"
    NEED_EVIDENCE = "NEED_EVIDENCE"
    ASSESSED = "ASSESSED"


@dataclass(frozen=True)
class SupervisorStep:
    phase: SupervisorPhase
    evidence_request: EvidenceRequest | None = None
    assessment: AssessOutcome | None = None


class ChargebackSupervisor:
    def __init__(
        self,
        *,
        intake: IntakeAgent,
        evidence: EvidenceAgent,
        assess: ChargebackAssessAgent,
    ) -> None:
        self._intake = intake
        self._evidence = evidence
        self._assess = assess

    def intake(self, state: ChargebackCaseState, text: str) -> IntakeOutcome:
        outcome = self._intake.classify(text)
        state.reason_code = outcome.reason_code
        state.reason_confident = outcome.confident
        # A confident classification is auto-confirmed; an unconfident one must
        # be confirmed by a human before the flow proceeds.
        state.reason_confirmed = outcome.confident
        return outcome

    def confirm_reason(
        self,
        state: ChargebackCaseState,
        corrected: DisputeReasonCode | None = None,
    ) -> None:
        """Human confirms (or corrects) the proposed dispute reason."""
        if corrected is not None:
            state.reason_code = corrected
        state.reason_confirmed = True

    def submit_evidence(self, state: ChargebackCaseState, code: ChargebackEvidenceCode) -> None:
        state.collected.add(code)

    def advance(self, state: ChargebackCaseState) -> SupervisorStep:
        if state.reason_code is None:
            return SupervisorStep(phase=SupervisorPhase.NEEDS_INTAKE)
        if not state.reason_confirmed:
            # Kernel proposed a reason but a human has not confirmed it yet.
            return SupervisorStep(phase=SupervisorPhase.REASON_PROPOSED)
        request = self._evidence.next_request(state.reason_code, state.collected)
        if not request.complete:
            return SupervisorStep(phase=SupervisorPhase.NEED_EVIDENCE, evidence_request=request)
        outcome = self._assess.assess(state.reason_code, state.collected)
        return SupervisorStep(phase=SupervisorPhase.ASSESSED, assessment=outcome)
