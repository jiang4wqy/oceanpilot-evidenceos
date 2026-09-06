function renderDiagnosticMaterials(c){
  const missing=c.missing||[];
  $('diagMaterialRows').innerHTML=missing.length?missing.map((item,index)=>`<div class="material-row"><span class="material-state">${index+1}</span><div><strong>${esc(item.label)}${item.critical?' <span class="crit-tag">关键材料</span>':''}</strong><p class="material-description">为什么需要：${esc(item.why||'请按当前案件材料要求补充登记。')}</p><p class="material-impact">补充后：${esc(item.what_changes||'后端重新计算本案材料登记缺口。')}</p></div>${allowed('REGISTER_MATERIAL')?`<button class="tbtn primary" data-write onclick="openEvidenceModal('${esc(item.code)}','${esc(item.label)}')">登记材料</button>`:''}</div>`).join(''):`<div class="empty">${c.reason_confirmed?'当前没有待登记材料；正文与真实性仍未核验。':'确认争议原因后显示缺失材料清单。'}</div>`;
  const registered=(c.materials||[]).filter(item=>item.active);
  $('registeredMaterialRows').innerHTML=registered.map(item=>materialRow(item,c)).join('')||'<div class="empty">尚未登记材料</div>';
  $('withdrawnMaterialRows').innerHTML=(c.materials||[]).filter(item=>!item.active).map(item=>materialRow(item,c)).join('')||'<p class="empty">暂无撤回记录</p>';
  $('materialActions').innerHTML=allowed('FINALIZE')&&missing.length?'<button class="tbtn" data-write onclick="finalize()">本次无法补齐，转人工处理</button>':'';
}
function materialRow(item,c){
  return `<div class="material-row ${item.active?'done':''}"><span class="material-state registered">${item.active?'✓':'↶'}</span><div><strong>${esc(item.label||item.code)}</strong><div class="material-meta"><span data-no-i18n>${esc(item.file_name||'未记录文件名')}</span><br>来源：${esc(MATERIAL_SOURCE[item.source]||'来源待确认')}<br><span data-no-i18n>${esc(item.registered_by||'登记人未记录')}</span> · ${esc(dateLabel(item.registered_at))} · 登记版本 ${esc(item.registered_revision)}<br><b>正文未读取 · 内容未核验</b>${!item.active?`<br>撤回于 ${esc(dateLabel(item.withdrawn_at))}`:''}</div></div>${item.active&&allowed('WITHDRAW_MATERIAL')?`<button class="tbtn withdraw-action" data-write onclick="openWithdrawModal('${esc(item.code)}')">撤回登记</button>`:''}</div>`;
}
function openEvidenceModal(code,label){
  if(!S.caseId||!allowed('REGISTER_MATERIAL'))return;
  S.dialogTrigger=document.activeElement;
  S.evidenceDraft={caseId:S.caseId,revision:S.caseRevision,code,label,fileName:'',source:'UNKNOWN',finished:false};
  $('evidenceModalCase').textContent=`${S.caseId} · 版本 ${S.caseRevision}`;$('evidenceModalLabel').textContent=label;
  for(const id of ['evidenceFile','evidenceSource','syntheticEvidenceButton'])$(id).disabled=false;
  $('evidenceFile').value='';$('evidenceSource').value='UNKNOWN';$('selectedEvidenceFile').textContent='尚未选择文件';
  $('evidenceModalError').textContent='';$('evidenceReceipt').innerHTML='';
  const button=$('evidenceSubmitButton');button.disabled=true;button.dataset.forbidden='true';button.textContent='确认登记材料';
  $('evidenceCancelButton').textContent='取消';
  $('evidenceModal').classList.add('on');$('evidenceModal').setAttribute('aria-hidden','false');setDialogBackground(true);$('evidenceFile').focus();applyLanguage();
}
function selectEvidenceFile(input){
  if(!S.evidenceDraft)return;
  const file=input.files&&input.files[0];S.evidenceDraft.fileName=file?file.name:'';S.evidenceDraft.source='SYNTHETIC_USER_METADATA';
  $('evidenceSource').value=S.evidenceDraft.source;
  $('selectedEvidenceFile').textContent=file?`已选择合成材料文件名：${file.name}。不读取或上传正文。`:'尚未选择文件';
  $('evidenceSubmitButton').dataset.forbidden=file?'false':'true';syncWriteButtons();
}
function useSyntheticEvidenceFile(){
  if(!S.evidenceDraft)return;
  const draft=S.evidenceDraft;draft.fileName=`synthetic-${draft.code.replace(/[^a-z0-9]+/gi,'-')}.pdf`;draft.source='SYNTHETIC_TEMPLATE';
  $('evidenceFile').value='';$('evidenceSource').value=draft.source;$('selectedEvidenceFile').textContent=`${draft.fileName} · Synthetic 演示占位，仅元数据`;
  $('evidenceSubmitButton').dataset.forbidden='false';syncWriteButtons();
}
function closeEvidenceModal(){
  if(S.commandSending)return;
  $('evidenceModal').classList.remove('on');$('evidenceModal').setAttribute('aria-hidden','true');S.evidenceDraft=null;setDialogBackground(false);
  const trigger=S.dialogTrigger;S.dialogTrigger=null;if(trigger&&trigger.isConnected)trigger.focus();else{$('caseTitle').setAttribute('tabindex','-1');$('caseTitle').focus();}
}
async function submitEvidenceModal(){
  const draft=S.evidenceDraft;if(!draft||draft.finished||S.pendingCommand)return;
  if(draft.fileName.length>180){formError('evidenceModalError','输入超过允许长度，请缩短后重试。');return;}
  if(!draft.fileName){formError('evidenceModalError','请先选择合成文件名或使用 Synthetic 演示文件。');return;}
  formError('evidenceModalError','');
  const result=await runCommand('REGISTER_MATERIAL',{evidence_code:draft.code,file_name:draft.fileName,source:$('evidenceSource').value},{caseId:draft.caseId,revision:draft.revision});
  if(S.evidenceDraft!==draft)return;
  if(!result){formError('evidenceModalError','尚未取得已保存回执。可关闭弹窗，在页面顶部查询本次处理结果。');return;}
  for(const id of ['evidenceFile','evidenceSource','syntheticEvidenceButton'])$(id).disabled=true;
  draft.finished=true;$('evidenceSubmitButton').dataset.forbidden='true';$('evidenceSubmitButton').disabled=true;$('evidenceSubmitButton').textContent='登记已记录';
  $('evidenceCancelButton').textContent='完成并返回案件';
  $('evidenceReceipt').innerHTML=`<div class="submit-receipt"><strong>材料登记已保存</strong><p>案件 ${esc(result.receipt.case_id)} · 版本 ${esc(result.receipt.revision)}<br>已登记「${esc(draft.label)}」；仍缺 ${esc(result.case.missing_count)} 项。正文未读取、内容未核验。</p></div>`;
}
function openWithdrawModal(code){
  const material=(S.caseSnapshot&&S.caseSnapshot.materials||[]).find(item=>item.active&&item.code===code);
  if(!material||!allowed('WITHDRAW_MATERIAL'))return;
  S.dialogTrigger=document.activeElement;S.withdrawDraft={caseId:S.caseId,revision:S.caseRevision,code};
  $('withdrawEvidenceLabel').textContent=material.label;$('withdrawCaseContext').textContent=`案件 ${S.caseId} · 版本 ${S.caseRevision}`;
  $('withdrawModalError').textContent='';$('withdrawModal').classList.add('on');$('withdrawModal').setAttribute('aria-hidden','false');setDialogBackground(true);$('withdrawCancelButton').focus();syncWriteButtons();applyLanguage();
}
function closeWithdrawModal(){
  if(S.commandSending)return;
  $('withdrawModal').classList.remove('on');$('withdrawModal').setAttribute('aria-hidden','true');S.withdrawDraft=null;setDialogBackground(false);
  const trigger=S.dialogTrigger;S.dialogTrigger=null;if(trigger&&trigger.isConnected)trigger.focus();else{$('caseTitle').setAttribute('tabindex','-1');$('caseTitle').focus();}
}
async function confirmEvidenceWithdrawal(){
  const draft=S.withdrawDraft;if(!draft||S.pendingCommand)return;
  const result=await runCommand('WITHDRAW_MATERIAL',{evidence_code:draft.code},{caseId:draft.caseId,revision:draft.revision});
  if(result)closeWithdrawModal();else formError('withdrawModalError','尚未取得已保存回执，请关闭弹窗后查询本次处理结果。');
}

function setDialogBackground(active){
  const app=document.querySelector('.app'),skip=document.querySelector('.skip-link');
  if(app)app.inert=active;if(skip)skip.inert=active;
}
function trapDialogFocus(event){
  if(event.key!=='Tab')return;
  const dialog=['evidenceModal','withdrawModal'].map($).find(node=>node.classList.contains('on'));
  if(!dialog)return;
  const focusable=Array.from(dialog.querySelectorAll('button,input,select,textarea,a[href],[tabindex]')).filter(node=>!node.disabled&&node.tabIndex!==-1&&!node.hidden);
  if(!focusable.length)return;
  const first=focusable[0],last=focusable[focusable.length-1];
  if(event.shiftKey&&(document.activeElement===first||!dialog.contains(document.activeElement))){event.preventDefault();last.focus();}
  else if(!event.shiftKey&&(document.activeElement===last||!dialog.contains(document.activeElement))){event.preventDefault();first.focus();}
}
