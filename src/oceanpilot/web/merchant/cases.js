function returnToCaseCenter(){showView('overview');}
function invalidateDerivedViews(){S.packaged=false;S.appealed=false;['pkgOut','appealOut','ruleReferenceOut','diagnosisRuleReferenceOut'].forEach(id=>{const node=$(id);if(node)node.innerHTML='';});}
const STATUS_VIEW={REASON_PROPOSED:['待确认原因','p-warn'],NEED_EVIDENCE:['待补资料','p-acc'],ASSESSED:['评估完成','p-good'],NEEDS_INTAKE:['待识别','p-mut']};
function showView(v){
  if(v==='transactions')v='overview';
  S.currentView=v;clearGlobalSearchStatus();
  const navView=(v==='diagnosis'||v==='flow')?'overview':v;
  document.querySelectorAll('.nav button,.mobile-nav button').forEach(x=>{const active=x.dataset.v===navView;x.classList.toggle('on',active);if(active)x.setAttribute('aria-current','page');else x.removeAttribute('aria-current');});
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('on'));
  const view=$('v-'+v);if(view)view.classList.add('on');
  if(view){view.setAttribute('tabindex','-1');view.focus({preventScroll:true});}
  const navCrumb={hub:["OceanPilot","AI 运营中枢"],overview:["商户工作台","案件中心"],diagnosis:["案件中心",S.selectedCase?S.selectedCase.case_id.slice(0,18):"案件诊断"],create:["案件中心","新建案件"],flow:["案件中心",S.caseId?S.caseId.slice(0,18):"案件详情"],prev:["交易风险","实时评估"],rules:["规则知识",S.currentRuleId||"规则目录"],safe:["规则与运营","安全边界"]}[v]||["OceanPilot",v];
  $('crumbRoot').textContent=navCrumb[0];$('crumbId').textContent=navCrumb[1];
  const placeholders={rules:"搜索规则原因码、名称或来源"};
  $('globalSearch').placeholder=placeholders[navView]||"搜索案件号或争议原因";
  if(v==='overview')loadCases();
  if(v==='rules')loadRules();
}
function navigateTo(view){if(view==='create'){openCreate();return;}showView(view);}
document.querySelectorAll('.nav button,.mobile-nav button').forEach(button=>button.addEventListener('click',()=>navigateTo(button.dataset.v)));
async function loadCases(){const ticket=OceanRequest.begin('case-list');const result=await api("GET","/cases");
  if(!OceanRequest.isLatest(ticket))return;
  if(!result.ok||!Array.isArray(result.data)){S.cases=[];$('transactionCount').textContent='读取失败';$('transactionRows').innerHTML='<tr><td colspan="5" class="empty">案件库暂时无法读取，请稍后刷新。</td></tr>';return;}
  S.cases=result.data;renderTransactions();}
function renderTransactions(){const query=($('tableSearch').value||'').toLowerCase();const status=$('statusFilter').value;
  const rows=S.cases.filter(c=>(status==='ALL'||c.phase===status)&&[c.case_id,c.reason_code,REASON_LABEL[c.reason_code],tr(REASON_LABEL[c.reason_code])].join(' ').toLowerCase().includes(query));
  const synced=new Date().toLocaleTimeString(S.loc==='en'?'en-US':'zh-CN',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});$('transactionCount').textContent=`${rows.length} 件有效实体 · 更新于 ${synced}`;
  $('transactionRows').innerHTML=rows.map(c=>{const s=STATUS_VIEW[c.phase]||['未知','p-mut'];const missing=(c.missing_labels||[]).length;return `<tr onclick="openStoredCase('${esc(c.case_id)}')"><td class="primary-id">${esc(c.case_id)}<div class="sub-id">案件库有效实体</div></td><td>${esc(REASON_LABEL[c.reason_code]||c.reason_code||'待确认')}</td><td><span class="pill ${s[1]}">${s[0]}</span></td><td>${missing?`<span class="pill p-warn">仍缺 ${missing} 项</span>`:'<span class="pill p-good">无待补项</span>'}</td><td class="action-cell"><button class="tbtn primary" onclick="event.stopPropagation();openStoredCase('${esc(c.case_id)}')">进入 AI 分析</button></td></tr>`;}).join('')||'<tr><td colspan="5" class="empty-state"><strong>暂无有效案件记录</strong><p>列表不使用预置案件；只有成功写入案件库且可重新读取的案件才会显示。</p><button class="tbtn primary" onclick="openCreate(null)">新建案件</button></td></tr>';
  const pending=S.cases.filter(c=>c.phase!=='ASSESSED');$('pendingCaseCount').textContent=`${pending.length} 件`;
  $('pendingCaseRows').innerHTML=pending.slice(0,3).map(c=>`<div class="quick-row"><strong>${esc(c.case_id)}</strong><p>${esc((STATUS_VIEW[c.phase]||['待处理'])[0])} · 仍缺 ${(c.missing_labels||[]).length} 项资料</p><div class="actions"><button class="tbtn primary" onclick="openStoredCase('${esc(c.case_id)}')">进入 AI 分析</button></div></div>`).join('')||'<div class="panel-bd empty">暂无待处理案件</div>';}
async function openStoredCase(caseId){const ticket=OceanRequest.begin('case-open');const [result,auditResult]=await Promise.all([api("GET",`/cases/${caseId}`),api("GET",`/cases/${caseId}/audit`)]);
  if(!OceanRequest.isLatest(ticket))return;
  if(auditResult.ok&&Array.isArray(auditResult.data&&auditResult.data.events))S.auditByCase.set(caseId,auditResult.data.events);
  if(!result.ok){await loadCases();if(OceanRequest.isLatest(ticket))showView('overview');return;}
  const switched=S.caseId!==caseId;if(switched){S.expectedReason=null;S.autoEvidence=[];S.packaged=false;S.appealed=false;}
  const c=result.data;selectCase(c.case_id);if(!acceptCaseSnapshot(c))return;
  renderStoredDiagnosis(c);showView('diagnosis');if(await bindAgentCase(caseId,switched))await analyzeCurrentCase('CASE_OPENED');}
function renderStoredDiagnosis(c){if(c.case_id!==S.caseId||c.revision!==S.caseRevision)return;const s=STATUS_VIEW[c.phase]||['未知','p-mut'];const missing=c.missing_labels||[];
  $('diagnosisSummary').className=`panel diagnosis-summary ${c.phase==='ASSESSED'?'good':'warn'}`;
  $('diagId').textContent=c.case_id;$('diagStage').textContent=s[0];$('diagCode').textContent=REASON_LABEL[c.reason_code]||c.reason_code||'待确认';$('diagCaseId').textContent=c.case_id;
  $('diagSideId').innerHTML='<span class="pill p-good">案件库可读</span>';const status=$('diagStatus');status.className=`pill ${s[1]}`;status.textContent=s[0];
  if(c.phase==='REASON_PROPOSED'){$('diagCause').textContent='争议原因尚未确认';$('diagMeaning').textContent='系统已给出初步判断，需要人工确认后才能继续收集材料。';$('diagAdvice').textContent='请先确认争议原因，系统将在确认后生成缺失材料清单。';}
  else{$('diagCause').textContent=missing.length?`案件仍缺 ${missing.length} 项材料，暂不能完成评估`:'案件材料已齐全';$('diagMeaning').textContent=missing.length?'当前案件存在明确的证据缺口，下方清单来自后端当前状态。':'当前没有待补资料；欺诈类案件仍必须人工审核。';$('diagAdvice').textContent=missing.length?'请按清单逐项补交；每次提交后系统会重新读取案件状态。':'请在右侧输入审核结论；AI 只生成拟写入提案，确认后才会落库。';}
  $('diagImpact').textContent=c.phase==='REASON_PROPOSED'?'待确认原因':(missing.length?`仍缺 ${missing.length} 项`:'无待补项');const network=$('diagnosisNetwork');if(network)network.value=S.cardNetwork;const ruleOut=$('diagnosisRuleReferenceOut');if(ruleOut)ruleOut.innerHTML='';renderDiagnosticMaterials(c);}
$('tableSearch').addEventListener('input',renderTransactions);$('statusFilter').addEventListener('change',renderTransactions);
$('ruleSearch').addEventListener('keydown',event=>{if(event.key==='Enter')loadRules();});$('ruleScheme').addEventListener('change',loadRules);
function clearGlobalSearchStatus(){const status=$('globalSearchStatus');status.textContent='';status.classList.remove('on');}
function setGlobalSearchStatus(message){const status=$('globalSearchStatus');status.textContent=message;status.classList.add('on');}
const globalSearch=$('globalSearch');globalSearch.addEventListener('input',clearGlobalSearchStatus);globalSearch.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.target.value='';clearGlobalSearchStatus();return;}if(event.key!=='Enter')return;const raw=event.target.value.trim();if(!raw)return;if(S.currentView==='rules'){$('ruleSearch').value=raw;clearGlobalSearchStatus();loadRules();return;}const q=raw.toLowerCase();const hit=S.cases.find(c=>[c.case_id,c.reason_code,REASON_LABEL[c.reason_code],tr(REASON_LABEL[c.reason_code])].join(' ').toLowerCase().includes(q));if(hit){clearGlobalSearchStatus();openStoredCase(hit.case_id);return;}setGlobalSearchStatus('未找到匹配案件，请检查案件号或争议原因。');});
document.addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'){event.preventDefault();$('globalSearch').focus();}});
function focusTransactionSearch(){showView('overview');$('tableSearch').focus();}
function openCreate(){S.scenarioIndex=0;S.cardNetwork=SCENARIOS[0].network;S.expectedReason=SCENARIOS[0].reason;S.autoEvidence=SCENARIOS[0].available.slice();renderCreateForm();showView('create');}

const STAGES=["创建案件","补全材料","检查结果","生成材料"];
function stageStatus(){const st=STAGES.map(()=> "");const d=S.last;
  if(!S.caseId){st[0]="now";return st;}
  st[0]="done";const ph=d?d.phase:null;
  if(ph==="REASON_PROPOSED"||ph==="NEED_EVIDENCE"){st[1]="now";return st;}
  st[1]="done";st[2]="done";st[3]=S.packaged?"done":"now";
  return st;}
function renderStages(){const stt=stageStatus();let h="";
  STAGES.forEach((n,i)=>{if(i)h+=`<span class="sep ${stt[i]==='done'||stt[i-1]==='done'?'done':''}"></span>`;
    h+=`<span class="step ${stt[i]}"><span class="b">${stt[i]==='done'?'✓':(i+1)}</span>${n}</span>`;});
  $('steps').innerHTML=h;}

function renderCreateForm(){const selected=SCENARIOS[S.scenarioIndex]||SCENARIOS[0];const cards=SCENARIOS.map((s,i)=>`<button class="scenario-card${i===S.scenarioIndex?' on':''}" data-i="${i}" onclick="fillScenario(${i})">`
    +`<strong>${esc(s.label)}</strong><span>${esc(s.meta)}</span></button>`).join("");
  $('createAction').innerHTML=`<div style="color:var(--ink);font-weight:700">1. 选择常见案件模板</div>`
    +`<div class="scenario-grid">${cards}</div>`
    +`<label class="field-label" for="desc">2. 确认案件说明</label><textarea id="desc" rows="3">${esc(tr(selected.desc))}</textarea>`
    +`<div class="helper">创建完成后会进入案件详情，并列出案件处理所需材料。</div>`
    +`<div class="actions"><button class="tbtn primary" id="createCaseButton" onclick="openCase()">确认创建案件</button></div>`;}

async function openCase(loadAvailable=true){if(S.caseCreating)return;S.caseCreating=true;const ticket=OceanRequest.begin('case-open');const button=$('createCaseButton');if(button){button.disabled=true;button.textContent='正在创建案件…';}
  try{const {ok,data}=await api("POST","/cases",{description:$('desc').value.trim(),card_network:S.cardNetwork||null});
    if(!ok){$('createAction').insertAdjacentHTML('beforeend','<div class="form-error" role="alert">创建失败：请检查案件说明后重试。</div>');if(button){button.disabled=false;button.textContent='确认创建案件';}return;}
    const createdCaseId=data.case_id;let current=data;if(!OceanRequest.isLatest(ticket)){await loadCases();return;}selectCase(createdCaseId);acceptCaseSnapshot(current);S.packaged=false;S.appealed=false;S.autoEvidence=loadAvailable?SCENARIOS[S.scenarioIndex].available.slice():[];
    while(current.phase==='NEED_EVIDENCE'&&S.autoEvidence.length){const seeded=await api('POST',`/cases/${createdCaseId}/evidence`,{evidence_code:S.autoEvidence.shift()});if(!seeded.ok)break;current=seeded.data;}
    await loadCaseAudit(createdCaseId);if(!OceanRequest.isLatest(ticket)||!acceptCaseSnapshot(current)){await loadCases();return;}renderStoredDiagnosis(current);showView('diagnosis');if(await bindAgentCase(createdCaseId,true))await analyzeCurrentCase('CASE_OPENED');await loadCases();
  }finally{S.caseCreating=false;}}
async function refreshCase(){if(!S.caseId)return;const context=caseContext.capture();const result=await api("GET",`/cases/${context.caseId}`);if(result.ok&&caseContext.isCurrent(context,false))apply(result.data);}
async function confirmReason(){const context=caseContext.capture();const v=$('fix')?$('fix').value:(S.expectedReason||"");const result=await api("POST",`/cases/${context.caseId}/confirm`,v?{reason_code:v}:{});if(!result.ok||!caseContext.isCurrent(context,false))return;apply(result.data);if(S.agentCase&&await bindAgentCase(context.caseId,false))await analyzeCurrentCase('REASON_CONFIRMED');}
async function submitEvidence(code,caseId=S.caseId){if(!caseId||!code||S.evidenceSubmittingCases.has(caseId))return;S.evidenceSubmitting=true;S.evidenceSubmittingCases.add(caseId);const buttons=S.caseId===caseId?document.querySelectorAll('#action button'):[];buttons.forEach(button=>button.disabled=true);
  try{const result=await api("POST",`/cases/${caseId}/evidence`,{evidence_code:code});if(result.ok){if(S.caseId===caseId)apply(result.data);}else if(S.caseId===caseId){$('action').insertAdjacentHTML('beforeend','<div class="form-error" role="alert">补交失败：后端未接受该材料，案件状态未改变。</div>');buttons.forEach(button=>button.disabled=false);}}
  finally{S.evidenceSubmittingCases.delete(caseId);S.evidenceSubmitting=S.evidenceSubmittingCases.size>0;}}
async function finalize(){const context=caseContext.capture();const result=await api("POST",`/cases/${context.caseId}/finalize`);if(result.ok&&caseContext.isCurrent(context,false))apply(result.data);}
function fillScenario(i){const d=$('desc');if(d)d.value=tr(SCENARIOS[i].desc);S.scenarioIndex=i;
  S.cardNetwork=SCENARIOS[i].network;S.expectedReason=SCENARIOS[i].reason;S.autoEvidence=SCENARIOS[i].available.slice();
  document.querySelectorAll('.scenario-card').forEach(c=>c.classList.toggle('on',+c.dataset.i===i));}
async function autoRun(){if(!S.caseId)await openCase(false);let g=0;
  while(S.last&&S.last.phase!=="ASSESSED"&&g++<40){
    if(S.last.phase==="REASON_PROPOSED")await confirmReason();
    else if(S.last.phase==="NEED_EVIDENCE"&&S.autoEvidence.length){
      await submitEvidence(S.autoEvidence.shift());}else break;}}
async function completeAll(){let g=0;while(S.last&&S.last.phase==="NEED_EVIDENCE"&&g++<40){
  await submitEvidence(S.last.next_evidence);}}

function apply(d){if(!acceptCaseSnapshot(d))return;
  $('crumbId').textContent=d.case_id.slice(0,18);
  renderCaseHead(d);renderStages();renderAction();renderTrace(d);
  const ready=d.phase==="ASSESSED";$('verdictCard').style.display=ready?"block":"none";
  if(ready)renderAssess(d);refreshAudit();refreshMetrics();}

function renderCaseHead(d){
  const conf=d.reason_confirmed?'<span class="pill p-good">已确认</span>':'<span class="pill p-warn">待确认</span>';
  const st=PHASE[d.phase]||["—","p-mut",""];
  let h=`<div class="srow">`
    +`<div class="field"><div class="k">案件</div><div class="v mono">${esc(d.case_id.slice(0,18))}</div></div>`
    +`<div class="field"><div class="k">争议原因</div><div class="v">${esc(REASON_LABEL[d.reason_code]||d.reason_code||"—")} ${conf}</div></div>`;
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
  if(!S.caseId){if(tag)tag.textContent="尚未选择";$('action').innerHTML=`<div class="empty-state"><strong>尚未打开案件详情</strong><p>请返回案件中心选择案件，或通过“新建案件”创建一个案件。</p><button class="tbtn primary" onclick="showView('overview')">返回案件中心</button></div>`;return;}
  const ph=d.phase;if(tag)tag.textContent=(PHASE[ph]||["","",""])[2];
  if(ph==="REASON_PROPOSED"){
    $('action').innerHTML=`<div class="muted">${esc(d.question||"")}</div>`
      +`<div class="actions"><select id="fix" aria-label="确认或修正争议原因" style="max-width:280px"></select>`
      +`<button class="tbtn primary" onclick="confirmReason()">确认争议原因</button></div>`;populateReasons();
  }else if(ph==="NEED_EVIDENCE"){
    const labels=d.missing_labels||[];const next=d.next_evidence_label||"下一项证据";
    const question=cleanCopy(d.question||"");
    const missing=labels.map((x,i)=>`<div class="missing-row ${x===next?'next':''}"><span class="box">${i+1}</span><span>${x===next?'下一项优先补交：':''}${esc(x)}</span></div>`).join("");
    $('action').innerHTML=`<div class="missing-box"><div class="missing-head"><span>材料尚未齐全</span>`
      +`<span class="missing-count">仍缺 ${labels.length} 项</span></div><div class="missing-checklist">${missing}</div></div>`
      +(question?`<div style="font-size:15px;color:var(--ink);font-weight:600;margin-top:14px">${esc(question)}</div>`:"")
      +`<div class="helper">每补交一项，系统都会自动重新检查并提示下一项。</div>`
      +`<div class="actions"><button class="tbtn primary" onclick="openEvidenceModalForCase('${esc(S.caseId)}','${esc(d.next_evidence)}','${esc(next)}')">补交：${esc(next)}</button>`
      +`<button class="tbtn" onclick="finalize()">本次无法提供，提交人工复核</button>${latestEvidenceAction(d)}</div>`;
  }else if(ph==="ASSESSED"){$('action').innerHTML=`<span class="muted">材料收集已完成。请查看下方评估结果并选择下一步。</span>${latestEvidenceAction(d,true)}`;}
  else $('action').innerHTML=`<span class="muted">阶段：${esc(ph)}</span>`;}
async function populateReasons(){const {data}=await api("GET",`/catalog?locale=${S.loc}`);const sel=$('fix');if(!sel)return;
  sel.innerHTML='<option value="">（接受系统判定）</option>'+data.reasons.map(r=>`<option value="${esc(r.code)}">${esc(r.label)}</option>`).join("");}
