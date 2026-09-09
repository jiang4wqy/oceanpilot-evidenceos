"""V2.1 DTO extensions; application composition merges DATA_MODELS into V2 routes."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ReasonData(StrictDTO):
    reason: StrictStr = Field(min_length=3, max_length=1000)


class RuleData(ReasonData):
    allowed_actions: list[Literal["ACCEPT", "CONTEST"]] = Field(min_length=1, max_length=2)
    source_id: StrictStr = Field(min_length=1, max_length=160)
    source_locator: StrictStr = Field(min_length=1, max_length=500)
    rule_version: StrictStr = Field(min_length=1, max_length=100)
    external_deadline: StrictStr = Field(min_length=10, max_length=60)
    merchant_deadline: StrictStr | None = Field(default=None, max_length=60)
    internal_deadline: StrictStr | None = Field(default=None, max_length=60)
    required_evidence: list[StrictStr] = Field(min_length=0, max_length=30)


class ResolveResponseData(ReasonData):
    resolution: Literal["RESTORE_DECISION", "RESTORE_EVIDENCE", "CONFIRM_LOSS", "FOLLOW_UP"]
    authorization_reference: StrictStr = Field(min_length=1, max_length=500)
    external_deadline: StrictStr | None = Field(default=None, max_length=60)


class FinalReviewData(ReasonData):
    decision: Literal["APPROVE", "RETURN_MATERIALS", "RETURN_DOCUMENT", "RECOMMEND_ACCEPT", "HOLD"]
    package_id: StrictStr | None = Field(default=None, max_length=100)
    pii_checked: StrictBool = False


class EvidenceContentReviewData(ReasonData):
    evidence_id: StrictStr = Field(min_length=1, max_length=100)
    decision: Literal["SUPPORTED", "INSUFFICIENT"]
    applicable_facts: list[StrictStr] = Field(min_length=1, max_length=20)
    locators: list[StrictStr] = Field(min_length=1, max_length=20)


class OutcomeData(StrictDTO):
    event_id: StrictStr = Field(min_length=1, max_length=100)
    outcome: Literal[
        "UNKNOWN", "WON", "LOST", "PARTIAL", "ACCEPTED_RESPONSIBILITY", "WITHDRAWN", "OTHER"
    ]
    final: StrictBool
    source: StrictStr = Field(min_length=1, max_length=160)
    reason: StrictStr = Field(default="", max_length=1000)
    disposition: Literal["WAIT", "VERIFY", "ACTION", "NEXT_STAGE", "FINAL"] | None = None
    next_stage: Literal["REPRESENTMENT", "PRE_ARBITRATION", "ARBITRATION", "OTHER"] | None = None
    occurred_at: StrictStr | None = Field(default=None, max_length=60)
    received_at: StrictStr | None = Field(default=None, max_length=60)
    stage_number: StrictInt | None = Field(default=None, ge=1)
    corrects_event_id: StrictStr | None = Field(default=None, max_length=100)
    basis_reference: StrictStr | None = Field(default=None, max_length=500)
    mapped_outcome: (
        Literal["WON", "LOST", "PARTIAL", "ACCEPTED_RESPONSIBILITY", "WITHDRAWN"] | None
    ) = None
    authorization_reference: StrictStr | None = Field(default=None, max_length=500)
    supported_minor: StrictInt | None = Field(default=None, ge=0, le=10**12)
    liable_minor: StrictInt | None = Field(default=None, ge=0, le=10**12)
    currency: StrictStr | None = Field(default=None, pattern=r"^[A-Z]{3}$")


class VerifyOutcomeData(ReasonData):
    event_id: StrictStr = Field(min_length=1, max_length=100)
    decision: Literal["CONFIRM", "REJECT"]
    authorization_reference: StrictStr = Field(min_length=1, max_length=500)


class StageData(StrictDTO):
    stage: Literal["REPRESENTMENT", "PRE_ARBITRATION", "ARBITRATION", "OTHER"]
    event_id: StrictStr = Field(min_length=1, max_length=100)
    source: StrictStr = Field(min_length=1, max_length=160)
    occurred_at: StrictStr | None = Field(default=None, max_length=60)
    received_at: StrictStr | None = Field(default=None, max_length=60)
    external_deadline: StrictStr | None = Field(default=None, max_length=60)


class ReopenData(ReasonData):
    authorization_reference: StrictStr = Field(min_length=1, max_length=500)
    event_reference: StrictStr = Field(min_length=1, max_length=500)


class ReuseData(ReasonData):
    evidence_ids: list[StrictStr] = Field(min_length=1, max_length=100)


class SubmitData(StrictDTO):
    package_id: StrictStr | None = Field(default=None, max_length=100)
    mock_scenario: (
        Literal["ACCEPTED", "TECHNICAL_FAILURE", "BUSINESS_REJECTED", "TIMEOUT", "RESPONSE_LOST"]
        | None
    ) = None


class AcceptData(ReasonData):
    reference: StrictStr = Field(min_length=1, max_length=500)
    mode: Literal["MOCK", "NO_ACTION_REQUIRED"] = "MOCK"
    mock_scenario: (
        Literal["ACCEPTED", "TECHNICAL_FAILURE", "BUSINESS_REJECTED", "TIMEOUT", "RESPONSE_LOST"]
        | None
    ) = None


class QueryData(ReasonData):
    request_id: StrictStr = Field(min_length=1, max_length=200)
    result: Literal["ACCEPTED", "NOT_ACCEPTED", "UNKNOWN"]


class ResolveTaskData(ReasonData):
    task_id: StrictStr = Field(min_length=1, max_length=100)
    resolution: Literal["CANCELLED", "WAIVED", "SUPERSEDED"]
    replacement_task_id: StrictStr | None = Field(default=None, max_length=100)


class AssignData(ReasonData):
    user_id: StrictStr = Field(min_length=1, max_length=100)


DATA_MODELS = {
    "CONFIRM_RULE": RuleData,
    "RESOLVE_RESPONSE": ResolveResponseData,
    "FINAL_REVIEW": FinalReviewData,
    "REVIEW_EVIDENCE_CONTENT": EvidenceContentReviewData,
    "RECORD_OUTCOME": OutcomeData,
    "VERIFY_OUTCOME": VerifyOutcomeData,
    "NEXT_STAGE": StageData,
    "REOPEN_CASE": ReopenData,
    "REUSE_EVIDENCE": ReuseData,
    "SUBMIT": SubmitData,
    "PROCESS_ACCEPT": AcceptData,
    "QUERY_SUBMISSION": QueryData,
    "RESOLVE_TASK": ResolveTaskData,
    "ASSIGN_CASE": AssignData,
}
