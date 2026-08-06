"""Store seam for chargeback case state.

The HTTP channel persists the supervisor's ``ChargebackCaseState`` between
stateless requests through this port. The in-memory adapter is enough for the
demo/HTTP entry; T9 swaps in a SQLite-backed store (with audit / CAS) behind the
same protocol.
"""

from typing import Protocol

from oceanpilot.application.chargeback_supervisor import ChargebackCaseState


class ChargebackCaseStore(Protocol):
    def create(self) -> str: ...

    def load(self, case_id: str) -> ChargebackCaseState | None: ...

    def save(self, case_id: str, state: ChargebackCaseState) -> None: ...
