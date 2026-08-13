import re
from pathlib import Path

import pytest
from pypdf import PdfReader

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _submission_text() -> str:
    candidates = tuple((REPOSITORY_ROOT / "artifacts").glob("*.pdf"))
    assert len(candidates) == 1, "expected exactly one submission PDF"
    return "\n".join(page.extract_text() or "" for page in PdfReader(candidates[0]).pages)


@pytest.mark.parametrize(
    ("label", "pattern"),
    (
        (
            "comprehensive merchant-success-agent vision",
            r"综合商户成功(?:智能体|Agent)(?:愿景)?|"
            r"comprehensive merchant[- ]success agent",
        ),
        ("payment-incident slice", r"payment[ -]incident|支付异常"),
        ("chargeback slice", r"chargeback|拒付"),
        ("synthetic boundary", r"synthetic|合成数据"),
        (
            "OpenAPI path count",
            r"(?<!\d)19\s*(?:条\s*)?OpenAPI(?:\s*(?:路径|paths?))?",
        ),
        (
            "signed fixture",
            r"signed fixture|签名(?:飞书)?\s*fixture|经签名校验的本地\s*fixture",
        ),
        ("human confirmation", r"human confirmation|人工确认"),
        (
            "no-business-action boundary",
            r"no business action|不执行(?:任何)?业务动作|不触发(?:任何)?业务动作",
        ),
        (
            "real-Feishu-group verification boundary",
            r"real Feishu group not verified|"
            r"真实飞书(?:测试)?群(?:尚未|未)(?:完成)?验证|"
            r"尚未验证真实飞书(?:测试)?群",
        ),
    ),
)
def test_submission_pdf_states_the_combined_verified_scope_and_boundaries(label, pattern):
    text = _submission_text()
    assert re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL), (
        f"submission PDF is missing the current {label} fact"
    )


@pytest.mark.parametrize(
    ("label", "pattern"),
    (
        ("717-test baseline", r"(?<!\d)717(?!\d)"),
        ("1035-test baseline", r"(?<!\d)1035\s+tests?\b"),
        (
            "five-path API",
            r"(?<!\d)5\s*(?:条\s*)?API(?:\s*(?:路径|paths?))?",
        ),
        (
            "eight-path OpenAPI",
            r"(?<!\d)8\s*(?:条\s*)?OpenAPI(?:\s*(?:路径|paths?))?",
        ),
        ("deferred diagnosis HTTP status", r"HTTP\s*501"),
        ("deferred diagnosis code", r"FEATURE_DEFERRED"),
        (
            "diagnosis described as unimplemented",
            r"(?:diagnosis|诊断).{0,24}"
            r"(?:unimplemented|not implemented|未实现|尚未接入|未接入)"
            r"|(?:尚未|未)接入.{0,12}诊断(?:主链)?",
        ),
        (
            "Feishu callbacks described as unimplemented",
            r"(?:Feishu callbacks?|飞书(?:事件|卡片)?回调).{0,24}"
            r"(?:unimplemented|not implemented|未实现|尚未接入|未接入)"
            r"|完整飞书闭环按阶段接入",
        ),
    ),
)
def test_submission_pdf_rejects_stale_foundation_milestone_claims(label, pattern):
    text = _submission_text()
    assert not re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL), (
        f"submission PDF still contains stale claim: {label}"
    )
