"""Provider-agnostic model access seam.

The application and agent layers depend only on the ``ModelProvider`` protocol
and the DTOs defined here. Concrete providers (Claude via the Anthropic SDK, a
local isolated model, a fake for tests) live in the adapter/test layers and are
injected at composition time. This keeps the "Claude first, but keep the API
pathway pluggable" requirement: swapping or routing models never touches the
callers.
"""

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


class SecurityTier(StrEnum):
    """Confidentiality of the data a task handles — drives provider routing."""

    HIGH = "HIGH"  # raw PII / transaction detail: local isolated model only
    MEDIUM = "MEDIUM"  # redact, then an external model
    LOW = "LOW"  # non-sensitive: external model directly


class ModelRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Effort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ModelMessage(_Frozen):
    role: ModelRole
    content: StrictStr


class ToolSpec(_Frozen):
    name: StrictStr
    description: StrictStr
    input_schema: Mapping[str, object]


class ToolCall(_Frozen):
    call_id: StrictStr
    name: StrictStr
    arguments: Mapping[str, object]


class TaskSpec(_Frozen):
    kind: StrictStr
    security_tier: SecurityTier = SecurityTier.LOW
    effort: Effort = Effort.HIGH
    max_output_tokens: Annotated[StrictInt, Field(ge=1, le=200_000)] = 4096


class ModelResult(_Frozen):
    text: StrictStr
    tool_calls: tuple[ToolCall, ...] = ()
    stop_reason: StrictStr | None = None
    model: StrictStr | None = None


class ModelProviderError(Exception):
    """Fixed, non-leaking error raised by every provider on failure."""

    def __init__(self) -> None:
        super().__init__("model provider request failed")


@runtime_checkable
class ModelProvider(Protocol):
    def complete(
        self,
        task: TaskSpec,
        messages: Sequence[ModelMessage],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
    ) -> ModelResult: ...


class RoutingModelProvider:
    """Dispatch to a concrete provider by the task's security tier.

    High-secrecy tasks route to a local isolated model; lower tiers route to an
    external model (after redaction for MEDIUM, handled upstream). Structurally
    satisfies ``ModelProvider`` so it composes anywhere a provider is expected.
    """

    def __init__(self, providers: Mapping[SecurityTier, ModelProvider]) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self._providers = dict(providers)

    def complete(
        self,
        task: TaskSpec,
        messages: Sequence[ModelMessage],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
    ) -> ModelResult:
        provider = self._providers.get(task.security_tier)
        if provider is None:
            raise ModelProviderError()
        return provider.complete(task, messages, system=system, tools=tools)
