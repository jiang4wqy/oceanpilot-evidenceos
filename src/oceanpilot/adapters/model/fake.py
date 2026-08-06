"""A deterministic, offline ModelProvider.

Used by tests and by the synthetic demo so the agent cluster runs end-to-end
with no API key or network. It never calls a real model; it returns scripted
results (or a default) and records every request for assertions.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from oceanpilot.application.model_provider import (
    ModelMessage,
    ModelResult,
    TaskSpec,
    ToolSpec,
)


@dataclass
class CapturedRequest:
    task: TaskSpec
    messages: tuple[ModelMessage, ...]
    system: str | None
    tools: tuple[ToolSpec, ...]


class ScriptedModelProvider:
    """Returns queued results in order, then falls back to ``default_text``.

    Pass ``error`` to make every call raise it (to exercise graceful
    degradation). Queue items may be ``ModelResult`` or a plain ``str``.
    """

    def __init__(
        self,
        responses: Sequence[ModelResult | str] | None = None,
        *,
        default_text: str = "",
        error: Exception | None = None,
    ) -> None:
        self._queue: list[ModelResult | str] = list(responses or ())
        self._default_text = default_text
        self._error = error
        self.requests: list[CapturedRequest] = []

    def complete(
        self,
        task: TaskSpec,
        messages: Sequence[ModelMessage],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
    ) -> ModelResult:
        self.requests.append(
            CapturedRequest(
                task=task,
                messages=tuple(messages),
                system=system,
                tools=tuple(tools),
            )
        )
        if self._error is not None:
            raise self._error
        if self._queue:
            item = self._queue.pop(0)
            return item if isinstance(item, ModelResult) else ModelResult(text=item)
        return ModelResult(text=self._default_text)
