from pathlib import Path

import pytest
from test_diagnosis_store import (
    _assert_concurrent_diagnosis_unique_key_creates_once_and_replays_once,
    _assert_concurrent_different_policy_loser_gets_case_revision_conflict,
)

from oceanpilot.adapters.persistence.sqlite import connect_sqlite


@pytest.mark.parametrize("attempt", range(3))
def test_concurrent_identical_diagnoses_create_one_complete_aggregate(
    db_path: Path,
    attempt: int,
) -> None:
    _assert_concurrent_diagnosis_unique_key_creates_once_and_replays_once(db_path, attempt)

    connection = connect_sqlite(db_path)
    try:
        counts = tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "diagnosis_snapshots",
                "hypotheses",
                "hypothesis_evidence_refs",
            )
        )
        diagnosis_audits = connection.execute(
            """
            SELECT count(*)
            FROM audit_events
            WHERE event_type IN (
                'DIAGNOSIS_CREATED', 'ROUTING_PROPOSED', 'STATE_TRANSITIONED'
            ) AND case_revision = 7 AND evidence_revision = 5
            """
        ).fetchone()[0]
    finally:
        connection.close()

    assert counts == (1, 1, 2)
    assert diagnosis_audits == 3


def test_concurrent_different_policy_keeps_only_the_winner(db_path: Path) -> None:
    _assert_concurrent_different_policy_loser_gets_case_revision_conflict(db_path)
