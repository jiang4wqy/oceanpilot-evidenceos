from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr

from oceanpilot.domain.enums import EvidenceAvailability, EvidenceCode

MESSAGE_RECEIVE_EVENT = "im.message.receive_v1"
CARD_ACTION_EVENT = "card.action.trigger"

ACTION_SUBMIT_EVIDENCE = "submit_evidence"
ACTION_CONFIRM_REVIEW = "confirm_review"
ALLOWED_CARD_ACTIONS = frozenset({ACTION_SUBMIT_EVIDENCE, ACTION_CONFIRM_REVIEW})


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)


class FeishuHeader(_Lenient):
    event_id: StrictStr | None = None
    event_type: StrictStr | None = None


class FeishuSenderId(_Lenient):
    open_id: StrictStr | None = None


class FeishuSender(_Lenient):
    sender_type: StrictStr | None = None
    sender_id: FeishuSenderId | None = None


class FeishuMessage(_Lenient):
    chat_id: StrictStr
    message_id: StrictStr | None = None
    message_type: StrictStr | None = None
    content: StrictStr | None = None


class FeishuMessageBody(_Lenient):
    sender: FeishuSender | None = None
    message: FeishuMessage


class FeishuMessageEnvelope(_Lenient):
    header: FeishuHeader
    event: FeishuMessageBody


class FeishuActionValue(_Lenient):
    action: StrictStr
    flow: StrictStr | None = None
    case_id: StrictStr | None = None
    diagnosis_id: StrictStr | None = None
    evidence_id: StrictStr | None = None
    evidence_code: EvidenceCode | None = None
    availability: EvidenceAvailability | None = None
    typed_value: StrictStr | StrictBool | None = None
    observed_at: StrictStr | None = None
    source_ref: StrictStr | None = None
    chargeback_evidence_code: StrictStr | None = None
    reason_code: StrictStr | None = None


class FeishuAction(_Lenient):
    tag: StrictStr | None = None
    value: FeishuActionValue


class FeishuOperator(_Lenient):
    open_id: StrictStr | None = None


class FeishuCardContext(_Lenient):
    open_chat_id: StrictStr | None = None
    open_message_id: StrictStr | None = None


class FeishuCardActionBody(_Lenient):
    operator: FeishuOperator | None = None
    action: FeishuAction
    context: FeishuCardContext | None = None


class FeishuCardActionEnvelope(_Lenient):
    header: FeishuHeader
    event: FeishuCardActionBody
