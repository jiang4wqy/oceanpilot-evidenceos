"""Offline HTTP walkthrough: A registration -> human review -> saved summary.

Uses the public workspace API and temporary SQLite files. All cases assume a
synthetic formal dispute; only material metadata is registered, no file body is
read. B demonstrates invalidated approval after withdrawal, C checks Visa 13.1.
No model credentials or network are used, even if live mode is set in the shell.

Run: python examples/chargeback_transcript.py
"""

import tempfile
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from oceanpilot.adapters.model.fake import ScriptedModelProvider
from oceanpilot.config import Settings
from oceanpilot.main import create_app

_BASE = "/api/v1/workspace"
_MERCHANT = {"X-Demo-Role": "MERCHANT", "X-Demo-Actor": "synthetic-merchant"}
_BUSINESS = {"X-Demo-Role": "BUSINESS", "X-Demo-Actor": "synthetic-business"}


def build(emit: Callable[[str], None] | None = None) -> list[str]:
    lines: list[str] = []

    def say(message: str = "") -> None:
        lines.append(message)
        if emit is not None:
            emit(message)

    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(
            Settings(db_path=Path(tmp) / "demo.db", mock_send_enabled=False),
            chargeback_model=ScriptedModelProvider(default_text="（离线合成输出）"),
        )
        with TestClient(app) as client:
            _run(client, say)
    return lines


def _command(client, action, data, *, case=None, business=False):
    payload = {"command_id": str(uuid4()), "action": action, "data": data, "confirmed": True}
    if case is not None:
        payload |= {"case_id": case["case_id"], "expected_revision": case["revision"]}
    response = client.post(
        f"{_BASE}/commands", json=payload, headers=_BUSINESS if business else _MERCHANT
    )
    response.raise_for_status()
    return response.json()


def _run(client: TestClient, say: Callable[[str], None]) -> None:
    say("═══ 双端案件工作台 — 合成正式争议：人工审核＋复核摘要 ═══")
    say("前提：假定已进入正式争议流程；普通支付失败或 3DS 挑战失败不能直接当作拒付。")
    say("仅登记合成材料元数据，未读取或核验真实文件正文。")

    say("\n【1】用户端：新建 A 样例副本")
    result = _command(client, "COPY_SAMPLE", {"sample": "A"})
    case = result["case"]
    case_id = case["case_id"]
    assert case["readiness"]["present"] == 5 and case["readiness"]["total"] == 6
    assert case["rule_reference"]["scheme_reason_code"] == "10.4"
    assert case["gate"]["status"] == "CRITICAL_MISSING"
    say(f"  案件 {case_id} @rev{case['revision']}｜Visa 10.4｜材料就绪度 5/6")
    gap = next(item for item in case["missing"] if item["critical"])
    say(f"  补问：请登记 {gap['label']}。{gap['why']}")
    say(f"  门槛：{case['gate']['reason']}")

    say("\n【2】用户端：登记剩余关键材料并核对回执")
    result = _command(
        client,
        "REGISTER_MATERIAL",
        {
            "evidence_code": gap["code"],
            "file_name": "synthetic-3ds-registration.txt",
            "source": "SYNTHETIC_TEMPLATE",
        },
        case=case,
    )
    case = result["case"]
    assert case["gate"]["status"] == "READY_FOR_REVIEW"
    assert case["gate"]["requires_human"] is True
    say(f"  操作回执：{result['receipt']['command_id']}｜版本 {case['revision']}")
    say("  材料就绪度 6/6；仅表示内部清单登记齐全，正文、真实性与内容一致性仍待核验。")

    say("\n【3】业务端：复核同一案件的当前版本")
    shared = client.get(f"{_BASE}/cases/{case_id}", headers=_BUSINESS)
    shared.raise_for_status()
    assert shared.json()["revision"] == case["revision"]
    result = _command(
        client,
        "REVIEW",
        {
            "decision": "APPROVED",
            "summary": "当前版本内部材料登记清单已复核；未读取真实正文，规则正式适用性待核验。",
            "scope": ["材料登记清单", "内部处理门槛", "规则引用来源"],
            "expected_rule_fingerprint": case["rule_fingerprint"],
        },
        case=case,
        business=True,
    )
    case = result["case"]
    assert case["review"]["status"] == "APPROVED"
    say(f"  人工登记复核：APPROVED @rev{case['revision']}；下一步为生成同版复核摘要。")
    say(f"  规则：Visa 10.4｜{case['rule_reference']['verification_status']}")

    say("\n【4】业务端：导出案件复核摘要（合成示例）")
    response = client.post(
        f"{_BASE}/cases/{case_id}/summaries",
        json={"expected_revision": case["revision"]},
        headers=_BUSINESS,
    )
    response.raise_for_status()
    summary = response.json()
    html = client.get(summary["html_url"], headers=_BUSINESS)
    snapshot = client.get(summary["json_url"], headers=_BUSINESS)
    html.raise_for_status()
    snapshot.raise_for_status()
    saved = snapshot.json()
    assert saved["revision"] == saved["case"]["revision"] == case["revision"]
    assert saved["case"]["review"]["status"] == "APPROVED"
    say(f"  HTML / JSON 已生成｜摘要 {summary['summary_id']}｜同一版本 {saved['revision']}")
    say("  摘要来自已保存的确定性快照，导出不调用模型；含未核验事项与合成说明。")

    say("\n【5】B 阻断检查：旧审核后撤回关键材料")
    blocked = _command(client, "COPY_SAMPLE", {"sample": "B"})["case"]
    assert blocked["review"]["stale"] is True
    assert blocked["gate"]["status"] == "CRITICAL_MISSING"
    assert blocked["gate"]["can_review"] is False
    say("  B：关键材料缺失；旧审核已失效并保留历史，当前版本不能通过登记复核。")

    say("\n【6】C 跨场景自测：Visa 13.1")
    cross = _command(client, "COPY_SAMPLE", {"sample": "C"})["case"]
    assert cross["rule_reference"]["scheme_reason_code"] == "13.1"
    say(
        f"  C：{cross['rule_reference']['display_name']}｜缺失项："
        + "、".join(item["label"] for item in cross["missing"])
    )
    say("  A / B / C 都通过后端新建副本，不清空数据库、不在浏览器修改进度。")
    say("\n完成：主演示止于人工登记复核＋摘要导出。默认最终模拟发送由后端关闭。")
    say("全程合成；不执行支付/退款/风控/提交动作。以上摘要在本次临时数据库中验证。")


def main() -> int:
    build(emit=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
