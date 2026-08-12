from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from oceanpilot.application.feishu_models import (
    FeishuApprovalRecord,
    FeishuConfirmationReceipt,
)
from oceanpilot.domain.models import AwareDateTime, UUID4Str


class FeishuBindingOutcome(StrEnum):
    CLAIMED = "CLAIMED"
    IN_PROGRESS = "IN_PROGRESS"
    BOUND = "BOUND"


class FeishuBindingClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: FeishuBindingOutcome
    case_id: UUID4Str


class FeishuChatCasePort(Protocol):
    def get_case_id(self, binding_key: str) -> UUID4Str | None: ...

    def claim_case_binding(
        self,
        binding_key: str,
        event_id: str,
        case_id: UUID4Str,
        *,
        claim_token: str,
        now: AwareDateTime,
        lease_expires_at: AwareDateTime,
    ) -> FeishuBindingClaim: ...

    def complete_case_binding(
        self,
        binding_key: str,
        event_id: str,
        case_id: UUID4Str,
        *,
        claim_token: str,
        updated_at: AwareDateTime,
    ) -> FeishuBindingClaim: ...

    def release_case_binding(
        self,
        binding_key: str,
        event_id: str,
        *,
        claim_token: str,
    ) -> None: ...


class FeishuApprovalPort(Protocol):
    def record_confirmation(
        self,
        record: FeishuApprovalRecord,
    ) -> FeishuConfirmationReceipt: ...
