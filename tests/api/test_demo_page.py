"""Dual workspace routes and shipped HTML contracts.

State transitions, explicit confirmation, version/race boundaries, and command
recovery execute the actual packaged JavaScript in tests/web/test_page_runtime.py.
"""

import re
import shutil
import subprocess
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app


def _client(tmp_path, **settings):
    return TestClient(
        create_app(Settings(db_path=tmp_path / "api.db", **settings)),
        raise_server_exceptions=False,
    )


class PageElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


@pytest.mark.parametrize(
    ("path", "role", "title", "other"),
    [
        ("/demo", "MERCHANT", "Oceanpayment · 商户工作台", "/business"),
        ("/business", "BUSINESS", "Oceanpayment · 企业争议运营", "/demo"),
    ],
)
def test_both_workspaces_are_served_in_same_app_with_explicit_demo_role(
    tmp_path, path, role, title, other
):
    with _client(tmp_path) as client:
        response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert f"<title>{title}</title>" in body
    assert f'<body data-role="{role}">' in body
    assert f'const WORKSPACE_CONFIG={{"role":"{role}"}}' in body
    assert f'id="roleSwitch" href="{other}"' in body
    assert "演示角色，非生产身份认证。" in body
    assert "X-Demo-Role" in body and "X-Demo-Actor" in body
    assert f'value="synthetic-{role.lower()}" readonly' in body
    assert "/api/v1/workspace" in body


def test_html_routes_are_excluded_from_openapi_and_root_redirect_remains(tmp_path):
    with _client(tmp_path) as client:
        paths = client.get("/openapi.json").json()["paths"]
        response = client.get("/", follow_redirects=False)
        followed = client.get("/")
    assert "/demo" not in paths and "/business" not in paths
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/v2/operations"
    assert followed.status_code == 200


@pytest.mark.parametrize("path", ["/demo", "/business"])
def test_workspaces_keep_one_case_context_and_mark_unimplemented_navigation(tmp_path, path):
    with _client(tmp_path) as client:
        body = client.get(path).text
    page = PageElements()
    page.feed(body)
    ids = [attrs["id"] for _, attrs in page.elements if "id" in attrs]
    assert len(ids) == len(set(ids)), "Duplicate IDs break the shared case context"
    assert "v-workspace" in ids
    assert "v-diagnosis" not in ids and "v-flow" not in ids and "v-hub" not in ids
    assert {
        "section-summary",
        "section-materials",
        "section-rules",
        "section-concerns",
        "section-review",
    } <= set(ids)
    assert {
        "caseTitle",
        "caseRevision",
        "caseOwner",
        "diagStatus",
        "caseReviewBadge",
        "agentOutput",
        "summaryRows",
    } <= set(ids)
    planned = [attrs for tag, attrs in page.elements if tag == "button" and "disabled" in attrs]
    assert len(planned) >= 3
    assert all("onclick" not in attrs and "data-v" not in attrs for attrs in planned)
    assert "规划中" in body
    assert 'href="/docs"' not in body and 'href="/health"' not in body
    assert 'data-v="metrics"' not in body and 'data-v="support"' not in body


@pytest.mark.parametrize("path", ["/demo", "/business"])
def test_list_and_case_surfaces_expose_current_version_materials_and_history(tmp_path, path):
    with _client(tmp_path) as client:
        body = client.get(path).text
    for label in ["案件名称 / 编号", "当前阶段", "缺失项", "待谁处理", "当前版复核", "最近更新"]:
        assert f"<th>{label}</th>" in body
    for element_id in [
        "registeredMaterialRows",
        "withdrawnMaterialRows",
        "reviewHistory",
        "auditOut",
        "commandNotice",
    ]:
        assert f'id="{element_id}"' in body
    assert 'role="status" aria-live="polite"' in body
    assert 'class="skip-link" href="#mainContent"' in body
    assert 'id="mainContent" tabindex="-1"' in body
    assert "--accent:#087a70" in body
    assert 'src="data:image/png;base64,' in body


@pytest.mark.parametrize("path", ["/demo", "/business"])
def test_material_body_boundary_and_formal_dispute_premise_are_visible(tmp_path, path):
    with _client(tmp_path) as client:
        body = client.get(path).text
    assert "普通支付失败或 3DS 挑战失败不等于拒付" in body
    assert 'id="formalDisputeConfirm" type="checkbox"' in body
    assert "不上传或读取文件正文" in body
    assert "正文未读取 · 内容未核验" in body
    assert "清单完成度，不是胜诉率或业务准确率" in body
    assert "来源待确认" in body
    assert "file.name" in body
    assert "FileReader" not in body and "readAsText" not in body and "FormData" not in body
    assert 'id="evidenceSource"' in body
    assert 'id="withdrawModal" role="dialog" aria-modal="true"' in body


@pytest.mark.parametrize("path", ["/demo", "/business"])
def test_review_and_summary_are_explicit_and_final_send_has_no_client_path(tmp_path, path):
    with _client(tmp_path) as client:
        body = client.get(path).text
    assert 'id="reviewForm" class="business-only"' in body
    assert "预览本版本复核" in body and "确认写入复核决定" in body
    assert "材料登记清单" in body and "内部处理门槛" in body
    assert "案件复核摘要（合成示例）" in body
    assert "导出不会重新调用模型" in body
    assert "最终发送未开放。" in body
    app_script = next(
        script
        for script in re.findall(r"<script[^>]*>(.*?)</script>", body, flags=re.DOTALL)
        if "const WORKSPACE_CONFIG=" in script
    )
    assert "/appeal" not in app_script and "/package" not in app_script
    assert "generateSummary" in app_script
    assert "api('POST'" not in app_script  # all mutations use versioned workspace commands
    assert "runCommand('REVIEW'" in app_script


@pytest.mark.parametrize("path", ["/demo", "/business"])
def test_sample_reset_is_new_backend_copy_and_rules_have_return_context(tmp_path, path):
    with _client(tmp_path) as client:
        body = client.get(path).text
    for sample in "ABC":
        assert f"copySample('{sample}')" in body
    assert "Visa 10.4" in body and "Visa 13.1" in body
    assert "预先登记 5/6 项合成材料" in body
    assert "不会清空数据库" in body
    assert "返回原案件" in body
    assert "默认模板或相似条款当作正式依据" in body


@pytest.mark.parametrize("path", ["/demo", "/business"])
def test_workspaces_share_language_preference_across_roles(tmp_path, path):
    with _client(tmp_path) as client:
        body = client.get(path).text
    assert 'id="languageSelect"' in body
    assert '<option value="zh">中文</option>' in body
    assert '<option value="en">English</option>' in body
    assert 'const COOKIE="oceanpilot_workspace_language"' in body
    assert '"商户材料提交区":"Merchant materials workspace"' in body
    assert '"企业争议运营区":"Business dispute workspace"' in body
    assert "oceanpilot:languagechange" in body
    assert 'id="agentServiceStatus" class="helper" role="status" aria-live="polite"' in body
    assert 'onclick="analyzeCurrentCase()"' in body
    assert "onclick=\"analyzeCurrentCase('CASE_OPENED')\"" not in body
    assert '"案件复核摘要（合成示例）":"Case review summary (synthetic example)"' in body


def test_operations_console_is_secondary_and_uses_configured_origin(tmp_path):
    with _client(tmp_path, admin_origin="http://127.0.0.1:9555") as client:
        merchant = client.get("/demo").text
        business = client.get("/business").text
    for body in [merchant, business]:
        assert 'href="http://127.0.0.1:9555/admin"' in body
        assert "运行维护中心 ↗" in body
        assert 'href="/admin"' not in body


@pytest.mark.parametrize("path", ["/demo", "/business"])
def test_every_embedded_script_parses(tmp_path, path):
    with _client(tmp_path) as client:
        body = client.get(path).text
    node = shutil.which("node")
    assert node is not None, "Node.js is required for shipped script validation"
    for script in re.findall(r"<script[^>]*>(.*?)</script>", body, flags=re.DOTALL):
        result = subprocess.run(
            [node, "--check", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
