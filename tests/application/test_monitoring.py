from datetime import UTC, datetime, timedelta

from oceanpilot.application.monitoring import RequestMonitor, predict_failure_risks


def test_request_monitor_aggregates_rolling_endpoint_metrics():
    now = [datetime(2026, 8, 14, 12, 0, tzinfo=UTC)]
    monitor = RequestMonitor(clock=lambda: now[0])
    monitor.record(method="GET", route="/health", status_code=200, duration_ms=12)
    monitor.record(method="GET", route="/health", status_code=503, duration_ms=42)

    snapshot = monitor.snapshot(window_minutes=15)

    assert snapshot.total == 2
    assert snapshot.successes == 1
    assert snapshot.server_errors == 1
    endpoint = snapshot.endpoints[0]
    assert (endpoint.method, endpoint.route, endpoint.total) == ("GET", "/health", 2)
    assert endpoint.error_rate == 0.5
    assert endpoint.average_latency_ms == 27.0
    assert endpoint.p95_latency_ms == 42

    now[0] += timedelta(minutes=16)
    assert monitor.snapshot(window_minutes=15).total == 0


def test_failure_prediction_is_threshold_based_and_explainable():
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    monitor = RequestMonitor(clock=lambda: now)
    monitor.record(
        method="POST",
        route="/api/v1/chargeback/cases",
        status_code=500,
        duration_ms=900,
    )

    signals = predict_failure_risks(
        monitor.snapshot(),
        database_healthy=True,
        business_counts={"appeal_blocked": 4, "appeal_submitted": 1},
    )

    assert [item.severity for item in signals][:2] == ["CRITICAL", "WARNING"]
    assert any("5xx" in item.evidence for item in signals)
    assert any(item.signal_id == "appeal-blocked-backlog" for item in signals)
    assert all(item.recommendation for item in signals)


def test_failure_prediction_reports_no_leading_indicator_for_clean_window():
    monitor = RequestMonitor()
    monitor.record(method="GET", route="/health", status_code=200, duration_ms=8)

    signals = predict_failure_risks(
        monitor.snapshot(),
        database_healthy=True,
        business_counts={},
    )

    assert len(signals) == 1
    assert signals[0].severity == "INFO"
    assert signals[0].signal_id == "no-leading-indicator"
