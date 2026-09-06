from threading import Event
from time import monotonic
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from oceanpilot.adapters.model.deadline import DeadlineModelProvider
from oceanpilot.application.model_provider import (
    ModelFailureCode,
    ModelProviderError,
    ModelResult,
    TaskSpec,
    model_request_budget,
    remaining_model_seconds,
)


def test_deadline_returns_without_waiting_for_late_provider_and_limits_in_flight_calls():
    release = Event()
    provider = Mock()
    provider.complete.side_effect = lambda *args, **kwargs: (
        release.wait(2) and ModelResult(text="late result")
    )
    bounded = DeadlineModelProvider(provider, timeout_seconds=0.02, max_in_flight=1)
    try:
        started = monotonic()
        with pytest.raises(ModelProviderError) as error:
            bounded.complete(TaskSpec(kind="synthetic"), [])
        assert error.value.code is ModelFailureCode.TIMEOUT
        assert monotonic() - started < 0.5
        with pytest.raises(ModelProviderError) as busy:
            bounded.complete(TaskSpec(kind="synthetic"), [])
        assert busy.value.code is ModelFailureCode.BUSY
        assert provider.complete.call_count == 1
    finally:
        release.set()


def test_request_budget_is_shared_by_calls_and_nested_budget_cannot_extend_it():
    release = Event()
    provider = Mock()
    provider.complete.side_effect = lambda *args, **kwargs: release.wait(2)
    bounded = DeadlineModelProvider(provider, timeout_seconds=1)
    try:
        with model_request_budget(0.02):
            with model_request_budget(10):
                with pytest.raises(ModelProviderError) as first:
                    bounded.complete(TaskSpec(kind="synthetic"), [])
                assert first.value.code is ModelFailureCode.TIMEOUT
            with pytest.raises(ModelProviderError) as second:
                bounded.complete(TaskSpec(kind="synthetic"), [])
            assert second.value.code is ModelFailureCode.TIMEOUT
        assert provider.complete.call_count == 1
        assert remaining_model_seconds(1) == 1
    finally:
        release.set()


def test_context_budget_crosses_fastapi_sync_and_provider_worker_threads():
    recorded = []
    provider = Mock()

    def complete(*args, **kwargs):
        recorded.append(remaining_model_seconds(100))
        return ModelResult(text="synthetic")

    provider.complete.side_effect = complete
    bounded = DeadlineModelProvider(provider, timeout_seconds=12)
    app = FastAPI()

    @app.middleware("http")
    async def budget(request: Request, call_next):
        with model_request_budget(0.5):
            return await call_next(request)

    @app.get("/synthetic")
    def read():
        return {"text": bounded.complete(TaskSpec(kind="synthetic"), []).text}

    with TestClient(app) as client:
        response = client.get("/synthetic")
    assert response.json() == {"text": "synthetic"}
    assert len(recorded) == 1
    assert 0 < recorded[0] <= 0.5


def test_unexpected_transport_errors_are_sanitized():
    provider = Mock()
    provider.complete.side_effect = RuntimeError("secret-upstream-error")
    with pytest.raises(ModelProviderError) as error:
        DeadlineModelProvider(provider).complete(TaskSpec(kind="synthetic"), [])
    assert str(error.value) == "model provider request failed"
    assert error.value.code is ModelFailureCode.UNAVAILABLE


@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf")])
def test_deadline_configuration_requires_finite_positive_seconds(value):
    with pytest.raises(ValueError):
        DeadlineModelProvider(Mock(), timeout_seconds=value)
    with pytest.raises(ValueError), model_request_budget(value):
        pass


def test_malformed_injected_provider_result_is_an_explicit_failure():
    provider = Mock()
    provider.complete.return_value = {"text": "not-a-model-result"}
    with pytest.raises(ModelProviderError) as error:
        DeadlineModelProvider(provider).complete(TaskSpec(kind="synthetic"), [])
    assert error.value.code is ModelFailureCode.INVALID_RESPONSE
