import json

import pytest

from oceanpilot.adapters.model.local import (
    LocalHttpRequest,
    LocalHttpResponse,
    LocalModelProvider,
    build_local_model_provider_from_env,
)
from oceanpilot.application.model_provider import (
    Effort,
    ModelMessage,
    ModelProviderError,
    ModelRole,
    RoutingModelProvider,
    SecurityTier,
    TaskSpec,
    ToolSpec,
)

ENDPOINT = "http://127.0.0.1:8000/v1/chat/completions"
_MSGS = [ModelMessage(role=ModelRole.USER, content="hi")]


class _RecordingTransport:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.requests: list[LocalHttpRequest] = []

    def __call__(self, request: LocalHttpRequest) -> LocalHttpResponse:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        return self._response


def _ok(body: dict) -> LocalHttpResponse:
    return LocalHttpResponse(status_code=200, body=json.dumps(body).encode())


def _text_body(text, *, finish_reason="stop", model="local-isolated-model"):
    return {
        "model": model,
        "choices": [
            {"message": {"role": "assistant", "content": text}, "finish_reason": finish_reason}
        ],
    }


def _decode_payload(request: LocalHttpRequest) -> dict:
    return json.loads(request.body)


def test_complete_builds_openai_chat_request_with_system_prepended():
    transport = _RecordingTransport(response=_ok(_text_body("hello")))
    provider = LocalModelProvider(
        endpoint=ENDPOINT, default_model="qwen-local", transport=transport
    )

    result = provider.complete(
        TaskSpec(kind="intake", security_tier=SecurityTier.HIGH, effort=Effort.HIGH),
        _MSGS,
        system="be terse",
    )

    assert result.text == "hello"
    assert result.model == "local-isolated-model"
    assert result.stop_reason == "stop"

    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url == ENDPOINT
    payload = _decode_payload(request)
    assert payload["model"] == "qwen-local"
    assert payload["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hi"},
    ]
    assert payload["max_tokens"] == 4096
    assert payload["metadata"] == {
        "kind": "intake",
        "effort": "high",
        "security_tier": "HIGH",
    }
    # Auth header only when an api_key is configured.
    assert not any(name == "Authorization" for name, _ in request.headers)


def test_api_key_is_sent_as_bearer_header():
    transport = _RecordingTransport(response=_ok(_text_body("ok")))
    provider = LocalModelProvider(endpoint=ENDPOINT, api_key="local-secret", transport=transport)
    provider.complete(TaskSpec(kind="assess"), _MSGS)
    headers = dict(transport.requests[0].headers)
    assert headers["Authorization"] == "Bearer local-secret"


def test_tools_are_mapped_to_openai_function_schema():
    transport = _RecordingTransport(response=_ok(_text_body("ok")))
    provider = LocalModelProvider(endpoint=ENDPOINT, transport=transport)
    provider.complete(
        TaskSpec(kind="assess"),
        _MSGS,
        tools=[ToolSpec(name="lookup", description="d", input_schema={"type": "object"})],
    )
    payload = _decode_payload(transport.requests[0])
    assert payload["tool_choice"] == "auto"
    assert payload["tools"] == [
        {
            "type": "function",
            "function": {"name": "lookup", "description": "d", "parameters": {"type": "object"}},
        }
    ]


def test_tool_calls_are_parsed_from_json_string_arguments():
    body = {
        "model": "local-isolated-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": '{"q": "x"}'},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }
    provider = LocalModelProvider(
        endpoint=ENDPOINT, transport=_RecordingTransport(response=_ok(body))
    )
    result = provider.complete(TaskSpec(kind="assess"), _MSGS)
    assert result.text == ""
    assert len(result.tool_calls) == 1
    call = result.tool_calls[0]
    assert call.call_id == "call_1"
    assert call.name == "lookup"
    assert call.arguments == {"q": "x"}
    assert result.stop_reason == "tool_calls"


def test_model_override_by_task_kind():
    transport = _RecordingTransport(response=_ok(_text_body("ok")))
    provider = LocalModelProvider(
        endpoint=ENDPOINT,
        default_model="base",
        model_overrides={"classify": "small-local"},
        transport=transport,
    )
    provider.complete(TaskSpec(kind="classify"), _MSGS)
    assert _decode_payload(transport.requests[0])["model"] == "small-local"


@pytest.mark.parametrize(
    "response, error",
    [
        (LocalHttpResponse(status_code=500, body=b"upstream boom secret-key-xyz"), None),
        (LocalHttpResponse(status_code=200, body=b"not-json"), None),
        (LocalHttpResponse(status_code=200, body=json.dumps({"choices": []}).encode()), None),
        (None, RuntimeError("boom secret-key-xyz")),
    ],
)
def test_failures_are_wrapped_and_never_leak(response, error):
    provider = LocalModelProvider(
        endpoint=ENDPOINT,
        api_key="local-secret",
        transport=_RecordingTransport(response=response, error=error),
    )
    with pytest.raises(ModelProviderError) as captured:
        provider.complete(TaskSpec(kind="intake", security_tier=SecurityTier.HIGH), _MSGS)
    message = str(captured.value)
    assert "secret-key-xyz" not in message
    assert "local-secret" not in message
    assert ENDPOINT not in message


def test_malformed_tool_call_arguments_are_rejected():
    body = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [{"function": {"name": "lookup", "arguments": "{not json}"}}],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }
    provider = LocalModelProvider(
        endpoint=ENDPOINT, transport=_RecordingTransport(response=_ok(body))
    )
    with pytest.raises(ModelProviderError):
        provider.complete(TaskSpec(kind="assess"), _MSGS)


def test_registers_as_the_high_tier_provider_in_the_router():
    high = _RecordingTransport(response=_ok(_text_body("from-local")))
    local = LocalModelProvider(endpoint=ENDPOINT, transport=high)

    external_calls: list[TaskSpec] = []

    class _ExternalProvider:
        def complete(self, task, messages, *, system=None, tools=()):
            external_calls.append(task)
            raise AssertionError("HIGH-tier task must not reach the external provider")

    router = RoutingModelProvider({SecurityTier.HIGH: local, SecurityTier.LOW: _ExternalProvider()})
    result = router.complete(
        TaskSpec(kind="intake", security_tier=SecurityTier.HIGH),
        _MSGS,
    )
    assert result.text == "from-local"
    assert len(high.requests) == 1
    assert external_calls == []


def test_invalid_endpoint_is_rejected():
    with pytest.raises(ValueError):
        LocalModelProvider(endpoint="ftp://nope")
    with pytest.raises(ValueError):
        LocalModelProvider(endpoint="")


def test_build_from_env_returns_none_without_endpoint(monkeypatch):
    monkeypatch.delenv("OCEANPILOT_LOCAL_MODEL_ENDPOINT", raising=False)
    assert build_local_model_provider_from_env() is None


def test_build_from_env_configures_endpoint_and_model(monkeypatch):
    monkeypatch.setenv("OCEANPILOT_LOCAL_MODEL_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("OCEANPILOT_LOCAL_MODEL_NAME", "env-local-model")
    transport = _RecordingTransport(response=_ok(_text_body("ok")))
    provider = build_local_model_provider_from_env(transport=transport)
    assert provider is not None
    provider.complete(TaskSpec(kind="intake", security_tier=SecurityTier.HIGH), _MSGS)
    payload = _decode_payload(transport.requests[0])
    assert payload["model"] == "env-local-model"
    assert transport.requests[0].url == ENDPOINT
