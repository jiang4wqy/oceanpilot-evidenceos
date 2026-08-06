"""Channel-agnostic core operation for the chargeback cluster (issue #10 T1).

Turns a ``NormalizedInbound`` (from any channel) into a ``Delivery`` by driving
the supervisor + case store — the single place the chargeback flow logic lives,
shared by the HTTP route and every channel adapter. Depends only on application
protocols (``ChargebackSupervisor``, ``ChargebackCaseStore``) and the domain, so
it stays free of any channel or transport detail.
"""

from oceanpilot.application.channels import (
    Delivery,
    DeliveryAssessment,
    InboundKind,
    NormalizedInbound,
)
from oceanpilot.application.chargeback_ports import ChargebackCaseStore
from oceanpilot.application.chargeback_supervisor import (
    ChargebackCaseState,
    ChargebackSupervisor,
    SupervisorPhase,
    SupervisorStep,
)
from oceanpilot.application.errors import CaseNotFound, InvalidInbound
from oceanpilot.domain.chargeback import ChargebackEvidenceCode


def _delivery(case_id: str, state: ChargebackCaseState, step: SupervisorStep) -> Delivery:
    next_evidence: str | None = None
    question: str | None = None
    missing: tuple[str, ...] | None = None
    assessment: DeliveryAssessment | None = None

    if step.phase is SupervisorPhase.NEED_EVIDENCE and step.evidence_request is not None:
        request = step.evidence_request
        next_evidence = request.next_evidence.value if request.next_evidence else None
        question = request.question
        missing = tuple(code.value for code in request.missing)
    elif step.phase is SupervisorPhase.ASSESSED and step.assessment is not None:
        outcome = step.assessment
        result = outcome.assessment
        assessment = DeliveryAssessment(
            win_likelihood=str(result.win_likelihood),
            completeness=str(result.completeness),
            responsible_team=result.responsible_team.value,
            requires_human=result.requires_human,
            review_reasons=tuple(reason.value for reason in result.review_reasons),
            explanation=outcome.explanation,
        )

    return Delivery(
        case_id=case_id,
        phase=step.phase.value,
        reason_code=state.reason_code.value if state.reason_code else None,
        collected=tuple(sorted(code.value for code in state.collected)),
        next_evidence=next_evidence,
        question=question,
        missing=missing,
        assessment=assessment,
    )


class ChargebackChannelService:
    def __init__(
        self,
        supervisor: ChargebackSupervisor,
        store: ChargebackCaseStore,
    ) -> None:
        self._supervisor = supervisor
        self._store = store

    def handle(self, inbound: NormalizedInbound) -> Delivery:
        if inbound.kind is InboundKind.OPEN_CASE:
            return self._open_case(inbound)
        if inbound.kind is InboundKind.SUBMIT_EVIDENCE:
            return self._submit_evidence(inbound)
        if inbound.kind is InboundKind.GET_CASE:
            return self._get_case(inbound)
        raise InvalidInbound()

    def _open_case(self, inbound: NormalizedInbound) -> Delivery:
        if not inbound.description:
            raise InvalidInbound()
        case_id = self._store.create()
        state = self._require_state(case_id)
        self._supervisor.intake(state, inbound.description)
        self._store.save(case_id, state)
        return _delivery(case_id, state, self._supervisor.advance(state))

    def _submit_evidence(self, inbound: NormalizedInbound) -> Delivery:
        if not inbound.case_id or not inbound.evidence_code:
            raise InvalidInbound()
        try:
            code = ChargebackEvidenceCode(inbound.evidence_code)
        except ValueError:
            raise InvalidInbound() from None
        state = self._require_state(inbound.case_id)
        self._supervisor.submit_evidence(state, code)
        self._store.save(inbound.case_id, state)
        return _delivery(inbound.case_id, state, self._supervisor.advance(state))

    def _get_case(self, inbound: NormalizedInbound) -> Delivery:
        if not inbound.case_id:
            raise InvalidInbound()
        state = self._require_state(inbound.case_id)
        return _delivery(inbound.case_id, state, self._supervisor.advance(state))

    def _require_state(self, case_id: str) -> ChargebackCaseState:
        state = self._store.load(case_id)
        if state is None:
            raise CaseNotFound()
        return state
