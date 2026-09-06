import json

from oceanpilot.adapters.model.deepseek import build_deepseek_model_provider_from_env
from oceanpilot.adapters.model.local import LocalHttpRequest, LocalHttpResponse
from oceanpilot.application.model_provider import ModelMessage, ModelRole, TaskSpec


class _RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[LocalHttpRequest] = []

    def __call__(self, request: LocalHttpRequest) -> LocalHttpResponse:
        self.requests.append(request)
        body = {
            "model": "deepseek-chat",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "synthetic response"},
                    "finish_reason": "stop",
                }
            ],
        }
        return LocalHttpResponse(status_code=200, body=json.dumps(body).encode())


def test_build_from_env_calls_the_deepseek_chat_api(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    monkeypatch.delenv("DEEPSEEK_API_BASE", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    transport = _RecordingTransport()

    provider = build_deepseek_model_provider_from_env(transport=transport)

    assert provider is not None
    result = provider.complete(
        TaskSpec(kind="chargeback_intake"),
        [ModelMessage(role=ModelRole.USER, content="synthetic merchant issue")],
        system="Classify this synthetic issue.",
    )
    assert result.text == "synthetic response"
    request = transport.requests[0]
    assert request.url == "https://api.deepseek.com/chat/completions"
    assert dict(request.headers)["Authorization"] == "Bearer test-only-key"
    payload = json.loads(request.body)
    assert payload["model"] == "deepseek-chat"
    assert payload["messages"] == [
        {"role": "system", "content": "Classify this synthetic issue."},
        {"role": "user", "content": "synthetic merchant issue"},
    ]
    assert "metadata" not in payload


def test_deepseek_has_a_single_twelve_second_transport_attempt(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    transport = _RecordingTransport()
    provider = build_deepseek_model_provider_from_env(transport=transport)
    provider.complete(TaskSpec(kind="synthetic"), [])
    assert len(transport.requests) == 1
    assert transport.requests[0].timeout == 12


def test_rate_limit_is_sanitized_and_not_retried(monkeypatch):
    from oceanpilot.application.model_provider import ModelFailureCode, ModelProviderError

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    calls = []

    def limited(request):
        calls.append(request)
        return LocalHttpResponse(status_code=429, body=b"secret-upstream-body")

    provider = build_deepseek_model_provider_from_env(transport=limited)
    import pytest

    with pytest.raises(ModelProviderError) as error:
        provider.complete(TaskSpec(kind="synthetic"), [])
    assert error.value.code is ModelFailureCode.RATE_LIMITED
    assert str(error.value) == "model provider request failed"
    assert len(calls) == 1


def test_timeout_has_a_safe_failure_code(monkeypatch):
    from oceanpilot.application.model_provider import ModelFailureCode, ModelProviderError

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")

    def timeout(request):
        raise TimeoutError("secret-url-and-upstream-detail")

    provider = build_deepseek_model_provider_from_env(transport=timeout)
    import pytest

    with pytest.raises(ModelProviderError) as error:
        provider.complete(TaskSpec(kind="synthetic"), [])
    assert error.value.code is ModelFailureCode.TIMEOUT
    assert str(error.value) == "model provider request failed"
