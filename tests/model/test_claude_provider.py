from types import SimpleNamespace

import pytest

from oceanpilot.adapters.model.claude import ClaudeProvider
from oceanpilot.application.model_provider import (
    Effort,
    ModelMessage,
    ModelProviderError,
    ModelRole,
    TaskSpec,
    ToolSpec,
)

_MSGS = [ModelMessage(role=ModelRole.USER, content="hi")]


class _FakeMessages:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class _FakeClient:
    def __init__(self, response=None, error=None):
        self.messages = _FakeMessages(response=response, error=error)


def _text_response(text, *, stop_reason="end_turn", model="claude-opus-4-8"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        model=model,
    )


def test_complete_builds_adaptive_request_without_banned_params():
    client = _FakeClient(response=_text_response("hello"))
    provider = ClaudeProvider(client=client)

    result = provider.complete(
        TaskSpec(kind="intake", effort=Effort.HIGH),
        _MSGS,
        system="be terse",
    )

    assert result.text == "hello"
    assert result.model == "claude-opus-4-8"
    assert result.stop_reason == "end_turn"

    req = client.messages.calls[0]
    assert req["model"] == "claude-opus-4-8"
    assert req["system"] == "be terse"
    assert req["messages"] == [{"role": "user", "content": "hi"}]
    assert req["extra_body"]["thinking"] == {"type": "adaptive"}
    assert req["extra_body"]["output_config"] == {"effort": "high"}
    # Opus 4.8 rejects these — they must never be sent, anywhere in the request.
    assert "temperature" not in req
    assert "top_p" not in req
    assert "budget_tokens" not in req
    assert "budget_tokens" not in req["extra_body"]


def test_tool_calls_are_parsed():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="calling"),
            SimpleNamespace(type="tool_use", id="tu_1", name="lookup", input={"q": "x"}),
        ],
        stop_reason="tool_use",
        model="claude-opus-4-8",
    )
    provider = ClaudeProvider(client=_FakeClient(response=response))

    result = provider.complete(
        TaskSpec(kind="assess"),
        _MSGS,
        tools=[ToolSpec(name="lookup", description="d", input_schema={"type": "object"})],
    )

    assert result.text == "calling"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "lookup"
    assert result.tool_calls[0].arguments == {"q": "x"}
    assert result.stop_reason == "tool_use"


def test_effort_and_max_tokens_flow_through():
    client = _FakeClient(response=_text_response("ok"))
    provider = ClaudeProvider(client=client)
    provider.complete(TaskSpec(kind="draft", effort=Effort.XHIGH, max_output_tokens=9000), _MSGS)
    req = client.messages.calls[0]
    assert req["max_tokens"] == 9000
    assert req["extra_body"]["output_config"] == {"effort": "xhigh"}


def test_model_override_by_task_kind():
    client = _FakeClient(response=_text_response("ok"))
    provider = ClaudeProvider(client=client, model_overrides={"classify": "claude-haiku-4-5"})
    provider.complete(TaskSpec(kind="classify"), _MSGS)
    assert client.messages.calls[0]["model"] == "claude-haiku-4-5"


def test_provider_failure_is_wrapped_and_never_leaks():
    client = _FakeClient(error=RuntimeError("boom secret-key-xyz"))
    provider = ClaudeProvider(client=client)
    with pytest.raises(ModelProviderError) as captured:
        provider.complete(TaskSpec(kind="intake"), _MSGS)
    assert "secret-key-xyz" not in str(captured.value)
