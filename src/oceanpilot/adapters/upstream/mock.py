"""Mock upstream connector — records submissions, performs no real action.

Deterministic ids by default (injectable factory for tests). Stands in until a
real, human-gated upstream channel is built.
"""

from collections.abc import Callable, Mapping

from oceanpilot.application.upstream import SubmissionReceipt, SubmissionStatus


class MockUpstreamConnector:
    def __init__(
        self,
        *,
        channel: str = "mock",
        id_factory: Callable[[], str] | None = None,
        review_status: SubmissionStatus = SubmissionStatus.UNDER_REVIEW,
    ) -> None:
        self._channel = channel
        self._id_factory = id_factory
        self._review_status = review_status
        self._counter = 0
        self.submissions: list[dict[str, object]] = []

    def submit(self, *, reference: str, payload: Mapping[str, object]) -> SubmissionReceipt:
        self._counter += 1
        submission_id = self._id_factory() if self._id_factory else f"mock-sub-{self._counter:04d}"
        self.submissions.append(
            {"id": submission_id, "reference": reference, "payload": dict(payload)}
        )
        return SubmissionReceipt(
            submission_id=submission_id,
            status=SubmissionStatus.SUBMITTED,
            channel=self._channel,
        )

    def status(self, submission_id: str) -> SubmissionStatus:
        return self._review_status
