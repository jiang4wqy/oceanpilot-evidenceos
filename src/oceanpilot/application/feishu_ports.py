from typing import Protocol

from oceanpilot.application.feishu_models import (
    FeishuApprovalRecord,
    FeishuConfirmationReceipt,
)
from oceanpilot.domain.models import AwareDateTime, UUID4Str


class FeishuChatCasePort(Protocol):
    def get_case_id(self, binding_key: str) -> UUID4Str | None: ...

    def bind_case(
        self,
        binding_key: str,
        case_id: UUID4Str,
        *,
        updated_at: AwareDateTime,
    ) -> None: ...


class FeishuApprovalPort(Protocol):
    def record_confirmation(
        self,
        record: FeishuApprovalRecord,
    ) -> FeishuConfirmationReceipt: ...
