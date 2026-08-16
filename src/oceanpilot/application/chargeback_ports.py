"""Store seam for chargeback case state.

The HTTP channel persists the supervisor's ``ChargebackCaseState`` between
stateless requests through this port. The in-memory adapter is enough for the
demo/HTTP entry; T9 swaps in a SQLite-backed store (with audit / CAS) behind the
same protocol.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from oceanpilot.application.chargeback_supervisor import ChargebackCaseState
from oceanpilot.domain.chargeback import CardNetwork, ChargebackEvidenceCode


@dataclass(frozen=True)
class ChargebackAuditEvent:
    """One append-only audit entry, in application-neutral shape."""

    seq: int
    event_type: str
    detail: str | None
    case_revision: int
    occurred_at: datetime


class ChargebackCaseStore(Protocol):
    def create(self) -> str: ...

    def list_case_ids(self) -> tuple[str, ...]: ...

    def load(self, case_id: str) -> ChargebackCaseState | None: ...

    def save(self, case_id: str, state: ChargebackCaseState) -> None: ...

    def withdraw_latest_evidence(
        self,
        case_id: str,
        expected_evidence_code: ChargebackEvidenceCode,
    ) -> ChargebackCaseState: ...

    def set_card_network(
        self,
        case_id: str,
        card_network: CardNetwork,
        expected_revision: int,
    ) -> ChargebackCaseState: ...

    def audit_trail(self, case_id: str) -> tuple[ChargebackAuditEvent, ...]: ...
