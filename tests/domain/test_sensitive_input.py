from collections.abc import Callable
from time import perf_counter

import pytest
from pydantic import BaseModel

from oceanpilot.domain.security import SensitiveDataRejected, assert_no_sensitive_data


@pytest.mark.parametrize("sentinel", [
    "Bearer secret-demo-token",
    "cvv=123",
    "password=hunter-demo",
    "4242424242424242",
])
def test_sensitive_sentinels_are_rejected(sentinel: str) -> None:
    with pytest.raises(SensitiveDataRejected):
        assert_no_sensitive_data({"value": sentinel})


class Payload(BaseModel):
    value: str


@pytest.mark.parametrize("wrap", [
    pytest.param(lambda value: value, id="scalar"),
    pytest.param(lambda value: {"nested": [value]}, id="mapping-sequence-value"),
    pytest.param(lambda value: {value: "nested-key"}, id="mapping-key"),
    pytest.param(lambda value: Payload(value=value), id="pydantic-model"),
])
def test_sensitive_scan_is_recursive(wrap: Callable[[str], object]) -> None:
    with pytest.raises(SensitiveDataRejected, match="^sensitive data is not accepted$"):
        assert_no_sensitive_data(wrap("token=secret-demo"))


@pytest.mark.parametrize("sentinel", [
    "Authorization: Basic secret-demo",
    "api_key=secret-demo",
    "access_token=secret-demo",
    "user-password: secret-demo",
    "privateKey=secret-demo",
    '"oauth.access_token": "secret-demo"',
    '"$access_token": "secret-demo"',
    '"_access_token": "secret-demo"',
    f'"{"a" * 59}_token": "secret-demo"',
    "secret-key: secret-demo",
    "cvc=123",
    "4000000000006",
    "4242 4242 4242 4242",
    "4242\t4242\t4242\t4242",
    "4242\u00a04242\u00a04242\u00a04242",
    "4000000000000000006",
    "card-4242424242424242",
])
def test_supported_sensitive_forms_are_rejected_without_echo(sentinel: str) -> None:
    with pytest.raises(SensitiveDataRejected) as caught:
        assert_no_sensitive_data({"value": sentinel})
    assert str(caught.value) == "sensitive data is not accepted"
    assert sentinel not in str(caught.value)


@pytest.mark.parametrize("key", [
    "authorization",
    "api_key",
    "api_keys",
    "apiKeys",
    "apikeys",
    "access_token",
    "accessTokens",
    "accesstokens",
    "user_password",
    "userPasswords",
    "userpasswords",
    "private_key",
    "clientSecret",
    "password",
    "passwords",
    "token",
    "tokens",
    "cvv",
])
def test_structured_sensitive_assignments_are_rejected(key: str) -> None:
    with pytest.raises(SensitiveDataRejected, match="^sensitive data is not accepted$"):
        assert_no_sensitive_data({key: "secret-demo"})


@pytest.mark.parametrize("value", [
    "ordinary synthetic fixture",
    "00000000-0000-4000-8000-000000000011",
    "4242424242424243",
    "monkey=synthetic",
    "4242\r4242\r4242\r4242",
    "4242\n4242\n4242\n4242",
    "0000\t4242\t4242\t4242\t4242",
    "4242\u00a04242\u00a04242\u00a04242\u00a00000",
    {"hockey": "synthetic", "token_count": 0, "token_status": "absent"},
    {"result": "no credentials supplied", "count": 3},
])
def test_safe_values_are_accepted(value: object) -> None:
    assert assert_no_sensitive_data(value) is None


def test_assignment_scan_scales_linearly_on_key_alphabet_runs() -> None:
    def best_elapsed(value: str) -> float:
        samples = []
        for _ in range(3):
            started = perf_counter()
            assert_no_sensitive_data(value)
            samples.append(perf_counter() - started)
        return min(samples)

    small_elapsed = best_elapsed("_" * 2_000)
    large_elapsed = best_elapsed("_" * 4_000)

    assert large_elapsed < small_elapsed * 3, {
        "small_elapsed": small_elapsed,
        "large_elapsed": large_elapsed,
    }
