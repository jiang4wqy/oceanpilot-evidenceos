import base64
import binascii
import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


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
        *,
        allow_url_verification: bool = False,
        allow_card_timestamp: bool = False,
    ) -> dict[str, Any]:
        if type(raw_body) is not bytes:
            raise TypeError("raw_body must be bytes")
        if not isinstance(headers, Mapping):
            raise TypeError("headers must be a mapping")

        signing_headers = {"x-lark-request-timestamp", "x-lark-request-nonce", "x-lark-signature"}
        if any(type(key) is not str or type(value) is not str for key, value in headers.items()):
            raise FeishuVerificationError()
        unsigned_challenge = allow_url_verification and not any(
            key.lower() in signing_headers for key in headers
        )
        if not unsigned_challenge:
            # Normal events authenticate the exact encrypted HTTP body before parsing/decryption.
            self._verify_signature(headers, raw_body, allow_card_timestamp=allow_card_timestamp)
        payload = self._decode_payload(raw_body)
        if not unsigned_challenge:
            timestamp = self._header(headers, "X-Lark-Request-Timestamp")
            if not timestamp.isdecimal() and (
                payload.get("schema") != "2.0"
                or not isinstance(payload.get("header"), dict)
                or payload["header"].get("event_type") != "card.action.trigger"
            ):
                raise FeishuVerificationError()
        if unsigned_challenge and payload.get("type") != "url_verification":
            raise FeishuVerificationError()
        supplied_token = self._payload_token(payload)
        if type(supplied_token) is not str:
            raise FeishuVerificationError()
        try:
            token_matches = hmac.compare_digest(
                supplied_token.encode(), self._verification_token.encode()
            )
        except UnicodeError:
            raise FeishuVerificationError() from None
        if not token_matches:
            raise FeishuVerificationError()
        return payload

    def _verify_signature(
        self, headers: Mapping[str, str], raw_body: bytes, *, allow_card_timestamp: bool = False
    ) -> None:
        timestamp_text = self._header(headers, "X-Lark-Request-Timestamp")
        nonce = self._header(headers, "X-Lark-Request-Nonce")
        supplied_signature = self._header(headers, "X-Lark-Signature")
        if (
            len(timestamp_text) > 100
            or not timestamp_text.isascii()
            or not supplied_signature.isascii()
        ):
            raise FeishuVerificationError()
        # Always authenticate the verbatim header and HTTP bytes, never a
        # normalized timestamp. Observed signed card callbacks use Go Time.String
        # while message events use Unix seconds. No legacy SHA-1 fallback.
        prefix = f"{timestamp_text}{nonce}{self._encrypt_key}".encode()
        expected_signature = hashlib.sha256(prefix + raw_body).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise FeishuVerificationError()
        timestamp = self._timestamp(timestamp_text, allow_card_timestamp=allow_card_timestamp)
        current = self._now()
        if type(current) is not int or abs(current - timestamp) > 300:
            raise FeishuVerificationError()

    @staticmethod
    def _timestamp(value: str, *, allow_card_timestamp: bool) -> int:
        if value.isdecimal() and len(value) <= 20:
            return int(value)
        if allow_card_timestamp:
            match = re.fullmatch(
                r"(?P<wall>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
                r"(?:\.\d{1,9})? (?P<offset>[+-]\d{4}) [A-Za-z]{1,10}"
                r"(?: m=[+-]\d{1,20}(?:\.\d{1,9})?)?",
                value,
                flags=re.ASCII,
            )
            if match:
                try:
                    # Numeric UTC offset is authoritative. Go's process-relative
                    # monotonic suffix cannot measure cross-machine request age.
                    wall = datetime.strptime(
                        match["wall"] + " " + match["offset"], "%Y-%m-%d %H:%M:%S %z"
                    )
                    return int(wall.timestamp())
                except (ValueError, OverflowError, OSError):
                    pass
        raise FeishuVerificationError()

    def _decode_payload(self, raw_body: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(raw_body)
            if not isinstance(payload, dict):
                raise FeishuVerificationError()
            if "encrypt" in payload:
                # Feishu: base64(16-byte IV + AES-256-CBC ciphertext), SHA256(Encrypt Key).
                if set(payload) != {"encrypt"} or type(payload["encrypt"]) is not str:
                    raise FeishuVerificationError()
                wire = base64.b64decode(payload["encrypt"], validate=True)
                if len(wire) < 32 or len(wire) % 16:
                    raise FeishuVerificationError()
                key = hashlib.sha256(self._encrypt_key.encode()).digest()
                decryptor = Cipher(algorithms.AES(key), modes.CBC(wire[:16])).decryptor()
                padded = decryptor.update(wire[16:]) + decryptor.finalize()
                unpadder = padding.PKCS7(128).unpadder()
                plaintext = unpadder.update(padded) + unpadder.finalize()
                payload = json.loads(plaintext.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, binascii.Error, RecursionError):
            raise FeishuVerificationError() from None
        if not isinstance(payload, dict):
            raise FeishuVerificationError()
        return payload
