"""Signed live card timestamp shape, without real credentials or callback bodies."""

import hashlib
from datetime import datetime

import pytest

from oceanpilot.adapters.feishu.security import FeishuRequestVerifier, FeishuVerificationError
from tests.feishu.crypto_helpers import encrypted_body

STAMP = "2026-09-15 17:36:47.660764037 +0800 CST m=+439285.172981143"
NOW = int(datetime.fromisoformat("2026-09-15T09:36:47+00:00").timestamp())


def request(stamp=STAMP, *, event="card.action.trigger", token="test-token"):
    payload = {"schema": "2.0", "header": {"event_type": event, "token": token}, "event": {}}
    body = encrypted_body(payload, "test-key")
    signature = hashlib.sha256((stamp + "nonce" + "test-key").encode() + body).hexdigest()
    return {
        "X-Lark-Request-Timestamp": stamp,
        "X-Lark-Request-Nonce": "nonce",
        "X-Lark-Signature": signature,
    }, body


def verifier(now=NOW):
    return FeishuRequestVerifier(
        encrypt_key="test-key", verification_token="test-token", now=lambda: now
    )


@pytest.mark.parametrize("age", [-300, 0, 300])
def test_signed_card_wall_clock_format_keeps_five_minute_window(age):
    payload = verifier(NOW + age).verify(*request(), allow_card_timestamp=True)
    assert payload["header"]["event_type"] == "card.action.trigger"


@pytest.mark.parametrize("age", [-301, 301])
def test_old_or_future_signed_card_is_rejected(age):
    with pytest.raises(FeishuVerificationError):
        verifier(NOW + age).verify(*request(), allow_card_timestamp=True)


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-09-15 17:36:47 +0800 CST",
        "2026-09-15 09:36:47.1 +0000 UTC",
    ],
)
def test_timezone_offset_and_optional_fraction_monotonic_suffix(stamp):
    assert verifier().verify(*request(stamp), allow_card_timestamp=True)["schema"] == "2.0"


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-09-15 17:36:47 CST",
        "2026-09-15 17:36:47 +2500 CST",
        "2026-09-15 17:36:47 +0800 CST garbage",
        "2026-02-31 17:36:47 +0800 CST",
        "2026-09-15 17:36:47 +0800 CST m=+NaN",
        "0",
        str(NOW * 1000),
        "９" * 10,
    ],
)
def test_invalid_timestamp_cannot_bypass_age_check(stamp):
    with pytest.raises(FeishuVerificationError):
        verifier().verify(*request(stamp), allow_card_timestamp=True)


def test_extended_timestamp_is_opt_in_and_only_for_v2_card_payload():
    with pytest.raises(FeishuVerificationError):
        verifier().verify(*request())
    with pytest.raises(FeishuVerificationError):
        verifier().verify(*request(event="im.message.receive_v1"), allow_card_timestamp=True)


def test_signature_covers_original_timestamp_and_body_and_token_still_required():
    headers, body = request()
    headers["X-Lark-Request-Timestamp"] = STAMP.replace(".660764037", "")
    with pytest.raises(FeishuVerificationError):
        verifier().verify(headers, body, allow_card_timestamp=True)
    with pytest.raises(FeishuVerificationError):
        verifier().verify(*request(token="wrong"), allow_card_timestamp=True)


def test_bad_signature_is_rejected_before_decrypting(monkeypatch):
    instance = verifier()

    def forbidden(*args):
        raise AssertionError("Must authenticate bytes before decrypting")

    monkeypatch.setattr(instance, "_decode_payload", forbidden)
    headers, body = request()
    headers["X-Lark-Signature"] = "0" * 64
    with pytest.raises(FeishuVerificationError):
        instance.verify(headers, body, allow_card_timestamp=True)
