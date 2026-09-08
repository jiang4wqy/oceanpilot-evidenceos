/* OceanPilot V2: self-contained client. All changes go through revisioned commands. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const list = (value) => (Array.isArray(value) ? value : []);
  const text = (value) =>
    typeof value === "object" && value !== null
      ? JSON.stringify(value)
      : String(value ?? "—");
  const names = {
    OPERATOR: "OP 运营专员",
    RISK_OFFICER: "OP 风控审核员",
    SUPERVISOR: "OP 主管",
    ADMIN: "平台管理员",
    MERCHANT: "商户协作人",
    AGENT: "Agent（权限演示）",
    FORMAL_DISPUTE: "正式争议",
    REPRESENTMENT: "再请款",
    PRE_ARBITRATION: "预仲裁",
    ARBITRATION: "仲裁",
    OTHER: "其他",
    RECEIVED: "新接收",
    TRIAGED: "已分流",
    MERCHANT_ACTION_REQUIRED: "待商户响应",
    EVIDENCE_COLLECTING: "收集证据中",
    EVIDENCE_SUBMITTED: "证据已提交",
    OP_REVIEW: "待 OP 审核",
    MERCHANT_REVISION_REQUIRED: "待补充证据",
    READY_TO_SUBMIT: "待提交",
    SUBMISSION_PENDING_CONFIRMATION: "待提交确认",
    SUBMITTED: "已提交",
    WAITING_UPSTREAM: "等待上游",
    FINANCIAL_RECONCILIATION: "资金核对中",
    CLOSED: "已关闭",
    NONE: "尚未决定",
    ACCEPT: "接受责任",
    CONTEST: "提出抗辩",
    NO_RESPONSE: "商户未响应",
    AUTHORIZED_WAIVER: "授权放弃",
    UNKNOWN: "尚未确认",
    WON: "胜诉",
    LOST: "败诉",
    PARTIAL: "部分支持",
    ACCEPTED_RESPONSIBILITY: "已承担责任",
    WITHDRAWN: "已撤回",
    NOT_FINAL: "非终局",
    FINAL_CONFIRMED: "已确认终局",
    NOT_APPLICABLE: "不适用",
    PENDING: "待核对",
    PROCESSING: "处理中",
    RECONCILED: "已核对",
    DISCREPANCY: "存在差异",
    VERIFIED: "已核验（合成）",
    NEEDS_CONFIRMATION: "待人工确认",
    CONFLICTING_SOURCES: "来源冲突",
    OPEN: "待完成",
    COMPLETED: "已完成",
    DRAFT: "待最终审核",
    FROZEN: "已冻结",
    INVALIDATED: "已失效",
    PASS: "审核通过",
    REVISION: "退回补证",
    APPROVE: "批准",
    REJECT: "驳回",
    DECISION: "商户决定",
    EVIDENCE: "证据清单",
    SLA_ESCALATION: "SLA 升级",
    DEBIT: "扣款",
    CREDIT: "返还",
    REFUND: "退款",
    FEE: "费用",
    ADJUSTMENT: "调整",
    ON_TRACK: "时间窗内",
    AT_RISK: "即将到期",
    OVERDUE: "已超期",
    CONFIRMED: "已确认",
    DELIVERED: "已送达",
    MOCK_ACCEPTED: "模拟受理",
    OUTCOME: "上游结果",
    TASK_PUBLISHED: "任务发布",
    MESSAGE: "协作消息",
    APPROVED: "已批准",
    CANDIDATE: "待审核",
    PORTAL: "商户门户",
    FEISHU: "飞书适配器",
    EMAIL: "邮件",
    MOCK: "模拟",
    DISABLED: "未启用",
    SYNTHETIC_DEMO: "合成演示",
    RULE_DERIVED: "规则衍生",
    SOURCE_EXPLICIT: "明确来源",
    INTAKE: "接收上游事件",
    CONFIRM_RULE: "人工确认规则",
    PUBLISH_TASK: "发布商户任务",
    MERCHANT_DECISION: "提交商户决定",
    REGISTER_EVIDENCE: "登记证据",
    WITHDRAW_EVIDENCE: "撤回证据",
    SUBMIT_EVIDENCE: "提交证据审核",
    REVIEW: "OP 人工审核",
    BUILD_PACKAGE: "生成证据包草稿",
    APPROVE_PACKAGE: "终审并冻结证据包",
    SUBMIT: "提交至 Mock 上游",
    RECORD_OUTCOME: "登记上游结果",
    NEXT_STAGE: "进入后续阶段",
    RECORD_FINANCIAL: "登记资金事件",
    RECONCILE: "人工资金核对",
    NOTIFY_MERCHANT: "通知商户结果",
    CLOSE: "关闭案件",
    COMMENT: "发送协作消息",
    MONITOR_SLA: "执行 SLA 检查",
    KNOWLEDGE_CANDIDATE: "提取脱敏知识候选",
    APPROVE_KNOWLEDGE: "审核知识候选",
  };
  const label = (value) => names[value] || text(value);
  const rolePermissions = {
    OPERATOR: [
      "INTAKE",
      "PUBLISH_TASK",
      "MERCHANT_DECISION",
      "REGISTER_EVIDENCE",
      "WITHDRAW_EVIDENCE",
      "SUBMIT_EVIDENCE",
      "SUBMIT",
      "RECORD_OUTCOME",
      "NEXT_STAGE",
      "RECORD_FINANCIAL",
      "NOTIFY_MERCHANT",
      "COMMENT",
      "MONITOR_SLA",
      "BUILD_PACKAGE",
      "KNOWLEDGE_CANDIDATE",
    ],
    RISK_OFFICER: ["CONFIRM_RULE", "REVIEW", "COMMENT", "MONITOR_SLA"],
    SUPERVISOR: [
      "APPROVE_PACKAGE",
      "RECONCILE",
      "CLOSE",
      "COMMENT",
      "MONITOR_SLA",
    ],
    MERCHANT: [
      "MERCHANT_DECISION",
      "REGISTER_EVIDENCE",
      "WITHDRAW_EVIDENCE",
      "SUBMIT_EVIDENCE",
      "COMMENT",
    ],
    AGENT: ["BUILD_PACKAGE", "COMMENT", "MONITOR_SLA", "KNOWLEDGE_CANDIDATE"],
    ADMIN: ["APPROVE_KNOWLEDGE"],
  };
  const tabs = [
    ["overview", "概览"],
    ["tasks", "商户任务"],
    ["evidence", "证据"],
    ["agent", "Agent 建议"],
    ["collaboration", "协作"],
    ["review", "审核与提交"],
    ["outcome", "结果与资金"],
    ["audit", "审计"],
  ];
  const queueViews = [
    ["ALL", "全部案件"],
    ["URGENT", "SLA 待关注"],
    ["MERCHANT", "等待商户"],
    ["EVIDENCE", "等待证据"],
    ["REVIEW", "OP 审核"],
    ["SUBMISSION", "上游与提交"],
    ["FINANCIAL", "资金待核对"],
    ["CLOSED", "已关闭"],
  ];
  const surface = V2_CONFIG.surface;
  const S = {
    role:
      surface === "merchant"
        ? "MERCHANT"
        : surface === "governance"
          ? "ADMIN"
          : "OPERATOR",
    merchantId: "synthetic-merchant-001",
    cases: [],
    current: null,
    plan: null,
    governance: null,
    capabilities: null,
    tab: "overview",
    queue: "ALL",
    search: "",
    stage: "ALL",
    selection: 0,
    refreshEpoch: 0,
    loading: false,
    dialog: null,
    pending: null,
    busy: false,
  };
  const storage = {
    get(key) {
      try {
        return sessionStorage.getItem(key);
      } catch {
        return null;
      }
    },
    set(key, value) {
      try {
        sessionStorage.setItem(key, value);
      } catch {}
    },
    remove(key) {
      try {
        sessionStorage.removeItem(key);
      } catch {}
    },
  };
  function uuid() {
    return (
      globalThis.crypto?.randomUUID?.() ||
      `v2-${Date.now()}-${Math.random().toString(16).slice(2)}`
    );
  }
  function money(amount, currency = "USD") {
    try {
      const formatter = new Intl.NumberFormat("zh-CN", {
        style: "currency",
        currency,
      });
      const digits = formatter.resolvedOptions().maximumFractionDigits;
      return formatter.format(Number(amount || 0) / 10 ** digits);
    } catch {
      return `${currency} ${amount ?? 0}（原始最小货币单位）`;
    }
  }
  function date(value) {
    if (!value) return "尚未确认";
    const d = new Date(value);
    return Number.isNaN(d.getTime())
      ? text(value)
      : d.toLocaleString("zh-CN", {
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        });
  }
  function tone(value) {
    if (
      [
        "CLOSED",
        "RECONCILED",
        "FINAL_CONFIRMED",
        "WON",
        "PASS",
        "FROZEN",
        "COMPLETED",
        "VERIFIED",
      ].includes(value)
    )
      return "green";
    if (
      [
        "DISCREPANCY",
        "LOST",
        "CONFLICTING_SOURCES",
        "NO_RESPONSE",
        "INVALIDATED",
      ].includes(value)
    )
      return "red";
    if (
      [
        "NEEDS_CONFIRMATION",
        "MERCHANT_REVISION_REQUIRED",
        "MERCHANT_ACTION_REQUIRED",
        "PENDING",
        "OPEN",
        "DRAFT",
        "READY_TO_SUBMIT",
      ].includes(value)
    )
      return "amber";
    if (
      [
        "OP_REVIEW",
        "EVIDENCE_SUBMITTED",
        "SUBMITTED",
        "WAITING_UPSTREAM",
        "REPRESENTMENT",
      ].includes(value)
    )
      return "blue";
    return "gray";
  }
  function badge(value, custom) {
    return `<span class="badge ${tone(value)}">${esc(custom || label(value))}</span>`;
  }
  function identity() {
    return {
      role: S.role,
      actor: `synthetic-${S.role.toLowerCase().replaceAll("_", "-")}`,
      merchant_id: S.merchantId,
    };
  }
  function headers(actor = identity()) {
    return {
      "Content-Type": "application/json",
      "X-Demo-Role": actor.role,
      "X-Demo-Actor": actor.actor,
      "X-Demo-Merchant": actor.merchant_id,
    };
  }
  function permitted(action) {
    return list(
      S.capabilities?.role === S.role
        ? S.capabilities.actions
        : S.governance?.permissions?.[S.role] || rolePermissions[S.role],
    ).includes(action);
  }
  function actionButton(action, title, opts = {}) {
    if (!permitted(action)) return "";
    return `<button type="button" class="button ${opts.primary ? "primary" : "secondary"} ${opts.small ? "small" : ""}" data-action="${esc(action)}"${opts.data ? ` data-command-data="${esc(JSON.stringify(opts.data))}"` : ""}>${esc(title || label(action))}</button>`;
  }
  function roleHint(action) {
    const owners = Object.entries(S.governance?.permissions || rolePermissions)
      .filter(([, actions]) => list(actions).includes(action))
      .map(([role]) => label(role));
    return owners.length ? `由 ${owners.join(" / ")} 执行` : "请由授权人员处理";
  }
  function setNotice(message, error = false, extra = "") {
    const node = $("globalNotice");
    node.hidden = !message;
    node.className = `notice${error ? " error" : ""}`;
    node.innerHTML = esc(message) + extra;
  }
  function problemMessage(body, status) {
    const value =
      body?.detail ||
      body?.message ||
      body?.title ||
      body?.error ||
      `请求失败（${status}）`;
    if (typeof value === "string") return value;
    if (Array.isArray(value))
      return value.map((i) => i.msg || text(i)).join("；");
    return value.message || value.detail || JSON.stringify(value);
  }
  async function api(path, options = {}, actor) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(`/api/v2${path}`, {
        ...options,
        headers: headers(actor),
        signal: controller.signal,
      });
      const body = await response.json();
      if (!response.ok) {
        const error = new Error(problemMessage(body, response.status));
        error.status = response.status;
        error.body = body;
        error.uncertain = response.status >= 500;
        throw error;
      }
      return body;
    } catch (error) {
      if (error.name === "AbortError") {
        const timeout = new Error("请求超时，执行状态尚未确认");
        timeout.uncertain = true;
        throw timeout;
      }
      if (!error.status) error.uncertain = true;
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }
  function matchesQueue(c, queue) {
    const status = c.work_status;
    if (queue === "ALL") return true;
    if (queue === "URGENT")
      return (
        status !== "CLOSED" &&
        (c.sla_risk === true ||
          (c.finality !== "FINAL_CONFIRMED" &&
            c.deadlines?.merchant &&
            new Date(c.deadlines.merchant).getTime() - Date.now() < 86400000) ||
          c.merchant_decision === "NO_RESPONSE" ||
          c.rule_snapshot?.conflict_status === "NEEDS_CONFIRMATION" ||
          list(c.tasks).some(
            (t) => t.type === "SLA_ESCALATION" && t.status === "OPEN",
          ))
      );
    if (queue === "MERCHANT") return status === "MERCHANT_ACTION_REQUIRED";
    if (queue === "EVIDENCE")
      return ["EVIDENCE_COLLECTING", "MERCHANT_REVISION_REQUIRED"].includes(
        status,
      );
    if (queue === "REVIEW")
      return ["EVIDENCE_SUBMITTED", "OP_REVIEW"].includes(status);
    if (queue === "SUBMISSION")
      return [
        "READY_TO_SUBMIT",
        "SUBMISSION_PENDING_CONFIRMATION",
        "SUBMITTED",
        "WAITING_UPSTREAM",
      ].includes(status);
    if (queue === "FINANCIAL")
      return (
        status !== "CLOSED" &&
        (status === "FINANCIAL_RECONCILIATION" ||
          c.finality === "FINAL_CONFIRMED") &&
        ["PENDING", "PROCESSING", "DISCREPANCY"].includes(c.financial_status)
      );
    return status === "CLOSED";
  }
  function filteredCases() {
    return S.cases.filter(
      (c) =>
        matchesQueue(c, S.queue) &&
        (S.stage === "ALL" || c.stage === S.stage) &&
        (!S.search ||
          [
            c.id,
            c.merchant_id,
            c.reason_code,
            c.scheme,
            label(c.work_status),
            c.transaction_id,
          ]
            .join(" ")
            .toLowerCase()
            .includes(S.search.toLowerCase())),
    );
  }
  function completeness(c) {
    const required = list(c.rule_snapshot?.required_evidence);
    const active = list(c.evidence).filter((e) => e.active !== false);
    return {
      present: required.filter((code) =>
        active.some(
          (e) => e.code === (typeof code === "string" ? code : code.code),
        ),
      ).length,
      total: required.length,
    };
  }
  function renderMetrics() {
    const active = S.cases.filter((c) => c.work_status !== "CLOSED").length;
    const urgent = S.cases.filter((c) => matchesQueue(c, "URGENT")).length;
    const review = S.cases.filter((c) => matchesQueue(c, "REVIEW")).length;
    const financial = S.cases.filter((c) =>
      matchesQueue(c, "FINANCIAL"),
    ).length;
    const values =
      surface === "merchant"
        ? [
            ["待处理争议", active, "ALL", "本人所属商户的争议收件箱", "▤"],
            [
              "待响应",
              S.cases.filter((c) => matchesQueue(c, "MERCHANT")).length,
              "MERCHANT",
              "Accept / Contest 由商户确认",
              "◷",
            ],
            [
              "待补充证据",
              S.cases.filter((c) => matchesQueue(c, "EVIDENCE")).length,
              "EVIDENCE",
              "按案件规则快照准备材料",
              "▧",
            ],
            [
              "已关闭",
              S.cases.filter((c) => c.work_status === "CLOSED").length,
              "CLOSED",
              "结果与资金完成后关闭",
              "✓",
            ],
          ]
        : [
            ["处理中案件", active, "ALL", "统一案件 · 完整生命周期", "▤"],
            ["需要关注", urgent, "URGENT", "时限风险 / 规则待确认", "◷"],
            ["待 OP 审核", review, "REVIEW", "由授权风控审核员处理", "◇"],
            [
              "资金待核对",
              financial,
              "FINANCIAL",
              "终局判断与资金状态独立",
              "⇄",
            ],
          ];
    $("metrics").innerHTML = values
      .map(
        ([title, value, queue, foot, icon]) =>
          `<${surface === "governance" ? "div" : "button"} class="metric"${surface === "governance" ? "" : ` data-queue="${queue}"`}><div class="metric-label">${title}<span class="metric-icon">${icon}</span></div><div class="metric-value">${value}<small>件</small></div><div class="metric-foot ${queue === "URGENT" && value ? "attention" : ""}">${foot}</div></${surface === "governance" ? "div" : "button"}>`,
      )
      .join("");
  }
  function renderQueue() {
    const visible = filteredCases();
    $("queueTitle").textContent =
      queueViews.find((v) => v[0] === S.queue)?.[1] || "全部案件";
    $("queueCount").textContent = visible.length;
    $("queueNav").innerHTML = queueViews
      .map(
        ([key, title]) =>
          `<button class="${S.queue === key ? "active" : ""}" data-queue="${key}"><span class="queue-dot"></span>${title}<span class="count">${S.cases.filter((c) => matchesQueue(c, key)).length}</span></button>`,
      )
      .join("");
    $("caseList").innerHTML = visible.length
      ? visible
          .map((c) => {
            const r = completeness(c);
            return `<button class="case-card ${c.id === S.current?.id ? "selected" : ""}" data-case="${esc(c.id)}" aria-pressed="${c.id === S.current?.id}"><div class="case-card-top"><span class="case-id">${esc(c.id)}</span>${badge(c.work_status)}</div><h3>${esc(c.merchant_id)}</h3><div class="case-card-meta"><span>${esc(c.scheme)} · ${esc(c.reason_code)}</span><span class="case-money">${esc(money(c.amount_minor, c.currency))}</span></div><div class="case-progress"><span>${esc(label(c.stage))}</span><span>${r.total ? `证据 ${r.present}/${r.total}` : "规则待确认"} · v${esc(c.revision)}</span></div></button>`;
          })
          .join("")
      : `<div class="empty-state compact"><div class="empty-symbol">⌕</div>${S.cases.length ? "没有符合条件的案件。调整搜索或案件视图。" : "暂无案件。运营专员可接收上游事件，或加载合成演示案例。"}</div>`;
  }
  function fact(key, value) {
    return `<div class="fact-row"><span>${esc(key)}</span><span>${esc(value)}</span></div>`;
  }
  function section(title, description = "", actions = "") {
    return `<div class="section-heading"><div><h3>${esc(title)}</h3>${description ? `<p>${esc(description)}</p>` : ""}</div>${actions}</div>`;
  }
  function empty(message) {
    return `<div class="empty-state compact">${esc(message)}</div>`;
  }
  function citations(items) {
    return list(items).length
      ? `<div class="source-list">${list(items)
          .map((s) => {
            const locator = s.source_locator || s.locator || "";
            const safe = /^https?:\/\//i.test(locator);
            return `<div>↗ ${esc(s.source_id || "来源")} · ${esc(s.rule_version || s.version || "")}<br>${safe ? `<a href="${esc(locator)}" target="_blank" rel="noopener noreferrer">${esc(locator)}</a>` : esc(locator)}</div>`;
          })
          .join("")}</div>`
      : empty("暂无可引用来源。规则不明确时需要人工确认。");
  }
  function renderOverview(c, p) {
    const next = p?.next_action;
    const percent = Math.min(
      100,
      Math.max(0, Number(p?.readiness?.percent || 0)),
    );
    const deadlines = p?.deadlines || c.deadlines || {};
    const rule = c.rule_snapshot || {};
    const lifecycle = [
      "RECEIVED",
      "MERCHANT_ACTION_REQUIRED",
      "EVIDENCE_COLLECTING",
      "OP_REVIEW",
      "SUBMITTED",
      "CLOSED",
    ];
    const pos =
      c.work_status === "CLOSED"
        ? 5
        : [
              "SUBMITTED",
              "WAITING_UPSTREAM",
              "FINANCIAL_RECONCILIATION",
            ].includes(c.work_status)
          ? 4
          : ["READY_TO_SUBMIT", "OP_REVIEW", "EVIDENCE_SUBMITTED"].includes(
                c.work_status,
              )
            ? 3
            : ["EVIDENCE_COLLECTING", "MERCHANT_REVISION_REQUIRED"].includes(
                  c.work_status,
                )
              ? 2
              : c.work_status === "MERCHANT_ACTION_REQUIRED"
                ? 1
                : 0;
    return `<div class="agent-summary"><div class="agent-summary-header"><span class="agent-symbol">✧</span>案件推进建议 <span class="badge green">确定性 Agent</span></div><p>${esc(p?.summary || "正在读取案件计划。所有操作均经过权限、规则与版本校验。")}</p><div class="agent-summary-footer"><span>基于案件 v${esc(c.revision)} · 规则与证据可追溯</span>${next ? actionButton(next.action, "处理下一步 →", { small: true }) : ""}</div></div>${section("证据准备度", "登记清单完整度，不代表证据真实性或胜诉概率")}<div class="progress-row"><span>已满足 ${esc(p?.readiness?.submitted ?? completeness(c).present)} / ${esc(p?.readiness?.required ?? completeness(c).total)} 项要求</span><strong>${percent}%</strong></div><div class="progress-track"><div class="progress-fill" style="width:${percent}%"></div></div>${next ? `<div class="callout ${p?.blockers?.length ? "" : "green"}"><strong>下一步 · ${esc(label(next.action))}</strong>${esc(next.reason || "")}<br>${esc(roleHint(next.action))}</div>` : ""}<div class="two-column"><div class="info-card"><h4>规则与来源</h4>${fact("规则状态", label(rule.conflict_status || p?.rule_status || "NEEDS_CONFIRMATION"))}${fact("版本", rule.rule_version || "尚未匹配")}${fact("来源", rule.source_id || "尚未确认")}${fact("适用阶段", label(c.stage))}${actionButton("CONFIRM_RULE", "查看并确认规则", { small: true })}</div><div class="info-card"><h4>案件时间窗</h4>${fact("商户目标", date(deadlines.merchant || deadlines.merchant_deadline))}${fact("OP 内部", date(deadlines.internal || deadlines.internal_deadline))}${fact("外部截止", date(deadlines.external || deadlines.external_deadline))}${fact("时限来源", deadlines.source || "尚未确认")}</div></div><div class="info-card" style="margin-top:15px"><h4>生命周期</h4><div class="timeline-mini">${lifecycle.map((step, i) => `<div class="timeline-step ${i <= pos ? "done" : ""} ${i === pos ? "current" : ""}">${["接收分流", "商户响应", "证据收集", "人工审核", "上游与资金", "终局关闭"][i]}</div>`).join("")}</div></div>`;
  }
  function renderTasks(c) {
    return `${section("商户协作任务", "由 OP 发布；商户完成决定与证据响应", actionButton("PUBLISH_TASK", "＋ 发布任务", { small: true }))}${c.merchant_decision === "NONE" ? '<div class="callout">商户需明确选择接受责任或提出抗辩。无回复不会自动视为接受责任。</div>' : `<div class="callout green">当前商户决定：<strong>${esc(label(c.merchant_decision))}</strong></div>`}${
      list(c.tasks)
        .map(
          (t) =>
            `<div class="task-row"><span class="check-mark ${t.status === "COMPLETED" ? "done" : ""}">${t.status === "COMPLETED" ? "✓" : "○"}</span><div class="row-content"><div class="row-title">${esc(label(t.type))}${t.required ? ' <span class="badge gray">必需</span>' : ""}</div><div class="row-subtitle">${esc(t.message || "")}<br>${esc(t.id)} · ${date(t.created_at)}</div></div>${badge(t.status)}</div>`,
        )
        .join("") || empty("尚未发布商户任务。")
    }<div class="action-bar">${actionButton("MERCHANT_DECISION", "确认 Accept / Contest", { primary: true })}${actionButton("SUBMIT_EVIDENCE")}${actionButton("MONITOR_SLA")}</div>${surface !== "merchant" ? `<p class="section-note">商户的响应由商户门户完成。主管处理未响应或授权放弃时，必须记录依据。</p>` : ""}`;
  }
  function renderEvidence(c, p) {
    const checklist = list(p?.checklist);
    const evidence = list(c.evidence);
    return `${section("规则要求的证据", "登记证据引用与元数据；本版本不接收或解析文件正文", actionButton("REGISTER_EVIDENCE", "＋ 登记证据", { small: true }))}${checklist.map((item) => `<div class="evidence-row"><span class="check-mark ${item.present ? "done" : ""}">${item.present ? "✓" : "○"}</span><div class="row-content"><div class="row-title">${esc(item.label || item.code)} ${item.critical ? '<span class="badge amber">关键证据</span>' : ""}</div><div class="row-subtitle">${esc(item.why || item.code)}</div></div><div class="row-actions">${item.present ? badge("COMPLETED", "已登记") : badge("PENDING", "缺失")}${!item.present ? actionButton("REGISTER_EVIDENCE", "补充", { small: true, data: { code: item.code, title: item.label || item.code } }) : ""}</div></div>`).join("") || empty("规则清单尚未确定。请先确认规则来源。")}<div class="action-bar">${actionButton("SUBMIT_EVIDENCE", "提交证据供 OP 审核", { primary: true })}</div>${section("证据登记记录", `${evidence.filter((e) => e.active !== false).length} 项有效 · 撤回保留历史并使旧证据包失效`)}${evidence.map((e) => `<div class="evidence-row"><span class="row-icon">▧</span><div class="row-content"><div class="row-title">${esc(e.title || e.code)} ${e.active === false ? badge("INVALIDATED", "已撤回") : ""}</div><div class="row-subtitle">${esc(e.reference)}<br>${esc(label(e.source_channel || "PORTAL"))} · ${date(e.registered_at)} · ${esc(e.registered_by || "")}${e.notes ? `<br>${esc(e.notes)}` : ""}</div></div>${e.active !== false ? actionButton("WITHDRAW_EVIDENCE", "撤回", { small: true, data: { evidence_id: e.id } }) : ""}</div>`).join("") || empty("尚无证据登记记录。")}`;
  }
  function renderAgent(c, p) {
    if (!p) return empty("案件计划暂时不可用，请刷新重试。");
    return `${section("Agent 案件计划", "解释、计划、检查与升级；最终业务决定由人确认", `<span class="badge green">${esc(p.agent?.provider || "DETERMINISTIC")}</span>`)}<div class="agent-summary"><div class="agent-summary-header"><span class="agent-symbol">✧</span>案件摘要</div><p>${esc(p.summary)}</p><div class="agent-summary-footer"><span>案件 v${esc(p.revision)} · ${esc(p.agent?.model || "case-planner-v2")}</span><span>Prompt ${esc(p.agent?.prompt_version || "2026-09-08")}</span></div></div>${p.next_action ? `<div class="info-card"><h4>下一步建议 · ${esc(label(p.next_action.action))}</h4><p class="section-note">${esc(p.next_action.reason)}<br>${esc(roleHint(p.next_action.action))}</p>${actionButton(p.next_action.action, "审核建议并执行 →", { primary: true })}</div>` : ""}${list(p.blockers).length ? `<div class="callout"><strong>需要先解决的阻断</strong>${p.blockers.map((b) => `<div>• ${esc(label(b))}</div>`).join("")}</div>` : '<div class="callout green">当前计划未报告阻断。最终执行仍需通过案件引擎检查。</div>'}${section("证据检查与时限")}${fact("清单完整度", `${p.readiness?.percent || 0}%`)}${fact("缺失关键证据", list(p.missing_critical).join("、") || "未报告缺失")}${fact("SLA 风险", label(p.sla_risk || "NEEDS_CONFIRMATION"))}${fact("人工升级", p.escalation_required ? "需要" : "当前无需")}<p class="section-note">${esc(p.readiness?.boundary || "完整度来自证据登记，不包含正文核验，不是胜诉概率。")}</p>${section("引用依据")}${citations(p.source_citations)}<div class="action-bar">${actionButton("MONITOR_SLA")}${actionButton("BUILD_PACKAGE")}${actionButton("KNOWLEDGE_CANDIDATE")}</div>`;
  }
  function renderCollaboration(c) {
    return `${section("案件协作记录", "所有渠道共享 Case ID；飞书状态以平台治理实际配置为准", actionButton("COMMENT", "＋ 协作消息", { small: true }))}<div class="callout">门户消息写入案件事件。演示中的飞书卡片与提醒属于适配器边界，不代表真实飞书消息已经送达。</div>${
      list(c.collaboration)
        .map(
          (m) =>
            `<div class="message"><header><strong>${esc(m.actor || m.actor_id || m.type || "系统")}</strong>${badge(m.channel || "PORTAL")}<time>${date(m.created_at || m.timestamp || m.at)}</time></header><p>${esc(m.message || m.text || text(m))}</p>${m.delivery_status ? `<div class="row-subtitle">投递状态：${esc(m.delivery_status)}</div>` : ""}</div>`,
        )
        .join("") || empty("尚无协作事件。发布商户任务或发送一条消息开始协同。")
    }<div class="action-bar">${actionButton("COMMENT", "发送案件消息", { primary: true })}${actionButton("PUBLISH_TASK")}${actionButton("NOTIFY_MERCHANT")}</div>`;
  }
  function renderReview(c) {
    return `${section("OP 人工审核", "审核决定绑定当前案件与证据版本")}<div class="action-bar">${actionButton("REVIEW", "执行风控审核", { primary: true })}${actionButton("BUILD_PACKAGE", "生成证据包草稿")}</div>${
      list(c.reviews)
        .map(
          (r) =>
            `<div class="record-row"><span class="row-icon">◇</span><div class="row-content"><div class="row-title">${esc(label(r.decision))} · ${esc(r.reviewer || r.actor || r.reviewed_by || "")}</div><div class="row-subtitle">${esc(r.reason || "")}<br>${date(r.created_at || r.reviewed_at || r.at)} · v${esc(r.revision || r.case_revision || "—")}</div></div>${badge(r.decision)}</div>`,
        )
        .join("") || empty("尚无人工审核记录。关键证据缺失时不能通过审核。")
    }${section("证据包与最终审批", "草稿经主管确认 PII 检查后冻结；变更证据将使旧包失效")}<div class="action-bar">${actionButton("APPROVE_PACKAGE", "终审并冻结", { primary: true })}${actionButton("SUBMIT", "Mock 提交")}</div>${
      list(c.packages)
        .map(
          (pkg) =>
            `<div class="info-card" style="margin-bottom:12px"><div class="section-heading"><h3>证据包 v${esc(pkg.version)} <span class="mono">${esc(pkg.id)}</span></h3>${badge(pkg.status)}</div>${fact("证据版本", pkg.evidence_version)}${fact("证据项数", list(pkg.evidence_index).length)}${fact("PII 人工检查", pkg.pii_checked ? "已确认" : "待确认")}${fact("审核人", pkg.approved_by || "待最终审核")}${pkg.digest ? `<div class="row-subtitle mono">摘要：${esc(pkg.digest)}</div>` : ""}<details><summary class="row-subtitle">查看草稿与来源</summary><pre class="code-block">${esc(pkg.draft || "暂无草稿")}</pre>${citations(pkg.citations)}</details></div>`,
        )
        .join("") || empty("尚未生成证据包。")
    }${section("上游提交与回执", "仅 Mock 上游；传输状态与业务受理状态分别记录")}${
      list(c.submissions)
        .map(
          (sub) =>
            `<div class="info-card" style="margin-bottom:10px">${fact("提交 ID", sub.id || sub.request_id)}${fact("传输状态", sub.transport_status || sub.transport_state || sub.status)}${fact("业务受理", sub.business_status || sub.business_acceptance || sub.acceptance_status)}${fact("回执", sub.receipt_id || sub.receipt?.id || text(sub.receipt))}${fact("提交渠道", sub.channel || sub.adapter || "MOCK")}<details><summary class="row-subtitle">完整提交记录</summary><pre class="code-block">${esc(JSON.stringify(sub, null, 2))}</pre></details></div>`,
        )
        .join("") || empty("尚未提交至上游。")
    }`;
  }
  function renderOutcome(c) {
    const financial = list(c.financial_events);
    const net = financial.reduce(
      (sum, e) =>
        sum +
        Number(
          e.net_minor ??
            (["DEBIT", "FEE"].includes(e.kind)
              ? -Math.abs(Number(e.amount_minor || 0))
              : Number(e.amount_minor || 0)),
        ),
      0,
    );
    const openTasks = list(c.tasks).filter(
      (t) => t.required && t.status === "OPEN",
    );
    const notified = Boolean(
      c.merchant_notified ||
        c.merchant_notification_completed ||
        c.notification_completed ||
        list(c.collaboration).some((m) =>
          ["MERCHANT_NOTIFICATION", "RESULT_NOTIFICATION"].includes(m.type),
        ),
    );
    const gates = [
      ["上游确认终局", c.finality === "FINAL_CONFIRMED"],
      [
        "资金已核对或不适用",
        ["RECONCILED", "NOT_APPLICABLE"].includes(c.financial_status),
      ],
      ["必要任务全部完成", !openTasks.length],
      ["商户通知已完成", notified],
    ];
    return `${section("上游结果与阶段", "结果不等于终局；非终局继续后续阶段")}<div class="two-column" style="margin-top:0"><div class="info-card">${fact("业务结果", label(c.business_outcome))}${fact("终局状态", label(c.finality))}</div><div class="info-card">${fact("当前阶段", label(c.stage))}${fact("资金状态", label(c.financial_status))}</div></div><div class="action-bar">${actionButton("RECORD_OUTCOME", "登记上游结果", { primary: true })}${actionButton("NEXT_STAGE", "开始后续阶段")}</div>${list(
      c.upstream_events,
    )
      .map(
        (e) =>
          `<div class="record-row"><span class="row-icon">↙</span><div class="row-content"><div class="row-title">${esc(label(e.outcome || e.type || e.kind || "上游事件"))}</div><div class="row-subtitle">${esc(e.event_id || e.id)} · ${esc(e.source || "上游")}<br>${date(e.created_at || e.received_at || e.at)} ${e.reason ? `· ${esc(e.reason)}` : ""}</div></div></div>`,
      )
      .join(
        "",
      )}${section("资金事件与核对", "金额以该币种最小货币单位登记；币种、差异与核对依据留痕")}<div class="action-bar">${actionButton("RECORD_FINANCIAL")}${actionButton("RECONCILE", "人工资金核对", { primary: true })}</div>${financial.length ? `<div class="table-scroll"><table class="rule-table"><thead><tr><th>事件</th><th>金额</th><th>来源 / 引用</th></tr></thead><tbody>${financial.map((e) => `<tr><td>${esc(label(e.kind))}<br><span class="mono">${esc(e.event_id || e.id)}</span></td><td>${esc(money(e.amount_minor, e.currency || c.currency))}</td><td>${esc(e.source)}<br>${esc(e.reference)}</td></tr>`).join("")}</tbody></table></div>` : empty("尚无资金事件。")}${fact("事件净影响（展示）", money(net, c.currency))}${section("案件关闭条件", "终局、资金、必要任务、商户通知与审计材料共同校验")}${gates.map(([title, done]) => `<div class="task-row"><span class="check-mark ${done ? "done" : ""}">${done ? "✓" : "○"}</span><div class="row-content"><div class="row-title">${title}</div></div>${badge(done ? "COMPLETED" : "OPEN")}</div>`).join("")}<p class="section-note">以服务端关闭 Gate 为准；存在资金差异或终局未确认时禁止关闭。</p><div class="action-bar">${actionButton("NOTIFY_MERCHANT")}${actionButton("CLOSE", "确认关闭案件", { primary: true })}${actionButton("KNOWLEDGE_CANDIDATE")}</div>`;
  }
  function renderAudit(c) {
    return `${section("案件审计时间线", "每条命令保留角色、版本、决策与回执", `<span class="badge gray">当前 v${esc(c.revision)}</span>`)}${
      list(c.audit)
        .slice()
        .reverse()
        .map(
          (a) =>
            `<div class="audit-row"><div class="audit-dot"></div><div><h4>${esc(label(a.action || a.type || "审计事件"))} ${a.revision ? `<span class="badge gray">v${esc(a.revision)}</span>` : ""}</h4><p>${esc(a.actor || a.actor_id || "")} · ${esc(label(a.role || a.actor_role || ""))} · ${date(a.created_at || a.timestamp || a.at)}<br><span class="mono">${esc(a.command_id || a.id || "")}</span>${a.reason ? `<br>${esc(a.reason)}` : ""}</p><details><summary class="row-subtitle">查看审计记录</summary><pre class="code-block">${esc(JSON.stringify(a, null, 2))}</pre></details></div></div>`,
        )
        .join("") || empty("暂无审计记录。")
    }`;
  }
  function renderDetail() {
    const c = S.current;
    if (!c) {
      $("caseDetail").innerHTML =
        `<div class="empty-state"><div class="empty-symbol">◈</div><h2>每一个决定，都有上下文。</h2><p>${surface === "merchant" ? "你的争议任务与准备清单将显示在这里。" : "加载一个合成演示案例，或接收上游事件，开始完整争议流程。"}</p>${permitted("INTAKE") ? '<button class="button primary" data-demo>加载演示案例 →</button>' : ""}</div>`;
      return;
    }
    const p = S.plan;
    const renderers = {
      overview: () => renderOverview(c, p),
      tasks: () => renderTasks(c),
      evidence: () => renderEvidence(c, p),
      agent: () => renderAgent(c, p),
      collaboration: () => renderCollaboration(c),
      review: () => renderReview(c),
      outcome: () => renderOutcome(c),
      audit: () => renderAudit(c),
    };
    const visibleTabs =
      surface === "merchant" ? tabs.filter(([key]) => key !== "review") : tabs;
    $("caseDetail").innerHTML =
      `<div class="detail-header"><button class="mobile-back" data-back>← 返回案件列表</button><div class="detail-topline"><span class="case-id">${esc(c.id)}</span><span>案件版本 v${esc(c.revision)} · ${esc(c.source_type || "SYNTHETIC_DEMO")}</span></div><div class="detail-title"><h2>${esc(c.merchant_id)}</h2><div class="detail-amount"><small>${esc(c.currency)}</small>${esc(money(c.amount_minor, c.currency))}</div></div><div class="case-facts"><span>卡组织 <strong>${esc(c.scheme)}</strong></span><span>原因码 <strong>${esc(c.reason_code)}</strong></span><span>渠道 <strong>${esc(c.channel)}</strong></span><span>案件负责人 <strong>${esc(c.owner || "OceanPayment")}</strong></span></div></div><div class="dimension-strip">${[
        ["争议阶段", c.stage],
        ["工作状态", c.work_status],
        ["商户决定", c.merchant_decision],
        ["业务结果", c.business_outcome],
        ["终局状态", c.finality],
        ["资金状态", c.financial_status],
      ]
        .map(
          ([key, value]) =>
            `<div class="dimension"><label>${key}</label>${badge(value)}</div>`,
        )
        .join(
          "",
        )}</div><nav class="detail-tabs" aria-label="案件详情">${visibleTabs.map(([key, title]) => `<button class="detail-tab ${S.tab === key ? "active" : ""}" data-tab="${key}" aria-current="${S.tab === key ? "page" : "false"}">${title}</button>`).join("")}</nav><div class="detail-content">${(renderers[S.tab] || renderers.overview)()}</div>`;
  }
  function renderGovernance() {
    const g = S.governance;
    if (!g) {
      $("governanceView").innerHTML = empty(
        "治理信息暂时不可用。请确认演示角色权限并刷新。",
      );
      return;
    }
    const integrationNames = {
      upstream: "上游提交",
      feishu: "飞书协作",
      model: "Agent / 模型",
      notification: "通知服务",
      persistence: "案件持久化",
      portal: "商户门户",
    };
    const integrations = Object.entries(g.integrations || {});
    $("governanceView").innerHTML =
      `<div class="governance-grid"><div class="governance-card"><h2>集成与运行边界</h2>${integrations
        .map(([key, value]) => {
          const v = typeof value === "object" ? value : { status: value };
          return `<div class="integration-row"><div>${esc(integrationNames[key] || key)}<p>${esc(v.description || v.boundary || v.mode || "")}</p></div>${badge(v.status || v.mode || text(value))}</div>`;
        })
        .join(
          "",
        )}<div class="callout">${esc(g.boundary || "合成演示数据，Mock 上游。生产认证、正式 SLA 与企业接口需独立配置验证。")}</div></div><div class="governance-card"><h2>待企业确认的集成事项</h2><ol class="confirm-points">${list(
        g.open_confirmation_points,
      )
        .map((point) => `<li>${esc(text(point))}</li>`)
        .join(
          "",
        )}</ol></div><div class="governance-card wide"><h2>规则治理与来源快照</h2><p class="section-note">案件冻结规则来源和版本；新规则不静默覆盖旧案。合成规则不能视为正式卡组织 SLA。</p><div class="table-scroll"><table class="rule-table"><thead><tr><th>规则 / 原因码</th><th>来源与版本</th><th>证据要求</th><th>状态</th></tr></thead><tbody>${list(
        g.rules,
      )
        .map(
          (r) =>
            `<tr><td>${esc(r.scheme)} · ${esc(r.reason_code)}<br>${esc(label(r.stage))}</td><td>${esc(r.source_id)}<br><span class="mono">${esc(r.rule_version)}</span><br>${esc(r.source_locator)}</td><td>${list(
              r.required_evidence,
            )
              .map((e) => esc(typeof e === "string" ? e : e.label || e.code))
              .join(
                "<br>",
              )}</td><td>${badge(r.conflict_status)}<br>${badge(r.source_type || "SYNTHETIC_DEMO")}<br><span class="row-subtitle">production_eligible: ${r.production_eligible === true ? "true" : "false"}</span></td></tr>`,
        )
        .join(
          "",
        )}</tbody></table></div></div><div class="governance-card"><h2>角色权限</h2><p class="section-note">X-Demo-Role 仅用于本地合成权限演示；不构成生产登录与认证。</p>${Object.entries(
        g.permissions || rolePermissions,
      )
        .map(
          ([role, actions]) =>
            `<div style="margin-bottom:16px"><h4 class="row-title">${esc(label(role))}</h4><div class="permission-grid">${list(
              actions,
            )
              .map((a) => `<span>${esc(label(a))}</span>`)
              .join("")}</div></div>`,
        )
        .join(
          "",
        )}</div><div class="governance-card"><h2>知识候选与人工审核</h2><p class="section-note">关闭案件后提取脱敏模式，经人工审核后才能进入可复用知识。</p>${
        list(g.knowledge)
          .map(
            (k) =>
              `<div class="info-card" style="margin-bottom:12px"><div class="row-title">${esc(k.summary || k.pattern || k.id)}</div><p class="row-subtitle">${esc(k.pattern || "")}<br>${esc(k.case_id || "")} · ${esc(k.status || "待审核")}</p>${permitted("APPROVE_KNOWLEDGE") ? `<button class="button secondary small" data-knowledge="${esc(k.id)}" data-knowledge-case="${esc(k.case_id)}">人工审核</button>` : ""}</div>`,
          )
          .join("") || empty("尚无知识候选。先完成案件闭环，再提取脱敏模式。")
      }</div><div class="governance-card wide"><h2>运行指标</h2><div class="permission-grid">${Object.entries(
        g.metrics || {},
      )
        .map(([k, v]) => `<span>${esc(k)}：${esc(text(v))}</span>`)
        .join("")}</div></div></div>`;
  }
  function writeNavigation() {
    const url = new URL(location.href);
    if (S.current) url.searchParams.set("case", S.current.id);
    url.searchParams.set("tab", S.tab);
    history.replaceState(null, "", url);
    document.querySelectorAll("[data-surface]").forEach((link) => {
      const target = new URL(link.href, location.origin);
      if (S.current) target.searchParams.set("case", S.current.id);
      link.href = target.pathname + target.search;
    });
  }
  async function openCase(id) {
    const ticket = ++S.selection;
    S.plan = null;
    S.current = null;
    renderQueue();
    $("caseDetail").innerHTML =
      '<div class="detail-load">正在读取案件与规则计划…</div>';
    $("workspaceGrid").classList.remove("show-queue");
    try {
      const [caseResult, planResult] = await Promise.allSettled([
        api(`/cases/${encodeURIComponent(id)}`),
        api(`/cases/${encodeURIComponent(id)}/plan`),
      ]);
      if (ticket !== S.selection) return;
      if (caseResult.status !== "fulfilled") throw caseResult.reason;
      S.current = caseResult.value.case || caseResult.value;
      S.plan = planResult.status === "fulfilled" ? planResult.value : null;
      if (
        S.plan?.revision !== undefined &&
        S.plan.revision !== S.current.revision
      )
        S.plan = null;
      if (planResult.status === "rejected")
        setNotice(
          `案件已读取，但计划暂不可用：${planResult.reason.message}`,
          true,
        );
      renderQueue();
      renderDetail();
      writeNavigation();
    } catch (error) {
      if (ticket !== S.selection) return;
      S.current = null;
      renderDetail();
      setNotice(error.message, true);
    }
  }
  async function refresh(force = false) {
    if (S.loading && !force) return;
    S.loading = true;
    $("refreshButton").disabled = true;
    const ticket = ++S.refreshEpoch;
    try {
      const results = await Promise.allSettled([
        api("/cases"),
        ["ADMIN", "SUPERVISOR"].includes(S.role)
          ? api("/governance")
          : Promise.resolve(null),
        api("/capabilities"),
      ]);
      if (ticket !== S.refreshEpoch) return;
      if (results[0].status === "rejected") throw results[0].reason;
      S.cases = list(results[0].value.cases);
      if (results[2].status === "fulfilled") S.capabilities = results[2].value;
      if (results[1].status === "fulfilled") S.governance = results[1].value;
      else if (surface === "governance")
        setNotice(results[1].reason.message, true);
      renderMetrics();
      renderQueue();
      if (surface === "governance") renderGovernance();
      else {
        const preferred =
          S.current?.id || new URL(location.href).searchParams.get("case");
        const next =
          S.cases.find((c) => c.id === preferred)?.id || S.cases[0]?.id;
        if (next) await openCase(next);
        else {
          S.current = null;
          S.plan = null;
          renderDetail();
        }
      }
    } catch (error) {
      setNotice(`读取失败：${error.message}`, true);
    } finally {
      if (ticket === S.refreshEpoch) {
        S.loading = false;
        $("refreshButton").disabled = false;
      }
    }
  }
  function field(name, title, value = "", type = "text", options = {}) {
    const required = options.optional ? "" : " required";
    const hint = options.hint ? `<small>${esc(options.hint)}</small>` : "";
    if (type === "checkbox")
      return `<label class="form-field checkbox"><input name="${esc(name)}" type="checkbox"${value ? " checked" : ""}${required}>${esc(title)}${hint}</label>`;
    const common = `name="${esc(name)}"${required}`;
    let input;
    if (type === "select")
      input = `<select ${common}>${list(options.choices)
        .map((choice) => {
          const [key, display] = Array.isArray(choice)
            ? choice
            : [choice, label(choice)];
          return `<option value="${esc(key)}"${String(value) === String(key) ? " selected" : ""}>${esc(display)}</option>`;
        })
        .join("")}</select>`;
    else if (type === "textarea")
      input = `<textarea ${common} maxlength="${options.max || 4000}">${esc(value)}</textarea>`;
    else
      input = `<input ${common} type="${type}" value="${esc(value)}"${type === "number" ? ' step="1"' : ""}${options.min !== undefined ? ` min="${options.min}"` : ""}${type === "text" ? ' maxlength="1000"' : ""}>`;
    return `<label class="form-field"><span>${esc(title)}${options.optional ? "（可选）" : ""}</span>${input}${hint}</label>`;
  }
  function isoInput(value) {
    if (!value) return "";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "";
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
  }
  function commandFields(action, data = {}) {
    const c = S.current || {};
    const pkg = list(c.packages)
      .filter((p) => p.status !== "INVALIDATED")
      .at(-1);
    const rule = c.rule_snapshot || {};
    const deadline = S.plan?.deadlines || c.deadlines || {};
    const reason = (value = "") =>
      field("reason", "决策依据 / 说明", data.reason || value, "textarea");
    const event = () =>
      field("event_id", "上游事件 ID", `synthetic-${uuid()}`, "text", {
        hint: "同一上游事件应复用相同 ID，以保证去重。",
      });
    switch (action) {
      case "INTAKE":
        return (
          field("merchant_id", "商户 ID", S.merchantId) +
          field(
            "transaction_id",
            "交易关联 ID",
            `synthetic-txn-${Date.now()}`,
          ) +
          field("scheme", "卡组织", "VISA", "select", {
            choices: ["VISA", "MASTERCARD"],
          }) +
          field("channel", "上游渠道", "MOCK") +
          field("reason_code", "原因码", "13.1") +
          field("amount_minor", "争议金额（最小货币单位）", 129900, "number", {
            min: 1,
            hint: "例如 USD 129900 最小单位表示 USD 1,299.00。",
          }) +
          field("currency", "币种", "USD", "select", {
            choices: ["USD", "EUR", "GBP", "CNY"],
          }) +
          event()
        );
      case "CONFIRM_RULE":
        return (
          field("source_id", "规则来源 ID", rule.source_id || "") +
          field(
            "source_locator",
            "来源定位 / 文档位置",
            rule.source_locator || "",
          ) +
          field("rule_version", "规则版本", rule.rule_version || "") +
          field(
            "external_deadline",
            "外部截止时间",
            isoInput(deadline.external),
            "datetime-local",
            {
              hint: "使用本地时区填写，发送时转换为 ISO 时间。无法确认时请保持案件阻断。",
            },
          ) +
          field(
            "merchant_deadline",
            "商户目标时间",
            isoInput(deadline.merchant),
            "datetime-local",
            { optional: true },
          ) +
          field(
            "internal_deadline",
            "OP 内部时间",
            isoInput(deadline.internal),
            "datetime-local",
            { optional: true },
          ) +
          field(
            "allow_accept",
            "依据来源确认允许接受责任（Accept）",
            list(rule.allowed_actions).includes("ACCEPT"),
            "checkbox",
            { optional: true },
          ) +
          field(
            "allow_contest",
            "依据来源确认允许提出抗辩（Contest）",
            list(rule.allowed_actions).includes("CONTEST"),
            "checkbox",
            { optional: true },
          ) +
          field(
            "required_evidence",
            "必需证据代码（逗号分隔）",
            list(rule.required_evidence).join(", "),
            "text",
            { optional: true },
          ) +
          reason()
        );
      case "PUBLISH_TASK":
        return (
          field(
            "message",
            "商户任务内容",
            data.message ||
              "请确认是否接受争议责任或提出抗辩，并按案件清单登记证据。",
            "textarea",
          ) + field("required", "必要任务", true, "checkbox")
        );
      case "MERCHANT_DECISION":
        return (
          field(
            "decision",
            "商户决定",
            data.decision ||
              (S.role === "MERCHANT" ? "CONTEST" : "NO_RESPONSE"),
            "select",
            {
              choices:
                S.role === "MERCHANT"
                  ? [
                      ["CONTEST", "Contest · 提出抗辩"],
                      ["ACCEPT", "Accept · 接受责任"],
                    ]
                  : ["NO_RESPONSE", "AUTHORIZED_WAIVER", "ACCEPT", "CONTEST"],
            },
          ) +
          reason() +
          field(
            "authorization_reference",
            "授权或未响应处理依据",
            data.authorization_reference || "",
            "text",
            {
              optional: true,
              hint: "接受责任、授权放弃等处理需要明确授权依据。",
            },
          )
        );
      case "REGISTER_EVIDENCE": {
        const options = list(S.plan?.checklist).map((i) => [
          i.code,
          i.label || i.code,
        ]);
        return (
          (options.length
            ? field("code", "证据类型", data.code || options[0][0], "select", {
                choices: options,
              })
            : field("code", "证据代码", data.code || "")) +
          field("title", "证据标题", data.title || "") +
          field(
            "reference",
            "证据位置 / 对象引用",
            data.reference || "",
            "text",
            {
              hint: "登记可追溯的对象引用。此演示不上传、解析或保存文件正文；请勿输入支付敏感信息。",
            },
          ) +
          field("source_channel", "来源渠道", "PORTAL", "select", {
            choices: ["PORTAL", "FEISHU", "EMAIL"],
          }) +
          field("notes", "证据说明", data.notes || "", "textarea", {
            optional: true,
          })
        );
      }
      case "WITHDRAW_EVIDENCE":
        return (
          field("evidence_id", "证据 ID", data.evidence_id || "", "select", {
            choices: list(c.evidence)
              .filter((e) => e.active !== false)
              .map((e) => [e.id, e.title || e.code]),
          }) + reason()
        );
      case "SUBMIT_EVIDENCE":
        return '<p class="section-note">将当前有效证据提交给 OP 审核。关键证据未齐全时，案件引擎会阻止提交。</p>';
      case "REVIEW":
        return (
          field("decision", "审核结论", data.decision || "PASS", "select", {
            choices: [
              ["PASS", "通过 · 准备证据包"],
              ["REVISION", "退回 · 要求补证"],
              ["ACCEPT", "建议接受责任 · 交商户确认"],
            ],
          }) + reason()
        );
      case "BUILD_PACKAGE":
        return field("draft", "证据包草稿", data.draft || "", "textarea", {
          optional: true,
          hint: "留空使用确定性模板。正文是草稿，需人工终审后冻结。",
        });
      case "APPROVE_PACKAGE":
        return (
          field(
            "package_id",
            "待冻结证据包",
            data.package_id || pkg?.id || "",
            "select",
            {
              choices: list(c.packages)
                .filter((p) => p.status === "DRAFT")
                .map((p) => [p.id, `v${p.version} · ${p.id}`]),
            },
          ) +
          reason() +
          field(
            "pii_checked",
            "已人工检查证据包的敏感信息与引用",
            false,
            "checkbox",
          )
        );
      case "SUBMIT":
        return (
          field(
            "package_id",
            "已冻结证据包",
            data.package_id || pkg?.id || "",
            "select",
            {
              choices: list(c.packages)
                .filter((p) => p.status === "FROZEN")
                .map((p) => [p.id, `v${p.version} · ${p.id}`]),
            },
          ) +
          '<div class="callout">此次操作只提交至 Mock 上游，并生成可审计模拟回执。</div>'
        );
      case "RECORD_OUTCOME":
        return (
          event() +
          field("outcome", "上游业务结果", data.outcome || "OTHER", "select", {
            choices: [
              "OTHER",
              "WON",
              "LOST",
              "PARTIAL",
              "ACCEPTED_RESPONSIBILITY",
              "WITHDRAWN",
            ],
          }) +
          field("final", "上游明确确认这是终局结果", false, "checkbox", {
            optional: true,
          }) +
          field("source", "结果来源", data.source || "MOCK_UPSTREAM") +
          reason() +
          field(
            "next_stage",
            "非终局后续阶段",
            data.next_stage || "",
            "select",
            {
              optional: true,
              choices: [
                ["", "暂不创建后续阶段"],
                "REPRESENTMENT",
                "PRE_ARBITRATION",
                "ARBITRATION",
                "OTHER",
              ],
            },
          )
        );
      case "NEXT_STAGE":
        return (
          field("stage", "后续阶段", "REPRESENTMENT", "select", {
            choices: [
              "REPRESENTMENT",
              "PRE_ARBITRATION",
              "ARBITRATION",
              "OTHER",
            ],
          }) +
          event() +
          field("source", "上游来源", "MOCK_UPSTREAM")
        );
      case "RECORD_FINANCIAL":
        return (
          event() +
          field("kind", "资金事件类型", "CREDIT", "select", {
            choices: ["DEBIT", "CREDIT", "REFUND", "FEE", "ADJUSTMENT"],
          }) +
          field("amount_minor", "金额（最小货币单位）", c.amount_minor || 0, "number") +
          field("currency", "币种", c.currency || "USD") +
          field("source", "资金事件来源", "MOCK_UPSTREAM") +
          field("reference", "核对凭证 / 流水引用", "")
        );
      case "RECONCILE":
        return (
          field("status", "核对结论", "RECONCILED", "select", {
            choices: ["RECONCILED", "DISCREPANCY", "NOT_APPLICABLE"],
          }) +
          field("expected_net_minor", "预期净影响（最小货币单位，有符号）", 0, "number", {
            hint: "扣款与费用为负，返还为正。填写经核对的预期净影响。",
          }) +
          reason() +
          field("reference", "核对依据 / 凭证引用", "")
        );
      case "NOTIFY_MERCHANT":
        return (
          field(
            "message",
            "通知商户的结果说明",
            `案件 ${c.id} 的结果为${label(c.business_outcome)}，资金状态为${label(c.financial_status)}。`,
            "textarea",
          ) +
          field("channel", "通知渠道", "PORTAL", "select", {
            choices: ["PORTAL"],
          }) +
          field("reference", "通知引用", "", "text", { optional: true })
        );
      case "CLOSE":
        return `<div class="callout">关闭案件必须已确认终局、完成资金核对、完成所有必要任务、通知商户，并具备审计材料。</div>${fact("案件版本", `v${c.revision}`)}${fact("终局", label(c.finality))}${fact("资金", label(c.financial_status))}`;
      case "COMMENT":
        return (
          field("message", "案件协作消息", data.message || "", "textarea") +
          field("channel", "协作渠道", "PORTAL", "select", {
            choices: ["PORTAL"],
          })
        );
      case "MONITOR_SLA":
        return '<p class="section-note">依据当前案件的已确认时限检查风险，生成提醒或人工升级事件。不会自动将商户未回复视为接受争议。</p>';
      case "KNOWLEDGE_CANDIDATE":
        return (
          field("summary", "脱敏案例摘要", "", "textarea", {
            hint: "仅复用处理模式。不要填写商户个人信息、卡号或支付凭据。",
          }) + field("pattern", "可复用处理模式", "", "textarea")
        );
      case "APPROVE_KNOWLEDGE":
        return (
          field("candidate_id", "候选 ID", data.candidate_id || "") +
          field("decision", "知识审核结论", "APPROVE", "select", {
            choices: ["APPROVE", "REJECT"],
          }) +
          reason()
        );
      default:
        return "";
    }
  }
  function openDialog(action, data = {}) {
    if (S.busy) return;
    if (S.pending) {
      setNotice(
        "上一条命令结果尚未确认，请先使用原命令重试。",
        true,
        '<button class="button secondary small" data-retry>使用原命令重试</button>',
      );
      return;
    }
    if (action === "DEMO" && S.role !== "OPERATOR") {
      setNotice("请切换到 OP 运营专员后加载演示案例。", true);
      return;
    }
    if (action !== "DEMO" && !permitted(action)) {
      setNotice(`${label(action)}：${roleHint(action)}`, true);
      return;
    }
    if (action !== "INTAKE" && action !== "DEMO" && !S.current) {
      setNotice("请先选择一个案件。", true);
      return;
    }
    S.dialog = {
      action,
      case_id: S.current?.id,
      revision: S.current?.revision,
      identity: identity(),
      data,
    };
    $("dialogTitle").textContent =
      action === "DEMO" ? "加载合成演示案例" : label(action);
    $("dialogEyebrow").textContent =
      action === "DEMO" ? "GOLDEN DEMO" : "REVIEW → CONFIRM → COMMAND";
    $("dialogContext").innerHTML =
      action === "DEMO"
        ? "创建独立的合成案例，用于演示规则、权限、版本与生命周期。"
        : `${esc(label(S.role))} · ${action === "INTAKE" ? "OceanPayment 接收上游事件" : `${esc(S.current.id)} · 当前版本 <strong>v${esc(S.current.revision)}</strong>`}<br>本次确认仅对显示的案件与版本有效。`;
    $("dialogFields").innerHTML =
      action === "DEMO"
        ? `<div class="demo-options">${[
            ["A", "正常 Contest", "从接收事件开始推进完整闭环"],
            ["B", "关键证据缺失", "缺证检查、阻断与补证"],
            ["C", "SLA / 未响应", "时限提醒与人工升级"],
            ["D", "财务异常", "终局结果后的资金差异处理"],
          ]
            .map(
              ([id, title, description], i) =>
                `<label class="demo-option"><input type="radio" name="scenario" value="${id}" ${i ? "" : "checked"} required>${id} · ${title}<small>${description}</small></label>`,
            )
            .join("")}</div>`
        : commandFields(action, data);
    $("dialogError").hidden = true;
    $("confirmCheckbox").checked = false;
    $("dialogConfirmation").hidden = false;
    $("submitDialog").textContent =
      action === "DEMO" ? "创建演示案例" : "确认并执行";
    $("submitDialog").disabled = false;
    $("actionDialog").showModal();
  }
  function closeDialog() {
    if (S.busy) return;
    $("actionDialog").close();
    S.dialog = null;
  }
  function collectData(form) {
    const values = {};
    for (const [key, value] of new FormData(form).entries())
      if (key !== "scenario") values[key] = String(value).trim();
    for (const input of form.querySelectorAll("input[type=checkbox][name]"))
      values[input.name] = input.checked;
    if ("allow_accept" in values || "allow_contest" in values) {
      values.allowed_actions = [
        ...(values.allow_accept ? ["ACCEPT"] : []),
        ...(values.allow_contest ? ["CONTEST"] : []),
      ];
      delete values.allow_accept;
      delete values.allow_contest;
    }
    for (const key of ["amount_minor", "expected_net_minor"])
      if (key in values) values[key] = Number(values[key]);
    for (const key of [
      "external_deadline",
      "merchant_deadline",
      "internal_deadline",
    ]) {
      if (values[key]) values[key] = new Date(values[key]).toISOString();
      else delete values[key];
    }
    if ("required_evidence" in values) {
      if (values.required_evidence)
        values.required_evidence = values.required_evidence
          .split(/[,，\n]/)
          .map((s) => s.trim())
          .filter(Boolean);
      else delete values.required_evidence;
    }
    for (const key of Object.keys(values))
      if (values[key] === "") delete values[key];
    return values;
  }
  function savePending() {
    if (S.pending)
      storage.set("oceanpilot.v2.pending", JSON.stringify(S.pending));
    else storage.remove("oceanpilot.v2.pending");
  }
  async function executePending() {
    if (!S.pending || S.busy) return;
    const pending = S.pending;
    if (
      pending.identity.role !== S.role ||
      pending.identity.merchant_id !== S.merchantId
    ) {
      setNotice(
        `请切换到原演示角色 ${label(pending.identity.role)} 后恢复命令。`,
        true,
      );
      return;
    }
    S.busy = true;
    $("submitDialog").disabled = true;
    try {
      const result = await api(
        "/commands",
        { method: "POST", body: JSON.stringify(pending.payload) },
        pending.identity,
      );
      S.pending = null;
      savePending();
      $("actionDialog").close();
      S.dialog = null;
      const c = result.case;
      setNotice(
        `${result.replayed ? "已确认原命令回执" : "操作已完成"}：${label(pending.payload.action)} · ${c?.id || pending.payload.case_id || ""} · v${c?.revision || "—"}${result.receipt?.command_id ? ` · 回执 ${result.receipt.command_id}` : ""}`,
      );
      if (
        c &&
        (!S.current ||
          S.current.id === pending.payload.case_id ||
          pending.payload.action === "INTAKE")
      )
        S.current = c;
      await refresh();
    } catch (error) {
      if (error.uncertain) {
        setNotice(
          "请求结果尚未确认。已保留原命令 ID、身份和版本，重试不会创建新的命令。",
          true,
          '<button class="button secondary small" data-retry>使用原命令重试</button>',
        );
        $("dialogError").textContent =
          error.message + "。关闭此窗口后，可使用页面上的原命令重试。";
        $("dialogError").hidden = false;
      } else {
        S.pending = null;
        savePending();
        $("dialogError").textContent =
          error.status === 409
            ? `案件版本或业务条件已变化：${error.message}。已刷新案件，请关闭本窗口并重新核对后操作。`
            : error.message;
        $("dialogError").hidden = false;
        setNotice(error.message, true);
        if (error.status === 409) {
          if (S.dialog) S.dialog.stale = true;
          if (pending.payload.case_id) await openCase(pending.payload.case_id);
        }
      }
    } finally {
      S.busy = false;
      $("submitDialog").disabled = Boolean(S.pending || S.dialog?.stale);
    }
  }
  async function submitDialog(event) {
    event.preventDefault();
    if (S.busy || !S.dialog) return;
    if (!$("actionForm").reportValidity()) return;
    if (!$("confirmCheckbox").checked) return;
    const d = S.dialog;
    if (
      d.stale ||
      (d.action !== "DEMO" &&
        d.action !== "INTAKE" &&
        (!S.current ||
          S.current.id !== d.case_id ||
          S.current.revision !== d.revision))
    ) {
      $("dialogError").textContent =
        "当前案件或版本已变化，请关闭窗口并重新核对操作。";
      $("dialogError").hidden = false;
      return;
    }
    if (d.identity.role !== S.role) {
      $("dialogError").textContent = "演示角色已变化，请重新发起操作。";
      $("dialogError").hidden = false;
      return;
    }
    if (d.action === "DEMO") {
      S.busy = true;
      $("submitDialog").disabled = true;
      try {
        const scenario = new FormData($("actionForm")).get("scenario");
        const result = await api("/demo", {
          method: "POST",
          body: JSON.stringify({ scenario }),
        });
        $("actionDialog").close();
        S.dialog = null;
        if (result.case) S.current = result.case;
        setNotice(`已加载演示 ${scenario}：所有记录均为 SYNTHETIC_DEMO。`);
        await refresh();
      } catch (error) {
        $("dialogError").textContent = error.message;
        $("dialogError").hidden = false;
      } finally {
        S.busy = false;
        $("submitDialog").disabled = false;
      }
      return;
    }
    const data = collectData($("actionForm"));
    if (d.action === "CONFIRM_RULE" && !data.allowed_actions?.length) {
      $("dialogError").textContent =
        "请根据已核对的规则来源明确选择至少一项允许的商户权利。";
      $("dialogError").hidden = false;
      return;
    }
    const payload = {
      command_id: uuid(),
      action: d.action,
      confirmed: true,
      data,
    };
    if (d.action !== "INTAKE") {
      payload.case_id = d.case_id;
      payload.expected_revision = d.revision;
    }
    S.pending = { payload, identity: d.identity };
    savePending();
    await executePending();
  }
  async function changeRole() {
    if (S.busy) {
      $("roleSelect").value = S.role;
      return;
    }
    S.role = $("roleSelect").value;
    storage.set(`oceanpilot.v2.role.${surface}`, S.role);
    S.current = null;
    S.plan = null;
    S.governance = null;
    S.capabilities = null;
    S.selection++;
    if ($("actionDialog").open) closeDialog();
    $("avatar").textContent =
      S.role === "MERCHANT" ? "M" : S.role === "AGENT" ? "AI" : "OP";
    $("intakeButton").hidden = surface !== "operations" || !permitted("INTAKE");
    $("demoButton").hidden = surface === "merchant" || S.role !== "OPERATOR";
    setNotice(`已切换为 ${label(S.role)}。操作权限由服务端重新校验。`);
    await refresh(true);
  }
  function bindEvents() {
    document.addEventListener("click", async (event) => {
      const button = event.target.closest("button");
      if (!button) return;
      if (button.dataset.case) {
        await openCase(button.dataset.case);
        return;
      }
      if (button.dataset.queue) {
        S.queue = button.dataset.queue;
        renderQueue();
        $("workspaceGrid").classList.add("show-queue");
        return;
      }
      if (button.dataset.tab) {
        S.tab = button.dataset.tab;
        renderDetail();
        writeNavigation();
        return;
      }
      if (button.dataset.action) {
        let data = {};
        try {
          data = JSON.parse(button.dataset.commandData || "{}");
        } catch {}
        openDialog(button.dataset.action, data);
        return;
      }
      if (button.hasAttribute("data-demo")) {
        openDialog("DEMO");
        return;
      }
      if (button.hasAttribute("data-back")) {
        $("workspaceGrid").classList.add("show-queue");
        return;
      }
      if (button.hasAttribute("data-retry")) {
        await executePending();
        return;
      }
      if (button.dataset.knowledge) {
        await openCase(button.dataset.knowledgeCase);
        if (S.current)
          openDialog("APPROVE_KNOWLEDGE", {
            candidate_id: button.dataset.knowledge,
          });
      }
    });
    $("refreshButton").addEventListener("click", () => refresh());
    $("demoButton").addEventListener("click", () => openDialog("DEMO"));
    $("intakeButton").addEventListener("click", () => openDialog("INTAKE"));
    $("caseSearch").addEventListener("input", (event) => {
      S.search = event.target.value;
      renderQueue();
    });
    $("stageFilter").addEventListener("change", (event) => {
      S.stage = event.target.value;
      renderQueue();
    });
    $("roleSelect").addEventListener("change", changeRole);
    $("actionForm").addEventListener("submit", submitDialog);
    $("closeDialog").addEventListener("click", closeDialog);
    $("cancelDialog").addEventListener("click", closeDialog);
    $("actionDialog").addEventListener("cancel", (event) => {
      if (S.busy) event.preventDefault();
      else S.dialog = null;
    });
  }
  function initialize() {
    const allowed =
      surface === "merchant"
        ? ["MERCHANT"]
        : surface === "governance"
          ? ["ADMIN", "OPERATOR", "RISK_OFFICER", "SUPERVISOR", "AGENT"]
          : ["OPERATOR", "RISK_OFFICER", "SUPERVISOR", "AGENT", "ADMIN"];
    const saved = storage.get(`oceanpilot.v2.role.${surface}`);
    if (allowed.includes(saved)) S.role = saved;
    $("roleSelect").innerHTML = allowed
      .map(
        (role) =>
          `<option value="${role}"${role === S.role ? " selected" : ""}>${esc(label(role))}</option>`,
      )
      .join("");
    document
      .querySelectorAll("[data-surface]")
      .forEach((link) =>
        link.classList.toggle("active", link.dataset.surface === surface),
      );
    const details =
      surface === "merchant"
        ? [
            "商户协作",
            "MERCHANT WORKSPACE",
            "你的响应，让事实更清晰。",
            "查看争议原因、确认决定，并按清单提交证据。",
          ]
        : surface === "governance"
          ? [
              "平台治理",
              "GOVERNANCE WORKSPACE",
              "让自动化，始终有边界。",
              "查看集成状态、规则来源、权限与知识审核。",
            ]
          : [
              "争议运营",
              "OPERATIONS WORKSPACE",
              "让每一笔争议，有据可循。",
              "从上游接收到资金核对，在一个案件中协同推进。",
            ];
    $("surfaceBreadcrumb").textContent = details[0];
    $("eyebrow").textContent = details[1];
    $("pageTitle").textContent = details[2];
    $("pageDescription").textContent = details[3];
    document.title = `OceanPilot V2 · ${details[0]}`;
    $("identityNote").textContent =
      surface === "merchant"
        ? `演示商户：${S.merchantId} · 仅访问本商户案件 · 非生产身份认证`
        : "角色切换用于 Synthetic 权限演示，非生产身份认证。";
    $("intakeButton").hidden = surface !== "operations" || !permitted("INTAKE");
    $("demoButton").hidden = surface === "merchant" || S.role !== "OPERATOR";
    $("workspaceGrid").hidden = surface === "governance";
    $("governanceView").hidden = surface !== "governance";
    $("queueNav").hidden = surface === "governance";
    $("queueNavLabel").hidden = surface === "governance";
    const requestedTab = new URL(location.href).searchParams.get("tab");
    if (
      tabs.some(([key]) => key === requestedTab) &&
      !(surface === "merchant" && requestedTab === "review")
    )
      S.tab = requestedTab;
    try {
      S.pending = JSON.parse(storage.get("oceanpilot.v2.pending") || "null");
      if (S.pending?.payload?.command_id)
        setNotice(
          "有一条结果未确认的命令。请使用原命令 ID 恢复，避免重复操作。",
          true,
          '<button class="button secondary small" data-retry>使用原命令重试</button>',
        );
      else S.pending = null;
    } catch {
      S.pending = null;
    }
    bindEvents();
    refresh();
  }
  globalThis.OceanV2 = {
    state: S,
    esc,
    money,
    label,
    matchesQueue,
    completeness,
    headers,
    collectData,
    openCase,
    executePending,
    api,
    renderDetail,
    renderGovernance,
    permitted,
    openDialog,
    submitDialog,
  };
  if (!globalThis.OCEAN_V2_NO_BOOT) initialize();
})();
