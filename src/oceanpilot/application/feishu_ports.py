from typing import Protocol

from oceanpilot.application.commands import (
    AddEvidenceCommand,
    CreateCaseCommand,
    DiagnoseCaseCommand,
)
from oceanpilot.domain.models import (
    AppendEvidenceResult,
    CaseView,
    CommandResult,
    DiagnosisView,
)


class CaseCommandPort(Protocol):
    def create_case(self, command: CreateCaseCommand) -> CaseView: ...

    def get_case(self, case_id: str) -> CaseView: ...

    def add_evidence(self, command: AddEvidenceCommand) -> AppendEvidenceResult: ...

    def diagnose(
        self, command: DiagnoseCaseCommand
    ) -> CommandResult[DiagnosisView]: ...


class FeishuBindingPort(Protocol):
    def get_chat_case(self, chat_id: str) -> str | None: ...

    def bind_chat_case(self, chat_id: str, case_id: str, *, updated_at: str) -> None: ...
