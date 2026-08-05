import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9_-]{1,64}")


class FeishuOutboundError(Exception):
    def __init__(self) -> None:
        super().__init__("feishu outbound request failed")


class FeishuReceiveIdType(StrEnum):
    CHAT_ID = "chat_id"
    OPEN_ID = "open_id"
    USER_ID = "user_id"
    UNION_ID = "union_id"
    EMAIL = "email"


@dataclass(frozen=True, slots=True)
class FeishuHttpRequest:
    method: Literal["POST"]
    url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes
    timeout: float


@dataclass(frozen=True, slots=True)
class FeishuHttpResponse:
    status_code: int
    body: bytes


@dataclass(frozen=True, slots=True)
class FeishuMessageReceipt:
    message_id: str
    idempotency_key: str


def _urllib_transport(request: FeishuHttpRequest) -> FeishuHttpResponse:
    outgoing = Request(
        request.url,
        data=request.body,
        headers=dict(request.headers),
        method=request.method,
    )
    with urlopen(outgoing, timeout=request.timeout) as response:  # noqa: S310
        return FeishuHttpResponse(
            status_code=response.status,
            body=response.read(),
        )


class FeishuOutboundClient:
    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        base_url: str = "https://open.feishu.cn",
        timeout: int | float = 10,
        transport: Callable[[FeishuHttpRequest], FeishuHttpResponse] | None = None,
    ) -> None:
        if type(app_id) is not str or not app_id:
            raise TypeError("app_id must be a nonempty string")
        if type(app_secret) is not str or not app_secret:
            raise TypeError("app_secret must be a nonempty string")
        if type(base_url) is not str or not base_url:
            raise TypeError("base_url must be a nonempty string")
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be an HTTPS origin")
        if type(timeout) not in (int, float) or timeout <= 0:
            raise TypeError("timeout must be a positive number")
        if transport is not None and not callable(transport):
            raise TypeError("transport must be callable")
        self._app_id = app_id
        self._app_secret = app_secret
        self._base_url = base_url.rstrip("/")
        self._timeout = float(timeout)
        self._transport = transport or _urllib_transport

    def _post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = {"Content-Type": "application/json; charset=utf-8"}
        if headers is not None:
            request_headers.update(headers)
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        request = FeishuHttpRequest(
            method="POST",
            url=f"{self._base_url}{path}",
            headers=tuple(request_headers.items()),
            body=body,
            timeout=self._timeout,
        )
        try:
            response = self._transport(request)
        except Exception:
            raise FeishuOutboundError() from None
        if (
            type(response) is not FeishuHttpResponse
            or type(response.status_code) is not int
            or type(response.body) is not bytes
            or response.status_code != 200
        ):
            raise FeishuOutboundError()
        try:
            decoded = json.loads(response.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise FeishuOutboundError() from None
        if (
            not isinstance(decoded, dict)
            or type(decoded.get("code")) is not int
            or decoded["code"] != 0
        ):
            raise FeishuOutboundError()
        return decoded

    def get_tenant_access_token(self) -> str:
        response = self._post_json(
            "/open-apis/auth/v3/tenant_access_token/internal",
            {"app_id": self._app_id, "app_secret": self._app_secret},
        )
        token = response.get("tenant_access_token")
        if type(token) is not str or not token:
            raise FeishuOutboundError()
        return token

    def _reject_credentials(self, *values: str) -> None:
        credentials = (self._app_id, self._app_secret)
        if any(credential in value for credential in credentials for value in values):
            raise FeishuOutboundError()

    def send_interactive_card(
        self,
        *,
        receive_id: str,
        receive_id_type: FeishuReceiveIdType,
        card: dict[str, object],
        idempotency_key: str,
    ) -> FeishuMessageReceipt:
        if type(receive_id) is not str or not receive_id or len(receive_id) > 128:
            raise TypeError("receive_id must be a nonempty string")
        if type(receive_id_type) is not FeishuReceiveIdType:
            raise TypeError("receive_id_type must be FeishuReceiveIdType")
        if type(card) is not dict:
            raise TypeError("card must be a dict")
        if type(idempotency_key) is not str:
            raise TypeError("idempotency_key must be a string")
        if _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise ValueError("idempotency_key has an invalid format")
        try:
            card_content = json.dumps(
                card,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError):
            raise FeishuOutboundError() from None
        self._reject_credentials(receive_id, idempotency_key, card_content)

        token = self.get_tenant_access_token()
        query = urlencode({"receive_id_type": receive_id_type.value})
        response = self._post_json(
            f"/open-apis/im/v1/messages?{query}",
            {
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": card_content,
                "uuid": idempotency_key,
            },
            headers=MappingProxyType({"Authorization": f"Bearer {token}"}),
        )
        data = response.get("data")
        message_id = data.get("message_id") if isinstance(data, dict) else None
        if type(message_id) is not str or not message_id:
            raise FeishuOutboundError()
        return FeishuMessageReceipt(
            message_id=message_id,
            idempotency_key=idempotency_key,
        )
