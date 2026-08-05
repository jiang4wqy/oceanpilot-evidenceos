import hashlib
import json

import pytest

import oceanpilot.adapters.feishu.security as security_module
from oceanpilot.adapters.feishu.security import (
    FeishuRequestVerifier,
    FeishuVerificationError,
)

NOW = 1_786_250_000
ENCRYPT_KEY = "synthetic-encrypt-key"
VERIFICATION_TOKEN = "synthetic-verification-token"
NONCE = "nonce-001"


def _signature(timestamp: int, raw_body: bytes) -> str:
    prefix = f"{timestamp}{NONCE}{ENCRYPT_KEY}".encode()
    return hashlib.sha256(prefix + raw_body).hexdigest()


def _headers(timestamp: int, raw_body: bytes, **changes: str) -> dict[str, str]:
    headers = {
        "X-Lark-Request-Timestamp": str(timestamp),
        "X-Lark-Request-Nonce": NONCE,
        "X-Lark-Signature": _signature(timestamp, raw_body),
    }
    headers.update(changes)
    return headers


def _verifier() -> FeishuRequestVerifier:
    return FeishuRequestVerifier(
        encrypt_key=ENCRYPT_KEY,
        verification_token=VERIFICATION_TOKEN,
        now=lambda: NOW,
    )


def test_valid_signature_and_exact_top_level_token_are_verified_before_return():
    raw_body = json.dumps(
        {"token": VERIFICATION_TOKEN, "type": "url_verification", "challenge": "ok"},
        separators=(",", ":"),
    ).encode()

    payload = _verifier().verify(_headers(NOW, raw_body), raw_body)

    assert payload == {
        "token": VERIFICATION_TOKEN,
        "type": "url_verification",
        "challenge": "ok",
    }


def test_v2_header_token_is_supported_with_case_insensitive_headers():
    raw_body = json.dumps({"header": {"token": VERIFICATION_TOKEN}, "event": {}}).encode()
    headers = {key.lower(): value for key, value in _headers(NOW, raw_body).items()}
    assert _verifier().verify(headers, raw_body)["event"] == {}


@pytest.mark.parametrize("offset", [-300, 300])
def test_timestamp_window_includes_exact_boundary(offset: int):
    raw_body = json.dumps({"token": VERIFICATION_TOKEN}).encode()
    assert _verifier().verify(_headers(NOW + offset, raw_body), raw_body)["token"]


@pytest.mark.parametrize("offset", [-301, 301])
def test_timestamp_outside_window_is_rejected_without_sensitive_echo(offset: int):
    raw_body = json.dumps({"token": VERIFICATION_TOKEN, "secret": "BODY-SENTINEL"}).encode()
    with pytest.raises(FeishuVerificationError) as captured:
        _verifier().verify(_headers(NOW + offset, raw_body), raw_body)
    assert str(captured.value) == "feishu request verification failed"
    assert "BODY-SENTINEL" not in str(captured.value)


def test_signature_is_checked_before_json_is_parsed(monkeypatch):
    raw_body = b'{"token":"JSON-SENTINEL"}'
    headers = _headers(NOW, raw_body, **{"X-Lark-Signature": "wrong-signature"})

    def forbidden_parse(*args, **kwargs):
        del args, kwargs
        raise AssertionError("JSON parser must not run")

    monkeypatch.setattr(security_module.json, "loads", forbidden_parse)
    with pytest.raises(FeishuVerificationError):
        _verifier().verify(headers, raw_body)


def test_signature_and_token_comparisons_use_constant_time_primitive(monkeypatch):
    raw_body = json.dumps({"token": VERIFICATION_TOKEN}).encode()
    compared: list[tuple[str, str]] = []
    original = security_module.hmac.compare_digest

    def recording_compare(left: str, right: str) -> bool:
        compared.append((left, right))
        return original(left, right)

    monkeypatch.setattr(security_module.hmac, "compare_digest", recording_compare)
    _verifier().verify(_headers(NOW, raw_body), raw_body)
    assert len(compared) == 2
    assert compared[1] == (VERIFICATION_TOKEN, VERIFICATION_TOKEN)


@pytest.mark.parametrize(
    "raw_body",
    [
        b'{"token":"wrong-token"}',
        b'{"event":{}}',
        b"not-json",
        b"[]",
    ],
)
def test_invalid_token_or_json_uses_one_safe_error(raw_body: bytes, caplog):
    with pytest.raises(FeishuVerificationError) as captured:
        _verifier().verify(_headers(NOW, raw_body), raw_body)
    assert str(captured.value) == "feishu request verification failed"
    assert caplog.records == []


@pytest.mark.parametrize(
    "arguments",
    [
        {"encrypt_key": "", "verification_token": VERIFICATION_TOKEN},
        {"encrypt_key": ENCRYPT_KEY, "verification_token": ""},
        {"encrypt_key": 1, "verification_token": VERIFICATION_TOKEN},
    ],
)
def test_credentials_are_strict_nonempty_constructor_inputs(arguments):
    with pytest.raises((TypeError, ValueError)):
        FeishuRequestVerifier(**arguments, now=lambda: NOW)


def test_raw_body_must_be_exact_bytes():
    with pytest.raises(TypeError):
        _verifier().verify({}, "{}")  # type: ignore[arg-type]
