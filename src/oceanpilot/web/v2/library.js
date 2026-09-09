/* Reference catalogue UI. It never creates or advances a business case. */
(() => {
  "use strict";
  const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  const array = (value) => Array.isArray(value) ? value : value == null ? [] : [value];
  const describe = (value) => typeof value === "object" && value !== null ? JSON.stringify(value) : String(value ?? "未提供");
  const labels = {
    SOURCE_EXPLICIT: "原文示例", RULE_DERIVED: "规则衍生", SYNTHETIC_DEMO: "合成演练",
    VERIFIED_EXTRACTED: "已核对提取来源", NEEDS_CONFIRMATION: "待人工核验", CONFLICTING_SOURCES: "来源存在冲突",
    SYSTEM_OF_RECORD: "交易系统记录", CONDITIONAL: "视渠道接入情况", OCR_THEN_REVIEW: "文档提取后人工复核", MERCHANT_UPLOAD: "由商户提供",
    required: "必需", optional: "可选", REQUIRED: "必需", OPTIONAL: "可选",
    transaction_id: "交易编号", order_id: "订单编号", transaction_time: "交易时间", amount: "交易金额", currency: "币种",
    product_or_service: "商品或服务", payment_channel: "支付渠道", authentication_method: "认证方式", delivery_or_service_status: "履约状态",
    refund_status: "退款状态", customer_contact_status: "客户沟通状态", dispute_received_at: "收到争议时间", response_deadline: "回应截止时间",
    merchant_position: "商户立场", issuer_notice: "上游通知", initial_case_status: "初始案件状态", should_accept_or_contest: "接受或抗辩决定",
  };
  const label = (value) => labels[value] || describe(value);
  const idOf = (entry) => entry?.template_id || entry?.case_template_id || entry?.id || "";
  const seedOf = (preview) => preview?.template || preview || {};
  const levelOf = (ref) => ref.evidence_level || "UNKNOWN";
  const statusOf = (ref) => ref.verification_status || ref.provenance?.verification_status || "NEEDS_CONFIRMATION";
  const badge = (value, type = "") => `<span class="library-badge ${escape(type || String(value).toLowerCase())}">${escape(label(value))}</span>`;
  const row = (title, value) => `<div class="library-fact"><dt>${escape(title)}</dt><dd>${escape(describe(value))}</dd></div>`;
  const catalogueAvailable = (ref) => ref.sandbox_template_available === true && levelOf(ref) !== "SOURCE_EXPLICIT";
  function supportedScheme(ref, preview) {
    const value = String(ref.scheme || ref.source_scheme || seedOf(preview).scheme || "").trim().toUpperCase();
    return ["VISA", "MASTERCARD", "MC"].includes(value);
  }
  function missingFacts(ref, preview) {
    const explicit = array(ref.missing_fields || ref.missing_information || preview?.missing_fields).map(describe);
    const seed = seedOf(preview);
    for (const group of [seed.transaction_facts, seed.dispute_facts]) {
      if (!group || typeof group !== "object") continue;
      for (const [key, value] of Object.entries(group))
        if (value == null || value === "" || /NOT_STATED|INSUFFICIENT_INFORMATION/i.test(String(value))) explicit.push(label(key));
    }
    return [...new Set(explicit)];
  }
  function citationMarkup(ref) {
    const citations = array(ref.citations);
    const locators = array(ref.source_locators || ref.source_locations);
    const sources = array(ref.source_ids);
    const versions = array(ref.rule_versions || ref.provenance?.rule_version);
    const items = citations.length ? citations : sources.map((source, i) => ({ source_id: source, source_locator: locators[i], rule_version: versions[i] }));
    const locatorLink = (value) => /^https?:\/\//i.test(String(value || "")) ? `<a href="${escape(value)}" target="_blank" rel="noopener noreferrer">${escape(value)} ↗</a>` : `<span>${escape(value || "定位未提供")}</span>`;
    return `${items.map((item) => {
      if (typeof item !== "object" || item === null) return `<div class="library-citation">${escape(item)}</div>`;
      const locations = array(item.source_locator || item.locator || item.location || item.page || item.source_location || item.locators);
      return `<div class="library-citation"><strong>${escape(item.source_id || item.id || "参考来源")}${item.title ? ` · ${escape(item.title)}` : ""}</strong>${locations.length ? locations.map(locatorLink).join("") : locatorLink(null)}${item.file_name ? `<small>${escape(item.file_name)}</small>` : ""}${item.rule_version || item.version ? `<small>${escape(item.rule_version || item.version)}</small>` : ""}</div>`;
    }).join("") || '<p class="library-muted">接口未提供逐项引用，需回查原始资料。</p>'}${locators.length ? `<div class="library-citation-extra"><span>来源定位</span>${locators.map((item) => locatorLink(describe(item))).join("")}</div>` : ""}${versions.length ? `<div class="library-citation-extra"><span>资料版本</span>${versions.map((item) => `<small>${escape(describe(item))}</small>`).join("")}</div>` : ""}`;
  }
  function evidenceMarkup(ref, preview) {
    const seed = seedOf(preview);
    const evidence = array(ref.required_evidence?.length ? ref.required_evidence : seed.evidence_required);
    return evidence.map((item) => {
      if (typeof item !== "object" || item === null) return `<div class="library-evidence"><strong>${escape(item)}</strong></div>`;
      return `<div class="library-evidence"><div><strong>${escape(item.label || item.evidence_name_cn || item.title || item.code || item.evidence_type || "证据参考")}</strong>${item.critical ? '<span class="library-badge needs_confirmation">关键</span>' : ""}${item.required_or_optional ? badge(item.required_or_optional, "neutral") : ""}</div><p>${escape(item.why || item.why_needed || item.description || "请根据具体案件核对适用要求。")}</p>${item.expected_fields ? `<small>关注字段：${escape(item.expected_fields)}</small>` : ""}${item.expected_source ? `<small>参考来源方式：${escape(label(item.expected_source))}</small>` : ""}${item.rule_reference ? `<small>依据：${escape(item.rule_reference)}</small>` : ""}</div>`;
    }).join("") || '<p class="library-muted">此条目未提供结构化证据清单。</p>';
  }
  function deadlineMarkup(policy) {
    if (!policy) return '<p class="library-muted">资料未提供可直接使用的案件截止时间。演练创建时仍需核对时间字段。</p>';
    if (typeof policy !== "object") return `<p class="library-body-copy">${escape(policy)}</p>`;
    return `<dl>${Object.entries(policy).map(([key, value]) => row(label(key), value)).join("")}</dl>`;
  }
  let currentMount = null;
  async function mount({ api, openTemplate, onCaseOpen } = {}) {
    const host = document.getElementById("libraryView");
    if (!host) throw new Error("案例库容器尚未准备好。");
    if (typeof api !== "function") throw new Error("案例库读取接口尚未提供。");
    currentMount?.destroy();
    let alive = true;
    const state = { references: [], templates: new Map(), manifest: {}, search: "", scheme: "ALL", level: "ALL", selected: "", detail: null, detailError: "", detailLoading: false, request: 0, templateBusy: false };
    const isCurrent = () => alive && currentMount?.host === host;
    const renderNotice = (message) => `<div class="library-load-error" role="alert"><strong>案例库暂时无法读取</strong><p>${escape(message)}</p><button class="button secondary" data-library-retry>重新读取</button></div>`;
    host.hidden = false;
    host.innerHTML = '<div class="library-loading" role="status">正在读取 guideline 案例目录…</div>';
    function filtered() {
      const query = state.search.trim().toLowerCase();
      return state.references.filter((ref) =>
        (state.scheme === "ALL" || String(ref.scheme || ref.source_scheme || "").toLowerCase().includes(state.scheme.toLowerCase())) &&
        (state.level === "ALL" || levelOf(ref) === state.level) &&
        (!query || [idOf(ref), ref.title, ref.summary, ref.scheme, ref.reason_code, ...array(ref.source_ids), ...array(ref.conflict_ids)].map(describe).join(" ").toLowerCase().includes(query)));
    }
    function listMarkup() {
      const entries = filtered();
      return `<div class="library-list-label"><strong>${entries.length} 条参考</strong><span>${state.search || state.scheme !== "ALL" || state.level !== "ALL" ? "已按条件筛选" : "按原始条目编号排序"}</span></div>${entries.map((ref) => `<button type="button" class="library-reference ${state.selected === idOf(ref) ? "selected" : ""}" data-library-reference="${escape(idOf(ref))}" aria-pressed="${state.selected === idOf(ref)}"><div class="library-ref-top"><span class="library-ref-id">${escape(idOf(ref))}</span>${badge(levelOf(ref))}</div><h3>${escape(ref.title || ref.title_cn || idOf(ref))}</h3><p>${escape(ref.summary || ref.scenario_one_line || "查看原文依据与适用边界。")}</p><div class="library-ref-bottom"><span>${escape(ref.scheme || ref.source_scheme || "组织未注明")} · ${escape(ref.reason_code || "原因码未注明")}</span><span class="${catalogueAvailable(ref) ? "library-available" : "library-readonly"}">${catalogueAvailable(ref) ? supportedScheme(ref) ? "包含演练模板" : "专项参考模板" : "仅供参考"} <b>→</b></span></div></button>`).join("") || '<div class="library-empty"><h3>没有符合条件的参考</h3><p>调整卡组织、资料性质或搜索内容。</p><button class="button secondary" data-library-clear>清除筛选</button></div>'}`;
    }
    function detailMarkup() {
      if (!state.selected) return '<div class="library-detail-empty"><span>▧</span><h3>选择一条参考，查看完整依据</h3><p>来源、规则衍生内容与合成演练会分别标记。参考案例不代表真实交易或生产规则。</p></div>';
      if (state.detailLoading) return '<div class="library-loading" role="status">正在读取这条参考的来源与模板…</div>';
      if (state.detailError) return `<div class="library-load-error" role="alert"><p>${escape(state.detailError)}</p><button class="button secondary" data-library-detail-retry>重试读取此参考</button></div>`;
      const ref = state.detail?.reference || state.references.find((item) => idOf(item) === state.selected) || {};
      const preview = state.detail?.template || null;
      const seed = seedOf(preview);
      const available = catalogueAvailable(ref) && preview !== null;
      const creatable = available && supportedScheme(ref, preview);
      const missing = missingFacts(ref, preview);
      const conflicts = array(ref.conflict_ids || ref.provenance?.conflict_ids);
      return `<div class="library-detail-heading"><div class="library-detail-kicker">${escape(idOf(ref))} <span>${escape(ref.scheme || ref.source_scheme || "参考资料")}</span></div><h2>${escape(ref.title || ref.title_cn || "案例参考")}</h2><div class="library-detail-badges">${badge(levelOf(ref))}${badge(statusOf(ref))}<span class="library-badge neutral">非生产规则</span></div><p>${escape(ref.summary || "")}</p></div><div class="library-template-action">${available ? `<div><strong>此条目包含演练模板</strong><p>创建前需确认交易字段、金额和时间。演练案件会保留此参考来源。</p></div>${typeof openTemplate === "function" ? `<button type="button" class="button primary" data-library-create="${escape(idOf(ref))}"${state.templateBusy || !creatable ? " disabled" : ""}>${state.templateBusy ? "正在打开确认…" : creatable ? "以此模板创建演练案件" : "当前双卡流程不建案"}</button>` : '<p class="library-scope-note">当前工作空间只读参考；演练创建由独立导演空间管理。</p>'}${!creatable ? '<p class="library-scope-note">保留为参考或专项测试。当前建案流程仅支持 Visa / Mastercard。</p>' : ""}` : `<strong>${levelOf(ref) === "SOURCE_EXPLICIT" ? "原文示例 · 仅供阅读" : "尚未提供可用演练模板"}</strong><p>${levelOf(ref) === "SOURCE_EXPLICIT" ? "保留原例语境与出处，不将它自动转换为虚构交易。" : "可查阅规则和证据参考，此条目当前不提供建案入口。"}</p>`}</div><section class="library-detail-section"><h3>来源与核验</h3><p class="library-section-note">资料性质与来源核验是两个独立维度；已核对来源不等于可直接用于生产。</p>${citationMarkup(ref)}</section><section class="library-detail-section"><h3>已知冲突与待核对项</h3>${conflicts.length ? `<div class="library-conflicts">${conflicts.map((item) => `<div>${escape(describe(item))}</div>`).join("")}</div>` : '<p class="library-muted">此条目未列出冲突编号。实际适用性仍需按案件与有效规则核对。</p>'}</section><section class="library-detail-section"><h3>未提供的案件事实</h3>${missing.length ? `<div class="library-missing-fields">${missing.map((item) => `<span>${escape(item)}</span>`).join("")}</div>` : `<p class="library-muted">${preview ? "未检测到标为 NOT_STATED 的结构化字段；创建演练时仍需核对实际输入。" : "此参考接口未提供完整交易事实，需回查原始资料；不推定金额、交易编号或截止时间。"}</p>`}</section><section class="library-detail-section"><h3>证据参考</h3><p class="library-section-note">以下为资料中的证据要求或建议，需结合本案规则确认。</p>${evidenceMarkup(ref, preview)}</section><section class="library-detail-section"><h3>时限依据</h3>${deadlineMarkup(ref.deadline_policy)}</section>${seed.dispute_facts?.recommendation_basis ? `<section class="library-detail-section"><h3>模板中的条件说明</h3><p class="library-body-copy">${escape(seed.dispute_facts.recommendation_basis)}</p><p class="library-section-note">这是资料中的条件性说明，不是本案自动接受、抗辩或提交的决定。</p></section>` : ""}`;
    }
    function renderList() {
      if (!isCurrent()) return;
      host.querySelector(".library-reference-list").innerHTML = listMarkup();
    }
    function renderDetail() {
      if (!isCurrent()) return;
      host.querySelector(".library-reference-detail").innerHTML = detailMarkup();
    }
    async function select(id, scroll = false) {
      const selected = state.references.find((ref) => idOf(ref) === id);
      if (!selected) return;
      state.selected = id;
      const referenceUrl = new URL(window.location.href);
      referenceUrl.searchParams.set("reference", id);
      window.history.replaceState(window.history.state, "", referenceUrl);
      state.detailLoading = true;
      state.detailError = "";
      state.templateBusy = false;
      const request = ++state.request;
      renderList(); renderDetail();
      if (scroll && window.innerWidth <= 1050) host.querySelector(".library-reference-detail").scrollIntoView({ behavior: "smooth", block: "start" });
      try {
        const payload = await api(`/case-library/${encodeURIComponent(id)}`);
        if (!isCurrent() || request !== state.request) return;
        if (idOf(payload.reference) !== id) throw new Error("返回的参考编号不匹配，请重新读取。");
        state.detail = payload;
      } catch (error) {
        if (!isCurrent() || request !== state.request) return;
        state.detailError = error.message || "无法读取这条参考。";
      } finally {
        if (isCurrent() && request === state.request) { state.detailLoading = false; renderDetail(); }
      }
    }
    async function load() {
      try {
        const payload = await api("/case-library");
        if (!isCurrent()) return;
        state.references = array(payload.references).filter((ref) => ref && typeof ref === "object" && idOf(ref)).sort((a, b) => idOf(a).localeCompare(idOf(b), "en", { numeric: true }));
        state.templates = new Map(array(payload.templates).map((item) => [idOf(item), item]));
        state.manifest = payload.manifest || {};
        const available = state.references.filter(catalogueAvailable).length;
        const explicit = state.references.filter((ref) => levelOf(ref) === "SOURCE_EXPLICIT").length;
        const supported = state.references.filter((ref) => catalogueAvailable(ref) && supportedScheme(ref)).length;
        const sourceName = state.manifest.name || state.manifest.title || "GitHub guideline 提纯资料";
        host.innerHTML = `<div class="library-intro"><div><span class="library-eyebrow">GUIDELINE REFERENCE LIBRARY</span><h2>Visa / Mastercard 案例库</h2><p>从 GitHub 中的 guideline 文件提纯，按案件问题查找规则、证据和出处。</p></div><a class="button secondary" href="/v2/operations">返回争议运营</a></div><div class="library-stats"><div><strong>${state.references.length}</strong><span>条案例参考</span><small>按实际目录计数</small></div><div><strong>${available}</strong><span>个演练模板</span><small>${supported} 个支持当前双卡建案</small></div><div><strong>${explicit}</strong><span>条原文示例</span><small>保留出处，仅供阅读</small></div></div><div class="library-boundary"><span>资料库 · 非交易列表</span><p>这些条目不是已发生的商户争议；演练案件使用合成输入，参考内容不能直接作为生产规则。</p></div><div class="library-toolbar"><label class="library-search"><span>⌕</span><input type="search" data-library-search placeholder="搜索标题、原因码、来源或案例编号" aria-label="搜索案例参考"></label><label>卡组织<select data-library-scheme aria-label="按卡组织筛选"><option value="ALL">全部卡组织</option><option value="Visa">Visa</option><option value="Mastercard">Mastercard</option></select></label><label>资料性质<select data-library-level aria-label="按资料性质筛选"><option value="ALL">全部资料性质</option><option value="SOURCE_EXPLICIT">原文示例</option><option value="RULE_DERIVED">规则衍生</option><option value="SYNTHETIC_DEMO">合成演练</option></select></label></div><div class="library-workspace"><div class="library-reference-list" aria-label="案例参考目录">${listMarkup()}</div><article class="library-reference-detail" aria-label="参考详情" aria-live="polite">${detailMarkup()}</article></div><div class="library-source-footer">${escape(describe(sourceName))}${state.manifest.version || state.manifest.schema_version ? ` · ${escape(describe(state.manifest.version || state.manifest.schema_version))}` : ""}<span>来源核验、冲突与演练边界随条目展示</span></div>`;
        const initialReference = new URLSearchParams(window.location.search).get("reference");
        if (initialReference && state.references.some((ref) => idOf(ref) === initialReference)) await select(initialReference, true);
      } catch (error) {
        if (isCurrent()) host.innerHTML = renderNotice(error.message || "请稍后重试。");
      }
    }
    function input(event) {
      const target = event.target;
      if (target.matches("[data-library-search]")) { state.search = target.value; renderList(); }
      if (target.matches("[data-library-scheme]")) { state.scheme = target.value; renderList(); }
      if (target.matches("[data-library-level]")) { state.level = target.value; renderList(); }
    }
    async function click(event) {
      const target = event.target.closest("button");
      if (!target || !host.contains(target)) return;
      if (target.hasAttribute("data-library-retry")) return load();
      if (target.hasAttribute("data-library-detail-retry")) return select(state.selected);
      if (target.hasAttribute("data-library-reference")) return select(target.dataset.libraryReference, true);
      if (target.hasAttribute("data-library-clear")) {
        state.search = ""; state.scheme = "ALL"; state.level = "ALL";
        host.querySelector("[data-library-search]").value = "";
        host.querySelector("[data-library-scheme]").value = "ALL";
        host.querySelector("[data-library-level]").value = "ALL";
        renderList(); return;
      }
      if (target.hasAttribute("data-library-create")) {
        const ref = state.detail?.reference;
        if (!catalogueAvailable(ref || {}) || !state.detail?.template || !supportedScheme(ref, state.detail.template) || typeof openTemplate !== "function" || state.templateBusy) return;
        const selected = state.selected;
        if (target.dataset.libraryCreate !== selected || idOf(ref) !== selected) return;
        state.templateBusy = true; renderDetail();
        try { await openTemplate(selected); }
        catch (error) {
          if (isCurrent() && selected === state.selected) {
            const errorNode = document.createElement("div"); errorNode.className = "library-load-error"; errorNode.setAttribute("role", "alert"); errorNode.textContent = error.message || "暂时无法打开演练确认。";
            host.querySelector(".library-reference-detail").prepend(errorNode);
          }
        } finally {
          if (isCurrent() && selected === state.selected) { state.templateBusy = false; const button = host.querySelector("[data-library-create]"); if (button) { button.disabled = false; button.textContent = "以此模板创建演练案件"; } }
        }
      }
    }
    const controller = { host, destroy() { alive = false; state.request++; host.removeEventListener("click", click); host.removeEventListener("input", input); host.removeEventListener("change", input); } };
    currentMount = controller;
    host.addEventListener("click", click);
    host.addEventListener("input", input);
    host.addEventListener("change", input);
    await load();
    return controller;
  }
  window.OceanV2Library = Object.freeze({ mount });
})();
