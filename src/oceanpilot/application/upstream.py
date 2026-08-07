"""Upstream appeal-channel seam.

The PSP submits the representment to an upstream channel (bank/network) and
tracks status. This is the port; the only implementation for now is a mock that
records but never performs a real submission. Real connectors are deferred and
must stay behind a human-approval gate.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class SubmissionStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    WON = "WON"
    LOST = "LOST"
    ERROR = "ERROR"


@dataclass(frozen=True)
class SubmissionReceipt:
    submission_id: str
    status: SubmissionStatus
    channel: str


@runtime_checkable
class UpstreamConnector(Protocol):
    def submit(self, *, reference: str, payload: Mapping[str, object]) -> SubmissionReceipt: ...

    def status(self, submission_id: str) -> SubmissionStatus: ...
