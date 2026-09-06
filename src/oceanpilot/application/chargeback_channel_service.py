"""Channel-agnostic core operation for the chargeback cluster (issue #10 T1).

Turns a ``NormalizedInbound`` (from any channel) into a ``Delivery`` by driving
the supervisor + case store — the single place the chargeback flow logic lives,
shared by the HTTP route and every channel adapter. Depends only on application
protocols (``ChargebackSupervisor``, ``ChargebackCaseStore``) and the domain, so
it stays free of any channel or transport detail.
"""

from oceanpilot.application.case_snapshot import CaseSnapshotReader
from oceanpilot.application.channels import (
    Delivery,
    InboundKind,
    NormalizedInbound,
)
from oceanpilot.application.chargeback_agents import CaseFacts
from oceanpilot.application.chargeback_deadline import DeadlineTracker
from oceanpilot.application.chargeback_ports import ChargebackCaseStore
from oceanpilot.application.chargeback_supervisor import (
    ChargebackCaseState,
    ChargebackSupervisor,
)
from oceanpilot.application.errors import CaseNotFound, InvalidInbound
from oceanpilot.application.metrics import DecisionMetrics
from oceanpilot.domain.chargeback import CardNetwork, ChargebackEvidenceCode, DisputeReasonCode


class ChargebackChannelService:
    def __init__(
        self,
        supervisor: ChargebackSupervisor,
        store: ChargebackCaseStore,
        *,
        deadline: DeadlineTracker | None = None,
        metrics: DecisionMetrics | None = None,
    ) -> None:
        self._supervisor = supervisor
        self._store = store
        self._reader = CaseSnapshotReader(store, deadline=deadline)
        self._metrics = metrics

    def _deliver(
        self,
        case_id: str,
        state: ChargebackCaseState,
        facts: CaseFacts | None = None,
    ) -> Delivery:
        step = self._supervisor.advance(state)
        delivery = self._reader.render(case_id, state, step, facts)
        self._record(delivery)
        return delivery

    def _record(self, delivery: Delivery) -> None:
        if self._metrics is None or delivery.assessment is None:
            return
        assessment = delivery.assessment
        self._metrics.incr("assessments_total")
        self._metrics.incr(
            "requires_human_true" if assessment.requires_human else "requires_human_false"
        )
        self._metrics.incr(f"explanation_source_{assessment.explanation_source}")

    def handle(self, inbound: NormalizedInbound) -> Delivery:
        if inbound.kind is InboundKind.OPEN_CASE:
            return self._open_case(inbound)
        if inbound.kind is InboundKind.CONFIRM_REASON:
            return self._confirm_reason(inbound)
        if inbound.kind is InboundKind.SUBMIT_EVIDENCE:
            return self._submit_evidence(inbound)
        if inbound.kind is InboundKind.WITHDRAW_LATEST_EVIDENCE:
            return self._withdraw_latest_evidence(inbound)
        if inbound.kind is InboundKind.SET_CARD_NETWORK:
            return self._set_card_network(inbound)
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
        if inbound.card_network is not None:
            try:
                network = CardNetwork(inbound.card_network)
            except ValueError:
                raise InvalidInbound() from None
            state = self._store.set_card_network(case_id, network, state.revision)
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

    def _withdraw_latest_evidence(self, inbound: NormalizedInbound) -> Delivery:
        if not inbound.case_id or not inbound.evidence_code:
            raise InvalidInbound()
        try:
            code = ChargebackEvidenceCode(inbound.evidence_code)
        except ValueError:
            raise InvalidInbound() from None
        state = self._store.withdraw_latest_evidence(inbound.case_id, code)
        return self._deliver(inbound.case_id, state)

    def _set_card_network(self, inbound: NormalizedInbound) -> Delivery:
        if (
            not inbound.case_id
            or not inbound.card_network
            or type(inbound.expected_revision) is not int
        ):
            raise InvalidInbound()
        try:
            network = CardNetwork(inbound.card_network)
        except ValueError:
            raise InvalidInbound() from None
        state = self._store.set_card_network(
            inbound.case_id,
            network,
            inbound.expected_revision,
        )
        return self._deliver(inbound.case_id, state)

    def _get_case(self, inbound: NormalizedInbound) -> Delivery:
        if not inbound.case_id:
            raise InvalidInbound()
        return self.get_case(inbound.case_id)

    def get_case(self, case_id: str) -> Delivery:
        """Read one stored case without a model call or decision metric."""
        return self._reader.read(case_id).delivery

    def list_cases(self) -> tuple[Delivery, ...]:
        """Read cases through the same projection as the single-case endpoint."""
        return tuple(snapshot.delivery for snapshot in self._reader.list_cases())

    def _require_state(self, case_id: str) -> ChargebackCaseState:
        state = self._store.load(case_id)
        if state is None:
            raise CaseNotFound()
        return state
