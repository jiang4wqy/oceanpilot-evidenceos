/* V2.1: one authorized conversation per case, with a separate internal scope. */
(() => {
  "use strict";
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  const list = value => Array.isArray(value) ? value : [];
  let active = null;
  const clock = value => value ? new Date(value).toLocaleString("zh-CN", {month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}) : "";
  const uuid = () => globalThis.crypto.randomUUID();
  const storage = { get(key) { try { return sessionStorage.getItem(key); } catch { return null; } }, set(key,value) { try { sessionStorage.setItem(key,value); } catch {} }, remove(key) { try { sessionStorage.removeItem(key); } catch {} } };
  const draftKey = state => `oceanpilot.v21.thread.${state.key}.${state.scope}`;
  const pendingKey = state => `oceanpilot.v21.thread.pending.${state.key}`;
  function readableAnswer(body) {
    const marker = body.indexOf("本次检索到的指南参考");
    let main = marker < 0 ? body : body.slice(0, marker).trim();
    main = main.replace(/（(?:transaction|fulfillment|comms)\.[a-z_]+）/g, "");
    main = main.replace(/尚缺以下登记材料：/g, "请补充以下材料：");
    main = main.replace(/^(- [^：\n]+)：[^\n]*登记不(?:代表|表示)[^\n]*$/gm, "$1");
    main = main.split("\n").filter(line => !line.startsWith("本案共享往来：")).filter((line, index, lines) => lines.indexOf(line) === index).join("\n");
    main = main.replace(/缺少必需材料时不能进入提交；请按本案规则来源补齐。/g, "补齐后提交给 OceanPayment 审核。");
    return `<div class="thread-message-body">${esc(main)}</div>${main !== body ? `<details class="thread-file-check"><summary>查看完整说明与参考依据</summary><div class="thread-message-body">${esc(body)}</div></details>` : ""}`;
  }
  function same(state) { return active === state && state.host.isConnected; }
  function path(state, suffix = "") { return `/cases/${encodeURIComponent(state.caseId)}/collaboration${suffix}`; }
  function notice(state, message, error = false) {
    if (!same(state)) return;
    const node = state.host.querySelector(".thread-notice");
    node.textContent = message; node.hidden = !message; node.classList.toggle("error", error);
  }
  function sender(message, participants = []) {
    const actor = message.actor || {};
    const role = message.actor_role || message.role || actor.role;
    const name = participants.find(p => p.user_id === message.actor_id)?.display_name || message.actor_display_name || message.display_name || actor.display_name || (role === "AGENT" || message.actor_type === "OCEANPILOT" || message.type === "AI_MESSAGE" ? "OceanPilot" : role === "MERCHANT" ? "商户协作人" : role ? "OceanPayment" : "系统事件");
    return {name, role, kind: role === "AGENT" || name === "OceanPilot" ? "ai" : role === "MERCHANT" ? "merchant" : "operations"};
  }
  function renderFile(state, file) {
    const evidence = list(state.c?.evidence).find(item => item.active !== false && item.object_id === (file.object_id || file.id));
    const review = list(state.c?.available_actions).find(item => item.action === "REVIEW_EVIDENCE_CONTENT");
    const check = evidence?.content_check || file.content_check;
    const canReview = evidence && review?.visible && review.enabled && list(review.choices?.evidence_id).includes(evidence.id);
    const uploader = list(state.c?.participants).find(person=>person.user_id === file.uploaded_by)?.display_name || "原上传人（当前名录未提供）";
    const statusText = check?.method === "INDEPENDENT_HUMAN_CONTENT_REVIEW" ? (check.status === "SUPPORTED" ? "人工已核验内容 · 待整包审核" : "人工确认内容不足") : ({SUPPORTED:"已解析 · 待核对材料内容",INSUFFICIENT:"内容不足 · 请查看材料反馈",NEEDS_MANUAL:"需人工核对内容"})[check?.status] || "已保存";
    const recognition = file.content_check?.recognition;
    const text = String(file.extracted_text || "").slice(0,16000).split("\n").map((line,index)=>`line:${index+1}  ${line}`).join("\n");
    return `<a class="thread-file" href="/api/v2${path(state, `/files/${encodeURIComponent(file.object_id || file.id)}`)}" target="_blank" rel="noopener"><span>▧ ${esc(file.filename || file.title || "案件材料")}</span><small>${esc(statusText)} · ${esc(clock(file.created_at))}</small></a>${check ? `<details class="thread-file-check"><summary>查看材料核查与已解析内容</summary>${recognition ? `<p>识别状态：${esc(({SUCCEEDED:"已识别 · 待人工核验",PARTIAL:"部分识别 · 请检查完整原件",FAILED:"识别未完成 · 可重试",NOT_CONFIGURED:"未配置识别模型",MANUAL_ONLY:"原件待人工核验"})[recognition.status] || recognition.status)}${recognition.model ? ` · ${esc(recognition.model)}` : ""}</p>` : ""}<p>上传者：${esc(uploader)} · ${esc(file.mime_type || "类型未提供")} · ${esc(file.size ?? "未知")} bytes</p><p>保存时 SHA-256：<code>${esc(file.sha256 || "未提供")}</code></p><p>哈希用于核对保存后的字节变化，不证明文件来源、业务事实或不可篡改；识别结果可能有误，需对照原件人工核验；不提供恶意文件扫描或真实性鉴定。</p><p>${esc(list(check.findings).map(item=>typeof item === "object" ? item.message || item.detail || JSON.stringify(item) : item).join("\n"))}</p><pre>${esc(text || "暂无可读取正文，需人工核实。")}</pre>${canReview ? `<button type="button" class="button secondary small" data-review-evidence="${esc(evidence.id)}">人工核验这份材料内容</button>` : ""}</details>` : ""}`;
  }
  function updateScope(state) {
    state.host.querySelectorAll("[data-thread-scope]").forEach(item=>item.classList.toggle("active",item.dataset.threadScope===state.scope));
    state.host.querySelector(".thread-visibility").textContent=state.scope==="SHARED"?"商户、获授权的 OP 人员与 OceanPilot 可见":"仅获授权的 OceanPayment 人员可见 · 不向商户公开";
    state.host.querySelector(".thread-heading h2").textContent=state.scope==="SHARED"?"本案共享沟通":"OP 内部讨论";
  }
  function renderData(state, data) {
    if (!same(state)) return;
    const feed = state.host.querySelector(".thread-messages");
    const nearBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 90;
    const oldTop = feed.scrollTop;
    state.messages ||= new Map();
    for (const message of list(data.messages)) state.messages.set(message.id, message);
    const messages = [...state.messages.values()].sort((a,b)=>Number(a.cursor)-Number(b.cursor));
    feed.innerHTML = messages.map(message => {
      const who = sender(message, data.participants), body = message.message || message.text || message.answer || message.content || "";
      const source = message.source === "MODEL" ? `${message.provider || "模型"} · ${message.model || "实际模型"}` : message.source === "FALLBACK" ? "降级回答 · 请核对依据" : who.kind === "ai" ? "确定性案件检查" : "";
      const readers = list(data.read_receipts).filter(receipt => receipt.actor_id !== state.session.user.id && Number(receipt.cursor) >= Number(message.cursor)).length;
      return `<article class="thread-message from-${who.kind}" data-message-id="${esc(message.id || message.message_id)}"><header><strong>${esc(who.name)}</strong><time>${esc(clock(message.created_at || message.at))}</time></header>${who.kind === "ai" ? readableAnswer(body) : `<div class="thread-message-body">${esc(body)}</div>`}${source ? `<details class="thread-source"><summary>回答信息</summary>${esc(source)}</details>` : ""}<small class="thread-read">${readers ? `已被 ${readers} 位参与者查看` : "已发布到本案"}</small>${list(message.attachments).map(file => `<a href="/api/v2${path(state, `/files/${encodeURIComponent(file.object_id || file.id)}`)}" target="_blank" rel="noopener">▧ ${esc(file.filename || file.title || "材料")}</a>`).join("")}</article>`;
    }).join("") || `<div class="thread-empty"><strong>一起处理这一笔争议</strong><p>${state.scope === "SHARED" ? "你在这里发送的消息，商户、获授权的 OceanPayment 人员与 OceanPilot 都能看到。" : "这里仅供获授权的 OceanPayment 人员讨论内部审核和策略，不向商户公开。"}</p></div>`;
    if (nearBottom || !state.loaded) feed.scrollTop = feed.scrollHeight; else feed.scrollTop = oldTop;
    const handoffs = state.host.querySelector(".thread-handoffs");
    handoffs.innerHTML = list(data.handoffs).map(item => `<div class="thread-handoff"><strong>${item.status === "RESOLVED" ? "人工跟进已解决" : item.status === "CLAIMED" || item.status === "ACKNOWLEDGED" ? "人工已接手" : "已请求人工跟进"}</strong><p>${esc(item.reason || item.summary)}</p><small>负责人：${esc(item.assignee?.display_name || item.assignee_name || list(data.participants).find(person => person.user_id === item.assignee_id)?.display_name || item.assignee_id || "等待处理团队确认")}${item.follow_up_at ? ` · 预计跟进 ${esc(clock(item.follow_up_at))}` : ""}</small>${state.session.user.role !== "MERCHANT" && !["RESOLVED", "CANCELLED"].includes(item.status) ? `<div><button class="button secondary small" data-handoff="${esc(item.id)}" data-handoff-action="${item.status === "OPEN" || item.status === "PENDING" ? "CLAIM" : "RESOLVE"}">${item.status === "OPEN" || item.status === "PENDING" ? "接手此事项" : "记录解决结果"}</button></div>` : ""}</div>`).join("");
    const files = state.host.querySelector(".thread-files-list");
    files.innerHTML = list(data.files).map(file => renderFile(state, file)).join("") || '<p class="section-note">本案还没有上传文件。</p>';
    state.loaded = true;
    state.cursor = data.cursor;
    if (data.case_revision > state.revision) state.onCaseChanged?.();
    if (data.cursor && data.cursor !== state.readCursor && document.visibilityState !== "hidden") {
      state.readCursor = data.cursor;
      state.api(path(state, "/read"), {method:"POST",body:JSON.stringify({scope:state.scope,cursor:data.cursor})}).catch(() => { if (same(state)) state.readCursor = null; });
    }
  }
  async function refresh(state = active) {
    if (!state || !same(state) || state.loading) return;
    state.loading = true;
    const scope = state.scope;
    try {
      const data = await state.api(`${path(state)}?scope=${encodeURIComponent(scope)}&after=${encodeURIComponent(state.cursor || 0)}`);
      if (same(state) && state.scope === scope) {
        renderData(state, data); if (!state.pending) notice(state, "");
        if (data.has_more) { state.loading = false; await refresh(state); }
      }
    } catch (error) { notice(state, `共享记录暂时无法读取：${error.message}。你的输入已保留。`, true); }
    finally { state.loading = false; }
  }
  async function submitMessage(state) {
    const input = state.host.querySelector(".thread-input"), ask = state.host.querySelector(".thread-ask");
    const message = input.value.trim();
    if (!message || state.busy) return;
    if (message.length > 4000) { notice(state, "消息不能超过 4000 个字符。", true); return; }
    const scope = state.scope;
    const pending = state.pending || {command_id:uuid(),scope,message,ask_agent:ask.checked};
    if (pending.scope !== scope) { notice(state, "请先回到原会话确认上一条消息结果。", true); return; }
    state.pending = pending; storage.set(pendingKey(state),JSON.stringify(pending)); state.busy = true;
    state.host.querySelector(".thread-send").disabled = true;
    notice(state, pending.ask_agent ? "正在基于本案共享材料与消息请求 OceanPilot…" : "正在发送…");
    try {
      await state.api(path(state, "/messages"), {method:"POST",body:JSON.stringify(pending),timeoutMs:60000});
      state.pending = null; storage.remove(pendingKey(state)); storage.remove(draftKey(state));
      if (same(state) && state.scope === scope) { input.value = ""; notice(state, "消息已发送，参与者将在本案看到。"); await refresh(state); }
    } catch (error) {
      if (!error.uncertain) { state.pending = null; storage.remove(pendingKey(state)); }
      notice(state, error.uncertain ? "发送结果待确认。再次点击会使用同一消息 ID 核对，不会重复创建。" : error.message, true);
    } finally { state.busy = false; if (same(state)) state.host.querySelector(".thread-send").disabled = false; }
  }
  function uploadMime(file) {
    const types = {txt:"text/plain",json:"application/json",csv:"text/csv",pdf:"application/pdf",doc:"application/msword",docx:"application/vnd.openxmlformats-officedocument.wordprocessingml.document",png:"image/png",jpg:"image/jpeg",jpeg:"image/jpeg",webp:"image/webp",gif:"image/gif",bmp:"image/bmp",tif:"image/tiff",tiff:"image/tiff"};
    return types[file.name.split(".").pop().toLowerCase()] || file.type || "application/octet-stream";
  }
  async function upload(state, form) {
    const file = form.elements.file.files[0];
    if (!file || state.uploading || !form.reportValidity()) return;
    if (file.size > 20 * 1024 * 1024) { notice(state, "请选择不超过 20 MiB 的文件。", true); return; }
    state.uploading = true; form.querySelector("button[type=submit]").disabled = true;
    try {
      const bytes = new Uint8Array(await file.arrayBuffer()); let binary = "";
      for (let offset=0;offset<bytes.length;offset+=8192) binary += String.fromCharCode(...bytes.subarray(offset,offset+8192));
      const selected = form.elements.material.selectedOptions[0];
      const payload = state.uploadPending || {command_id:uuid(),expected_revision:state.revision,code:selected.dataset.code || selected.value,title:selected.dataset.title,...(selected.dataset.evidenceId ? {evidence_id:selected.dataset.evidenceId} : {}),filename:file.name,content_base64:btoa(binary),mime_type:uploadMime(file)};
      if (state.uploadPending && (payload.filename !== file.name || payload.content_base64 !== btoa(binary) || payload.code !== (selected.dataset.code || selected.value) || (payload.evidence_id || "") !== (selected.dataset.evidenceId || ""))) throw Object.assign(new Error("上一份文件的保存结果待确认，请先使用原文件和原材料选项重试。"), {preservePending:true});
      state.uploadPending = payload;
      await state.api(path(state, "/files"), {method:"POST",body:JSON.stringify(payload),timeoutMs:60000});
      state.uploadPending = null;
      if (same(state)) { form.reset(); notice(state, "材料已保存。读取状态与人工判断会明确显示。"); await state.onCaseChanged?.(); await refresh(state); }
    } catch (error) {
      if (!error.uncertain && !error.preservePending) state.uploadPending = null;
      notice(state, error.uncertain ? "文件保存结果待确认。保留原文件并再次点击，将使用原操作 ID 核对。" : error.message, true);
      if (error.status === 409) state.onCaseChanged?.();
    }
    finally { state.uploading = false; if (same(state)) form.querySelector("button[type=submit]").disabled = false; }
  }
  function uploadChoices(checklist, c) {
    return list(checklist).filter(item => ["MERCHANT_UPLOAD", "OCR_THEN_REVIEW"].includes(item.expected_source) || (c?.view === "OPERATIONS" && item.expected_source === "SYSTEM_OF_RECORD"));
  }
  function uploadMarkup(c, checklist) {
    if (!list(c.available_actions).some(a=>a.action === "REGISTER_EVIDENCE" && a.enabled)) return '<p class="section-note">当前阶段不接受直接修改材料。请按本案任务或向负责人提出修订要求。</p>';
    const choices = uploadChoices(checklist, c);
    if (!choices.length) return '<p class="section-note">当前清单没有需要商户上传的文件。系统记录与条件材料由 OceanPayment 核对，请勿自行填写内部代码。</p>';
    return `<form class="thread-upload"><label>这份文件对应哪项材料<select name="material" required><option value="">请选择新增材料或要替换的文件</option>${choices.map(item=>{
      const existing = list(c.evidence).filter(e=>e.active !== false && e.code === item.code);
      const attrs = `data-code="${esc(item.code)}" data-title="${esc(item.label || "案件材料")}"`;
      return existing.map(e=>`<option value="replace:${esc(e.id)}" ${attrs} data-evidence-id="${esc(e.id)}">${esc(item.label || "案件材料")} · 替换 ${esc(e.filename || e.title)}（${esc(clock(e.registered_at || e.created_at))}）</option>`).join("") + `<option value="${esc(item.code)}" ${attrs}>${esc(item.label || "案件材料")} · 新增文件${existing.length ? "（保留已有文件）" : ""}</option>`;
    }).join("")}</select></label><label>选择实际文件<input type="file" name="file" required accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp,.gif,.bmp,.tif,.tiff,.txt,.csv,.json"></label><p>${c.view === "OPERATIONS" ? "系统记录项请上传明确来源的导出文件；合成样例不表示已连接真实系统。" : ""}无需填写内部代码。替换会保留旧版历史并使旧审批失效；新增不会消除旧文件的内容问题。支持 PDF、Word（DOC/DOCX）、图片（PNG/JPEG/WebP/GIF/BMP/TIFF）以及 UTF-8 文本、JSON、单行 CSV，单文件最大 20 MiB。原件保存并计算哈希；图片和扫描 PDF 使用已配置的视觉模型识别，DOCX 提取正文，旧版 DOC 需人工核验。识别失败可选择替换原材料并重传同一文件重试。识别不等于审核通过。</p><button class="button secondary" type="submit">上传并检查这份材料</button></form>`;
  }
  function mount(options) {
    const {host, c, session} = options;
    if (!host) return;
    if (!c || !session?.user?.id) {
      if (active?.timer) clearInterval(active.timer); active = null;
      host.innerHTML = '<div class="thread-empty">打开获授权的案件后，可查看本案共享沟通。</div>'; return;
    }
    const key = `${session.user.id}:${c.id}`;
    if (active?.key === key && active.host === host) {
      active.revision = c.revision; active.c = c; active.checklist = list(options.plan?.checklist);
      const canUpload = list(c.available_actions).some(a=>a.action === "REGISTER_EVIDENCE" && a.enabled);
      const checklistKey = JSON.stringify([active.checklist,c.evidence]);
      if (active.canUpload !== canUpload || active.checklistKey !== checklistKey) { active.canUpload = canUpload; active.checklistKey = checklistKey; host.querySelector(".thread-upload-host").innerHTML = uploadMarkup(c, active.checklist); }
      active.renderTools?.(); return;
    }
    if (active?.timer) clearInterval(active.timer);
    const checklist = list(options.plan?.checklist);
    const state = active = {...options,key,caseId:c.id,revision:c.revision,scope:"SHARED",loaded:false,pending:null,checklist,checklistKey:JSON.stringify([checklist,c.evidence]),canUpload:list(c.available_actions).some(a=>a.action === "REGISTER_EVIDENCE" && a.enabled)};
    try { state.pending = JSON.parse(storage.get(pendingKey(state)) || "null"); } catch { state.pending = null; }
    const merchant = session.user.role === "MERCHANT";
    if (state.pending && (!["SHARED", "OP_INTERNAL"].includes(state.pending.scope) || (merchant && state.pending.scope === "OP_INTERNAL"))) { state.pending = null; storage.remove(pendingKey(state)); }
    if (state.pending) state.scope = state.pending.scope;
    host.innerHTML = `<header class="thread-heading"><div><span class="thread-symbol">✧</span><h2>本案共享沟通</h2><p>商户 · OceanPayment · OceanPilot</p></div><span class="badge green">同一案件</span></header>${!merchant ? '<nav class="thread-scopes" aria-label="消息范围"><button class="active" data-thread-scope="SHARED">共享沟通</button><button data-thread-scope="OP_INTERNAL">OP 内部</button></nav>' : ""}<p class="thread-visibility">商户、获授权的 OP 人员与 OceanPilot 可见</p><div class="thread-handoffs"></div><div class="thread-messages" role="log" aria-label="案件消息" aria-live="polite"><div class="thread-empty">正在读取共享记录…</div></div><div class="thread-notice notice" role="status" hidden></div><form class="thread-composer"><div class="thread-prompts">${(merchant ? ["为什么需要这些材料？", "我已经补充材料，请核对", "请本案负责人协助"] : ["总结商户最新回应", "请说明当前阻断与负责人", "起草清楚的补证要求"]).map(prompt => `<button type="button" data-thread-prompt="${esc(prompt)}">${esc(prompt)}</button>`).join("")}</div><label class="sr-only" for="sharedMessage">发送本案消息</label><textarea class="thread-input" id="sharedMessage" maxlength="4000" rows="3" placeholder="向本案参与者说明情况或提问…" required></textarea><div class="thread-compose-actions"><label><input class="thread-ask" type="checkbox">请 OceanPilot 一起回答</label><button class="button primary thread-send" type="submit">发送消息</button></div></form><details class="thread-human"><summary>请人工接手一个具体问题</summary><form class="thread-handoff-form"><label>需要协助的事项<textarea name="reason" rows="2" maxlength="2000" required></textarea></label><button class="button secondary" type="submit">提交人工跟进请求</button></form></details><details class="thread-files"><summary>本案文件与材料</summary><div class="thread-files-list"></div><div class="thread-upload-host">${uploadMarkup(c, checklist)}</div></details><details class="thread-tools"><summary>OceanPilot 检查、提案与原私有历史</summary><div id="agentToolsPanel"></div></details>`;
    updateScope(state);
    host.querySelector(".thread-input").value = state.pending?.message || storage.get(draftKey(state)) || "";
    if (state.pending) { host.querySelector(".thread-ask").checked = state.pending.ask_agent; notice(state, "已恢复原范围待确认消息。再次发送将用原消息 ID 核对结果。", true); }
    host.querySelector(".thread-input").addEventListener("input",event=>storage.set(draftKey(state),event.target.value));
    host.querySelector(".thread-composer").addEventListener("submit",event=>{event.preventDefault();submitMessage(state);});
    host.addEventListener("submit",event=>{ if(event.target.matches(".thread-upload")){ event.preventDefault(); upload(state,event.target); } });
    host.querySelector(".thread-handoff-form").addEventListener("submit",async event=>{
      event.preventDefault(); const reason = event.target.elements.reason.value.trim(); if (!reason) return;
      const button=event.target.querySelector("button");button.disabled=true;
      try {
        state.handoffPending ||= {command_id:uuid(),scope:state.scope,reason};
        await state.api(path(state,"/handoffs"),{method:"POST",body:JSON.stringify(state.handoffPending)});
        state.handoffPending=null;if(same(state)){event.target.reset();await refresh(state);}
      }
      catch(error){if(!error.uncertain)state.handoffPending=null;notice(state,error.uncertain?"人工请求结果待确认，再次点击将核对原请求。":error.message,true);}finally{button.disabled=false;}
    });
    host.addEventListener("click", async event=>{
      const button=event.target.closest("button");if(!button)return;
      if(button.dataset.threadPrompt){host.querySelector(".thread-input").value=button.dataset.threadPrompt;storage.set(draftKey(state),button.dataset.threadPrompt);host.querySelector(".thread-ask").checked=true;host.querySelector(".thread-input").focus();}
      if(button.dataset.threadScope && button.dataset.threadScope !== state.scope){
        if(state.busy || state.pending){notice(state,"请先确认当前消息的发送结果。",true);return;}
        state.drafts ||= {};state.drafts[state.scope]=host.querySelector(".thread-input").value;storage.set(draftKey(state),host.querySelector(".thread-input").value);
        state.scope=button.dataset.threadScope;state.loaded=false;state.readCursor=null;state.cursor=0;state.messages=new Map();
        host.querySelector(".thread-input").value=state.drafts[state.scope]||storage.get(draftKey(state))||"";
        host.querySelector(".thread-messages").innerHTML='<div class="thread-empty">正在读取所选范围…</div>';
        host.querySelector(".thread-handoffs").innerHTML="";
        updateScope(state);
        state.loading=false;await refresh(state);
      }
      if(button.dataset.reviewEvidence){ globalThis.OceanV2?.openDialog("REVIEW_EVIDENCE_CONTENT",{evidence_id:button.dataset.reviewEvidence}); return; }
      if(button.dataset.handoff){
        const form=host.querySelector(".thread-handoff-form"),reason=form.elements.reason.value.trim();
        if(!reason){host.querySelector(".thread-human").open=true;form.elements.reason.focus();notice(state,"请填写接手或解决情况，再确认此事项。",true);return;}
        button.disabled=true;
        try{
          state.handoffActionPending ||= {id:button.dataset.handoff,body:{command_id:uuid(),action:button.dataset.handoffAction,reason}};
          if(state.handoffActionPending.id!==button.dataset.handoff)throw new Error("请先核对上一项人工任务操作的结果。");
          await state.api(path(state,`/handoffs/${encodeURIComponent(state.handoffActionPending.id)}`),{method:"POST",body:JSON.stringify(state.handoffActionPending.body)});
          state.handoffActionPending=null;await refresh(state);
        }catch(error){if(!error.uncertain)state.handoffActionPending=null;notice(state,error.message,true);button.disabled=false;}
      }
    });
    state.renderTools?.(); refresh(state);
    if (!globalThis.OCEAN_V2_NO_BOOT) state.timer=setInterval(()=>{if(document.visibilityState!=="hidden")refresh(state);},4000);
  }
  globalThis.OceanV21Collaboration={mount,refresh,openFiles(data={}) {
    if(!active)return;const details=active.host.querySelector(".thread-files");details.open=true;details.scrollIntoView({block:"center",behavior:"smooth"});
    const form=details.querySelector(".thread-upload");if(form){if(data.code){
      const matches=[...form.elements.material.options].filter(o=>o.dataset.code===data.code && o.dataset.evidenceId);
      form.elements.material.value=data.evidence_id ? `replace:${data.evidence_id}` : matches.length===1 ? matches[0].value : matches.length ? "" : data.code;
    }form.elements.material.focus();}
  }};
})();
