import json
import re
import shutil
import subprocess

from fastapi.testclient import TestClient

from oceanpilot.config import Settings
from oceanpilot.main import create_app


def _client(tmp_path):
    return TestClient(
        create_app(Settings(db_path=tmp_path / "api.db")), raise_server_exceptions=False
    )


def _embedded_app_script(body: str) -> str:
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", body, flags=re.DOTALL)
    return next(script for script in scripts if 'const BASE="/api/v1/chargeback"' in script)


def _js_function(script: str, name: str) -> str:
    marker = script.index(f"function {name}")
    start = (
        marker - len("async ")
        if script[max(0, marker - len("async ")) : marker] == "async "
        else marker
    )
    opening = script.index("{", start)
    depth = 0
    for index in range(opening, len(script)):
        if script[index] == "{":
            depth += 1
        elif script[index] == "}":
            depth -= 1
            if depth == 0:
                return script[start : index + 1]
    raise AssertionError(f"unterminated JavaScript function: {name}")


def _run_node(source: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    assert node is not None, "Node.js is required to validate the embedded demo script"
    return subprocess.run(
        [node, "-"],
        input=source,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
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
    assert "cleanCopy(a.explanation)" not in body
    assert "AI 说明不会改变材料就绪度、责任团队或人工闸门" in body
    assert 'api("GET","/cases")' in body
    assert "暂无有效案件记录" in body
    assert "CASE-20260814" not in body and "OP-20260814" not in body


def test_demo_keeps_oceanpayment_visual_baseline_with_hub_and_rules(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
    assert "Oceanpayment" in body
    assert "--canvas:#f5f7f5" in body
    assert "--side:#fff" in body
    assert "--accent:#087a70" in body
    assert "--crit:#c84646" in body
    assert "Ivory Ledger" not in body and "--canvas:#F5F2EB" not in body
    assert 'class="skip-link" href="#mainContent"' in body
    assert 'id="mainContent" tabindex="-1"' in body
    assert "view.focus({preventScroll:true})" in body
    assert "AI 运营中枢" in body and "支付异常" in body and "规则知识" in body
    assert "onclick=\"showView('overview')\">进入支付异常主线" in body
    assert 'id="v-incidents"' not in body and 'data-v="incidents"' not in body
    assert "异常事件队列" not in body and "Processing Path" not in body
    assert '<div class="brand-product">案件诊断系统</div>' in body
    assert 'data-v="overview" role="button" tabindex="0">案件中心' in body
    assert 'data-v="create" role="button" tabindex="0">新建案件' in body
    assert "案件中心" in body and "新建案件" in body and "交易风险" in body
    assert "案件诊断" in body and "查看诊断" in body
    assert "导出当前结果" not in body and "规则与配置" not in body
    assert "案件库有效实体" in body and "案件库可读" in body
    assert "需要商户补充" in body
    assert "已有 1 项 · 仍缺 5 项" in body
    assert "商户" in body and "OceanStore" in body
    assert "Synthetic Demo" in body and "UNVERIFIED_SUMMARY" in body
    assert "Curated rules prototype" in body and "本地规则知识库原型" in body
    assert "Backend Ready · 10 / 3" in body
    assert "onclick=\"showView('rules')\"" in body
    assert "Proprietary rules prototype" not in body and "专有规则数据库" not in body
    assert 'id="loc-zh"' not in body and 'id="loc-en"' not in body
    assert "智能体轨迹" not in body
    assert "确定性规则约束" in body
    assert "不展示思维链" in body
    assert "toggleTheme" not in body
    assert "--rule:" not in body and "var(--rule)" not in body
    assert "openAdminConsole" not in body and "openActiveAudit" not in body
    assert 'class="ocean-logo"' in body
    assert 'src="data:image/png;base64,' in body
    assert ".material-row .material-state" in body
    assert (
        "setInterval(()=>{if($('v-overview').classList.contains('on'))loadCases();},5000)" in body
    )


def test_embedded_demo_javascript_parses_independently(tmp_path):
    with _client(tmp_path) as client:
        script = _embedded_app_script(client.get("/demo").text)
    node = shutil.which("node")
    assert node is not None, "Node.js is required to validate the embedded demo script"
    result = subprocess.run(
        [node, "--check", "-"],
        input=script,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_rule_reference_helpers_execute_with_exact_ids_and_return_context(tmp_path):
    with _client(tmp_path) as client:
        script = _embedded_app_script(client.get("/demo").text)
    source = "\n".join(
        (
            _js_function(script, "ruleReferencePath"),
            _js_function(script, "ruleDetailPath"),
            _js_function(script, "normalizeRuleReturnContext"),
            "console.log(JSON.stringify({",
            "path:ruleReferencePath('case id/1','visa'),",
            "blank:ruleReferencePath('case-7',''),",
            "detail:ruleDetailPath('visa-13-1-demo-v1'),",
            "context:normalizeRuleReturnContext({sourceView:'diagnosis',caseId:'case-7',cardNetwork:'mc'})",
            "}));",
        )
    )
    result = _run_node(source)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "path": "/cases/case%20id%2F1/rule-reference?card_network=VISA",
        "blank": "",
        "detail": "/rules/visa-13-1-demo-v1",
        "context": {
            "sourceView": "diagnosis",
            "caseId": "case-7",
            "cardNetwork": "MC",
        },
    }


def test_rule_reference_round_trip_keeps_package_output_and_exact_id(tmp_path):
    with _client(tmp_path) as client:
        script = _embedded_app_script(client.get("/demo").text)
    source = "\n".join(
        (
            "const classList={add(){},remove(){},toggle(){}};",
            "const elements={",
            "ruleSearch:{value:'old'},ruleScheme:{value:'VISA'},",
            "pkgOut:{innerHTML:'<package>generated</package>'},",
            "verdictBody:{innerHTML:'<assessment><package>generated</package></assessment>'},",
            "ruleDetail:{innerHTML:'',classList},crumbId:{textContent:''}};",
            "const $=id=>elements[id]||(elements[id]={value:'',innerHTML:''});",
            "const document={querySelectorAll(){return[]}};",
            "const S={ruleReturnContext:null,currentRuleId:null,caseId:'case-7',",
            "last:{case_id:'case-7'},selectedCase:null,cardNetwork:'VISA',",
            "ruleDetailRequestId:0};",
            "const shown=[];let applyCalls=0;const opened=[];const apiPaths=[];",
            "function showView(view){shown.push(view)}",
            "function apply(){applyCalls+=1;elements.verdictBody.innerHTML='<rerendered>'}",
            "async function openStoredCase(caseId){opened.push(caseId)}",
            "async function api(method,path){",
            "apiPaths.push(path);return{ok:false,status:404,data:{}}}",
            _js_function(script, "ruleDetailPath"),
            _js_function(script, "normalizeRuleReturnContext"),
            _js_function(script, "markRuleSelection"),
            _js_function(script, "openRule"),
            _js_function(script, "showRuleReference"),
            _js_function(script, "returnFromRuleReference"),
            "(async()=>{",
            "const packageData={rule_version_id:'visa-13-1-demo-v1'};",
            "showRuleReference(packageData.rule_version_id,{sourceView:'flow',caseId:'case-7',cardNetwork:'VISA'});",
            "const selectedId=S.currentRuleId;",
            "await openRule(selectedId);",
            "await returnFromRuleReference();",
            "console.log(JSON.stringify({selectedId,apiPaths,shown,applyCalls,opened,packageHtml:$('pkgOut').innerHTML,verdictHtml:$('verdictBody').innerHTML}));",
            "})().catch(error=>{console.error(error);process.exit(1)});",
        )
    )
    result = _run_node(source)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "selectedId": "visa-13-1-demo-v1",
        "apiPaths": ["/rules/visa-13-1-demo-v1"],
        "shown": ["rules", "flow"],
        "applyCalls": 0,
        "opened": [],
        "packageHtml": "<package>generated</package>",
        "verdictHtml": "<assessment><package>generated</package></assessment>",
    }


def test_unselected_network_does_not_request_or_render_rule_link(tmp_path):
    with _client(tmp_path) as client:
        script = _embedded_app_script(client.get("/demo").text)
    source = "\n".join(
        (
            "const elements={network:{value:'VISA'},diagnosisNetwork:{value:''},",
            "diagnosisRuleReferenceOut:{innerHTML:''}};",
            "const $=id=>elements[id]||(elements[id]={value:'',innerHTML:''});",
            "const S={caseId:'case-flow',selectedCase:{case_id:'case-diagnosis'},cardNetwork:''};",
            "let apiCalls=0;async function api(){apiCalls+=1;return{ok:true,data:{}}}",
            _js_function(script, "ruleReferenceTarget"),
            _js_function(script, "resolveCaseRuleReference"),
            "resolveCaseRuleReference('diagnosis').then(()=>console.log(JSON.stringify({apiCalls,hasLink:$('diagnosisRuleReferenceOut').innerHTML.includes('showRuleReference')}))).catch(error=>{console.error(error);process.exit(1)});",
        )
    )
    result = _run_node(source)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"apiCalls": 0, "hasLink": False}


def test_demo_deep_links_real_rule_versions_and_preserves_case_context(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
    assert 'cardNetwork:""' in body
    assert "<option value=\"\" ${S.cardNetwork===''?'selected':''}>请选择卡组织</option>" in body
    assert 'id="diagnosisNetwork"' in body
    assert "/card-network`" in body
    assert "expected_revision:current.revision" in body
    assert "resolveCaseRuleReference('diagnosis')" in body
    assert "function ruleReferencePath" in body
    assert "/rule-reference?card_network=${encodeURIComponent(network)}" in body
    assert "data.match_status!=='EXACT_MATCH'" in body
    assert "没有使用相似规则代替" in body
    assert "function showRuleReference(ruleVersionId,returnContext)" in body
    assert "$('ruleSearch').value=''" in body and "$('ruleScheme').value=''" in body
    assert "data-rule-version-id" in body and "rule-selected" in body
    assert "reference-highlight" in body and "detail.focus({preventScroll:true})" in body
    assert "function returnFromRuleReference" in body
    assert "返回案件诊断" in body and "返回案件详情" in body
    assert "规则数据库暂不可用" in body and "旧详情已清除" in body
    assert "openRuleFromPackage" not in body
    assert "showRuleReference('${esc(data.rule_version_id)}',ruleReturnContext('flow'))" in body
    assert "ruleReturnContext('${target.sourceView}')" in body


def test_demo_retains_human_review_and_duplicate_submission_guards(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
    assert "caseCreating:false,evidenceSubmitting:false" in body
    assert "if(S.caseCreating)return" in body
    assert "while(current.phase==='NEED_EVIDENCE'&&S.autoEvidence.length)" in body
    assert "evidenceSubmittingCases:new Set()" in body
    assert "S.evidenceSubmittingCases.has(caseId)" in body
    assert "S.selectedCase&&S.selectedCase.case_id===draft.caseId" in body
    assert "sourceTransaction" not in body and "sourceCaseId" not in body
    assert 'id="formalNoticeConfirm"' not in body
    assert "普通客户投诉只能进入预争议分流" not in body
    assert "建案已阻断" not in body
    assert 'id="actorId"' in body and "需要复核人 Actor ID" in body
    assert 'id="appealOut" class="mt" aria-live="polite"' in body
    assert 'actor_id:"ou_reviewer"' not in body
    assert 'id="submitAppealButton"' in body and "S.appealed" in body
    assert 'id="diagnosisAlert" role="status" aria-live="polite"' in body
    assert 'id="preventionOut" class="mt" aria-live="polite"' in body
    assert "本次 mock 回执" in body
    assert "function agentReviewDecision" in body
    assert "decision.audit_event_id" in body


def test_demo_exposes_copilot_judgment_and_agent_trace(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
    assert "OceanPilot Agent" in body
    assert "/api/v1/agent/turns" in body
    assert "AI 判断总结" in body
    assert "Agent 可视化执行轨迹" in body
    assert "DeepSeek Live" in body and "Offline Fallback" in body
    assert 'id="agentTurnStatus" role="status" aria-live="polite"' in body
    assert "Agent 正在分析…" in body
    assert "请勿输入真实卡号" in body


def test_case_diagnosis_hosts_context_agent_and_explicit_evidence_submission(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
    hub = body.split('id="v-hub"', 1)[1].split('id="v-overview"', 1)[0]
    overview = body.split('id="v-overview"', 1)[1].split('id="v-diagnosis"', 1)[0]
    diagnosis = body.split('id="v-diagnosis"', 1)[1].split('id="v-create"', 1)[0]
    assert "OceanPilot Agent" not in hub
    assert "OceanPilot Agent" not in overview
    assert "OceanPilot Agent" in diagnosis and "围绕当前案件持续分析与建议" in diagnosis
    assert "进入 AI 分析" in overview and "后续提问不会重复建案" in body
    assert "case_id:caseId" in body
    assert 'id="agentHistory"' in body and "appendAgentMessage('assistant'" in body
    assert "确认写入案件" in body and "confirmAgentReview" in body
    assert "EVIDENCE_SUBMITTED" in body and "REVIEW_CONFIRMED" in body
    assert 'id="evidenceModal" role="dialog" aria-modal="true"' in body
    assert 'type="file" id="evidenceFile"' in body
    assert "使用 Synthetic 演示文件" in body
    assert "3. 确认提交资料" in body
    assert "形式校验" in body and "写入案件资料状态" in body and "重新执行规则检查" in body
    assert "资料提交成功" in body
    assert "submitDiagnosticEvidence" not in body


def test_demo_queues_agent_input_and_releases_evidence_modal_before_reanalysis(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text

    assert "pendingAgentTurn:null" in body
    assert "你的输入已排队，将在当前分析完成后自动发送" in body
    assert "function acceptAgentUserMessage(message)" in body
    assert "if(input.value.trim()===message)input.value=''" in body
    assert "已有一条人工输入等待分析；当前输入已保留" in body
    release = body.index("S.evidenceSubmittingCases.delete(draft.caseId)")
    reanalysis = body.index("await bindAgentCase(draft.caseId,false)")
    assert release < reanalysis


def test_demo_does_not_claim_materials_are_complete_before_reason_confirmation(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text

    assert "awaitingReason?'待确认原因'" in body
    assert "确认原因后生成材料清单</span>" in body


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
    assert (
        ".op-table .action-cell .tbtn{display:inline-flex;align-items:center;"
        "justify-content:center;width:118px" in body
    )
    assert "@media(max-width:1320px){.work-grid{grid-template-columns:1fr}" in body
    assert '"评估完成":"Assessment complete"' in body
    assert '"3DS 认证结果":"3DS authentication result"' in body
    assert '"AVS 地址验证结果":"AVS result"' in body
    assert '"CVV 校验结果":"CVV result"' in body
    assert '"设备/IP 匹配":"Device/IP match"' in body
    assert "Requested evidence: ${translate(m[1])}" in body
    assert "window.addEventListener('oceanpilot:languagechange'" in body
    assert "loc:window.oceanI18n.getLanguage()" in body


def test_evidence_modal_requires_explicit_confirmation_and_stays_synthetic(tmp_path):
    with _client(tmp_path) as client:
        script = _embedded_app_script(client.get("/demo").text)
        body = client.get("/demo").text

    assert 'id="evidenceModal"' in body
    assert 'id="evidenceFile"' in body
    assert 'id="evidenceSubmitButton"' in body
    assert "使用 Synthetic 演示文件" in body
    assert "不读取文件内容、不上传对象存储" in body
    assert 'id="evidenceSubmitProgress" aria-live="polite"' in body
    assert ".modal-backdrop" in body
    assert "event.key==='Escape'" in body
    assert "closeEvidenceModal()" in body

    open_function = _js_function(script, "openEvidenceModalForCase")
    select_function = _js_function(script, "useSyntheticEvidenceFile")
    confirm_function = _js_function(script, "submitEvidenceModal")
    assert "api(" not in open_function
    assert "api(" not in select_function
    assert "button.disabled=true" in open_function
    assert "S.dialogTrigger=document.activeElement" in open_function
    assert "evidenceSubmitButton').disabled=false" in select_function
    assert "evidenceDraft.fileName" in select_function
    assert "api('POST',`/cases/${draft.caseId}/evidence`" in confirm_function
    assert "{evidence_code:draft.code}" in confirm_function
    assert "evidenceReceipt" in confirm_function


def test_latest_evidence_reconstruction_handles_withdrawal_history(tmp_path):
    with _client(tmp_path) as client:
        script = _embedded_app_script(client.get("/demo").text)
    source = "\n".join(
        (
            "const S={auditByCase:new Map([['case-1',[",
            "{event_type:'EVIDENCE_ADDED',detail:'a'},",
            "{event_type:'EVIDENCE_ADDED',detail:'b'},",
            "{event_type:'EVIDENCE_WITHDRAWN',detail:'b'},",
            "{event_type:'EVIDENCE_ADDED',detail:'c'}]]])};",
            _js_function(script, "latestActiveEvidence"),
            "console.log(latestActiveEvidence('case-1',['a','c']));",
        )
    )
    result = _run_node(source)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "c"


def test_withdrawal_ui_is_two_step_and_sends_the_expected_code(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
        script = _embedded_app_script(body)
    assert 'id="withdrawModal"' in body
    assert "确认撤回最近资料" in body
    assert "撤回会写入审计" in body
    assert "撤回最近资料" in body
    assert 'EVIDENCE_WITHDRAWN:"材料已撤回"' in body
    open_function = _js_function(script, "openWithdrawModal")
    confirm_function = _js_function(script, "confirmEvidenceWithdrawal")
    assert "classList.add('on')" in open_function
    assert "api(" not in open_function
    assert "/evidence/withdraw-latest`" in confirm_function
    assert "{evidence_code:state.code}" in confirm_function
    assert "CONCURRENT_CASE_WRITE" in confirm_function


def test_return_to_case_center_is_navigation_only(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/demo").text
        script = _embedded_app_script(body)
    function = _js_function(script, "returnToCaseCenter")
    assert function == "function returnToCaseCenter(){showView('overview');}"
    assert "api(" not in function
    assert body.count('onclick="returnToCaseCenter()"') >= 2
