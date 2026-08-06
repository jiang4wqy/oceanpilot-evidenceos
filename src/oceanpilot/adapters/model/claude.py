from collections.abc import Mapping, Sequence

import anthropic

from oceanpilot.application.model_provider import (
    ModelMessage,
    ModelProviderError,
    ModelResult,
    TaskSpec,
    ToolCall,
    ToolSpec,
)

DEFAULT_MODEL = "claude-opus-4-8"


class ClaudeProvider:
    """`ModelProvider` backed by the official Anthropic SDK.

    Defaults to Claude Opus 4.8 with adaptive thinking and the effort control;
    it never sends `temperature` or `budget_tokens` (rejected with 400 on 4.8),
    and passes the newer controls via `extra_body` so they don't depend on the
    installed SDK's typing. A client can be injected for tests; production builds
    an `anthropic.Anthropic()` that reads credentials from the environment.
    """

    def __init__(
        self,
        *,
        default_model: str = DEFAULT_MODEL,
        model_overrides: Mapping[str, str] | None = None,
        client: object | None = None,
    ) -> None:
        if not default_model:
            raise ValueError("default_model must be non-empty")
        self._default_model = default_model
        self._overrides = dict(model_overrides or {})
        self._client = client if client is not None else anthropic.Anthropic()

    def _model_for(self, task: TaskSpec) -> str:
        return self._overrides.get(task.kind, self._default_model)

    def complete(
        self,
        task: TaskSpec,
        messages: Sequence[ModelMessage],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
    ) -> ModelResult:
        request: dict[str, object] = {
            "model": self._model_for(task),
            "max_tokens": task.max_output_tokens,
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
            "extra_body": {
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": task.effort.value},
            },
        }
        if system is not None:
            request["system"] = system
        if tools:
            request["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": dict(t.input_schema),
                }
                for t in tools
            ]
        try:
            response = self._client.messages.create(**request)
        except Exception:
            raise ModelProviderError() from None
        return self._to_result(response)

    @staticmethod
    def _to_result(response: object) -> ModelResult:
        texts: list[str] = []
        calls: list[ToolCall] = []
        for block in getattr(response, "content", ()) or ():
            block_type = getattr(block, "type", None)
            if block_type == "text":
                texts.append(getattr(block, "text", ""))
            elif block_type == "tool_use":
                calls.append(
                    ToolCall(
                        call_id=getattr(block, "id", ""),
                        name=getattr(block, "name", ""),
                        arguments=dict(getattr(block, "input", {}) or {}),
                    )
                )
        return ModelResult(
            text="".join(texts),
            tool_calls=tuple(calls),
            stop_reason=getattr(response, "stop_reason", None),
            model=getattr(response, "model", None),
        )
