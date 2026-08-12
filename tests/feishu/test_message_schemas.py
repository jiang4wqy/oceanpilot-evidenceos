import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from oceanpilot.api.feishu_schemas import parse_feishu_message_event


def _message_payload() -> dict[str, object]:
    fixture = Path(__file__).with_name("fixtures") / "message_received.json"
    return json.loads(
        fixture.read_text(encoding="utf-8")
        .replace("__VERIFICATION_TOKEN__", "synthetic-token")
        .replace("__APP_ID__", "cli_synthetic_app")
    )


def test_verified_v2_group_text_message_has_safe_typed_view():
    callback = parse_feishu_message_event(_message_payload())

    assert callback.schema_version == "2.0"
    assert callback.header.event_type == "im.message.receive_v1"
    assert callback.event.sender.sender_type == "user"
    assert callback.event.message.content.text == (
        "Synthetic 3DS callback was not received"
    )
    assert callback.event.message.root_id == "om_thread_001"
    assert callback.event.message.mentions == ()


def test_real_mention_shape_is_preserved_as_a_strict_typed_value():
    payload = _message_payload()
    payload["event"]["message"]["mentions"] = [  # type: ignore[index]
        {
            "key": "@_user_1",
            "id": {"open_id": "ou_mentioned_user"},
            "name": "Synthetic Operator",
            "tenant_key": "tenant_demo",
        }
    ]

    callback = parse_feishu_message_event(payload)

    mention = callback.event.message.mentions[0]
    assert mention.key == "@_user_1"
    assert mention.id.open_id == "ou_mentioned_user"
    assert mention.name == "Synthetic Operator"


@pytest.mark.parametrize("sender_type", ("user", "app"))
def test_only_supported_sender_types_are_structurally_accepted(sender_type):
    payload = _message_payload()
    payload["event"]["sender"]["sender_type"] = sender_type  # type: ignore[index]

    callback = parse_feishu_message_event(payload)

    assert callback.event.sender.sender_type == sender_type


def test_thread_identifiers_default_to_empty_strings():
    payload = _message_payload()
    del payload["event"]["message"]["root_id"]  # type: ignore[index]
    del payload["event"]["message"]["parent_id"]  # type: ignore[index]

    callback = parse_feishu_message_event(payload)

    assert callback.event.message.root_id == ""
    assert callback.event.message.parent_id == ""


@pytest.mark.parametrize(
    ("path", "invalid_value"),
    (
        (("schema",), "1.0"),
        (("header", "event_type"), "im.message.recalled_v1"),
        (("header", "create_time"), "178625000000"),
        (("header", "event_id"), "evt/message"),
        (("event", "sender", "sender_type"), "bot"),
        (("event", "message", "chat_type"), "p2p"),
        (("event", "message", "message_type"), "image"),
        (("event", "message", "create_time"), 1786250000000),
    ),
)
def test_protocol_discriminator_and_identifier_constraints_are_exact(
    path,
    invalid_value,
):
    payload = _message_payload()
    target = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index,assignment]
    target[path[-1]] = invalid_value  # type: ignore[index]

    with pytest.raises(ValidationError):
        parse_feishu_message_event(payload)


def test_sender_tenant_must_match_header_tenant():
    payload = _message_payload()
    payload["event"]["sender"]["tenant_key"] = "tenant_other"  # type: ignore[index]

    with pytest.raises(ValidationError):
        parse_feishu_message_event(payload)


@pytest.mark.parametrize(
    "invalid_content",
    (
        '["text"]',
        '{"text":"ok","extra":"CONTENT-EXTRA-SENTINEL"}',
        {"text": "CONTENT-DICT-SENTINEL"},
        '{"text":17}',
        '{"text":"   "}',
        '{"text":{"text":"CONTENT-RECURSIVE-SENTINEL"}}',
    ),
)
def test_content_is_exactly_one_safe_nonempty_text_object(invalid_content):
    payload = _message_payload()
    payload["event"]["message"]["content"] = invalid_content  # type: ignore[index]

    with pytest.raises(ValidationError) as captured:
        parse_feishu_message_event(payload)

    assert "SENTINEL" not in str(captured.value)


def test_content_is_stripped_before_enforcing_the_500_character_limit():
    payload = _message_payload()
    payload["event"]["message"]["content"] = json.dumps(  # type: ignore[index]
        {"text": f"  {'x' * 500}  "}
    )

    callback = parse_feishu_message_event(payload)

    assert callback.event.message.content.text == "x" * 500


@pytest.mark.parametrize(
    ("container_path", "extra_key"),
    (
        ((), "top_extra"),
        (("header",), "header_extra"),
        (("event",), "event_extra"),
        (("event", "sender"), "sender_extra"),
        (("event", "sender", "sender_id"), "sender_id_extra"),
        (("event", "message"), "message_extra"),
    ),
)
def test_every_callback_layer_forbids_unknown_fields(container_path, extra_key):
    payload = deepcopy(_message_payload())
    target = payload
    for key in container_path:
        target = target[key]  # type: ignore[index,assignment]
    target[extra_key] = "EXTRA-LAYER-SENTINEL"  # type: ignore[index]

    with pytest.raises(ValidationError) as captured:
        parse_feishu_message_event(payload)

    assert "EXTRA-LAYER-SENTINEL" not in str(captured.value)


def test_callback_models_are_frozen():
    callback = parse_feishu_message_event(_message_payload())

    with pytest.raises(ValidationError):
        callback.event.message.content.text = "changed"
