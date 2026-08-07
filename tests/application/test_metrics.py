from oceanpilot.application.metrics import DecisionMetrics


def test_incr_and_snapshot():
    metrics = DecisionMetrics()
    metrics.incr("a")
    metrics.incr("a")
    metrics.incr("b", 3)
    assert metrics.snapshot() == {"a": 2, "b": 3}


def test_snapshot_is_sorted_and_isolated():
    metrics = DecisionMetrics()
    metrics.incr("z")
    metrics.incr("a")
    snapshot = metrics.snapshot()
    assert list(snapshot) == ["a", "z"]
    snapshot["a"] = 99  # mutating the copy must not affect the registry
    assert metrics.snapshot()["a"] == 1
