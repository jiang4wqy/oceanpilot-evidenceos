"""Persistence port for atomic V2 commands, receipts and audit records."""

from collections.abc import Callable
from typing import Protocol


class DisputeStore(Protocol):
    def list_cases(self, merchant_id: str | None = None) -> list[dict]: ...

    def get_case(self, case_id: str) -> dict | None: ...

    def get_command_fingerprint(self, command_id: str) -> str | None: ...

    def execute_atomic(
        self,
        *,
        command: dict,
        identity: dict,
        mutate: Callable[[dict | None], dict],
        event_key: str | None = None,
        event_fingerprint: str | None = None,
        upstream_case_key: str | None = None,
    ) -> dict: ...
