from datetime import UTC, datetime


class SystemClock:
    """Real wall-clock ``Clock`` (UTC)."""

    def now(self) -> datetime:
        return datetime.now(UTC)
