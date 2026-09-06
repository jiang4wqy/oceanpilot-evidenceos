const BASE="/api/v1/chargeback";
const WORKSPACE_BASE="/api/v1/workspace";
const ROLE=WORKSPACE_CONFIG.role;
const caseContext=createCaseContext();
const S={
  loc:window.oceanI18n.getLanguage(), currentView:'overview', section:'summary',
  cases:[], currentRuleId:null, rules:[], rulesRequestId:0, ruleDetailRequestId:0,
  ruleReturnContext:null, agentBoundCaseId:null, agentMessages:[], lastAgentTurn:null,
  agentSubmitting:false, pendingAgentTurn:null, reviewDraft:null, evidenceDraft:null,
  withdrawDraft:null, dialogTrigger:null, pendingCommand:null, commandSending:false,
  commandRecovery:null, commandProblem:null, lastReceipt:null, summaryGenerating:false,
  snapshotStale:false, loadingCase:false, navigationGeneration:0,
};
Object.defineProperties(S, {
  caseId:{get:()=>caseContext.caseId},
  caseRevision:{get:()=>caseContext.snapshot?caseContext.snapshot.revision:null},
  caseSnapshot:{get:()=>caseContext.snapshot},
  selectedCase:{get:()=>caseContext.snapshot},
  last:{get:()=>caseContext.snapshot},
  agentCase:{get:()=>S.agentBoundCaseId===S.caseId?caseContext.snapshot:null},
});
const $=id=>document.getElementById(id);
const esc=value=>String(value==null?'':value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tr=value=>window.oceanI18n.translate(value);
const REVIEW_LABEL={UNREVIEWED:'本版未复核',APPROVED:'登记复核通过',NEEDS_MORE_INFO:'待补充资料',REJECTED:'已驳回',STALE:'旧版复核已失效'};
const OWNER_LABEL={MERCHANT:'材料提交方',BUSINESS:'企业运营方',NONE:'暂无待办',HUMAN:'人工确认'};
const MATERIAL_SOURCE={SYNTHETIC_TEMPLATE:'合成演示模板',SYNTHETIC_USER_METADATA:'操作人员登记的合成元数据',UNKNOWN:'来源待确认'};
const NETWORK_LABEL={VISA:'Visa',MASTERCARD:'Mastercard',AMEX:'American Express'};
function reviewStatusLabel(value){return REVIEW_LABEL[value]||value||'本版未复核';}
function ownerLabel(value){return OWNER_LABEL[value]||value||'待确认处理方';}
function dateLabel(value){if(!value)return'未记录';const date=new Date(value);return Number.isNaN(date.getTime())?'未记录':date.toLocaleString(S.loc==='en'?'en-US':'zh-CN',{hour12:false});}
function allowed(action){return Boolean(S.caseSnapshot&&(S.caseSnapshot.allowed_actions||[]).includes(action));}
function currentActor(){return ROLE==='BUSINESS'?'synthetic-business':'synthetic-merchant';}
function safeReadStorage(key){try{return sessionStorage.getItem(key);}catch(error){return null;}}
function safeWriteStorage(key,value){try{if(value===null)sessionStorage.removeItem(key);else sessionStorage.setItem(key,value);}catch(error){void error;}}
function selectCase(caseId){
  if(caseContext.select(caseId)){
    S.agentBoundCaseId=null;S.agentMessages=[];S.lastAgentTurn=null;S.pendingAgentTurn=null;
    S.reviewDraft=null;S.snapshotStale=false;
    for(const id of ['reviewSummary','agentMessage','concernField','concernOriginal','concernProposed','concernOriginalSource','concernProposedSource','concernSummary']){const input=$(id);if(input)input.value='';}
    for(const id of ['reviewError','summaryStatus','agentTurnStatus','concernError']){const status=$(id);if(status)status.textContent='';}
    for(const id of ['reviewProposal','agentHistory']){const output=$(id);if(output)output.innerHTML='';}
  }
}
function invalidateDerivedViews(){
  S.reviewDraft=null;S.lastAgentTurn=null;
  const proposal=$('reviewProposal');if(proposal)proposal.innerHTML='';
  const output=$('agentOutput');if(output)output.innerHTML='<p class="muted">案件版本或规则依据已变化；旧版分析不再作为当前结论。</p>';
  const badge=$('agentRuntimeBadge');if(badge){badge.textContent='尚未生成输出';badge.className='pill p-mut runtime-badge';}
}
function acceptCaseSnapshot(snapshot){
  const previous=caseContext.snapshot;
  if(!caseContext.accept(snapshot))return false;
  if(previous&&(snapshot.revision!==previous.revision||snapshot.rule_fingerprint!==previous.rule_fingerprint))invalidateDerivedViews();
  S.agentBoundCaseId=snapshot.case_id;S.snapshotStale=false;
  return true;
}
function syncWriteButtons(){
  const busy=Boolean(S.pendingCommand)||S.commandSending;
  document.querySelectorAll('[data-write]').forEach(button=>{button.disabled=busy||button.dataset.forbidden==='true';});
  const actor=$('demoActor');if(actor)actor.disabled=busy;
}
function formError(id,text){const node=$(id);if(node)node.textContent=text;}
function applyLanguage(){window.oceanI18n.apply();}
