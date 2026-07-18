from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import Protocol

from oceanpilot.domain.enums import CaseStatus
from oceanpilot.domain.models import (
    AppendEvidenceResult,
    AuditEvent,
    CaseInputSnapshot,
    CaseView,
    CommitDiagnosisResult,
    DiagnosisSnapshot,
    EvidenceItem,
    MerchantSuccessCase,
    ReadinessAssessment,
    UUID4Str,
)


class CaseStoreSession(Protocol):
    def healthcheck(self) -> None: ...

    def get_case_view(self, case_id: UUID4Str) -> CaseView | None: ...

    def load_case_snapshot(self, case_id: UUID4Str) -> CaseInputSnapshot | None: ...

    def create_case_atomic(
        self,
        *,
        case: MerchantSuccessCase,
        audit: AuditEvent,
    ) -> CaseView: ...

    def append_evidence_atomic(
        self,
        *,
        expected_case_revision: int,
        expected_evidence_revision: int,
        evidence: EvidenceItem,
        readiness: ReadinessAssessment,
        target_status: CaseStatus,
        audit_events: Sequence[AuditEvent],
    ) -> AppendEvidenceResult: ...

    def find_diagnosis(
        self,
        *,
        case_id: UUID4Str,
        evidence_revision: int,
        policy_version: str,
    ) -> DiagnosisSnapshot | None: ...

    def commit_diagnosis_atomic(
        self,
        *,
        expected_case_revision: int,
        expected_evidence_revision: int,
        snapshot: DiagnosisSnapshot,
        target_status: CaseStatus,
        audit_events: Sequence[AuditEvent],
    ) -> CommitDiagnosisResult: ...


class CaseStoreFactory(Protocol):
    def __call__(self) -> AbstractContextManager[CaseStoreSession]: ...
