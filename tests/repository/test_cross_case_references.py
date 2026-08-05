from pathlib import Path

from test_diagnosis_store import (
    _assert_commit_diagnosis_rejects_evidence_owned_by_another_case_atomically,
)


def test_diagnosis_commit_rejects_cross_case_evidence_references(db_path: Path) -> None:
    _assert_commit_diagnosis_rejects_evidence_owned_by_another_case_atomically(db_path)
