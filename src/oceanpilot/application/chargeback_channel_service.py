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
    DeliveryDeadline,
    DeliveryEvidenceItem,
    InboundKind,
    NormalizedInbound,
)
from oceanpilot.application.chargeback_agents import CaseFacts
from oceanpilot.application.chargeback_deadline import DeadlineTracker
from oceanpilot.application.chargeback_ports import ChargebackCaseStore
from oceanpilot.application.chargeback_supervisor import (
    ChargebackCaseState,
    ChargebackSupervisor,
    SupervisorPhase,
    SupervisorStep,
)
from oceanpilot.application.errors import CaseNotFound, InvalidInbound
from oceanpilot.domain.chargeback import ChargebackEvidenceCode, DisputeReasonCode
from oceanpilot.domain.evidence_catalog import label_of
from oceanpilot.domain.reason_catalog import confirm_prompt


def _delivery(
    case_id: str,
    state: ChargebackCaseState,
    step: SupervisorStep,
    deadline: DeliveryDeadline | None = None,
    facts: CaseFacts | None = None,
) -> Delivery:
    next_evidence: str | None = None
    question: str | None = None
    missing: tuple[str, ...] | None = None
    assessment: DeliveryAssessment | None = None

    if step.phase is SupervisorPhase.REASON_PROPOSED and state.reason_code is not None:
        # Ask the human to confirm/correct the proposed reason before proceeding.
        question = confirm_prompt(state.reason_code, confident=state.reason_confident)
    elif step.phase is SupervisorPhase.NEED_EVIDENCE and step.evidence_request is not None:
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
            explanation_source=outcome.explanation_source.value,
            evidence_breakdown=tuple(
                DeliveryEvidenceItem(
                    code=item.code.value,
                    label=label_of(item.code),
                    weight=item.weight,
                    critical=item.critical,
                    present=item.present,
                )
                for item in result.evidence_breakdown
            ),
        )

    return Delivery(
        case_id=case_id,
        phase=step.phase.value,
        reason_code=state.reason_code.value if state.reason_code else None,
        reason_confirmed=state.reason_confirmed,
        collection_finalized=state.collection_finalized,
        collected=tuple(sorted(code.value for code in state.collected)),
        next_evidence=next_evidence,
        question=question,
        missing=missing,
        assessment=assessment,
        deadline=deadline,
        facts=facts if facts is not None and not facts.is_empty else None,
    )


class ChargebackChannelService:
    def __init__(
        self,
        supervisor: ChargebackSupervisor,
        store: ChargebackCaseStore,
        *,
        deadline: DeadlineTracker | None = None,
    ) -> None:
        self._supervisor = supervisor
        self._store = store
        self._deadline_tracker = deadline

    def _deadline(self, state: ChargebackCaseState) -> DeliveryDeadline | None:
        if self._deadline_tracker is None or state.created_at is None:
            return None
        outcome = self._deadline_tracker.evaluate(created_at=state.created_at)
        return DeliveryDeadline(
            phase=outcome.phase.value,
            days_remaining=outcome.days_remaining,
            deadline_at=outcome.deadline_at.isoformat() if outcome.deadline_at else None,
            overdue=outcome.overdue,
        )

    def _deliver(
        self,
        case_id: str,
        state: ChargebackCaseState,
        facts: CaseFacts | None = None,
    ) -> Delivery:
        step = self._supervisor.advance(state)
        return _delivery(case_id, state, step, self._deadline(state), facts)

    def handle(self, inbound: NormalizedInbound) -> Delivery:
        if inbound.kind is InboundKind.OPEN_CASE:
            return self._open_case(inbound)
        if inbound.kind is InboundKind.CONFIRM_REASON:
            return self._confirm_reason(inbound)
        if inbound.kind is InboundKind.SUBMIT_EVIDENCE:
            return self._submit_evidence(inbound)
        if inbound.kind is InboundKind.FINALIZE_EVIDENCE:
            return self._finalize_evidence(inbound)
        if inbound.kind is InboundKind.GET_CASE:
            return self._get_case(inbound)
        raise InvalidInbound()

    def _open_case(self, inbound: NormalizedInbound) -> Delivery:
        if not inbound.description:
            raise InvalidInbound()
        case_id = self._store.create()
        state = self._require_state(case_id)
        self._supervisor.intake(state, inbound.description)
        facts = self._supervisor.extract_facts(inbound.description)
        self._store.save(case_id, state)
        return self._deliver(case_id, state, facts)

    def _confirm_reason(self, inbound: NormalizedInbound) -> Delivery:
        if not inbound.case_id:
            raise InvalidInbound()
        corrected: DisputeReasonCode | None = None
        if inbound.reason_code is not None:
            try:
                corrected = DisputeReasonCode(inbound.reason_code)
            except ValueError:
                raise InvalidInbound() from None
        state = self._require_state(inbound.case_id)
        self._supervisor.confirm_reason(state, corrected)
        self._store.save(inbound.case_id, state)
        return self._deliver(inbound.case_id, state)

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
        return self._deliver(inbound.case_id, state)

    def _finalize_evidence(self, inbound: NormalizedInbound) -> Delivery:
        if not inbound.case_id:
            raise InvalidInbound()
        state = self._require_state(inbound.case_id)
        self._supervisor.finalize_evidence(state)
        self._store.save(inbound.case_id, state)
        return self._deliver(inbound.case_id, state)

    def _get_case(self, inbound: NormalizedInbound) -> Delivery:
        if not inbound.case_id:
            raise InvalidInbound()
        state = self._require_state(inbound.case_id)
        return self._deliver(inbound.case_id, state)

    def _require_state(self, case_id: str) -> ChargebackCaseState:
        state = self._store.load(case_id)
        if state is None:
            raise CaseNotFound()
        return state
