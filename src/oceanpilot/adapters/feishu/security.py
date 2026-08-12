import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from typing import Any


class FeishuVerificationError(Exception):
    def __init__(self) -> None:
        super().__init__("feishu request verification failed")


class FeishuRequestVerifier:
    def __init__(
        self,
        *,
        encrypt_key: str,
        verification_token: str,
        now: Callable[[], int],
    ) -> None:
        if type(encrypt_key) is not str or not encrypt_key:
            raise TypeError("encrypt_key must be a nonempty string")
        if type(verification_token) is not str or not verification_token:
            raise TypeError("verification_token must be a nonempty string")
        if not callable(now):
            raise TypeError("now must be callable")
        self._encrypt_key = encrypt_key
        self._verification_token = verification_token
        self._now = now

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str:
        expected = name.lower()
        matches: list[str] = []
        for key, value in headers.items():
            if type(key) is not str or type(value) is not str:
                raise FeishuVerificationError()
            if key.lower() == expected:
                matches.append(value)
        if len(matches) != 1 or not matches[0]:
            raise FeishuVerificationError()
        return matches[0]

    @staticmethod
    def _payload_token(payload: dict[str, Any]) -> object:
        if "token" in payload:
            return payload["token"]
        header = payload.get("header")
        if isinstance(header, dict):
            return header.get("token")
        return None

    def verify(
        self,
        headers: Mapping[str, str],
        raw_body: bytes,
    ) -> dict[str, Any]:
        if type(raw_body) is not bytes:
            raise TypeError("raw_body must be bytes")
        if not isinstance(headers, Mapping):
            raise TypeError("headers must be a mapping")

        timestamp_text = self._header(headers, "X-Lark-Request-Timestamp")
        nonce = self._header(headers, "X-Lark-Request-Nonce")
        supplied_signature = self._header(headers, "X-Lark-Signature")
        if (
            len(timestamp_text) > 20
            or not timestamp_text.isascii()
            or not timestamp_text.isdecimal()
        ):
            raise FeishuVerificationError()
        try:
            timestamp = int(timestamp_text)
        except ValueError:
            raise FeishuVerificationError() from None
        current = self._now()
        if type(current) is not int or abs(current - timestamp) > 300:
            raise FeishuVerificationError()

        prefix = f"{timestamp_text}{nonce}{self._encrypt_key}".encode()
        expected_signature = hashlib.sha256(prefix + raw_body).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise FeishuVerificationError()

        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
            raise FeishuVerificationError() from None
        if not isinstance(payload, dict):
            raise FeishuVerificationError()
        supplied_token = self._payload_token(payload)
        if type(supplied_token) is not str or not hmac.compare_digest(
            supplied_token,
            self._verification_token,
        ):
            raise FeishuVerificationError()
        return payload
