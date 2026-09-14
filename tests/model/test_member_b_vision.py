import base64
import json

import pytest

from oceanpilot.adapters.model.claude import ClaudeProvider
from oceanpilot.adapters.model.local import LocalHttpResponse, LocalModelProvider
from oceanpilot.adapters.redaction import RegexRedactor
from oceanpilot.application.model_provider import (
    ModelImage,
    ModelMessage,
    ModelProviderError,
    ModelRole,
    TaskSpec,
)
from oceanpilot.application.redaction import RedactingModelProvider


def message():
    return ModelMessage(
        role=ModelRole.USER,
        content="read this synthetic image",
        images=(
            ModelImage(mime_type="image/png", data_base64=base64.b64encode(b"synthetic").decode()),
        ),
    )


def test_openai_compatible_provider_encodes_actual_image_data_blocks():
    requests = []

    def transport(request):
        requests.append(json.loads(request.body))
        return LocalHttpResponse(
            status_code=200, body=b'{"choices":[{"message":{"content":"ok"}}]}'
        )

    provider = LocalModelProvider(
        endpoint="https://example.invalid/chat/completions", transport=transport
    )
    provider.complete(TaskSpec(kind="evidence_document_extraction"), [message()])
    blocks = requests[0]["messages"][0]["content"]
    assert blocks[0] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,c3ludGhldGlj"},
    }
    assert blocks[1]["text"] == "read this synthetic image"


def test_anthropic_provider_preserves_image_input():
    from types import SimpleNamespace

    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(content=[])

    provider = ClaudeProvider(client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    provider.complete(TaskSpec(kind="evidence_document_extraction"), [message()])
    block = calls[0]["messages"][0]["content"][0]
    assert block == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "c3ludGhldGlj"},
    }


def test_text_redactor_never_silently_drops_or_exposes_pixels():
    class NeverSend:
        def complete(self, *args, **kwargs):
            pytest.fail("raw image reached external provider through a text redactor")

    with pytest.raises(ModelProviderError):
        RedactingModelProvider(NeverSend(), RegexRedactor()).complete(
            TaskSpec(kind="document"), [message()]
        )
