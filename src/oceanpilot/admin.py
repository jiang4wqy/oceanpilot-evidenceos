"""Separate management-console application, intended for port 8003."""

import json
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

_ADMIN_HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<script>if(location.hash.includes("figmacapture=")){const s=document.createElement("script");s.src="https://mcp.figma.com/mcp/html-to-design/capture.js";s.async=true;document.head.appendChild(s)}</script>
<title>Oceanpayment · 维护中心</title>
<style>
:root{--canvas:#f5f8f7;--surface:#fff;--sunken:#edf4f2;--border:#dde7e4;--border2:#c8d8d4;
--ink:#172321;--body:#40504d;--muted:#63716e;--faint:#8a9995;--accent:#087a70;--accentHover:#06685f;--accentSoft:#dff3ef;--deep:#123b3a;
--good:#178a52;--goodBg:#e5f4ec;--warn:#c88722;--warnBg:#fff4df;--crit:#c84646;--critBg:#fbeaea;--info:#3676a8;--shadow:0 1px 2px rgba(18,59,58,.035),0 8px 20px -16px rgba(18,59,58,.22);
--sans:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--body);font-family:var(--sans);font-size:14px;line-height:1.55}
button,select{font:inherit}.app{display:grid;grid-template-columns:220px minmax(0,1fr);min-height:100vh}
.side{background:#fff;border-right:1px solid var(--border);height:100vh;position:sticky;top:0}
.brand{padding:24px 22px 18px;border-bottom:1px solid var(--border)}.brand strong{display:block;color:var(--accent);font-size:20px;letter-spacing:-.5px}
.brand span{display:block;margin-top:7px;color:var(--muted);font-size:11px;letter-spacing:.08em}.navlabel{padding:22px 20px 7px;color:var(--faint);font-size:10px;letter-spacing:.12em}
.nav{padding:4px 10px}.nav button{display:block;width:100%;border:0;background:transparent;text-align:left;color:var(--muted);padding:11px 12px;border-radius:8px;cursor:pointer}
.nav button:hover{background:#f6f8f6;color:var(--ink)}.nav button.on{background:var(--accentSoft);color:var(--accent);font-weight:700;border-left:3px solid var(--accent)}
.main{min-width:0}.top{height:64px;background:#fff;border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 32px;gap:14px;position:sticky;top:0;z-index:4}
.crumb{color:var(--muted);font-size:13px}.crumb b{color:var(--ink)}.grow{flex:1}.source{font-size:12px;color:var(--muted)}
.refresh{border:1px solid var(--accent);background:var(--accent);color:#fff;border-radius:8px;padding:8px 13px;cursor:pointer;font-weight:650}.refresh:hover{background:var(--accentHover)}
.refresh:disabled{opacity:.55;cursor:wait}.content{max-width:1440px;margin:auto;padding:28px 32px 42px}.view{display:none}.view.on{display:block}
.pagehead{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;padding-bottom:18px;border-bottom:1px solid var(--border);margin-bottom:20px}
.pagehead h1{margin:0 0 4px;color:var(--ink);font-size:25px;letter-spacing:-.02em}.pagehead p{margin:0;color:var(--muted)}
.updated{font-size:12px;color:var(--muted);white-space:nowrap}.banner{display:none;margin-bottom:16px;padding:12px 14px;border-radius:8px;border:1px solid #e2a2a2;background:var(--critBg);color:var(--crit);font-weight:650}
.banner.on{display:block}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:18px;background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden}.card{background:#fff;border:1px solid var(--border);border-radius:10px;box-shadow:var(--shadow)}
.metric{padding:15px 17px;border:0;border-right:1px solid var(--border);border-radius:0;box-shadow:none}.metric:last-child{border-right:0}.metric .label{font-size:12px;color:var(--muted)}.metric .value{margin-top:7px;color:var(--ink);font-size:23px;font-weight:750;font-variant-numeric:tabular-nums}
.metric .hint{margin-top:3px;font-size:11.5px;color:var(--faint)}.grid2{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(320px,.85fr);gap:18px}
.hd{padding:13px 18px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}.hd h2{font-size:14px;margin:0;color:var(--ink)}
.bd{padding:16px 18px}.badge{display:inline-flex;padding:3px 8px;border-radius:5px;font-size:11px;font-weight:700;white-space:nowrap}.healthy{color:var(--good);background:var(--goodBg)}.info{color:var(--info);background:#e8f0f6}
.watch,.warning{color:var(--warn);background:var(--warnBg)}.degraded,.critical{color:var(--crit);background:var(--critBg)}.notcalled{color:var(--muted);background:var(--sunken)}
.signal{padding:13px 0;border-bottom:1px solid var(--border)}.signal:last-child{border-bottom:0}.signaltop{display:flex;align-items:center;gap:9px}.signal strong{color:var(--ink)}
.signal p{margin:6px 0 0;color:var(--body);font-size:12.5px}.signal .advice{color:var(--muted)}.endpointmini{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--border)}
.endpointmini:last-child{border-bottom:0}.endpointmini .name{flex:1;color:var(--ink);font-weight:650}.endpointmini .meta{font-family:var(--mono);font-size:11px;color:var(--muted)}
.toolbar{display:flex;justify-content:flex-end;margin-bottom:12px}.toolbar select{width:220px;border:1px solid var(--border2);border-radius:8px;background:#fff;padding:8px 10px;color:var(--ink)}
.tablewrap{overflow:auto}.table{width:100%;border-collapse:collapse;min-width:920px}.table th{text-align:left;padding:11px 14px;background:var(--sunken);color:var(--muted);font-size:11px;font-weight:650;border-bottom:1px solid var(--border)}
.table td{padding:12px 14px;border-bottom:1px solid var(--border);font-size:12.5px}.table tr:last-child td{border-bottom:0}.route{font-family:var(--mono);font-size:11.5px;color:var(--body)}
.method{font-family:var(--mono);font-size:11px;color:var(--accent);font-weight:750}.num{font-variant-numeric:tabular-nums}.business{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.businessitem{border:1px solid var(--border);border-radius:8px;padding:13px 14px}.businessitem span{display:block;color:var(--muted);font-size:12px}.businessitem strong{display:block;margin-top:5px;color:var(--ink);font-size:21px}
.methodnote{margin-top:14px;padding:12px 14px;background:var(--sunken);border-radius:8px;color:var(--muted);font-size:12px}.empty{color:var(--faint);font-size:12.5px}.scopegrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.scopeitem{border:1px solid var(--border);border-radius:8px;padding:14px}.scopeitem strong{display:block;color:var(--ink);font-size:13px}.scopeitem p{margin:5px 0 0;color:var(--muted);font-size:12px}.env{font-size:11px;color:var(--accent);background:var(--accentSoft);border:1px solid #b8ddd6;border-radius:5px;padding:4px 8px;font-weight:700}
@media(max-width:1100px){.cards{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}}
@media(max-width:760px){.app{grid-template-columns:1fr}.side{display:none}.top{padding:0 16px}.source{display:none}.content{padding:20px 14px 32px}.cards,.business{grid-template-columns:1fr}.pagehead{align-items:flex-start}.updated{display:none}}
</style>
</head>
<body>
<div class="app">
<aside class="side"><div class="brand"><strong>Oceanpayment</strong><span>运行维护中心</span></div><div class="navlabel">监控中心</div>
<nav class="nav"><button class="on" data-view="overview">运行总览</button><button data-view="api">API 监控</button><button data-view="prediction">故障预判</button><button data-view="business">业务指标</button><button data-view="audit">审计与配置</button></nav></aside>
<main class="main"><header class="top"><div class="crumb"><b>运行维护</b> / <span id="crumb">运行总览</span></div><div class="grow"></div><span class="env">Sandbox</span><div class="source">监控客户服务 <span id="sourceHost"></span></div><button class="refresh" id="refresh" onclick="loadOverview()">立即刷新</button></header>
<div class="content"><div class="banner" id="offline">客户服务暂时不可达。请确认 8002 端口已启动，再检查网络和服务日志。</div>

<section class="view on" id="view-overview"><div class="pagehead"><div><h1>运行总览</h1><p>集中查看服务、数据库、API 与业务流程的当前状态。</p></div><div class="updated" id="updatedOverview">等待首次刷新</div></div>
<div class="cards"><div class="card metric"><div class="label">客户服务</div><div class="value" id="serviceValue">—</div><div class="hint">应用与数据库综合状态</div></div>
<div class="card metric"><div class="label">近 15 分钟请求</div><div class="value" id="requestValue">0</div><div class="hint">不记录请求正文和敏感数据</div></div>
<div class="card metric"><div class="label">P95 延迟</div><div class="value" id="latencyValue">0 ms</div><div class="hint">风险阈值 800 ms</div></div>
<div class="card metric"><div class="label">5xx 错误</div><div class="value" id="errorValue">0</div><div class="hint">出现即进入严重预警</div></div></div>
<div class="grid2"><div class="card"><div class="hd"><h2>故障风险预判</h2><span class="badge notcalled">阈值判断</span></div><div class="bd" id="overviewSignals"><span class="empty">等待数据</span></div></div>
<div class="card"><div class="hd"><h2>关键接口</h2><span class="badge notcalled">近 15 分钟</span></div><div class="bd" id="keyEndpoints"><span class="empty">等待数据</span></div></div></div></section>

<section class="view" id="view-api"><div class="pagehead"><div><h1>API 监控</h1><p>按接口查看调用量、错误率和延迟，未调用接口单独标记。</p></div><div class="updated" id="updatedApi">等待首次刷新</div></div>
<div class="toolbar"><select id="apiGroup" onchange="renderEndpoints()"><option value="ALL">全部接口分组</option></select></div>
<div class="card tablewrap"><table class="table"><thead><tr><th>接口</th><th>状态</th><th>调用量</th><th>4xx</th><th>5xx</th><th>错误率</th><th>平均延迟</th><th>P95</th><th>最近状态</th></tr></thead><tbody id="endpointRows"></tbody></table></div></section>

<section class="view" id="view-prediction"><div class="pagehead"><div><h1>故障预判</h1><p>在明显报错前发现延迟、错误率和业务积压的上升信号。</p></div><div class="updated" id="updatedPrediction">等待首次刷新</div></div>
<div class="card"><div class="hd"><h2>当前预警</h2><span class="badge notcalled">可解释规则</span></div><div class="bd" id="allSignals"><span class="empty">等待数据</span></div></div><div class="methodnote" id="predictionNote">预判只使用确定性阈值，不是故障概率。</div></section>

<section class="view" id="view-business"><div class="pagehead"><div><h1>业务指标</h1><p>观察人工复核、申诉阻断和交易风险等流程指标。</p></div><div class="updated" id="updatedBusiness">等待首次刷新</div></div>
<div class="card"><div class="hd"><h2>拒付处理指标</h2><span class="badge notcalled">当前进程</span></div><div class="bd"><div class="business" id="businessMetrics"><span class="empty">尚无业务数据</span></div></div></div></section>

<section class="view" id="view-audit"><div class="pagehead"><div><h1>审计与配置</h1><p>确认监控采集边界、运行参数和外部连接状态。</p></div><div class="updated" id="updatedAudit">只读</div></div>
<div class="card"><div class="hd"><h2>监控边界</h2><span class="badge healthy">已启用</span></div><div class="bd"><div class="scopegrid"><div class="scopeitem"><strong>请求遥测</strong><p>仅记录规范化路由、方法、状态码和耗时；不记录请求正文、卡号或原始 URL。</p></div><div class="scopeitem"><strong>滚动窗口</strong><p>近 15 分钟进程内统计；服务重启后自动清空，不声明长期历史。</p></div><div class="scopeitem"><strong>故障预判</strong><p>使用可解释阈值识别 5xx、错误率、P95 延迟及业务积压，不输出虚构概率。</p></div><div class="scopeitem"><strong>外部连接</strong><p>Oceanpayment 真实 API、生产数据和上游申诉接口尚未接入；当前为本地合成链路。</p></div></div></div></div></section>
</div></main></div>
<script>
const CLIENT_BASE=__CLIENT_BASE__;
let DATA=null;
const $=id=>document.getElementById(id);
const esc=value=>String(value==null?"":value).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const STATUS={HEALTHY:["正常","healthy"],WATCH:["关注","watch"],DEGRADED:["异常","degraded"],NOT_CALLED:["未调用","notcalled"]};
const SEVERITY={INFO:["提示","info"],WARNING:["预警","warning"],CRITICAL:["严重","critical"]};
const METRIC_LABEL={assessments_total:"评估次数",requires_human_true:"需人工复核",requires_human_false:"无需人工复核",appeal_submitted:"申诉已提交",appeal_blocked:"申诉被阻断",prevention_risk_LOW:"低风险交易",prevention_risk_MEDIUM:"中风险交易",prevention_risk_HIGH:"高风险交易",explanation_source_MODEL:"辅助说明",explanation_source_FALLBACK:"规则说明"};
function badge(value,map=STATUS){const item=map[value]||[value,"notcalled"];return `<span class="badge ${item[1]}">${esc(item[0])}</span>`;}
document.querySelectorAll('.nav button').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('.nav button').forEach(x=>x.classList.remove('on'));button.classList.add('on');document.querySelectorAll('.view').forEach(x=>x.classList.remove('on'));$('view-'+button.dataset.view).classList.add('on');$('crumb').textContent=button.textContent;}));
function signalHtml(item){return `<div class="signal"><div class="signaltop">${badge(item.severity,SEVERITY)}<strong>${esc(item.title)}</strong></div><p>${esc(item.evidence)}</p><p class="advice">建议：${esc(item.recommendation)}</p></div>`;}
function endpointHtml(item){return `<div class="endpointmini"><div><div class="name">${esc(item.name)}</div><div class="meta">${esc(item.method)} ${esc(item.route)}</div></div><div class="grow"></div>${badge(item.status)}</div>`;}
function renderOverview(){const d=DATA;if(!d)return;const status=STATUS[d.service_status.overall]||STATUS.NOT_CALLED;$('serviceValue').innerHTML=badge(d.service_status.overall);$('requestValue').textContent=d.request_summary.total;$('latencyValue').textContent=Math.round(d.request_summary.p95_latency_ms)+' ms';$('errorValue').textContent=d.request_summary.server_errors;$('overviewSignals').innerHTML=d.predictions.slice(0,3).map(signalHtml).join('');$('keyEndpoints').innerHTML=d.endpoints.slice(0,6).map(endpointHtml).join('');void status;}
function renderEndpoints(){if(!DATA)return;const selected=$('apiGroup').value;const rows=DATA.endpoints.filter(item=>selected==='ALL'||item.group===selected);$('endpointRows').innerHTML=rows.map(item=>`<tr><td><strong>${esc(item.name)}</strong><div class="route"><span class="method">${esc(item.method)}</span> ${esc(item.route)}</div></td><td>${badge(item.status)}</td><td class="num">${item.total}</td><td class="num">${item.client_errors}</td><td class="num">${item.server_errors}</td><td class="num">${(item.error_rate*100).toFixed(1)}%</td><td class="num">${Math.round(item.average_latency_ms)} ms</td><td class="num">${Math.round(item.p95_latency_ms)} ms</td><td class="num">${item.last_status||'—'}</td></tr>`).join('');}
function renderPredictions(){if(!DATA)return;$('allSignals').innerHTML=DATA.predictions.map(signalHtml).join('');$('predictionNote').textContent=DATA.prediction_disclaimer;}
function renderBusiness(){if(!DATA)return;const entries=Object.entries(DATA.business_counts);$('businessMetrics').innerHTML=entries.length?entries.map(([key,value])=>`<div class="businessitem"><span>${esc(METRIC_LABEL[key]||key)}</span><strong>${value}</strong></div>`).join(''):'<span class="empty">尚无业务数据；客户端产生评估或申诉后会自动出现。</span>';}
function configureGroups(){const select=$('apiGroup');if(select.options.length>1)return;[...new Set(DATA.endpoints.map(item=>item.group))].forEach(group=>{const option=document.createElement('option');option.value=group;option.textContent=group;select.appendChild(option);});}
async function loadOverview(){const button=$('refresh');button.disabled=true;$('offline').classList.remove('on');try{const response=await fetch(CLIENT_BASE+'/api/v1/admin/overview',{headers:{Accept:'application/json'}});if(!response.ok)throw new Error('status');DATA=await response.json();configureGroups();renderOverview();renderEndpoints();renderPredictions();renderBusiness();const stamp=new Date(DATA.generated_at).toLocaleTimeString('zh-CN',{hour12:false});['updatedOverview','updatedApi','updatedPrediction','updatedBusiness'].forEach(id=>$(id).textContent='更新于 '+stamp);$('sourceHost').textContent=new URL(CLIENT_BASE).host;}catch(error){$('offline').classList.add('on');$('serviceValue').innerHTML=badge('DEGRADED');void error;}finally{button.disabled=false;}}
loadOverview();setInterval(loadOverview,5000);
</script>
</body>
</html>"""


def create_admin_app(client_base_url: str | None = None) -> FastAPI:
    base_url = client_base_url or os.getenv("OCEANPILOT_CLIENT_BASE_URL", "http://127.0.0.1:8002")
    page = _ADMIN_HTML.replace("__CLIENT_BASE__", json.dumps(base_url.rstrip("/")))
    application = FastAPI(
        title="Oceanpayment Operations Console",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @application.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/admin")

    @application.get("/admin", include_in_schema=False, response_class=HTMLResponse)
    def admin_page() -> HTMLResponse:
        return HTMLResponse(page)

    @application.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok", "client_base_url": base_url.rstrip("/")}

    return application
