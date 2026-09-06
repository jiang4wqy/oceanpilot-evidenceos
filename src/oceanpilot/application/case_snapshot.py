"""Shared, deterministic projections of stored chargeback cases.

This reader depends on the case store and clock only. It has no model provider,
never advances a command, and never increments decision metrics. HTTP case
views and the operations console therefore use the same phase and evidence
projection. This is a read foundation, not a frozen export or approval bundle.
"""

from dataclasses import dataclass
from datetime import datetime

from oceanpilot.application.channels import (
    AgentActivity,
    Delivery,
    DeliveryAssessment,
    DeliveryDeadline,
    DeliveryEvidenceItem,
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
from oceanpilot.application.errors import CaseNotFound
from oceanpilot.domain.evidence_catalog import label_of
from oceanpilot.domain.reason_catalog import confirm_prompt, reason_label


def _agent_trace(state: ChargebackCaseState, step: SupervisorStep) -> tuple[AgentActivity, ...]:
    """Who-proposed-what for this step — makes the agent cluster visible."""
    trace: list[AgentActivity] = []
    if state.reason_code is not None:
        status = "已确认" if state.reason_confirmed else "待确认"
        trace.append(
            AgentActivity(
                agent="IntakeAgent",
                action=f"判定争议原因：{reason_label(state.reason_code)}（{status}）",
            )
        )
    if step.phase is SupervisorPhase.REASON_PROPOSED:
        trace.append(AgentActivity(agent="HumanGate", action="等待人工确认/更正争议原因"))
    elif step.phase is SupervisorPhase.NEED_EVIDENCE and step.evidence_request is not None:
        request = step.evidence_request
        if request.next_evidence is not None:
            trace.append(
                AgentActivity(
                    agent="EvidenceAgent",
                    action=f"请求证据：{label_of(request.next_evidence)}",
                    source=request.question_source.value,
                )
            )
    elif step.phase is SupervisorPhase.ASSESSED and step.assessment is not None:
        outcome = step.assessment
        trace.append(
            AgentActivity(
                agent="AssessAgent",
                action=f"材料就绪度 {outcome.assessment.win_likelihood}（数字由内核判定）",
                source=outcome.explanation_source.value,
            )
        )
        if outcome.assessment.requires_human:
            trace.append(AgentActivity(agent="HumanGate", action="建议人工复核"))
    return tuple(trace)


def render_delivery(
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
        revision=state.revision,
        card_network=state.card_network.value if state.card_network else None,
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
        agent_trace=_agent_trace(state, step),
    )


@dataclass(frozen=True)
class CaseSnapshot:
    """An immutable case view derived from one loaded case revision."""

    delivery: Delivery
    created_at: datetime | None


class CaseSnapshotReader:
    def __init__(
        self,
        store: ChargebackCaseStore,
        *,
        deadline: DeadlineTracker | None = None,
    ) -> None:
        self._store = store
        self._deadline_tracker = deadline

    def read(self, case_id: str) -> CaseSnapshot:
        state = self._store.load(case_id)
        if state is None:
            raise CaseNotFound()
        return self._snapshot(case_id, state)

    def list_cases(self) -> tuple[CaseSnapshot, ...]:
        snapshots = []
        for case_id in self._store.list_case_ids():
            state = self._store.load(case_id)
            if state is not None:
                snapshots.append(self._snapshot(case_id, state))
        return tuple(snapshots)

    def _snapshot(self, case_id: str, state: ChargebackCaseState) -> CaseSnapshot:
        return CaseSnapshot(
            delivery=self.render(case_id, state, ChargebackSupervisor.snapshot(state)),
            created_at=state.created_at,
        )

    def render(
        self,
        case_id: str,
        state: ChargebackCaseState,
        step: SupervisorStep,
        facts: CaseFacts | None = None,
    ) -> Delivery:
        """Use one renderer for stored snapshots and explicit command results."""
        deadline = None
        if self._deadline_tracker is not None and state.created_at is not None:
            outcome = self._deadline_tracker.evaluate(created_at=state.created_at)
            deadline = DeliveryDeadline(
                phase=outcome.phase.value,
                days_remaining=outcome.days_remaining,
                deadline_at=outcome.deadline_at.isoformat() if outcome.deadline_at else None,
                overdue=outcome.overdue,
            )
        return render_delivery(case_id, state, step, deadline, facts)
