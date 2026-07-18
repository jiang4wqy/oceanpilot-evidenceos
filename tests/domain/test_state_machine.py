from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import cast

import pytest

from oceanpilot.domain.enums import (
    CaseCommand,
    CaseStatus,
    StopReason,
)
from oceanpilot.domain.errors import InvalidTransition
from oceanpilot.domain.evidence_policy import assess_readiness, build_active_evidence_view
from oceanpilot.domain.models import DiagnosisDraft, ReadinessAssessment
from oceanpilot.domain.state_machine import (
    ALLOWED_COMMANDS,
    assert_command_allowed,
    status_after_creation,
    status_after_diagnosis,
    status_after_evidence,
)


def readiness(ready: bool) -> ReadinessAssessment:
    return ReadinessAssessment(
        ready=ready,
        missing_fields=() if ready else ("transaction.reference",),
        known_unknown_fields=(),
        next_question=None if ready else "transaction.reference",
        question_reason=None if ready else "定位同一笔交易",
        target_role=None,
        completion_ratio=Decimal("1") if ready else Decimal("0"),
        stop_reason=StopReason.READY if ready else StopReason.NEED_MORE_EVIDENCE,
    )


EXPECTED_COMMANDS = {
    CaseStatus.NEW: frozenset(),
    CaseStatus.NEED_INFO: frozenset({CaseCommand.ADD_EVIDENCE}),
    CaseStatus.EVIDENCE_READY: frozenset({
        CaseCommand.ADD_EVIDENCE,
        CaseCommand.DIAGNOSE,
    }),
    CaseStatus.DIAGNOSED: frozenset({
        CaseCommand.ADD_EVIDENCE,
        CaseCommand.DIAGNOSE,
    }),
    CaseStatus.HUMAN_REVIEW: frozenset({
        CaseCommand.ADD_EVIDENCE,
        CaseCommand.DIAGNOSE,
    }),
}


def test_allowed_commands_are_exact_and_externally_immutable() -> None:
    assert isinstance(ALLOWED_COMMANDS, MappingProxyType)
    assert dict(ALLOWED_COMMANDS) == EXPECTED_COMMANDS

    with pytest.raises(TypeError):
        ALLOWED_COMMANDS[CaseStatus.NEW] = frozenset({CaseCommand.DIAGNOSE})
    with pytest.raises(TypeError):
        del ALLOWED_COMMANDS[CaseStatus.NEED_INFO]


@pytest.mark.parametrize(
    ("status", "command"),
    tuple(
        (status, command)
        for status, commands in EXPECTED_COMMANDS.items()
        for command in commands
    ),
)
def test_allowlisted_commands_are_accepted(
    status: CaseStatus,
    command: CaseCommand,
) -> None:
    assert_command_allowed(status, command)


@pytest.mark.parametrize(
    ("status", "command"),
    tuple(
        (status, command)
        for status, commands in EXPECTED_COMMANDS.items()
        for command in CaseCommand
        if command not in commands
    ),
)
def test_unlisted_commands_are_denied_without_mutating_the_allowlist(
    status: CaseStatus,
    command: CaseCommand,
) -> None:
    before = dict(ALLOWED_COMMANDS)
    with pytest.raises(
        InvalidTransition,
        match="^case command is not allowed in the current state$",
    ):
        assert_command_allowed(status, command)
    assert dict(ALLOWED_COMMANDS) == before


def test_unknown_status_and_command_default_to_deny() -> None:
    with pytest.raises(
        InvalidTransition,
        match="^case command is not allowed in the current state$",
    ):
        assert_command_allowed(cast(CaseStatus, "UNKNOWN"), CaseCommand.ADD_EVIDENCE)
    with pytest.raises(
        InvalidTransition,
        match="^case command is not allowed in the current state$",
    ):
        assert_command_allowed(CaseStatus.EVIDENCE_READY, cast(CaseCommand, "UNKNOWN"))


@pytest.mark.parametrize(
    ("ready", "expected"),
    ((False, CaseStatus.NEED_INFO), (True, CaseStatus.EVIDENCE_READY)),
)
def test_creation_status_follows_readiness(ready: bool, expected: CaseStatus) -> None:
    assert status_after_creation(readiness(ready)) is expected


@pytest.mark.parametrize(
    "current",
    (
        CaseStatus.NEED_INFO,
        CaseStatus.EVIDENCE_READY,
        CaseStatus.DIAGNOSED,
        CaseStatus.HUMAN_REVIEW,
    ),
)
@pytest.mark.parametrize(
    ("ready", "expected"),
    ((False, CaseStatus.NEED_INFO), (True, CaseStatus.EVIDENCE_READY)),
)
def test_every_add_evidence_status_follows_recomputed_readiness(
    current: CaseStatus,
    ready: bool,
    expected: CaseStatus,
) -> None:
    assert status_after_evidence(current, readiness(ready)) is expected


def test_new_cannot_transition_through_add_evidence() -> None:
    with pytest.raises(
        InvalidTransition,
        match="^case command is not allowed in the current state$",
    ):
        status_after_evidence(CaseStatus.NEW, readiness(True))


@pytest.mark.parametrize("current", (CaseStatus.DIAGNOSED, CaseStatus.HUMAN_REVIEW))
def test_plugin_evidence_can_reopen_ready_cases_to_need_info(
    evidence_factory,
    current: CaseStatus,
) -> None:
    facts = (
        ("transaction.reference", "txn_1"),
        ("transaction.occurred_at", datetime.fromisoformat("2026-07-18T12:00:00+08:00")),
        ("context.environment", "PROD"),
        ("symptom.status", "FAILED"),
        ("integration.type", "PLUGIN"),
    )
    items = [
        evidence_factory(
            code=code,
            value=value,
            evidence_id=f"00000000-0000-4000-8000-{index:012d}",
        )
        for index, (code, value) in enumerate(facts, start=1)
    ]
    recomputed = assess_readiness(build_active_evidence_view(items))

    assert recomputed.ready is False
    assert recomputed.missing_fields == (
        "integration.platform",
        "integration.plugin_version",
    )
    assert status_after_evidence(current, recomputed) is CaseStatus.NEED_INFO


@pytest.mark.parametrize(
    ("requires_human", "expected"),
    ((False, CaseStatus.DIAGNOSED), (True, CaseStatus.HUMAN_REVIEW)),
)
def test_diagnosis_status_follows_human_review_flag(
    requires_human: bool,
    expected: CaseStatus,
) -> None:
    draft = DiagnosisDraft(
        hypotheses=(),
        requires_human=requires_human,
        review_reasons=frozenset(),
    )
    assert status_after_diagnosis(draft) is expected
