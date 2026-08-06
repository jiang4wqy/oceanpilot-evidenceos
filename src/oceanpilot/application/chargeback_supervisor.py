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


class SupervisorPhase(StrEnum):
    NEEDS_INTAKE = "NEEDS_INTAKE"
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
        return outcome

    def submit_evidence(self, state: ChargebackCaseState, code: ChargebackEvidenceCode) -> None:
        state.collected.add(code)

    def advance(self, state: ChargebackCaseState) -> SupervisorStep:
        if state.reason_code is None:
            return SupervisorStep(phase=SupervisorPhase.NEEDS_INTAKE)
        request = self._evidence.next_request(state.reason_code, state.collected)
        if not request.complete:
            return SupervisorStep(phase=SupervisorPhase.NEED_EVIDENCE, evidence_request=request)
        outcome = self._assess.assess(state.reason_code, state.collected)
        return SupervisorStep(phase=SupervisorPhase.ASSESSED, assessment=outcome)
