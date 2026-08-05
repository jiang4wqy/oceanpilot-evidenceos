from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from oceanpilot.domain.enums import CaseCommand, CaseStatus
from oceanpilot.domain.errors import InvalidTransition
from oceanpilot.domain.models import DiagnosisDraft, ReadinessAssessment

ALLOWED_COMMANDS: Final[Mapping[CaseStatus, frozenset[CaseCommand]]] = MappingProxyType(
    {
        CaseStatus.NEW: frozenset(),
        CaseStatus.NEED_INFO: frozenset({CaseCommand.ADD_EVIDENCE}),
        CaseStatus.EVIDENCE_READY: frozenset(
            {
                CaseCommand.ADD_EVIDENCE,
                CaseCommand.DIAGNOSE,
            }
        ),
        CaseStatus.DIAGNOSED: frozenset(
            {
                CaseCommand.ADD_EVIDENCE,
                CaseCommand.DIAGNOSE,
            }
        ),
        CaseStatus.HUMAN_REVIEW: frozenset(
            {
                CaseCommand.ADD_EVIDENCE,
                CaseCommand.DIAGNOSE,
            }
        ),
    }
)


def assert_command_allowed(status: CaseStatus, command: CaseCommand) -> None:
    if command not in ALLOWED_COMMANDS.get(status, frozenset()):
        raise InvalidTransition()


def status_after_creation(readiness: ReadinessAssessment) -> CaseStatus:
    return CaseStatus.EVIDENCE_READY if readiness.ready else CaseStatus.NEED_INFO


def status_after_evidence(
    current: CaseStatus,
    readiness: ReadinessAssessment,
) -> CaseStatus:
    assert_command_allowed(current, CaseCommand.ADD_EVIDENCE)
    return CaseStatus.EVIDENCE_READY if readiness.ready else CaseStatus.NEED_INFO


def status_after_diagnosis(draft: DiagnosisDraft) -> CaseStatus:
    return CaseStatus.HUMAN_REVIEW if draft.requires_human else CaseStatus.DIAGNOSED
