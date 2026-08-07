import json

import pytest

from oceanpilot.adapters.channels.feishu.channel import FeishuChannel
from oceanpilot.adapters.channels.http.channel import HttpChannel
from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.adapters.persistence.chargeback_memory import InMemoryChargebackCaseStore
from oceanpilot.application.channels import (
    Channel,
    Delivery,
    DeliveryAssessment,
    InboundKind,
    NormalizedInbound,
)
from oceanpilot.application.chargeback_agents import (
    ChargebackAssessAgent,
    EvidenceAgent,
    IntakeAgent,
)
from oceanpilot.application.chargeback_channel_service import ChargebackChannelService
from oceanpilot.application.chargeback_supervisor import ChargebackSupervisor
from oceanpilot.application.errors import CaseNotFound, InvalidInbound
from oceanpilot.domain.chargeback import DisputeReasonCode, required_evidence_for


def _service() -> ChargebackChannelService:
    model = ScriptedModelProvider(default_text="（合成）")
    supervisor = ChargebackSupervisor(
        intake=IntakeAgent(model),
        evidence=EvidenceAgent(model),
        assess=ChargebackAssessAgent(model),
    )
    return ChargebackChannelService(supervisor, InMemoryChargebackCaseStore())


def test_adapters_satisfy_the_channel_protocol():
    assert isinstance(HttpChannel(), Channel)
    assert isinstance(FeishuChannel(), Channel)


def test_open_case_via_service_classifies_and_asks_for_evidence():
    service = _service()
    delivery = service.handle(
        NormalizedInbound(
            kind=InboundKind.OPEN_CASE, channel="test", description="客户下单后一直没收到货"
        )
    )
    assert delivery.case_id
    assert delivery.reason_code == DisputeReasonCode.PRODUCT_NOT_RECEIVED.value
    assert delivery.phase == "NEED_EVIDENCE"
    assert delivery.next_evidence in (delivery.missing or ())


def test_same_normalized_inbound_is_channel_independent():
    """The core result depends on the NormalizedInbound, not the channel that
    produced it: parsing the HTTP and Feishu wire forms yields the same inbound
    (modulo channel tag), and the service returns equivalent deliveries."""
    http_raw = {"action": "open_case", "description": "没收到货，要拒付"}
    feishu_raw = {
        "event": {"message": {"content": '{"text": "没收到货，要拒付"}'}},
    }
    http_inbound = HttpChannel().parse_inbound(http_raw)
    feishu_inbound = FeishuChannel().parse_inbound(feishu_raw)

    assert http_inbound.kind is InboundKind.OPEN_CASE
    assert feishu_inbound.kind is InboundKind.OPEN_CASE
    assert http_inbound.description == feishu_inbound.description

    d1 = _service().handle(http_inbound)
    d2 = _service().handle(feishu_inbound)
    # Case ids differ (separate stores); everything decision-relevant matches.
    assert (d1.reason_code, d1.phase, d1.next_evidence, d1.missing) == (
        d2.reason_code,
        d2.phase,
        d2.next_evidence,
        d2.missing,
    )


def test_full_evidence_flow_through_the_service_reaches_assessment():
    service = _service()
    reason = DisputeReasonCode.PRODUCT_NOT_RECEIVED
    delivery = service.handle(
        NormalizedInbound(
            kind=InboundKind.OPEN_CASE, channel="test", description="没收到货，要拒付"
        )
    )
    case_id = delivery.case_id
    for _ in range(20):
        if delivery.phase == "ASSESSED":
            break
        delivery = service.handle(
            NormalizedInbound(
                kind=InboundKind.SUBMIT_EVIDENCE,
                channel="test",
                case_id=case_id,
                evidence_code=delivery.next_evidence,
            )
        )
    assert delivery.phase == "ASSESSED"
    assert delivery.assessment is not None
    assert delivery.assessment.win_likelihood == "1.0000"
    assert set(delivery.collected) == {c.value for c in required_evidence_for(reason)}


def test_get_unknown_case_raises_case_not_found():
    with pytest.raises(CaseNotFound):
        _service().handle(
            NormalizedInbound(kind=InboundKind.GET_CASE, channel="test", case_id="missing")
        )


@pytest.mark.parametrize(
    "inbound",
    [
        NormalizedInbound(kind=InboundKind.OPEN_CASE, channel="test"),  # no description
        NormalizedInbound(kind=InboundKind.SUBMIT_EVIDENCE, channel="test", case_id="c"),  # no code
        NormalizedInbound(
            kind=InboundKind.SUBMIT_EVIDENCE, channel="test", case_id="c", evidence_code="nope"
        ),
        NormalizedInbound(kind=InboundKind.GET_CASE, channel="test"),  # no case_id
    ],
)
def test_invalid_inbound_is_rejected(inbound):
    with pytest.raises(InvalidInbound):
        _service().handle(inbound)


# -- HTTP channel adapter ---------------------------------------------------


def test_http_channel_parses_each_action():
    channel = HttpChannel()
    assert channel.parse_inbound({"action": "open_case", "description": "d"}).kind is (
        InboundKind.OPEN_CASE
    )
    submit = channel.parse_inbound(
        {"action": "submit_evidence", "case_id": "c1", "evidence_code": "transaction.receipt"}
    )
    assert submit.kind is InboundKind.SUBMIT_EVIDENCE
    assert submit.case_id == "c1"
    assert submit.evidence_code == "transaction.receipt"
    assert channel.parse_inbound({"action": "get_case", "case_id": "c1"}).kind is (
        InboundKind.GET_CASE
    )


def test_http_channel_rejects_unknown_action():
    with pytest.raises(InvalidInbound):
        HttpChannel().parse_inbound({"action": "delete_everything"})
    with pytest.raises(InvalidInbound):
        HttpChannel().parse_inbound({"description": "no action key"})


def test_http_channel_renders_delivery_as_json():
    delivery = Delivery(
        case_id="c1",
        phase="ASSESSED",
        reason_code="PRODUCT_NOT_RECEIVED",
        collected=("transaction.receipt",),
        assessment=DeliveryAssessment(
            win_likelihood="1.0000",
            completeness="1.0000",
            responsible_team="BUSINESS",
            requires_human=False,
            review_reasons=(),
            explanation="ok",
        ),
    )
    out = HttpChannel().render(delivery)
    assert out["channel"] == "http"
    assert out["case_id"] == "c1"
    assert out["collected"] == ["transaction.receipt"]
    assert out["assessment"]["win_likelihood"] == "1.0000"
    assert out["assessment"]["requires_human"] is False


# -- Feishu channel adapter -------------------------------------------------


def test_feishu_channel_parses_card_action():
    raw = {
        "action": {
            "value": {
                "action": "submit_evidence",
                "case_id": "c1",
                "evidence_code": "fulfillment.tracking",
            }
        }
    }
    inbound = FeishuChannel().parse_inbound(raw)
    assert inbound.kind is InboundKind.SUBMIT_EVIDENCE
    assert inbound.channel == "feishu"
    assert inbound.case_id == "c1"
    assert inbound.evidence_code == "fulfillment.tracking"


def test_feishu_channel_parses_message_as_open_case_with_actor():
    raw = {
        "event": {
            "message": {"content": '{"text": "  没收到货  "}'},
            "sender": {"sender_id": {"open_id": "ou_123"}},
        }
    }
    inbound = FeishuChannel().parse_inbound(raw)
    assert inbound.kind is InboundKind.OPEN_CASE
    assert inbound.description == "没收到货"
    assert inbound.actor == "ou_123"


def test_feishu_channel_rejects_unparseable_input():
    with pytest.raises(InvalidInbound):
        FeishuChannel().parse_inbound({"action": {"value": {"action": "nope"}}})
    with pytest.raises(InvalidInbound):
        FeishuChannel().parse_inbound({"event": {"message": {"content": "not-json"}}})
    with pytest.raises(InvalidInbound):
        FeishuChannel().parse_inbound({})


def test_feishu_channel_renders_need_evidence_card_with_action_button():
    delivery = Delivery(
        case_id="c1",
        phase="NEED_EVIDENCE",
        reason_code="PRODUCT_NOT_RECEIVED",
        collected=(),
        next_evidence="fulfillment.tracking",
        question="请提供物流单号",
        missing=("fulfillment.tracking",),
    )
    card = FeishuChannel().render(delivery)
    assert card["header"]["title"]["content"] == "跨境拒付案件"
    actions = [e for e in card["elements"] if e.get("tag") == "action"]
    assert len(actions) == 1
    button = actions[0]["actions"][0]
    assert button["value"] == {
        "action": "submit_evidence",
        "case_id": "c1",
        "evidence_code": "fulfillment.tracking",
    }


# --- reason confirmation flow (P0-3) ---------------------------------------

_UNCLEAR = "这是一段用于测试的中性内容"


def _open_unclear(service: ChargebackChannelService, channel: str = "test") -> Delivery:
    return service.handle(
        NormalizedInbound(kind=InboundKind.OPEN_CASE, channel=channel, description=_UNCLEAR)
    )


def test_unconfident_open_case_asks_to_confirm_reason():
    delivery = _open_unclear(_service())
    assert delivery.phase == "REASON_PROPOSED"
    assert delivery.reason_confirmed is False
    assert delivery.reason_code is not None
    assert delivery.question  # a confirm prompt is shown
    assert delivery.next_evidence is None


def test_confirming_reason_advances_to_evidence():
    service = _service()
    opened = _open_unclear(service)
    confirmed = service.handle(
        NormalizedInbound(kind=InboundKind.CONFIRM_REASON, channel="test", case_id=opened.case_id)
    )
    assert confirmed.reason_confirmed is True
    assert confirmed.phase == "NEED_EVIDENCE"


def test_confirming_with_a_correction_changes_the_reason():
    service = _service()
    opened = _open_unclear(service)
    confirmed = service.handle(
        NormalizedInbound(
            kind=InboundKind.CONFIRM_REASON,
            channel="test",
            case_id=opened.case_id,
            reason_code=DisputeReasonCode.FRAUD_CARD_NOT_PRESENT.value,
        )
    )
    assert confirmed.reason_code == DisputeReasonCode.FRAUD_CARD_NOT_PRESENT.value
    assert confirmed.reason_confirmed is True
    assert confirmed.phase == "NEED_EVIDENCE"


def test_confirm_with_unknown_reason_is_rejected():
    service = _service()
    opened = _open_unclear(service)
    with pytest.raises(InvalidInbound):
        service.handle(
            NormalizedInbound(
                kind=InboundKind.CONFIRM_REASON,
                channel="test",
                case_id=opened.case_id,
                reason_code="NOT_A_REASON",
            )
        )


def test_feishu_renders_a_confirm_button_for_reason_proposed():
    opened = _open_unclear(_service(), channel="feishu")
    card = FeishuChannel().render(opened)
    serialized = json.dumps(card, ensure_ascii=False)
    assert "confirm_reason" in serialized
    assert "确认该原因" in serialized


def test_finalize_evidence_routes_to_assessment():
    service = _service()
    opened = service.handle(
        NormalizedInbound(
            kind=InboundKind.OPEN_CASE, channel="test", description="没收到货，要拒付"
        )
    )
    assert opened.phase == "NEED_EVIDENCE"
    final = service.handle(
        NormalizedInbound(
            kind=InboundKind.FINALIZE_EVIDENCE, channel="test", case_id=opened.case_id
        )
    )
    assert final.collection_finalized is True
    assert final.phase == "ASSESSED"
    assert final.assessment is not None
    assert final.assessment.requires_human is True


def test_finalize_without_case_id_is_rejected():
    with pytest.raises(InvalidInbound):
        _service().handle(NormalizedInbound(kind=InboundKind.FINALIZE_EVIDENCE, channel="test"))


def test_feishu_evidence_card_offers_a_finalize_button():
    service = _service()
    opened = service.handle(
        NormalizedInbound(
            kind=InboundKind.OPEN_CASE, channel="feishu", description="没收到货，要拒付"
        )
    )
    card = FeishuChannel().render(opened)
    serialized = json.dumps(card, ensure_ascii=False)
    assert "finalize_evidence" in serialized
    assert "转人工复核" in serialized


def test_open_case_surfaces_extracted_facts():
    model = ScriptedModelProvider(
        [
            "PRODUCT_NOT_RECEIVED",
            '{"amount": "1200", "currency": "USD", "summary": "客户称未收到货"}',
        ],
        default_text="（合成）",
    )
    supervisor = ChargebackSupervisor(
        intake=IntakeAgent(model),
        evidence=EvidenceAgent(model),
        assess=ChargebackAssessAgent(model),
    )
    service = ChargebackChannelService(supervisor, InMemoryChargebackCaseStore())
    delivery = service.handle(
        NormalizedInbound(kind=InboundKind.OPEN_CASE, channel="test", description="下单后没收到货")
    )
    assert delivery.facts is not None
    assert delivery.facts.amount == "1200"
    assert delivery.facts.currency == "USD"
    assert delivery.facts.summary == "客户称未收到货"


def test_feishu_card_shows_extracted_facts():
    model = ScriptedModelProvider(
        ["PRODUCT_NOT_RECEIVED", '{"summary": "客户称未收到跨境订单"}'],
        default_text="（合成）",
    )
    supervisor = ChargebackSupervisor(
        intake=IntakeAgent(model),
        evidence=EvidenceAgent(model),
        assess=ChargebackAssessAgent(model),
    )
    service = ChargebackChannelService(supervisor, InMemoryChargebackCaseStore())
    delivery = service.handle(
        NormalizedInbound(
            kind=InboundKind.OPEN_CASE, channel="feishu", description="下单后没收到货"
        )
    )
    card = FeishuChannel().render(delivery)
    serialized = json.dumps(card, ensure_ascii=False)
    assert "识别要点" in serialized
    assert "客户称未收到跨境订单" in serialized


def test_assessment_delivery_exposes_source_and_breakdown():
    service = _service()
    delivery = service.handle(
        NormalizedInbound(
            kind=InboundKind.OPEN_CASE, channel="test", description="没收到货，要拒付"
        )
    )
    case_id = delivery.case_id
    for _ in range(20):
        if delivery.phase == "ASSESSED":
            break
        delivery = service.handle(
            NormalizedInbound(
                kind=InboundKind.SUBMIT_EVIDENCE,
                channel="test",
                case_id=case_id,
                evidence_code=delivery.next_evidence,
            )
        )
    assert delivery.assessment is not None
    assert delivery.assessment.explanation_source in ("MODEL", "FALLBACK")
    breakdown = delivery.assessment.evidence_breakdown
    assert breakdown
    for item in breakdown:
        assert item.label and item.weight >= 1
        assert "." in item.code  # raw token; label is the human name
    assert all(item.present for item in breakdown)  # full evidence submitted
