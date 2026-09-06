function fillAgentPrompt(text){$('agentMessage').value=text;$('agentMessage').focus();}
function agentRuntimeDetails(data){
  const runtime=data.runtime||{};
  return `${runtime.provider||runtime.mode||''} ${runtime.model||''}${data.failure_code?` · 降级原因 ${data.failure_code}`:''}`.trim();
}
function renderAgentServiceStatus(){
  const node=$('agentServiceStatus');if(!node)return;
  const runtime=S.caseSnapshot&&S.caseSnapshot.runtime||{};
  const label=runtime.mode==='DEEPSEEK_LIVE'?'当前服务配置：实时 DeepSeek':runtime.mode==='OFFLINE_FALLBACK'?'当前服务配置：离线规则':runtime.mode==='INJECTED_MODEL'?'当前服务配置：合成测试模型':'当前服务配置尚未读取，请刷新案件。';
  node.innerHTML=`<strong>${esc(label)}</strong>${runtime.model?` · ${esc(runtime.model)}`:''}<br><span>当前配置与历史回复来源分别记录；每条回复以自身来源标签为准。</span>`;
}
function renderAgentHistory(){
  $('agentHistory').innerHTML=S.agentMessages.slice(-12).map(item=>{
    if(item.role==='user')return `<div class="chat-bubble user">${esc(item.text)}</div>`;
    const source=item.output_source||item.failure_code?agentOutputSource(item):{label:'历史来源未记录',className:'p-mut'};
    const details=agentRuntimeDetails(item);
    return `<div class="chat-bubble assistant"><div class="helper"><span class="pill ${source.className}">${esc(source.label)}</span>${details?`<div>${esc(details)}</div>`:''}</div><div>${esc(item.text)}</div></div>`;
  }).join('')||'<p class="empty">本次尚无对话</p>';
}
function appendAgentMessage(role,text,result={}){
  const message={role,text};
  if(role==='assistant'){
    const runtime=result.runtime||{};
    Object.assign(message,{output_source:result.output_source||null,failure_code:result.failure_code||null,
      runtime:{mode:runtime.mode||null,provider:runtime.provider||null,model:runtime.model||null}});
  }
  S.agentMessages.push(message);renderAgentHistory();
}
function agentOutputSource(data){
  if(data.output_source==='FALLBACK'||data.failure_code)return {label:'模型异常后的降级输出',className:'p-warn'};
  if(data.output_source==='MODEL')return {label:'实时模型输出',className:'p-good'};
  if(data.output_source==='DETERMINISTIC')return {label:data.runtime&&data.runtime.mode==='OFFLINE_FALLBACK'?'离线确定性输出':'确定性规则输出',className:'p-acc'};
  return {label:'本次输出来源未报告',className:'p-mut'};
}
function renderAgentTurn(data,append=true){
  if(!data||data.case_id!==S.caseId||data.case_revision!==S.caseRevision)return;
  S.lastAgentTurn=data;
  if(append&&data.assistant_message)appendAgentMessage('assistant',data.assistant_message,data);
  const source=agentOutputSource(data),judgment=data.judgment||{},trace=data.agent_trace||[];
  const badge=$('agentRuntimeBadge');badge.textContent=source.label;badge.className=`pill runtime-badge ${source.className}`;
  const citations=(data.citations||[]).map(item=>`<div class="agent-citation"><strong>${esc(item.title)}</strong><p>${esc(item.claim)}</p><p>${esc(item.verification_status)} · ${esc(item.limitation)}</p>${item.reference_id?`<button class="tbtn" onclick="showRuleReference('${esc(item.reference_id)}')">查看引用规则</button>`:''}</div>`).join('');
  const action=data.recommended_action||{};
  const next=action.kind==='OPEN_EVIDENCE_MODAL'&&action.evidence_code&&allowed('REGISTER_MATERIAL')?`<div class="actions"><button class="tbtn" onclick="openEvidenceModal('${esc(action.evidence_code)}','${esc(action.evidence_label||action.evidence_code)}')">查看并登记所需材料</button></div>`:action.kind&&action.kind!=='NONE'?'<div class="helper">涉及状态变更的意见，请到对应分区查看范围并明确确认。</div>':'';
  $('agentOutput').innerHTML=`<div class="assistant-message"><span>${esc(source.label)} · 版本 ${esc(data.case_revision)}</span><p>${esc(data.assistant_message||data.analysis_summary||'未返回说明')}</p></div><div class="helper">${esc(agentRuntimeDetails(data))}${data.result==='REPLAYED'?' · 已保存结果回放':''}</div><p class="judgment-summary">${esc(data.decision_reason||judgment.decision_summary||'')}</p>${judgment.next_action?`<div class="next-action"><strong>建议下一步</strong><p>${esc(judgment.next_action)}</p></div>`:''}${next}${citations?`<details class="agent-details"><summary>规则引用与核验边界</summary><div class="agent-citations">${citations}</div></details>`:'<p class="helper">当前没有精确匹配的规则引用。</p>'}<details class="agent-details"><summary>查看执行记录（不展示思维链）</summary><div class="agent-trace">${trace.map(step=>`<div class="trace-step ${step.status==='BLOCKED'?'blocked':'rule'}"><div class="trace-top"><strong>${esc(step.actor)}</strong><span>${esc(step.status)}</span></div><p>${esc(step.action)}</p><div class="trace-meta">${esc(step.source)} · ${esc(step.output_summary)}</div></div>`).join('')}</div></details><p class="helper">材料仅登记元数据；AI 未读取正文，也未核验真实交易或材料内容一致性。</p>`;
  applyLanguage();
}
async function bindAgentCase(caseId){
  if(S.caseId!==caseId||!S.caseSnapshot)return false;
  S.agentBoundCaseId=caseId;return true;
}
async function runAgentTurn(message,trigger='USER_MESSAGE',showUser=false){
  if(!S.agentCase)return false;
  const caseId=S.caseId,status=$('agentTurnStatus');
  if(S.agentSubmitting){
    if(S.pendingAgentTurn&&S.pendingAgentTurn.trigger==='USER_MESSAGE'){status.textContent='已有一条输入等待分析，请稍后再发送。';return false;}
    S.pendingAgentTurn={message,trigger,caseId,showUser};status.textContent='输入已排队，将在当前分析结束后处理。';return true;
  }
  const context=caseContext.capture();S.agentSubmitting=true;
  if(showUser){appendAgentMessage('user',message);if($('agentMessage').value.trim()===message)$('agentMessage').value='';}
  $('agentSendButton').disabled=true;$('agentAnalyzeButton').disabled=true;status.className='copilot-status';status.textContent='正在读取当前案件版本并生成说明…';
  try{
    const payload={case_id:caseId,message,trigger,locale:S.loc==='en'?'en-US':'zh-CN'};
    if(S.caseSnapshot.card_network)payload.card_network=S.caseSnapshot.card_network;
    const result=await requestJson('','POST','/api/v1/agent/turns',payload,{timeoutMs:45000});
    if(!caseContext.isCurrent(context))return false;
    if(!result.ok){status.className='copilot-status error';status.innerHTML='本轮说明未完成，可重试分析；本操作不批准或提交案件。<button class="tbtn" onclick="analyzeCurrentCase()">重试分析</button>';return false;}
    if(result.data.case_id!==caseId||result.data.case_revision!==S.caseRevision){status.textContent='服务端案件版本已变化，请刷新本案后重新分析。';return false;}
    renderAgentTurn(result.data);status.textContent=`已完成本案版本 ${S.caseRevision} 的说明。`;return true;
  }finally{
    S.agentSubmitting=false;$('agentSendButton').disabled=false;$('agentAnalyzeButton').disabled=false;
    const pending=S.pendingAgentTurn;S.pendingAgentTurn=null;
    if(pending&&pending.caseId===S.caseId)await runAgentTurn(pending.message,pending.trigger,pending.showUser);
  }
}
async function sendAgentTurn(){const message=$('agentMessage').value.trim();if(message.length<3){$('agentTurnStatus').textContent='请至少输入 3 个字符。';return;}await runAgentTurn(message,'USER_MESSAGE',true);}
async function analyzeCurrentCase(){await runAgentTurn('请基于当前案件版本，解释材料登记缺口、阻断原因、下一步和需要谁确认；明确尚未读取文件正文。','USER_MESSAGE',false);}
