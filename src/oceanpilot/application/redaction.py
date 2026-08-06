"""Redaction seam + a redacting model wrapper.

Security tier MEDIUM means "redact, then send to an external model". This module
provides the ``Redactor`` protocol and a ``RedactingModelProvider`` that redacts
every message (and the system prompt) before delegating to a wrapped provider —
so raw PII never leaves for an external model. Compose it under the MEDIUM tier
of ``RoutingModelProvider``; HIGH routes to a local model instead, LOW sends
directly. Concrete redactors live in the adapter layer.
"""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from oceanpilot.application.model_provider import (
    ModelMessage,
    ModelProvider,
    ModelResult,
    TaskSpec,
    ToolSpec,
)


@runtime_checkable
class Redactor(Protocol):
    def redact(self, text: str) -> str: ...


class RedactingModelProvider:
    def __init__(self, inner: ModelProvider, redactor: Redactor) -> None:
        self._inner = inner
        self._redactor = redactor

    def complete(
        self,
        task: TaskSpec,
        messages: Sequence[ModelMessage],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
    ) -> ModelResult:
        redacted = [
            ModelMessage(role=m.role, content=self._redactor.redact(m.content)) for m in messages
        ]
        redacted_system = self._redactor.redact(system) if system is not None else None
        return self._inner.complete(task, redacted, system=redacted_system, tools=tools)
