"""Time seam for deadline-driven work.

Deadlines are a first-class concern in chargeback (15-day evidence window,
45-day review window). The application depends on this ``Clock`` protocol so the
current time is injectable — deterministic in tests, real in production.
"""

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...
