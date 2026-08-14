from decimal import Decimal

from scripts.eval_chargeback import build_report, evaluate_calibration, evaluate_intake


def test_intake_accuracy_is_high():
    report = evaluate_intake()
    assert report.total == 7
    assert report.accuracy >= 0.7


def test_calibration_separates_won_from_lost():
    cal = evaluate_calibration()
    assert cal.won_mean > cal.lost_mean
    assert cal.separation > Decimal("0")
    assert cal.threshold_accuracy >= 0.75
    # Every weak (lost) case is routed to human review.
    assert cal.lost_review_recall == 1.0


def test_report_renders_markdown_sections():
    report = build_report()
    assert "离线评测报告" in report
    assert "Intake" in report
    assert "规则分离度" in report
    assert "不代表真实胜诉概率" in report
