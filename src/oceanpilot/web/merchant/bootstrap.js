document.querySelectorAll('.nav button[data-v],.mobile-nav button').forEach(button=>button.addEventListener('click',()=>showView(button.dataset.v)));
document.querySelectorAll('[data-section]').forEach(button=>button.addEventListener('click',()=>selectCaseSection(button.dataset.section)));
$('tableSearch').addEventListener('input',()=>{renderTransactions();writeNavigation(true);});
for(const id of ['statusFilter','ownerFilter'])$(id).addEventListener('change',()=>{renderTransactions();writeNavigation(true);});
$('ruleSearch').addEventListener('keydown',event=>{if(event.key==='Enter')loadRules();});$('ruleScheme').addEventListener('change',loadRules);
$('agentMessage').addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key==='Enter'){event.preventDefault();sendAgentTurn();}});
for(const [id,close] of [['evidenceModal',closeEvidenceModal],['withdrawModal',closeWithdrawModal]]){
  $(id).addEventListener('click',event=>{if(event.target===$(id))close();});
}
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'){if($('evidenceModal').classList.contains('on'))closeEvidenceModal();if($('withdrawModal').classList.contains('on'))closeWithdrawModal();}
});
window.addEventListener('popstate',restoreNavigation);
window.addEventListener('oceanpilot:languagechange',event=>{
  S.loc=event.detail&&event.detail.language||'zh';renderTransactions();
  if(S.caseSnapshot)renderStoredDiagnosis(S.caseSnapshot);
  if(S.lastAgentTurn)renderAgentTurn(S.lastAgentTurn,false);renderCommandNotice();
});
(async()=>{
  const stored=safeReadStorage(`oceanpilot.pending.${ROLE}`);
  if(stored){try{const pending=JSON.parse(stored);if(pending.payload&&pending.payload.command_id&&pending.actor===currentActor()){pending.openResult=false;S.pendingCommand=pending;}}catch(error){safeWriteStorage(`oceanpilot.pending.${ROLE}`,null);}}
  await restoreNavigation();
  if(S.pendingCommand){renderCommandNotice();await checkPendingCommand();}
  syncWriteButtons();
})();
setInterval(()=>{if(S.currentView==='overview'&&!S.commandSending)loadCases();},5000);

function updateWorkspaceHeaderOffset(){
  const header=$('workspaceHeader');if(!header)return;
  const height=Math.ceil(header.getBoundingClientRect().height);
  document.documentElement.style.setProperty('--workspace-header-offset',`${height+16}px`);
}
if(typeof ResizeObserver==='function')new ResizeObserver(updateWorkspaceHeaderOffset).observe($('workspaceHeader'));
window.addEventListener('resize',updateWorkspaceHeaderOffset);
requestAnimationFrame(updateWorkspaceHeaderOffset);
