"""V2 packaged-page and browser-state safety boundaries."""

import json
import shutil
import subprocess
from html.parser import HTMLParser
from importlib.resources import files

import pytest

from oceanpilot.web.v2.rendering import render_v2_page


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.remote_assets = []
        self.images = []
        self.confirmation_required = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and "src" in attrs:
            self.remote_assets.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.remote_assets.append(attrs.get("href"))
        if tag == "img":
            self.images.append(attrs.get("src"))
        if tag == "input" and attrs.get("id") == "confirmCheckbox":
            self.confirmation_required = "required" in attrs


@pytest.mark.parametrize("surface", ["operations", "merchant", "governance"])
def test_v2_pages_are_self_contained_and_identify_demo_boundaries(surface):
    page = render_v2_page(surface)
    parser = References()
    parser.feed(page)
    assert parser.remote_assets == []
    assert parser.images and parser.images[0].startswith("data:image/png;base64,")
    assert "__V2_" not in page
    assert json.dumps({"surface": surface}) in page
    assert "非生产身份认证" in page
    assert "Mock" in page
    assert 'aria-labelledby="dialogTitle"' in page
    assert parser.confirmation_required


def test_unrecognized_surface_is_not_interpolated_into_html():
    with pytest.raises(ValueError, match="Unknown V2 workspace"):
        render_v2_page("</script><script>alert(1)</script>")
    assert render_v2_page("MERCHANT") == render_v2_page("merchant")


DOM = """
global.OCEAN_V2_NO_BOOT=true;
const V2_CONFIG={surface:'operations'};
const nodes=new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',hidden:false,
 disabled:false,open:false,value:'',className:'',dataset:{},
 classList:{add(){},remove(){},toggle(){}},
 close(){this.open=false;},showModal(){this.open=true;},
 querySelectorAll(){return [];},addEventListener(){}});return nodes.get(id);}
global.document={getElementById:node,querySelectorAll:()=>[],addEventListener(){}};
global.location=new URL('http://localhost/v2/operations');
global.history={replaceState(_,__,url){global.location=new URL(url);}};
const stored=new Map();
global.sessionStorage={getItem:k=>stored.get(k),setItem:(k,v)=>stored.set(k,v),
 removeItem:k=>stored.delete(k)};
const sample={id:'a',revision:2,merchant_id:'synthetic-merchant-001',owner:'OceanPayment',
 scheme:'VISA',channel:'MOCK',reason_code:'13.1',amount_minor:123400,currency:'USD',
 stage:'FORMAL_DISPUTE',work_status:'EVIDENCE_COLLECTING',merchant_decision:'CONTEST',
 business_outcome:'UNKNOWN',finality:'NOT_FINAL',financial_status:'PENDING',
 tasks:[],evidence:[],audit:[],rule_snapshot:{required_evidence:['ORDER','DELIVERY']}};
const ok=body=>({ok:true,status:200,json:async()=>body});
"""


def run_js(assertions):
    node = shutil.which("node")
    assert node, "Node.js is required for the V2 page runtime tests"
    script = files("oceanpilot.web").joinpath("v2/app.js").read_text("utf-8")
    result = subprocess.run(
        [node, "-"],
        input="const assert=require('node:assert/strict');\n"
        + DOM
        + script
        + "\n(async()=>{\n"
        + assertions
        + "\n})().catch(e=>{console.error(e);process.exitCode=1;});",
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_merchant_and_agent_controls_never_offer_human_review_or_submit():
    run_js("""
const ui=OceanV2;
ui.state.role='MERCHANT';ui.state.current=sample;
assert.equal(ui.headers()['X-Demo-Merchant'],'synthetic-merchant-001');
assert.equal(ui.headers()['X-Demo-Role'],'MERCHANT');
for(const action of ['INTAKE','REVIEW','APPROVE_PACKAGE','SUBMIT','CLOSE'])
 assert.equal(ui.permitted(action),false);
ui.openDialog('SUBMIT');assert.equal(ui.state.dialog,null);
ui.state.role='AGENT';
for(const action of ['REVIEW','APPROVE_PACKAGE','SUBMIT','CLOSE'])
 assert.equal(ui.permitted(action),false);
assert.equal(ui.permitted('BUILD_PACKAGE'),true);
""")


def test_untrusted_case_content_is_escaped_in_rendered_detail():
    run_js("""
OceanV2.state.current={...sample,merchant_id:'<img src=x onerror=alert(1)>'};
OceanV2.state.plan={revision:2,summary:'<script>bad()</script>',readiness:{percent:40},
 next_action:{action:'REGISTER_EVIDENCE',reason:'Safe'},blockers:[]};
OceanV2.state.isCasePage=true;OceanV2.renderDetail();
const output=node('caseDetail').innerHTML;
assert.match(output,/&lt;img/);assert.match(output,/&lt;script&gt;/);
assert.equal(output.includes('<img src=x'),false);
assert.equal(output.includes('<script>bad'),false);
""")


def test_queues_keep_financial_outcome_and_work_dimensions_independent():
    run_js("""
const ui=OceanV2;
assert.equal(ui.matchesQueue({...sample,business_outcome:'WON',
 finality:'FINAL_CONFIRMED',financial_status:'DISCREPANCY'},'FINANCIAL'),true);
assert.equal(ui.matchesQueue({...sample,business_outcome:'WON'},'CLOSED'),false);
assert.equal(ui.matchesQueue(sample,'FINANCIAL'),false);
assert.equal(ui.matchesQueue({...sample,work_status:'CLOSED'},'FINANCIAL'),false);
assert.equal(ui.matchesQueue({...sample,merchant_decision:'NO_RESPONSE'},'URGENT'),true);
assert.deepEqual(ui.completeness({...sample,evidence:[
 {code:'ORDER',active:true},{code:'DELIVERY',active:false}]}),{present:1,total:2});
""")


def test_late_case_response_cannot_replace_current_selection():
    run_js("""
const pending=new Map();
global.fetch=url=>new Promise(resolve=>pending.set(url,resolve));
OceanV2.state.isCasePage=true;
const first=OceanV2.openCase('a',{withAgent:false}),second=OceanV2.openCase('b',{withAgent:false});
pending.get('/api/v2/cases/b')(ok({...sample,id:'b',revision:8}));
pending.get('/api/v2/cases/b/plan')(ok({case_id:'b',revision:8}));await second;
pending.get('/api/v2/cases/a')(ok(sample));
pending.get('/api/v2/cases/a/plan')(ok({case_id:'a',revision:2}));await first;
assert.equal(OceanV2.state.current.id,'b');
assert.equal(OceanV2.state.current.revision,8);
assert.match(node('caseDetail').innerHTML,/b/);
""")


def test_uncertain_write_retries_same_payload_and_never_impersonates_other_role():
    run_js("""
const ui=OceanV2,writes=[];
ui.state.current=sample;
const payload={command_id:'immutable-id',action:'COMMENT',case_id:'a',
 expected_revision:2,confirmed:true,data:{message:'synthetic'}};
ui.state.pending={payload,identity:{role:'OPERATOR',actor:'synthetic-operator',
 merchant_id:'synthetic-merchant-001'}};
global.fetch=async(url,options)=>{if(url==='/api/v2/commands'){
 writes.push({payload:JSON.parse(options.body),headers:options.headers});
 if(writes.length===1)throw Error('Connection dropped');
 return ok({case:{...sample,revision:3},receipt:{command_id:'immutable-id'},replayed:true});
 }if(url==='/api/v2/cases')return ok({cases:[]});
 if(url==='/api/v2/capabilities')return ok({role:'OPERATOR',actions:['COMMENT']});
 throw Error(url);};
await ui.executePending();assert.equal(ui.state.pending.payload.command_id,'immutable-id');
assert.equal(writes.length,1);assert.match(node('globalNotice').innerHTML,/原命令/);
ui.state.role='MERCHANT';await ui.executePending();assert.equal(writes.length,1);
ui.state.role='OPERATOR';await ui.executePending();
assert.equal(writes.length,2);assert.deepEqual(writes[0],writes[1]);
assert.equal(ui.state.pending,null);assert.equal(stored.has('oceanpilot.v2.pending'),false);
""")


def test_mismatched_plan_revision_is_not_presented_as_current_advice():
    run_js("""
global.fetch=async url=>ok(url.endsWith('/plan')?
 {case_id:'a',revision:1,summary:'stale advice'}:sample);
await OceanV2.openCase('a',{withAgent:false});
assert.equal(OceanV2.state.plan,null);
assert.equal(node('caseDetail').innerHTML.includes('stale advice'),false);
""")


def test_human_confirmation_cannot_execute_against_a_newer_case_revision():
    run_js("""
const ui=OceanV2;
ui.state.role='RISK_OFFICER';ui.state.current=sample;
ui.state.dialog={action:'REVIEW',case_id:'a',revision:1,
 identity:{role:'RISK_OFFICER'}};
node('actionForm').reportValidity=()=>true;
node('confirmCheckbox').checked=true;
global.fetch=()=>{throw Error('A stale human confirmation must never issue a request');};
await ui.submitDialog({preventDefault(){}});
assert.match(node('dialogError').textContent,/版本已变化/);
assert.equal(ui.state.pending,null);
""")


def test_unknown_rules_never_preselect_merchant_rights():
    run_js("""
const ui=OceanV2;
ui.state.role='RISK_OFFICER';
ui.state.current={...sample,rule_snapshot:{conflict_status:'NEEDS_CONFIRMATION'}};
ui.openDialog('CONFIRM_RULE');
const markup=node('dialogFields').innerHTML;
assert.match(markup,/name="allow_accept"/);
assert.match(markup,/name="allow_contest"/);
assert.equal(markup.includes(' checked'),false);
global.FormData=class{entries(){return [['source_id','reviewed-source']];}};
const form={querySelectorAll:()=>[
 {name:'allow_accept',checked:false},{name:'allow_contest',checked:true}]};
const data=ui.collectData(form);
assert.deepEqual(data.allowed_actions,['CONTEST']);
assert.equal('allow_accept' in data,false);
assert.equal('allow_contest' in data,false);
""")


def test_currency_display_respects_currency_minor_units_without_guessing_on_error():
    run_js(r"""
assert.match(OceanV2.money(12800,'USD'),/128\.00/);
assert.match(OceanV2.money(12800,'JPY'),/12,800/);
assert.equal(OceanV2.money(12800,'JPY').includes('.00'),false);
assert.match(OceanV2.money(12800,'KWD'),/12\.800/);
assert.equal(OceanV2.money(12800,'INVALID'),'INVALID 12800（原始最小货币单位）');
""")


def test_agent_sources_distinguish_model_answers_tools_and_fallback():
    run_js("""
assert.match(OceanV2.agentSource({source:'MODEL',provider:'DEEPSEEK'}).label,/实时回答/);
assert.match(OceanV2.agentSource({source:'FALLBACK',provider:'DETERMINISTIC'}).label,/降级/);
assert.match(OceanV2.agentSource({provider:'DETERMINISTIC'}).label,/工具结果/);
assert.equal(OceanV2.agentSource({provider:'DEEPSEEK'}).label,'输出来源未报告');
""")


def test_first_agent_render_handles_real_absent_textarea_before_case_selection():
    run_js("""
document.getElementById=id=>id==='agentMessage'?null:node(id);
OceanV2.state.current=null;
OceanV2.renderAgentPanel();
assert.equal(node('agentPanel').hidden,true);
assert.equal(node('agentPanel').innerHTML,'');
""")


def test_agent_activity_keeps_unsent_input_and_escapes_actual_tool_and_model_output():
    run_js("""
const ui=OceanV2;ui.state.current=sample;
node('agentMessage').dataset={case:'a',role:'OPERATOR'};
node('agentMessage').value='尚未发送的商户沟通草稿';
const activity={run:{id:'run-2',case_id:'a',case_revision:2,provider:'DETERMINISTIC',
 trigger:'REGISTER_EVIDENCE',summary:'<script>bad()</script>',steps:[{
 capability:'evidence_check',title:'检查证据',status:'COMPLETED',output:{note:'<img>'}}],
 findings:[],prepared:{}},proposals:[],conversations:[{message:'我的问题',
 answer:'<iframe src=x>',source:'MODEL',provider:'DEEPSEEK',model:'actual-model',
 case_revision:2}],runtime:{mode:'DEEPSEEK_LIVE'}};
assert.equal(ui.acceptAgentActivity(activity,'a:2:OPERATOR'),true);
const output=node('agentPanel').innerHTML;
assert.match(output,/已完成 1 项工具检查/);
assert.match(output,/DEEPSEEK · 实时回答/);
assert.match(output,/actual-model/);
assert.match(output,/&lt;iframe/);assert.equal(output.includes('<iframe'),false);
assert.equal(ui.state.agentDrafts['a:operations:synthetic-merchant-001'],'尚未发送的商户沟通草稿');
assert.equal(ui.acceptAgentActivity({...activity,summary:'wrong'},'b:2:OPERATOR'),false);
assert.equal(ui.state.activity.summary,undefined);
""")


def test_stale_or_other_owners_agent_proposals_never_offer_execution():
    run_js("""
const ui=OceanV2;ui.state.current=sample;
const proposal={id:'p',case_id:'a',expected_revision:2,status:'PENDING_CONFIRMATION',
 action:'MERCHANT_DECISION',owner:'MERCHANT',title:'确认商户决定',data:{}};
ui.state.activity={run:{id:'r',case_revision:2,steps:[]},proposals:[proposal]};
assert.equal(ui.permitted('MERCHANT_DECISION'),true);
ui.renderAgentPanel();
assert.equal(node('agentPanel').innerHTML.includes('data-agent-proposal="p"'),false);
ui.openAgentProposal('p');assert.equal(ui.state.dialog,null);
assert.match(ui.state.agentNotice,/商户/);
assert.deepEqual(ui.proposalsFor({...ui.state.activity,stale:true},sample),[]);
assert.deepEqual(ui.proposalsFor(ui.state.activity,{...sample,revision:3}),[]);
""")


@pytest.mark.parametrize(
    "edited, required_inputs, expected_route",
    [
        (False, [], "/cases/a/agent/proposals/proposal-a/execute"),
        (True, [], "/commands"),
        (False, ["message"], "/commands"),
    ],
)
def test_proposal_confirmation_uses_saved_proposal_only_when_unchanged_and_complete(
    edited, required_inputs, expected_route
):
    run_js(f"""
const ui=OceanV2,writes=[];ui.state.current=sample;
const initial={{message:'prepared notice',required:true}};
ui.state.dialog={{action:'PUBLISH_TASK',case_id:'a',revision:2,
 identity:{{role:'OPERATOR',actor:'synthetic-operator',merchant_id:'synthetic-merchant-001'}},
 proposal:{{id:'proposal-a',owner:'OPERATOR',required_inputs:{json.dumps(required_inputs)}}},
 proposalInitialData:initial}};
node('actionForm').reportValidity=()=>true;
node('actionForm').querySelectorAll=()=>[{{name:'required',checked:true}}];
node('confirmCheckbox').checked=true;
global.FormData=class{{entries(){{return [['message',
 {json.dumps("edited notice" if edited else "prepared notice")}]];}}}};
global.fetch=async(url,options)=>{{if(options.method==='POST'){{
 writes.push({{url,body:JSON.parse(options.body)}});
 return ok({{case:{{...sample,revision:3}},receipt:{{command_id:'done'}}}});
 }}if(url==='/api/v2/cases')return ok({{cases:[]}});
 if(url==='/api/v2/capabilities')return ok({{role:'OPERATOR',actions:[]}});
 throw Error(url);}};
await ui.submitDialog({{preventDefault(){{}}}});
assert.equal(writes.length,1);assert.equal(writes[0].url,'/api/v2{expected_route}');
assert.equal(writes[0].body.expected_revision,2);
assert.equal(writes[0].body.confirmed,true);
if(writes[0].url.endsWith('/execute'))assert.equal('data' in writes[0].body,false);
else assert.equal(writes[0].body.data.message,
 {json.dumps("edited notice" if edited else "prepared notice")});
""")


def test_late_model_answer_never_appears_in_another_case_or_role():
    run_js("""
const ui=OceanV2;ui.state.current=sample;
let resolve;
global.fetch=()=>new Promise(done=>resolve=done);
const pending=ui.sendAgentMessage('为什么不能提交');
ui.state.current={...sample,id:'b'};ui.state.role='MERCHANT';
ui.state.activity=null;ui.state.agentBusy=false;
resolve(ok({answer:'A private reply',source:'MODEL',provider:'DEEPSEEK'}));
await pending;
assert.equal(ui.state.current.id,'b');assert.equal(ui.state.role,'MERCHANT');
assert.equal(ui.state.activity,null);
assert.equal(node('agentPanel').innerHTML.includes('A private reply'),false);
""")


def test_list_page_does_not_select_a_case_or_start_an_unrelated_conversation():
    run_js("""
const calls=[];
global.fetch=async url=>{calls.push(url);return ok(url.endsWith('/cases')?
 {cases:[sample]}:{actions:[]});};
await OceanV2.refresh();
assert.equal(OceanV2.state.current,null);
assert.equal(OceanV2.state.activity,null);
assert.equal(calls.some(url=>url.includes('/agent')||url.includes('/plan')),false);
assert.equal(OceanV2.caseHref('a/b'),'/v2/operations/cases/a%2Fb');
""")


def test_remote_update_preserves_input_and_invalidates_old_confirmation():
    run_js("""
const ui=OceanV2;ui.state.current=sample;ui.state.caseId='a';ui.state.isCasePage=true;
ui.state.dialog={case_id:'a',revision:2,action:'COMMENT'};
node('agentMessage').dataset={case:'a',role:'OPERATOR'};
node('agentMessage').value='还没有发送的本案问题';
node('dialogFields').innerHTML='<textarea>未提交的协作说明</textarea>';
node('confirmCheckbox').checked=true;
global.fetch=async url=>ok(url.endsWith('/cases')?{cases:[{...sample,revision:3}]}:
 url.endsWith('/plan')?{revision:3}:url.endsWith('/agent')?
 {case_revision:3,conversations:[],run:null}:{...sample,revision:3});
await ui.reconcileUpdates();
assert.equal(ui.state.current.revision,3);
assert.equal(ui.state.dialog.stale,true);
assert.equal(node('confirmCheckbox').checked,false);
assert.equal(node('submitDialog').disabled,true);
assert.match(node('dialogFields').innerHTML,/未提交的协作说明/);
assert.equal(ui.state.agentDrafts['a:operations:synthetic-merchant-001'],'还没有发送的本案问题');
assert.equal(stored.get('oceanpilot.v2.draft.a:operations:synthetic-merchant-001'),'还没有发送的本案问题');
""")


def test_new_ai_reply_updates_without_changing_case_revision_or_dialog():
    run_js("""
const ui=OceanV2;ui.state.current=sample;ui.state.caseId='a';ui.state.isCasePage=true;
ui.state.dialog={case_id:'a',revision:2,action:'COMMENT'};
ui.state.plan={revision:2};
node('caseDetail').innerHTML='existing detail';
global.fetch=async url=>ok(url.endsWith('/cases')?{cases:[sample]}:
 url.endsWith('/plan')?{revision:2}:url.endsWith('/agent')?
 {case_revision:2,conversations:[{answer:'新的本案分析',source:'DETERMINISTIC'}]}:sample);
await ui.reconcileUpdates();
assert.equal(ui.state.current.revision,2);
assert.equal(ui.state.dialog.stale,undefined);
assert.equal(node('caseDetail').innerHTML,'existing detail');
assert.match(node('agentPanel').innerHTML,/新的本案分析/);
""")


def test_chat_pending_is_released_when_remote_case_advances_before_model_reply():
    run_js("""
const ui=OceanV2;ui.state.current=sample;
let resolveReply;
global.fetch=url=>url.endsWith('/messages')?new Promise(resolve=>resolveReply=resolve):
 Promise.resolve(ok({case_revision:3,conversations:[]}));
const request=ui.sendAgentMessage('请分析这个案件');
ui.state.current={...sample,revision:3};
resolveReply(ok({answer:'过时的答案',case_revision:2}));await request;
assert.equal(ui.state.agentBusy,false);
assert.equal(ui.state.agentDrafts['a:operations:synthetic-merchant-001'],'请分析这个案件');
assert.equal(node('agentPanel').innerHTML.includes('过时的答案'),false);
""")


def test_case_page_never_falls_back_to_another_accessible_case():
    run_js("""
const ui=OceanV2;ui.state.caseId='missing';ui.state.isCasePage=true;
global.fetch=async url=>url.includes('/missing')?
 {ok:false,status:404,json:async()=>({detail:'Case not found'})}:
 ok(url.endsWith('/cases')?{cases:[sample]}:{actions:[]});
await ui.refresh();
assert.equal(ui.state.current,null);
assert.equal(ui.state.caseId,'missing');
assert.match(node('globalNotice').innerHTML,/Case not found/);
""")


def test_old_agent_get_releases_loading_after_remote_revision_changes():
    run_js("""
const ui=OceanV2;ui.state.current=sample;
let finish;global.fetch=()=>new Promise(resolve=>finish=resolve);
const reading=ui.refreshAgent();
assert.equal(ui.state.agentLoading,true);
ui.state.current={...sample,revision:3};
finish(ok({case_revision:2,run:{case_revision:2},conversations:[]}));await reading;
assert.equal(ui.state.agentLoading,false);
assert.equal(ui.state.activity,null);
""")


def test_old_role_message_cannot_release_a_new_message_request():
    run_js("""
const ui=OceanV2;ui.state.current=sample;
const replies=[];global.fetch=url=>url.endsWith('/messages')?
 new Promise(resolve=>replies.push(resolve)):
 Promise.resolve(ok({case_revision:2,conversations:[]}));
const first=ui.sendAgentMessage('运营问题');
ui.state.role='RISK_OFFICER';ui.state.agentBusy=false;
const second=ui.sendAgentMessage('风控问题');
replies[0](ok({answer:'旧运营答案'}));await first;
assert.equal(ui.state.agentBusy,true);
assert.equal(ui.state.agentDrafts['a:operations:synthetic-merchant-001'],'风控问题');
replies[1](ok({answer:'新风控答案'}));await second;
assert.equal(ui.state.agentBusy,false);
""")
