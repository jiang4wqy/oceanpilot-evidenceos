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
