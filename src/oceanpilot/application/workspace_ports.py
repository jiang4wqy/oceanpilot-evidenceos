"""Versioned workspace metadata and atomic command/summary storage contracts."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from oceanpilot.application.case_review import CaseReviewStore
from oceanpilot.application.chargeback_ports import ChargebackCaseStore
from oceanpilot.application.chargeback_supervisor import ChargebackCaseState


class WorkspaceError(Exception):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


@dataclass(frozen=True)
class WorkspaceBundle:
    state: ChargebackCaseState
    info: dict[str, Any]
    materials: list[dict[str, Any]]
    concerns: list[dict[str, Any]]
    reviews: list[dict[str, Any]]
    timeline: list[dict[str, Any]]
    turns: list[dict[str, Any]]
    summaries: list[dict[str, Any]]


class WorkspaceUnit(Protocol):
    cases: ChargebackCaseStore
    reviews: CaseReviewStore

    def bundle(self, case_id: str) -> WorkspaceBundle: ...

    def set_info(self, case_id: str, data: dict[str, Any]) -> None: ...

    def register_material(self, case_id: str, data: dict[str, Any]) -> None: ...

    def withdraw_material(self, case_id: str, code: str) -> None: ...

    def add_concern(self, case_id: str, data: dict[str, Any]) -> str: ...

    def resolve_concern(self, case_id: str, concern_id: str, data: dict[str, Any]) -> None: ...

    def correct_fact(self, case_id: str, field: str, value: str) -> None: ...

    def touch(self, case_id: str) -> None: ...

    def record(self, case_id: str, event_type: str, detail: str, actor: str) -> str: ...


class WorkspaceStore(Protocol):
    def read(self, case_id: str) -> WorkspaceBundle: ...

    def case_ids(self) -> tuple[str, ...]: ...

    def run(
        self,
        command: dict[str, Any],
        role: str,
        actor: str,
        apply: Callable[[WorkspaceUnit], dict[str, Any]],
    ) -> dict[str, Any]: ...

    def command(self, command_id: str, role: str, actor: str) -> dict[str, Any]: ...

    def save_summary(
        self,
        case_id: str,
        revision: int,
        summary: dict[str, Any],
        html: str,
        validate: Callable[[], None],
    ) -> dict[str, Any]: ...

    def summary(self, summary_id: str) -> dict[str, Any]: ...
