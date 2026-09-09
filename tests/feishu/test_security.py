import base64
import hashlib
import json

import pytest

import oceanpilot.adapters.feishu.security as security_module
from oceanpilot.adapters.feishu.security import (
    FeishuRequestVerifier,
    FeishuVerificationError,
)
from tests.feishu.crypto_helpers import encrypted_body

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
    assert compared[1] == (VERIFICATION_TOKEN.encode(), VERIFICATION_TOKEN.encode())


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


def test_signed_encrypted_body_returns_verified_inner_payload():
    payload = {"header": {"token": VERIFICATION_TOKEN}, "event": {"text": "合成测试消息"}}
    raw = encrypted_body(payload, ENCRYPT_KEY)
    assert _verifier().verify(_headers(NOW, raw), raw) == payload


@pytest.mark.parametrize("encrypted", [False, True])
def test_url_verification_may_omit_signing_headers_only_with_explicit_handshake_mode(encrypted):
    payload = {"type": "url_verification", "token": VERIFICATION_TOKEN, "challenge": "test-only"}
    raw = encrypted_body(payload, ENCRYPT_KEY) if encrypted else json.dumps(payload).encode()
    with pytest.raises(FeishuVerificationError):
        _verifier().verify({}, raw)
    assert _verifier().verify({}, raw, allow_url_verification=True) == payload


@pytest.mark.parametrize("encrypted", [False, True])
def test_handshake_mode_never_accepts_unsigned_business_events(encrypted):
    payload = {"header": {"token": VERIFICATION_TOKEN}, "event": {"text": "must-not-run"}}
    raw = encrypted_body(payload, ENCRYPT_KEY) if encrypted else json.dumps(payload).encode()
    with pytest.raises(FeishuVerificationError):
        _verifier().verify({}, raw, allow_url_verification=True)


@pytest.mark.parametrize("headers", [{"X-Lark-Signature": "bad"}, {"X-Lark-Request-Nonce": "x"}])
def test_partial_signature_cannot_downgrade_to_unsigned_challenge(headers):
    raw = encrypted_body(
        {"type": "url_verification", "token": VERIFICATION_TOKEN, "challenge": "test"},
        ENCRYPT_KEY,
    )
    with pytest.raises(FeishuVerificationError):
        _verifier().verify(headers, raw, allow_url_verification=True)


@pytest.mark.parametrize("plaintext", [b"not-json", b"[]", b"\xff", b'{"token":"wrong-token"}'])
def test_invalid_decrypted_json_or_token_has_no_sensitive_error_details(plaintext, caplog):
    raw = encrypted_body({}, ENCRYPT_KEY, plaintext=plaintext)
    with pytest.raises(FeishuVerificationError) as captured:
        _verifier().verify(_headers(NOW, raw), raw)
    assert str(captured.value) == "feishu request verification failed"
    assert not caplog.records


@pytest.mark.parametrize("encrypted", ["", "!bad-base64!", "AAAA", 42, None])
def test_bad_ciphertext_cannot_fall_back_to_valid_outer_token(encrypted):
    raw = json.dumps({"encrypt": encrypted, "token": VERIFICATION_TOKEN}).encode()
    with pytest.raises(FeishuVerificationError):
        _verifier().verify(_headers(NOW, raw), raw)


def test_independent_openssl_encrypted_challenge_vector():
    # Generated with openssl enc -aes-256-cbc, SHA256(synthetic-encrypt-key), IV 00..0f.
    ciphertext = (
        "AAECAwQFBgcICQoLDA0OD6YbFy6P+SNhyIaElFlGd8kdUxNwobc0wXD35SXjyYlZvRaneGTy4vYX"
        "vrFXWjEGoMBe2d9Dggqh3dZbdAIH4q+Epvz8slZvEGLwT/qBN48KS5OuxeRh0a3T+x/ICj8owuI/"
        "iAZGEnS/wuMiv5PBcMo="
    )
    raw = json.dumps({"encrypt": ciphertext}).encode()
    payload = _verifier().verify(_headers(NOW, raw), raw)
    assert payload == {
        "token": VERIFICATION_TOKEN,
        "type": "url_verification",
        "challenge": "OpenSSL-independent-vector",
    }


@pytest.mark.parametrize("kind", ["base64", "short", "alignment", "padding", "wrong-key"])
def test_invalid_encrypted_wire_format_is_rejected_uniformly(kind):
    payload = {"token": VERIFICATION_TOKEN, "type": "url_verification", "challenge": "test"}
    encoded = json.loads(
        encrypted_body(payload, "wrong-key" if kind == "wrong-key" else ENCRYPT_KEY)
    )
    if kind == "base64":
        encoded["encrypt"] = "not-base64!"
    elif kind in {"short", "alignment"}:
        encoded["encrypt"] = base64.b64encode(b"x" * (16 if kind == "short" else 33)).decode()
    elif kind == "padding":
        wire = bytearray(base64.b64decode(encoded["encrypt"]))
        # Alter the final plaintext padding byte via the preceding CBC block.
        wire[-17] ^= 0x80
        encoded["encrypt"] = base64.b64encode(wire).decode()
    raw = json.dumps(encoded).encode()
    with pytest.raises(FeishuVerificationError) as captured:
        _verifier().verify(_headers(NOW, raw), raw)
    assert str(captured.value) == "feishu request verification failed"


def test_signature_rejection_precedes_encrypted_body_decryption(monkeypatch):
    verifier = _verifier()
    raw = encrypted_body({"token": VERIFICATION_TOKEN}, ENCRYPT_KEY)

    def forbidden_decode(*args):
        raise AssertionError("Unverified ciphertext must not be decrypted")

    monkeypatch.setattr(verifier, "_decode_payload", forbidden_decode)
    with pytest.raises(FeishuVerificationError):
        verifier.verify(_headers(NOW, raw, **{"X-Lark-Signature": "bad"}), raw)


@pytest.mark.parametrize("token", ["wrong", "错", "\ud800"])
def test_unsigned_handshake_still_requires_exact_well_formed_token(token):
    raw = json.dumps({"type": "url_verification", "token": token, "challenge": "test"}).encode()
    with pytest.raises(FeishuVerificationError):
        _verifier().verify({}, raw, allow_url_verification=True)
