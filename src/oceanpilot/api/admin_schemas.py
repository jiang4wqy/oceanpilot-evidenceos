"""Response contracts for the read-only operations dashboard."""

from pydantic import BaseModel, ConfigDict, StrictBool, StrictFloat, StrictInt, StrictStr


class ServiceStatusDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: StrictStr
    application: StrictStr
    database: StrictStr


class RequestSummaryDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: StrictInt
    successes: StrictInt
    client_errors: StrictInt
    server_errors: StrictInt
    average_latency_ms: StrictFloat
    p95_latency_ms: StrictFloat


class EndpointStatusDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: StrictStr
    group: StrictStr
    method: StrictStr
    route: StrictStr
    status: StrictStr
    observed: StrictBool
    total: StrictInt
    successes: StrictInt
    client_errors: StrictInt
    server_errors: StrictInt
    error_rate: StrictFloat
    average_latency_ms: StrictFloat
    p95_latency_ms: StrictFloat
    last_status: StrictInt | None = None
    last_seen_at: StrictStr | None = None


class FailureSignalDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: StrictStr
    severity: StrictStr
    title: StrictStr
    evidence: StrictStr
    recommendation: StrictStr


class PersistedCaseDTO(BaseModel):
    """A case that still resolves from the durable chargeback store."""

    model_config = ConfigDict(extra="forbid")

    case_id: StrictStr
    phase: StrictStr
    reason_code: StrictStr | None = None
    reason_label: StrictStr | None = None
    missing_count: StrictInt
    created_at: StrictStr | None = None


class AdminOverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: StrictStr
    window_minutes: StrictInt
    service_status: ServiceStatusDTO
    request_summary: RequestSummaryDTO
    endpoints: tuple[EndpointStatusDTO, ...]
    cases: tuple[PersistedCaseDTO, ...]
    business_counts: dict[StrictStr, StrictInt]
    predictions: tuple[FailureSignalDTO, ...]
    prediction_method: StrictStr
    prediction_disclaimer: StrictStr
