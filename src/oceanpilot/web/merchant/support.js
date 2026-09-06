function renderTrace(d){const t=d.agent_trace||[];
  $('agentOut').innerHTML=t.length?t.map(x=>`<div class="agent"><span class="atag">${esc(AGENT_LABEL[x.agent]||x.agent)}</span>`
    +`<span>${esc(actionLabel(x.action))}${x.source?` <span class="src">· ${esc(SOURCE_LABEL[x.source]||x.source)}</span>`:""}</span></div>`).join(""):'<div class="empty">—</div>';}
async function refreshAudit(){if(!S.caseId)return;const context=caseContext.capture();const ticket=OceanRequest.begin('audit-view');const {ok,data}=await api("GET",`/cases/${context.caseId}/audit`);if(!ok||!caseContext.isCurrent(context)||!OceanRequest.isLatest(ticket))return;
  $('auditOut').innerHTML=data.events.map(e=>`<li><div class="e">${esc(EVENT_LABEL[e.event_type]||e.event_type)}${e.detail?` · ${esc(detailLabel(e.detail))}`:""}</div>`
    +`<div class="m">版本 ${e.case_revision}</div></li>`).join("")||'<li class="empty">—</li>';}
async function refreshMetrics(){const {data}=await api("GET","/metrics");const c=(data&&data.counts)||{};
  if(!Object.keys(c).length){$('metricsOut').innerHTML='<span class="empty">暂无（运行一个案子后出现）</span>';return;}
  const g=k=>c[k]||0;
  const rhT=g('requires_human_true'),rhF=g('requires_human_false'),rhTot=rhT+rhF,rhPct=rhTot?Math.round(rhT/rhTot*100):0;
  const mdl=g('explanation_source_MODEL'),fb=g('explanation_source_FALLBACK'),sTot=mdl+fb,mdlPct=sTot?Math.round(mdl/sTot*100):0;
  let h="";
  if(rhTot)h+=`<div class="mstat"><div class="ml"><span>需人工复核率</span><b>${rhPct}%</b></div><div class="mbar"><i style="width:${rhPct}%"></i></div></div>`;
  if(sTot)h+=`<div class="mstat"><div class="ml"><span>辅助说明使用率</span><b>辅助 ${mdl} · 规则 ${fb}</b></div><div class="mbar"><i style="width:${mdlPct}%"></i></div></div>`;
  const extra=[['评估次数',g('assessments_total')],['申诉已提交',g('appeal_submitted')],['申诉被阻断',g('appeal_blocked')]];
  h+=`<div class="mnote">`+extra.map(x=>`<span>${x[0]}</span><b>${x[1]}</b>`).join("")+`</div>`;
  $('metricsOut').innerHTML=h;}
async function assessPrevention(){
  const b={three_ds_authenticated:!$('p_no3ds').checked,avs_match:!$('p_noavs').checked,cross_border:$('p_cross').checked,amount:($('p_amount').value||"0")};
  const {ok,data}=await api("POST","/prevention/assess",b);
  if(!ok){$('preventionOut').innerHTML='<span class="pill p-crit">请求无效</span>';return;}
  const cls={LOW:'p-good',MEDIUM:'p-warn',HIGH:'p-crit'}[data.risk_level]||'p-mut';
  const col={LOW:'var(--good)',MEDIUM:'var(--warn)',HIGH:'var(--crit)'}[data.risk_level]||'var(--muted)';
  $('preventionOut').innerHTML=`<div class="verdict"><div><div class="vnum" style="font-size:32px;color:${col}">${esc(RISK_LABEL[data.risk_level]||data.risk_level)}</div>`
    +`<div class="vcap">拒付风险 · 评分 ${esc(data.risk_score)}</div></div><div class="vmeta">`
    +`<div class="row">${data.factors.map(f=>`<span class="pill ${cls}">${esc(FACTOR_LABEL[f]||f)}</span>`).join("")||'<span class="muted">未发现明显风险因子</span>'}`
    +`${data.recommend_manual_review?'<span class="pill p-warn">建议人工复核</span>':''}</div>`
    +`<div class="note" style="margin:0">建议现在留存：${data.recommended_evidence.map(e=>esc(e.label)).join("、")||"—"}。`
    +(cleanCopy(data.advice)?`<br>${esc(cleanCopy(data.advice))}`:"")+`</div></div></div>`;
  refreshMetrics();}
async function safetyScan(){const {ok,data}=await api("POST","/safety/scan",{text:$('safeText').value});
  if(!ok){$('safeOut').innerHTML='<span class="pill p-crit">请求无效</span>';return;}
  const p=data.accepted?'<span class="pill p-good">✓ 通过</span>':'<span class="pill p-crit">⛔ 已拦截</span>';
  $('safeOut').innerHTML=`<div class="note" style="margin:0">${p} &nbsp;${esc(data.detail)}</div>`;}
