from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.adapters.redaction import RegexRedactor
from oceanpilot.application.model_provider import (
    ModelMessage,
    ModelResult,
    ModelRole,
    RoutingModelProvider,
    SecurityTier,
    TaskSpec,
)
from oceanpilot.application.redaction import RedactingModelProvider, Redactor

_CARD = "4111 1111 1111 1111"


def test_regex_redactor_masks_card_email_phone():
    redactor = RegexRedactor()
    assert redactor.redact(f"card {_CARD} ok") == "card [REDACTED:CARD] ok"
    assert redactor.redact("mail a.b+x@shop.co") == "mail [REDACTED:EMAIL]"
    assert redactor.redact("call +1 415 555 1234") == "call [REDACTED:PHONE]"
    assert redactor.redact("no pii here") == "no pii here"


def test_regex_redactor_satisfies_protocol():
    assert isinstance(RegexRedactor(), Redactor)


def _msg(text: str):
    return [ModelMessage(role=ModelRole.USER, content=text)]


def test_redacting_provider_strips_pii_before_delegating():
    inner = ScriptedModelProvider(["ok"])
    provider = RedactingModelProvider(inner, RegexRedactor())

    result = provider.complete(
        TaskSpec(kind="k", security_tier=SecurityTier.MEDIUM),
        _msg(f"客户卡号 {_CARD} 请处理"),
        system=f"账号 {_CARD}",
    )

    assert result == ModelResult(text="ok")
    sent = inner.requests[0]
    assert "[REDACTED:CARD]" in sent.messages[0].content
    assert _CARD not in sent.messages[0].content
    assert "[REDACTED:CARD]" in sent.system
    assert _CARD not in sent.system


def test_router_redacts_for_medium_but_not_for_low():
    external = ScriptedModelProvider(default_text="x")
    router = RoutingModelProvider(
        {
            SecurityTier.MEDIUM: RedactingModelProvider(external, RegexRedactor()),
            SecurityTier.LOW: external,
        }
    )

    router.complete(TaskSpec(kind="k", security_tier=SecurityTier.MEDIUM), _msg(_CARD))
    router.complete(TaskSpec(kind="k", security_tier=SecurityTier.LOW), _msg(_CARD))

    medium_seen, low_seen = external.requests[0], external.requests[1]
    assert _CARD not in medium_seen.messages[0].content  # redacted
    assert _CARD in low_seen.messages[0].content  # non-sensitive, sent as-is
