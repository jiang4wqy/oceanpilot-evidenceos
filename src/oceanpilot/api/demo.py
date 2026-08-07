"""Self-contained single-page demo console for the chargeback cluster.

Served by FastAPI at ``GET /demo`` (kept out of the OpenAPI schema). Pure inline
HTML + vanilla JS that drives the existing JSON API — no build step, no external
assets, works offline. One unified console ties every backend capability
together: a stage pipeline down the middle (open → confirm → evidence → assess →
package → appeal) with an always-on side rail (prevention, agent trace, audit,
metrics), so a reviewer sees the whole system — and its safety story (kernel
decides / model explains / human confirms / never executes) — on one screen.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()

_DEMO_HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>OceanPilot · 跨境拒付申诉控制台</title>
<style>
  :root{
    --accent1:#6366f1; --accent2:#22d3ee;
    --ok:#34d399; --warn:#fbbf24; --bad:#f87171; --info:#38bdf8;
    --fg:#e6ebf5; --mut:#9aa7bd; --faint:#64748b;
    --line:rgba(255,255,255,.09); --line2:rgba(255,255,255,.06);
    --card:rgba(255,255,255,.035); --card2:rgba(255,255,255,.02);
    --shadow:0 10px 30px -12px rgba(0,0,0,.6);
    --mono:"SF Mono","JetBrains Mono",ui-monospace,Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
    color:var(--fg); line-height:1.55; font-size:14px;
    background:
      radial-gradient(1200px 700px at 12% -8%, rgba(99,102,241,.18), transparent 60%),
      radial-gradient(1000px 650px at 100% 0%, rgba(34,211,238,.12), transparent 55%),
      #070b16;
    min-height:100vh;
  }
  a{color:var(--info)}
  .wrap{max-width:1240px; margin:0 auto; padding:20px 22px 44px}

  /* top bar */
  .topbar{display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-bottom:6px}
  .brand{display:flex; align-items:center; gap:11px}
  .logo{width:34px;height:34px;border-radius:9px;
    background:linear-gradient(135deg,var(--accent1),var(--accent2));
    display:grid;place-items:center;font-weight:800;color:#06121f;box-shadow:0 6px 18px -6px rgba(34,211,238,.6)}
  .brand h1{margin:0;font-size:16px;font-weight:700;letter-spacing:.2px}
  .brand .sub{font-size:12px;color:var(--mut)}
  .spacer{flex:1}
  .safety{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--mut);
    border:1px solid var(--line);background:var(--card);border-radius:999px;padding:6px 12px}
  .safety b{color:var(--ok)}
  .dot{width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 10px var(--ok)}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  .seg button{background:transparent;border:0;color:var(--mut);padding:6px 11px;font-size:12px;cursor:pointer}
  .seg button.on{background:linear-gradient(135deg,var(--accent1),var(--accent2));color:#06121f;font-weight:700}
  .lnk{color:var(--mut);font-size:12px;text-decoration:none;border:1px solid var(--line);border-radius:8px;
    padding:6px 10px;background:var(--card)}
  .lnk:hover{color:var(--fg);border-color:var(--accent2)}
  .howto{margin:10px 2px 0;font-size:12.5px;color:var(--mut);border:1px solid var(--line);
    background:var(--card);border-radius:10px;padding:9px 13px}
  .howto b{color:var(--fg)}

  /* pipeline */
  .pipe{display:flex;align-items:flex-start;gap:0;margin:20px 2px 22px;overflow-x:auto;padding-bottom:4px}
  .stage{flex:1;min-width:96px;display:flex;flex-direction:column;align-items:center;position:relative;text-align:center}
  .stage .bar{position:absolute;top:17px;left:-50%;width:100%;height:2px;background:var(--line);z-index:0}
  .stage:first-child .bar{display:none}
  .stage.done .bar,.stage.active .bar{background:linear-gradient(90deg,var(--accent1),var(--accent2))}
  .node{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;font-size:13px;font-weight:700;
    background:#0d1424;border:1px solid var(--line);color:var(--mut);position:relative;z-index:1;transition:.25s}
  .stage.done .node{background:linear-gradient(135deg,var(--accent1),var(--accent2));color:#06121f;border-color:transparent}
  .stage.active .node{color:#fff;border-color:var(--accent2);box-shadow:0 0 0 4px rgba(34,211,238,.16);
    animation:pulse 1.8s infinite}
  @keyframes pulse{0%,100%{box-shadow:0 0 0 4px rgba(34,211,238,.16)}50%{box-shadow:0 0 0 7px rgba(34,211,238,.05)}}
  .stage .lbl{margin-top:8px;font-size:12px;color:var(--mut)}
  .stage.active .lbl{color:var(--fg);font-weight:600}
  .stage.done .lbl{color:var(--fg)}

  /* layout */
  .grid{display:grid;grid-template-columns:1.55fr 1fr;gap:16px}
  @media(max-width:900px){.grid{grid-template-columns:1fr}}
  .col{display:flex;flex-direction:column;gap:16px}
  .card{background:linear-gradient(180deg,var(--card),var(--card2));border:1px solid var(--line);
    border-radius:14px;padding:16px 17px;box-shadow:var(--shadow);backdrop-filter:blur(6px)}
  .card h2{margin:0 0 12px;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--info);
    display:flex;align-items:center;gap:8px}
  .card h2 .n{width:18px;height:18px;border-radius:6px;background:rgba(56,189,248,.14);color:var(--info);
    display:grid;place-items:center;font-size:11px;font-weight:800}
  .rail .card{padding:14px 15px}

  /* bits */
  .kv{display:flex;gap:8px;font-size:13px;margin:4px 0}
  .kv b{color:var(--mut);font-weight:500;min-width:64px}
  .kv code{font-family:var(--mono);font-size:12px;color:var(--fg);background:rgba(255,255,255,.05);
    padding:1px 6px;border-radius:5px;word-break:break-all}
  .muted{color:var(--mut);font-size:12.5px}
  .faint{color:var(--faint)}
  .badge{display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;
    border:1px solid transparent}
  .b-ok{background:rgba(52,211,153,.13);color:var(--ok)}
  .b-warn{background:rgba(251,191,36,.13);color:var(--warn)}
  .b-bad{background:rgba(248,113,113,.13);color:var(--bad)}
  .b-info{background:rgba(56,189,248,.13);color:var(--info)}
  .b-mut{background:rgba(148,163,184,.12);color:var(--mut)}
  .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
  .mt{margin-top:12px}
  button.btn{border:0;border-radius:9px;padding:9px 15px;font-size:13px;font-weight:650;cursor:pointer;
    color:#06121f;background:linear-gradient(135deg,var(--accent1),var(--accent2));
    box-shadow:0 8px 20px -10px rgba(34,211,238,.7);transition:.18s}
  button.btn:hover{transform:translateY(-1px);filter:brightness(1.06)}
  button.btn:active{transform:translateY(0)}
  button.ghost{background:rgba(255,255,255,.06);color:var(--fg);box-shadow:none;border:1px solid var(--line)}
  button.danger{background:rgba(248,113,113,.14);color:#fecaca;box-shadow:none;border:1px solid rgba(248,113,113,.3)}
  button:disabled{opacity:.4;cursor:not-allowed;transform:none!important;filter:none!important}
  textarea,select,input{width:100%;background:#0a1120;color:var(--fg);border:1px solid var(--line);
    border-radius:9px;padding:10px;font-size:13px;font-family:inherit}
  textarea:focus,select:focus,input:focus{outline:none;border-color:var(--accent2)}
  label.chk{display:inline-flex;align-items:center;gap:6px;color:var(--mut);font-size:12.5px;
    border:1px solid var(--line);border-radius:8px;padding:6px 9px;cursor:pointer}

  /* action zone */
  .action{border:1px dashed var(--line);border-radius:12px;padding:15px;background:rgba(56,189,248,.03)}
  .phase-pill{font-size:11px;letter-spacing:.1em;text-transform:uppercase}

  /* evidence checklist */
  .chks{list-style:none;padding:0;margin:8px 0 0;display:grid;grid-template-columns:1fr 1fr;gap:4px 14px}
  @media(max-width:520px){.chks{grid-template-columns:1fr}}
  .chks li{font-size:12.5px;display:flex;align-items:center;gap:6px}
  .win{font-size:30px;font-weight:800;letter-spacing:-.02em;
    background:linear-gradient(135deg,#fff,var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent}

  /* timeline */
  .tl{list-style:none;margin:6px 0 0;padding:0;position:relative}
  .tl:before{content:"";position:absolute;left:6px;top:4px;bottom:4px;width:2px;background:var(--line)}
  .tl li{position:relative;padding:3px 0 8px 22px;font-size:12.5px}
  .tl li:before{content:"";position:absolute;left:1px;top:7px;width:11px;height:11px;border-radius:50%;
    background:#0d1424;border:2px solid var(--accent2)}
  .tl .ev{font-weight:600}
  .trace{list-style:none;margin:0;padding:0}
  .trace li{padding:6px 0;border-bottom:1px solid var(--line2);font-size:12.5px;display:flex;gap:8px;align-items:flex-start}
  .trace li:last-child{border-bottom:0}
  .agent{font-family:var(--mono);font-size:11px;color:var(--accent2);white-space:nowrap;margin-top:1px}
  .met{display:grid;grid-template-columns:1fr auto;gap:2px 10px;font-size:12.5px}
  .met .k{color:var(--mut);font-family:var(--mono);font-size:11px}
  .met .v{font-weight:700;text-align:right}
  .empty{color:var(--faint);font-size:12.5px;font-style:italic}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="brand">
      <div class="logo">OP</div>
      <div><h1>跨境拒付申诉控制台</h1>
        <div class="sub">OceanPilot EvidenceOS · 多智能体集群 · 合成数据</div></div>
    </div>
    <div class="spacer"></div>
    <div class="safety"><span class="dot"></span>内核决策 · 模型解释 · 人工确认 · <b>绝不执行业务动作</b></div>
    <a class="lnk" href="/docs" target="_blank" rel="noopener">API 文档</a>
    <a class="lnk" href="/health" target="_blank" rel="noopener">健康</a>
    <div class="seg"><button id="loc-zh" class="on" onclick="setLocale('zh')">中文</button>
      <button id="loc-en" onclick="setLocale('en')">EN</button></div>
    <button class="btn ghost" onclick="reset()">＋ 新建案件</button>
  </div>

  <!-- pipeline -->
  <div class="pipe" id="pipe"></div>

  <div class="grid">
    <!-- spine -->
    <div class="col">
      <div class="card">
        <h2><span class="n">◆</span> 案件</h2>
        <div id="caseHead"><div class="empty">尚未建案。在下方描述问题即可开始。</div></div>
      </div>

      <div class="card">
        <h2><span class="n">▶</span> 当前步骤</h2>
        <div id="action"></div>
      </div>

      <div class="card" id="assessCard" style="display:none">
        <h2><span class="n">✓</span> 胜诉评估 · 打包 · 申诉</h2>
        <div id="assessBody"></div>
      </div>
    </div>

    <!-- rail -->
    <div class="col rail">
      <div class="card">
        <h2><span class="n">⚑</span> 交易前风险（预防）</h2>
        <div class="row">
          <label class="chk"><input type="checkbox" id="p_no3ds"> 无 3DS</label>
          <label class="chk"><input type="checkbox" id="p_noavs"> AVS 不符</label>
          <label class="chk"><input type="checkbox" id="p_cross"> 跨境</label>
        </div>
        <div class="row mt"><input id="p_amount" placeholder="金额，如 4200" style="max-width:150px" />
          <button class="btn" onclick="assessPrevention()">评估</button></div>
        <div id="preventionOut" class="mt"></div>
      </div>

      <div class="card">
        <h2><span class="n">⇄</span> 智能体决策轨迹</h2>
        <ul id="traceOut" class="trace"><li class="empty">—</li></ul>
      </div>

      <div class="card">
        <h2><span class="n">◷</span> 审计轨迹</h2>
        <ul id="auditOut" class="tl"><li class="empty">建案后自动记录。</li></ul>
      </div>

      <div class="card">
        <h2><span class="n">▤</span> 决策指标</h2>
        <div id="metricsOut" class="empty">—</div>
      </div>
    </div>
  </div>
</div>

<script>
const BASE="/api/v1/chargeback";
const S={caseId:null, loc:"zh", packaged:false, appealed:false, last:null};
const $=(id)=>document.getElementById(id);
const esc=(s)=>String(s==null?"":s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
async function api(m,p,b){const o={method:m,headers:{'Content-Type':'application/json'}};
  if(b!==undefined)o.body=JSON.stringify(b);
  const r=await fetch(BASE+p,o);return{ok:r.ok,status:r.status,data:await r.json().catch(()=>({}))};}

function setLocale(l){S.loc=l;$('loc-zh').classList.toggle('on',l==='zh');$('loc-en').classList.toggle('on',l==='en');
  if(S.caseId){refreshCase();}}
function reset(){S.caseId=null;S.packaged=false;S.appealed=false;S.last=null;
  $('caseHead').innerHTML='<div class="empty">尚未建案。在下方描述问题即可开始。</div>';
  $('assessCard').style.display='none';$('traceOut').innerHTML='<li class="empty">—</li>';
  $('auditOut').innerHTML='<li class="empty">建案后自动记录。</li>';renderStages();renderAction();}

/* ---------- pipeline ---------- */
const STAGES=["立案","确认原因","补证","评估","打包","申诉"];
function stageStatus(){
  const st=STAGES.map(()=> "pending"); const d=S.last;
  if(!S.caseId){st[0]="active";return st;}
  st[0]="done";
  const ph=d?d.phase:null;
  const confirmed=d&&d.reason_confirmed;
  st[1]= confirmed?"done":(ph==="REASON_PROPOSED"?"active":"done");
  if(ph==="REASON_PROPOSED"){return st;}
  if(ph==="NEED_EVIDENCE"){st[2]="active";return st;}
  // ASSESSED or beyond
  st[2]="done";st[3]="done";
  st[4]= S.packaged?"done":"active";
  if(S.packaged) st[5]= S.appealed?"done":"active";
  return st;
}
function renderStages(){
  const stt=stageStatus();
  $('pipe').innerHTML=STAGES.map((name,i)=>{
    const num=stt[i]==="done"?"✓":(i+1);
    return `<div class="stage ${stt[i]}"><div class="bar"></div>`
      +`<div class="node">${num}</div><div class="lbl">${name}</div></div>`;
  }).join("");
}

/* ---------- case + flow ---------- */
async function openCase(){
  const desc=$('desc').value.trim();
  const {ok,data}=await api("POST","/cases",{description:desc});
  if(!ok){$('action').innerHTML='<div class="badge b-bad">建案失败：描述不能为空</div>';return;}
  S.caseId=data.case_id;S.packaged=false;S.appealed=false;apply(data);
}
async function refreshCase(){if(!S.caseId)return;apply((await api("GET",`/cases/${S.caseId}`)).data);}
async function confirmReason(){const v=$('fix')?$('fix').value:"";
  apply((await api("POST",`/cases/${S.caseId}/confirm`, v?{reason_code:v}:{})).data);}
async function submitEvidence(code){apply((await api("POST",`/cases/${S.caseId}/evidence`,{evidence_code:code})).data);}
async function finalize(){apply((await api("POST",`/cases/${S.caseId}/finalize`)).data);}

function apply(d){
  if(!d||!d.case_id)return; S.last=d;
  renderCaseHead(d); renderStages(); renderAction(); renderTrace(d);
  const ready=d.phase==="ASSESSED";
  $('assessCard').style.display=ready?"block":"none";
  if(ready) renderAssess(d);
  refreshAudit(); refreshMetrics();
}

function renderCaseHead(d){
  const conf=d.reason_confirmed?'<span class="badge b-ok">已确认</span>':'<span class="badge b-warn">待确认</span>';
  let h=`<div class="kv"><b>案件</b><code>${esc(d.case_id)}</code></div>`
    +`<div class="kv"><b>争议原因</b><span>${esc(d.reason_code||"—")}</span> ${conf}</div>`;
  if(d.deadline){const od=d.deadline.overdue?' <span class="badge b-bad">已逾期</span>':'';
    h+=`<div class="kv"><b>举证时限</b><span>还剩 ${d.deadline.days_remaining} 天${od}</span></div>`;}
  if(d.facts&&d.facts.summary)h+=`<div class="kv"><b>识别要点</b><span>${esc(d.facts.summary)}</span></div>`;
  $('caseHead').innerHTML=h;
}

function renderAction(){
  const d=S.last;
  if(!S.caseId){
    $('action').innerHTML=`<textarea id="desc" rows="2">客户下单后一直没收到货，现在要求拒付。</textarea>`
      +`<div class="row mt"><button class="btn" onclick="openCase()">建案 · 开始</button>`
      +`<span class="muted">系统将判定争议原因并逐项补证</span></div>`;
    return;
  }
  const ph=d.phase;
  if(ph==="REASON_PROPOSED"){
    $('action').innerHTML=`<div class="badge b-warn phase-pill">待人工确认原因</div>`
      +`<div class="muted mt">${esc(d.question||"")}</div>`
      +`<div class="row mt"><select id="fix" style="max-width:280px"></select>`
      +`<button class="btn" onclick="confirmReason()">确认 / 更正</button></div>`;
    populateReasons();
  } else if(ph==="NEED_EVIDENCE"){
    $('action').innerHTML=`<div class="badge b-info phase-pill">补证进行中</div>`
      +`<div class="mt" style="font-size:14px">${esc(d.question||"")}</div>`
      +`<div class="row mt"><button class="btn" onclick="submitEvidence('${esc(d.next_evidence)}')">我已提交该证据</button>`
      +`<button class="btn danger" onclick="finalize()">无法提供更多 · 转人工</button></div>`;
  } else if(ph==="ASSESSED"){
    $('action').innerHTML=`<div class="badge b-ok phase-pill">评估完成</div>`
      +`<div class="muted mt">证据已达标，见右下「评估 · 打包 · 申诉」。</div>`;
  } else {
    $('action').innerHTML=`<div class="muted">阶段：${esc(ph)}</div>`;
  }
}
async function populateReasons(){
  const {data}=await api("GET",`/catalog?locale=${S.loc}`);const sel=$('fix');if(!sel)return;
  sel.innerHTML='<option value="">（接受系统判定）</option>'
    +data.reasons.map(r=>`<option value="${esc(r.code)}">${esc(r.label)}</option>`).join("");
}

function renderAssess(d){
  const a=d.assessment;if(!a)return;
  const rev=a.requires_human?'<span class="badge b-warn">需人工复核</span>':'<span class="badge b-ok">可自动推进</span>';
  const src=a.explanation_source==="MODEL"?"模型":"确定性兜底";
  const chk=a.evidence_breakdown.map(i=>`<li>${i.present?'✅':'❌'}${i.critical?'⭐':''} ${esc(i.label)}`
    +` <span class="faint">·w${i.weight}</span></li>`).join("");
  let h=`<div class="row" style="align-items:baseline;gap:14px">`
    +`<span class="win">${esc(a.win_likelihood)}</span>${rev}`
    +`<span class="muted">责任域 ${esc(a.responsible_team)}</span></div>`
    +`<ul class="chks">${chk}</ul>`
    +`<div class="muted mt">说明（来源：${src}；数字由内核判定）：${esc(a.explanation)}</div>`;
  // package + appeal controls
  h+=`<div class="row mt"><button class="btn" onclick="doPackage()">生成打包</button>`
    +`<button class="btn ghost" onclick="doAppeal(false)">生成申诉草稿</button>`
    +`<button class="btn danger" onclick="doAppeal(true)">人工批准并提交</button></div>`
    +`<div id="pkgOut" class="mt"></div><div id="appealOut" class="mt"></div>`;
  $('assessBody').innerHTML=h;
}
async function doPackage(){
  const {ok,data}=await api("GET",`/cases/${S.caseId}/package?locale=${S.loc}`);
  if(!ok){$('pkgOut').innerHTML='<div class="badge b-warn">案件未就绪</div>';return;}
  S.packaged=true;renderStages();
  $('pkgOut').innerHTML=`<div class="kv"><b>打包</b><span><b style="color:var(--fg)">${esc(data.reason_label)}</b>`
    +` · 规则 ${esc(data.rule_source)} · 完整度 ${esc(data.completeness)} `
    +`${data.ready_to_submit?'<span class="badge b-ok">可提交</span>':'<span class="badge b-warn">未就绪</span>'}</span></div>`
    +`<div class="kv"><b>随附</b><span>${data.ordered_evidence.map(e=>esc(e.label)).join("、")||"—"}</span></div>`
    +`<div class="muted">${esc(data.cover_note)}</div>`;
}
async function doAppeal(approve){
  const body=approve?{human_approved:true,actor_id:"ou_reviewer"}:{};
  const {data}=await api("POST",`/cases/${S.caseId}/appeal`,body);
  if(data.submitted){S.appealed=true;renderStages();}
  const badge=data.submitted?'<span class="badge b-ok">已提交上游(mock)</span>'
    :`<span class="badge b-warn">未提交 · ${esc(data.blocked_reason||"")}</span>`;
  $('appealOut').innerHTML=`<div class="kv"><b>申诉</b><span>${badge}`
    +(data.submission_id?` <code>${esc(data.submission_id)}</code>`:"")+`</span></div>`
    +`<div class="muted" style="white-space:pre-wrap;border-left:2px solid var(--line);padding-left:10px;margin-top:6px">${esc(data.draft)}</div>`;
  refreshAudit();refreshMetrics();
}

/* ---------- rail ---------- */
function renderTrace(d){
  const t=d.agent_trace||[];
  $('traceOut').innerHTML=t.length? t.map(x=>`<li><span class="agent">${esc(x.agent)}</span>`
    +`<span>${esc(x.action)}${x.source?` <span class="faint">(${esc(x.source)})</span>`:""}</span></li>`).join("")
    :'<li class="empty">—</li>';
}
async function refreshAudit(){
  if(!S.caseId)return;const {ok,data}=await api("GET",`/cases/${S.caseId}/audit`);if(!ok)return;
  $('auditOut').innerHTML=data.events.map(e=>`<li><span class="ev">${esc(e.event_type)}</span>`
    +`${e.detail?` <span class="faint">${esc(e.detail)}</span>`:""}`
    +` <span class="faint">· rev${e.case_revision}</span></li>`).join("")||'<li class="empty">—</li>';
}
async function refreshMetrics(){
  const {data}=await api("GET","/metrics");const c=(data&&data.counts)||{};const ks=Object.keys(c);
  $('metricsOut').innerHTML=ks.length?`<div class="met">`
    +ks.map(k=>`<span class="k">${esc(k)}</span><span class="v">${c[k]}</span>`).join("")+`</div>`
    :'<span class="empty">暂无</span>';
}
async function assessPrevention(){
  const b={three_ds_authenticated:!$('p_no3ds').checked,avs_match:!$('p_noavs').checked,
    cross_border:$('p_cross').checked,amount:($('p_amount').value||"0")};
  const {ok,data}=await api("POST","/prevention/assess",b);
  if(!ok){$('preventionOut').innerHTML='<div class="badge b-bad">请求无效</div>';return;}
  const cls={LOW:'b-ok',MEDIUM:'b-warn',HIGH:'b-bad'}[data.risk_level]||'b-mut';
  $('preventionOut').innerHTML=`<span class="badge ${cls}">风险 ${esc(data.risk_level)} · ${esc(data.risk_score)}</span>`
    +`<div class="kv mt"><b>因子</b><span>${data.factors.map(esc).join("、")||"—"}</span></div>`
    +`<div class="kv"><b>建议留证</b><span>${data.recommended_evidence.map(e=>esc(e.label)).join("、")||"—"}</span></div>`
    +`<div class="muted">${esc(data.advice)}</div>`;
  refreshMetrics();
}

/* boot */
renderStages();renderAction();refreshMetrics();
</script>
</body>
</html>
"""


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/demo")


@router.get("/demo", include_in_schema=False, response_class=HTMLResponse)
def demo_page() -> HTMLResponse:
    return HTMLResponse(_DEMO_HTML)
