"""In-memory decision metrics for the chargeback cluster.

A tiny, dependency-free counter registry so the API can expose trust/operability
signals — how often cases need human review, how often the explanation came from
the model vs the deterministic fallback, appeal submit-vs-block rates, prevention
risk mix. Process-local and synthetic; not a production metrics backend.
"""

from threading import Lock


class DecisionMetrics:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = Lock()

    def incr(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + amount

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(sorted(self._counts.items()))
