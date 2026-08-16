from oceanpilot.adapters.model.composition import build_chargeback_model_provider
from oceanpilot.application.model_provider import (
    Effort,
    ModelMessage,
    ModelProvider,
    ModelResult,
    ModelRole,
    RoutingModelProvider,
    SecurityTier,
    TaskSpec,
)

_MSGS = [ModelMessage(role=ModelRole.USER, content="card 4111 1111 1111 1111")]


class _RecordingProvider:
    def __init__(self) -> None:
        self.systems: list[str | None] = []
        self.contents: list[str] = []

    def complete(self, task, messages, *, system=None, tools=()):
        self.systems.append(system)
        self.contents.extend(m.content for m in messages)
        return ModelResult(text="ok")


def test_returns_none_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert build_chargeback_model_provider() is None


def test_composes_tiered_router_with_injected_claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-dummy")
    monkeypatch.delenv("OCEANPILOT_LOCAL_MODEL_ENDPOINT", raising=False)
    recorder = _RecordingProvider()

    provider = build_chargeback_model_provider(claude=recorder)
    assert isinstance(provider, RoutingModelProvider)
    assert isinstance(provider, ModelProvider)

    # LOW goes straight to Claude, unredacted.
    provider.complete(TaskSpec(kind="k", security_tier=SecurityTier.LOW, effort=Effort.LOW), _MSGS)
    assert recorder.contents[-1] == "card 4111 1111 1111 1111"

    # MEDIUM redacts before reaching Claude; the raw PAN never leaves.
    provider.complete(
        TaskSpec(kind="k", security_tier=SecurityTier.MEDIUM, effort=Effort.LOW), _MSGS
    )
    assert "4111 1111 1111 1111" not in recorder.contents[-1]

    # HIGH with no local endpoint falls back to the redacting path (never clear).
    provider.complete(TaskSpec(kind="k", security_tier=SecurityTier.HIGH, effort=Effort.LOW), _MSGS)
    assert "4111 1111 1111 1111" not in recorder.contents[-1]


def test_composes_tiered_router_with_injected_deepseek(monkeypatch):
    monkeypatch.setenv("OCEANPILOT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OCEANPILOT_LOCAL_MODEL_ENDPOINT", raising=False)
    recorder = _RecordingProvider()

    provider = build_chargeback_model_provider(deepseek=recorder)

    assert isinstance(provider, RoutingModelProvider)
    provider.complete(TaskSpec(kind="k", security_tier=SecurityTier.LOW), _MSGS)
    assert recorder.contents[-1] == "card 4111 1111 1111 1111"

    provider.complete(TaskSpec(kind="k", security_tier=SecurityTier.MEDIUM), _MSGS)
    assert "4111 1111 1111 1111" not in recorder.contents[-1]

    provider.complete(TaskSpec(kind="k", security_tier=SecurityTier.HIGH), _MSGS)
    assert "4111 1111 1111 1111" not in recorder.contents[-1]
