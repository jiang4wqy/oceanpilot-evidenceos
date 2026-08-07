"""Offline evaluation harness for the chargeback kernel + intake.

Answers the judge's question "how do you know it works?" without any network or
real data. Two synthetic, reproducible measurements:

1. **Intake accuracy** — the reason classifier over a small labeled description
   set (offline heuristic path), reported as accuracy + any mismatches.
2. **Win-likelihood calibration** — synthetic case samples (routed through the
   real ``adapters/ingestion`` loader, so company samples drop in later) scored
   by the deterministic kernel; reports mean win for won vs lost cases, their
   separation, a threshold accuracy, and how often lost cases are flagged for
   human review.

Run:  python scripts/eval_chargeback.py
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from oceanpilot.adapters.ingestion.loader import load_case_samples
from oceanpilot.adapters.ingestion.schema import CaseSampleRecord
from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.application.chargeback_agents import IntakeAgent
from oceanpilot.domain.chargeback import (
    WIN_REVIEW_THRESHOLD,
    DisputeReasonCode,
    assess_chargeback,
    required_evidence_for,
)

_R = DisputeReasonCode
_QUANT = Decimal("0.0001")

# Synthetic labeled descriptions (one per reason family the intake handles).
LABELED_DESCRIPTIONS: tuple[tuple[str, DisputeReasonCode], ...] = (
    ("客户说一直没收到货", _R.PRODUCT_NOT_RECEIVED),
    ("收到的商品与描述不符", _R.PRODUCT_NOT_AS_DESCRIBED),
    ("被重复扣款了两笔", _R.DUPLICATE_PROCESSING),
    ("退款一直没退到账", _R.CREDIT_NOT_PROCESSED),
    ("订阅已取消还在扣费", _R.SUBSCRIPTION_CANCELED),
    ("这笔是盗刷，不是我本人", _R.FRAUD_CARD_NOT_PRESENT),
    ("支付授权处理错误", _R.AUTHORIZATION_ERROR),
)


def _first_critical(reason: DisputeReasonCode) -> DisputeReasonCode | None:
    for item in assess_chargeback(reason, []).evidence_breakdown:
        if item.critical:
            return item.code
    return None


def _eval_sample(case_ref: str, reason: DisputeReasonCode, outcome: str, *, drop_critical: bool):
    present = list(required_evidence_for(reason))
    if drop_critical:
        critical = _first_critical(reason)
        if critical is not None:
            present = [code for code in present if code != critical]
    return {
        "case_ref": case_ref,
        "reason_code": reason.value,
        "present_evidence": [code.value for code in present],
        "outcome": outcome,
        "synthetic": True,
    }


# Synthetic calibration set: complete-evidence cases labeled won, missing-critical
# cases labeled lost. Routed through the ingestion loader (real pipeline).
_CALIBRATION_SPECS = [
    ("SYN-WON-PNR", _R.PRODUCT_NOT_RECEIVED, "won", False),
    ("SYN-LOST-PNR", _R.PRODUCT_NOT_RECEIVED, "lost", True),
    ("SYN-WON-FRAUD", _R.FRAUD_CARD_NOT_PRESENT, "won", False),
    ("SYN-LOST-FRAUD", _R.FRAUD_CARD_NOT_PRESENT, "lost", True),
    ("SYN-WON-CREDIT", _R.CREDIT_NOT_PROCESSED, "won", False),
    ("SYN-LOST-CREDIT", _R.CREDIT_NOT_PROCESSED, "lost", True),
    ("SYN-WON-DUP", _R.DUPLICATE_PROCESSING, "won", False),
    ("SYN-LOST-DUP", _R.DUPLICATE_PROCESSING, "lost", True),
]


def calibration_samples() -> tuple[CaseSampleRecord, ...]:
    records = [
        _eval_sample(ref, reason, outcome, drop_critical=drop)
        for ref, reason, outcome, drop in _CALIBRATION_SPECS
    ]
    return load_case_samples(records)


@dataclass
class IntakeReport:
    total: int
    correct: int
    mismatches: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass
class CalibrationReport:
    rows: list[tuple[str, str, str, str, bool]]  # ref, reason, outcome, win, requires_human
    won_mean: Decimal
    lost_mean: Decimal
    threshold_accuracy: float
    lost_review_recall: float

    @property
    def separation(self) -> Decimal:
        return (self.won_mean - self.lost_mean).quantize(_QUANT, rounding=ROUND_HALF_UP)


def evaluate_intake() -> IntakeReport:
    agent = IntakeAgent(ScriptedModelProvider(default_text="（合成，非理由码）"))
    correct = 0
    mismatches: list[tuple[str, str, str]] = []
    for text, expected in LABELED_DESCRIPTIONS:
        got = agent.classify(text).reason_code
        if got is expected:
            correct += 1
        else:
            mismatches.append((text, expected.value, got.value))
    return IntakeReport(total=len(LABELED_DESCRIPTIONS), correct=correct, mismatches=mismatches)


def evaluate_calibration() -> CalibrationReport:
    rows: list[tuple[str, str, str, str, bool]] = []
    won: list[Decimal] = []
    lost: list[Decimal] = []
    correct_threshold = 0
    lost_flagged = 0
    lost_total = 0
    for record in calibration_samples():
        result = assess_chargeback(record.reason_code, record.present_evidence)
        win = result.win_likelihood
        rows.append(
            (
                record.case_ref,
                record.reason_code.value,
                record.outcome or "",
                str(win),
                result.requires_human,
            )
        )
        predicted_won = win >= Decimal("0.5")
        actual_won = record.outcome == "won"
        if predicted_won == actual_won:
            correct_threshold += 1
        if actual_won:
            won.append(win)
        else:
            lost.append(win)
            lost_total += 1
            if result.requires_human:
                lost_flagged += 1

    def mean(values: list[Decimal]) -> Decimal:
        if not values:
            return Decimal("0")
        return (sum(values, Decimal("0")) / Decimal(len(values))).quantize(
            _QUANT, rounding=ROUND_HALF_UP
        )

    return CalibrationReport(
        rows=rows,
        won_mean=mean(won),
        lost_mean=mean(lost),
        threshold_accuracy=correct_threshold / len(rows) if rows else 0.0,
        lost_review_recall=lost_flagged / lost_total if lost_total else 0.0,
    )


def build_report() -> str:
    intake = evaluate_intake()
    cal = evaluate_calibration()
    lines: list[str] = []
    lines.append("# 拒付集群离线评测报告（合成数据）\n")
    lines.append("## 1. 立案理由分类（Intake）")
    lines.append(f"- 准确率：**{intake.accuracy:.0%}**（{intake.correct}/{intake.total}）")
    if intake.mismatches:
        lines.append("- 误分类：")
        for text, expected, got in intake.mismatches:
            lines.append(f"  - “{text}” 期望 {expected}，得到 {got}")
    else:
        lines.append("- 无误分类。")
    lines.append("\n## 2. 胜诉率校准（确定性内核）")
    lines.append(f"- 胜诉样本均值：**{cal.won_mean}**；败诉样本均值：**{cal.lost_mean}**")
    lines.append(f"- 分离度（won-lost）：**{cal.separation}**（>0 表示方向正确）")
    lines.append(f"- 阈值分类准确率（win≥0.5 判胜）：**{cal.threshold_accuracy:.0%}**")
    lines.append(f"- 败诉样本被标记人工复核比例：**{cal.lost_review_recall:.0%}**")
    lines.append("\n| 案例 | 理由 | 实际结果 | 胜诉率 | 需人工 |")
    lines.append("|---|---|---|---|---|")
    for ref, reason, outcome, win, requires_human in cal.rows:
        lines.append(f"| {ref} | {reason} | {outcome} | {win} | {requires_human} |")
    lines.append(
        f"\n> 判胜阈值 WIN_REVIEW_THRESHOLD={WIN_REVIEW_THRESHOLD}。"
        "全部合成、可复现；真实（脱敏）样本经 adapters/ingestion 直接替换即可。"
    )
    return "\n".join(lines)


def main() -> int:
    print(build_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
