"""End-to-end HTTP transcript of the chargeback cluster — one readable run.

Drives the FastAPI app in-process (offline, synthetic) over the *public* HTTP
surface and prints a human-readable transcript of the whole loop: pre-dispute
prevention → open case → (human-confirm reason) → evidence collection with SLA →
kernel assessment (with provenance + per-evidence breakdown) → representment
package → appeal (blocked, then human-approved) → audit trail.

No API key, no network, no business action — the strongest action is advising a
human review; appeal only submits to a *mock* upstream after explicit approval.

Run (needs the dev extra for the test client):  python examples/chargeback_transcript.py
"""

import tempfile
from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app

_BASE = "/api/v1/chargeback"
_MAX_ROUNDS = 50


def build(emit: Callable[[str], None] | None = None) -> list[str]:
    lines: list[str] = []

    def say(message: str = "") -> None:
        lines.append(message)
        if emit is not None:
            emit(message)

    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(db_path=Path(tmp) / "demo.db"))
        with TestClient(app) as client:
            _run(client, say)
    return lines


def _run(client: TestClient, say: Callable[[str], None]) -> None:
    say("═══ 跨境拒付申诉集群 — 端到端演示（合成数据，不执行任何业务动作）═══")

    say("\n【0】预防：交易前风险提示")
    prevention = client.post(
        f"{_BASE}/prevention/assess",
        json={"three_ds_authenticated": False, "avs_match": False, "amount": "4200"},
    ).json()
    say(f"  拒付风险：{prevention['risk_level']}（评分 {prevention['risk_score']}）")
    say("  命中因子：" + "、".join(prevention["factors"]))
    say("  建议现在留存：" + "、".join(e["label"] for e in prevention["recommended_evidence"]))
    say(f"  建议人工复核：{prevention['recommend_manual_review']}")

    say("\n【1】建案：商户描述问题")
    description = "客户下单后一直没收到货，现在要求拒付。"
    say(f"  商户：{description}")
    case = client.post(
        f"{_BASE}/cases",
        json={"description": description, "card_network": "VISA"},
    ).json()
    case_id = case["case_id"]
    say(f"  案件：{case_id}")
    say(f"  判定原因：{case['reason_code']}（已确认={case['reason_confirmed']}）")
    if case.get("deadline"):
        say(f"  举证时限：还剩 {case['deadline']['days_remaining']} 天")

    if case["phase"] == "REASON_PROPOSED":
        say("  → 原因不确定，等待人工确认…")
        case = client.post(f"{_BASE}/cases/{case_id}/confirm", json={}).json()
        say(f"  人工已确认原因：{case['reason_code']}")

    say("\n【2】补证：逐项收集（可随时“无法提供→转人工”）")
    body = case
    rounds = 0
    while body["phase"] == "NEED_EVIDENCE":
        say(f"  补问：{body['question']}")
        body = client.post(
            f"{_BASE}/cases/{case_id}/evidence",
            json={"evidence_code": body["next_evidence"]},
        ).json()
        rounds += 1
        if rounds > _MAX_ROUNDS:
            raise RuntimeError("evidence loop did not converge")

    say("\n【3】评估：确定性内核判定")
    a = body["assessment"]
    review = "需人工复核" if a["requires_human"] else "可自动推进"
    say(
        f"  规则证据就绪度：{a.get('evidence_readiness', a['win_likelihood'])}"
        f"（非胜诉概率）｜责任域：{a['responsible_team']}｜{review}"
    )
    checklist = " ".join(
        ("✅" if item["present"] else "❌") + ("⭐" if item["critical"] else "") + item["label"]
        for item in a["evidence_breakdown"]
    )
    say(f"  证据构成：{checklist}")
    say(f"  说明（来源={a['explanation_source']}）：{a['explanation']}")

    say("\n【4】打包：按银行模板生成 representment")
    pkg = client.get(f"{_BASE}/cases/{case_id}/package?card_network=VISA").json()
    say(
        f"  规则来源：{pkg['rule_source']}｜Visa {pkg['scheme_reason_code']}"
        f"｜完整度：{pkg['completeness']}"
        f"｜可提交：{pkg['ready_to_submit']}"
    )
    say("  随附证据：" + "、".join(e["label"] for e in pkg["ordered_evidence"]))
    say(f"  封面说明：{pkg['cover_note']}")

    say("\n【5】申诉：人工确认硬闸门")
    blocked = client.post(f"{_BASE}/cases/{case_id}/appeal", json={}).json()
    say(f"  未经批准提交 → submitted={blocked['submitted']}，原因={blocked['blocked_reason']}")
    approved = client.post(
        f"{_BASE}/cases/{case_id}/appeal",
        json={"human_approved": True, "actor_id": "ou_reviewer"},
    ).json()
    say(f"  人工批准后 → 已提交上游(mock)：submission_id={approved['submission_id']}")

    say("\n【6】审计：完整可追溯")
    audit = client.get(f"{_BASE}/cases/{case_id}/audit").json()
    for event in audit["events"]:
        detail = f"（{event['detail']}）" if event["detail"] else ""
        say(f"  #{event['seq']} {event['event_type']}{detail} @rev{event['case_revision']}")

    say("\n完成。全程合成数据；系统绝不执行支付/退款/风控/提交动作，最终以人工确认为准。")


def main() -> int:
    build(emit=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
