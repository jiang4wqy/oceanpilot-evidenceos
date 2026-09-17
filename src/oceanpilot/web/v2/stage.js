/* A projection of the authenticated V2 case. No demo state or business commands. */
(() => {
  "use strict";
  const list = value => Array.isArray(value) ? value : [];
  let renderedKey = null, connected = "正在连接案件服务…", failed = false, originalUrl = null;
  const supports = (c, plan) => c?.scheme === "VISA" && c.reason_code === "13.1" && c.channel === "MOCK" && c.merchant_decision === "CONTEST" && c.rule_snapshot?.production_eligible === false && list(plan?.checklist).length === 5 && list(plan?.checklist).filter(i => i.code !== "fulfillment.proof_of_delivery").length === 4 && list(plan?.checklist).filter(i => i.code !== "fulfillment.proof_of_delivery").every(i => i.present);
  const enabled = () => new URL(location.href).searchParams.get("stage") === "1" && /\/v2\/(merchant|operations)\/cases\//.test(location.pathname) && supports(globalThis.OceanV2?.state.current,globalThis.OceanV2?.state.plan);
  function sync(message, error = false) {
    connected = message; failed = error;
    const node = document.getElementById("stageConnection");
    if (node) { node.textContent = message; node.classList.toggle("failed", error); }
  }
  function render(target, ctx) {
    const {c, plan, surface, esc, label, money, caseOwner, actionButton, renderAudit} = ctx;
    const merchant = surface === "merchant", checklist = list(plan?.checklist);
    const missing = checklist.filter(item => !item.present);
    const evidence = list(c.evidence).filter(e => e.active !== false);
    const requirement = missing[0] || checklist.find(i => i.code === "fulfillment.proof_of_delivery");
    const item = evidence.find(e => e.code === requirement?.code);
    const check = item?.content_check || {}, automatic = check.automatic_check || check;
    const human = check.method === "INDEPENDENT_HUMAN_CONTENT_REVIEW" && check.status === "SUPPORTED";
    const insufficient = automatic.extraction_check_status === "INSUFFICIENT" || check.status === "INSUFFICIENT";
    const missingTime = list(automatic.findings).some(f => String(f).includes("delivered_at"));
    const complete = c.work_status === "OP_REVIEW";
    const sourceNotice = automatic.recognition?.method === "EXPLICIT_TEXT_FIELDS_V1" ? "确定性正文提取 · 未调用模型 · 仍须人工核验" : automatic.recognition?.notice;
    const submit = list(c.available_actions).find(a => a.action === "SUBMIT_EVIDENCE");
    const title = complete ? "材料已送达，等待 OP 人工审核" : !item ? `还差${missing.length || 1}项：${requirement?.label || "案件材料"}` : human ? "材料已核验，可以提交" : insufficient ? (missingTime ? "缺少送达时间，暂不能提交" : "材料内容不足，暂不能提交") : "提取完成，等待独立人工核验";
    const next = complete ? "OceanPayment 人工审核；未提交银行，未形成终局结果。" : human ? "回到已绑定的飞书私聊，二次确认提交材料。" : insufficient ? "请上传同一材料的修订版；原版本保留在审计记录中。" : item ? "运营人员打开原件，逐项核验交易、页码和签收事实。" : "上传签收证明，核对签收人与送达时间。";
    const fields = {transaction_id:"交易编号",currency:"币种",amount_minor:"金额（分）",tracking_number:"物流单号",delivered_at:"送达时间",recipient_confirmation:"签收确认"};
    const facts = automatic.facts || {};
    const key = `${c.id}:${c.revision}`, changed = renderedKey && renderedKey !== key;
    const auditOpen = document.getElementById("stageAudit")?.open;
    const mock = c.channel === "MOCK" && c.rule_snapshot?.production_eligible === false;
    target.innerHTML = `<section class="stage-view ${changed ? "stage-changed" : ""}">
      <header class="stage-heading"><div><p class="stage-eyebrow">OCEANPILOT / ${merchant ? "商户工作台" : "运营工作台"}</p><h1>${esc(title)}</h1></div><span class="stage-progress">${checklist.filter(i=>i.present).length}<small> / ${checklist.length} 项就绪</small></span></header>
      <div class="stage-facts"><span>案件 <b>${esc(c.id)}</b> · v${esc(c.revision)}</span><span>${esc(c.scheme)} ${esc(c.reason_code)} · ${esc(money(c.amount_minor,c.currency))}</span><span>当前负责人 <b>${esc(complete ? caseOwner(c) : human ? "商户协作人" : item && !insufficient ? "OP 风控专员" : "商户协作人")}</b></span><span>期限 <b>${esc(c.deadlines?.merchant ? new Date(c.deadlines.merchant).toLocaleString("zh-CN",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}) : "待核实")}</b></span></div>
      <div class="stage-body"><article class="stage-panel"><p class="stage-eyebrow">${merchant ? "01 / 还差什么" : "01 / 原件与版本"}</p><h2>${esc(requirement?.label || "本案证据")}</h2><p class="stage-purpose">${esc(requirement?.why || "按当前案件规则核对材料。")}</p>
      <div class="stage-materials">${checklist.map(i=>`<div><span class="stage-dot ${i.present ? "ready" : ""}">${i.present ? "✓" : "!"}</span><span>${esc(i.label)}</span><strong>${i.present ? "就绪" : item && i.code === item.code ? "待核验" : "待补充"}</strong></div>`).join("")}</div>
      ${item ? `<p class="stage-version">材料 v${esc(item.revision || 1)}${list(item.history).length ? ` ← ${list(item.history).map(h=>`v${esc(h.revision || 1)}`).join("、")} 已保留` : " · 原件已保存"}</p><button class="button secondary" data-stage-original="${esc(item.object_id)}">打开原件 · 第 1 页</button>` : ""}</article>
      <article class="stage-panel stage-main"><p class="stage-eyebrow">02 / ${complete ? "交接完成" : "检查结果"}</p><h2>${complete ? "关键决定仍由人完成" : human ? "独立人工核验已完成" : !item ? "签收证明需要回答两个问题" : insufficient ? (missingTime ? "缺少送达时间" : "存在未解决的内容缺口") : "提取内容完整 ≠ 人工审核通过"}</h2>
      ${!item ? `<div class="stage-question">谁签收了？<br>什么时候送达？</div>` : `<dl class="stage-extraction">${Object.entries(fields).filter(([k])=>Object.hasOwn(facts,k)||k==="delivered_at"||k==="recipient_confirmation").map(([k,name])=>`<div class="${facts[k] ? "" : "missing"}"><dt>${name}</dt><dd>${esc(facts[k] || "未提取到，需补充 / 核对")}</dd></div>`).join("")}</dl>`}
      <p class="stage-source">${esc(sourceNotice || "状态、清单和门禁来自确定性规则；不由语言模型决定。")}</p><div class="stage-next"><strong>下一步</strong><p>${esc(next)}</p></div>
      <div class="stage-actions">${complete ? `<span class="stage-success">✓ 已进入 OP 人工审核</span>` : human ? `<span class="stage-success">✓ 等待商户在飞书确认提交</span>` : merchant ? actionButton("REGISTER_EVIDENCE",item ? "上传修订版" : "上传签收证明",{main:true,data:{code:requirement?.code,...(item ? {evidence_id:item.id}:{}),title:requirement?.label}}) : item ? actionButton("REVIEW_EVIDENCE_CONTENT","人工核验这份材料",{main:true,data:{evidence_id:item.id}}) : `<span>等待商户上传签收证明</span>`}</div>
      ${merchant && !complete && !submit?.enabled ? `<p class="stage-blocked">提交已阻断：${insufficient ? "请先补齐原件中的缺失事实。" : "材料尚未完成核验。"}</p>` : ""}</article></div>
      <footer class="stage-footer"><span>${mock ? "合成案件 / Mock 上游" : "当前案件非合成 Mock，请勿用于舞台演示"}</span><span id="stageConnection" class="${failed ? "failed" : ""}">${esc(connected)}</span><span>结果：${esc(label(c.business_outcome))} · ${esc(label(c.finality))}</span><details id="stageAudit" ${auditOpen ? "open" : ""}><summary>来源与审计</summary><div class="stage-audit"><p>规则：${esc(c.rule_snapshot?.source_id)} / ${esc(c.rule_snapshot?.rule_version)}。提取只是建议；真实性、适用性和最终决定由人确认。</p><p>当前接手人：${esc(caseOwner(c))}。飞书连接及消息送达请以飞书实际回执为准；本页指示器仅代表网页案件同步。</p>${list(item?.history).map(h=>`<p>历史原件 v${esc(h.revision)} <button class="button secondary" data-stage-original="${esc(h.object_id)}">打开原件</button></p>`).join("")}${renderAudit(c)}</div></details></footer>
    </section>`;
    renderedKey = key;
    target.querySelectorAll("[data-stage-original]").forEach(button => button.addEventListener("click", () => showOriginal(c.id,button.dataset.stageOriginal)));
  }
  async function showOriginal(caseId, objectId) {
    let dialog = document.getElementById("stageOriginal");
    if (!dialog) {
      dialog = document.createElement("dialog"); dialog.id = "stageOriginal"; dialog.className = "stage-original";
      dialog.innerHTML = '<header><strong>原件逐页预览 · 根据保存字节渲染</strong><form method="dialog"><button class="button secondary">关闭原件</button></form></header><p role="status"></p><img alt="案件原件第 1 页"><a class="stage-download" target="_blank" rel="noopener">下载完整原件</a>';
      document.body.append(dialog);
      dialog.addEventListener("close",()=>{ dialog.querySelector("img").removeAttribute("src"); if(originalUrl) URL.revokeObjectURL(originalUrl); originalUrl=null; });
    }
    dialog.showModal(); dialog.querySelector("p").textContent = "正在读取已授权原件…";
    try {
      const source = `/api/v2/cases/${encodeURIComponent(caseId)}/collaboration/files/${encodeURIComponent(objectId)}`;
      dialog.querySelector("a").href=source;
      const response = await fetch(source+"/pages/1", {credentials:"same-origin",cache:"no-store"});
      if(!response.ok) throw new Error("原件读取失败，请核对登录与案件权限。");
      const blob = await response.blob();
      if (!dialog.open) return;
      if(originalUrl) URL.revokeObjectURL(originalUrl);
      originalUrl=URL.createObjectURL(blob); dialog.querySelector("img").src=originalUrl;
      await dialog.querySelector("img").decode();
      dialog.querySelector("p").textContent="请在原件中检查交易、金额、签收人与送达时间。";
    } catch(error) { dialog.querySelector("p").textContent=error.message; }
  }
  globalThis.OceanV2Stage = {enabled,supports,render,sync};
})();
