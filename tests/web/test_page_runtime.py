"""Execute the packaged vanilla-JS state and transport boundaries in Node."""

import json
import shutil
import subprocess

from oceanpilot.web.rendering import resource_text

DOM_STUB = """
const nodes = new Map();
function node(id) {
  if (!nodes.has(id)) nodes.set(id, {
    value: id === 'statusFilter' ? 'ALL' : '', textContent: '', innerHTML: '',
    options: [], disabled: false, className: '', isConnected: true,
    classList: {add() {}, remove() {}, toggle() {}, contains() { return false; }},
    addEventListener() {}, setAttribute() {}, removeAttribute() {}, focus() {},
    scrollIntoView() {}, insertAdjacentHTML() {}, remove() { this.removed=true; }, appendChild() {},
  });
  return nodes.get(id);
}
global.document = {getElementById: node, querySelectorAll: () => [],
  addEventListener() {}, activeElement: node('active')};
global.window = {oceanI18n: {getLanguage: () => 'zh', translate: s => s, apply() {}},
  addEventListener() {}};
global.setInterval = () => 0;
if (typeof invalidateDerivedViews !== 'function') global.invalidateDerivedViews = () => {};
"""


def _execute(paths: tuple[str, ...], assertions: str) -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for page runtime regression tests"
    source = "\n".join(
        (
            "const assert = require('node:assert/strict');",
            DOM_STUB,
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
assert.equal(S.cardNetwork, 'MASTERCARD');
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
global.api=(_,path)=>new Promise(resolve=>pending.set(path,resolve));
renderStoredDiagnosis=data=>rendered.push(data.case_id);
showView=()=>{};
global.bindAgentCase=async()=>true;
global.analyzeCurrentCase=async()=>{};
const first=openStoredCase('a');
const second=openStoredCase('b');
pending.get('/cases/b')({ok:true,data:{case_id:'b',revision:2}});
pending.get('/cases/b/audit')({ok:true,data:{events:[]}});
await second;
pending.get('/cases/a')({ok:true,data:{case_id:'a',revision:1}});
pending.get('/cases/a/audit')({ok:true,data:{events:[]}});
await first;
assert.equal(S.caseId,'b');
assert.equal(S.caseRevision,2);
assert.deepEqual(rendered,['b']);
""",
    )


def test_late_agent_bind_cannot_restore_a_previous_case_context():
    _execute(
        ("shared/request.js", *STATE, "merchant/agent-review.js"),
        """
let resolve;
global.api=()=>new Promise(done=>{resolve=done;});
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:1});
const binding=bindAgentCase('a');
selectCase('b');acceptCaseSnapshot({case_id:'b',revision:4});
resolve({ok:true,data:{case_id:'a',revision:2}});
assert.equal(await binding,false);
assert.equal(S.caseId,'b');
assert.equal(S.caseRevision,4);
assert.equal(S.agentCase,null);
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


def test_new_snapshot_invalidates_package_and_review_views_but_equal_revision_does_not():
    _execute(
        (*STATE, "merchant/cases.js", "merchant/rules.js"),
        """
selectCase('a');acceptCaseSnapshot({case_id:'a',revision:1});
S.packaged=true;S.appealed=true;S.pendingReview={caseId:'a',caseRevision:1};
node('pkgOut').innerHTML='version 1 package';
acceptCaseSnapshot({case_id:'a',revision:1});
assert.equal(S.packaged,true);
assert.notEqual(S.pendingReview,null);
acceptCaseSnapshot({case_id:'a',revision:2});
assert.equal(S.packaged,false);
assert.equal(S.appealed,false);
assert.equal(node('pkgOut').innerHTML,'');
assert.equal(S.pendingReview,null);
assert.equal(node('agentReviewProposal').removed,true);
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
