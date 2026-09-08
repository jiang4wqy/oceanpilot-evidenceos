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
OceanV2.renderDetail();
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
const first=OceanV2.openCase('a'),second=OceanV2.openCase('b');
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
await OceanV2.openCase('a');
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
