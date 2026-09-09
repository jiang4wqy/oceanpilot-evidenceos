/* Review immutable source events using the server's current field contract. */
(() => {
  "use strict";
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  const names = {
    FORMAL_DISPUTE:"正式争议", ALERT:"预警", INQUIRY:"查询", WITHDRAWAL:"撤回", CORRECTION:"更正",
    PROCESSED:"已处理", RECORDED:"已记录", QUARANTINED:"待核对", RECEIVED:"已接收",
    UNKNOWN:"尚未确认", WON:"支持抗辩", LOST:"不支持抗辩", PARTIAL:"部分支持",
    ACCEPTED_RESPONSIBILITY:"接受责任", WITHDRAWN:"已撤回", OTHER:"其他，待核验映射",
    TRANSACTION_NOT_REGISTERED:"未找到已登记的对应交易",
    TRANSACTION_FACTS_MISMATCH:"上游事件与已登记交易不一致",
    CASE_ASSOCIATION_REQUIRES_VERIFICATION:"需要人工核对案件关联",
    AUTHORIZED_REOPEN_REQUIRED:"该案件需授权重开后才能继续", EVENT_TIMES_INVALID:"事件时间需要核对"
  };
  let state;
  const form = () => state.dialog.querySelector("form");
  const submitButton = () => state.dialog.querySelector(".intake-submit");
  const schema = () => state.schemas?.[state.retry ? "retry" : "event"];
  function notice(text, error = false) {
    const node = state.dialog.querySelector(".intake-notice");
    node.textContent = text; node.hidden = !text; node.classList.toggle("error", error);
  }
  function field(name, title, type = null) {
    const spec = schema()?.fields?.[name];
    if (!spec) throw new Error("表单字段尚未完整加载，请重新获取后继续。");
    let attrs = ` name="${esc(name)}"${spec.required ? " required" : ""}`;
    for (const [source, target] of [["minLength","minlength"],["maxLength","maxlength"],["pattern","pattern"]]) {
      if (spec[source] != null) attrs += ` ${target}="${esc(spec[source])}"`;
    }
    const kind = type || (spec.type === "integer" ? "number" : "text");
    if (kind === "number") {
      attrs += ' step="1"';
      if (spec.minimum != null) attrs += ` min="${esc(spec.minimum)}"`;
      else if (spec.exclusiveMinimum != null) attrs += ` min="${esc(spec.exclusiveMinimum + 1)}"`;
      attrs += ` max="${esc(Math.min(spec.maximum ?? Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER))}"`;
    }
    const label = `${esc(title)}${spec.required ? "" : "（可选）"}`;
    if (spec.type === "boolean") return `<label class="form-field checkbox"><input type="checkbox"${attrs}>${esc(title)}</label>`;
    const input = spec.enum ? `<select${attrs}><option value="">请选择</option>${spec.enum.map(value => `<option value="${esc(value)}">${esc(names[value] || value)}</option>`).join("")}</select>`
      : kind === "textarea" ? `<textarea${attrs}></textarea>` : `<input type="${kind}"${attrs}>`;
    return `<label class="form-field"><span data-field-title="${esc(title)}">${label}</span>${input}</label>`;
  }
  function updateRequirements() {
    if (state.pending) return;
    for (const [name, spec] of Object.entries(schema()?.fields || {})) {
      const input = form().elements.namedItem(name);
      if (!input) continue;
      const matches = ([key, value]) => {
        const control = form().elements.namedItem(key);
        return (control?.type === "checkbox" ? control.checked : control?.value) === value;
      };
      const all = Object.entries(spec.required_when_all || {});
      const conditional = Object.entries(spec.required_when || {}).some(matches) || all.length > 0 && all.every(matches);
      input.required = Boolean(spec.required || conditional);
      input.setCustomValidity("");
      if (input.required && input.type !== "checkbox" && !input.value.trim()) input.setCustomValidity("请填写此项。");
      const note = input.closest("label")?.querySelector("span");
      if (note && (spec.required_when || spec.required_when_all)) note.textContent = `${note.dataset.fieldTitle}（${conditional ? "当前事件必填" : "可选"}）`;
    }
  }
  function freezeFields(frozen) {
    state.dialog.querySelectorAll(".intake-fields input, .intake-fields select, .intake-fields textarea").forEach(input => { input.disabled = frozen; });
  }
  function renderEvents() {
    if (!state.host) return;
    state.host.innerHTML = `<details class="intake-events"><summary>上游事件与待核对事项 <span>${state.events.length} 条已授权记录</span></summary><p>正式争议经交易关联核验后才可立案。预警与查询保留事件记录；需要核对的事件会显示原因。</p>${state.events.slice().reverse().map(event => `<article class="intake-event"><div><strong>${esc(names[event.event_type || event.envelope?.event_type] || event.event_type || "上游事件")}</strong><span class="badge ${event.status === "QUARANTINED" ? "amber" : "gray"}">${esc(names[event.status] || event.status)}</span></div><p>${esc(names[event.reason] || event.reason || event.source_event_id || event.id)}</p><small>${esc(event.channel || event.envelope?.channel || "")} · ${esc(event.id)}</small><div>${event.case_id ? `<a class="button secondary small" href="/v2/operations/cases/${encodeURIComponent(event.case_id)}">打开关联案件</a>` : ""}${event.status === "QUARANTINED" ? `<button class="button secondary small" data-intake-retry="${esc(event.id)}">核对原事件并重试</button>` : ""}</div><details><summary>查看原事件</summary><pre>${esc(JSON.stringify(event.envelope || event, null, 2))}</pre></details></article>`).join("") || '<div class="empty-state compact">暂无可见上游事件。</div>'}</details>`;
  }
  async function refresh() {
    if (!state) return false;
    if (state.loading) return state.loading;
    state.loading = (async () => {
      try {
        const result = await state.api("/intake/events");
        state.events = result.events || [];
        if (!result.form_schemas?.event?.fields || !result.form_schemas?.retry?.fields) throw new Error("服务器尚未提供当前表单约束。");
        state.schemas = result.form_schemas;
        renderEvents(); return true;
      } catch (error) {
        if (state.host) state.host.innerHTML = `<div class="notice error">上游事件暂时无法读取：${esc(error.message)}</div>`;
        state.loadError = error.message; return false;
      }
    })();
    try { return await state.loading; } finally { state.loading = null; }
  }
  async function open(retryId = null) {
    if (!state || state.busy || state.opening) return;
    if (state.pending) {
      state.dialog.showModal(); freezeFields(true);
      notice("上一条事件的结果尚未确认。请核对原内容，再使用原始信封重试。", true); return;
    }
    state.opening = true; state.formReady = false; state.retryId = retryId;
    const fields = state.dialog.querySelector(".intake-fields");
    state.dialog.showModal(); submitButton().disabled = true;
    state.dialog.querySelector("h2").textContent = retryId ? "核对原事件并重试" : "接收标准化上游事件";
    state.dialog.querySelector(".intake-confirm").checked = false;
    notice(""); fields.innerHTML = '<p role="status">正在读取当前表单约束…</p>';
    try {
      if (!state.schemas && !await refresh()) throw new Error(state.loadError || "表单暂时无法加载。");
      state.retry = retryId ? state.events.find(event => event.id === retryId) : null;
      if (retryId && !state.retry) throw new Error("原事件已不可见，请重新读取事件列表。");
      fields.innerHTML = state.retry
        ? `<pre>${esc(JSON.stringify(state.retry.envelope || state.retry, null, 2))}</pre>${field("reason", "本次核对或修复了什么", "textarea")}`
        : `${field("event_type", "上游事件类型")}${field("source_event_id", "来源系统事件 ID")}${field("channel", "来源渠道")}${field("merchant_id", "对应商户 ID")}${field("transaction_id", "原交易 ID")}${field("scheme", "卡组织（VISA 或 MASTERCARD）")}${field("amount_minor", "交易金额（最小货币单位）")}${field("currency", "币种（例如 USD）")}${field("reason_code", "原始原因码")}${field("received_at", "实际收到事件的时间", "datetime-local")}${field("occurred_at", "上游事件发生时间", "datetime-local")}${field("case_template_id", "指南演练模板编号，例如 CB-CASE-041")}<p class="section-note">引用已核对的模板不会生成交易事实或自动确认规则。仍须先由演示导演登记对应合成交易。</p><details class="intake-extra"><summary>已有案件关联、撤回或更正依据</summary>${field("upstream_case_id", "来源系统案件编号")}${field("target_case_id", "明确关联的 OceanPilot 案件")}${field("stage_number", "事件所属轮次")}${field("corrects_event_id", "本次更正的原事件 ID")}${field("outcome", "上游明确的业务结果")}${field("final", "上游已明确确认终局")}${field("mapped_outcome", "其他结果的候选映射")}${field("supported_minor", "已确认支持金额（最小货币单位）")}${field("liable_minor", "已确认责任金额（最小货币单位）")}${field("reason", "结果与映射说明", "textarea")}${field("basis_reference", "核实与更正依据")}${field("authorization_reference", "授权依据")}<p class="section-note">部分支持或映射为部分支持时，须填写支持金额和责任金额；两者合计应与争议金额一致。未知和其他结果仍须由风控核验，填写映射不会自动确认终局。</p></details>`;
      updateRequirements(); state.formReady = true; submitButton().disabled = false;
    } catch (error) {
      fields.innerHTML = '<button type="button" class="button secondary" data-intake-reload>重新获取表单</button>';
      notice(error.message, true);
    } finally { state.opening = false; }
  }
  function valuesFromForm() {
    const values = {};
    for (const [name, spec] of Object.entries(schema().fields)) {
      const input = form().elements.namedItem(name);
      if (!input) continue;
      if (spec.type === "boolean") { values[name] = input.checked; continue; }
      const raw = input.value.trim();
      if (!raw) continue;
      if (spec.type === "integer") {
        const number = Number(raw);
        if (!Number.isSafeInteger(number)) throw new Error("金额和轮次必须是可准确表示的整数，不能包含小数或超长数值。");
        values[name] = number;
      } else values[name] = raw;
    }
    if (!state.retry) {
      for (const key of ["occurred_at", "received_at"]) values[key] = new Date(values[key]).toISOString();
      if (values.occurred_at > values.received_at) throw new Error("事件发生时间不能晚于实际收到事件的时间。");
      if (values.event_type === "WITHDRAWAL" && values.outcome && values.outcome !== "WITHDRAWN") throw new Error("撤回事件的业务结果须留空或选择‘已撤回’，并核对上游已明确确认终局。");
      if ((values.outcome === "PARTIAL" || values.mapped_outcome === "PARTIAL") && values.supported_minor + values.liable_minor !== values.amount_minor) throw new Error("支持金额与责任金额合计须等于争议金额。");
    }
    return values;
  }
  async function submit(event) {
    event.preventDefault();
    if (state.busy || !state.formReady || !schema()) return;
    updateRequirements();
    if (!form().reportValidity()) return;
    try {
      if (!state.pending) {
        const values = valuesFromForm();
        state.pending = state.retry
          ? {endpoint:`/intake/events/${encodeURIComponent(state.retry.id)}/retry`, body:{confirmed:true, reason:values.reason}}
          : {endpoint:"/intake/events", body:{confirmed:true, event:values}};
      }
      state.busy = true; submitButton().disabled = true; freezeFields(true);
      notice("正在核对事件与交易关联…");
      const {endpoint, body} = state.pending;
      const result = await state.api(endpoint, {method:"POST", body:JSON.stringify(body)});
      state.pending = null;
      const incoming = result.event || result;
      notice(`${names[incoming.status] || incoming.status || "事件已接收"}：${names[incoming.reason] || incoming.reason || (result.case_id ? "已关联案件。" : "本事件已留存，未自动创建争议案件。")}`);
      await refresh();
      state.dialog.querySelector(".intake-confirm").checked = false;
      if (result.case_id) { state.dialog.close(); state.onCaseOpen?.(result.case_id); }
    } catch (error) {
      if (!error.uncertain) state.pending = null;
      notice(error.uncertain ? "核验结果尚未确认。再次点击将使用原始事件信封核对，不会生成新的源事件。" : error.message, true);
    } finally {
      state.busy = false; submitButton().disabled = false; freezeFields(Boolean(state.pending));
    }
  }
  function mount({host, api, onCaseOpen}) {
    if (state) return;
    const dialog = document.createElement("dialog");
    dialog.id = "intakeEventDialog"; dialog.className = "intake-event-dialog";
    dialog.setAttribute("aria-labelledby", "intakeEventTitle");
    dialog.innerHTML = '<form class="intake-form"><div class="dialog-heading"><h2 id="intakeEventTitle">接收标准化上游事件</h2><button type="button" class="icon-button intake-close" aria-label="关闭">×</button></div><p class="section-note">逐项使用已收到的上游字段。服务器将核对交易归属和数据一致性；无法匹配的事件留待核对。</p><div class="intake-fields"></div><div class="intake-notice notice" role="status" hidden></div><label class="confirmation"><input class="intake-confirm" type="checkbox" required>我已核对原始事件、商户和交易关联，确认提交核验。</label><div class="dialog-footer"><button type="button" class="button secondary intake-close">取消</button><button type="submit" class="button primary intake-submit">确认并提交核验</button></div></form>';
    document.body.append(dialog);
    state = {host, api, onCaseOpen, dialog, busy:false, opening:false, pending:null, schemas:null, events:[]};
    dialog.querySelectorAll(".intake-close").forEach(button => button.addEventListener("click", () => { if (!state.busy) dialog.close(); }));
    dialog.addEventListener("cancel", event => { if (state.busy) event.preventDefault(); });
    dialog.addEventListener("click", event => { if (event.target.closest("[data-intake-reload]")) { state.schemas = null; open(state.retryId); } });
    host?.addEventListener("click", event => { const button = event.target.closest("[data-intake-retry]"); if (button) open(button.dataset.intakeRetry); });
    form().addEventListener("invalid", event => { const details = event.target.closest("details"); if (details) details.open = true; }, true);
    form().addEventListener("input", updateRequirements); form().addEventListener("change", updateRequirements);
    form().addEventListener("submit", submit);
    refresh();
  }
  globalThis.OceanV21Intake = {mount, open, refresh};
})();
