"""Bound model waiting even when a transport ignores its socket timeout.

Only the provider call runs in a worker: it can return text/tool proposals, but
cannot execute a case command. Late results are discarded. A bounded semaphore
prevents timed-out upstream connections from spawning unlimited workers; daemon
workers do not block application shutdown. This is cancellation of waiting, not
an assertion that the upstream server canceled generation or billing.
"""

from collections.abc import Sequence
from contextvars import copy_context
from math import isfinite
from threading import BoundedSemaphore, Event, Thread
from time import monotonic

from oceanpilot.application.model_provider import (
    ModelFailureCode,
    ModelMessage,
    ModelProvider,
    ModelProviderError,
    ModelResult,
    TaskSpec,
    ToolSpec,
    remaining_model_seconds,
)


class DeadlineModelProvider:
    def __init__(
        self,
        provider: ModelProvider,
        *,
        timeout_seconds: float = 12.0,
        max_in_flight: int = 4,
    ) -> None:
        if (
            type(timeout_seconds) not in (int, float)
            or not isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("model timeout must be a finite positive number")
        if type(max_in_flight) is not int or max_in_flight < 1:
            raise ValueError("max_in_flight must be a positive integer")
        self._provider = provider
        self._timeout_seconds = float(timeout_seconds)
        self._slots = BoundedSemaphore(max_in_flight)

    def complete(
        self,
        task: TaskSpec,
        messages: Sequence[ModelMessage],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
    ) -> ModelResult:
        deadline = monotonic() + remaining_model_seconds(self._timeout_seconds)
        if not self._slots.acquire(blocking=False):
            raise ModelProviderError(ModelFailureCode.BUSY)
        finished = Event()
        outcomes: list[ModelResult | ModelProviderError] = []

        def invoke() -> None:
            try:
                result = self._provider.complete(task, messages, system=system, tools=tools)
                outcomes.append(
                    result
                    if isinstance(result, ModelResult)
                    else ModelProviderError(ModelFailureCode.INVALID_RESPONSE)
                )
            except ModelProviderError as error:
                outcomes.append(ModelProviderError(error.code))
            except Exception:
                outcomes.append(ModelProviderError())
            finally:
                self._slots.release()
                finished.set()

        context = copy_context()
        worker = Thread(target=context.run, args=(invoke,), name="model-request", daemon=True)
        try:
            worker.start()
        except Exception:
            self._slots.release()
            raise ModelProviderError() from None
        if not finished.wait(max(0, deadline - monotonic())) or monotonic() >= deadline:
            raise ModelProviderError(ModelFailureCode.TIMEOUT)
        outcome = outcomes[0]
        if isinstance(outcome, ModelProviderError):
            raise outcome from None
        return outcome
