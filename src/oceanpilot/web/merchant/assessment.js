function renderAssess(d){const a=d.assessment;if(!a)return;
  const pct=Math.round(parseFloat(a.evidence_readiness||a.win_likelihood||"0")*100);
  const col=pct>=60?'var(--good)':(pct>=30?'var(--warn)':'var(--crit)');
  const rev=a.requires_human?'<span class="pill p-warn">需人工复核</span>':'<span class="pill p-good">材料已齐全</span>';
  const src=SOURCE_LABEL[a.explanation_source]||"规则说明";
  const bd=a.evidence_breakdown||[];const have=bd.filter(i=>i.present).length;const cov=bd.length?Math.round(have/bd.length*100):0;
  const chk=bd.map(i=>`<div class="ei"><span class="tick ${i.present?'y':'n'}">${i.present?'✓':'•'}</span>`
    +`${esc(i.label)}${i.critical?' <span class="crit-tag">关键</span>':''}</div>`).join("");
  $('verdictBody').innerHTML=`<div class="verdict"><div><div class="vnum" style="color:${col}">${pct}%</div>`
    +`<div class="vcap">规则证据就绪度 · 非胜诉概率</div></div>`
    +`<div class="vmeta"><div class="row"><span class="pill p-acc">规则评估</span>${rev}`
    +`<span class="pill p-mut">负责团队 · ${esc(TEAM_LABEL[a.responsible_team]||a.responsible_team)}</span>`
    +`<span class="pill p-mut">说明来源 · ${src}</span></div>`
    +`<div class="cov"><div class="track"><i style="width:${cov}%"></i></div><span class="n">证据 ${have}/${bd.length}</span></div></div></div>`
    +`<div class="field-label">内部案件准备清单 · ${bd.length} 项</div><div class="helper">驱动逐项补证与 Evidence Readiness；AVS/CVV 仅为内部准备项。</div>`
    +`<div class="ev">${chk}</div>`
    +`<div class="note"><b>该分数仅表示规则要求的材料就绪程度，不代表真实胜诉概率；AI 说明不会改变材料就绪度、责任团队或人工闸门。</b></div>`
    +`<div class="field-label">卡组织规则</div><div class="helper">只有明确选择卡组织后，系统才会解析并引用具体条款；不会按原因码猜测。</div>`
    +`<div class="actions"><select id="network" aria-label="卡组织" onchange="setRuleReferenceNetwork('flow',this.value)" style="max-width:180px">`
    +`<option value="" ${S.cardNetwork===''?'selected':''}>请选择卡组织</option>`
    +`<option value="VISA" ${S.cardNetwork==='VISA'?'selected':''}>Visa</option>`
    +`<option value="MASTERCARD" ${S.cardNetwork==='MASTERCARD'?'selected':''}>Mastercard</option>`
    +`<option value="AMEX" ${S.cardNetwork==='AMEX'?'selected':''}>American Express</option></select>`
    +`<button class="tbtn" onclick="resolveCaseRuleReference('flow')">查看评估引用条款</button>`
    +`<button class="tbtn primary" onclick="doPackage()">生成申诉材料包</button>`
    +`<button class="tbtn" onclick="doAppeal(false)">验证未批准阻断</button></div>`
    +`<div id="ruleReferenceOut" class="mt" aria-live="polite"></div>`
    +`<label class="field-label" for="actorId">复核人 Actor ID</label><input id="actorId" autocomplete="off" placeholder="例如 judge_reviewer_01" aria-describedby="actorHelp">`
    +`<div class="helper" id="actorHelp">只有填写复核人并显式确认，才会进入本地 mock connector。</div>`
    +`<div class="actions"><button class="tbtn danger" id="submitAppealButton" onclick="doAppeal(true)">人工确认并模拟提交</button></div>`
    +`<div id="pkgOut" class="mt" aria-live="polite"></div><div id="appealOut" class="mt" aria-live="polite"></div>`;}
async function doPackage(){const context=caseContext.capture();const ticket=OceanRequest.begin('case-package');const network=currentCardNetwork();S.cardNetwork=network;
  if(!network){$('pkgOut').innerHTML='<span class="pill p-warn">请先明确选择卡组织</span>';return;}
  const {ok,data}=await api("GET",`/cases/${S.caseId}/package?locale=${S.loc}&card_network=${encodeURIComponent(network)}`);
  if(!caseContext.isCurrent(context)||!OceanRequest.isLatest(ticket))return;
  if(!ok){$('pkgOut').innerHTML='<span class="pill p-warn">案件未就绪</span>';return;}
  S.packaged=true;renderStages();
  $('pkgOut').innerHTML=`<div class="kv"><span class="k">材料包</span><span><b style="color:var(--ink)">${esc(data.reason_label)}</b>`
    +` · ${esc(data.card_network||"")} ${esc(data.scheme_reason_code||"")} · 完整度 ${esc(data.completeness)} `
    +`${data.ready_to_submit?'<span class="pill p-good">可提交</span>':'<span class="pill p-warn">未就绪</span>'}</span></div>`
    +`<div class="kv"><span class="k">需证明</span><span>${data.required_assertions.map(esc).join("；")||"—"}</span></div>`
    +`<div class="kv"><span class="k">卡组织打包摘要</span><span>${data.ordered_evidence.length} 项 · ${data.ordered_evidence.map(e=>esc(e.label)).join("、")||"—"}</span></div>`
    +`<div class="kv"><span class="k">依据</span><span>${esc(data.source_document||"合成默认规则")} ${esc(data.rule_version||"")} · ${esc(data.source_section||"")}</span></div>`
    +(data.rule_version_id?`<div class="kv"><span class="k">规则追溯</span><span><button class="tbtn" onclick="showRuleReference('${esc(data.rule_version_id)}',ruleReturnContext('flow'))">${esc(data.rule_version_id)}</button> · ${esc(data.verification_status||'待核验')} · ${esc(data.submission_window_basis||'INTERNAL_DEMO')} ${esc(data.submission_window_days)} 天</span></div>`:'')
    +`<div class="note">${esc(data.cover_note)}${data.rule_limitation?`<br><b>边界：</b>${esc(data.rule_limitation)}`:""}</div>`;}
async function doAppeal(approve){const context=caseContext.capture();const network=currentCardNetwork();
  const submitButton=approve?$('submitAppealButton'):null;if(approve&&S.appealed){$('appealOut').innerHTML='<div class="note"><b>本次会话已完成 mock 提交。</b> 为避免重复回执，提交按钮保持禁用。</div>';if(submitButton)submitButton.disabled=true;return;}
  const base={card_network:network};const actor=approve&&$('actorId')?$('actorId').value.trim():'';
  if(approve&&!actor){$('appealOut').innerHTML='<div class="error-state" role="alert"><strong>需要复核人 Actor ID</strong><br>未发送 mock 提交请求。</div>';return;}
  if(submitButton){submitButton.disabled=true;submitButton.textContent='正在发送至 mock connector…';}
  const payload=approve?{...base,human_approved:true,actor_id:actor}:base;
  const result=await api("POST",`/cases/${S.caseId}/appeal`,payload);const data=result.data||{};
  if(!caseContext.isCurrent(context))return;
  if(!result.ok){$('appealOut').innerHTML=`<div class="error-state" role="alert"><strong>人工闸门请求失败</strong><br>${esc(data.detail||'请检查案件与复核人信息。')}</div>`;if(submitButton){submitButton.disabled=false;submitButton.textContent='人工确认并模拟提交';}return;}
  if(data.submitted){S.appealed=true;renderStages();if(submitButton)submitButton.textContent='本次已模拟提交';}else if(submitButton){submitButton.disabled=false;submitButton.textContent='人工确认并模拟提交';}
  const b=data.submitted?'<span class="pill p-good">模拟提交成功</span>':`<span class="pill p-warn">仅生成草稿 · ${esc(data.blocked_reason||"")}</span>`;
  $('appealOut').innerHTML=`<div class="field-label">${data.submitted?'本次 mock 回执':'人工闸门结果'}</div><div class="kv"><span class="k">申诉</span><span>${b}`
    +(data.submission_id?` <code>${esc(data.submission_id)}</code>`:"")+`</span></div>`
    +(actor?`<div class="kv"><span class="k">复核人</span><span>${esc(actor)}</span></div>`:'')
    +`<div class="note" style="white-space:pre-wrap">${esc(data.draft)}</div>`;refreshAudit();refreshMetrics();}
