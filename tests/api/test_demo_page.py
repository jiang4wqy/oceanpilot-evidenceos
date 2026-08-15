from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app


def _client(tmp_path):
    return TestClient(
        create_app(Settings(db_path=tmp_path / "api.db")), raise_server_exceptions=False
    )


def test_demo_page_is_served_html(tmp_path):
    with _client(tmp_path) as client:
        resp = client.get("/demo")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "Oceanpayment · 商户工作台" in body
    assert "/api/v1/chargeback" in body  # the page drives the real API
    assert "人工确认并模拟提交" in body  # the safety boundary remains in the workflow


def test_demo_page_is_not_in_openapi(tmp_path):
    with _client(tmp_path) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert "/demo" not in paths


def test_root_redirects_to_demo(tmp_path):
    with _client(tmp_path) as client:
        r = client.get("/", follow_redirects=False)
        assert r.status_code in (302, 307)
        assert r.headers["location"] == "/demo"
        followed = client.get("/")
    assert followed.status_code == 200
    assert "Oceanpayment · 商户工作台" in followed.text


def test_demo_keeps_technical_endpoints_out_of_customer_navigation(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
        assert client.get("/docs").status_code == 200
        assert client.get("/health").status_code == 200
    assert 'href="/docs"' not in body
    assert 'href="/health"' not in body


def test_demo_separates_case_diagnosis_from_new_case_creation(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
    assert "历史案件" in body and "待补资料" in body
    assert "需要补交的资料" in body and "补交资料" in body
    assert "1. 选择常见案件模板" in body
    assert "确认创建案件" in body
    assert "材料尚未齐全" in body and "仍缺" in body
    assert "下一项优先补交" in body
    assert "本次无法提供，提交人工复核" in body
    assert "客户提出争议，创建案件" not in body
    assert "载入示例材料" not in body
    assert "补齐缺失材料" not in body
    assert "/safety/scan" in body  # PII guardrail remains available to the app
    assert "Visa 13.1" in body and "Visa 10.4" in body and "Mastercard 4853" in body
    assert "未收到货" in body and "非本人交易" in body and "商品不符" in body
    assert 'available:["transaction.receipt","fulfillment.tracking"]' in body
    assert 'available:["transaction.receipt","product.description"]' in body
    assert "规则证据就绪度" in body
    assert "预计胜诉概率" not in body
    assert 'api("GET","/cases")' in body
    assert "暂无有效案件记录" in body
    assert "CASE-20260814" not in body and "OP-20260814" not in body


def test_demo_uses_oceanpayment_console_language_without_ai_jargon(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
    assert "Oceanpayment" in body
    assert "--accent:#087a70" in body
    assert "案件中心" in body and "新建案件" in body and "交易风险" in body
    assert "案件诊断" in body and "查看诊断" in body
    assert "导出当前结果" not in body and "规则与配置" not in body
    assert "案件库有效实体" in body and "案件库可读" in body
    assert "需要商户补充" in body
    assert "已有 1 项 · 仍缺 5 项" in body
    assert "商户" in body and "OceanStore" in body
    assert "演示环境" not in body and "演示数据" not in body
    assert 'id="loc-zh"' not in body and 'id="loc-en"' not in body
    assert "智能体轨迹" not in body
    assert "确定性内核" not in body
    assert "toggleTheme" not in body
    assert 'class="ocean-logo"' in body
    assert 'src="data:image/png;base64,' in body
    assert ".material-row .material-state" in body
    assert (
        "setInterval(()=>{if($('v-overview').classList.contains('on'))loadCases();},5000)" in body
    )


def test_demo_supports_complete_zh_en_language_switching(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "demo.db"))
    with TestClient(app, raise_server_exceptions=False) as client:
        body = client.get("/demo").text

    assert 'id="languageSelect"' in body
    assert '<option value="zh">中文</option>' in body
    assert '<option value="en">English</option>' in body
    assert 'const COOKIE="oceanpilot_client_language"' in body
    assert "oceanpilot_admin_language" not in body
    assert 'document.cookie=COOKIE+"="' in body
    assert "setInterval(()=>{const cookieLanguage=readLanguage()" in body
    assert 'title_en="Oceanpayment · Merchant Workspace"' not in body
    assert '"案件中心":"Case center"' in body
    assert '"补交资料":"Submit evidence"' in body
    assert ".op-table .pill{max-width:150px;white-space:normal" in body
    assert ".op-table td:nth-child(3) .pill{min-width:138px}" in body
    assert "@media(max-width:1320px){.work-grid{grid-template-columns:1fr}" in body
    assert '"评估完成":"Assessment complete"' in body
    assert "window.addEventListener('oceanpilot:languagechange'" in body
    assert "loc:window.oceanI18n.getLanguage()" in body
