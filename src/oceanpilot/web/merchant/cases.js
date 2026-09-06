const CASE_SECTIONS=['summary','materials','rules','concerns','review'];
const CASE_VIEWS=['overview','workspace','create','samples','rules'];
const PHASE_LABEL={REASON_PROPOSED:'待确认原因',CRITICAL_MISSING:'关键材料阻断',LIMITED_ANALYSIS:'有限分析',NEEDS_REVIEW:'疑点待复核',NO_EXACT_RULE:'无精确规则',READY_FOR_REVIEW:'待登记复核',HUMAN_APPROVED:'登记复核通过',NEEDS_MORE_INFO:'已退回补证',REJECTED:'复核驳回'};
function currentNavigationUrl(path=location.pathname){
  const url=new URL(path,location.origin);
  const query=$('tableSearch').value.trim(),status=$('statusFilter').value,owner=$('ownerFilter').value;
  if(query)url.searchParams.set('q',query);
  if(status&&status!=='ALL')url.searchParams.set('status',status);
  if(owner&&owner!=='ALL')url.searchParams.set('owner',owner);
  if(S.caseId&&(S.currentView==='workspace'||S.currentView==='rules')){
    url.searchParams.set('case',S.caseId);url.searchParams.set('section',S.section);
  }
  if(S.currentView!=='overview')url.searchParams.set('view',S.currentView);
  if(S.currentView==='rules'&&S.currentRuleId)url.searchParams.set('rule',S.currentRuleId);
  return url;
}
function writeNavigation(replace=false){
  const url=currentNavigationUrl();
  if(url.pathname+url.search!==location.pathname+location.search)history[replace?'replaceState':'pushState']({},'',url.pathname+url.search);
  updateRoleLinks();
}
function updateRoleLinks(){
  const path=ROLE==='BUSINESS'?'/demo':'/business';
  const url=currentNavigationUrl(path);
  for(const id of ['roleSwitch','sideRoleLink'])if($(id))$(id).href=url.pathname+url.search;
  const reviewUrl=currentNavigationUrl('/business');
  if(S.caseId){reviewUrl.searchParams.set('case',S.caseId);reviewUrl.searchParams.set('section','review');reviewUrl.searchParams.set('view','workspace');}
  $('reviewRoleLink').href=reviewUrl.pathname+reviewUrl.search;
}
function showView(value,options={}){
  const v=value==='diagnosis'||value==='flow'?'workspace':value;
  if(!CASE_VIEWS.includes(v))return;
  if(v==='workspace'&&!S.caseSnapshot)return;
  if(v!=='workspace')OceanRequest.begin('case-open');
  S.currentView=v;S.navigationGeneration++;
  document.querySelectorAll('.view').forEach(node=>node.classList.toggle('on',node.id===`v-${v}`));
  document.querySelectorAll('.nav button[data-v],.mobile-nav button').forEach(button=>{
    const active=button.dataset.v===(v==='workspace'?'overview':v);button.classList.toggle('on',active);
    if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
  });
  const labels={overview:'案件中心',workspace:S.caseSnapshot&&S.caseSnapshot.title||'案件工作台',create:'新建案件',samples:'演示样例',rules:'规则知识'};
  $('crumbId').textContent=labels[v];
  const view=$(`v-${v}`);view.setAttribute('tabindex','-1');view.focus({preventScroll:true});
  if(options.history!==false)writeNavigation(Boolean(options.replace));else updateRoleLinks();
  if(v==='overview')loadCases();
  if(v==='rules')loadRules();
  if(v==='workspace')selectCaseSection(S.section,{write:false,scroll:options.scroll!==false});
  applyLanguage();
}
function returnToCaseCenter(){showView('overview');}
function openCreate(){showView('create');$('caseName').focus();}
function selectCaseSection(section,options={}){
  S.section=CASE_SECTIONS.includes(section)?section:'summary';
  document.querySelectorAll('[data-section]').forEach(button=>{const active=button.dataset.section===S.section;button.classList.toggle('on',active);if(active)button.setAttribute('aria-current','location');else button.removeAttribute('aria-current');});
  if(options.write!==false)writeNavigation(true);
  if(options.scroll!==false){const target=$(`section-${S.section}`);if(target)requestAnimationFrame(()=>target.scrollIntoView({block:'start',behavior:'auto'}));}
}
async function restoreNavigation(){
  const url=new URL(location.href);
  $('tableSearch').value=url.searchParams.get('q')||'';
  $('statusFilter').value=url.searchParams.get('status')||'ALL';if(!$('statusFilter').value)$('statusFilter').value='ALL';
  $('ownerFilter').value=url.searchParams.get('owner')||'ALL';if(!$('ownerFilter').value)$('ownerFilter').value='ALL';
  S.section=CASE_SECTIONS.includes(url.searchParams.get('section'))?url.searchParams.get('section'):'summary';
  const requested=url.searchParams.get('view'),caseId=url.searchParams.get('case');
  if(caseId){
    await openStoredCase(caseId,{history:false,scroll:false});
    if(requested==='rules'&&S.caseId===caseId){S.currentRuleId=url.searchParams.get('rule');S.ruleReturnContext={caseId,section:S.section};showView('rules',{history:false});}
    else if(S.caseId===caseId)selectCaseSection(S.section,{write:false});
  }else showView(CASE_VIEWS.includes(requested)&&requested!=='workspace'?requested:'overview',{history:false});
  updateRoleLinks();
}
async function loadCases(){
  const ticket=OceanRequest.begin('case-list');
  const result=await workspaceApi('GET','/cases',undefined,{timeoutMs:15000});
  if(!OceanRequest.isLatest(ticket))return;
  if(!result.ok||!Array.isArray(result.data.cases)){
    $('transactionCount').textContent='读取失败';
    $('transactionRows').innerHTML='<tr><td colspan="8"><div class="error-state">案件列表暂不可用。<button class="tbtn" onclick="loadCases()">重试读取</button></div></td></tr>';return;
  }
  S.cases=result.data.cases;renderTransactions();
}
function renderTransactions(){
  const q=$('tableSearch').value.trim().toLowerCase(),status=$('statusFilter').value,owner=$('ownerFilter').value;
  const rows=S.cases.filter(c=>(status==='ALL'||c.phase===status)&&(owner==='ALL'||c.next_actor===owner)&&[c.title,c.case_id,c.reason_code,c.reason_label,c.card_network,c.rule_reference&&c.rule_reference.scheme_reason_code].join(' ').toLowerCase().includes(q));
  $('transactionCount').textContent=`${rows.length} 件案件 · 更新于 ${new Date().toLocaleTimeString(S.loc==='en'?'en-US':'zh-CN',{hour12:false})}`;
  $('transactionRows').innerHTML=rows.map(c=>`<tr><td><strong>${esc(c.title||c.case_id)}</strong><div class="sub-id">${esc(c.case_id)} · 版本 ${esc(c.revision)}</div>${c.scenario?`<span class="pill p-mut">合成样例 ${esc(c.scenario)}</span>`:''}</td><td>${esc(c.reason_label||'待确认原因')}<div class="sub-id">${esc(NETWORK_LABEL[c.card_network]||'卡组织待确认')}${c.rule_reference&&c.rule_reference.scheme_reason_code?` · ${esc(c.rule_reference.scheme_reason_code)}`:''}</div></td><td><span class="pill ${c.missing_count?'p-warn':'p-acc'}">${esc(c.phase_label||PHASE_LABEL[c.phase]||c.phase)}</span></td><td>${Number.isInteger(c.missing_count)?c.missing_count:'—'} 项</td><td>${esc(ownerLabel(c.next_actor))}</td><td><span class="pill ${c.review_status==='APPROVED'?'p-good':'p-mut'}">${esc(reviewStatusLabel(c.review_status))}</span></td><td>${esc(dateLabel(c.updated_at))}</td><td class="action-cell"><button class="tbtn primary" onclick="openStoredCase('${esc(c.case_id)}')">打开案件</button></td></tr>`).join('')||'<tr><td colspan="8"><div class="empty-state"><strong>暂无匹配案件</strong><p>可调整筛选，或从演示样例创建一个新副本。</p><button class="tbtn" onclick="showView(\'samples\')">打开演示样例</button></div></td></tr>';
  applyLanguage();
}
async function openStoredCase(caseId,options={}){
  const ticket=OceanRequest.begin('case-open');S.loadingCase=true;
  const result=await workspaceApi('GET',`/cases/${encodeURIComponent(caseId)}`,undefined,{timeoutMs:15000});
  if(!OceanRequest.isLatest(ticket))return;
  S.loadingCase=false;
  if(!result.ok){S.commandProblem='案件暂时无法读取，请返回列表重试。';renderCommandNotice();showView('overview',{history:options.history});return;}
  selectCase(result.data.case_id);
  if(!acceptCaseSnapshot(result.data))return;
  renderStoredDiagnosis(result.data);showView('workspace',options);
}
async function refreshCase(){
  if(!S.caseId)return;
  const context=caseContext.capture();const result=await workspaceApi('GET',`/cases/${encodeURIComponent(context.caseId)}`,undefined,{timeoutMs:15000});
  if(!caseContext.isCurrent(context,false))return;
  if(!result.ok){S.commandProblem='本案刷新失败，仍显示上次读取的版本；请重试。';S.snapshotStale=true;renderCommandNotice();return;}
  if(acceptCaseSnapshot(result.data))renderStoredDiagnosis(result.data);
}
function renderStoredDiagnosis(c){
  if(c.case_id!==S.caseId||c.revision!==S.caseRevision)return;
  $('caseTitle').textContent=c.title||'合成争议案件';$('diagId').textContent=c.case_id;
  $('caseRevision').textContent=`版本 ${c.revision}`;$('caseUpdated').textContent=`更新于 ${dateLabel(c.updated_at)}`;
  $('diagStatus').textContent=c.phase_label||PHASE_LABEL[c.phase]||c.phase;$('diagStatus').className=`pill ${c.missing_count?'p-warn':'p-acc'}`;
  $('caseReviewBadge').textContent=reviewStatusLabel(c.review_status);$('caseReviewBadge').className=`pill ${c.review_status==='APPROVED'?'p-good':'p-mut'}`;$('caseReviewBadge').hidden=c.phase==='HUMAN_APPROVED'&&c.review_status==='APPROVED';
  $('caseOwner').textContent=`待处理方：${ownerLabel(c.next_actor)}`;
  const gate=c.gate||{},readiness=c.readiness||{},next=c.next_action||{};
  $('caseGate').textContent=PHASE_LABEL[gate.status]||'由后端校验处理条件';$('caseGate').hidden=!gate.status||gate.status===c.phase;$('diagCause').textContent=gate.reason||next.label||'查看当前材料登记状态';
  $('diagMeaning').textContent=readiness.meaning||'材料登记就绪度仅表示内部清单完成情况。';$('caseDescription').textContent=c.description||'';
  $('caseFacts').innerHTML=[['卡组织',NETWORK_LABEL[c.card_network]||'待确认'],['争议原因',c.reason_label||'待确认'],['流程前提',c.formal_dispute?'已进入正式争议流程（合成）':'正式争议前提待确认'],['材料边界','仅登记元数据 · 正文未读取']].map(([label,value])=>`<div class="fact"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('');
  $('readinessLabel').textContent=`材料登记就绪度 ${readiness.present??'—'} / ${readiness.total??'—'}`;
  $('readinessMeaning').textContent='清单完成度，不是胜诉率或业务准确率';
  const ratio=typeof readiness.ratio==='number'?readiness.ratio:Number(readiness.ratio||0);$('readinessBar').style.width=`${Math.round(Math.max(0,Math.min(1,ratio))*100)}%`;
  $('diagMissingBadge').textContent=c.reason_confirmed?`仍缺 ${c.missing_count} 项`:'先确认争议原因';
  $('caseNextAction').innerHTML=`<strong>下一步：${esc(next.label||'等待人工确认')}</strong><p>${esc(next.reason||'')}</p><p>需要 ${esc(ownerLabel(next.owner||c.next_actor))} · ${next.approval_required?'需要人工确认':'只读查看'}</p>${next.expected_state?`<p>预期变化：${esc(PHASE_LABEL[next.expected_state]||next.expected_state)}</p>`:''}<div class="actions"><button class="tbtn primary" onclick="selectCaseSection('${!c.reason_confirmed?'summary':c.missing_count?'materials':(c.concerns||[]).some(x=>x.status==='OPEN')?'concerns':'review'}')">查看并处理下一步</button></div>`;
  $('caseReasonControls').innerHTML=!c.reason_confirmed&&allowed('CONFIRM_REASON')?'<div class="note"><b>确认争议原因后生成材料清单</b><div class="actions"><select id="diagReasonFix" aria-label="确认争议原因"></select><button class="tbtn primary" data-write onclick="confirmDiagnosisReason()">确认争议原因</button></div></div>':'';
  if(!c.reason_confirmed&&allowed('CONFIRM_REASON'))populateDiagnosisReasons(c.reason_code);
  $('diagnosisNetwork').value=c.card_network||'';$('diagnosisNetwork').disabled=!allowed('SET_NETWORK');$('saveNetworkButton').dataset.forbidden=String(!allowed('SET_NETWORK'));
  renderDiagnosticMaterials(c);renderCaseRule(c);renderConcerns(c);renderReview(c);renderCaseHistory(c);
  $('agentCaseContext').textContent=`${c.case_id.slice(0,12)}… · 版本 ${c.revision}`;
  if(c.latest_analysis&&c.latest_analysis.case_id===c.case_id&&c.latest_analysis.case_revision===c.revision)renderAgentTurn(c.latest_analysis,false);
  else if(!S.lastAgentTurn||S.lastAgentTurn.case_revision!==c.revision){$('agentOutput').innerHTML='<p class="muted">当前版本尚未生成 Agent 输出。缺口与下一步来自后端确定性规则。</p>';$('agentRuntimeBadge').textContent='尚未生成输出';}
  updateRoleLinks();syncWriteButtons();applyLanguage();
}
async function populateDiagnosisReasons(reason){
  const context=caseContext.capture();const result=await api('GET',`/catalog?locale=${S.loc}`);
  if(!result.ok||!caseContext.isCurrent(context)||!$('diagReasonFix'))return;
  $('diagReasonFix').innerHTML=(result.data.reasons||[]).map(item=>`<option value="${esc(item.code)}" ${item.code===reason?'selected':''}>${esc(item.label)}</option>`).join('');
}
async function confirmDiagnosisReason(){if(!S.caseId||!allowed('CONFIRM_REASON'))return;await runCommand('CONFIRM_REASON',{reason_code:$('diagReasonFix').value});}
async function saveCaseNetwork(){if(!allowed('SET_NETWORK'))return;await runCommand('SET_NETWORK',{card_network:$('diagnosisNetwork').value});}
async function openCase(){
  if(S.pendingCommand||S.commandSending)return;
  formError('createError','');
  if(!$('formalDisputeConfirm').checked){formError('createError','请明确确认：这是已进入正式争议流程的合成案件。');return;}
  const title=$('caseName').value.trim(),description=$('desc').value.trim();
  if(!title||description.length<10){formError('createError','请填写案件名称及至少 10 个字符的合成案件说明。');return;}
  await runCommand('CREATE_CASE',{title,description,card_network:$('createNetwork').value,formal_dispute:true});
}
async function copySample(sample){if(['A','B','C'].includes(sample))await runCommand('COPY_SAMPLE',{sample});}
async function finalize(){if(allowed('FINALIZE'))await runCommand('FINALIZE',{});}
function renderCaseHistory(c){
  const labels={CASE_OPENED:'案件创建',REASON_CONFIRMED:'原因已确认',REASON_CLASSIFIED:'原因识别',EVIDENCE_ADDED:'材料已登记',EVIDENCE_WITHDRAWN:'材料登记已撤回',COLLECTION_FINALIZED:'材料收集结束',CARD_NETWORK_UPDATED:'卡组织已更新',REVIEW_DECISION_RECORDED:'登记复核已记录',REVIEW_DECISION_CONFIRMED:'登记复核已确认',CONCERN_REPORTED:'疑点已登记',CONCERN_RESOLVED:'疑点已处理'};
  $('auditOut').innerHTML=(c.timeline||[]).slice().reverse().map(item=>`<li><div class="e">${esc(labels[item.event_type]||item.event_type)}${item.detail?` · ${esc(typeof item.detail==='string'?item.detail:JSON.stringify(item.detail))}`:''}</div><div class="m">版本 ${esc(item.case_revision)} · ${esc(dateLabel(item.occurred_at))} · ${esc(item.actor||'系统记录')}</div></li>`).join('')||'<li class="empty">尚无处理记录</li>';
}
