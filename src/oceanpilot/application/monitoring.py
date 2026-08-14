"""PII-free rolling HTTP telemetry and deterministic failure-risk signals."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from threading import Lock


@dataclass(frozen=True, slots=True)
class RequestObservation:
    occurred_at: datetime
    method: str
    route: str
    status_code: int
    duration_ms: float


@dataclass(frozen=True, slots=True)
class EndpointTelemetry:
    method: str
    route: str
    total: int
    successes: int
    client_errors: int
    server_errors: int
    error_rate: float
    average_latency_ms: float
    p95_latency_ms: float
    last_status: int
    last_seen_at: datetime


@dataclass(frozen=True, slots=True)
class RequestTelemetrySnapshot:
    generated_at: datetime
    window_minutes: int
    total: int
    successes: int
    client_errors: int
    server_errors: int
    average_latency_ms: float
    p95_latency_ms: float
    endpoints: tuple[EndpointTelemetry, ...]


@dataclass(frozen=True, slots=True)
class FailureSignal:
    signal_id: str
    severity: str
    title: str
    evidence: str
    recommendation: str


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil(len(ordered) * percentile) - 1))
    return round(ordered[index], 2)


class RequestMonitor:
    """Keep a bounded, process-local request window without bodies or raw paths."""

    def __init__(
        self,
        *,
        retention_minutes: int = 60,
        max_events: int = 10_000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._retention = timedelta(minutes=retention_minutes)
        self._events: deque[RequestObservation] = deque(maxlen=max_events)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = Lock()

    def record(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        observation = RequestObservation(
            occurred_at=self._clock(),
            method=method.upper(),
            route=route,
            status_code=status_code,
            duration_ms=max(0.0, round(duration_ms, 2)),
        )
        with self._lock:
            self._events.append(observation)
            self._prune_locked(observation.occurred_at - self._retention)

    def snapshot(self, *, window_minutes: int = 15) -> RequestTelemetrySnapshot:
        now = self._clock()
        cutoff = now - timedelta(minutes=window_minutes)
        with self._lock:
            self._prune_locked(now - self._retention)
            events = tuple(event for event in self._events if event.occurred_at >= cutoff)

        grouped: dict[tuple[str, str], list[RequestObservation]] = defaultdict(list)
        for event in events:
            grouped[(event.method, event.route)].append(event)

        endpoints = tuple(
            self._endpoint_snapshot(method, route, rows)
            for (method, route), rows in sorted(grouped.items())
        )
        durations = [event.duration_ms for event in events]
        return RequestTelemetrySnapshot(
            generated_at=now,
            window_minutes=window_minutes,
            total=len(events),
            successes=sum(event.status_code < 400 for event in events),
            client_errors=sum(400 <= event.status_code < 500 for event in events),
            server_errors=sum(event.status_code >= 500 for event in events),
            average_latency_ms=round(sum(durations) / len(durations), 2) if durations else 0.0,
            p95_latency_ms=_percentile(durations, 0.95),
            endpoints=endpoints,
        )

    def _prune_locked(self, cutoff: datetime) -> None:
        while self._events and self._events[0].occurred_at < cutoff:
            self._events.popleft()

    @staticmethod
    def _endpoint_snapshot(
        method: str,
        route: str,
        rows: list[RequestObservation],
    ) -> EndpointTelemetry:
        durations = [row.duration_ms for row in rows]
        client_errors = sum(400 <= row.status_code < 500 for row in rows)
        server_errors = sum(row.status_code >= 500 for row in rows)
        errors = client_errors + server_errors
        return EndpointTelemetry(
            method=method,
            route=route,
            total=len(rows),
            successes=sum(row.status_code < 400 for row in rows),
            client_errors=client_errors,
            server_errors=server_errors,
            error_rate=round(errors / len(rows), 4),
            average_latency_ms=round(sum(durations) / len(durations), 2),
            p95_latency_ms=_percentile(durations, 0.95),
            last_status=rows[-1].status_code,
            last_seen_at=rows[-1].occurred_at,
        )


def predict_failure_risks(
    snapshot: RequestTelemetrySnapshot,
    *,
    database_healthy: bool,
    business_counts: Mapping[str, int],
) -> tuple[FailureSignal, ...]:
    """Return explainable threshold alerts, not a learned failure probability."""

    signals: list[FailureSignal] = []
    if not database_healthy:
        signals.append(
            FailureSignal(
                signal_id="database-unavailable",
                severity="CRITICAL",
                title="数据库连接异常",
                evidence="健康检查未能完成数据库读写连通性验证。",
                recommendation="暂停关键提交并检查数据库文件、权限与磁盘状态。",
            )
        )

    for endpoint in snapshot.endpoints:
        label = f"{endpoint.method} {endpoint.route}"
        if endpoint.server_errors:
            signals.append(
                FailureSignal(
                    signal_id=f"server-error:{label}",
                    severity="CRITICAL",
                    title="接口出现服务端错误",
                    evidence=f"{label} 在监控窗口内出现 {endpoint.server_errors} 次 5xx。",
                    recommendation="优先查看对应 trace 日志，并暂停依赖该接口的批量操作。",
                )
            )
        elif endpoint.total >= 5 and endpoint.error_rate >= 0.2:
            signals.append(
                FailureSignal(
                    signal_id=f"error-rate:{label}",
                    severity="WARNING",
                    title="接口错误率持续偏高",
                    evidence=f"{label} 的错误率为 {endpoint.error_rate:.1%}。",
                    recommendation="检查调用参数、鉴权状态及上游返回，避免错误继续累积。",
                )
            )
        if endpoint.total >= 3 and endpoint.p95_latency_ms >= 800:
            signals.append(
                FailureSignal(
                    signal_id=f"latency:{label}",
                    severity="WARNING",
                    title="接口延迟接近风险阈值",
                    evidence=f"{label} 的 P95 延迟为 {endpoint.p95_latency_ms:.0f} ms。",
                    recommendation="检查数据库锁等待、外部调用和并发请求量。",
                )
            )

    submitted = business_counts.get("appeal_submitted", 0)
    blocked = business_counts.get("appeal_blocked", 0)
    if blocked >= 3 and blocked > submitted:
        signals.append(
            FailureSignal(
                signal_id="appeal-blocked-backlog",
                severity="WARNING",
                title="申诉阻断可能形成积压",
                evidence=f"已阻断 {blocked} 次，高于已提交 {submitted} 次。",
                recommendation="检查材料齐备率和人工审批队列，优先处理临近截止案件。",
            )
        )

    human = business_counts.get("requires_human_true", 0)
    automatic = business_counts.get("requires_human_false", 0)
    assessed = human + automatic
    if assessed >= 5 and human / assessed >= 0.6:
        signals.append(
            FailureSignal(
                signal_id="manual-review-pressure",
                severity="WARNING",
                title="人工复核压力上升",
                evidence=f"最近累计评估中 {human}/{assessed} 需要人工复核。",
                recommendation="检查高频缺失材料，并提前分配复核人员。",
            )
        )

    if not signals:
        signals.append(
            FailureSignal(
                signal_id="no-leading-indicator",
                severity="INFO",
                title="暂未发现明显故障前兆",
                evidence="数据库正常，且当前请求错误率与延迟未触发阈值。",
                recommendation="继续观察请求量、5xx、P95 延迟和业务阻断趋势。",
            )
        )
    severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    return tuple(sorted(signals, key=lambda item: (severity_order[item.severity], item.signal_id)))
