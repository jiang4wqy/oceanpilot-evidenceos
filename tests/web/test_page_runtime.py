"""Execute the packaged vanilla-JS state and transport boundaries in Node."""

import json
import shutil
import subprocess

from oceanpilot.web.rendering import resource_text

DOM_STUB = """
const nodes = new Map();
function node(id) {
  if (!nodes.has(id)) {
    const classes=new Set();
    nodes.set(id, {
      id, value: ['statusFilter','ownerFilter'].includes(id) ? 'ALL' : '',
      textContent: '', innerHTML: '', options: [], disabled: false, hidden:false,
      checked:false, className: '', isConnected: true, dataset:{},style:{},
      classList: {add(c) {classes.add(c);}, remove(c) {classes.delete(c);},
        toggle(c,on) {if(on)classes.add(c);else classes.delete(c);},
        contains(c) {return classes.has(c);}},
      addEventListener() {}, setAttribute() {}, removeAttribute() {}, focus() {},
      querySelector: selector=>node(id+selector),scrollIntoView() {},
      insertAdjacentHTML() {}, remove() { this.removed=true; }, appendChild() {},
    });
  }
  return nodes.get(id);
}
global.document = {getElementById: node, querySelector: node, querySelectorAll: () => [],
  addEventListener() {}, activeElement: node('active')};
global.window = {oceanI18n: {getLanguage: () => 'zh',
 translate: s => s, translateTo:s=>s, apply() {}},

  addEventListener() {}};
global.location=new URL('http://localhost/demo');
global.history={pushState(_,__,url){global.location=new URL(url,location.origin);},
  replaceState(_,__,url){global.location=new URL(url,location.origin);}};
global.requestAnimationFrame=callback=>callback();
global.setInterval = () => 0;
const stored=new Map();
global.sessionStorage={getItem:k=>stored.get(k),
setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)};

global.crypto=require('node:crypto').webcrypto;
"""


def _execute(paths: tuple[str, ...], assertions: str, *, role="MERCHANT") -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for page runtime regression tests"
    source = "\n".join(
        (
            "const assert = require('node:assert/strict');",
            DOM_STUB,
            f"const WORKSPACE_CONFIG={json.dumps({'role': role})};",
            *(resource_text(path) for path in paths),
            f"(async () => {{\n{assertions}\n}})().catch(error => {{"
            "console.error(error); process.exitCode = 1;});",
        )
    )
    result = subprocess.run(
        [node, "-"], input=source, capture_output=True, text=True, timeout=10, check=False
    )
    assert result.returncode == 0, result.stderr


STATE = ("merchant/case-state.js", "merchant/state.js")


def test_case_views_share_one_snapshot_and_reject_stale_or_cross_case_data():
    _execute(
        STATE,
        """
selectCase('a');
assert.equal(acceptCaseSnapshot({case_id:'a', revision:2, card_network:'VISA'}), true);
S.agentBoundCaseId='a';
const ticket=caseContext.capture();
assert.equal(S.selectedCase, S.last);
assert.equal(S.last, S.agentCase);
assert.equal(S.caseRevision, 2);
assert.equal(acceptCaseSnapshot({case_id:'a', revision:1}), false);
assert.equal(acceptCaseSnapshot({case_id:'b', revision:99}), false);
assert.equal(acceptCaseSnapshot({case_id:'a'}), false);
assert.equal(S.caseRevision, 2);
assert.equal(acceptCaseSnapshot({case_id:'a', revision:3, card_network:'MASTERCARD'}), true);
assert.equal(S.agentCase.revision, 3);
assert.equal(S.caseSnapshot.card_network, 'MASTERCARD');
assert.equal(caseContext.isCurrent(ticket), false);
selectCase('b');
assert.equal(S.caseSnapshot, null);
assert.equal(S.agentCase, null);
selectCase('a');
acceptCaseSnapshot({case_id:'a', revision:2});
assert.equal(caseContext.isCurrent(ticket, false), false);
assert.equal(Object.getOwnPropertyDescriptor(S,'selectedCase').set, undefined);
""",
    )


def test_transport_single_flight_releases_after_failure_without_retrying():
    _execute(
        ("shared/request.js",),
        """
let calls=0, reject;
const operation=()=>{calls++; return new Promise((_, fail)=>{reject=fail;});};
const first=OceanRequest.singleFlight('write',operation);
const duplicate=OceanRequest.singleFlight('write',operation);
assert.equal(first,duplicate);
await Promise.resolve();
assert.equal(calls,1);
reject(new Error('failed'));
await assert.rejects(first,/failed/);
await OceanRequest.singleFlight('write',()=>{calls++; return 'recovered';});
assert.equal(calls,2);
const a=OceanRequest.begin('case-open');
const b=OceanRequest.begin('case-open');
assert.equal(OceanRequest.isLatest(a),false);
assert.equal(OceanRequest.isLatest(b),true);
""",
    )


def test_transport_timeout_covers_fetch_and_body_and_never_retries_a_write():
    _execute(
        ("shared/request.js",),
        """
let calls=0, signal;
global.fetch=(_, options)=>{calls++; signal=options.signal; return new Promise((_, reject)=>{
  signal.addEventListener('abort',()=>reject(new Error('aborted')));
});};
let result=await OceanRequest.json('/write',{method:'POST'},5);
assert.equal(result.ok,false);
assert.equal(result.status,0);
assert.equal(result.timedOut,true);
assert.equal(signal.aborted,true);
assert.equal(calls,1);
global.fetch=(_, options)=>{calls++; signal=options.signal;
  return Promise.resolve({ok:true,status:200,json:()=>new Promise(()=>{})});};
result=await OceanRequest.json('/read',{},5);
assert.equal(result.timedOut,true);
assert.equal(signal.aborted,true);
assert.equal(calls,2);
global.fetch=async()=>({ok:false,status:409,json:async()=>({code:'CONCURRENT_CASE_WRITE'})});
result=await OceanRequest.json('/write',{method:'POST'},50);
assert.equal(result.status,409);
assert.equal(result.data.code,'CONCURRENT_CASE_WRITE');
""",
    )


def test_late_case_open_cannot_replace_a_newer_case_selection():
    _execute(
        ("shared/request.js", *STATE, "merchant/cases.js", "merchant/rules.js"),
        """
const pending=new Map(), rendered=[];
global.workspaceApi=(_,path)=>new Promise(resolve=>pending.set(path,resolve));
renderStoredDiagnosis=data=>rendered.push(data.case_id);
showView=()=>{};
global.bindAgentCase=async()=>true;
global.analyzeCurrentCase=async()=>{};
const first=openStoredCase('a');
const second=openStoredCase('b');
pending.get('/cases/b')({ok:true,data:{case_id:'b',revision:2}});
await second;
pending.get('/cases/a')({ok:true,data:{case_id:'a',revision:1}});
await first;
assert.equal(S.caseId,'b');
assert.equal(S.caseRevision,2);
assert.deepEqual(rendered,['b']);
""",
    )


def test_agent_binding_uses_canonical_case_and_cannot_bind_a_different_case():
    _execute(
        (*STATE, "merchant/agent-review.js"),
        """
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:1});
assert.equal(await bindAgentCase('a'),true);
selectCase('b');acceptCaseSnapshot({case_id:'b',revision:4});
assert.equal(await bindAgentCase('a'),false);
assert.equal(S.caseId,'b');
assert.equal(S.agentCase,S.caseSnapshot);
""",
    )


def test_late_agent_turn_cannot_render_over_a_newer_case_revision():
    _execute(
        ("shared/request.js", *STATE, "merchant/agent-review.js"),
        """
let resolve, renders=0;
global.requestJson=()=>new Promise(done=>{resolve=done;});
global.loadCases=async()=>{};
renderAgentTurn=()=>{renders++;};
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:1});S.agentBoundCaseId='a';
const turn=runAgentTurn('explain');
acceptCaseSnapshot({case_id:'a',revision:2});
resolve({ok:true,data:{case_id:'a',case_revision:1}});
await turn;
assert.equal(renders,0);
assert.equal(S.caseRevision,2);
assert.equal(S.agentSubmitting,false);
assert.equal(node('agentSendButton').disabled,false);
""",
    )


def test_switching_cases_queues_the_new_agent_turn_without_old_case_output():
    _execute(
        ("shared/request.js", *STATE, "merchant/agent-review.js"),
        """
const pending=[], rendered=[];
global.requestJson=(_,method,path,payload)=>new Promise(resolve=>pending.push({payload,resolve}));
global.loadCases=async()=>{};
renderAgentTurn=data=>rendered.push(data.case_id);
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:1});S.agentBoundCaseId='a';
const first=runAgentTurn('explain A');
selectCase('b');acceptCaseSnapshot({case_id:'b',revision:5});S.agentBoundCaseId='b';
await runAgentTurn('explain B','CASE_OPENED');
assert.equal(pending.length,1);
assert.equal(S.pendingAgentTurn.caseId,'b');
pending[0].resolve({ok:false,status:503});
await new Promise(setImmediate);
assert.equal(pending.length,2);
assert.equal(pending[1].payload.case_id,'b');
assert.equal(S.agentMessages.length,0);
pending[1].resolve({ok:true,data:{case_id:'b',case_revision:5}});
await first;
assert.deepEqual(rendered,['b']);
assert.equal(S.caseId,'b');
assert.equal(S.agentSubmitting,false);
assert.equal(S.pendingAgentTurn,null);
""",
    )


def test_new_snapshot_invalidates_review_draft_and_analysis_but_equal_revision_does_not():
    _execute(
        STATE,
        """
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:1});
S.reviewDraft={caseId:'a',revision:1};S.lastAgentTurn={case_id:'a',case_revision:1};
node('reviewProposal').innerHTML='version 1 review';
acceptCaseSnapshot({case_id:'a',revision:1});
assert.notEqual(S.reviewDraft,null);
assert.notEqual(S.lastAgentTurn,null);
acceptCaseSnapshot({case_id:'a',revision:2});
assert.equal(S.reviewDraft,null);
assert.equal(S.lastAgentTurn,null);
assert.equal(node('reviewProposal').innerHTML,'');
assert.match(node('agentOutput').innerHTML,/旧版分析/);
""",
    )


def test_operations_polling_shares_one_inflight_refresh_and_recovers():
    # Run the actual operations module, including its initial automatic refresh.
    console = resource_text("operations/console.js").replace(
        "__CLIENT_BASE__", json.dumps("http://127.0.0.1:8002")
    )
    _execute(
        ("shared/request.js",),
        """
let calls=0, resolve;
global.fetch=()=>{calls++;return new Promise(done=>{resolve=done;});};
"""
        + console
        + """
const first=loadOverview(), second=loadOverview();
await Promise.resolve();
assert.equal(calls,1);
assert.equal(node('refresh').disabled,true);
resolve({ok:false,status:503,json:async()=>({})});
await Promise.all([first,second]);
assert.equal(node('refresh').disabled,false);
const retry=loadOverview();await Promise.resolve();
assert.equal(calls,2);
resolve({ok:true,status:200,json:async()=>({
 service_status:{overall:'HEALTHY'},request_summary:{total:0,p95_latency_ms:0,server_errors:0},
 endpoints:[],predictions:[],business_counts:{},cases:[],generated_at:'2026-09-06T00:00:00Z'
})});
await retry;
assert.equal(node('refresh').disabled,false);
assert.equal(DATA.service_status.overall,'HEALTHY');
""",
    )


def test_command_timeout_queries_receipt_before_same_id_retry_and_disables_duplicate_write():
    _execute(
        ("shared/request.js", *STATE, "merchant/api.js"),
        """
const calls=[];let first;
requestJson=(base,method,path,payload,options)=>{
  calls.push({method,path,payload,options});
  if(calls.length===1)return new Promise(done=>first=done);
  if(method==='GET')return Promise.resolve({ok:true,data:{status:'UNKNOWN'}});
  return Promise.resolve({ok:true,data:{status:'REPLAYED',receipt:{
    command_id:payload.command_id,case_id:'a',revision:2,audit_event_id:'audit-1'},
    case:{case_id:'a',revision:2}}});
};
global.renderStoredDiagnosis=()=>{};global.loadCases=async()=>{};
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:1});
const write=runCommand('REGISTER_MATERIAL',{evidence_code:'receipt',source:'UNKNOWN'});
const id=S.pendingCommand.payload.command_id;
await runCommand('FINALIZE',{});
assert.equal(calls.length,1);
assert.equal(JSON.parse(stored.get('oceanpilot.pending.MERCHANT')).payload.command_id,id);
first({ok:false,status:0,timedOut:true});await write;
assert.equal(S.commandRecovery,'UNKNOWN');assert.equal(S.pendingCommand.payload.command_id,id);
assert.deepEqual(calls.map(c=>c.method),['POST','GET']);
await retryPendingCommand();
assert.deepEqual(calls.map(c=>c.method),['POST','GET','GET','POST']);
assert.deepEqual(calls[3].payload,calls[0].payload);
assert.equal(calls[3].payload.expected_revision,1);
assert.equal(S.pendingCommand,null);assert.equal(S.caseRevision,2);
assert.equal(S.lastReceipt.audit_event_id,'audit-1');
assert.equal(stored.has('oceanpilot.pending.MERCHANT'),false);
assert.match(node('commandNotice').innerHTML,/a.*版本 2/s);
""",
    )


def test_recovered_receipt_finishes_without_resending_or_overwriting_other_case():
    _execute(
        ("shared/request.js", *STATE, "merchant/api.js"),
        """
let calls=0, resolve;
requestJson=(base,method,path,payload)=>{
  calls++;
  if(method==='POST')return new Promise(done=>resolve=done);
  return Promise.resolve({ok:true,data:{status:'REPLAYED',receipt:{
    command_id:S.pendingCommand.payload.command_id,case_id:'a',revision:2},
    case:{case_id:'a',revision:2}}});
};
global.renderStoredDiagnosis=()=>{throw Error('must not render A over B');};
global.loadCases=async()=>{};
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:1});
const write=runCommand('FINALIZE',{});
selectCase('b');acceptCaseSnapshot({case_id:'b',revision:4});
resolve({ok:false,status:0,timedOut:true});await write;
assert.equal(calls,2);assert.equal(S.pendingCommand,null);
assert.equal(S.caseId,'b');assert.equal(S.caseRevision,4);
assert.equal(S.lastReceipt.case_id,'a');
""",
    )


def test_late_sample_creation_receipt_does_not_steal_navigation():
    _execute(
        ("shared/request.js", *STATE, "merchant/api.js"),
        """
let resolve;
requestJson=()=>new Promise(done=>resolve=done);
global.renderStoredDiagnosis=()=>{throw Error('must preserve selected B');};
global.loadCases=async()=>{};
const write=runCommand('COPY_SAMPLE',{sample:'A'});
const id=S.pendingCommand.payload.command_id;
selectCase('b');acceptCaseSnapshot({case_id:'b',revision:4});
resolve({ok:true,data:{status:'APPLIED',receipt:{command_id:id,
case_id:'new-a',revision:7},case:{case_id:'new-a',
revision:7}}});
await write;
assert.equal(S.caseId,'b');assert.equal(S.lastReceipt.case_id,'new-a');
assert.match(node('commandNotice').innerHTML,/打开回执案件/);
""",
    )


def test_pending_command_cannot_be_dismissed_until_definite_rejection_and_unknown_receipt():
    _execute(
        ("shared/request.js", *STATE, "merchant/api.js"),
        """
S.pendingCommand={payload:{command_id:'same'},actor:currentActor()};
S.commandRecovery='UNKNOWN';dismissRejectedCommand();assert.notEqual(S.pendingCommand,null);
S.pendingCommand.definitiveError=true;S.commandRecovery='PENDING';
dismissRejectedCommand();assert.notEqual(S.pendingCommand,null);
S.commandRecovery='UNKNOWN';dismissRejectedCommand();assert.equal(S.pendingCommand,null);
assert.match(node('commandNotice').innerHTML,/输入已保留/);
assert.equal(demoHeaders()['X-Demo-Role'],'MERCHANT');
assert.equal(demoHeaders()['X-Demo-Actor'],'synthetic-merchant');
assert.equal(/[^\\x00-\\x7F]/.test(demoHeaders()['X-Demo-Actor']),false);
""",
    )


def test_review_preview_is_local_and_confirmation_is_bound_to_exact_revision():
    _execute(
        (*STATE, "merchant/assessment.js"),
        """
const calls=[];global.runCommand=async(...args)=>{calls.push(args);return {status:'APPLIED'};};
selectCase('a');acceptCaseSnapshot({case_id:'a',
revision:3,rule_fingerprint:'rule-v1',allowed_actions:['REVIEW'],

  gate:{can_review:true},readiness:{present:6,
total:6},rule_reference:{rule_version_id:'visa-10.4'}});

node('reviewSummary').value='仅复核材料登记与内部处理条件';node('reviewDecision').value='APPROVED';
previewReview();assert.equal(calls.length,0);assert.equal(S.reviewDraft.revision,3);
assert.match(node('reviewProposal').innerHTML,/版本 3/);
assert.match(node('reviewProposal').innerHTML,/不包含/);
acceptCaseSnapshot({...S.caseSnapshot,revision:4});await confirmWorkspaceReview();
assert.equal(calls.length,0);
previewReview();await confirmWorkspaceReview();
assert.equal(calls.length,1);assert.equal(calls[0][0],'REVIEW');
assert.deepEqual(calls[0][1].scope,['材料登记清单','内部处理门槛']);
assert.equal(calls[0][1].expected_rule_fingerprint,'rule-v1');
assert.deepEqual(calls[0][2],{caseId:'a',revision:4});
assert.equal(S.reviewDraft,null);
""",
        role="BUSINESS",
    )


def test_blocked_case_can_preview_return_but_never_approval_or_merchant_review():
    for role in ("MERCHANT", "BUSINESS"):
        _execute(
            (*STATE, "merchant/assessment.js"),
            """
selectCase('a');acceptCaseSnapshot({case_id:'a',
revision:1,rule_fingerprint:'rule-v1',allowed_actions:['REVIEW'],
gate:{can_review:false}});
node('reviewSummary').value='关键材料仍缺失';node('reviewDecision').value='APPROVED';
previewReview();assert.equal(S.reviewDraft,null);
node('reviewDecision').value='NEEDS_MORE_INFO';previewReview();
assert.equal(Boolean(S.reviewDraft),ROLE==='BUSINESS');
""",
            role=role,
        )


def test_material_selection_is_metadata_only_and_write_requires_frozen_confirmation():
    _execute(
        (*STATE, "merchant/materials.js"),
        """
const calls=[];global.runCommand=async(...args)=>{calls.push(args);return {
 receipt:{case_id:'a',revision:3},case:{missing_count:0}};};
selectCase('a');acceptCaseSnapshot({case_id:'a',
revision:2,allowed_actions:['REGISTER_MATERIAL',
'WITHDRAW_MATERIAL'],
 materials:[{code:'old-item',label:'早先登记的材料',active:true},{code:'new-item',active:true}]});
openEvidenceModal('receipt','交易凭证');assert.equal(calls.length,0);
selectEvidenceFile({files:[{name:'synthetic.txt',text(){throw Error('body must not read');},
 arrayBuffer(){throw Error('body must not read');}}]});
assert.equal(calls.length,0);assert.equal(S.evidenceDraft.fileName,'synthetic.txt');
assert.equal(node('evidenceSource').value,'SYNTHETIC_USER_METADATA');
await submitEvidenceModal();assert.equal(calls[0][0],'REGISTER_MATERIAL');
assert.deepEqual(calls[0][1],{evidence_code:'receipt',
file_name:'synthetic.txt',source:'SYNTHETIC_USER_METADATA'});

assert.deepEqual(calls[0][2],{caseId:'a',revision:2});
assert.match(node('evidenceReceipt').innerHTML,/正文未读取/);
openWithdrawModal('old-item');assert.equal(calls.length,1);
await confirmEvidenceWithdrawal();assert.equal(calls[1][0],'WITHDRAW_MATERIAL');
assert.deepEqual(calls[1][1],{evidence_code:'old-item'});
assert.deepEqual(calls[1][2],{caseId:'a',revision:2});
""",
    )


def test_rules_use_exact_snapshot_reference_without_a_default_and_preserve_case_section():
    _execute(
        ("shared/request.js", *STATE, "merchant/cases.js", "merchant/rules.js"),
        """
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:5});
for(const code of ['10.4','13.1','4853']){
 renderCaseRule({rule_reference:{match_status:'EXACT_MATCH',
rule_version_id:'exact-'+code,scheme:code==='4853'?'MASTERCARD':'VISA',
scheme_reason_code:code}});
 assert.match(node('diagnosisRuleReferenceOut').innerHTML,new RegExp('exact-'+code));
 if(code!=='10.4')assert.equal(node('diagnosisRuleReferenceOut').innerHTML.includes('10.4'),false);
}
renderCaseRule({card_network:null,rule_reference:{match_status:'NO_EXACT_MATCH'}});
assert.match(node('diagnosisRuleReferenceOut').innerHTML,/不会把默认模板/);
assert.equal(node('diagnosisRuleReferenceOut').innerHTML.includes('showRuleReference'),false);
assert.equal(safeHttpUrl('javascript:alert(1)'),'#');
assert.equal(ruleDetailPath('visa/13.1'),'/rules/visa%2F13.1');
S.currentView='workspace';S.section='materials';
node('tableSearch').value='主案例';node('ownerFilter').value='MERCHANT';

loadRules=async()=>{};global.refreshCase=async()=>{};
showRuleReference('visa/13.1');assert.equal(S.currentView,'rules');
assert.equal(new URL(node('roleSwitch').href,location.origin).searchParams.get('case'),'a');
assert.equal(location.search.includes('case=a'),true);
await returnFromRuleReference();assert.equal(S.currentView,'workspace');
assert.equal(S.section,'materials');
assert.equal(S.caseRevision,5);assert.equal(node('tableSearch').value,'主案例');
assert.equal(new URL(node('roleSwitch').href,location.origin).pathname,'/business');
assert.equal(new URL(node('roleSwitch').href,location.origin).searchParams.get('owner'),'MERCHANT');
""",
    )


def test_refresh_restores_case_section_and_filters_on_other_role():
    _execute(
        ("shared/request.js", *STATE, "merchant/cases.js"),
        """
global.location=new URL('http://localhost/business?case=a&view=workspace&section=review&q=sample&status=READY_FOR_REVIEW&owner=BUSINESS');

const requests=[];global.workspaceApi=async(method,path)=>{requests.push(path);
 return {ok:true,data:{case_id:'a',revision:9}};};
renderStoredDiagnosis=()=>{};
await restoreNavigation();
assert.deepEqual(requests,['/cases/a']);assert.equal(S.caseId,'a');assert.equal(S.caseRevision,9);
assert.equal(S.section,'review');assert.equal(S.currentView,'workspace');
assert.equal(node('tableSearch').value,'sample');
assert.equal(node('statusFilter').value,'READY_FOR_REVIEW');

const link=new URL(node('roleSwitch').href,location.origin);
assert.equal(link.pathname,'/demo');assert.equal(link.searchParams.get('case'),'a');
assert.equal(link.searchParams.get('section'),'review');
""",
        role="BUSINESS",
    )


def test_output_source_badge_depends_on_this_result_and_recommendations_do_not_write():
    _execute(
        (*STATE, "merchant/agent-review.js"),
        """
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:1,allowed_actions:['REVIEW']});
assert.equal(agentOutputSource({runtime:{provider:'deepseek',mode:'LIVE'}}).label,'本次输出来源未报告');
assert.equal(agentOutputSource({output_source:'MODEL'}).label,'实时模型输出');
assert.equal(agentOutputSource({output_source:'DETERMINISTIC'}).label,'确定性规则输出');
assert.equal(agentOutputSource({output_source:'DETERMINISTIC',
runtime:{mode:'OFFLINE_FALLBACK'}}).label,'离线确定性输出');

assert.equal(agentOutputSource({output_source:'FALLBACK',
failure_code:'MODEL_TIMEOUT'}).label,'模型异常后的降级输出');

global.runCommand=()=>{throw Error('AI may not mutate');};
renderAgentTurn({case_id:'a',case_revision:1,output_source:'MODEL',
recommended_action:{kind:'APPROVE_REVIEW'},assistant_message:'请审核'});

assert.match(node('agentOutput').innerHTML,/明确确认/);
assert.equal(node('agentOutput').innerHTML.includes('onclick="confirm'),false);
assert.match(node('agentOutput').innerHTML,/AI 未读取正文/);
""",
    )


def test_summary_uses_expected_revision_without_model_call_and_rejects_late_version():
    _execute(
        (*STATE, "merchant/assessment.js"),
        """
let resolve,call,refreshes=0;
global.workspaceApi=(method,path,body)=>{call={method,path,body};
 return new Promise(done=>resolve=done);};
global.refreshCase=async()=>{refreshes++;};
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:7});
const first=generateSummary();await generateSummary();
assert.deepEqual(call,{method:'POST',path:'/cases/a/summaries',body:{expected_revision:7}});
assert.equal(S.summaryGenerating,true);assert.equal(node('generateSummaryButton').disabled,true);
acceptCaseSnapshot({case_id:'a',revision:8});
resolve({ok:true,data:{case_id:'a',revision:7,summary_id:'summary-old'}});await first;
assert.equal(refreshes,0);assert.equal(S.summaryGenerating,false);
assert.equal(node('summaryStatus').textContent.includes('摘要已保存'),false);
const second=generateSummary();
resolve({ok:true,data:{case_id:'a',revision:8,summary_id:'summary-new'}});await second;
assert.equal(refreshes,1);assert.match(node('summaryStatus').textContent,/版本 8/);
""",
        role="BUSINESS",
    )


def test_same_revision_rule_change_invalidates_preview_analysis_and_current_history_label():
    _execute(
        (*STATE, "merchant/assessment.js"),
        """
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:4,rule_fingerprint:'rules-old',
 allowed_actions:['REVIEW'],gate:{can_review:true}});
node('reviewSummary').value='仅复核登记清单';node('reviewDecision').value='APPROVED';
previewReview();const ticket=caseContext.capture();
assert.equal(S.reviewDraft.ruleFingerprint,'rules-old');
S.lastAgentTurn={case_id:'a',case_revision:4};
acceptCaseSnapshot({...S.caseSnapshot,rule_fingerprint:'rules-new'});
assert.equal(caseContext.isCurrent(ticket),false);
assert.equal(S.reviewDraft,null);assert.equal(S.lastAgentTurn,null);
renderReview({...S.caseSnapshot,review:{current_record:null,stale:true,history:[
 {decision_id:'old',case_revision:4,status:'APPROVED',summary:'旧规则审核'}]},
 summaries:[{summary_id:'s1',revision:4}]});
assert.match(node('reviewHistory').innerHTML,/历史记录/);
assert.equal(node('reviewHistory').innerHTML.includes('当前复核决定'),false);
assert.match(node('currentReview').innerHTML,/未覆盖当前规则与材料版本，只作历史记录/);
assert.match(node('summaryRows').innerHTML,/规则以摘要为准/);
""",
        role="BUSINESS",
    )


def test_current_service_configuration_is_separate_from_saved_reply_source():
    _execute(
        (*STATE, "merchant/agent-review.js"),
        """
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:7,
 runtime:{mode:'DEEPSEEK_LIVE',provider:'DEEPSEEK',model:'deepseek-chat'}});
renderAgentServiceStatus();
assert.match(node('agentServiceStatus').innerHTML,/当前服务配置：实时 DeepSeek/);
const offline={case_id:'a',case_revision:7,assistant_message:'旧离线说明',
 output_source:'DETERMINISTIC',runtime:{mode:'OFFLINE_FALLBACK',
provider:'DETERMINISTIC',model:'offline-rules'}};

renderAgentTurn(offline);
assert.equal(node('agentRuntimeBadge').textContent,'离线确定性输出');
assert.match(node('agentHistory').innerHTML,/离线确定性输出/);
assert.match(node('agentHistory').innerHTML,/offline-rules/);
assert.equal(node('agentHistory').innerHTML.includes('实时模型输出'),false);
assert.match(node('agentServiceStatus').innerHTML,/实时 DeepSeek/);
renderAgentTurn({case_id:'a',case_revision:7,assistant_message:'新的实时说明',output_source:'MODEL',
 runtime:{mode:'DEEPSEEK_LIVE',provider:'DEEPSEEK',model:'deepseek-chat'}});
assert.equal(S.agentMessages.length,2);
assert.equal(S.agentMessages[0].output_source,'DETERMINISTIC');
assert.equal(S.agentMessages[1].output_source,'MODEL');
offline.runtime.mode='DEEPSEEK_LIVE';offline.runtime.provider='DEEPSEEK';
renderAgentHistory();assert.equal(S.agentMessages[0].runtime.mode,'OFFLINE_FALLBACK');
assert.match(node('agentHistory').innerHTML,/离线确定性输出/);
assert.match(node('agentHistory').innerHTML,/实时模型输出/);
""",
    )


def test_explicit_analysis_and_error_retry_always_request_a_new_user_turn():
    _execute(
        (*STATE, "merchant/agent-review.js"),
        """
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:7});
const payloads=[];
global.requestJson=async(base,method,path,payload)=>{
 payloads.push(payload);
 if(payloads.length===1)return {ok:false,status:503};
 return {ok:true,data:{case_id:'a',case_revision:7,output_source:'MODEL',
   assistant_message:'新的说明',runtime:{mode:'DEEPSEEK_LIVE',provider:'DEEPSEEK'}}};
};
await analyzeCurrentCase('CASE_OPENED');
assert.equal(payloads[0].trigger,'USER_MESSAGE');
assert.equal(payloads[0].case_id,'a');
const retry=node('agentTurnStatus').innerHTML.match(/onclick="([^"]+)"/)[1];
assert.equal(retry,'retryFailedAgentTurn()');
await eval(retry);
assert.equal(payloads.length,2);assert.equal(payloads[1].trigger,'USER_MESSAGE');
assert.equal(payloads[0].message,payloads[1].message);
assert.equal(S.agentSubmitting,false);assert.equal(node('agentAnalyzeButton').disabled,false);
assert.equal(S.agentMessages[0].output_source,'MODEL');
""",
    )


def test_chat_source_labels_keep_legacy_messages_unknown_and_escape_runtime_fields():
    _execute(
        (*STATE, "merchant/agent-review.js"),
        """
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:1});
S.agentMessages=[{role:'assistant',text:'历史离线文字'}, {role:'user',text:'<script>bad</script>'}];
renderAgentHistory();
assert.match(node('agentHistory').innerHTML,/历史来源未记录/);
assert.equal(node('agentHistory').innerHTML.includes('实时模型输出'),false);
assert.match(node('agentHistory').innerHTML,/&lt;script&gt;/);
appendAgentMessage('assistant','<img src=x onerror=bad>',{output_source:'FALLBACK',
 failure_code:'TIMEOUT <unsafe>',
 runtime:{mode:'DEEPSEEK_LIVE',provider:'<provider>',model:'<model>'}});
assert.match(node('agentHistory').innerHTML,/模型异常后的降级输出/);
assert.match(node('agentHistory').innerHTML,/TIMEOUT &lt;unsafe&gt;/);
assert.match(node('agentHistory').innerHTML,/&lt;provider&gt; &lt;model&gt;/);
assert.equal(node('agentHistory').innerHTML.includes('<img'),false);
renderAgentServiceStatus();
assert.match(node('agentServiceStatus').innerHTML,/当前服务配置尚未读取/);
acceptCaseSnapshot({...S.caseSnapshot,runtime:{mode:'OFFLINE_FALLBACK',model:'offline-rules'}});
renderAgentServiceStatus();assert.match(node('agentServiceStatus').innerHTML,/当前服务配置：离线规则/);
acceptCaseSnapshot({...S.caseSnapshot,runtime:{mode:'INJECTED_MODEL',model:'<test-model>'}});
renderAgentServiceStatus();assert.match(node('agentServiceStatus').innerHTML,/合成测试模型/);
assert.match(node('agentServiceStatus').innerHTML,/&lt;test-model&gt;/);
""",
    )


def test_all_create_and_concern_controls_validate_before_dispatch():
    _execute(
        (*STATE, "merchant/cases.js", "merchant/concerns.js"),
        """
const calls=[];global.runCommand=async(...args)=>{calls.push(args);};
node('formalDisputeConfirm').checked=false;
await openCase();assert.equal(calls.length,0);
node('formalDisputeConfirm').checked=true;node('caseName').value='x'.repeat(101);
node('desc').value='Synthetic test description';

await openCase();assert.equal(calls.length,0);
node('caseName').value='UI audit';await openCase();assert.equal(calls[0][0],'CREATE_CASE');
for(const sample of ['A','B','C'])await copySample(sample);
await copySample('D');assert.equal(calls.length,4);
selectCase('a');acceptCaseSnapshot({case_id:'a',
revision:1,allowed_actions:['CONFIRM_REASON','SET_NETWORK',
'FINALIZE','ADD_CONCERN','RESOLVE_CONCERN']});

node('diagReasonFix').value='PRODUCT_NOT_RECEIVED';await confirmDiagnosisReason();
assert.deepEqual(calls[4],['CONFIRM_REASON',{reason_code:'PRODUCT_NOT_RECEIVED'}]);
global.renderCommandNotice=()=>{};node('diagnosisNetwork').value='';
await saveCaseNetwork();assert.equal(calls.length,
5);
node('diagnosisNetwork').value='MASTERCARD';await saveCaseNetwork();
assert.equal(calls[5][0],'SET_NETWORK');
await finalize();assert.equal(calls[6][0],'FINALIZE');
node('concernField').value='qa_note';node('concernSummary').value='Synthetic concern';
await addConcern();assert.equal(calls.length,7);
assert.match(node('concernError').textContent,/来源/);
node('concernOriginalSource').value='Synthetic A';node('concernProposedSource').value='Synthetic B';
node('concernKind').value='FACT_CONFLICT';await addConcern();
assert.equal(calls[7][0],'ADD_CONCERN');
await resolveConcern('x');assert.equal(calls.length,8);
node('resolution-summary-x').value='Synthetic resolution';
for(const resolution of ['KEEP_ORIGINAL','ACCEPT_PROPOSED','ACKNOWLEDGE']){
 node('resolution-x').value=resolution;await resolveConcern('x');
assert.equal(calls.at(-1)[1].resolution,resolution);

}
""",
    )


def test_modal_focus_wrap_and_completed_material_controls_cannot_resubmit():
    _execute(
        (*STATE, "merchant/materials.js"),
        """
const first=node('first'),last=node('last');first.tabIndex=last.tabIndex=0;
first.focus=()=>{document.activeElement=first;};last.focus=()=>{document.activeElement=last;};
node('evidenceModal').querySelectorAll=()=>[first,last];node('evidenceModal').contains=()=>true;
let calls=0;global.runCommand=async()=>{calls++;
return {receipt:{case_id:'a',revision:2},case:{missing_count:0}};
};
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:1,allowed_actions:['REGISTER_MATERIAL']});
openEvidenceModal('receipt','交易收据');assert.equal(node('.app').inert,true);
document.activeElement=last;let prevented=false;
trapDialogFocus({key:'Tab',shiftKey:false,preventDefault(){prevented=true;
}});
assert.equal(document.activeElement,first);assert.equal(prevented,true);
trapDialogFocus({key:'Tab',shiftKey:true,preventDefault(){}});
assert.equal(document.activeElement,last);
useSyntheticEvidenceFile();await submitEvidenceModal();
await submitEvidenceModal();assert.equal(calls,
1);
for(const id of ['evidenceFile','evidenceSource',
'syntheticEvidenceButton','evidenceSubmitButton'])assert.equal(node(id).disabled,
true);
closeEvidenceModal();assert.equal(node('.app').inert,false);assert.equal(S.evidenceDraft,null);
""",
    )


def test_all_section_buttons_and_rule_filter_clear_stale_detail_url():
    _execute(
        (*STATE, "shared/request.js", "merchant/cases.js", "merchant/rules.js"),
        """
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:2});
global.renderStoredDiagnosis=()=>{};global.loadCases=async()=>{};
S.currentView='workspace';
for(const section of CASE_SECTIONS){selectCaseSection(section);
assert.equal(new URL(location).searchParams.get('section'),
section);}
S.currentView='rules';S.currentRuleId='old-rule';writeNavigation();
node('ruleSearch').value='goods';
window.oceanI18n.translateTo=s=>s==='商品 / 服务未收到'?'Goods / services not received':s;

global.api=async()=>({ok:true,data:{items:[{rule_version_id:'new-rule',
display_name:'商品 / 服务未收到',scheme:'VISA',demo_role:'DEMO_MAPPED',
document_id:'doc'}],total:1}});
await loadRules();assert.equal(S.rules.length,
1);assert.equal(S.currentRuleId,null);assert.equal(new URL(location).searchParams.has('rule'),
false);
assert.match(node('ruleRows').innerHTML,/new-rule/);
""",
    )


def test_download_controls_use_frozen_summary_locale_and_fail_without_false_success():
    _execute(
        (*STATE, "merchant/assessment.js"),
        """
selectCase('a');acceptCaseSnapshot({case_id:'a',
revision:9,summaries:[{summary_id:'s',case_id:'a',
revision:2,html_url:'/api/v1/workspace/summaries/s?format=html',
json_url:'/api/v1/workspace/summaries/s?format=json'}]});

S.loc='en';global.demoHeaders=()=>({});const requests=[];
global.OceanRequest={text:async(path)=>{requests.push(path);return {ok:false};}};
await downloadSummary('s','html');assert.match(requests[0],
/locale=en/);assert.match(node('summaryStatus').textContent,
/失败/);
await downloadSummary('s','xml');await downloadSummary('missing',
'json');assert.equal(requests.length,1);
S.loc='zh';await downloadSummary('s','json');assert.match(requests[1],/format=json&locale=zh/);
""",
    )


def test_agent_empty_input_is_blocked_and_retry_preserves_the_actual_question():
    _execute(
        (*STATE, "merchant/agent-review.js"),
        """
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:1});
S.loc='en';const calls=[];
global.requestJson=async(_,__,___,payload)=>{calls.push(payload);return {ok:false,status:503};};
node('agentMessage').value=' ';await sendAgentTurn();assert.equal(calls.length,0);
node('agentMessage').value='Who needs to confirm?';await sendAgentTurn();
await retryFailedAgentTurn();assert.equal(calls.length,2);
assert.equal(calls[0].message,calls[1].message);assert.equal(calls[1].locale,'en-US');
acceptCaseSnapshot({case_id:'a',revision:2});await retryFailedAgentTurn();
assert.equal(calls.length,2);assert.equal(S.agentSubmitting,false);
""",
    )


def test_create_entry_focus_and_notice_dismissal_do_not_write_or_drop_pending_commands():
    _execute(
        (*STATE, "shared/request.js", "merchant/cases.js", "merchant/api.js"),
        """
global.loadCases=async()=>{};
let focused=false;node('caseName').focus=()=>{focused=true;};
openCreate();assert.equal(S.currentView,'create');assert.equal(focused,true);
returnToCaseCenter();assert.equal(S.currentView,'overview');
S.lastReceipt={case_id:'a'};S.commandProblem='old error';
clearCommandNotice();assert.equal(S.lastReceipt,null);assert.equal(node('commandNotice').hidden,true);
S.pendingCommand={payload:{command_id:'keep'}};clearCommandNotice();
assert.equal(S.pendingCommand.payload.command_id,'keep');
""",
    )


def test_language_switch_preserves_unsent_form_values_and_review_preview():
    script = resource_text("merchant/bootstrap.js")
    listener = script.split("window.addEventListener('oceanpilot:languagechange',event=>{", 1)[
        1
    ].split("});", 1)[0]
    _execute(
        STATE,
        """
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:1});
node('reviewSummary').value='Unsent review';node('diagnosisNetwork').value='AMEX';
node('resolution-summary-x').value='Unsent resolution';S.reviewDraft={revision:1};
global.renderTransactions=()=>{};global.renderAgentHistory=()=>{};
global.renderCommandNotice=()=>{};
global.renderStoredDiagnosis=()=>{throw new Error('Language switch must not rebuild forms');};
const onLanguage=event=>{LISTENER};onLanguage({detail:{language:'en'}});
assert.equal(S.loc,'en');assert.equal(node('reviewSummary').value,'Unsent review');
assert.equal(node('diagnosisNetwork').value,'AMEX');
assert.equal(node('resolution-summary-x').value,'Unsent resolution');
assert.deepEqual(S.reviewDraft,{revision:1});
""".replace("LISTENER", listener),
    )
