"""Hero copy must never prescribe delivery evidence to unrelated cases."""

import subprocess
from pathlib import Path


def test_stage_is_opt_in_and_only_supported_for_the_prepared_synthetic_hero():
    script = Path("src/oceanpilot/web/v2/stage.js").read_text()
    checks = """
const assert=require('node:assert/strict');
const c={scheme:'VISA',reason_code:'13.1',channel:'MOCK',merchant_decision:'CONTEST',
 rule_snapshot:{production_eligible:false}};
const plan={checklist:[...['receipt','tracking','address','comms'].map(code=>({code,present:true})),
 {code:'fulfillment.proof_of_delivery',present:false}]};
global.OceanV2={state:{current:c,plan}};
global.location={href:'http://localhost/v2/merchant/cases/one?stage=1',pathname:'/v2/merchant/cases/one'};
assert(OceanV2Stage.enabled());
assert(!OceanV2Stage.supports({...c,reason_code:'10.4'},plan));
assert(!OceanV2Stage.supports({...c,channel:'LIVE'},plan));
assert(!OceanV2Stage.supports({...c,merchant_decision:'ACCEPT'},plan));
assert(!OceanV2Stage.supports(c,null));
assert(!OceanV2Stage.supports(c,{checklist:plan.checklist.map(i=>({...i,present:false}))}));
location.href='http://localhost/v2/merchant/cases/one';assert(!OceanV2Stage.enabled());
"""
    result = subprocess.run(["node", "-"], input=script + checks, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
