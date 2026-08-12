import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

from oceanpilot.domain.enums import EvidenceAvailability, EvidenceCode
from oceanpilot.domain.models import Revision, UUID4Str

_STRICT_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    strict=True,
    hide_input_in_errors=True,
)
_IDENTIFIER_PATTERN = r"^[A-Za-z0-9_-]+$"
_MILLISECOND_PATTERN = r"^[0-9]{13}$"


Identifier = Annotated[
    StrictStr,
    Field(min_length=1, max_length=100, pattern=_IDENTIFIER_PATTERN),
]
OptionalIdentifier = Annotated[
    StrictStr,
    Field(max_length=100, pattern=r"^(?:[A-Za-z0-9_-]+)?$"),
]
MillisecondTimestamp = Annotated[
    StrictStr,
    Field(pattern=_MILLISECOND_PATTERN),
]


class FeishuUrlVerificationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    token: Annotated[StrictStr, Field(min_length=1, max_length=512)]
    type: Literal["url_verification"]
    challenge: Annotated[StrictStr, Field(min_length=1, max_length=512)]


class FeishuUrlVerificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    challenge: Annotated[StrictStr, Field(min_length=1, max_length=512)]


class FeishuCallbackAcknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    ok: Literal[True] = True


class FeishuMessageHeader(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    event_id: Identifier
    token: Annotated[StrictStr, Field(min_length=1, max_length=512)]
    create_time: MillisecondTimestamp
    event_type: Literal["im.message.receive_v1"]
    tenant_key: Identifier
    app_id: Identifier


class FeishuSenderId(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    union_id: OptionalIdentifier = ""
    user_id: OptionalIdentifier = ""
    open_id: OptionalIdentifier = ""

    @model_validator(mode="after")
    def _has_identifier(self) -> "FeishuSenderId":
        if not (self.union_id or self.user_id or self.open_id):
            raise ValueError("sender_id must contain an identifier")
        return self


class FeishuMessageSender(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    sender_id: FeishuSenderId
    sender_type: Literal["user", "app"]
    tenant_key: Identifier


class FeishuMentionId(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    union_id: OptionalIdentifier = ""
    user_id: OptionalIdentifier = ""
    open_id: OptionalIdentifier = ""

    @model_validator(mode="after")
    def _has_identifier(self) -> "FeishuMentionId":
        if not (self.union_id or self.user_id or self.open_id):
            raise ValueError("mention id must contain an identifier")
        return self


class FeishuMessageMention(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    key: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    id: FeishuMentionId
    name: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    tenant_key: Identifier


class FeishuTextContent(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    text: Annotated[StrictStr, Field(min_length=1, max_length=500)]

    @field_validator("text", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        if type(value) is not str:
            raise ValueError("message text must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError("message text must not be empty")
        return stripped


class FeishuMessage(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    message_id: Identifier
    root_id: OptionalIdentifier = ""
    parent_id: OptionalIdentifier = ""
    create_time: MillisecondTimestamp
    chat_id: Identifier
    chat_type: Literal["group"]
    message_type: Literal["text"]
    content: FeishuTextContent
    mentions: tuple[FeishuMessageMention, ...] = ()

    @field_validator("mentions", mode="before")
    @classmethod
    def _freeze_mentions(cls, value: object) -> object:
        if type(value) is not list:
            raise ValueError("mentions must be a list")
        return tuple(value)

    @field_validator("content", mode="before")
    @classmethod
    def _parse_content(cls, value: object) -> object:
        if type(value) is not str:
            raise ValueError("message content must be JSON text")
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, RecursionError):
            raise ValueError("message content must be valid JSON") from None
        if type(decoded) is not dict:
            raise ValueError("message content must be a JSON object")
        return decoded


class FeishuMessageEvent(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    sender: FeishuMessageSender
    message: FeishuMessage


class FeishuMessageCallback(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    schema_version: Literal["2.0"] = Field(alias="schema")
    header: FeishuMessageHeader
    event: FeishuMessageEvent

    @model_validator(mode="after")
    def _tenant_keys_match(self) -> "FeishuMessageCallback":
        if self.event.sender.tenant_key != self.header.tenant_key:
            raise ValueError("sender tenant does not match callback tenant")
        return self


def parse_feishu_message_event(payload: dict[str, object]) -> FeishuMessageCallback:
    if type(payload) is not dict:
        raise TypeError("payload must be a dict")
    return FeishuMessageCallback.model_validate(payload)


class FeishuCardActionHeader(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    event_id: Identifier
    token: Annotated[StrictStr, Field(min_length=1, max_length=512)]
    create_time: MillisecondTimestamp
    event_type: Literal["card.action.trigger"]
    tenant_key: Identifier
    app_id: Identifier


class FeishuCardOperator(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    open_id: OptionalIdentifier = ""
    user_id: OptionalIdentifier = ""
    union_id: OptionalIdentifier = ""

    @model_validator(mode="after")
    def _has_identifier(self) -> "FeishuCardOperator":
        if not (self.open_id or self.user_id or self.union_id):
            raise ValueError("operator must contain an identifier")
        return self


class FeishuCardContext(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    open_message_id: Identifier
    open_chat_id: Identifier


class FeishuEvidenceActionValue(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    action_kind: Literal["submit_evidence"]
    case_id: UUID4Str
    case_revision: Revision
    evidence_code: EvidenceCode
    availability: EvidenceAvailability
    typed_value: StrictStr | None = None

    @field_validator("typed_value", mode="before")
    @classmethod
    def _require_string_value(cls, value: object) -> object:
        if value is not None and type(value) is not str:
            raise ValueError("typed value must be text")
        return value

    @field_validator("evidence_code", mode="before")
    @classmethod
    def _parse_evidence_code(cls, value: object) -> EvidenceCode:
        if type(value) is not str:
            raise ValueError("evidence code must be text")
        return EvidenceCode(value)

    @field_validator("availability", mode="before")
    @classmethod
    def _parse_availability(cls, value: object) -> EvidenceAvailability:
        if type(value) is not str:
            raise ValueError("availability must be text")
        return EvidenceAvailability(value)

    @model_validator(mode="after")
    def _availability_matches_value(self) -> "FeishuEvidenceActionValue":
        if self.availability is EvidenceAvailability.AVAILABLE:
            if self.typed_value is None:
                raise ValueError("available evidence requires a value")
        elif self.typed_value is not None:
            raise ValueError("unavailable evidence must not have a value")
        return self


class FeishuEvidenceCardAction(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    tag: Literal["button"]
    value: FeishuEvidenceActionValue


class FeishuEvidenceCardEvent(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    operator: FeishuCardOperator
    context: FeishuCardContext
    action: FeishuEvidenceCardAction


class FeishuEvidenceCardCallback(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    schema_version: Literal["2.0"] = Field(alias="schema")
    header: FeishuCardActionHeader
    event: FeishuEvidenceCardEvent


def parse_feishu_evidence_action(
    payload: dict[str, object],
) -> FeishuEvidenceCardCallback:
    if type(payload) is not dict:
        raise TypeError("payload must be a dict")
    return FeishuEvidenceCardCallback.model_validate(payload)
