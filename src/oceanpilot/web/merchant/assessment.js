function renderReview(c){
  const review=c.review||{},current=review.current_record;
  $('reviewVersion').textContent=`当前版本 ${c.revision}`;
  $('currentReview').innerHTML=current&&current.case_revision===c.revision?`<div class="review-current"><span class="pill ${current.status==='APPROVED'?'p-good':'p-warn'}">${esc(reviewStatusLabel(current.status))}</span><p>${esc(current.summary)}</p><div class="meta">${esc(current.confirmed_by)} · ${esc(dateLabel(current.confirmed_at))} · 版本 ${esc(current.case_revision)}<br>审计 ${esc(current.audit_event_id)}</div></div>`:`<div class="review-current"><strong>当前版本尚未完成登记复核</strong><p>${review.stale?'旧复核未覆盖当前规则与材料版本，只作历史记录。':'企业运营方可在核对材料登记清单与内部处理门槛后记录决定。'}</p></div>`;
  $('reviewForm').hidden=!allowed('REVIEW');
  const approve=$('reviewDecision').querySelector('option[value="APPROVED"]');if(approve)approve.disabled=!(c.gate&&c.gate.can_review);
  if(!(c.gate&&c.gate.can_review)&&$('reviewDecision').value==='APPROVED')$('reviewDecision').value='NEEDS_MORE_INFO';
  $('reviewHistory').innerHTML=(review.history||[]).slice().reverse().map(item=>`<div class="review-history-item"><span class="pill ${current&&item.decision_id===current.decision_id?'p-acc':'p-mut'}">版本 ${esc(item.case_revision)}${current&&item.decision_id===current.decision_id?' · 当前复核决定':' · 历史记录'}</span> ${esc(reviewStatusLabel(item.status))}<p>${esc(item.summary)}</p><div class="meta">${esc(item.confirmed_by)} · ${esc(dateLabel(item.confirmed_at))} · 审计 ${esc(item.audit_event_id)}</div></div>`).join('')||'<p class="empty">暂无历史复核</p>';
  renderSummaryRows(c);
}
function previewReview(){
  formError('reviewError','');
  if(ROLE!=='BUSINESS'||!allowed('REVIEW'))return;
  if(!S.caseSnapshot.rule_fingerprint){formError('reviewError','尚未读取当前规则依据，请刷新本案后再预览复核。');return;}
  const summary=$('reviewSummary').value.trim(),decision=$('reviewDecision').value;
  if(summary.length<3){formError('reviewError','请填写至少 3 个字符的复核意见。');return;}
  if(decision==='APPROVED'&&!S.caseSnapshot.gate.can_review){formError('reviewError','当前版本仍有阻断项，不能批准登记复核。可退回补充或驳回。');return;}
  S.reviewDraft={caseId:S.caseId,revision:S.caseRevision,ruleFingerprint:S.caseSnapshot.rule_fingerprint,decision,summary,scope:['材料登记清单','内部处理门槛']};
  const rule=S.caseSnapshot.rule_reference||{},readiness=S.caseSnapshot.readiness||{};
  $('reviewProposal').innerHTML=`<div class="review-proposal"><h4>待确认：${esc(reviewStatusLabel(decision))}</h4><p>案件 ${esc(S.caseId)} · 版本 ${esc(S.caseRevision)}</p><p>登记清单 ${esc(readiness.present)}/${esc(readiness.total)} · 规则 ${esc(rule.rule_version_id||'没有精确匹配')}（${esc(rule.verification_status||'未核验')}）</p><p><b>复核范围：</b>材料登记清单、内部处理门槛。<br><b>不包含：</b>材料正文、真实性、一致性或真实交易核验。</p><p>${esc(summary)}</p><div class="actions"><button class="tbtn primary" data-write onclick="confirmWorkspaceReview()">确认写入复核决定</button><button class="tbtn" onclick="cancelWorkspaceReview()">返回修改</button></div></div>`;
  syncWriteButtons();applyLanguage();
}
function cancelWorkspaceReview(){S.reviewDraft=null;$('reviewProposal').innerHTML='';}
async function confirmWorkspaceReview(){
  const draft=S.reviewDraft;if(!draft||S.pendingCommand)return;
  if(draft.caseId!==S.caseId||draft.revision!==S.caseRevision||draft.ruleFingerprint!==S.caseSnapshot.rule_fingerprint){cancelWorkspaceReview();formError('reviewError','案件版本或规则依据已变化，请重新预览本版本复核范围。');return;}
  const result=await runCommand('REVIEW',{decision:draft.decision,summary:draft.summary,scope:draft.scope,expected_rule_fingerprint:draft.ruleFingerprint},{caseId:draft.caseId,revision:draft.revision});
  if(result)cancelWorkspaceReview();
}
function renderSummaryRows(c){
  $('summaryRows').innerHTML=(c.summaries||[]).slice().reverse().map(item=>`<div class="summary-row"><strong>${esc(item.title||'案件复核摘要（合成示例）')}</strong><div class="helper">冻结版本 ${esc(item.revision)}${item.revision===c.revision?' · 案件版本相同，规则以摘要为准':' · 历史案件版本'} · ${esc(dateLabel(item.generated_at))}</div><div class="actions"><button class="tbtn" onclick="downloadSummary('${esc(item.summary_id)}','html')">下载 HTML</button><button class="tbtn" onclick="downloadSummary('${esc(item.summary_id)}','json')">下载 JSON</button></div></div>`).join('')||'<p class="empty">尚无已生成摘要。企业运营方可生成当前版本的复核摘要。</p>';
  $('generateSummaryButton').disabled=S.summaryGenerating||Boolean(S.pendingCommand);
}
async function generateSummary(){
  if(ROLE!=='BUSINESS'||!S.caseId||S.summaryGenerating||S.pendingCommand)return;
  const context=caseContext.capture();S.summaryGenerating=true;$('generateSummaryButton').disabled=true;$('summaryStatus').textContent='正在从当前版本生成确定性复核摘要…';
  try{
    const result=await workspaceApi('POST',`/cases/${encodeURIComponent(context.caseId)}/summaries`,{expected_revision:context.revision});
    if(!caseContext.isCurrent(context)){if(S.caseId===context.caseId)$('summaryStatus').textContent='案件版本已变化，请刷新案件后重新生成。';return;}
    if(!result.ok){
      $('summaryStatus').textContent=result.status===409?'案件版本已变化，请刷新案件后重新生成。':'摘要生成结果尚未确认，请刷新本案查看已保存摘要，再决定是否重试。';
      if(result.status===0||result.status>=500)await refreshCase();return;
    }
    if(result.data.case_id!==context.caseId||result.data.revision!==context.revision){$('summaryStatus').textContent='摘要版本与本次请求不一致，请刷新案件后重新生成。';return;}
    $('summaryStatus').textContent=`摘要已保存 · 案件 ${context.caseId} · 版本 ${context.revision}`;
    await refreshCase();
  }finally{S.summaryGenerating=false;$('generateSummaryButton').disabled=Boolean(S.pendingCommand);}
}
async function downloadSummary(summaryId,format){
  const item=(S.caseSnapshot&&S.caseSnapshot.summaries||[]).find(value=>value.summary_id===summaryId);
  if(!item||!['html','json'].includes(format))return;
  const path=format==='html'?item.html_url:item.json_url;
  const url=new URL(path,location.origin);
  if(url.origin!==location.origin||!url.pathname.startsWith(`${WORKSPACE_BASE}/summaries/`))return;
  $('summaryStatus').textContent='正在读取已冻结摘要…';
  const result=await OceanRequest.text(url.pathname+url.search,{method:'GET',headers:demoHeaders()},15000);
  if(!result.ok){$('summaryStatus').textContent='摘要读取失败，请重试下载。';return;}
  const blob=new Blob([result.data],{type:format==='html'?'text/html;charset=utf-8':'application/json;charset=utf-8'});
  const objectUrl=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=objectUrl;link.download=`案件复核摘要（合成示例）-${item.case_id}-v${item.revision}.${format}`;
  document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(objectUrl),1000);
  $('summaryStatus').textContent=`已下载冻结版本 ${item.revision} 的 ${format.toUpperCase()} 摘要。`;
}
