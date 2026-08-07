"""Self-contained single-page console for the chargeback cluster.

Served by FastAPI at ``GET /demo`` (kept out of the OpenAPI schema). Pure inline
HTML + vanilla JS driving the existing JSON API — no build step, no external
assets, works offline. Application-shell layout (dark sidebar · focused
workspace · pinned activity rail) modeled on dispute-review tooling: summary
before detail, state encoded as pills/severity, a restrained cool-neutral
palette with a single brand accent, light/dark aware. The safety story (kernel
decides / model explains / human confirms / never executes) is always on screen.
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
    --canvas:#f5f6f8; --surface:#ffffff; --sunken:#eef1f5; --border:#e4e8ef; --border-2:#d7dce5;
    --ink:#121722; --body:#39424f; --muted:#6a7280; --faint:#9aa2ae;
    --side:#10151f; --side-2:#0b0f17; --side-ink:#e8ebf1; --side-muted:#8892a2; --side-active:#1a2434; --side-border:#20293a;
    --accent:#1f5fe0; --accent-soft:#e8f0ff;
    --good:#0e9c6b; --good-bg:#e6f5ee; --warn:#b4791c; --warn-bg:#faf1df; --crit:#d14343; --crit-bg:#fbecec;
    --sh:0 1px 2px rgba(18,23,34,.05),0 12px 28px -18px rgba(18,23,34,.18);
    --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  }
  @media (prefers-color-scheme:dark){:root{
    --canvas:#0b0f16; --surface:#121821; --sunken:#0e141c; --border:#232c39; --border-2:#2c3745;
    --ink:#eef1f6; --body:#b9c2cf; --muted:#8b95a4; --faint:#6b7686; --accent:#5b8bff; --accent-soft:#16233c;
    --good:#34d39e; --good-bg:#0f2a22; --warn:#e0a94a; --warn-bg:#2c2312; --crit:#f0868a; --crit-bg:#2e1719;
  }}
  :root[data-theme="light"]{
    --canvas:#f5f6f8; --surface:#ffffff; --sunken:#eef1f5; --border:#e4e8ef; --border-2:#d7dce5;
    --ink:#121722; --body:#39424f; --muted:#6a7280; --faint:#9aa2ae; --accent:#1f5fe0; --accent-soft:#e8f0ff;
    --good:#0e9c6b; --good-bg:#e6f5ee; --warn:#b4791c; --warn-bg:#faf1df; --crit:#d14343; --crit-bg:#fbecec;
  }
  :root[data-theme="dark"]{
    --canvas:#0b0f16; --surface:#121821; --sunken:#0e141c; --border:#232c39; --border-2:#2c3745;
    --ink:#eef1f6; --body:#b9c2cf; --muted:#8b95a4; --faint:#6b7686; --accent:#5b8bff; --accent-soft:#16233c;
    --good:#34d39e; --good-bg:#0f2a22; --warn:#e0a94a; --warn-bg:#2c2312; --crit:#f0868a; --crit-bg:#2e1719;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--canvas);color:var(--body);font-family:var(--sans);font-size:14px;line-height:1.55;
    -webkit-font-smoothing:antialiased}
  .app{display:grid;grid-template-columns:236px 1fr;min-height:100vh}
  @media(max-width:840px){.app{grid-template-columns:1fr}.side{display:none}}
  a{color:var(--accent)}

  .side{background:var(--side);color:var(--side-ink);display:flex;flex-direction:column;
    border-right:1px solid var(--side-border);position:sticky;top:0;height:100vh}
  .sbrand{display:flex;align-items:center;gap:10px;padding:18px 18px 14px}
  .mark{width:30px;height:30px;border-radius:8px;background:var(--accent);display:grid;place-items:center;color:#fff;font-weight:800;font-size:13px}
  .sbrand .nm{font-weight:700;font-size:14px;color:#fff}
  .sbrand .rl{font-size:11px;color:var(--side-muted)}
  .navlbl{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#5c6577;padding:12px 15px 6px}
  .nav{padding:6px 8px}
  .nav a{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:8px;color:var(--side-muted);
    text-decoration:none;font-size:13px;cursor:pointer;user-select:none}
  .nav a .ic{width:15px;height:15px;border:1.6px solid currentColor;border-radius:4px;opacity:.7}
  .nav a:hover{color:var(--side-ink);background:var(--side-active)}
  .nav a.on{color:#fff;background:var(--side-active)}
  .nav a.on .ic{background:var(--accent);border-color:var(--accent);opacity:1}
  .sfoot{margin-top:auto;padding:14px}
  .guard{border:1px solid var(--side-border);border-radius:10px;padding:12px;background:var(--side-2)}
  .guard .h{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#5c6577;margin-bottom:8px}
  .guard .g{display:flex;align-items:center;gap:8px;font-size:12px;color:#c3cad6;margin:5px 0}
  .gd{width:6px;height:6px;border-radius:50%;background:var(--good)} .gd.r{background:var(--crit)}

  .main{display:flex;flex-direction:column;min-width:0}
  .top{display:flex;align-items:center;gap:10px;padding:12px 24px;border-bottom:1px solid var(--border);
    background:var(--surface);position:sticky;top:0;z-index:5;flex-wrap:wrap}
  .crumb{font-size:13px;color:var(--muted)} .crumb b{color:var(--ink);font-weight:600}
  .crumb .id{font-family:var(--mono);font-size:12.5px;color:var(--ink)}
  .grow{flex:1}
  .tlink{color:var(--muted);font-size:12.5px;text-decoration:none;padding:6px 9px;border-radius:7px}
  .tlink:hover{color:var(--accent);background:var(--accent-soft)}
  .seg{display:inline-flex;border:1px solid var(--border);border-radius:8px;overflow:hidden}
  .seg button{background:var(--surface);border:0;color:var(--muted);padding:6px 11px;font-size:12px;cursor:pointer;font-family:var(--sans)}
  .seg button.on{background:var(--accent);color:#fff;font-weight:600}
  .tbtn{border:1px solid var(--border);background:var(--surface);color:var(--body);border-radius:8px;padding:7px 12px;
    font-size:12.5px;cursor:pointer;font-family:var(--sans)}
  .tbtn:hover{border-color:var(--border-2)}
  .tbtn.primary{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
  .tbtn.primary:hover{filter:brightness(1.05)}
  .tbtn.danger{color:var(--crit);border-color:var(--border)}
  .tbtn:disabled{opacity:.45;cursor:not-allowed}

  .howto{margin:16px 24px 0;font-size:12.5px;color:var(--muted);background:var(--accent-soft);
    border:1px solid var(--border);border-radius:10px;padding:10px 14px}
  .howto b{color:var(--accent)}

  .content{padding:18px 24px 30px;display:grid;grid-template-columns:1fr 328px;gap:22px;align-items:start}
  @media(max-width:1080px){.content{grid-template-columns:1fr}}
  .stack{display:flex;flex-direction:column;gap:18px;min-width:0}
  .view{display:none} .view.on{display:grid}

  .summary{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px;box-shadow:var(--sh)}
  .srow{display:flex;flex-wrap:wrap;gap:24px}
  .field .k{font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--faint);margin-bottom:3px}
  .field .v{font-size:14px;color:var(--ink);font-weight:600}
  .field .v.mono{font-family:var(--mono);font-weight:500;font-size:13px}
  .num{font-variant-numeric:tabular-nums}
  .pill{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:6px;font-size:12px;font-weight:600}
  .p-good{background:var(--good-bg);color:var(--good)} .p-warn{background:var(--warn-bg);color:var(--warn)}
  .p-crit{background:var(--crit-bg);color:var(--crit)} .p-mut{background:var(--sunken);color:var(--muted)}
  .p-acc{background:var(--accent-soft);color:var(--accent)}

  .steps{display:flex;align-items:center;flex-wrap:wrap;gap:6px 0;margin-top:16px}
  .step{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--faint)}
  .step .b{width:20px;height:20px;border-radius:50%;border:1.6px solid var(--border-2);display:grid;place-items:center;
    font-size:11px;color:var(--faint);background:var(--surface);font-variant-numeric:tabular-nums}
  .step.done .b{background:var(--accent);border-color:var(--accent);color:#fff}
  .step.now .b{border-color:var(--accent);color:var(--accent)}
  .step.done,.step.now{color:var(--ink);font-weight:600}
  .sep{width:22px;height:1.6px;background:var(--border);margin:0 8px} .sep.done{background:var(--accent)}

  .card{background:var(--surface);border:1px solid var(--border);border-radius:12px;box-shadow:var(--sh)}
  .card .hd{padding:13px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
  .card .hd h3{margin:0;font-size:14px;color:var(--ink);font-weight:700}
  .eyebrow{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);font-weight:700}
  .bd{padding:16px 18px}

  .verdict{display:flex;gap:24px;align-items:center;flex-wrap:wrap}
  .vnum{font-family:var(--mono);font-size:46px;font-weight:700;line-height:1;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
  .vcap{font-size:12px;color:var(--muted);margin-top:6px}
  .vmeta{flex:1;display:flex;flex-direction:column;gap:10px;min-width:210px}
  .cov{display:flex;align-items:center;gap:10px}
  .track{flex:1;height:7px;border-radius:5px;background:var(--sunken);overflow:hidden}
  .track > i{display:block;height:100%;background:var(--accent)}
  .cov .n{font-family:var(--mono);font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
  .ev{display:grid;grid-template-columns:1fr 1fr;gap:8px 22px;margin-top:16px;border-top:1px solid var(--border);padding-top:14px}
  @media(max-width:560px){.ev{grid-template-columns:1fr}}
  .ei{display:flex;align-items:center;gap:9px;font-size:13px;color:var(--body)}
  .tick{width:18px;height:18px;border-radius:50%;display:grid;place-items:center;font-size:11px;flex:0 0 auto}
  .tick.y{background:var(--good-bg);color:var(--good)} .tick.n{background:var(--sunken);color:var(--faint)}
  .crit-tag{font-size:11px;color:var(--warn);background:var(--warn-bg);padding:0 6px;border-radius:5px}
  .note{margin-top:14px;font-size:13px;color:var(--body);background:var(--sunken);border-radius:8px;padding:11px 13px}
  .note b{color:var(--ink)}
  .actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}

  .rail{display:flex;flex-direction:column;gap:18px;position:sticky;top:74px}
  @media(max-width:1080px){.rail{position:static}}
  .tl{list-style:none;margin:0;padding:0;position:relative}
  .tl:before{content:"";position:absolute;left:5px;top:5px;bottom:6px;width:1.6px;background:var(--border)}
  .tl li{position:relative;padding:0 0 15px 20px}
  .tl li:before{content:"";position:absolute;left:0;top:4px;width:11px;height:11px;border-radius:50%;background:var(--surface);border:2px solid var(--accent)}
  .tl .e{font-size:12.5px;color:var(--ink);font-weight:600}
  .tl .m{font-size:11.5px;color:var(--muted);font-family:var(--mono)}
  .agent{display:flex;gap:9px;padding:9px 0;border-bottom:1px solid var(--border);font-size:12.5px}
  .agent:last-child{border-bottom:0}
  .atag{font-family:var(--mono);font-size:10.5px;color:#fff;background:var(--accent);padding:2px 6px;border-radius:5px;height:fit-content;white-space:nowrap}
  .src{font-size:10.5px;color:var(--faint);font-family:var(--mono)}
  .metrics{display:grid;grid-template-columns:1fr auto;gap:6px 12px;font-family:var(--mono);font-size:12px}
  .metrics .k{color:var(--muted)} .metrics .v{color:var(--ink);font-weight:700;text-align:right;font-variant-numeric:tabular-nums}

  .kv{display:flex;gap:10px;font-size:13px;margin:6px 0} .kv .k{color:var(--muted);min-width:64px}
  .kv code{font-family:var(--mono);font-size:12px;background:var(--sunken);padding:1px 6px;border-radius:5px;word-break:break-all;color:var(--ink)}
  .muted{color:var(--muted);font-size:12.5px} .faint{color:var(--faint)}
  .row{display:flex;gap:9px;flex-wrap:wrap;align-items:center} .mt{margin-top:12px}
  textarea,select,input{width:100%;background:var(--surface);color:var(--ink);border:1px solid var(--border);border-radius:9px;
    padding:10px;font-size:13.5px;font-family:var(--sans)}
  textarea:focus,select:focus,input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
  label.chk{display:inline-flex;align-items:center;gap:7px;color:var(--muted);font-size:12.5px;border:1px solid var(--border);border-radius:8px;padding:8px 11px;cursor:pointer;background:var(--surface)}
  .empty{color:var(--faint);font-size:12.5px}
  :focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  @media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
  .schips{display:flex;flex-wrap:wrap;gap:8px;margin:2px 0 12px}
  .schip{border:1px solid var(--border);background:var(--surface);color:var(--body);border-radius:999px;
    padding:6px 13px;font-size:12.5px;cursor:pointer;font-family:var(--sans)}
  .schip:hover{border-color:var(--border-2)}
  .schip.on{border-color:var(--accent);color:var(--accent);background:var(--accent-soft);font-weight:600}
  .mstat{margin:0 0 12px}
  .mstat .ml{display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted);margin-bottom:4px}
  .mstat .ml b{color:var(--ink);font-variant-numeric:tabular-nums;font-family:var(--mono);font-weight:600}
  .mbar{height:8px;border-radius:5px;background:var(--sunken);overflow:hidden}
  .mbar > i{display:block;height:100%;background:var(--accent)}
  .mnote{display:grid;grid-template-columns:1fr auto;gap:4px 12px;font-family:var(--mono);font-size:11px;
    color:var(--muted);border-top:1px solid var(--border);padding-top:10px;margin-top:4px}
  .mnote b{color:var(--body);font-weight:600;text-align:right;font-variant-numeric:tabular-nums}
</style>
</head>
<body>
<div class="app">
  <aside class="side">
    <div class="sbrand"><div class="mark">OP</div>
      <div><div class="nm">OceanPilot</div><div class="rl">EvidenceOS · 跨境拒付集群</div></div></div>
    <div class="navlbl">工作台</div>
    <nav class="nav">
      <a class="on" data-v="flow"><span class="ic"></span>拒付处理</a>
      <a data-v="prev"><span class="ic"></span>交易前预防</a>
      <a data-v="safe"><span class="ic"></span>安全与指标</a>
    </nav>
    <div class="sfoot"><div class="guard">
      <div class="h">运行边界</div>
      <div class="g"><span class="gd"></span>确定性内核决策</div>
      <div class="g"><span class="gd"></span>智能体仅解释建议</div>
      <div class="g"><span class="gd"></span>关键动作人工确认</div>
      <div class="g"><span class="gd r"></span>绝不执行 · 仅合成数据</div>
    </div></div>
  </aside>

  <div class="main">
    <div class="top">
      <div class="crumb">拒付处理 <b>/</b> <span id="crumbId" class="id">新建案件</span></div>
      <div class="grow"></div>
      <a class="tlink" href="/docs" target="_blank" rel="noopener">API 文档</a>
      <a class="tlink" href="/health" target="_blank" rel="noopener">健康</a>
      <div class="seg"><button id="loc-zh" class="on" onclick="setLocale('zh')">中文</button>
        <button id="loc-en" onclick="setLocale('en')">EN</button></div>
      <button class="tbtn" onclick="toggleTheme()">切换主题</button>
      <button class="tbtn primary" onclick="reset()">＋ 新建案件</button>
    </div>

    <div class="howto">如何评审：① 在「拒付处理」选<b>示例场景</b>点「⚡自动补证跑到评估」一键跑完 ·
      ② 看<b>胜诉评估</b>的概率、决策来源与证据构成，验证「内核决策、模型仅解释」 ·
      ③ 到「安全与指标」提交一个卡号看<b>安全护栏</b>当场拦截。</div>

    <!-- 拒付处理 -->
    <div class="content view on" id="v-flow">
      <div class="stack">
        <div class="summary">
          <div id="caseHead"><span class="empty">尚未建案 · 在下方选择场景开始。</span></div>
          <div class="steps" id="steps"></div>
        </div>
        <div class="card">
          <div class="hd"><h3>当前步骤</h3><span class="eyebrow" id="phaseTag">Intake</span></div>
          <div class="bd" id="action"></div>
        </div>
        <div class="card" id="verdictCard" style="display:none">
          <div class="hd"><h3>胜诉评估</h3><span class="eyebrow">Kernel-decided</span></div>
          <div class="bd" id="verdictBody"></div>
        </div>
      </div>
      <div class="rail">
        <div class="card">
          <div class="hd"><h3>活动</h3><span class="eyebrow">Audit</span></div>
          <div class="bd"><ul class="tl" id="auditOut"><li class="empty">建案后自动记录。</li></ul></div>
        </div>
        <div class="card">
          <div class="hd"><h3>智能体轨迹</h3><span class="eyebrow">Agents</span></div>
          <div class="bd" id="agentOut"><div class="empty">—</div></div>
        </div>
      </div>
    </div>

    <!-- 交易前预防 -->
    <div class="content view" id="v-prev">
      <div class="stack"><div class="card">
        <div class="hd"><h3>交易前风险评估</h3><span class="eyebrow">Prevention</span></div>
        <div class="bd">
          <div class="row">
            <label class="chk"><input type="checkbox" id="p_no3ds" style="width:auto"> 无 3DS</label>
            <label class="chk"><input type="checkbox" id="p_noavs" style="width:auto"> AVS 不符</label>
            <label class="chk"><input type="checkbox" id="p_cross" style="width:auto"> 跨境</label>
            <input id="p_amount" placeholder="金额 4200" style="max-width:150px">
            <button class="tbtn primary" onclick="assessPrevention()">评估</button>
          </div>
          <div id="preventionOut" class="mt"></div>
        </div>
      </div></div>
      <div class="rail"></div>
    </div>

    <!-- 安全与指标 -->
    <div class="content view" id="v-safe">
      <div class="stack">
        <div class="card">
          <div class="hd"><h3>安全护栏 · PII / 卡号</h3><span class="eyebrow">Safety</span></div>
          <div class="bd">
            <input type="text" id="safeText" value="请退款到卡号 4111 1111 1111 1111">
            <div class="actions"><button class="tbtn primary" onclick="safetyScan()">扫描</button>
              <span class="muted">复用领域守卫 · 不回显输入</span></div>
            <div id="safeOut" class="mt"></div>
          </div>
        </div>
        <div class="card">
          <div class="hd"><h3>决策指标</h3><span class="eyebrow">Metrics</span></div>
          <div class="bd" id="metricsOut"><span class="empty">—</span></div>
        </div>
      </div>
      <div class="rail"></div>
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
const PHASE={NEEDS_INTAKE:["未建案","p-mut","Intake"],REASON_PROPOSED:["待确认原因","p-warn","Confirm"],
  NEED_EVIDENCE:["补证中","p-acc","Evidence"],ASSESSED:["评估完成","p-good","Verdict"]};
const $=(id)=>document.getElementById(id);
const esc=(s)=>String(s==null?"":s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
async function api(m,p,b){const o={method:m,headers:{'Content-Type':'application/json'}};
  if(b!==undefined)o.body=JSON.stringify(b);
  const r=await fetch(BASE+p,o);return{ok:r.ok,status:r.status,data:await r.json().catch(()=>({}))};}

function toggleTheme(){const r=document.documentElement;
  const cur=r.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  r.setAttribute('data-theme',cur==='dark'?'light':'dark');}
document.querySelectorAll('.nav a').forEach(a=>a.addEventListener('click',()=>{
  const v=a.dataset.v;document.querySelectorAll('.nav a').forEach(x=>x.classList.remove('on'));a.classList.add('on');
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('on'));$('v-'+v).classList.add('on');}));
function setLocale(l){S.loc=l;$('loc-zh').classList.toggle('on',l==='zh');$('loc-en').classList.toggle('on',l==='en');
  if(S.caseId)refreshCase();}
function reset(){S.caseId=null;S.packaged=false;S.appealed=false;S.last=null;
  $('caseHead').innerHTML='<span class="empty">尚未建案 · 在下方选择场景开始。</span>';
  $('crumbId').textContent='新建案件';$('verdictCard').style.display='none';
  $('auditOut').innerHTML='<li class="empty">建案后自动记录。</li>';$('agentOut').innerHTML='<div class="empty">—</div>';
  renderStages();renderAction();}

const STAGES=["立案","确认","补证","评估","打包","申诉"];
function stageStatus(){const st=STAGES.map(()=> "");const d=S.last;
  if(!S.caseId){st[0]="now";return st;}
  st[0]="done";const ph=d?d.phase:null;
  st[1]=(d&&d.reason_confirmed)?"done":(ph==="REASON_PROPOSED"?"now":"done");
  if(ph==="REASON_PROPOSED")return st;
  if(ph==="NEED_EVIDENCE"){st[2]="now";return st;}
  st[2]="done";st[3]="done";st[4]=S.packaged?"done":"now";
  if(S.packaged)st[5]=S.appealed?"done":"now";
  return st;}
function renderStages(){const stt=stageStatus();let h="";
  STAGES.forEach((n,i)=>{if(i)h+=`<span class="sep ${stt[i]==='done'||stt[i-1]==='done'?'done':''}"></span>`;
    h+=`<span class="step ${stt[i]}"><span class="b">${stt[i]==='done'?'✓':(i+1)}</span>${n}</span>`;});
  $('steps').innerHTML=h;}

async function openCase(){const {ok,data}=await api("POST","/cases",{description:$('desc').value.trim()});
  if(!ok){$('action').innerHTML='<span class="pill p-crit">建案失败：描述不能为空</span>';return;}
  S.caseId=data.case_id;S.packaged=false;S.appealed=false;apply(data);}
async function refreshCase(){if(!S.caseId)return;apply((await api("GET",`/cases/${S.caseId}`)).data);}
async function confirmReason(){const v=$('fix')?$('fix').value:"";apply((await api("POST",`/cases/${S.caseId}/confirm`,v?{reason_code:v}:{})).data);}
async function submitEvidence(code){apply((await api("POST",`/cases/${S.caseId}/evidence`,{evidence_code:code})).data);}
async function finalize(){apply((await api("POST",`/cases/${S.caseId}/finalize`)).data);}
function fillScenario(i){const d=$('desc');if(d)d.value=SCENARIOS[i].desc;
  document.querySelectorAll('.schip').forEach(c=>c.classList.toggle('on',+c.dataset.i===i));}
async function autoRun(){if(!S.caseId)await openCase();let g=0;
  while(S.last&&S.last.phase!=="ASSESSED"&&g++<40){
    if(S.last.phase==="REASON_PROPOSED")await confirmReason();
    else if(S.last.phase==="NEED_EVIDENCE")await submitEvidence(S.last.next_evidence);else break;}}

function apply(d){if(!d||!d.case_id)return;S.last=d;
  $('crumbId').textContent=d.case_id.slice(0,18);
  renderCaseHead(d);renderStages();renderAction();renderTrace(d);
  const ready=d.phase==="ASSESSED";$('verdictCard').style.display=ready?"block":"none";
  if(ready)renderAssess(d);refreshAudit();refreshMetrics();}

function renderCaseHead(d){
  const conf=d.reason_confirmed?'<span class="pill p-good">已确认</span>':'<span class="pill p-warn">待确认</span>';
  const st=PHASE[d.phase]||["—","p-mut",""];
  let h=`<div class="srow">`
    +`<div class="field"><div class="k">案件</div><div class="v mono">${esc(d.case_id.slice(0,18))}</div></div>`
    +`<div class="field"><div class="k">争议原因</div><div class="v">${esc(d.reason_code||"—")} ${conf}</div></div>`;
  if(d.facts&&d.facts.amount)h+=`<div class="field"><div class="k">金额</div><div class="v num">${esc(d.facts.amount)} ${esc(d.facts.currency||"")}</div></div>`;
  if(d.deadline){const dl=d.deadline;let cls='p-mut',lb='充裕';
    if(dl.overdue){cls='p-crit';lb='已逾期';}
    else if(dl.days_remaining<=3){cls='p-crit';lb='紧迫';}
    else if(dl.days_remaining<=7){cls='p-warn';lb='临近';}
    const txt=dl.overdue?'已逾期':`还剩 ${dl.days_remaining} 天`;
    h+=`<div class="field"><div class="k">举证时限</div><div class="v"><span class="num">${txt}</span> <span class="pill ${cls}">${lb}</span></div></div>`;}
  h+=`<div class="field"><div class="k">状态</div><div class="v"><span class="pill ${st[1]}">${st[0]}</span></div></div></div>`;
  $('caseHead').innerHTML=h;}

function renderAction(){const d=S.last;const tag=$('phaseTag');
  if(!S.caseId){if(tag)tag.textContent="Intake";
    const chips=SCENARIOS.map((s,i)=>`<button class="schip${i===0?' on':''}" data-i="${i}" onclick="fillScenario(${i})">${esc(s.label)}</button>`).join("");
    $('action').innerHTML=`<div class="muted" style="margin-bottom:8px">选择示例场景，或直接描述问题：</div>`
      +`<div class="schips">${chips}</div>`
      +`<textarea id="desc" rows="2">${esc(SCENARIOS[0].desc)}</textarea>`
      +`<div class="actions"><button class="tbtn primary" onclick="openCase()">建案 · 开始</button>`
      +`<button class="tbtn" onclick="autoRun()">⚡ 自动补证跑到评估</button></div>`;return;}
  const ph=d.phase;if(tag)tag.textContent=(PHASE[ph]||["","",""])[2];
  if(ph==="REASON_PROPOSED"){
    $('action').innerHTML=`<div class="muted">${esc(d.question||"")}</div>`
      +`<div class="actions"><select id="fix" style="max-width:280px"></select>`
      +`<button class="tbtn primary" onclick="confirmReason()">确认 / 更正</button></div>`;populateReasons();
  }else if(ph==="NEED_EVIDENCE"){
    $('action').innerHTML=`<div style="font-size:15px;color:var(--ink);font-weight:600">${esc(d.question||"")}</div>`
      +`<div class="actions"><button class="tbtn primary" onclick="submitEvidence('${esc(d.next_evidence)}')">我已提交该证据</button>`
      +`<button class="tbtn" onclick="autoRun()">⚡ 自动补齐剩余</button>`
      +`<button class="tbtn danger" onclick="finalize()">无法提供更多 · 转人工</button></div>`;
  }else if(ph==="ASSESSED"){$('action').innerHTML='<span class="muted">证据已达标，结论见下方「胜诉评估」。</span>';}
  else $('action').innerHTML=`<span class="muted">阶段：${esc(ph)}</span>`;}
async function populateReasons(){const {data}=await api("GET",`/catalog?locale=${S.loc}`);const sel=$('fix');if(!sel)return;
  sel.innerHTML='<option value="">（接受系统判定）</option>'+data.reasons.map(r=>`<option value="${esc(r.code)}">${esc(r.label)}</option>`).join("");}

function renderAssess(d){const a=d.assessment;if(!a)return;
  const pct=Math.round(parseFloat(a.win_likelihood||"0")*100);
  const col=pct>=60?'var(--good)':(pct>=30?'var(--warn)':'var(--crit)');
  const rev=a.requires_human?'<span class="pill p-warn">需人工复核</span>':'<span class="pill p-good">可自动推进</span>';
  const src=a.explanation_source==="MODEL"?"模型":"确定性兜底";
  const bd=a.evidence_breakdown||[];const have=bd.filter(i=>i.present).length;const cov=bd.length?Math.round(have/bd.length*100):0;
  const chk=bd.map(i=>`<div class="ei"><span class="tick ${i.present?'y':'n'}">${i.present?'✓':'•'}</span>`
    +`${esc(i.label)}${i.critical?' <span class="crit-tag">关键</span>':''}</div>`).join("");
  $('verdictBody').innerHTML=`<div class="verdict"><div><div class="vnum" style="color:${col}">${pct}%</div>`
    +`<div class="vcap">预计胜诉概率 · 内核判定</div></div>`
    +`<div class="vmeta"><div class="row"><span class="pill p-acc">判定 · 确定性内核</span>${rev}`
    +`<span class="pill p-mut">责任域 · ${esc(a.responsible_team)}</span>`
    +`<span class="pill p-mut">说明来源 · ${src}</span></div>`
    +`<div class="cov"><div class="track"><i style="width:${cov}%"></i></div><span class="n">证据 ${have}/${bd.length}</span></div></div></div>`
    +`<div class="ev">${chk}</div>`
    +`<div class="note">${esc(a.explanation)} <b>数字由确定性内核判定，模型仅生成说明。</b></div>`
    +`<div class="actions"><button class="tbtn primary" onclick="doPackage()">生成 representment 打包</button>`
    +`<button class="tbtn" onclick="doAppeal(false)">生成申诉草稿</button>`
    +`<button class="tbtn danger" onclick="doAppeal(true)">人工批准并提交</button></div>`
    +`<div id="pkgOut" class="mt"></div><div id="appealOut" class="mt"></div>`;}
async function doPackage(){const {ok,data}=await api("GET",`/cases/${S.caseId}/package?locale=${S.loc}`);
  if(!ok){$('pkgOut').innerHTML='<span class="pill p-warn">案件未就绪</span>';return;}
  S.packaged=true;renderStages();
  $('pkgOut').innerHTML=`<div class="kv"><span class="k">打包</span><span><b style="color:var(--ink)">${esc(data.reason_label)}</b>`
    +` · 规则 ${esc(data.rule_source)} · 完整度 ${esc(data.completeness)} `
    +`${data.ready_to_submit?'<span class="pill p-good">可提交</span>':'<span class="pill p-warn">未就绪</span>'}</span></div>`
    +`<div class="kv"><span class="k">随附</span><span>${data.ordered_evidence.map(e=>esc(e.label)).join("、")||"—"}</span></div>`
    +`<div class="note">${esc(data.cover_note)}</div>`;}
async function doAppeal(approve){const {data}=await api("POST",`/cases/${S.caseId}/appeal`,approve?{human_approved:true,actor_id:"ou_reviewer"}:{});
  if(data.submitted){S.appealed=true;renderStages();}
  const b=data.submitted?'<span class="pill p-good">已提交上游(mock)</span>':`<span class="pill p-warn">未提交 · ${esc(data.blocked_reason||"")}</span>`;
  $('appealOut').innerHTML=`<div class="kv"><span class="k">申诉</span><span>${b}`
    +(data.submission_id?` <code>${esc(data.submission_id)}</code>`:"")+`</span></div>`
    +`<div class="note" style="white-space:pre-wrap">${esc(data.draft)}</div>`;refreshAudit();refreshMetrics();}

function renderTrace(d){const t=d.agent_trace||[];
  $('agentOut').innerHTML=t.length?t.map(x=>`<div class="agent"><span class="atag">${esc(x.agent)}</span>`
    +`<span>${esc(x.action)}${x.source?` <span class="src">(${esc(x.source)})</span>`:""}</span></div>`).join(""):'<div class="empty">—</div>';}
async function refreshAudit(){if(!S.caseId)return;const {ok,data}=await api("GET",`/cases/${S.caseId}/audit`);if(!ok)return;
  $('auditOut').innerHTML=data.events.map(e=>`<li><div class="e">${esc(e.event_type)}${e.detail?` · ${esc(e.detail)}`:""}</div>`
    +`<div class="m">rev ${e.case_revision}</div></li>`).join("")||'<li class="empty">—</li>';}
async function refreshMetrics(){const {data}=await api("GET","/metrics");const c=(data&&data.counts)||{};
  if(!Object.keys(c).length){$('metricsOut').innerHTML='<span class="empty">暂无（运行一个案子后出现）</span>';return;}
  const g=k=>c[k]||0;
  const rhT=g('requires_human_true'),rhF=g('requires_human_false'),rhTot=rhT+rhF,rhPct=rhTot?Math.round(rhT/rhTot*100):0;
  const mdl=g('explanation_source_MODEL'),fb=g('explanation_source_FALLBACK'),sTot=mdl+fb,mdlPct=sTot?Math.round(mdl/sTot*100):0;
  let h="";
  if(rhTot)h+=`<div class="mstat"><div class="ml"><span>需人工复核率</span><b>${rhPct}%</b></div><div class="mbar"><i style="width:${rhPct}%"></i></div></div>`;
  if(sTot)h+=`<div class="mstat"><div class="ml"><span>说明来源 · 模型占比</span><b>模型 ${mdl} · 兜底 ${fb}</b></div><div class="mbar"><i style="width:${mdlPct}%"></i></div></div>`;
  const extra=[['评估次数',g('assessments_total')],['申诉已提交',g('appeal_submitted')],['申诉被阻断',g('appeal_blocked')]];
  h+=`<div class="mnote">`+extra.map(x=>`<span>${x[0]}</span><b>${x[1]}</b>`).join("")+`</div>`;
  $('metricsOut').innerHTML=h;}
async function assessPrevention(){
  const b={three_ds_authenticated:!$('p_no3ds').checked,avs_match:!$('p_noavs').checked,cross_border:$('p_cross').checked,amount:($('p_amount').value||"0")};
  const {ok,data}=await api("POST","/prevention/assess",b);
  if(!ok){$('preventionOut').innerHTML='<span class="pill p-crit">请求无效</span>';return;}
  const cls={LOW:'p-good',MEDIUM:'p-warn',HIGH:'p-crit'}[data.risk_level]||'p-mut';
  const col={LOW:'var(--good)',MEDIUM:'var(--warn)',HIGH:'var(--crit)'}[data.risk_level]||'var(--muted)';
  $('preventionOut').innerHTML=`<div class="verdict"><div><div class="vnum" style="font-size:32px;color:${col}">${esc(data.risk_level)}</div>`
    +`<div class="vcap">拒付风险 · 评分 ${esc(data.risk_score)}</div></div><div class="vmeta">`
    +`<div class="row">${data.factors.map(f=>`<span class="pill ${cls}">${esc(f)}</span>`).join("")||'<span class="muted">无风险因子</span>'}`
    +`${data.recommend_manual_review?'<span class="pill p-warn">建议人工复核</span>':''}</div>`
    +`<div class="note" style="margin:0">建议现在留存：${data.recommended_evidence.map(e=>esc(e.label)).join("、")||"—"}。<br>${esc(data.advice)}</div></div></div>`;
  refreshMetrics();}
async function safetyScan(){const {ok,data}=await api("POST","/safety/scan",{text:$('safeText').value});
  if(!ok){$('safeOut').innerHTML='<span class="pill p-crit">请求无效</span>';return;}
  const p=data.accepted?'<span class="pill p-good">✓ 通过</span>':'<span class="pill p-crit">⛔ 已拦截</span>';
  $('safeOut').innerHTML=`<div class="note" style="margin:0">${p} &nbsp;${esc(data.detail)}</div>`;}

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
