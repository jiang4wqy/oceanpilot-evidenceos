from tests.web.test_v2_rendering import run_js


def test_material_guidance_tracks_current_case_and_stops_after_accept():
    run_js(
        r"""
const ui = OceanV2;
ui.state.role = 'MERCHANT'; ui.state.isCasePage = true;
ui.state.current = {...sample, revision:3,
 work_status:'EVIDENCE_COLLECTING', merchant_decision:'CONTEST'};
ui.state.plan = {revision:3,checklist:[
{label:'交易收据',expected_source:'MERCHANT_UPLOAD',present:false},
{label:'签收证明',expected_source:'OCR_THEN_REVIEW',present:false,
 upload_status:'NEEDS_MANUAL'},
{label:'收货地址匹配',expected_source:'SYSTEM_OF_RECORD',present:false}]};
ui.renderDetail();
assert.ok(node('caseDetail').innerHTML.includes('接下来请准备这些材料'));
assert.ok(node('caseDetail').innerHTML.includes('签收证明（已上传，待人工核验）'));
assert.ok(node('caseDetail').innerHTML.includes('由 OceanPayment 补充或核对：收货地址匹配'));
ui.state.current.merchant_decision='ACCEPT';ui.state.current.work_status='ACCEPT_PROCESSING';ui.renderDetail();
assert.ok(!node('caseDetail').innerHTML.includes('OceanPilot 材料指引'));
ui.state.current.merchant_decision='CONTEST';ui.state.current.work_status='CLOSED';ui.renderDetail();
assert.ok(!node('caseDetail').innerHTML.includes('OceanPilot 材料指引'));
""",
        surface="merchant",
    )
