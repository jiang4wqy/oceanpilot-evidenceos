"""Signal-source seam for the prevention agent (design §6 ⑦).

The Prevention agent scores a transaction from ``PreventionSignals``. Where those
signals come from — the company's risk/authorization feed in production, a
synthetic table in the demo — is hidden behind this port, so the agent and the
channel layer never depend on a concrete signal system.
"""

from typing import Protocol

from oceanpilot.domain.chargeback_prevention import PreventionSignals


class SignalSource(Protocol):
    def get_signals(self, transaction_ref: str) -> PreventionSignals | None: ...
