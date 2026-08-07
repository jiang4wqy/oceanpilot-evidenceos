"""Self-contained single-page demo console for the chargeback cluster.

Served by FastAPI at ``GET /demo`` (kept out of the OpenAPI schema). Pure inline
HTML + vanilla JS that drives the existing JSON API — no build step, no external
assets, works offline. One premium console ties every backend capability
together: a stage pipeline, a prominent verdict card, and a trust rail
(prevention / safety guard / agent trace / audit / metrics), so a reviewer sees
the whole system — and its safety story (kernel decides / model explains / human
confirms / never executes) — on one screen. Ocean-blue corporate palette.
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
    --brand:#0a5cd6; --brand-2:#18a0e8; --brand-deep:#0b3ea8;
    --grad:linear-gradient(135deg,#0a5cd6,#18a0e8);
    --navy:#0f1e3d; --ink:#17233f;
    --bg:#eaf0f9; --panel:#ffffff; --panel-2:#f6f9ff; --line:#e2e9f4;
    --mut:#5f6f8c; --faint:#94a2bd;
    --ok:#0e9f6e; --ok-bg:#e7f7f0; --warn:#b06f08; --warn-bg:#fdf3e2;
    --bad:#d92d33; --bad-bg:#fdeaea; --info:#0a5cd6; --info-bg:#e9f1fd;
    --sh-sm:0 1px 2px rgba(16,35,63,.06); --sh:0 14px 34px -18px rgba(11,62,168,.35);
    --mono:"SF Mono","JetBrains Mono",ui-monospace,Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
    color:var(--ink);line-height:1.55;font-size:14px;background:var(--bg);
    -webkit-font-smoothing:antialiased;min-height:100vh}
  .wrap{max-width:1280px;margin:0 auto;padding:0 22px 48px}

  /* top bar */
  .topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:14px;flex-wrap:wrap;
    background:rgba(255,255,255,.9);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);
    margin:0 -22px;padding:12px 22px}
  .brand{display:flex;align-items:center;gap:11px}
  .logo{width:36px;height:36px;border-radius:10px;background:var(--grad);display:grid;place-items:center;
    color:#fff;font-weight:800;font-size:15px;box-shadow:0 6px 16px -6px rgba(10,92,214,.6)}
  .brand h1{margin:0;font-size:15.5px;font-weight:700;color:var(--navy);letter-spacing:.2px}
  .brand .sub{font-size:11.5px;color:var(--mut)}
  .spacer{flex:1}
  .tlink{color:var(--mut);font-size:12.5px;text-decoration:none;padding:7px 11px;border-radius:8px}
  .tlink:hover{color:var(--brand);background:var(--info-bg)}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;background:#fff}
  .seg button{background:#fff;border:0;color:var(--mut);padding:7px 12px;font-size:12.5px;cursor:pointer}
  .seg button.on{background:var(--grad);color:#fff;font-weight:700}

  /* hero */
  .hero{margin:18px 0 0;border-radius:18px;padding:26px 28px;color:#eaf2ff;position:relative;overflow:hidden;
    background:linear-gradient(125deg,#0b3ea8,#0a5cd6 52%,#1585d8);box-shadow:var(--sh)}
  .hero:after{content:"";position:absolute;right:-80px;top:-80px;width:320px;height:320px;border-radius:50%;
    background:radial-gradient(circle,rgba(255,255,255,.16),transparent 70%)}
  .hero h2{margin:0;font-size:23px;font-weight:750;letter-spacing:.3px;color:#fff}
  .hero p{margin:8px 0 0;font-size:13.5px;color:#cfe0fb;max-width:760px}
  .pillars{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:18px;position:relative}
  @media(max-width:820px){.pillars{grid-template-columns:1fr 1fr}}
  .pillar{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18);border-radius:12px;padding:12px 13px}
  .pillar .t{font-weight:700;font-size:13.5px;color:#fff;display:flex;align-items:center;gap:7px}
  .pillar .d{font-size:11.5px;color:#c3d8f7;margin-top:3px}
  .pdot{width:8px;height:8px;border-radius:50%;background:#7ee0b5;box-shadow:0 0 8px #7ee0b5}
  .pillar.red .pdot{background:#ffb4b4;box-shadow:0 0 8px #ffb4b4}

  /* pipeline */
  .pipe{display:flex;gap:0;margin:22px 4px 20px;overflow-x:auto;padding-bottom:2px}
  .stage{flex:1;min-width:100px;display:flex;flex-direction:column;align-items:center;position:relative;text-align:center}
  .stage .bar{position:absolute;top:18px;left:-50%;width:100%;height:3px;background:var(--line);z-index:0;border-radius:2px}
  .stage:first-child .bar{display:none}
  .stage.done .bar,.stage.active .bar{background:var(--grad)}
  .node{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;font-size:14px;font-weight:700;
    background:#fff;border:2px solid var(--line);color:var(--faint);position:relative;z-index:1;transition:.25s}
  .stage.done .node{background:var(--grad);color:#fff;border-color:transparent;box-shadow:0 6px 14px -6px rgba(10,92,214,.6)}
  .stage.active .node{color:var(--brand);border-color:var(--brand);box-shadow:0 0 0 5px var(--info-bg)}
  .stage .lbl{margin-top:9px;font-size:12.5px;color:var(--mut)}
  .stage.active .lbl,.stage.done .lbl{color:var(--navy);font-weight:600}

  .howto{font-size:12.5px;color:var(--mut);background:var(--info-bg);border:1px solid #d3e3fb;
    border-radius:11px;padding:11px 14px;margin-bottom:16px}
  .howto b{color:var(--brand)}

  /* layout */
  .grid{display:grid;grid-template-columns:1.55fr 1fr;gap:16px}
  @media(max-width:920px){.grid{grid-template-columns:1fr}}
  .col{display:flex;flex-direction:column;gap:16px}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px 20px;box-shadow:var(--sh-sm)}
  .eyebrow{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--brand);font-weight:700}
  .panel h3{margin:3px 0 14px;font-size:16px;font-weight:700;color:var(--navy);display:flex;align-items:center;gap:9px}
  .rail .panel{padding:15px 16px}
  .rail h3{font-size:14.5px;margin-bottom:10px}

  /* bits */
  .kv{display:flex;gap:10px;font-size:13.5px;margin:6px 0}
  .kv .k{color:var(--mut);min-width:72px;font-weight:500}
  .kv code{font-family:var(--mono);font-size:12px;background:var(--panel-2);border:1px solid var(--line);
    padding:1px 7px;border-radius:6px;word-break:break-all;color:var(--ink)}
  .muted{color:var(--mut);font-size:12.5px} .faint{color:var(--faint)}
  .badge{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:650}
  .b-ok{background:var(--ok-bg);color:var(--ok)} .b-warn{background:var(--warn-bg);color:var(--warn)}
  .b-bad{background:var(--bad-bg);color:var(--bad)} .b-info{background:var(--info-bg);color:var(--info)}
  .b-mut{background:#eef1f7;color:var(--mut)}
  .row{display:flex;gap:9px;flex-wrap:wrap;align-items:center} .mt{margin-top:13px}
  button.btn{border:0;border-radius:10px;padding:10px 16px;font-size:13.5px;font-weight:650;cursor:pointer;color:#fff;
    background:var(--grad);box-shadow:0 10px 22px -12px rgba(10,92,214,.8);transition:.16s}
  button.btn:hover{transform:translateY(-1px);filter:brightness(1.04)}
  button.ghost{background:#fff;color:var(--brand);border:1px solid #cfe0fb;box-shadow:none}
  button.danger{background:#fff;color:var(--bad);border:1px solid #f3c9cb;box-shadow:none}
  button:disabled{opacity:.45;cursor:not-allowed;transform:none!important}
  textarea,select,input{width:100%;background:#fff;color:var(--ink);border:1px solid var(--line);border-radius:10px;
    padding:11px;font-size:13.5px;font-family:inherit}
  textarea:focus,select:focus,input:focus{outline:none;border-color:var(--brand);box-shadow:0 0 0 3px var(--info-bg)}
  label.chk{display:inline-flex;align-items:center;gap:7px;color:var(--mut);font-size:12.5px;
    border:1px solid var(--line);border-radius:9px;padding:8px 11px;cursor:pointer;background:#fff}

  .phase-pill{font-size:11px;letter-spacing:.08em;text-transform:uppercase}

  /* verdict hero */
  .verdict{display:flex;align-items:center;gap:22px;background:linear-gradient(120deg,var(--panel-2),#eef4ff);
    border:1px solid #dbe6f8;border-radius:14px;padding:18px 20px}
  .verdict .win{font-size:52px;font-weight:820;line-height:1;letter-spacing:-.03em;
    background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
  .verdict .vcap{font-size:12px;color:var(--mut);margin-top:4px}
  .verdict .vside{flex:1;display:flex;flex-direction:column;gap:8px}
  .cov{height:9px;border-radius:6px;background:#e3ebf7;overflow:hidden}
  .cov > i{display:block;height:100%;background:var(--grad);border-radius:6px}
  .chks{list-style:none;padding:0;margin:14px 0 0;display:grid;grid-template-columns:1fr 1fr;gap:6px 16px}
  @media(max-width:560px){.chks{grid-template-columns:1fr}}
  .chks li{font-size:13px;display:flex;align-items:center;gap:7px}
  .ck{width:18px;height:18px;border-radius:50%;display:grid;place-items:center;font-size:11px;color:#fff;flex:0 0 auto}
  .ck.y{background:var(--ok)} .ck.n{background:#c9d3e5}
  .explain{font-size:13px;color:var(--ink);background:var(--panel-2);border-left:3px solid var(--brand);
    border-radius:0 8px 8px 0;padding:10px 13px;margin-top:14px}

  /* timeline / trace / metrics */
  .tl{list-style:none;margin:4px 0 0;padding:0;position:relative}
  .tl:before{content:"";position:absolute;left:6px;top:6px;bottom:6px;width:2px;background:var(--line)}
  .tl li{position:relative;padding:4px 0 9px 22px;font-size:12.5px}
  .tl li:before{content:"";position:absolute;left:0;top:7px;width:13px;height:13px;border-radius:50%;background:#fff;border:2px solid var(--brand)}
  .tl .ev{font-weight:650;color:var(--navy)}
  .trace{list-style:none;margin:0;padding:0}
  .trace li{padding:8px 0;border-bottom:1px solid var(--line);font-size:12.5px;display:flex;gap:9px;align-items:flex-start}
  .trace li:last-child{border-bottom:0}
  .agent{font-family:var(--mono);font-size:11px;color:#fff;background:var(--brand);padding:2px 7px;border-radius:6px;white-space:nowrap}
  .metrics{display:grid;grid-template-columns:1fr auto;gap:5px 12px;font-size:12.5px}
  .metrics .k{color:var(--mut);font-family:var(--mono);font-size:11px}
  .metrics .v{font-weight:700;text-align:right;color:var(--navy)}
  .empty{color:var(--faint);font-size:12.5px;font-style:italic}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="brand"><div class="logo">OP</div>
      <div><h1>跨境拒付申诉控制台</h1><div class="sub">OceanPilot EvidenceOS · 多智能体集群</div></div>
    </div>
    <div class="spacer"></div>
    <a class="tlink" href="/docs" target="_blank" rel="noopener">API 文档</a>
    <a class="tlink" href="/health" target="_blank" rel="noopener">健康</a>
    <div class="seg"><button id="loc-zh" class="on" onclick="setLocale('zh')">中文</button>
      <button id="loc-en" onclick="setLocale('en')">EN</button></div>
    <button class="btn ghost" onclick="reset()">＋ 新建案件</button>
  </div>

  <div class="hero">
    <h2>证据驱动的跨境拒付申诉</h2>
    <p>把一次拒付串成可检查的闭环：判定 → 补证 → 评估 → 打包 → 申诉 → 审计。确定性内核做决策，智能体只做解释，人来拍板。</p>
    <div class="pillars">
      <div class="pillar"><div class="t"><span class="pdot"></span>确定性内核决策</div><div class="d">胜诉率/路由/是否人工由规则给出</div></div>
      <div class="pillar"><div class="t"><span class="pdot"></span>智能体解释建议</div><div class="d">LLM 仅解释，不可达时确定性兜底</div></div>
      <div class="pillar"><div class="t"><span class="pdot"></span>人工确认闸门</div><div class="d">理由确认、申诉提交均需人工</div></div>
      <div class="pillar red"><div class="t"><span class="pdot"></span>绝不执行 · 仅合成</div><div class="d">不碰支付/退款/风控，无真实数据</div></div>
    </div>
  </div>

  <div class="pipe" id="pipe"></div>

  <div class="howto">如何评审：① 选一个<b>示例场景</b>点「⚡自动补证跑到评估」一键跑完 ·
    ② 看<b>结论卡</b>的胜诉率、决策来源与证据构成，验证「内核决策、模型仅解释」 ·
    ③ 右侧<b>安全护栏</b>提交一个卡号看它被当场拦截。</div>

  <div class="grid">
    <div class="col">
      <div class="panel">
        <div class="eyebrow">CASE</div><h3>案件</h3>
        <div id="caseHead"><div class="empty">尚未建案。在下方选择场景并开始。</div></div>
      </div>
      <div class="panel">
        <div class="eyebrow">CURRENT STEP</div><h3>当前步骤</h3>
        <div id="action"></div>
      </div>
      <div class="panel" id="assessCard" style="display:none">
        <div class="eyebrow">VERDICT</div><h3>胜诉评估 · 打包 · 申诉</h3>
        <div id="assessBody"></div>
      </div>
    </div>

    <div class="col rail">
      <div class="panel">
        <div class="eyebrow">PREVENTION</div><h3>交易前风险</h3>
        <div class="row">
          <label class="chk"><input type="checkbox" id="p_no3ds"> 无 3DS</label>
          <label class="chk"><input type="checkbox" id="p_noavs"> AVS 不符</label>
          <label class="chk"><input type="checkbox" id="p_cross"> 跨境</label>
        </div>
        <div class="row mt"><input id="p_amount" placeholder="金额，如 4200" style="max-width:150px" />
          <button class="btn" onclick="assessPrevention()">评估</button></div>
        <div id="preventionOut" class="mt"></div>
      </div>
      <div class="panel">
        <div class="eyebrow">SAFETY</div><h3>安全护栏 · PII / 卡号</h3>
        <textarea id="safeText" rows="2">请退款到卡号 4111 1111 1111 1111</textarea>
        <div class="row mt"><button class="btn" onclick="safetyScan()">扫描</button>
          <span class="muted">复用领域守卫 · 不回显输入</span></div>
        <div id="safeOut" class="mt"></div>
      </div>
      <div class="panel">
        <div class="eyebrow">AGENTS</div><h3>智能体决策轨迹</h3>
        <ul id="traceOut" class="trace"><li class="empty">—</li></ul>
      </div>
      <div class="panel">
        <div class="eyebrow">AUDIT</div><h3>审计轨迹</h3>
        <ul id="auditOut" class="tl"><li class="empty">建案后自动记录。</li></ul>
      </div>
      <div class="panel">
        <div class="eyebrow">METRICS</div><h3>决策指标</h3>
        <div id="metricsOut" class="empty">—</div>
      </div>
    </div>
  </div>
</div>

<script>
const BASE="/api/v1/chargeback";
const S={caseId:null, loc:"zh", packaged:false, appealed:false, last:null};
const SCENARIOS=[
  {label:"未收到货（可胜诉）",desc:"客户下单后一直没收到货，现在要求拒付。"},
  {label:"无卡欺诈（需人工）",desc:"这笔交易不是我本人，是被盗刷的。"},
  {label:"退款未入账",desc:"我已经申请退款，但一直没有退到账。"},
  {label:"原因不明（需人工确认）",desc:"这是一段无法自动判定的中性描述内容。"},
];
const $=(id)=>document.getElementById(id);
const esc=(s)=>String(s==null?"":s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
async function api(m,p,b){const o={method:m,headers:{'Content-Type':'application/json'}};
  if(b!==undefined)o.body=JSON.stringify(b);
  const r=await fetch(BASE+p,o);return{ok:r.ok,status:r.status,data:await r.json().catch(()=>({}))};}

function setLocale(l){S.loc=l;$('loc-zh').classList.toggle('on',l==='zh');$('loc-en').classList.toggle('on',l==='en');
  if(S.caseId)refreshCase();}
function reset(){S.caseId=null;S.packaged=false;S.appealed=false;S.last=null;
  $('caseHead').innerHTML='<div class="empty">尚未建案。在下方选择场景并开始。</div>';
  $('assessCard').style.display='none';$('traceOut').innerHTML='<li class="empty">—</li>';
  $('auditOut').innerHTML='<li class="empty">建案后自动记录。</li>';renderStages();renderAction();}

const STAGES=["立案","确认原因","补证","评估","打包","申诉"];
function stageStatus(){
  const st=STAGES.map(()=> "pending");const d=S.last;
  if(!S.caseId){st[0]="active";return st;}
  st[0]="done";const ph=d?d.phase:null;
  st[1]=(d&&d.reason_confirmed)?"done":(ph==="REASON_PROPOSED"?"active":"done");
  if(ph==="REASON_PROPOSED")return st;
  if(ph==="NEED_EVIDENCE"){st[2]="active";return st;}
  st[2]="done";st[3]="done";st[4]=S.packaged?"done":"active";
  if(S.packaged)st[5]=S.appealed?"done":"active";
  return st;
}
function renderStages(){const stt=stageStatus();
  $('pipe').innerHTML=STAGES.map((n,i)=>`<div class="stage ${stt[i]}"><div class="bar"></div>`
    +`<div class="node">${stt[i]==="done"?"✓":(i+1)}</div><div class="lbl">${n}</div></div>`).join("");}

async function openCase(){const desc=$('desc').value.trim();
  const {ok,data}=await api("POST","/cases",{description:desc});
  if(!ok){$('action').innerHTML='<div class="badge b-bad">建案失败：描述不能为空</div>';return;}
  S.caseId=data.case_id;S.packaged=false;S.appealed=false;apply(data);}
async function refreshCase(){if(!S.caseId)return;apply((await api("GET",`/cases/${S.caseId}`)).data);}
async function confirmReason(){const v=$('fix')?$('fix').value:"";
  apply((await api("POST",`/cases/${S.caseId}/confirm`, v?{reason_code:v}:{})).data);}
async function submitEvidence(code){apply((await api("POST",`/cases/${S.caseId}/evidence`,{evidence_code:code})).data);}
async function finalize(){apply((await api("POST",`/cases/${S.caseId}/finalize`)).data);}
function fillScenario(){const s=$('scenario');const d=$('desc');if(s&&d)d.value=SCENARIOS[+s.value].desc;}
async function autoRun(){if(!S.caseId){await openCase();}let g=0;
  while(S.last&&S.last.phase!=="ASSESSED"&&g++<40){
    if(S.last.phase==="REASON_PROPOSED")await confirmReason();
    else if(S.last.phase==="NEED_EVIDENCE")await submitEvidence(S.last.next_evidence);
    else break;}}

function apply(d){if(!d||!d.case_id)return;S.last=d;
  renderCaseHead(d);renderStages();renderAction();renderTrace(d);
  const ready=d.phase==="ASSESSED";$('assessCard').style.display=ready?"block":"none";
  if(ready)renderAssess(d);refreshAudit();refreshMetrics();}

function renderCaseHead(d){
  const conf=d.reason_confirmed?'<span class="badge b-ok">已确认</span>':'<span class="badge b-warn">待确认</span>';
  let h=`<div class="kv"><span class="k">案件</span><code>${esc(d.case_id)}</code></div>`
    +`<div class="kv"><span class="k">争议原因</span><span>${esc(d.reason_code||"—")} ${conf}</span></div>`;
  if(d.deadline){const od=d.deadline.overdue?' <span class="badge b-bad">已逾期</span>':'';
    h+=`<div class="kv"><span class="k">举证时限</span><span>还剩 ${d.deadline.days_remaining} 天${od}</span></div>`;}
  if(d.facts&&d.facts.summary)h+=`<div class="kv"><span class="k">识别要点</span><span>${esc(d.facts.summary)}</span></div>`;
  $('caseHead').innerHTML=h;}

function renderAction(){const d=S.last;
  if(!S.caseId){
    const opts=SCENARIOS.map((s,i)=>`<option value="${i}">${esc(s.label)}</option>`).join("");
    $('action').innerHTML=`<div class="row" style="margin-bottom:9px"><span class="muted">示例场景</span>`
      +`<select id="scenario" style="max-width:260px" onchange="fillScenario()">${opts}</select></div>`
      +`<textarea id="desc" rows="2">${esc(SCENARIOS[0].desc)}</textarea>`
      +`<div class="row mt"><button class="btn" onclick="openCase()">建案 · 开始</button>`
      +`<button class="btn ghost" onclick="autoRun()">⚡ 自动补证跑到评估</button></div>`;
    return;}
  const ph=d.phase;
  if(ph==="REASON_PROPOSED"){
    $('action').innerHTML=`<span class="badge b-warn phase-pill">待人工确认原因</span>`
      +`<div class="muted mt">${esc(d.question||"")}</div>`
      +`<div class="row mt"><select id="fix" style="max-width:280px"></select>`
      +`<button class="btn" onclick="confirmReason()">确认 / 更正</button></div>`;
    populateReasons();
  }else if(ph==="NEED_EVIDENCE"){
    $('action').innerHTML=`<span class="badge b-info phase-pill">补证进行中</span>`
      +`<div class="mt" style="font-size:15px;color:var(--navy);font-weight:600">${esc(d.question||"")}</div>`
      +`<div class="row mt"><button class="btn" onclick="submitEvidence('${esc(d.next_evidence)}')">我已提交该证据</button>`
      +`<button class="btn ghost" onclick="autoRun()">⚡ 自动补齐剩余</button>`
      +`<button class="btn danger" onclick="finalize()">无法提供更多 · 转人工</button></div>`;
  }else if(ph==="ASSESSED"){
    $('action').innerHTML=`<span class="badge b-ok phase-pill">评估完成</span>`
      +`<div class="muted mt">证据已达标，结论见下方。</div>`;
  }else $('action').innerHTML=`<div class="muted">阶段：${esc(ph)}</div>`;}
async function populateReasons(){const {data}=await api("GET",`/catalog?locale=${S.loc}`);const sel=$('fix');if(!sel)return;
  sel.innerHTML='<option value="">（接受系统判定）</option>'
    +data.reasons.map(r=>`<option value="${esc(r.code)}">${esc(r.label)}</option>`).join("");}

function renderAssess(d){const a=d.assessment;if(!a)return;
  const rev=a.requires_human?'<span class="badge b-warn">需人工复核</span>':'<span class="badge b-ok">可自动推进</span>';
  const src=a.explanation_source==="MODEL"?"模型":"确定性兜底";
  const bd=a.evidence_breakdown||[];const have=bd.filter(i=>i.present).length;
  const pct=bd.length?Math.round(have/bd.length*100):0;
  const chk=bd.map(i=>`<li><span class="ck ${i.present?'y':'n'}">${i.present?'✓':'×'}</span>`
    +`${esc(i.label)}${i.critical?' <span class="faint">·关键</span>':''}</li>`).join("");
  let h=`<div class="verdict"><div><div class="win">${esc(a.win_likelihood)}</div>`
    +`<div class="vcap">胜诉可能性 · 内核判定</div></div>`
    +`<div class="vside"><div class="row">${rev} <span class="badge b-info">责任域 ${esc(a.responsible_team)}</span>`
    +`<span class="badge b-mut">说明来源：${src}</span></div>`
    +`<div class="muted">证据完整度 ${have}/${bd.length}</div><div class="cov"><i style="width:${pct}%"></i></div></div></div>`
    +`<ul class="chks">${chk}</ul>`
    +`<div class="explain">${esc(a.explanation)}</div>`
    +`<div class="row mt"><button class="btn" onclick="doPackage()">生成打包</button>`
    +`<button class="btn ghost" onclick="doAppeal(false)">生成申诉草稿</button>`
    +`<button class="btn danger" onclick="doAppeal(true)">人工批准并提交</button></div>`
    +`<div id="pkgOut" class="mt"></div><div id="appealOut" class="mt"></div>`;
  $('assessBody').innerHTML=h;}
async function doPackage(){const {ok,data}=await api("GET",`/cases/${S.caseId}/package?locale=${S.loc}`);
  if(!ok){$('pkgOut').innerHTML='<div class="badge b-warn">案件未就绪</div>';return;}
  S.packaged=true;renderStages();
  $('pkgOut').innerHTML=`<div class="kv"><span class="k">打包</span><span><b style="color:var(--navy)">${esc(data.reason_label)}</b>`
    +` · 规则 ${esc(data.rule_source)} · 完整度 ${esc(data.completeness)} `
    +`${data.ready_to_submit?'<span class="badge b-ok">可提交</span>':'<span class="badge b-warn">未就绪</span>'}</span></div>`
    +`<div class="kv"><span class="k">随附</span><span>${data.ordered_evidence.map(e=>esc(e.label)).join("、")||"—"}</span></div>`
    +`<div class="explain">${esc(data.cover_note)}</div>`;}
async function doAppeal(approve){const body=approve?{human_approved:true,actor_id:"ou_reviewer"}:{};
  const {data}=await api("POST",`/cases/${S.caseId}/appeal`,body);
  if(data.submitted){S.appealed=true;renderStages();}
  const badge=data.submitted?'<span class="badge b-ok">已提交上游(mock)</span>'
    :`<span class="badge b-warn">未提交 · ${esc(data.blocked_reason||"")}</span>`;
  $('appealOut').innerHTML=`<div class="kv"><span class="k">申诉</span><span>${badge}`
    +(data.submission_id?` <code>${esc(data.submission_id)}</code>`:"")+`</span></div>`
    +`<div class="explain" style="white-space:pre-wrap">${esc(data.draft)}</div>`;
  refreshAudit();refreshMetrics();}

function renderTrace(d){const t=d.agent_trace||[];
  $('traceOut').innerHTML=t.length?t.map(x=>`<li><span class="agent">${esc(x.agent)}</span>`
    +`<span>${esc(x.action)}${x.source?` <span class="faint">(${esc(x.source)})</span>`:""}</span></li>`).join("")
    :'<li class="empty">—</li>';}
async function refreshAudit(){if(!S.caseId)return;const {ok,data}=await api("GET",`/cases/${S.caseId}/audit`);if(!ok)return;
  $('auditOut').innerHTML=data.events.map(e=>`<li><span class="ev">${esc(e.event_type)}</span>`
    +`${e.detail?` <span class="faint">${esc(e.detail)}</span>`:""} <span class="faint">· rev${e.case_revision}</span></li>`).join("")
    ||'<li class="empty">—</li>';}
async function refreshMetrics(){const {data}=await api("GET","/metrics");const c=(data&&data.counts)||{};const ks=Object.keys(c);
  $('metricsOut').innerHTML=ks.length?`<div class="metrics">`
    +ks.map(k=>`<span class="k">${esc(k)}</span><span class="v">${c[k]}</span>`).join("")+`</div>`:'<span class="empty">暂无</span>';}
async function assessPrevention(){
  const b={three_ds_authenticated:!$('p_no3ds').checked,avs_match:!$('p_noavs').checked,
    cross_border:$('p_cross').checked,amount:($('p_amount').value||"0")};
  const {ok,data}=await api("POST","/prevention/assess",b);
  if(!ok){$('preventionOut').innerHTML='<div class="badge b-bad">请求无效</div>';return;}
  const cls={LOW:'b-ok',MEDIUM:'b-warn',HIGH:'b-bad'}[data.risk_level]||'b-mut';
  $('preventionOut').innerHTML=`<span class="badge ${cls}">风险 ${esc(data.risk_level)} · ${esc(data.risk_score)}</span>`
    +`<div class="kv mt"><span class="k">因子</span><span>${data.factors.map(esc).join("、")||"—"}</span></div>`
    +`<div class="kv"><span class="k">建议留证</span><span>${data.recommended_evidence.map(e=>esc(e.label)).join("、")||"—"}</span></div>`
    +`<div class="muted">${esc(data.advice)}</div>`;refreshMetrics();}
async function safetyScan(){const {ok,data}=await api("POST","/safety/scan",{text:$('safeText').value});
  if(!ok){$('safeOut').innerHTML='<div class="badge b-bad">请求无效</div>';return;}
  const badge=data.accepted?'<span class="badge b-ok">✓ 通过</span>':'<span class="badge b-bad">⛔ 已拦截</span>';
  $('safeOut').innerHTML=`${badge} <span class="muted">${esc(data.detail)}</span>`;}

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
