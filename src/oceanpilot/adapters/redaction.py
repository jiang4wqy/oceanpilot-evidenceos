import re
from collections.abc import Sequence

# Ordered: cards (longest digit runs) first, then email, then shorter phone runs
# — so a card isn't re-matched as a phone after replacement.
_DEFAULT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b\d(?:[ -]?\d){12,18}\b"), "[REDACTED:CARD]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED:EMAIL]"),
    (re.compile(r"\+?\d[\d -]{7,}\d"), "[REDACTED:PHONE]"),
)


class RegexRedactor:
    """Best-effort PII redactor (card / email / phone) for the MEDIUM tier.

    Deterministic, one-way: replaces matches with typed placeholders so an
    external model never receives the raw values. Patterns are configurable.
    """

    def __init__(self, patterns: Sequence[tuple[re.Pattern[str], str]] | None = None) -> None:
        self._patterns = tuple(patterns) if patterns is not None else _DEFAULT_PATTERNS

    def redact(self, text: str) -> str:
        for pattern, replacement in self._patterns:
            text = pattern.sub(replacement, text)
        return text
