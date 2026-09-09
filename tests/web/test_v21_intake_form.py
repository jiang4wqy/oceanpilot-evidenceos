"""Canonical source forms preserve input and immutable event retry semantics."""

import json
import shutil
import subprocess
from importlib.resources import files

import pytest

from oceanpilot.api.dispute_intake import NormalizedEvent, RetryData
from oceanpilot.api.dispute_presenter import command_schema

DOM = r"""
const inputs = new Map(), notices = {}, handlers = {};
const confirm = {checked:false};
function node(name) {
  return {name,value:'',checked:false,required:false,disabled:false,type:'text',
    hidden:false,textContent:'',attrs:{},validityMessage:'',open:false,
    classList:{toggle(){}},setAttribute(){},
    addEventListener(type, callback){handlers[name+':'+type]=callback;},
    closest(){return {querySelector(){return {textContent:'',dataset:{fieldTitle:name}};}};},
    setCustomValidity(text){this.validityMessage=text;},
    showModal(){this.open=true;},close(){this.open=false;}};
}
const fields=node('fields');
Object.defineProperty(fields,'innerHTML',{get(){return this.html||'';},set(html){
  this.html=html;inputs.clear();
  for(const match of html.matchAll(/<(input|select|textarea)\b([^>]*)>/g)) {
    const attrs=Object.fromEntries(
      [...match[2].matchAll(/([\w-]+)="([^"]*)"/g)].map(m=>[m[1],m[2]]));
    if(!attrs.name)continue;
    const item=node(attrs.name);item.attrs=attrs;item.type=attrs.type||match[1];
    item.required=/\srequired\b/.test(match[2]);inputs.set(attrs.name,item);
  }
}});
const form=node('form');form.elements={namedItem:name=>inputs.get(name)||null};
form.reportValidity=()=>confirm.checked&&[...inputs.values()].every(input=>input.disabled||(
  !input.validityMessage&&(!input.required||input.type==='checkbox'&&input.checked||Boolean(input.value))));
const dialog=node('dialog');
const nodes=new Map([['form',form],['.intake-fields',fields],['.intake-confirm',confirm]]);
dialog.querySelector=selector=>{
  if(!nodes.has(selector))nodes.set(selector,node(selector));return nodes.get(selector);};
dialog.querySelectorAll=selector=>selector.startsWith('.intake-fields')?[...inputs.values()]:[];
global.document={createElement:()=>dialog,body:{append(){}}};
const host=node('host'), sent=[], opened=[];
let failGet=false, uncertain=false;
const events=[{id:'quarantine-one',status:'QUARANTINED',
  envelope:{source_event_id:'unchanged-source'}}];
async function api(path, options){
  if(!options){if(failGet)throw new Error('offline');return {events,form_schemas:schemas};}
  sent.push({path,body:options.body});
  if(uncertain){uncertain=false;const error=new Error('response lost');
    error.uncertain=true;throw error;}
  return {event:{status:'PROCESSED'},case_id:'case-result'};
}
const set=(name,value)=>{const input=inputs.get(name);
  assert.ok(input,'missing '+name);input.value=String(value);};
function fillBase(){
  for(const [key,value] of Object.entries({event_type:'FORMAL_DISPUTE',
    source_event_id:'source-form',
    channel:'MOCK',merchant_id:'merchant-a',transaction_id:'transaction-form',scheme:'VISA',
    amount_minor:'12800',currency:'USD',reason_code:'13.1',
    occurred_at:'2026-09-09T10:00',received_at:'2026-09-09T10:01'}))set(key,value);
  confirm.checked=true;handlers['form:input']();
}
const submit=()=>handlers['form:submit']({preventDefault(){}});
"""


def run_js(assertions):
    schemas = {"event": command_schema(NormalizedEvent), "retry": command_schema(RetryData)}
    script = files("oceanpilot.web").joinpath("v2/intake.js").read_text()
    result = subprocess.run(
        [shutil.which("node"), "-"],
        input="const assert=require('node:assert/strict');const schemas="
        + json.dumps(schemas)
        + ";\n"
        + DOM
        + script
        + "\n(async()=>{OceanV21Intake.mount({host,api,onCaseOpen:id=>opened.push(id)});"
        + assertions
        + "\n})().catch(error=>{console.error(error);process.exitCode=1;});",
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_form_renders_real_limits_and_submits_template_and_partial_amounts():
    run_js("""
await OceanV21Intake.open();
assert.equal(inputs.get('source_event_id').attrs.maxlength,'100');
assert.equal(inputs.get('channel').attrs.maxlength,'30');
assert.equal(inputs.get('currency').attrs.pattern,'^[A-Z]{3}$');
assert.equal(inputs.get('supported_minor').attrs.min,'0');
assert.equal(inputs.get('amount_minor').attrs.max,'1000000000000');
fillBase();set('case_template_id','CB-CASE-041');set('outcome','PARTIAL');
handlers['form:change']();
assert.equal(inputs.get('supported_minor').required,true);
assert.equal(inputs.get('liable_minor').required,true);
await submit();assert.equal(sent.length,0);
set('supported_minor','8000');set('liable_minor','4800');await submit();
const event=JSON.parse(sent[0].body).event;
assert.equal(event.case_template_id,'CB-CASE-041');
assert.equal(event.supported_minor,8000);assert.equal(event.liable_minor,4800);
assert.equal(typeof event.amount_minor,'number');assert.ok(event.received_at.endsWith('Z'));
assert.deepEqual(opened,['case-result']);
""")


def test_other_partial_mapping_preserves_reason_authority_and_pending_payload():
    run_js("""
await OceanV21Intake.open();fillBase();
set('event_type','CORRECTION');set('outcome','OTHER');set('mapped_outcome','PARTIAL');
set('corrects_event_id','prior-result');set('reason','Source calls this an adjusted result');
set('basis_reference','source-result-v2');set('authorization_reference','review-only-source');
set('supported_minor','0');set('liable_minor','12800');uncertain=true;
await submit();assert.equal(sent.length,1);
assert.equal(inputs.get('supported_minor').disabled,true);
set('supported_minor','999');set('source_event_id','must-not-replace');
await OceanV21Intake.open();await submit();
assert.equal(sent.length,2);assert.deepEqual(sent[1],sent[0]);
const event=JSON.parse(sent[0].body).event;
assert.equal(event.mapped_outcome,'PARTIAL');assert.equal(event.supported_minor,0);
assert.equal(event.reason,'Source calls this an adjusted result');
assert.equal(event.authorization_reference,'review-only-source');
""")


@pytest.mark.parametrize("amount", ["12.5", "9007199254740993"])
def test_fractional_and_unsafe_integers_never_become_rounded_source_values(amount):
    run_js(f"""
await OceanV21Intake.open();fillBase();set('amount_minor',{json.dumps(amount)});
await submit();assert.equal(sent.length,0);
assert.match(dialog.querySelector('.intake-notice').textContent,/整数/);
""")


def test_schema_failure_has_explicit_retry_and_cannot_submit_partial_form():
    run_js("""
await OceanV21Intake.refresh();delete schemas.event.fields.currency;
await OceanV21Intake.open();confirm.checked=true;await submit();
assert.equal(sent.length,0);assert.equal(dialog.querySelector('.intake-submit').disabled,true);
assert.match(fields.innerHTML,/重新获取表单/);
""")


def test_retry_form_uses_retry_contract_without_rewriting_original_event():
    run_js("""
await OceanV21Intake.open('quarantine-one');
assert.equal(inputs.get('reason').attrs.minlength,'3');
assert.equal(inputs.has('source_event_id'),false);
set('reason','Verified registry association');confirm.checked=true;await submit();
assert.deepEqual(JSON.parse(sent[0].body),{confirmed:true,reason:'Verified registry association'});
assert.equal(sent[0].path,'/intake/events/quarantine-one/retry');
assert.equal(events[0].envelope.source_event_id,'unchanged-source');
""")


def test_withdrawal_requires_explicit_final_confirmation_and_rejects_conflicting_outcome():
    run_js("""
await OceanV21Intake.open();fillBase();set('event_type','WITHDRAWAL');
handlers['form:change']();assert.equal(inputs.get('final').required,true);
await submit();assert.equal(sent.length,0);
inputs.get('final').checked=true;set('outcome','WON');await submit();
assert.equal(sent.length,0);assert.match(dialog.querySelector('.intake-notice').textContent,/撤回/);
set('outcome','WITHDRAWN');await submit();assert.equal(sent.length,1);
assert.equal(JSON.parse(sent[0].body).event.final,true);
""")


def test_terminal_other_mapping_and_correction_reference_have_conditional_required_fields():
    run_js("""
await OceanV21Intake.open();fillBase();set('event_type','CORRECTION');set('outcome','OTHER');
handlers['form:change']();assert.equal(inputs.get('corrects_event_id').required,true);
assert.equal(inputs.get('mapped_outcome').required,false);
inputs.get('final').checked=true;handlers['form:change']();
for(const key of ['mapped_outcome','basis_reference','authorization_reference']) {
  assert.equal(inputs.get(key).required,true,key);
}
await submit();assert.equal(sent.length,0);
set('corrects_event_id','prior-result');set('mapped_outcome','WON');
set('basis_reference','actual-source-notice');set('authorization_reference','source-review');
await submit();assert.equal(sent.length,1);
""")
