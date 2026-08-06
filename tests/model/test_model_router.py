import pytest

from oceanpilot.application.model_provider import (
    ModelMessage,
    ModelProvider,
    ModelProviderError,
    ModelResult,
    ModelRole,
    RoutingModelProvider,
    SecurityTier,
    TaskSpec,
)

_MSGS = [ModelMessage(role=ModelRole.USER, content="x")]


class _FakeProvider:
    def __init__(self, label: str) -> None:
        self.label = label
        self.calls = 0

    def complete(self, task, messages, *, system=None, tools=()):
        self.calls += 1
        return ModelResult(text=self.label)


def test_router_dispatches_by_security_tier():
    high = _FakeProvider("local")
    low = _FakeProvider("external")
    router = RoutingModelProvider({SecurityTier.HIGH: high, SecurityTier.LOW: low})

    assert (
        router.complete(TaskSpec(kind="k", security_tier=SecurityTier.HIGH), _MSGS).text == "local"
    )
    assert (
        router.complete(TaskSpec(kind="k", security_tier=SecurityTier.LOW), _MSGS).text
        == "external"
    )
    assert high.calls == 1
    assert low.calls == 1


def test_router_missing_tier_raises_safe_error():
    router = RoutingModelProvider({SecurityTier.LOW: _FakeProvider("external")})
    with pytest.raises(ModelProviderError):
        router.complete(TaskSpec(kind="k", security_tier=SecurityTier.HIGH), _MSGS)


def test_router_requires_at_least_one_provider():
    with pytest.raises(ValueError):
        RoutingModelProvider({})


def test_router_satisfies_model_provider_protocol():
    router = RoutingModelProvider({SecurityTier.LOW: _FakeProvider("external")})
    assert isinstance(router, ModelProvider)
