from collections.abc import Sequence
from typing import ClassVar

from oceanpilot.domain.models import Revision, UUID4Str


class ApplicationError(Exception):
    message: ClassVar[str] = "application error"

    def __init__(self) -> None:
        super().__init__()

    def __str__(self) -> str:
        return type(self).message


class CaseNotFound(ApplicationError):
    message = "case was not found"


class CaseTypeNotEnabled(ApplicationError):
    message = "case type is not enabled"


class CaseNotReady(ApplicationError):
    message = "case is not ready for diagnosis"

    def __init__(
        self,
        *,
        case_id: UUID4Str,
        missing_fields: Sequence[str],
        current_revision: Revision,
    ) -> None:
        super().__init__()
        self._case_id = case_id
        self._missing_fields = tuple(missing_fields)
        self._current_revision = current_revision

    @property
    def case_id(self) -> UUID4Str:
        return self._case_id

    @property
    def missing_fields(self) -> tuple[str, ...]:
        return self._missing_fields

    @property
    def current_revision(self) -> Revision:
        return self._current_revision


class EvidenceConflict(ApplicationError):
    message = "evidence id conflicts with existing content"


class ConcurrentCaseWrite(ApplicationError):
    message = "case changed during write"


class DiagnosisInputStale(ApplicationError):
    message = "diagnosis input is stale"


class DatabaseUnavailable(ApplicationError):
    message = "database is unavailable"


class PersistenceInvariantViolation(ApplicationError):
    message = "persistence invariant was violated"


class InvalidInbound(ApplicationError):
    message = "inbound request is invalid"
