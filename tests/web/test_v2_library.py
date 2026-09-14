"""The case-library detail view renders the full source narrative on demand."""

import json
import shutil
import subprocess
from importlib.resources import files


def test_reference_detail_renders_full_case_content_without_bloating_collection():
    script = files("oceanpilot.web").joinpath("v2/library.js").read_text()
    collection = {
        "manifest": {"schema_version": "1.1"},
        "references": [
            {
                "template_id": "CB-CASE-001",
                "title": "油漆工泼漆",
                "summary": "摘要",
                "scheme": "MASTERCARD",
                "reason_code": "4853/4854",
                "evidence_level": "SOURCE_EXPLICIT",
                "verification_status": "VERIFIED_EXTRACTED",
                "source_ids": ["SRC-02"],
                "citations": [],
                "required_evidence": [],
                "sandbox_template_available": False,
            }
        ],
        "templates": [],
    }
    detail = {
        "reference": collection["references"][0],
        "template": None,
        "detail": {
            "source_excerpt": "持卡人与油漆工签订粉刷合同。",
            "extraction_confidence": "HIGH",
            "parties": {"merchant": "油漆工"},
            "fund_flow": {"who_paid_whom": "持卡人向商户支付 USD 500"},
            "transaction_facts": {"amount": "USD 500"},
            "dispute_facts": {"cardholder_claim": "沙发受损"},
            "process_flow": {"first_see": "识别规则排除"},
            "outcome": {"result": "NOT_STATED"},
            "oceanpilot_mapping": {"required_product_modules": ["案件详情", "Agent 解释"]},
        },
    }
    harness = r"""
const assert=require('node:assert/strict');
const nodes=new Map();
function node(name){return {name,innerHTML:'',hidden:false,value:'',dataset:{},
  addEventListener(){},removeEventListener(){},scrollIntoView(){},
  insertAdjacentHTML(_position,html){this.innerHTML+=html;},
  querySelector(){return null;},querySelectorAll(){return [];}};}
const list=node('list'), detailNode=node('detail');
const host=node('host');
host.querySelector=(selector)=>selector==='.library-reference-list'?list:
  selector==='.library-reference-detail'?detailNode:null;
global.document={getElementById:id=>id==='libraryView'?host:null,createElement:()=>node('created')};
global.window={innerWidth:1440,location:new URL('http://localhost/v2/operations/library?reference=CB-CASE-001'),
  history:{state:null,replaceState(_state,_title,url){window.location=new URL(url);}}};
global.URL=URL;global.URLSearchParams=URLSearchParams;
"""
    assertions = r"""
(async()=>{
  const calls=[];
  await window.OceanV2Library.mount({
    api:async path=>{calls.push(path);return path==='/case-library'?collection:detail;}
  });
  assert.deepEqual(calls,['/case-library','/case-library/CB-CASE-001']);
  assert.match(detailNode.innerHTML,/案例原文摘录/);
  assert.match(detailNode.innerHTML,/持卡人与油漆工签订粉刷合同/);
  assert.match(detailNode.innerHTML,/参与方/);
  assert.match(detailNode.innerHTML,/资金流与风险/);
  assert.match(detailNode.innerHTML,/交易事实/);
  assert.match(detailNode.innerHTML,/争议事实/);
  assert.match(detailNode.innerHTML,/处理流程/);
  assert.match(detailNode.innerHTML,/案例结果/);
  assert.match(detailNode.innerHTML,/OceanPilot 使用映射/);
  assert.match(detailNode.innerHTML,/此内容是参考资料，不是当前运行案件事实/);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        [shutil.which("node"), "-"],
        input=(
            harness
            + "\nconst collection="
            + json.dumps(collection, ensure_ascii=False)
            + ";\nconst detail="
            + json.dumps(detail, ensure_ascii=False)
            + ";\n"
            + script
            + assertions
        ),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
