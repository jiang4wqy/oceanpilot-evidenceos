function demoHeaders(actor=currentActor()){
  return {'Content-Type':'application/json','X-Demo-Role':ROLE,'X-Demo-Actor':actor};
}
async function requestJson(base,method,path,body,options={}){
  const init={method,headers:demoHeaders(options.actor)};
  if(body!==undefined)init.body=JSON.stringify(body);
  return OceanRequest.json(base+path,init,options.timeoutMs||45000);
}
const api=(method,path,body)=>requestJson(BASE,method,path,body);
const workspaceApi=(method,path,body,options)=>requestJson(WORKSPACE_BASE,method,path,body,options);
function persistPendingCommand(){
  safeWriteStorage(`oceanpilot.pending.${ROLE}`,S.pendingCommand?JSON.stringify(S.pendingCommand):null);
}
function commandProblemText(result){
  const data=result&&result.data||{};
  return data.detail||data.message||(result&&result.timedOut?'请求超时，处理结果尚未确认。':'请求未完成，处理结果尚未确认。');
}
function renderCommandNotice(){
  const box=$('commandNotice');
  if(!S.pendingCommand&&!S.lastReceipt&&!S.commandProblem){box.hidden=true;return;}
  box.hidden=false;box.className='command-notice';
  if(S.pendingCommand){
    const pending=S.pendingCommand;
    box.classList.add('error');
    let message=S.commandSending?'正在等待后端处理并保存回执…':'处理结果尚未确认。先查询同一命令的已保存回执，不创建另一条命令。';
    if(S.commandRecovery==='UNKNOWN')message='尚无已提交回执；原操作可能仍在处理中。可继续查询，或使用同一命令编号重试。';
    if(S.commandRecovery==='PENDING')message='后端仍在处理此命令，请稍后查询原回执。';
    box.innerHTML=`<strong>${esc(message)}</strong><div class="helper">命令 <code>${esc(pending.payload.command_id)}</code>${pending.payload.case_id?` · 案件 ${esc(pending.payload.case_id)} · 版本 ${esc(pending.payload.expected_revision)}`:''}</div>${S.commandProblem?`<p>${esc(S.commandProblem)}</p>`:''}${S.commandSending?'':`<div class="actions"><button class="tbtn" onclick="checkPendingCommand()">查询原回执</button>${S.commandRecovery==='UNKNOWN'?'<button class="tbtn" onclick="retryPendingCommand()">使用同一命令重试</button>':''}${pending.definitiveError?'<button class="tbtn" onclick="dismissRejectedCommand()">关闭本次尝试并修改输入</button>':''}</div>`}`;
  }else if(S.commandProblem){
    box.classList.add('error');box.innerHTML=`<strong>${esc(S.commandProblem)}</strong><div class="actions"><button class="tbtn" onclick="clearCommandNotice()">关闭提示</button>${S.caseId?'<button class="tbtn" onclick="refreshCase()">刷新案件</button>':''}</div>`;
  }else{
    const receipt=S.lastReceipt;
    box.innerHTML=`<strong>操作已记录 · ${esc(receipt.result||'APPLIED')}</strong><div>案件 ${esc(receipt.case_id)} · 版本 ${esc(receipt.revision)} · ${esc(dateLabel(receipt.applied_at))}</div><div class="helper">审计 ${esc(receipt.audit_event_id)} · 命令 <code>${esc(receipt.command_id)}</code></div><button class="tbtn" onclick="openStoredCase('${esc(receipt.case_id)}')">打开回执案件</button>`;
  }
  syncWriteButtons();applyLanguage();
}
function clearCommandNotice(){S.commandProblem=null;S.lastReceipt=null;renderCommandNotice();}
async function finishCommand(result){
  const pending=S.pendingCommand;
  if(!pending||!result.receipt||result.receipt.command_id!==pending.payload.command_id)return false;
  S.lastReceipt=result.receipt;S.pendingCommand=null;S.commandSending=false;S.commandRecovery=null;S.commandProblem=null;
  persistPendingCommand();
  const snapshot=result.case;
  if(snapshot&&pending.openResult&&pending.navigationGeneration===S.navigationGeneration&&caseContext.isCurrent(pending.context,false)){
    selectCase(snapshot.case_id);acceptCaseSnapshot(snapshot);renderStoredDiagnosis(snapshot);showView('workspace');
  }else if(snapshot&&snapshot.case_id===S.caseId&&acceptCaseSnapshot(snapshot))renderStoredDiagnosis(snapshot);
  renderCommandNotice();syncWriteButtons();
  await loadCases();
  return true;
}
async function sendPendingCommand(){
  const pending=S.pendingCommand;if(!pending||S.commandSending)return null;
  S.commandSending=true;S.commandProblem=null;renderCommandNotice();syncWriteButtons();
  const result=await workspaceApi('POST','/commands',pending.payload,{actor:pending.actor});
  if(result.ok&&(result.data.status==='APPLIED'||result.data.status==='REPLAYED')){
    await finishCommand(result.data);return result.data;
  }
  S.commandSending=false;S.commandProblem=commandProblemText(result);
  pending.definitiveError=result.status>=400&&result.status<500;
  persistPendingCommand();
  return checkPendingCommand();
}
async function runCommand(action,data={},options={}){
  if(S.pendingCommand){renderCommandNotice();return null;}
  const actor=currentActor();
  if(!actor){S.commandProblem='请填写演示操作者，再确认本次操作。';renderCommandNotice();$('demoActor').focus();return null;}
  const create=action==='CREATE_CASE'||action==='COPY_SAMPLE';
  const payload={command_id:crypto.randomUUID(),action,data,confirmed:true};
  if(!create){payload.case_id=options.caseId||S.caseId;payload.expected_revision=options.revision??S.caseRevision;}
  S.pendingCommand={payload,actor,openResult:create,navigationGeneration:S.navigationGeneration,context:caseContext.capture(),createdAt:new Date().toISOString()};
  S.commandRecovery=null;persistPendingCommand();
  return sendPendingCommand();
}
async function checkPendingCommand(){
  const pending=S.pendingCommand;if(!pending||S.commandSending)return null;
  S.commandSending=true;renderCommandNotice();
  const result=await workspaceApi('GET',`/commands/${encodeURIComponent(pending.payload.command_id)}`,undefined,{actor:pending.actor,timeoutMs:15000});
  S.commandSending=false;
  if(result.ok&&(result.data.status==='APPLIED'||result.data.status==='REPLAYED')){
    await finishCommand(result.data);return result.data;
  }
  S.commandRecovery=result.ok?result.data.status:'UNAVAILABLE';
  if(!result.ok)S.commandProblem='暂时无法查询原回执。请保持同一命令编号，恢复连接后再次查询。';
  renderCommandNotice();syncWriteButtons();return null;
}
async function retryPendingCommand(){
  if(!S.pendingCommand||S.commandSending)return;
  // Query immediately before a retry; UNKNOWN is not cancellation of the first request.
  await checkPendingCommand();
  if(S.pendingCommand&&S.commandRecovery==='UNKNOWN')await sendPendingCommand();
}
function dismissRejectedCommand(){
  if(!S.pendingCommand||!S.pendingCommand.definitiveError||S.commandRecovery!=='UNKNOWN')return;
  S.pendingCommand=null;S.commandSending=false;S.commandRecovery=null;persistPendingCommand();
  S.commandProblem='后端已拒绝本次请求且未查到已提交回执。输入已保留，请检查当前版本及填写内容后重新确认。';
  renderCommandNotice();syncWriteButtons();
}
