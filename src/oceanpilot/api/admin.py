"""Read-only operational overview for the separate management console."""

from dataclasses import dataclass

from fastapi import APIRouter, Request

from oceanpilot.api.admin_schemas import (
    AdminOverviewResponse,
    EndpointStatusDTO,
    FailureSignalDTO,
    RequestSummaryDTO,
    ServiceStatusDTO,
)
from oceanpilot.application.monitoring import EndpointTelemetry, predict_failure_risks

router = APIRouter(prefix="/api/v1/admin", tags=["operations"])


@dataclass(frozen=True, slots=True)
class _EndpointDefinition:
    name: str
    group: str
    method: str
    route: str


_ENDPOINTS = (
    _EndpointDefinition("服务健康检查", "基础服务", "GET", "/health"),
    _EndpointDefinition("创建拒付案件", "拒付案件", "POST", "/api/v1/chargeback/cases"),
    _EndpointDefinition("读取案件详情", "拒付案件", "GET", "/api/v1/chargeback/cases/{case_id}"),
    _EndpointDefinition(
        "补充案件材料", "拒付案件", "POST", "/api/v1/chargeback/cases/{case_id}/evidence"
    ),
    _EndpointDefinition(
        "确认争议原因", "拒付案件", "POST", "/api/v1/chargeback/cases/{case_id}/confirm"
    ),
    _EndpointDefinition(
        "生成申诉材料包", "拒付案件", "GET", "/api/v1/chargeback/cases/{case_id}/package"
    ),
    _EndpointDefinition(
        "提交申诉", "拒付案件", "POST", "/api/v1/chargeback/cases/{case_id}/appeal"
    ),
    _EndpointDefinition("交易风险评估", "交易预警", "POST", "/api/v1/chargeback/prevention/assess"),
    _EndpointDefinition("敏感信息检查", "安全控制", "POST", "/api/v1/chargeback/safety/scan"),
    _EndpointDefinition("飞书事件回调", "外部集成", "POST", "/api/v1/integrations/feishu/events"),
    _EndpointDefinition(
        "飞书卡片回调", "外部集成", "POST", "/api/v1/integrations/feishu/card-actions"
    ),
)


def _endpoint_status(item: EndpointTelemetry | None) -> str:
    if item is None:
        return "NOT_CALLED"
    if item.server_errors > 0 or (item.total >= 5 and item.error_rate >= 0.2):
        return "DEGRADED"
    if item.p95_latency_ms >= 800 or item.client_errors >= 3 or item.error_rate >= 0.05:
        return "WATCH"
    return "HEALTHY"


def _endpoint_dto(
    definition: _EndpointDefinition,
    item: EndpointTelemetry | None,
) -> EndpointStatusDTO:
    if item is None:
        return EndpointStatusDTO(
            name=definition.name,
            group=definition.group,
            method=definition.method,
            route=definition.route,
            status="NOT_CALLED",
            observed=False,
            total=0,
            successes=0,
            client_errors=0,
            server_errors=0,
            error_rate=0.0,
            average_latency_ms=0.0,
            p95_latency_ms=0.0,
        )
    return EndpointStatusDTO(
        name=definition.name,
        group=definition.group,
        method=item.method,
        route=item.route,
        status=_endpoint_status(item),
        observed=True,
        total=item.total,
        successes=item.successes,
        client_errors=item.client_errors,
        server_errors=item.server_errors,
        error_rate=float(item.error_rate),
        average_latency_ms=float(item.average_latency_ms),
        p95_latency_ms=float(item.p95_latency_ms),
        last_status=item.last_status,
        last_seen_at=item.last_seen_at.isoformat(),
    )


@router.get("/overview", response_model=AdminOverviewResponse)
def get_admin_overview(request: Request) -> AdminOverviewResponse:
    monitor = request.app.state.request_monitor
    snapshot = monitor.snapshot(window_minutes=15)
    metrics = request.app.state.chargeback_metrics.snapshot()

    database_healthy = True
    try:
        with request.app.state.store_factory() as store:
            store.healthcheck()
    except Exception:
        database_healthy = False

    observed = {(item.method, item.route): item for item in snapshot.endpoints}
    endpoints_list = [
        _endpoint_dto(definition, observed.get((definition.method, definition.route)))
        for definition in _ENDPOINTS
    ]
    defined = {(item.method, item.route) for item in _ENDPOINTS}
    for key, item in sorted(observed.items()):
        if key not in defined:
            endpoints_list.append(
                _endpoint_dto(
                    _EndpointDefinition("未登记接口", "其他接口", item.method, item.route),
                    item,
                )
            )
    endpoints = tuple(endpoints_list)
    predictions = predict_failure_risks(
        snapshot,
        database_healthy=database_healthy,
        business_counts=metrics,
    )
    if (
        not database_healthy
        or any(item.status == "DEGRADED" for item in endpoints)
        or any(item.severity == "CRITICAL" for item in predictions)
    ):
        overall = "DEGRADED"
    elif any(item.status == "WATCH" for item in endpoints) or any(
        item.severity == "WARNING" for item in predictions
    ):
        overall = "WATCH"
    else:
        overall = "HEALTHY"

    return AdminOverviewResponse(
        generated_at=snapshot.generated_at.isoformat(),
        window_minutes=snapshot.window_minutes,
        service_status=ServiceStatusDTO(
            overall=overall,
            application="HEALTHY",
            database="HEALTHY" if database_healthy else "DEGRADED",
        ),
        request_summary=RequestSummaryDTO(
            total=snapshot.total,
            successes=snapshot.successes,
            client_errors=snapshot.client_errors,
            server_errors=snapshot.server_errors,
            average_latency_ms=float(snapshot.average_latency_ms),
            p95_latency_ms=float(snapshot.p95_latency_ms),
        ),
        endpoints=endpoints,
        business_counts=metrics,
        predictions=tuple(
            FailureSignalDTO(
                signal_id=item.signal_id,
                severity=item.severity,
                title=item.title,
                evidence=item.evidence,
                recommendation=item.recommendation,
            )
            for item in predictions
        ),
        prediction_method="DETERMINISTIC_THRESHOLDS_V1",
        prediction_disclaimer="基于近 15 分钟请求、数据库健康和业务计数的阈值预警，不是故障概率。",
    )
