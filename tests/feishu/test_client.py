import json

import pytest

from oceanpilot.adapters.feishu.client import (
    FeishuHttpRequest,
    FeishuHttpResponse,
    FeishuOutboundClient,
    FeishuOutboundError,
    FeishuReceiveIdType,
)

APP_ID = "cli_synthetic_app_id"
APP_SECRET = "synthetic-app-secret"
TOKEN = "t-synthetic-tenant-token"


class _ScriptedTransport:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.requests: list[FeishuHttpRequest] = []

    def __call__(self, request: FeishuHttpRequest) -> FeishuHttpResponse:
        self.requests.append(request)
        response = next(self._responses)
        if isinstance(response, BaseException):
            raise response
        return response


def _response(payload: object, status: int = 200) -> FeishuHttpResponse:
    return FeishuHttpResponse(
        status_code=status,
        body=json.dumps(payload, separators=(",", ":")).encode(),
    )


def _client(transport) -> FeishuOutboundClient:
    return FeishuOutboundClient(
        app_id=APP_ID,
        app_secret=APP_SECRET,
        base_url="https://open.feishu.test",
        timeout=5,
        transport=transport,
    )


def test_get_tenant_access_token_internal_uses_injected_credentials():
    transport = _ScriptedTransport(
        [_response({"code": 0, "tenant_access_token": TOKEN, "expire": 7200})]
    )

    assert _client(transport).get_tenant_access_token() == TOKEN
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url == (
        "https://open.feishu.test/open-apis/auth/v3/tenant_access_token/internal"
    )
    assert dict(request.headers) == {"Content-Type": "application/json; charset=utf-8"}
    assert json.loads(request.body) == {"app_id": APP_ID, "app_secret": APP_SECRET}
    assert request.timeout == 5.0


def test_interactive_card_send_uses_token_and_stable_idempotency_key():
    transport = _ScriptedTransport(
        [
            _response({"code": 0, "tenant_access_token": TOKEN, "expire": 7200}),
            _response({"code": 0, "data": {"message_id": "om_001"}}),
            _response({"code": 0, "tenant_access_token": TOKEN, "expire": 7200}),
            _response({"code": 0, "data": {"message_id": "om_001"}}),
        ]
    )
    client = _client(transport)
    card = {"schema": "2.0", "body": {"elements": []}}

    first = client.send_interactive_card(
        receive_id="oc_synthetic_chat",
        receive_id_type=FeishuReceiveIdType.CHAT_ID,
        card=card,
        idempotency_key="case-001-diagnosis-005",
    )
    second = client.send_interactive_card(
        receive_id="oc_synthetic_chat",
        receive_id_type=FeishuReceiveIdType.CHAT_ID,
        card=card,
        idempotency_key="case-001-diagnosis-005",
    )

    assert first == second
    assert first.message_id == "om_001"
    assert first.idempotency_key == "case-001-diagnosis-005"
    for request in (transport.requests[1], transport.requests[3]):
        assert request.url == (
            "https://open.feishu.test/open-apis/im/v1/messages?receive_id_type=chat_id"
        )
        assert dict(request.headers) == {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json; charset=utf-8",
        }
        body = json.loads(request.body)
        assert body == {
            "receive_id": "oc_synthetic_chat",
            "msg_type": "interactive",
            "content": json.dumps(
                card,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            "uuid": "case-001-diagnosis-005",
        }


@pytest.mark.parametrize(
    "responses",
    [
        [RuntimeError(f"network leaked {APP_SECRET}")],
        [_response({"code": 10003, "msg": f"invalid {APP_SECRET}"})],
        [_response({"code": 0, "tenant_access_token": APP_SECRET}, status=500)],
        [_response({"code": 0, "tenant_access_token": ""})],
    ],
)
def test_token_failures_use_one_safe_error_without_logs(responses, caplog):
    with pytest.raises(FeishuOutboundError) as captured:
        _client(_ScriptedTransport(responses)).get_tenant_access_token()
    assert str(captured.value) == "feishu outbound request failed"
    assert APP_SECRET not in str(captured.value)
    assert caplog.records == []


def test_message_failure_never_echoes_token_or_response_body():
    transport = _ScriptedTransport(
        [
            _response({"code": 0, "tenant_access_token": TOKEN}),
            _response({"code": 999, "msg": f"failed with {TOKEN}"}),
        ]
    )
    with pytest.raises(FeishuOutboundError) as captured:
        _client(transport).send_interactive_card(
            receive_id="oc_synthetic_chat",
            receive_id_type=FeishuReceiveIdType.CHAT_ID,
            card={"schema": "2.0"},
            idempotency_key="case-001-diagnosis-005",
        )
    assert str(captured.value) == "feishu outbound request failed"
    assert TOKEN not in str(captured.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"app_id": ""},
        {"app_secret": ""},
        {"app_id": 1},
        {"timeout": True},
        {"base_url": "http://open.feishu.test"},
    ],
)
def test_constructor_inputs_are_strict(changes):
    arguments = {
        "app_id": APP_ID,
        "app_secret": APP_SECRET,
        "base_url": "https://open.feishu.test",
        "timeout": 5,
        "transport": _ScriptedTransport([]),
    }
    arguments.update(changes)
    with pytest.raises((TypeError, ValueError)):
        FeishuOutboundClient(**arguments)


def test_card_payload_cannot_contain_injected_credentials():
    transport = _ScriptedTransport([])
    with pytest.raises(FeishuOutboundError):
        _client(transport).send_interactive_card(
            receive_id="oc_synthetic_chat",
            receive_id_type=FeishuReceiveIdType.CHAT_ID,
            card={"content": APP_SECRET},
            idempotency_key="case-001-diagnosis-005",
        )
    assert transport.requests == []


def test_send_inputs_are_strict_and_closed():
    client = _client(_ScriptedTransport([]))
    with pytest.raises(TypeError):
        client.send_interactive_card(
            receive_id="oc_synthetic_chat",
            receive_id_type="chat_id",
            card={"schema": "2.0"},
            idempotency_key="case-001-diagnosis-005",
        )
    with pytest.raises(ValueError):
        client.send_interactive_card(
            receive_id="oc_synthetic_chat",
            receive_id_type=FeishuReceiveIdType.CHAT_ID,
            card={"schema": "2.0"},
            idempotency_key="contains spaces",
        )


def test_reply_card_uses_official_thread_reply_contract_and_stable_uuid():
    transport = _ScriptedTransport(
        [
            _response({"code": 0, "tenant_access_token": TOKEN}),
            _response({"code": 0, "data": {"message_id": "om_reply"}}),
        ]
    )
    receipt = _client(transport).reply_interactive_card(
        message_id="om_parent", card={"elements": []}, idempotency_key="stable-reply-uuid"
    )
    request = transport.requests[-1]
    assert request.method == "POST"
    assert request.url.endswith("/im/v1/messages/om_parent/reply")
    assert json.loads(request.body) == {
        "content": '{"elements":[]}',
        "msg_type": "interactive",
        "reply_in_thread": True,
        "uuid": "stable-reply-uuid",
    }
    assert receipt.message_id == "om_reply"


def test_update_card_uses_patch_and_does_not_invent_provider_idempotency_parameter():
    transport = _ScriptedTransport(
        [
            _response({"code": 0, "tenant_access_token": TOKEN}),
            _response({"code": 0}),
        ]
    )
    receipt = _client(transport).update_interactive_card(
        message_id="om_existing", card={"elements": []}, idempotency_key="local-update-id"
    )
    request = transport.requests[-1]
    assert request.method == "PATCH"
    assert request.url.endswith("/im/v1/messages/om_existing")
    assert json.loads(request.body) == {"content": '{"elements":[]}'}
    assert receipt.message_id == "om_existing"


@pytest.mark.parametrize("method", ["reply_interactive_card", "update_interactive_card"])
@pytest.mark.parametrize("message_id", ["../other", "om_id?foo=bar", "", "om_id/unsafe"])
def test_reply_and_patch_reject_unsafe_message_paths_without_network(method, message_id):
    transport = _ScriptedTransport([])
    with pytest.raises(ValueError):
        getattr(_client(transport), method)(message_id=message_id, card={}, idempotency_key="key")
    assert not transport.requests


@pytest.mark.parametrize("method", ["reply_interactive_card", "update_interactive_card"])
def test_reply_and_patch_never_send_configured_credentials_in_card(method):
    transport = _ScriptedTransport([])
    with pytest.raises(FeishuOutboundError):
        getattr(_client(transport), method)(
            message_id="om_safe", card={"text": APP_SECRET}, idempotency_key="key"
        )
    assert not transport.requests
