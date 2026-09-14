"""Member B regressions for the actual V2 decision and material UI contracts."""

import subprocess
from pathlib import Path

from tests.web.test_v2_rendering import run_js


def test_private_history_does_not_repeat_shared_questions():
    run_js(
        r"""
const ui=OceanV2;ui.state.role='MERCHANT';ui.state.isCasePage=true;ui.state.current={...sample};
ui.state.activity={legacy_read_only:true,run:{case_revision:2,prepared:{}},
 conversations:[{message:'SHARED-QUESTION',answer:'SHARED-ANSWER'}],
 legacy_conversations:[{message:'LEGACY-QUESTION',answer:'LEGACY-ANSWER'}]};
ui.renderAgentPanel();const output=node('agentToolsPanel').innerHTML;
assert.ok(output.includes('LEGACY-QUESTION'));
assert.equal(output.includes('SHARED-QUESTION'),false);
ui.state.activity.legacy_conversations=[];ui.renderAgentPanel();
assert.equal(node('agentToolsPanel').innerHTML.includes('SHARED-ANSWER'),false);
""",
        surface="merchant",
    )


def test_current_deadline_uses_current_task_and_closed_case_explains_history():
    run_js(
        r"""
const ui=OceanV2;ui.state.role='MERCHANT';ui.state.isCasePage=true;ui.state.tab='tasks';
ui.state.current={...sample,work_status:'OP_REVIEW',primary_action:null,
 current_task:{action:'REVIEW',
owner:{display_name:'风控'},
deadline:'2030-01-03T00:00:00Z',
deadline_status:'CONFIRMED'},
 deadlines:{merchant:'2030-01-02T00:00:00Z'},available_actions:[],
 deadline_summary:[{label:'OP 内部处理目标',
at:'2030-01-03T00:00:00Z',
status:'CONFIRMED',
explanation:'当前责任人的任务期限。'}]};
ui.state.plan={revision:2};ui.renderDetail();
const first=node('caseDetail').innerHTML
.match(/<section class="current-task"[\s\S]*?<\/section>/)[0];
ui.state.current.deadlines.merchant='2030-07-22T00:00:00Z';ui.renderDetail();
const second=node('caseDetail').innerHTML
.match(/<section class="current-task"[\s\S]*?<\/section>/)[0];
assert.equal(first,second);
ui.state.current.work_status='CLOSED';ui.renderDetail();
const closed=node('caseDetail').innerHTML;
assert.ok(closed.includes('历史期限（已结束，不再催办）'));
assert.equal(closed.includes('你的回应期限'),false);
ui.state.current.work_status='OP_REVIEW';
ui.state.current.current_task.deadline_status='NEEDS_CONFIRMATION';
ui.renderDetail();
assert.ok(node('caseDetail').innerHTML.includes('当前回应期限 <strong>尚未确认'));
""",
        surface="merchant",
    )


def test_guidance_keeps_authorization_empty_even_with_proposal_text():
    run_js(
        r"""
const ui=OceanV2;ui.state.role='MERCHANT';ui.state.current={...sample};
ui.openDialog('MERCHANT_DECISION',{reason:'我已获得授权'});
const output=node('dialogFields').innerHTML;
assert.ok(output.includes('未响应不代表同意'));
assert.ok(output.includes('不会自动退款或结案'));
assert.equal(output.includes('我已获得授权'),false);
assert.match(output,/<textarea[^>]*name="reason"[^>]*><\/textarea>/);
assert.equal(node('confirmCheckbox').checked,false);
""",
        surface="merchant",
    )


def test_revision_selector_transmits_selected_material_id_without_guessing():
    source = Path("src/oceanpilot/web/v2/collaboration.js").read_text()
    source = source.replace(
        "  globalThis.OceanV21Collaboration=",
        "  globalThis.probe={upload,uploadMarkup,renderFile,activate(s){active=s;}};\n"
        "  globalThis.OceanV21Collaboration=",
    )
    code = (
        r"""
const assert=require('node:assert/strict');
global.crypto=require('node:crypto').webcrypto;
global.sessionStorage={getItem(){return null},setItem(){},removeItem(){}};
"""
        + source
        + r"""
(async()=>{
const c={evidence:[{id:'old1',
code:'proof',
title:'不足版',
active:true},
{id:'old2',
code:'proof',
title:'另一文件',
active:true}],
available_actions:[{action:'REGISTER_EVIDENCE',
enabled:true}]};
const markup=probe.uploadMarkup(c,
[{code:'proof',
label:'签收',
expected_source:'MERCHANT_UPLOAD',
present:false}]);
assert.ok(markup.includes('请选择新增材料或要替换的文件'));
assert.ok(markup.includes('data-evidence-id="old1"'));
assert.ok(markup.includes('data-evidence-id="old2"'));
assert.ok(markup.includes('新增文件（保留已有文件）'));
const system=[{code:'system',label:'系统导出',expected_source:'SYSTEM_OF_RECORD'}];
assert.equal(probe.uploadMarkup({...c,view:'MERCHANT'},system).includes('value="system"'),false);
assert.ok(probe.uploadMarkup({...c,view:'OPERATIONS'},system).includes('value="system"'));
const meta=probe.renderFile({c:{participants:[{user_id:'u',display_name:'合成上传者'}]}},
{uploaded_by:'u',sha256:'abc123',size:42,mime_type:'application/json',content_check:{}});
assert.ok(meta.includes('合成上传者'));assert.ok(meta.includes('abc123'));
assert.ok(meta.includes('不证明文件来源'));
const selected={value:'replace:old1',dataset:{code:'proof',title:'签收',evidenceId:'old1'}};
const button={};
const form={elements:{material:{selectedOptions:[selected]},
file:{files:[{name:'corrected.json',
size:2,
type:'application/json',
arrayBuffer:async()=>Buffer.from('{}') }]}},
reportValidity:()=>true,
querySelector:()=>button,
reset(){}};
let sent;
const state={caseId:'c1',
revision:7,
host:{isConnected:true,
querySelector:()=>({classList:{toggle(){}}})},
api:async(path,
request)=>{sent=JSON.parse(request.body);
throw Object.assign(new Error('timeout'),
{uncertain:true});
}};
probe.activate(state);await probe.upload(state,form);
assert.equal(sent.evidence_id,
'old1');
assert.equal(sent.code,
'proof');
assert.equal(sent.expected_revision,
7);
const original=JSON.stringify(sent);
selected.dataset.evidenceId="old2";
await probe.upload(state,form);
assert.equal(JSON.stringify(state.uploadPending),original);
selected.dataset.evidenceId="old1";
await probe.upload(state,
form);
assert.equal(JSON.stringify(sent),
original);
})();
"""
    )
    result = subprocess.run(["node", "-"], input=code, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


def test_projected_merchant_samples_and_overview_deadlines():
    run_js(
        r"""
const ui=OceanV2;ui.state.role='MERCHANT';ui.state.isCasePage=true;ui.state.tab='evidence';
ui.state.current={...sample,channel:undefined,synthetic_samples_available:true};
ui.state.plan={checklist:[{code:'fulfillment.proof_of_delivery',
label:'签收证明',expected_fields:['delivered_at'],expected_source:'MERCHANT_UPLOAD'}]};
ui.renderDetail();let html=node('caseDetail').innerHTML;
assert.ok(html.includes('?variant=sufficient'));assert.ok(html.includes('?variant=wrong_transaction'));
ui.state.current.synthetic_samples_available=false;ui.renderDetail();
assert.equal(node('caseDetail').innerHTML.includes('?variant=sufficient'),false);
ui.state.tab='overview';ui.state.current.work_status='CLOSED';ui.renderDetail();
html=node('caseDetail').innerHTML;
assert.equal(html.includes('你的回应期限'),false);
assert.ok(html.includes('没有当前回应任务'));
""",
        surface="merchant",
    )
