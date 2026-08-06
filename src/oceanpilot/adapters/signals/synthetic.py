"""Synthetic ``SignalSource`` for the prevention agent (offline/demo).

Holds a small table of synthetic ``PreventionSignals`` keyed by transaction ref.
No PII, no external calls — enough to run the prevention agent without the
company's real signal feed. The production adapter implements the same
``SignalSource`` protocol.
"""

from collections.abc import Mapping

from oceanpilot.domain.chargeback_prevention import PreventionSignals


class InMemorySignalSource:
    def __init__(self, signals: Mapping[str, PreventionSignals] | None = None) -> None:
        self._signals: dict[str, PreventionSignals] = dict(signals or {})

    def put(self, transaction_ref: str, signals: PreventionSignals) -> None:
        self._signals[transaction_ref] = signals

    def get_signals(self, transaction_ref: str) -> PreventionSignals | None:
        return self._signals.get(transaction_ref)
