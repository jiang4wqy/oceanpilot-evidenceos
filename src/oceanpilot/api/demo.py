"""Self-contained single-page demo UI for the chargeback cluster.

Served by FastAPI at ``GET /demo`` (kept out of the OpenAPI schema). Pure inline
HTML + vanilla JS that drives the existing JSON API — no build step, no external
assets, works offline. Purpose: let a reviewer click through the whole loop and
see the safety story (kernel decides / model explains / human confirms / never
executes) in one screen.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_DEMO_HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>OceanPilot · 跨境拒付申诉集群 演示</title>
<style>
  :root { --bg:#0f172a; --card:#1e293b; --line:#334155; --fg:#e2e8f0; --mut:#94a3b8;
          --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; --acc:#38bdf8; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font-family: system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
         line-height:1.5; }
  header { padding:16px 22px; border-bottom:1px solid var(--line); }
  header h1 { margin:0; font-size:18px; }
  .safety { margin-top:6px; color:var(--mut); font-size:13px; }
  main { display:grid; grid-template-columns: 1fr 1fr; gap:16px; padding:16px 22px; max-width:1200px; }
  @media (max-width: 860px){ main{ grid-template-columns:1fr; } }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }
  .card h2 { margin:0 0 10px; font-size:14px; color:var(--acc); letter-spacing:.03em; }
  button { background:#0ea5e9; color:#04283a; border:0; border-radius:7px; padding:7px 12px;
           font-weight:600; cursor:pointer; font-size:13px; }
  button.ghost { background:#334155; color:var(--fg); }
  button.danger { background:#7f1d1d; color:#fecaca; }
  button:disabled { opacity:.45; cursor:not-allowed; }
  textarea, select, input { width:100%; background:#0b1220; color:var(--fg); border:1px solid var(--line);
           border-radius:7px; padding:8px; font-size:13px; }
  .row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:8px; }
  .muted { color:var(--mut); font-size:12px; }
  .badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:600; }
  .b-ok{ background:#052e16; color:var(--ok); } .b-warn{ background:#3b2807; color:var(--warn); }
  .b-bad{ background:#3f1212; color:var(--bad); } .b-mut{ background:#1f2937; color:var(--mut); }
  .kv { font-size:13px; margin:3px 0; } .kv b{ color:var(--mut); font-weight:600; }
  ul { margin:6px 0; padding-left:18px; } li { font-size:13px; margin:2px 0; }
  .trace li { list-style:none; } .trace { padding-left:0; }
  code { background:#0b1220; padding:1px 5px; border-radius:4px; font-size:12px; }
  .full { grid-column: 1 / -1; }
</style>
</head>
<body>
<header>
  <h1>OceanPilot · 跨境拒付申诉多智能体集群 <span class="badge b-mut">演示 / 合成数据</span></h1>
  <div class="safety">确定性内核决策 · 智能体解释/建议 · 人工确认 · <b>绝不执行支付/退款/风控/提交动作</b></div>
</header>
<main>
  <section class="card">
    <h2>① 预防 · 交易前风险</h2>
    <div class="row">
      <label class="muted"><input type="checkbox" id="p_no3ds"> 无 3DS</label>
      <label class="muted"><input type="checkbox" id="p_noavs"> AVS 不符</label>
      <label class="muted"><input type="checkbox" id="p_cross"> 跨境</label>
      <input id="p_amount" placeholder="金额，如 4200" style="width:120px" />
      <button onclick="assessPrevention()">评估风险</button>
    </div>
    <div id="preventionOut" class="muted" style="margin-top:8px">—</div>
  </section>

  <section class="card">
    <h2>② 建案 · 描述问题</h2>
    <textarea id="desc" rows="2">客户下单后一直没收到货，现在要求拒付。</textarea>
    <div class="row"><button onclick="openCase()">建案</button>
      <span class="muted">语言</span>
      <select id="locale" style="width:90px" onchange="if(caseId) refreshPackage()">
        <option value="zh">中文</option><option value="en">English</option>
      </select>
    </div>
    <div id="caseOut" style="margin-top:8px" class="muted">—</div>
  </section>

  <section class="card">
    <h2>③ 当前步骤 · 补证 / 评估</h2>
    <div id="stepOut" class="muted">先建案。</div>
  </section>

  <section class="card">
    <h2>④ 智能体决策轨迹</h2>
    <ul id="traceOut" class="trace"><li class="muted">—</li></ul>
  </section>

  <section class="card">
    <h2>⑤ 打包 · representment</h2>
    <div class="row"><button id="pkgBtn" onclick="refreshPackage()" disabled>生成打包</button></div>
    <div id="pkgOut" class="muted" style="margin-top:8px">—</div>
  </section>

  <section class="card">
    <h2>⑥ 申诉 · 人工确认硬闸门</h2>
    <div class="row">
      <button id="draftBtn" onclick="appeal(false)" disabled>生成草稿（不提交）</button>
      <button id="submitBtn" class="danger" onclick="appeal(true)" disabled>人工批准并提交</button>
    </div>
    <div id="appealOut" class="muted" style="margin-top:8px">—</div>
  </section>

  <section class="card full">
    <h2>⑦ 审计轨迹 · 指标</h2>
    <div class="row">
      <button class="ghost" onclick="refreshAudit()" disabled id="auditBtn">刷新审计</button>
      <button class="ghost" onclick="refreshMetrics()">刷新指标</button>
    </div>
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:8px">
      <ul id="auditOut"><li class="muted">—</li></ul>
      <div id="metricsOut" class="muted">—</div>
    </div>
  </section>
</main>
<script>
const BASE = "/api/v1/chargeback";
let caseId = null;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

async function api(method, path, body) {
  const opt = { method, headers: {"Content-Type":"application/json"} };
  if (body !== undefined) opt.body = JSON.stringify(body);
  const r = await fetch(BASE + path, opt);
  const data = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, data };
}
function locale(){ return $("locale").value; }

async function assessPrevention(){
  const body = {
    three_ds_authenticated: !$("p_no3ds").checked,
    avs_match: !$("p_noavs").checked,
    cross_border: $("p_cross").checked,
    amount: ($("p_amount").value || "0"),
  };
  const { ok, data } = await api("POST", "/prevention/assess", body);
  if(!ok){ $("preventionOut").innerHTML = "请求无效"; return; }
  const lvl = {LOW:"b-ok",MEDIUM:"b-warn",HIGH:"b-bad"}[data.risk_level] || "b-mut";
  $("preventionOut").innerHTML =
    `<span class="badge ${lvl}">风险 ${esc(data.risk_level)} · ${esc(data.risk_score)}</span>`
    + `<div class="kv"><b>因子</b> ${data.factors.map(esc).join("、")||"—"}</div>`
    + `<div class="kv"><b>建议留证</b> ${data.recommended_evidence.map(e=>esc(e.label)).join("、")||"—"}</div>`
    + `<div class="kv"><b>建议人工复核</b> ${data.recommend_manual_review}</div>`
    + `<div class="muted">${esc(data.advice)}</div>`;
}

async function openCase(){
  const { ok, data } = await api("POST", "/cases", { description: $("desc").value });
  if(!ok){ $("caseOut").innerHTML = "建案失败（描述不能为空）"; return; }
  caseId = data.case_id;
  render(data);
}
async function confirmReason(correction){
  const body = correction ? { reason_code: correction } : {};
  render((await api("POST", `/cases/${caseId}/confirm`, body)).data);
}
async function submitEvidence(code){
  render((await api("POST", `/cases/${caseId}/evidence`, { evidence_code: code })).data);
}
async function finalize(){
  render((await api("POST", `/cases/${caseId}/finalize`)).data);
}

function render(d){
  if(!d || !d.case_id) return;
  // case summary
  const conf = d.reason_confirmed ? '<span class="badge b-ok">已确认</span>' : '<span class="badge b-warn">待确认</span>';
  let html = `<div class="kv"><b>案件</b> <code>${esc(d.case_id)}</code></div>`
    + `<div class="kv"><b>原因</b> ${esc(d.reason_code||"—")} ${conf}</div>`;
  if(d.deadline) html += `<div class="kv"><b>举证时限</b> 还剩 ${d.deadline.days_remaining} 天`
    + (d.deadline.overdue?' <span class="badge b-bad">逾期</span>':'') + `</div>`;
  if(d.facts && d.facts.summary) html += `<div class="kv"><b>识别要点</b> ${esc(d.facts.summary)}</div>`;
  $("caseOut").innerHTML = html;

  // current step
  let step = `<div class="kv"><b>阶段</b> ${esc(d.phase)}</div>`;
  if(d.phase === "REASON_PROPOSED"){
    step += `<div class="muted">${esc(d.question||"")}</div>`
      + `<div class="row"><select id="fix"></select>`
      + `<button onclick="confirmReason(document.getElementById('fix').value)">确认/更正原因</button></div>`;
    $("stepOut").innerHTML = step; populateReasons();
  } else if(d.phase === "NEED_EVIDENCE"){
    step += `<div class="muted">${esc(d.question||"")}</div>`
      + `<div class="row"><button onclick="submitEvidence('${esc(d.next_evidence)}')">我已提交该证据</button>`
      + `<button class="danger" onclick="finalize()">无法提供更多 · 转人工</button></div>`;
    $("stepOut").innerHTML = step;
  } else if(d.phase === "ASSESSED" && d.assessment){
    const a = d.assessment;
    const rev = a.requires_human ? '<span class="badge b-warn">需人工复核</span>' : '<span class="badge b-ok">可自动推进</span>';
    const src = a.explanation_source === "MODEL" ? "模型" : "确定性兜底";
    const chk = a.evidence_breakdown.map(i =>
      `<li>${i.present?"✅":"❌"}${i.critical?"⭐":""} ${esc(i.label)} <span class="muted">(权重 ${i.weight})</span></li>`).join("");
    step += `<div class="kv"><b>胜诉可能性</b> <span class="badge b-ok">${esc(a.win_likelihood)}</span> ${rev}`
      + ` <span class="muted">责任域 ${esc(a.responsible_team)}</span></div>`
      + `<ul>${chk}</ul>`
      + `<div class="muted">说明（来源：${src}；数字由内核判定）：${esc(a.explanation)}</div>`;
    $("stepOut").innerHTML = step;
  } else { $("stepOut").innerHTML = step; }

  // agent trace
  $("traceOut").innerHTML = (d.agent_trace && d.agent_trace.length)
    ? d.agent_trace.map(t => `<li><span class="badge b-mut">${esc(t.agent)}</span> ${esc(t.action)}`
        + (t.source?` <span class="muted">(${esc(t.source)})</span>`:"") + `</li>`).join("")
    : '<li class="muted">—</li>';

  const ready = d.phase === "ASSESSED";
  ["pkgBtn","draftBtn","submitBtn","auditBtn"].forEach(id => $(id).disabled = !caseId);
  if(ready) refreshPackage();
  refreshAudit();
}

async function populateReasons(){
  const { data } = await api("GET", `/catalog?locale=${locale()}`);
  const sel = $("fix"); if(!sel) return;
  sel.innerHTML = '<option value="">（接受系统判定）</option>'
    + data.reasons.map(r => `<option value="${esc(r.code)}">${esc(r.label)}</option>`).join("");
}
async function refreshPackage(){
  if(!caseId) return;
  const { ok, data } = await api("GET", `/cases/${caseId}/package?locale=${locale()}`);
  if(!ok){ $("pkgOut").innerHTML = "案件未就绪"; return; }
  $("pkgOut").innerHTML = `<div class="kv"><b>${esc(data.reason_label)}</b> · 规则 ${esc(data.rule_source)}`
    + ` · 完整度 ${esc(data.completeness)} · ${data.ready_to_submit?'<span class="badge b-ok">可提交</span>':'<span class="badge b-warn">未就绪</span>'}</div>`
    + `<div class="kv"><b>随附</b> ${data.ordered_evidence.map(e=>esc(e.label)).join("、")||"—"}</div>`
    + `<div class="muted">${esc(data.cover_note)}</div>`;
}
async function appeal(approve){
  if(!caseId) return;
  const body = approve ? { human_approved: true, actor_id: "ou_reviewer" } : {};
  const { data } = await api("POST", `/cases/${caseId}/appeal`, body);
  const badge = data.submitted ? '<span class="badge b-ok">已提交(mock)</span>'
    : `<span class="badge b-warn">未提交 · ${esc(data.blocked_reason||"")}</span>`;
  $("appealOut").innerHTML = badge
    + (data.submission_id?` <code>${esc(data.submission_id)}</code>`:"")
    + `<div class="muted" style="white-space:pre-wrap">${esc(data.draft)}</div>`;
  refreshAudit(); refreshMetrics();
}
async function refreshAudit(){
  if(!caseId) return;
  const { ok, data } = await api("GET", `/cases/${caseId}/audit`);
  if(!ok) return;
  $("auditOut").innerHTML = data.events.map(e =>
    `<li>#${e.seq} <b>${esc(e.event_type)}</b>${e.detail?` <span class="muted">(${esc(e.detail)})</span>`:""} @rev${e.case_revision}</li>`
  ).join("") || '<li class="muted">—</li>';
}
async function refreshMetrics(){
  const { data } = await api("GET", "/metrics");
  const c = data.counts || {};
  const keys = Object.keys(c);
  $("metricsOut").innerHTML = keys.length
    ? keys.map(k => `<div class="kv"><b>${esc(k)}</b> ${c[k]}</div>`).join("")
    : '<span class="muted">暂无</span>';
}
</script>
</body>
</html>
"""


@router.get("/demo", include_in_schema=False, response_class=HTMLResponse)
def demo_page() -> HTMLResponse:
    return HTMLResponse(_DEMO_HTML)
