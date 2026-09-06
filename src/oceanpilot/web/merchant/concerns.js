const CONCERN_KIND={FACT_CONFLICT:'事实冲突',SOURCE_ISSUE:'来源问题',RULE_CONFLICT:'规则冲突'};
function renderConcerns(c){
  const concerns=c.concerns||[],open=concerns.filter(item=>item.status==='OPEN');
  $('concernCount').textContent=`${open.length} 项待处理`;
  $('unverifiedItems').innerHTML='<b>仍未完成的核验</b><ul class="unverified-list">'+(c.unverified_items||[]).map(item=>`<li>${esc(item)}</li>`).join('')+'</ul><span class="helper">疑点来自人工登记或结构化元数据检查，不代表已读取文件正文。</span>';
  $('concernRows').innerHTML=concerns.map(item=>`<article class="concern-item ${item.status==='OPEN'?'':'resolved'}"><h3>${esc(CONCERN_KIND[item.kind]||item.kind)} · ${esc(item.field)} <span class="pill ${item.status==='OPEN'?'p-warn':'p-mut'}">${item.status==='OPEN'?'待处理':'已记录处理决定'}</span></h3><p>${esc(item.summary)}</p>${item.kind==='SOURCE_ISSUE'&&item.status==='OPEN'?'<p class="note">来源未明确时，请先撤回对应材料登记，明确来源后重新登记，再由企业运营方复核此疑点；仅记录“已知悉”不会解除阻断。</p>':''}<div class="comparison"><div><span>原登记值 / 来源</span><strong>${esc(item.original_value||'未提供')}</strong><br>${esc(item.original_source||'未提供')}</div><div><span>建议值 / 来源</span><strong>${esc(item.proposed_value||'未提供')}</strong><br>${esc(item.proposed_source||'未提供')}</div></div><div class="helper">${esc(item.reported_by)} · ${esc(dateLabel(item.reported_at))} · 登记版本 ${esc(item.case_revision)}</div>${item.status==='OPEN'&&allowed('RESOLVE_CONCERN')?`<div class="concern-resolution"><label class="field-label" for="resolution-${esc(item.concern_id)}">处理决定</label><select id="resolution-${esc(item.concern_id)}"><option value="KEEP_ORIGINAL">保留原登记</option><option value="ACCEPT_PROPOSED">采纳建议值</option><option value="ACKNOWLEDGE">确认已知悉并说明处理边界</option></select><textarea id="resolution-summary-${esc(item.concern_id)}" rows="2" maxlength="1000" placeholder="说明处理理由及仍需核验的事项"></textarea><div class="actions"><button class="tbtn" data-write onclick="resolveConcern('${esc(item.concern_id)}')">确认记录处理决定</button></div></div>`:item.resolution_summary?`<p><b>处理说明：</b>${esc(item.resolution_summary)}</p><div class="helper">${esc(item.resolved_by)} · ${esc(dateLabel(item.resolved_at))}</div>`:''}</article>`).join('')||'<p class="empty">目前未登记冲突或来源疑点；这不等于已经验证材料内容一致。</p>';
  $('concernForm').hidden=!allowed('ADD_CONCERN');
}
async function addConcern(){
  if(!allowed('ADD_CONCERN'))return;
  const data={kind:$('concernKind').value,field:$('concernField').value.trim(),original_value:$('concernOriginal').value.trim(),proposed_value:$('concernProposed').value.trim(),original_source:$('concernOriginalSource').value.trim(),proposed_source:$('concernProposedSource').value.trim(),summary:$('concernSummary').value.trim()};
  if(!data.field||data.summary.length<3){formError('concernError','请填写涉及字段及疑点说明。');return;}
  formError('concernError','');await runCommand('ADD_CONCERN',data);
}
async function resolveConcern(concernId){
  if(!allowed('RESOLVE_CONCERN'))return;
  const summary=$(`resolution-summary-${concernId}`).value.trim();
  if(summary.length<3){S.commandProblem='请填写疑点处理说明，再确认记录处理决定。';renderCommandNotice();return;}
  await runCommand('RESOLVE_CONCERN',{concern_id:concernId,resolution:$(`resolution-${concernId}`).value,summary});
}
