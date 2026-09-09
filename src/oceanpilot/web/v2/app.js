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
    REGISTER_EVIDENCE: "补充案件材料",
    WITHDRAW_EVIDENCE: "撤回证据",
    REVIEW_EVIDENCE_CONTENT: "人工核验材料内容",
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
    ASSIGN_CASE: "分配案件负责人", RESOLVE_RESPONSE: "核实响应与恢复处理", FINAL_REVIEW: "执行最终审核", VERIFY_OUTCOME: "核实上游结果", REOPEN_CASE: "授权重开案件", REUSE_EVIDENCE: "确认材料适用于当前阶段", PROCESS_ACCEPT: "处理接受责任回执", QUERY_SUBMISSION: "核实上游提交状态", RESOLVE_TASK: "处置未解决任务",
    RESPONSE_REVIEW_REQUIRED: "响应待人工核实", ACCEPT_PROCESSING: "接受责任处理中", ACCEPT_RECOMMENDATION: "待确认接受建议", DOCUMENT_REVISION_REQUIRED: "待修订文书", ON_HOLD: "已暂缓并转交", OUTCOME_VERIFICATION: "结果待核实", UPSTREAM_ACTION_REQUIRED: "待处理上游要求", SUBMISSION_UNCERTAIN: "提交结果待核实",
    CANCELLED: "已取消", WAIVED: "已豁免", SUPERSEDED: "已被替代", HOLD: "暂缓并升级", RETURN_MATERIALS: "退回材料", RETURN_DOCUMENT: "退回文书", RECOMMEND_ACCEPT: "建议接受责任", RESTORE_DECISION: "恢复商户决定", RESTORE_EVIDENCE: "恢复材料任务", CONFIRM_LOSS: "确认权利已失效", FOLLOW_UP: "继续核实跟进", WAIT: "同阶段继续等待", VERIFY: "需要核实", ACTION: "需要进一步行动", FINAL: "已确认终局", NO_ACTION_REQUIRED: "有依据无需渠道处理", NOT_ACCEPTED: "尚未受理", CLAIM: "已接手", RESOLVED: "已解决",
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
    ["agent", "规则与计划"],
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
  const routeCase = decodeURIComponent(location.pathname.match(/\/cases\/([^/]+)\/?$/)?.[1] || "");
  const S = {
    session: null,
    commandSchemas: {},
    listTicket: 0,
    csrfToken: "",
    caseError: null,
    listError: null,
    total: 0,
    limit: 25,
    offset: 0,
    assignedTo: "",
    queueCounts: null,
    searchTimer: null,
    isLibraryPage: location.pathname === "/v2/operations/library",
    caseId: routeCase,
    isCasePage: Boolean(routeCase),
    syncEpoch: 0,
    syncCursor: "",
    syncController: null,
    syncTask: null,
    reconcileTicket: 0,
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
    activity: null,
    agentIndex: {},
    agentLoading: false,
    agentBusy: false,
    agentMessageTicket: 0,
    agentCollapsed: false,
    agentNotice: "",
    agentDrafts: {},
    agentPrepared: "merchant_message",
    agentPoll: null,
    agentPollCount: 0,
    activityTicket: 0,
    agentInboxTicket: 0,
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
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    const bytes = new Uint8Array(16);
    if (globalThis.crypto?.getRandomValues) {
      globalThis.crypto.getRandomValues(bytes);
    } else {
      for (let i = 0; i < bytes.length; i++)
        bytes[i] = Math.floor(Math.random() * 256);
    }
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
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
      actor: S.session?.user?.id || "",
      merchant_id: S.merchantId,
    };
  }
  function headers() {
    return {
      "Content-Type": "application/json",
      ...(S.csrfToken ? { "X-CSRF-Token": S.csrfToken } : {}),
    };
  }
  function actionContract(action, c = S.current) {
    return list(c?.available_actions).find((item) => item.action === action);
  }
  function ownerName(owner) {
    if (owner && typeof owner === "object")
      return owner.display_name || owner.name || label(owner.role) || "待分配";
    return owner ? label(owner) : "待分配负责人";
  }
  function caseOwner(c) {
    return ownerName(c.current_task?.owner || c.current_assignee || c.assignee || c.assignment?.owner || c.assigned_op || c.owner);
  }
  function primaryContract(c) {
    const primary = c.primary_action;
    return typeof primary === "object" && primary ? primary : actionContract(primary, c);
  }
  function renderPrimaryTask(c) {
    const primary = primaryContract(c);
    const actionable = list(c.available_actions).filter((a) => a.visible && a.action !== primary?.action && a.action !== "COMMENT");
    const title = primary?.title || primary?.label || (primary?.action ? label(primary.action) : c.current_task?.action ? c.current_task.title || label(c.current_task.action) : c.work_status === "CLOSED" ? "案件处理已结束" : "等待当前负责人处理");
    const owner = primary?.owner ? ownerName(primary.owner) : caseOwner(c);
    const deadline = c.current_task?.deadline || (surface === "merchant" ? c.deadlines?.merchant : c.deadlines?.internal || c.deadlines?.external);
    return `<section class="current-task" aria-label="当前任务"><div class="current-task-kicker">${primary?.enabled ? "你的下一步" : "当前进展"}<span>负责人 · ${esc(owner)}</span></div><h3>${esc(title)}</h3><p>${esc(primary?.reason || primary?.blocked_reason || c.current_task?.reason || c.current_task?.message || (surface === "merchant" ? merchantSituation(c).description : "案件信息和协作消息会自动同步。"))}</p><div class="current-task-footer">${c.work_status === "CLOSED" ? "<span>本案处理已结束</span>" : `<span>当前回应期限 <strong>${esc(date(deadline))}</strong></span>`}${primary?.action ? actionButton(primary.action, primary.label || label(primary.action), { main: true }) : '<a class="button secondary" href="#agentPanel">查看本案共享沟通</a>'}</div>${actionable.length ? `<details class="secondary-actions"><summary>其他操作与条件</summary><div class="action-bar">${actionable.map((a) => actionButton(a.action, a.label || label(a.action), { small: true })).join("")}</div></details>` : ""}</section>`;
  }
  function permitted(action) {
    if (action === "DEMO") return false;
    if (action === "INTAKE") return Boolean(S.session && S.capabilities?.intake_events === true);
    return actionContract(action)?.visible === true;
  }
  function actionButton(action, title, opts = {}) {
    if (!permitted(action)) return "";
    const contract = actionContract(action);
    const choices = contract?.choices?.decision;
    if (opts.data?.decision && Array.isArray(choices) && !choices.some((value) => (typeof value === "object" ? value.value : value) === opts.data.decision)) return "";
    const disabled = opts.disabled || (contract && (!contract.enabled || (contract.revision !== undefined && contract.revision !== S.current?.revision)));
    const reason = disabled ? contract?.blocked_reason || "请等待当前任务完成后再操作。" : "";
    return `<span class="action-control"><button type="button" class="button ${opts.main ? "primary" : "secondary"} ${opts.small ? "small" : ""}" data-action="${esc(action)}"${action === "REGISTER_EVIDENCE" ? " data-upload-materials" : ""}${disabled ? ` disabled title="${esc(reason)}"` : ""}${opts.data ? ` data-command-data="${esc(JSON.stringify(opts.data))}"` : ""}>${esc(title || contract?.label || label(action))}</button>${reason ? `<small class="action-blocked-reason">${esc(reason)}</small>` : ""}</span>`;
  }
  function roleHint(action) {
    const contract = actionContract(action);
    return contract?.blocked_reason || (contract?.owner ? `由 ${ownerName(contract.owner)} 处理` : "当前账号没有此项操作权限");
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
    const { timeoutMs = 20000, signal, ...requestOptions } = options;
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) controller.abort();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(`/api/v2${path}`, {
        ...requestOptions,
        credentials: "same-origin",
        headers: headers(),
        signal: controller.signal,
      });
      const body = await response.json();
      if (!response.ok) {
        const error = new Error(problemMessage(body, response.status));
        error.status = response.status;
        error.body = body;
        error.uncertain = response.status >= 500;
        if (response.status === 401 && path !== "/session/login" && !globalThis.OCEAN_V2_NO_BOOT) {
          stopUpdates();
          location.replace(`/v2/login?next=${encodeURIComponent(location.pathname + location.search)}`);
        }
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
      signal?.removeEventListener("abort", abort);
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
    if (c.evidence_summary) return { present: Number(c.evidence_summary.present || 0), total: Number(c.evidence_summary.required || c.evidence_summary.total || 0) };
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
  function casePageHref(c) {
    return `/v2/${surface}/cases/${encodeURIComponent(c.id)}`;
  }
  function merchantSituation(c) {
    if (c.pending_next_stage) return {
      title: "OceanPayment 正在评估后续处理",
      description: "当前结果仍需跟进，处理团队正在确认可用的后续阶段与要求；如需你补充材料，会在本案告知。",
      owner: "OceanPayment", action: "查看后续处理进展", tab: "outcome",
    };
    const situations = {
      ACCEPT_RECOMMENDATION: ["请核对接受责任的建议", "处理团队提出了接受责任的建议，请查看理由后确认你的决定。", "商户", "查看建议并作决定", "tasks"],
      RESPONSE_REVIEW_REQUIRED: ["回应方式正在由人工核实", "处理团队正在核实剩余权利、期限和恢复处理条件。", "OceanPayment", "查看核实进度", "overview"],
      ACCEPT_PROCESSING: ["正在处理接受责任的后续手续", "你的决定已记录，OceanPayment 正在核对渠道处理与回执。", "OceanPayment", "查看接受处理进度", "outcome"],
      DOCUMENT_REVISION_REQUIRED: ["OceanPayment 正在修订提交文书", "处理团队将按最终审核反馈修订文书，必要时会向你核实事实。", "OceanPayment", "查看处理进展", "overview"],
      ON_HOLD: ["案件已暂缓并转交人工跟进", "本案负责人正在处理待确认事项，进展将在共享沟通中更新。", "OceanPayment", "查看人工跟进", "collaboration"],
      OUTCOME_VERIFICATION: ["上游结果正在核实", "目前还不能确认最终结果，请等待处理团队完成来源核对。", "OceanPayment", "查看结果核实进度", "outcome"],
      UPSTREAM_ACTION_REQUIRED: ["OceanPayment 正在处理上游新要求", "处理团队正在核对上游要求及本案下一步。", "OceanPayment", "查看处理进展", "outcome"],
      SUBMISSION_UNCERTAIN: ["正在确认上游是否受理", "处理团队正在查询原提交的结果，确认前不会重复提交。", "OceanPayment", "查看提交进展", "outcome"],
      MERCHANT_ACTION_REQUIRED: ["请确认如何回应这笔争议", "核对交易事实后，选择接受责任或提出抗辩。", "商户", "确认处理决定", "tasks"],
      EVIDENCE_COLLECTING: ["请按清单准备抗辩材料", "材料提交给 OceanPayment 后，由处理团队审核并推进。", "商户", "继续准备材料", "evidence"],
      MERCHANT_REVISION_REQUIRED: ["OceanPayment 需要你补充材料", "查看审核反馈，补齐指定材料后再次提交。", "商户", "查看补证要求", "tasks"],
      EVIDENCE_SUBMITTED: ["材料已交给 OceanPayment", "处理团队将核对材料；如需补充，会在这里告知你。", "OceanPayment", "查看已提交材料", "evidence"],
      OP_REVIEW: ["OceanPayment 正在审核", "你可以查看已有材料与消息，等待处理团队反馈。", "OceanPayment", "查看处理进展", "overview"],
      READY_TO_SUBMIT: ["抗辩材料已通过审核", "OceanPayment 正在准备向上游正式提交。", "OceanPayment", "查看处理进展", "overview"],
      SUBMISSION_PENDING_CONFIRMATION: ["等待最终提交确认", "OceanPayment 正在核对正式提交的内容。", "OceanPayment", "查看处理进展", "overview"],
      SUBMITTED: ["OceanPayment 已提交回应", "正在等待上游处理结果，提交回执由处理团队留存。", "上游处理机构", "查看处理结果", "outcome"],
      WAITING_UPSTREAM: ["正在等待上游结果", "收到新结果后，这个案件会自动更新。", "上游处理机构", "查看处理结果", "outcome"],
      FINANCIAL_RECONCILIATION: ["正在核对资金影响", "争议结果与实际资金分开核对，完成后会通知你。", "OceanPayment", "查看结果与资金", "outcome"],
      CLOSED: ["这笔争议已处理完成", "你可以回看处理结果、材料和与团队的往来。", "已完成", "查看处理结果", "outcome"],
    };
    const value = situations[c.work_status] || ["OceanPayment 正在准备处理要求", "处理团队正在核对规则与下一步任务，暂时无需你操作。", "OceanPayment", "查看案件", "overview"];
    return { title: value[0], description: value[1], owner: value[2], action: value[3], tab: value[4] };
  }
  function caseFollowupText(c) {
    if (c.pending_next_stage) return "待确认后续阶段";
    if (Number(c.stage_number) > 1) return `已进入第 ${Number(c.stage_number)} 轮 · ${label(c.stage)}`;
    if (c.finality === "FINAL_CONFIRMED") return "已终局";
    return "等待上游确认";
  }
  function merchantReason(c) {
    const reason = {
      "10.4": "持卡人对这笔交易的授权提出异议。请核对交易收据、身份验证及授权记录。",
      "13.1": "持卡人表示没有收到商品或服务。请核对物流、交付凭据及双方沟通记录。",
      "4853": "这笔交易收到商品或服务相关争议。请结合具体投诉，核对履约事实及相关沟通记录。",
    }[String(c.reason_code)];
    return reason || "OceanPayment 收到了这笔交易的争议。请根据已确认的案件要求，核对交易事实并准备回应。";
  }
  function latestCaseFeedback(c) {
    return list(c.public_feedback || c.collaboration).filter((m) => (m.message || m.reason) && (m.role || m.actor_role) !== "MERCHANT").at(-1);
  }
  function merchantCanRespond(c) {
    return list(c.available_actions).some(action => ["MERCHANT_DECISION", "REGISTER_EVIDENCE"].includes(action.action) && action.visible && action.enabled);
  }
  function renderMerchantOverviewPage(c, p) {
    const situation = merchantSituation(c);
    const r = completeness(c);
    const feedback = latestCaseFeedback(c);
    const decisionActions = '<a class="button secondary" href="#agentPanel">在本案提问或联系负责人</a>';
    return `<div class="customer-context-grid"><section><h3>为什么发生争议？</h3><p>${esc(merchantReason(c))}</p><small>${esc(c.scheme)} · 原因码 ${esc(c.reason_code)} · 具体材料要求以已确认规则为准</small></section><section><h3>现在由谁处理？</h3><p class="customer-owner">${esc(caseOwner(c))}</p><small>OceanPilot 在本案中帮助你理解要求、整理材料和准备回应。</small></section></div><dl class="customer-facts"><div><dt>你的回应期限</dt><dd>${esc(date(p?.deadlines?.merchant || c.deadlines?.merchant))}</dd></div><div><dt>你的处理决定</dt><dd>${esc(label(c.merchant_decision))}</dd></div><div><dt>已登记材料</dt><dd>${r.total ? `${r.present} / ${r.total} 项` : "等待确认材料要求"}</dd></div><div><dt>交易编号</dt><dd>${esc(c.transaction_id || "尚未提供")}</dd></div></dl>${feedback ? `<div class="customer-latest"><div class="section-heading"><h3>OceanPayment 最新消息</h3><span>${esc(date(feedback.at || feedback.created_at))}</span></div><p>${esc(feedback.message || feedback.reason)}</p><button class="button secondary small" data-tab="collaboration">查看往来与回复 →</button></div>` : ""}`;
  }
  function renderMerchantTaskPage(c, p) {
    const tasks = list(c.tasks).filter((t) => ["DECISION", "EVIDENCE", "REVISION"].includes(t.type));
    const review = list(c.public_feedback || c.reviews).filter((r) => r.decision === "REVISION" || r.kind === "REVISION" || r.type === "REVISION").at(-1);
    const situation = merchantSituation(c);
    return `${section("我的待办", situation.description)}${review && c.work_status === "MERCHANT_REVISION_REQUIRED" ? `<div class="callout"><strong>OceanPayment 的补证要求</strong>${esc(review.reason || review.message || "请按任务清单补充材料。")}</div>` : ""}<div class="customer-task-list">${tasks.map((t) => `<div class="task-row"><span class="check-mark ${t.status === "COMPLETED" ? "done" : ""}">${t.status === "COMPLETED" ? "✓" : "○"}</span><div class="row-content"><div class="row-title">${esc(label(t.type))}</div><div class="row-subtitle">${esc(t.message || (t.type === "DECISION" ? "确认你是否继续抗辩。" : "按本案清单准备相关材料。"))}</div></div>${badge(t.status)}</div>`).join("") || empty("当前没有需要你完成的任务。收到新要求后会自动更新。")}</div><div class="customer-task-deadline">你的回应期限 <strong>${esc(date(p?.deadlines?.merchant || c.deadlines?.merchant))}</strong></div><div class="action-bar">${merchantCanRespond(c) ? actionButton("MERCHANT_DECISION", c.merchant_decision === "NONE" ? "确认我的处理决定" : "查看或调整处理决定", { primary: c.merchant_decision === "NONE" }) : ""}${merchantCanRespond(c) && c.merchant_decision === "CONTEST" ? '<button class="button primary" data-tab="evidence">准备并提交材料 →</button>' : ""}${actionButton("COMMENT", "向 OceanPayment 补充说明")}</div><div class="customer-process-note">你负责决定与事实材料；OceanPayment 负责审核和向上游提交。OceanPilot 会根据本案变化更新建议。</div>`;
  }
  function renderMerchantEvidencePage(c, p) {
    const checklist = list(p?.checklist);
    const evidence = list(c.evidence);
    const canEdit = actionContract("REGISTER_EVIDENCE", c)?.enabled === true;
    const missing = checklist.filter((i) => (i.required || i.critical) && !i.present);
    const ready = canEdit && checklist.length && !missing.length;
    const submit = actionButton("SUBMIT_EVIDENCE", "提交材料给 OceanPayment");
    return `${section("准备抗辩材料", "每项材料对应本案的一项要求。上传文件后，OceanPilot 会结合内容检查清单；不明确之处交由人工判断。", canEdit ? actionButton("REGISTER_EVIDENCE", "＋ 上传案件材料", { small: true }) : "")}<p class="evidence-mode-note">在“本案文件与材料”上传文本、JSON、CSV，并查看已解析内容与核查反馈。历史引用保留供核对。</p>${checklist.map((item) => `<div class="evidence-row"><span class="check-mark ${item.present ? "done" : ""}">${item.present ? "✓" : "○"}</span><div class="row-content"><div class="row-title">${esc(item.label || item.code)} ${item.critical ? '<span class="badge amber">关键材料</span>' : ""}</div><div class="row-subtitle">${esc(item.why || "请提供能说明本案交易事实的相关记录。")}</div></div><div class="row-actions">${item.present ? badge("COMPLETED", "已登记") : badge("OPEN", "待补充")}${!item.present && canEdit ? actionButton("REGISTER_EVIDENCE", "补充", { small: true, data: { code: item.code, title: item.label || item.code } }) : ""}</div></div>`).join("") || empty("OceanPayment 尚未确认本案材料要求，请等待处理团队反馈。")}${canEdit ? `<div class="customer-submit"><div><strong>${missing.length ? `还需补充 ${missing.length} 项必要材料` : checklist.length ? "清单材料已登记，可提交团队审核" : "材料要求尚未确认"}</strong><p>提交后由 OceanPayment 审核；此操作不会向上游正式提交抗辩。</p></div>${submit}</div>` : `<div class="callout">${c.merchant_decision !== "CONTEST" ? "请先在我的待办中确认处理决定。" : "材料已交由 OceanPayment 处理。若收到补证要求，你可以继续补充。"}</div>`}${section("你已登记的材料", `${evidence.filter((e) => e.active !== false).length} 项有效材料；撤回会保留记录`)}${evidence.map((e) => `<div class="evidence-row"><span class="row-icon">▧</span><div class="row-content"><div class="row-title">${esc(e.title || e.code)} ${e.active === false ? badge("INVALIDATED", "已撤回") : ""}</div><div class="row-subtitle">${esc(e.reference)}<br>${esc(date(e.registered_at))}${e.notes ? `<br>${esc(e.notes)}` : ""}</div></div>${canEdit && e.active !== false ? actionButton("WITHDRAW_EVIDENCE", "撤回", { small: true, data: { evidence_id: e.id } }) : ""}</div>`).join("") || empty("还没有登记材料。")}`;
  }
  function renderMerchantFeedbackPage(c) {
    const messages = list(c.collaboration).slice().reverse();
    return `${section("与 OceanPayment 的往来", "这里的消息随案件同步，处理团队可以看到你的回复。", actionButton("COMMENT", "给处理团队留言", { small: true }))}${messages.map((m) => { const merchant = (m.role || m.actor_role) === "MERCHANT"; const sender = m.actor?.display_name || m.display_name || m.actor_name || ((m.role || m.actor_role) === "AGENT" ? "OceanPilot" : merchant ? "商户协作人" : "OceanPayment"); return `<div class="message ${merchant ? "from-merchant" : "from-operations"}"><header><strong>${esc(sender)}</strong><time>${esc(date(m.created_at || m.timestamp || m.at))}</time></header><p>${esc(m.message || m.text || label(m.type))}</p>${m.delivery_status ? `<div class="row-subtitle">${esc(label(m.delivery_status))}</div>` : ""}</div>`; }).join("") || empty("尚无往来消息。你可以向处理团队说明案件情况。")}`;
  }
  function renderMerchantOutcomePage(c) {
    const confirmed = c.finality === "FINAL_CONFIRMED";
    const hasResult = c.business_outcome && c.business_outcome !== "UNKNOWN";
    const moneyDone = ["RECONCILED", "NOT_APPLICABLE"].includes(c.financial_status);
    const moneyText = c.financial_status === "DISCREPANCY" ? "资金存在差异，OceanPayment 正在核对" : moneyDone ? label(c.financial_status) : confirmed ? "结果已确认，资金仍在核对" : "待处理结果明确后核对资金影响";
    const summary = c.financial_summary || {};
    const publicAmounts = [["supported_minor", "已确认支持金额"], ["liable_minor", "已确认承担金额"], ["credit_minor", "已登记返还"], ["debit_minor", "已登记扣款"], ["fee_minor", "已登记费用"], ["refund_minor", "已登记退款"], ["net_minor", "已登记资金净额"]].filter(([key]) => Number.isSafeInteger(summary[key]));
    const moneyBoundary = summary.boundary === "Synthetic event reconciliation; outcome allocation is not a second ledger entry" ? "本页展示合成资金核对；支持金额与责任金额用于解释结果，不重复计入资金流水。" : summary.boundary;
    const amounts = publicAmounts.length ? `${section("公开资金摘要", moneyBoundary || "依据本案已登记的资金记录展示；资金核对状态以本页为准。")}<dl class="customer-facts">${publicAmounts.map(([key,title])=>`<div><dt>${esc(title)}</dt><dd>${esc(money(summary[key],summary.currency || c.currency))}</dd></div>`).join("")}</dl>` : "";
    return `<div class="customer-result"><span class="customer-next-kicker">处理结果</span><h3>${hasResult ? esc(label(c.business_outcome)) : "尚未收到确定结果"}</h3><p>${confirmed ? "上游已确认终局结果。资金核对情况单独列在下方。" : "当前结果尚非终局，OceanPayment 会继续跟踪后续处理。"}</p>${badge(c.work_status)}</div><dl class="customer-facts"><div><dt>当前进度</dt><dd>${esc(label(c.work_status))}</dd></div><div><dt>处理阶段</dt><dd>${esc(label(c.stage))}</dd></div><div><dt>争议金额</dt><dd>${esc(money(c.amount_minor, c.currency))}</dd></div><div><dt>资金处理</dt><dd>${esc(moneyText)}</dd></div></dl>${amounts}<div class="action-bar"><a class="button secondary" href="#agentPanel">查看处理团队通知与本案沟通</a></div>`;
  }
  function renderMetrics() {
    const node = $("metrics");
    node.hidden = Boolean(S.isCasePage);
    if (node.hidden) return;
    const count = (queue) => S.queueCounts?.[queue] ?? (S.queue === queue ? S.total : "—");
    const values = surface === "merchant"
      ? [["待我决定", count("MERCHANT"), "MERCHANT", "核对事实并确认如何回应"], ["待我补充", count("EVIDENCE"), "EVIDENCE", "补充当前要求的材料"], ["处理中", count("PROCESSING"), "PROCESSING", "查看处理团队的进展"], ["已结束", count("CLOSED"), "CLOSED", "回看结果与处理记录"]]
      : [["当前工作队列", S.total, "ALL", "按负责人及当前任务组织"], ["需要关注", count("URGENT"), "URGENT", "时限风险或规则待确认"], ["等待审核", count("REVIEW"), "REVIEW", "当前材料与人工判断"], ["资金待核对", count("FINANCIAL"), "FINANCIAL", "终局结果与资金分别确认"]];
    node.innerHTML = values.map(([title, value, queue, foot]) => `<button class="metric" data-queue="${queue}"><div class="metric-label">${title}<span class="metric-arrow">↗</span></div><div class="metric-value">${value}<small>件</small></div><div class="metric-foot ${queue === "URGENT" && value ? "attention" : ""}">${foot}</div></button>`).join("");
  }
  function renderQueue() {
    const merchant = surface === "merchant";
    const views = merchant ? [["ALL", "我的全部案件"], ["MERCHANT", "待我决定"], ["EVIDENCE", "待我补充"], ["PROCESSING", "处理中"], ["CLOSED", "已结束"]] : queueViews;
    const visible = S.cases.slice().sort((a, b) => {
      if (!merchant) return 0;
      const taskOrder = (c) => merchantSituation(c).owner === "商户" ? 0 : c.work_status === "CLOSED" ? 2 : 1;
      return taskOrder(a) - taskOrder(b) || (new Date(a.deadlines?.merchant || "9999-01-01") - new Date(b.deadlines?.merchant || "9999-01-01"));
    });
    $("queueTitle").textContent = views.find((v) => v[0] === S.queue)?.[1] || (merchant ? "我的案件" : "全部案件");
    $("queueCount").textContent = S.total;
    $("queueNav").innerHTML = views.map(([key, title]) => `<button class="${S.queue === key ? "active" : ""}" data-queue="${key}"><span class="queue-dot"></span>${title}${S.queueCounts?.[key] !== undefined ? `<span class="count">${esc(S.queueCounts[key])}</span>` : ""}</button>`).join("");
    $("queuePagination").innerHTML = `<span>共 ${S.total} 件 · 第 ${Math.floor(S.offset / S.limit) + 1} 页</span><div><button class="button secondary small" data-page="prev"${S.offset === 0 ? " disabled" : ""}>上一页</button><button class="button secondary small" data-page="next"${S.offset + S.limit >= S.total ? " disabled" : ""}>下一页</button></div>`;
    $("caseSearch").placeholder = merchant ? "搜索案件或交易编号" : "搜索案件、商户、交易或原因码";
    if (!visible.length) {
      if (S.listError) { $("caseList").innerHTML = renderReadError(S.listError, false); return; }
      $("caseList").innerHTML = `<div class="empty-state list-empty"><div class="empty-symbol">⌕</div><h3>${S.cases.length ? "没有符合条件的案件" : merchant ? "暂时没有需要处理的争议" : "暂无争议案件"}</h3><p>${S.cases.length ? "试试其他筛选条件或搜索内容。" : merchant ? "OceanPayment 发布处理要求后，你会在这里看到自己的案件与待办。" : "接收上游事件或加载合成案例后，案件会进入工作队列。"}</p></div>`;
      return;
    }
    if (merchant) {
      $("caseList").innerHTML = `<div class="merchant-case-list">${visible.map((c) => {
        const situation = merchantSituation(c), r = completeness(c), feedback = latestCaseFeedback(c);
        return `<a class="merchant-case-link" href="${esc(casePageHref(c))}"><div class="merchant-case-main"><div class="merchant-case-top"><span class="case-id">${esc(c.id)}</span>${badge(c.work_status, situation.owner === "商户" ? "待你处理" : label(c.work_status))}</div><h3>${esc(situation.title)}</h3><p>${esc(c.transaction_id || "交易编号待提供")} · ${esc(c.scheme)} ${esc(c.reason_code)}</p><div class="merchant-case-task"><span>${situation.owner === "商户" ? "你的下一步" : "当前进展"}</span><strong>${esc(situation.action)}</strong>${situation.owner === "商户" ? `<span class="merchant-case-deadline">截止 ${esc(date(c.deadlines?.merchant))}</span>` : `<span>由 ${esc(situation.owner)} 处理</span>`}</div>${feedback ? `<div class="merchant-case-feedback">OceanPayment：${esc(feedback.message || feedback.reason)}</div>` : ""}</div><div class="merchant-case-aside"><strong>${esc(money(c.amount_minor, c.currency))}</strong><span>${r.total ? `材料 ${r.present} / ${r.total} 项` : `${Number(c.task_summary?.for_me || 0)} 项我的待办`}</span><span class="case-open-label">进入案件 <b>→</b></span></div></a>`;
      }).join("")}</div>`;
      return;
    }
    $("caseList").innerHTML = `<div class="operations-table-scroll"><table class="operations-case-table"><thead><tr><th>案件 / 商户</th><th>争议与金额</th><th>阶段 / 状态</th><th>商户决定</th><th>证据 / 审核</th><th>上游 / 后续阶段</th><th>资金</th><th>处理期限</th><th><span class="sr-only">打开案件</span></th></tr></thead><tbody>${visible.map((c) => {
      const r = completeness(c), review = list(c.reviews).at(-1), submission = list(c.submissions).at(-1);
      const financial = c.finality === "FINAL_CONFIRMED" || c.work_status === "FINANCIAL_RECONCILIATION" || list(c.financial_events).length ? badge(c.financial_status) : '<span class="table-muted">尚待结果</span>';
      return `<tr><td><a class="table-case-link" href="${esc(casePageHref(c))}">${esc(c.id)}</a><span class="table-sub">${esc(c.merchant_id)}</span></td><td><strong>${esc(money(c.amount_minor, c.currency))}</strong><span class="table-sub">${esc(c.scheme)} · ${esc(c.reason_code)}</span></td><td>${badge(c.work_status)}<span class="table-sub">${esc(label(c.stage))}</span></td><td>${badge(c.merchant_decision)}</td><td><span>${r.total ? `${r.present} / ${r.total} 项材料` : "打开查看材料"}</span><span class="table-sub">${review ? esc(label(review.decision)) : `${Number(c.task_summary?.for_me || 0)} 项分配给我的待办`}</span></td><td><span>${submission ? "已有提交回执" : "打开查看上游记录"}</span><span class="table-sub">${c.business_outcome !== "UNKNOWN" ? esc(label(c.business_outcome)) + " · " : ""}${esc(caseFollowupText(c))}</span></td><td>${financial}</td><td><span>${esc(date(c.deadlines?.external || c.deadlines?.merchant))}</span><span class="table-sub">${esc(caseOwner(c))} · v${esc(c.revision)}</span></td><td><a class="table-open-link" href="${esc(casePageHref(c))}" aria-label="打开案件 ${esc(c.id)}">→</a></td></tr>`;
    }).join("")}</tbody></table></div>`;
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
    const acceptPath = ["ACCEPT", "AUTHORIZED_WAIVER"].includes(c.merchant_decision) || c.work_status === "ACCEPT_PROCESSING";
    const lifecycle = acceptPath
      ? [["RECEIVED", "接收分流"], ["MERCHANT_ACTION_REQUIRED", "商户响应"], ["ACCEPT_PROCESSING", "接受处理"], ["SUBMITTED", "上游与资金"], ["CLOSED", "终局关闭"]]
      : [["RECEIVED", "接收分流"], ["MERCHANT_ACTION_REQUIRED", "商户响应"], ["EVIDENCE_COLLECTING", "证据收集"], ["OP_REVIEW", "人工审核"], ["SUBMITTED", "上游与资金"], ["CLOSED", "终局关闭"]];
    const phaseByStatus = {
      RECEIVED: "RECEIVED", TRIAGED: "RECEIVED",
      MERCHANT_ACTION_REQUIRED: "MERCHANT_ACTION_REQUIRED", RESPONSE_REVIEW_REQUIRED: "MERCHANT_ACTION_REQUIRED", ACCEPT_RECOMMENDATION: "MERCHANT_ACTION_REQUIRED",
      EVIDENCE_COLLECTING: "EVIDENCE_COLLECTING", MERCHANT_REVISION_REQUIRED: "EVIDENCE_COLLECTING",
      EVIDENCE_SUBMITTED: "OP_REVIEW", OP_REVIEW: "OP_REVIEW", READY_TO_SUBMIT: "OP_REVIEW", SUBMISSION_PENDING_CONFIRMATION: "OP_REVIEW", DOCUMENT_REVISION_REQUIRED: "OP_REVIEW", ON_HOLD: "OP_REVIEW",
      ACCEPT_PROCESSING: "ACCEPT_PROCESSING",
      SUBMITTED: "SUBMITTED", WAITING_UPSTREAM: "SUBMITTED", FINANCIAL_RECONCILIATION: "SUBMITTED", OUTCOME_VERIFICATION: "SUBMITTED", UPSTREAM_ACTION_REQUIRED: "SUBMITTED", SUBMISSION_UNCERTAIN: "SUBMITTED",
      CLOSED: "CLOSED",
    };
    const currentPhase = phaseByStatus[c.work_status];
    const preparation = acceptPath
      ? '<div class="callout"><strong>接受 / 授权放弃路径</strong>本路径跳过抗辩材料收集和材料包终审，仍需核对渠道处理、上游结果及资金。</div>'
      : `${section("证据准备度", "登记清单完整度，不代表证据真实性或胜诉概率")}<div class="progress-row"><span>已满足 ${esc(p?.readiness?.submitted ?? completeness(c).present)} / ${esc(p?.readiness?.required ?? completeness(c).total)} 项要求</span><strong>${percent}%</strong></div><div class="progress-track"><div class="progress-fill" style="width:${percent}%"></div></div>`;
    return `<div class="agent-summary"><div class="agent-summary-header"><span class="agent-symbol">✧</span>案件推进建议 <span class="badge green">确定性 Agent</span></div><p>${esc(p?.summary || "正在读取案件计划。所有操作均经过权限、规则与版本校验。")}</p><div class="agent-summary-footer"><span>基于案件 v${esc(c.revision)} · 规则与证据可追溯</span></div></div>${preparation}${next ? `<div class="callout ${p?.blockers?.length ? "" : "green"}"><strong>下一步 · ${esc(label(next.action))}</strong>${esc(next.reason || "")}<br>${esc(roleHint(next.action))}</div>` : ""}<div class="two-column"><div class="info-card"><h4>规则与来源</h4>${fact("规则状态", label(rule.conflict_status || p?.rule_status || "NEEDS_CONFIRMATION"))}${fact("版本", rule.rule_version || "尚未匹配")}${fact("来源", rule.source_id || "尚未确认")}${fact("适用阶段", label(c.stage))}${actionButton("CONFIRM_RULE", "查看并确认规则", { small: true })}</div><div class="info-card"><h4>案件时间窗</h4>${fact("商户目标", date(deadlines.merchant || deadlines.merchant_deadline))}${fact("OP 内部", date(deadlines.internal || deadlines.internal_deadline))}${fact("外部截止", date(deadlines.external || deadlines.external_deadline))}${fact("时限来源", deadlines.source || "尚未确认")}</div></div><div class="info-card" style="margin-top:15px"><h4>生命周期</h4><p class="section-note">当前环节：${esc(label(c.work_status))}。环节定位不代表前序材料或审批均已完成。</p><div class="timeline-mini">${lifecycle.map(([step,title]) => `<div class="timeline-step ${step === currentPhase ? "current" : ""}" data-lifecycle-step="${step}"${step === currentPhase ? ' aria-current="step"' : ""}>${title}</div>`).join("")}</div></div>`;
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
  function renderMerchantTasks(c, p) {
    const explanation =
      {
        10.4: "持卡人对这笔交易的授权提出异议。你可以核对交易收据、身份验证与授权相关记录。",
        13.1: "持卡人表示没有收到商品或服务。你可以准备物流、交付凭据和双方沟通记录。",
        4853: "持卡人对商品或服务与约定是否一致提出异议。你可以核对商品描述、履约记录和退款政策。",
      }[c.reason_code] ||
      "OceanPayment 收到了这笔交易的争议，需要你提供事实与处理决定。";
    const tasks = list(c.tasks).filter((t) =>
      ["DECISION", "EVIDENCE", "REVISION"].includes(t.type),
    );
    const review = list(c.reviews)
      .filter((r) => r.type === "EVIDENCE")
      .at(-1);
    const feedback = list(c.collaboration)
      .filter((m) => m.role !== "MERCHANT" && m.message)
      .slice(-2);
    const canRespond = [
      "MERCHANT_ACTION_REQUIRED",
      "EVIDENCE_COLLECTING",
      "MERCHANT_REVISION_REQUIRED",
    ].includes(c.work_status);
    return `<div class="merchant-brief"><span class="merchant-brief-icon">↙</span><div><h3>这笔争议为什么需要你回应</h3><p>${esc(explanation)}</p><small>OceanPayment 负责案件处理，OceanPilot 帮你理解要求与准备回应。</small></div></div><div class="merchant-deadline">你的目标回应时间 <strong>${esc(date(p?.deadlines?.merchant || c.deadlines?.merchant))}</strong></div>${section("我的待办", c.merchant_decision === "NONE" ? "先确认接受责任还是继续抗辩，再按清单回应。" : `你已选择：${label(c.merchant_decision)}。`)}${tasks.map((t) => `<div class="task-row"><span class="check-mark ${t.status === "COMPLETED" ? "done" : ""}">${t.status === "COMPLETED" ? "✓" : "○"}</span><div class="row-content"><div class="row-title">${esc(label(t.type))}</div><div class="row-subtitle">${esc(t.message || "")}</div></div>${badge(t.status)}</div>`).join("") || empty("暂时没有需要你处理的新任务。你仍可向 OceanPilot 提问或补充协作消息。")}<div class="action-bar">${canRespond ? actionButton("MERCHANT_DECISION", "确认我的处理决定", { primary: c.merchant_decision === "NONE" }) : ""}${canRespond && c.merchant_decision === "CONTEST" ? actionButton("REGISTER_EVIDENCE", "补充证据", { primary: true }) + actionButton("SUBMIT_EVIDENCE", "提交给 OceanPayment") : ""}${actionButton("COMMENT", "补充说明")}</div>${c.merchant_decision === "CONTEST" ? `<div class="merchant-evidence-progress"><span>证据准备</span><strong>${esc(p?.readiness?.submitted ?? 0)} / ${esc(p?.readiness?.required ?? 0)} 项</strong><button type="button" data-tab="evidence">查看准备清单 →</button></div>` : ""}${section("OceanPayment 的反馈", "你和处理团队的最新往来，共享同一个案件。")}${review ? `<div class="merchant-feedback"><span class="actor-avatar operations">OP</span><div><strong>OceanPayment 审核反馈 · ${esc(label(review.decision))}</strong><p>${esc(review.reason)}</p><small>${date(review.at || review.created_at)}</small></div></div>` : ""}${feedback.map((m) => `<div class="merchant-feedback"><span class="actor-avatar operations">OP</span><div><strong>${m.type === "TASK_PUBLISHED" ? "处理团队向你发布任务" : "OceanPayment 案件消息"}</strong><p>${esc(m.message)}</p><small>${date(m.at || m.created_at)}</small></div></div>`).join("") || (!review ? empty("后续审核意见与处理进展会显示在这里。") : "")}<button class="button secondary small" data-tab="collaboration">查看全部往来 / 回复团队 →</button>`;
  }
  function renderEvidence(c, p) {
    const checklist = list(p?.checklist);
    const evidence = list(c.evidence);
    return `${section("规则要求的证据", "上传实际文件并核查其中的交易事实；历史引用仅供查看", actionButton("REGISTER_EVIDENCE", "＋ 上传材料", { small: true }))}${checklist.map((item) => `<div class="evidence-row"><span class="check-mark ${item.present ? "done" : ""}">${item.present ? "✓" : "○"}</span><div class="row-content"><div class="row-title">${esc(item.label || item.code)} ${item.critical ? '<span class="badge amber">关键证据</span>' : ""}</div><div class="row-subtitle">${esc(item.why || item.code)}</div></div><div class="row-actions">${item.present ? badge("COMPLETED", "已登记") : badge("PENDING", "缺失")}${!item.present ? actionButton("REGISTER_EVIDENCE", "补充", { small: true, data: { code: item.code, title: item.label || item.code } }) : ""}</div></div>`).join("") || empty("规则清单尚未确定。请先确认规则来源。")}<div class="action-bar">${actionButton("SUBMIT_EVIDENCE", "提交证据供 OP 审核", { primary: true })}</div>${section("证据登记记录", `${evidence.filter((e) => e.active !== false).length} 项有效 · 撤回保留历史并使旧证据包失效`)}${evidence.map((e) => `<div class="evidence-row"><span class="row-icon">▧</span><div class="row-content"><div class="row-title">${esc(e.title || e.code)} ${e.active === false ? badge("INVALIDATED", "已撤回") : ""}</div><div class="row-subtitle">${esc(e.reference)}<br>${esc(label(e.source_channel || "PORTAL"))} · ${date(e.registered_at)} · ${esc(e.registered_by || "")}${e.notes ? `<br>${esc(e.notes)}` : ""}</div></div>${e.active !== false ? actionButton("WITHDRAW_EVIDENCE", "撤回", { small: true, data: { evidence_id: e.id } }) : ""}</div>`).join("") || empty("尚无证据登记记录。")}`;
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
            `<div class="record-row"><span class="row-icon">◇</span><div class="row-content"><div class="row-title">${esc(label(r.decision))} · ${esc(r.reviewer || r.actor || r.reviewed_by || "")}</div><div class="row-subtitle">${esc(r.reason || "")}<br>${date(r.created_at || r.reviewed_at || r.at)} · v${esc(r.revision || r.case_revision || "—")}</div></div>${badge(r.invalidated || r.valid === false || r.status === "INVALIDATED" ? "INVALIDATED" : r.decision, r.invalidated || r.valid === false || r.status === "INVALIDATED" ? "历史审核 · 已失效" : undefined)}${r.invalidated_reason ? `<p>${esc(r.invalidated_reason)}</p>` : ""}</div>`,
        )
        .join("") || empty("尚无人工审核记录。关键证据缺失时不能通过审核。")
    }${section("证据包与最终审批", "草稿经主管确认 PII 检查后冻结；变更证据将使旧包失效")}<div class="action-bar">${actionButton("APPROVE_PACKAGE", "终审并冻结", { primary: true })}${actionButton("SUBMIT", "确认向上游提交（Mock）")}</div>${
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
    const close = c.close_gate || {};
    const gates = [["上游确认终局", close.finality_confirmed === true], ["资金已核对或不适用", close.financial_reconciled === true], ["必要任务已妥善解决", close.required_tasks_resolved === true], ["商户已收到当前结果与资金通知", close.notification_current === true]];
    return `${section("上诉与后续阶段", "根据上游结果核对后续权利，按实际规则确认是否继续")}
      <div class="callout"><strong>${c.pending_next_stage ? "需要确认是否继续后续阶段" : c.stage_number > 1 ? `已进入第 ${esc(c.stage_number)} 轮 · ${esc(label(c.stage))}` : c.finality === "FINAL_CONFIRMED" ? "上游已确认终局" : "等待上游结果与后续权利确认"}</strong>${c.pending_next_stage ? "当前结果不是终局。请核对上游来源、可用后续阶段和期限，再确认新阶段。" : "后续阶段的建立依赖明确的非终局上游事件；演示不代表已向真实机构申请上诉。"}</div>
      ${list(c.stage_history).length ? `<details><summary>查看前序阶段与结果（${list(c.stage_history).length} 轮）</summary>${list(c.stage_history).map(h => `<div class="record-row">${esc(label(h.stage))} · ${esc(label(h.business_outcome))} · ${esc(label(h.finality))}</div>`).join("")}</details>` : ""}${section("上游结果与阶段", "按已核实事件区分继续等待、待核实、需要行动和后续阶段")}<div class="two-column" style="margin-top:0"><div class="info-card">${fact("业务结果", label(c.business_outcome))}${fact("终局状态", label(c.finality))}</div><div class="info-card">${fact("当前阶段", label(c.stage))}${fact("资金状态", label(c.financial_status))}</div></div><div class="action-bar">${actionButton("RECORD_OUTCOME", "登记上游结果", { primary: true })}${actionButton("NEXT_STAGE", "确认并进入后续阶段")}</div>${list(
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
    const target = $("caseDetail"), c = S.current;
    target.hidden = !S.isCasePage;
    if (!S.isCasePage) { target.innerHTML = ""; return; }
    if (!c) {
      target.innerHTML = S.caseError ? renderReadError(S.caseError, true) : `<div class="empty-state"><div class="empty-symbol">◈</div><h2>正在读取这个案件</h2><p>案件详情与 OceanPilot 会在读取完成后显示。</p><a class="button secondary" href="/v2/${surface}">返回案件列表</a></div>`;
      return;
    }
    const p = S.plan, merchant = surface === "merchant";
    const renderers = merchant
      ? { overview: () => renderMerchantOverviewPage(c, p), tasks: () => renderMerchantTaskPage(c, p), evidence: () => renderMerchantEvidencePage(c, p), collaboration: () => renderMerchantFeedbackPage(c), outcome: () => renderMerchantOutcomePage(c) }
      : { overview: () => renderOverview(c, p), tasks: () => renderTasks(c), evidence: () => renderEvidence(c, p), agent: () => renderAgent(c, p), collaboration: () => renderCollaboration(c), review: () => renderReview(c), outcome: () => renderOutcome(c), audit: () => renderAudit(c) };
    const visibleTabs = merchant ? [["overview", "案件概况"], ["tasks", "我的待办"], ["evidence", "抗辩材料"], ["collaboration", "与运营沟通"], ["outcome", "结果与资金"]] : tabs;
    const activeTab = visibleTabs.some(([key]) => key === S.tab) ? S.tab : "overview";
    const dimensions = merchant ? [["当前进度", c.work_status], ["我的决定", c.merchant_decision]] : [["争议阶段", c.stage], ["工作状态", c.work_status], ["商户决定", c.merchant_decision], ["业务结果", c.business_outcome], ["终局状态", c.finality], ["资金状态", c.financial_status]];
    target.innerHTML = `<div class="detail-header"><div class="detail-topline"><span class="case-id">${esc(c.id)}</span><span>v${esc(c.revision)} · 合成演示</span></div><div class="detail-title"><div><h2>${merchant ? "交易争议" : esc(c.merchant_id)}</h2><p>${merchant ? esc(c.transaction_id || "交易编号待提供") : `${esc(c.scheme)} · 原因码 ${esc(c.reason_code)}`}</p></div><div class="detail-amount">${esc(money(c.amount_minor, c.currency))}</div></div><div class="case-facts">${merchant ? `<span>${esc(c.scheme)} · ${esc(c.reason_code)}</span><span>处理团队 <strong>OceanPayment</strong></span>` : `<span>交易 <strong>${esc(c.transaction_id || "—")}</strong></span><span>渠道 <strong>${esc(c.channel)}</strong></span><span>负责人 <strong>${esc(caseOwner(c))}</strong></span>`}</div>${merchant ? `<p class="case-reason-summary">${esc(merchantReason(c))}</p>` : ""}</div><div class="dimension-strip">${dimensions.map(([key, value]) => `<div class="dimension"><label>${key}</label>${badge(value)}</div>`).join("")}</div>${renderPrimaryTask(c)}<nav class="detail-tabs" aria-label="${merchant ? "我的案件" : "案件详情"}">${visibleTabs.map(([key, title]) => `<button class="detail-tab ${activeTab === key ? "active" : ""}" data-tab="${key}" aria-current="${activeTab === key ? "page" : "false"}">${title}</button>`).join("")}</nav><div class="detail-content">${renderers[activeTab]()}${renderCaseReference(c)}</div>`;
  }
  function renderGovernance() {
    const g = S.governance;
    if (!g) {
      $("governanceView").innerHTML = empty(
        "治理信息暂时不可用。请确认账号权限并刷新。",
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
        )}</tbody></table></div></div><div class="governance-card"><h2>角色权限</h2><p class="section-note">岗位与案件权限由服务端账号会话确定。</p>${Object.entries(
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
              `<div class="info-card" style="margin-bottom:12px"><div class="row-title">${esc(k.summary || k.pattern || k.id)}</div><p class="row-subtitle">${esc(k.pattern || "")}<br>${esc(k.case_id || "")} · ${esc(k.status || "待审核")}</p>${["PENDING", "PENDING_REVIEW", "CANDIDATE", "PENDING_APPROVAL"].includes(k.status) && S.capabilities?.actions?.includes("APPROVE_KNOWLEDGE") ? `<button class="button secondary small" data-knowledge="${esc(k.id)}" data-knowledge-case="${esc(k.case_id)}">人工审核</button>` : ""}</div>`,
          )
          .join("") || empty("尚无知识候选。先完成案件闭环，再提取脱敏模式。")
      }</div><div class="governance-card wide"><h2>运行指标</h2><div class="permission-grid">${Object.entries(
        g.metrics || {},
      )
        .map(([k, v]) => `<span>${esc(k)}：${esc(text(v))}</span>`)
        .join("")}</div></div></div>`;
  }
  function agentSource(record = {}) {
    const source = String(
      record.source || record.output_source || "",
    ).toUpperCase();
    const provider = String(record.provider || "").toUpperCase();
    if (source === "FALLBACK")
      return { label: "模型异常 · 确定性降级", tone: "amber" };
    if (source === "MODEL")
      return {
        label: `${record.provider || "模型"} · 实时回答`,
        tone: "green",
      };
    if (source === "DETERMINISTIC" || provider === "DETERMINISTIC")
      return { label: "确定性工具结果", tone: "gray" };
    return { label: "输出来源未报告", tone: "gray" };
  }
  function sourceBadge(record) {
    const source = agentSource(record);
    return `<span class="badge ${source.tone}">${esc(source.label)}</span>`;
  }
  function agentAnswerText(value) {
    return esc(value)
      .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`\n]+)`/g, "<code>$1</code>")
      .replace(/^#{1,4}\s+(.+)$/gm, "<strong>$1</strong>")
      .replace(/^\s*[-*]\s+/gm, "• ");
  }
  function collaborationActor(role) {
    if (role === "MERCHANT") return "商户";
    if (["OPERATOR", "RISK_OFFICER", "SUPERVISOR"].includes(role))
      return "OceanPayment";
    if (role === "AGENT") return "OceanPilot";
    return label(role || "协作人");
  }
  function agentTrigger(trigger) {
    const name = String(trigger || "").replace(/^AUTO_EVENT:/, "");
    return (
      {
        USER_MESSAGE: "回应你的问题",
        CASE_OPENED: "打开案件后检查",
        MANUAL_REFRESH: "按要求重新检查",
        MANUAL: "人工请求检查",
        INTAKE: "接收到上游争议",
        PUBLISH_TASK: "商户任务已发布",
        MERCHANT_DECISION: "商户已确认处理决定",
        REGISTER_EVIDENCE: "有新证据登记",
        WITHDRAW_EVIDENCE: "证据已撤回",
        SUBMIT_EVIDENCE: "商户证据已送审",
        REVIEW: "收到 OP 审核结果",
        BUILD_PACKAGE: "证据包草稿已生成",
        APPROVE_PACKAGE: "主管已终审冻结",
        SUBMIT: "已取得 Mock 提交回执",
        RECORD_OUTCOME: "收到上游结果",
        RECORD_FINANCIAL: "有新资金事件",
        RECONCILE: "资金核对已更新",
        NOTIFY_MERCHANT: "结果已通知商户",
        CLOSE: "案件已关闭",
      }[name] || label(name || "最新案件事件")
    );
  }
  function currentAgentContext() {
    return S.current ? `${S.current.id}:${S.current.revision}:${S.role}` : "";
  }
  function agentDraftKey() {
    return S.current ? `${S.current.id}:${surface}:${S.merchantId}` : "";
  }
  function preserveAgentDraft() {
    const input = $("agentMessage");
    if (
      input &&
      S.current &&
      input.dataset?.case === S.current.id &&
      input.dataset.role === S.role
    ) {
      S.agentDrafts[agentDraftKey()] = input.value;
      storage.set(`oceanpilot.v2.draft.${agentDraftKey()}`, input.value);
    }
  }
  function proposalsFor(activity, c) {
    if (!c || activity?.stale || activity?.run?.case_revision !== c.revision)
      return [];
    return list(activity?.proposals).filter(
      (p) =>
        p.case_id === c.id &&
        p.expected_revision === c.revision &&
        p.status === "PENDING_CONFIRMATION",
    );
  }
  function renderCollaborationRoles() {
    const node = $("collaborationRoles");
    node.hidden = surface === "governance";
    if (node.hidden) return;
    node.innerHTML = S.isCasePage
      ? `<a class="case-back-link" href="/v2/${surface}">← ${surface === "merchant" ? "返回我的案件" : "返回争议工作队列"}</a><span class="case-collaborators">${surface === "merchant" ? "商户响应" : "OceanPayment 处理"}<span>·</span><a class="case-pilot-link" href="#agentPanel">询问本案 OceanPilot ↘</a></span>`
      : `<span class="surface-explainer">${surface === "merchant" ? "你的交易争议，由 OceanPayment 处理。进入案件后，OceanPilot 会帮你准备回应。" : "管理商户响应、人工审核、上游提交与资金核对。每个案件都有独立的 OceanPilot 协作空间。"}</span>`;
  }
  function renderAgentInbox() {
    const target = $("agentInbox");
    target.hidden = surface !== "operations";
    if (target.hidden) return;
    const pending = S.cases.flatMap((c) =>
      proposalsFor(S.agentIndex[c.id], c).map((p) => ({
        ...p,
        merchant_id: c.merchant_id,
      })),
    );
    const actionable = pending.filter(
      (p) => p.owner === S.role && permitted(p.action),
    );
    const items = [
      ...actionable,
      ...pending.filter((p) => p.owner !== S.role || !permitted(p.action)),
    ].slice(0, 3);
    const loaded = Object.keys(S.agentIndex).filter((id) =>
      S.cases.some((c) => c.id === id),
    ).length;
    target.innerHTML = `<div class="agent-inbox-heading"><span class="agent-symbol">✧</span><div><strong>OceanPilot 已为你准备</strong><p>${pending.length ? `${pending.length} 项已保存提案等待人工确认，当前角色可处理 ${actionable.length} 项。` : loaded ? "已读取的案件暂无待确认提案。智能体将在案件事件后重新检查。" : "正在读取案件智能体的实际待办…"}</p></div><span class="agent-inbox-scope">已读取 ${loaded} / ${S.cases.length} 案件</span></div>${items.length ? `<div class="agent-inbox-items">${items.map((p) => `<button type="button" class="agent-inbox-item" data-agent-case="${esc(p.case_id)}" data-agent-proposal="${esc(p.id)}"><span>${esc(p.title || label(p.action))}</span><small>${esc(p.case_id)} · ${esc(label(p.owner))}</small><b>${p.owner === S.role && permitted(p.action) ? "核对 →" : "查看 →"}</b></button>`).join("")}</div>` : ""}`;
  }
  async function loadAgentInbox() {
    if (surface !== "operations") return;
    const ticket = ++S.agentInboxTicket;
    const cases = S.cases.slice(0, 50);
    const results = await Promise.allSettled(
      cases.map((c) => api(`/cases/${encodeURIComponent(c.id)}/agent`)),
    );
    if (ticket !== S.agentInboxTicket) return;
    for (let i = 0; i < results.length; i++)
      if (results[i].status === "fulfilled")
        S.agentIndex[cases[i].id] = results[i].value;
    renderAgentInbox();
  }
  function renderAgentPanel() {
    const panel = $("agentPanel");
    panel.hidden = !S.isCasePage || !S.current;
    if (globalThis.OceanV21Collaboration) globalThis.OceanV21Collaboration.mount({
      host: panel, c: S.current, session: S.session, api,
      onCaseChanged: () => reconcileUpdates(), renderTools: renderLegacyAgentPanel,
    });
    else if (S.current) panel.innerHTML = '<div class="thread-empty">共享沟通模块暂不可用，请刷新页面。</div>';
  }
  function renderLegacyAgentPanel() {
    const panel = $("agentToolsPanel");
    if (!panel) return;
    panel.hidden = surface === "governance" || (!S.isCasePage && !S.current);
    if (panel.hidden) return;
    preserveAgentDraft();
    const previousScroll = panel.querySelector?.(".pilot-body")?.scrollTop || 0;
    const focused = document.activeElement?.id === "agentMessage";
    const selection = focused
      ? [
          document.activeElement.selectionStart,
          document.activeElement.selectionEnd,
        ]
      : null;
    if (S.current && S.agentDrafts[agentDraftKey()] === undefined)
      S.agentDrafts[agentDraftKey()] = storage.get(`oceanpilot.v2.draft.${agentDraftKey()}`) || "";
    const c = S.current,
      activity = S.activity,
      run = activity?.run;
    const stale = Boolean(
      run && (activity.stale || run.case_revision !== c?.revision),
    );
    const runtime = activity?.runtime || {};
    const conversations = list(activity?.conversations);
    const proposals = proposalsFor(activity, c);
    const prepared = run?.prepared || {};
    const preparedLabels = {
      merchant_message: "商户沟通文案",
      review_brief: "人工审核摘要",
      response_draft: "抗辩回复草稿",
    };
    const preparedKeys = Object.keys(preparedLabels).filter(
      (key) => prepared[key],
    );
    if (!preparedKeys.includes(S.agentPrepared))
      S.agentPrepared = preparedKeys[0] || "merchant_message";
    const source =
      runtime.mode === "DEEPSEEK_LIVE"
        ? "DeepSeek 已配置"
        : runtime.mode === "OFFLINE_FALLBACK"
          ? "确定性协同模式"
          : runtime.provider
            ? `${runtime.provider} 已配置`
            : "读取运行配置";
    panel.classList.toggle("collapsed", S.agentCollapsed);
    panel.innerHTML = `<header class="pilot-heading"><div class="pilot-identity"><span class="pilot-mark">✧</span><div><h2>OceanPilot</h2><p>工具检查与原私有历史 · 仅按原权限查看</p></div></div><button type="button" class="pilot-collapse" data-agent-collapse aria-label="${S.agentCollapsed ? "展开" : "收起"} OceanPilot" aria-expanded="${!S.agentCollapsed}">${S.agentCollapsed ? "＋" : "−"}</button></header><div class="pilot-status"><span class="status-dot"></span><span>${esc(source)}</span><span>${c ? `案件 v${esc(c.revision)}` : "选择案件开始"}</span></div><div class="pilot-body" ${S.agentCollapsed ? "hidden" : ""}>${
      !c
        ? `<div class="pilot-empty"><span>✧</span><h3>你的案件，交给我一起推进。</h3><p>选择一个争议案件。我会读取规则与证据，准备下一步，并把需要你确认的决定放在这里。</p></div>`
        : `<div class="pilot-event"><span>${S.agentLoading ? "正在读取工具运行记录" : runtime.analysis_pending ? "正在分析最新案件事件" : run ? agentTrigger(run.trigger) : "准备开始案件检查"}</span><time>${run ? date(run.completed_at || run.created_at) : ""}</time></div>${stale ? '<div class="pilot-warning">下方运行属于旧版案件，提案已停用。请基于当前版本重新检查。</div>' : ""}${run ? `<div class="pilot-summary"><p>${esc(run.summary || activity.summary || "")}</p><div>${sourceBadge(run)}<span>运行 ${esc(String(run.id).slice(-8))} · v${esc(run.case_revision)}</span></div></div>` : `<div class="pilot-empty compact"><p>尚无已保存的工具检查。启动后会实际读取规则、证据、时限和下一步。</p></div>`}${
            list(run?.steps).length
              ? `<details class="pilot-tools"><summary><span>✓ 已完成 ${list(run.steps).filter((s) => s.status === "COMPLETED").length} 项工具检查</span><span>查看依据 ↗</span></summary><div class="pilot-tool-list">${list(
                  run.steps,
                )
                  .map(
                    (step) =>
                      `<details class="pilot-tool"><summary><span class="check-mark ${step.status === "COMPLETED" ? "done" : ""}">${step.status === "COMPLETED" ? "✓" : "○"}</span><span>${esc(step.title || step.capability)}</span><small>${esc(label(step.status))}</small></summary><pre class="code-block">${esc(JSON.stringify(step.output || {}, null, 2))}</pre>${citations(step.citations)}</details>`,
                  )
                  .join("")}</div></details>`
              : ""
          }${
            list(run?.findings).length
              ? `<div class="pilot-findings"><h3>我发现了什么</h3>${list(
                  run.findings,
                )
                  .slice(0, 3)
                  .map(
                    (f) =>
                      `<div class="pilot-finding ${["ERROR", "CRITICAL", "BLOCKER", "HIGH"].includes(String(f.severity).toUpperCase()) ? "blocking" : ""}"><strong>${esc(f.title || f.severity)}</strong><p>${esc(f.detail || f.message || "")}</p></div>`,
                  )
                  .join("")}</div>`
              : ""
          }${
            proposals.length
              ? `<div class="pilot-proposals"><h3>已准备好，等人确认</h3>${proposals
                  .slice(0, 3)
                  .map(
                    (p) =>
                      `<div class="pilot-proposal"><div class="pilot-proposal-title"><span>↗</span><strong>${esc(p.title || label(p.action))}</strong></div><p>${esc(p.reason || "")}</p><div class="pilot-proposal-meta">${esc(label(p.owner))} · 绑定案件 v${esc(p.expected_revision)}</div>${p.owner === S.role && permitted(p.action) ? `<button type="button" class="button primary" data-agent-proposal="${esc(p.id)}">核对内容并确认 →</button>` : `<div class="pilot-owner-note">由 ${esc(label(p.owner))} 确认。${surface === "merchant" ? "你可以在下方补充说明或准备证据。" : "已交由该岗位的获授权人员处理。"}</div>`}</div>`,
                  )
                  .join("")}</div>`
              : ""
          }${preparedKeys.length ? `<details class="pilot-prepared" ${surface === "merchant" ? "" : "open"}><summary>✎ 已备好的文案与摘要</summary><div class="pilot-prepared-tabs">${preparedKeys.map((key) => `<button type="button" class="${S.agentPrepared === key ? "active" : ""}" data-agent-prepared="${key}">${preparedLabels[key]}</button>`).join("")}</div><p class="pilot-draft">${esc(text(prepared[S.agentPrepared]))}</p><div class="pilot-draft-note">草稿供人工核对。确认前不会发送或提交。</div></details>` : ""}<div class="pilot-conversation"><div class="pilot-conversation-heading"><h3>原私有对话历史</h3><span>${conversations.length ? `${conversations.length} 条已保存记录` : "基于当前案件"}</span></div>${conversations
            .slice(-30)
            .map((turn) => {
              const auto = String(turn.trigger || "").startsWith("AUTO_EVENT:");
              return `<div class="pilot-turn">${!auto && turn.message ? `<div class="pilot-question"><span>${esc(collaborationActor(turn.actor_role))}</span>${esc(turn.message)}</div>` : ""}<div class="pilot-answer"><div class="pilot-answer-head"><span class="mini-pilot">✧</span><strong>OceanPilot</strong>${sourceBadge(turn)}${turn.model ? `<small class="pilot-model">${esc(turn.model)}</small>` : ""}</div>${auto ? `<small class="pilot-auto-trigger">${esc(agentTrigger(turn.trigger))} · 自动跟进</small>` : ""}<p>${agentAnswerText(turn.answer || "")}</p><div class="pilot-answer-foot">${date(turn.created_at)} · 案件 v${esc(turn.case_revision ?? "—")}${turn.model ? ` · ${esc(turn.model)}` : ""}</div>${turn.knowledge_retrieval ? `<div class="pilot-reference-count">${turn.knowledge_retrieval.status === "COMPLETED" ? `已检索 ${list(turn.knowledge_retrieval.references).length} 条指南案例参考` : "指南参考读取暂不可用"} · 依据本案卡组织和原因码</div>` : ""}${turn.source_citations?.length ? `<details><summary>查看引用</summary>${citations(turn.source_citations)}</details>` : ""}</div></div>`;
            })
            .join(
              "",
            )}${!conversations.length ? '<div class="pilot-conversation-empty">尚无原私有历史。新问题在本案共享沟通中发送。</div>' : ""}</div>${S.agentNotice ? `<div class="pilot-warning" role="status">${esc(S.agentNotice)}</div>` : ""}`
    }</div><p class="private-history-notice">以上旧私有对话仅按原权限只读保留。新问题请在本案共享沟通中发送；未发布策略请使用 OP 内部讨论。</p>`;
    const body = panel.querySelector?.(".pilot-body");
    const conversation = panel.querySelector?.(".pilot-conversation");
    if (body && conversation) body.prepend(conversation);
    if (body) body.scrollTop = previousScroll;
    restoreAgentInputFocus(focused, selection);
    fitAgentPanel();
  }
  function restoreAgentInputFocus(focused, selection) {
    const input = $("agentMessage");
    if (focused && input && !input.disabled) {
      input.focus({ preventScroll: true });
      if (selection) input.setSelectionRange(selection[0], selection[1]);
    }
  }
  function fitAgentPanel() {
    const panel = $("agentPanel");
    if (typeof window === "undefined" || !panel?.getBoundingClientRect) return;
    const top = Math.max(18, panel.getBoundingClientRect().top);
    panel.style.setProperty(
      "--pilot-available-height",
      `${Math.max(470, window.innerHeight - top - 18)}px`,
    );
  }
  function acceptAgentActivity(activity, context) {
    if (context !== currentAgentContext()) return false;
    const previous = JSON.stringify(S.activity);
    S.activity = activity;
    if (S.current) S.agentIndex[S.current.id] = activity;
    if (previous !== JSON.stringify(activity)) renderAgentPanel();
    renderAgentInbox();
    scheduleAgentPoll();
    return true;
  }
  function scheduleAgentPoll() {
    if (S.agentPoll) clearTimeout(S.agentPoll);
    S.agentPoll = null;
    if (globalThis.OCEAN_V2_NO_BOOT || !S.current || !S.activity?.runtime?.analysis_pending) return;
    const context = currentAgentContext();
    // The model completion is persisted before its worker clears the in-memory pending flag.
    // Only reconcile that flag while work is pending; durable updates drive all case changes.
    S.agentPoll = setTimeout(() => {
      if (context === currentAgentContext()) refreshAgent({ quiet: true });
    }, 1000);
  }
  async function refreshAgent({ ensure = false, quiet = false } = {}) {
    if (!S.current || surface === "governance") return;
    const context = currentAgentContext(),
      id = S.current.id,
      revision = S.current.revision;
    const ticket = ++S.activityTicket;
    if (!quiet) {
      S.agentLoading = true;
      renderAgentPanel();
    }
    try {
      let result = await api(`/cases/${encodeURIComponent(id)}/agent`);
      if (ticket !== S.activityTicket || context !== currentAgentContext())
        return;
      if ((result.case_revision || result.run?.case_revision) > revision) {
        if (S.dialog?.case_id === id) {
          S.dialog.stale = true;
          $("dialogError").textContent =
            "案件有新进展，此确认已失效。请关闭后重新核对当前版本。";
          $("dialogError").hidden = false;
          $("submitDialog").disabled = true;
        }
        S.agentLoading = false;
        await reconcileUpdates();
        return;
      }
      if (ensure && !result.run) {
        result = await api(`/cases/${encodeURIComponent(id)}/agent/run`, {
          method: "POST",
          body: JSON.stringify({ expected_revision: revision }),
        });
        if (ticket !== S.activityTicket || context !== currentAgentContext())
          return;
      }
      S.agentLoading = false;
      S.agentNotice = "";
      acceptAgentActivity(result, context);
      if (!quiet) renderAgentPanel();
      scheduleAgentPoll();
    } catch (error) {
      if (ticket !== S.activityTicket || context !== currentAgentContext())
        return;
      S.agentLoading = false;
      S.agentNotice = `Agent 活动暂不可用：${error.message}`;
      renderAgentPanel();
    } finally {
      if (ticket === S.activityTicket) {
        S.agentLoading = false;
        renderAgentPanel();
      }
    }
  }
  async function runAgent() {
    if (!S.current || S.agentBusy || S.agentLoading) return;
    const ticket = ++S.activityTicket;
    const context = currentAgentContext(),
      c = S.current;
    S.agentLoading = true;
    S.agentNotice = "";
    S.agentPollCount = 0;
    renderAgentPanel();
    try {
      const result = await api(`/cases/${encodeURIComponent(c.id)}/agent/run`, {
        method: "POST",
        body: JSON.stringify({ expected_revision: c.revision }),
      });
      if (ticket !== S.activityTicket || context !== currentAgentContext()) return;
      S.agentLoading = false;
      acceptAgentActivity(result, context);
      renderAgentPanel();
      scheduleAgentPoll();
    } catch (error) {
      if (ticket === S.activityTicket && context === currentAgentContext()) {
        S.agentLoading = false;
        S.agentNotice = error.message;
        renderAgentPanel();
      }
    } finally {
      if (ticket === S.activityTicket && S.current?.id === c.id) {
        S.agentLoading = false;
        renderAgentPanel();
      }
    }
  }
  async function sendAgentMessage(message) {
    if (!S.current || S.agentBusy) return;
    preserveAgentDraft();
    const value = String(
      message ?? S.agentDrafts[agentDraftKey()] ?? "",
    ).trim();
    if (!value) {
      S.agentNotice = "请输入案件问题或希望准备的内容。";
      renderAgentPanel();
      return;
    }
    if (value.length > 2000) {
      S.agentNotice = "问题请控制在 2000 字以内。";
      renderAgentPanel();
      return;
    }
    const messageTicket = ++S.agentMessageTicket;
    const context = currentAgentContext(),
      c = S.current,
      key = agentDraftKey();
    S.agentDrafts[key] = value;
    storage.set(`oceanpilot.v2.draft.${key}`, value);
    const input = $("agentMessage");
    if (input) input.value = value;
    S.agentBusy = true;
    S.agentNotice = "";
    renderAgentPanel();
    try {
      const result = await api(
        `/cases/${encodeURIComponent(c.id)}/agent/messages`,
        {
          method: "POST",
          timeoutMs: 35000,
          body: JSON.stringify({
            message: value,
            expected_revision: c.revision,
          }),
        },
      );
      if (messageTicket !== S.agentMessageTicket || key !== agentDraftKey()) return;
      S.agentBusy = false;
      if (context !== currentAgentContext()) {
        S.agentNotice = "案件已同步到新版本，问题已保留，请基于最新进展重新发送。";
        renderAgentPanel();
        await refreshAgent({ quiet: true });
        return;
      }
      S.agentDrafts[key] = "";
      storage.remove(`oceanpilot.v2.draft.${key}`);
      const input = $("agentMessage");
      if (input) input.value = "";
      if (result.answer) {
        const turn = {
          ...result,
          case_id: c.id,
          case_revision: c.revision,
          message: value,
          actor_role: S.role,
          created_at: result.created_at || new Date().toISOString(),
        };
        S.activity = {
          ...(S.activity || {}),
          run: result.run || S.activity?.run,
          proposals: result.proposals || S.activity?.proposals || [],
          conversations: [...list(S.activity?.conversations), turn],
        };
        renderAgentPanel();
      }
      await refreshAgent({ quiet: true });
    } catch (error) {
      if (messageTicket !== S.agentMessageTicket || key !== agentDraftKey()) return;
      S.agentBusy = false;
      S.agentNotice = `未取得确认回答：${error.message}。问题已保留，可重新发送。`;
      renderAgentPanel();
    }
  }
  function prefillProposalData(data) {
    const form = $("actionForm");
    for (const input of form.querySelectorAll("[name]")) {
      const key = input.name;
      if (key === "allow_accept" || key === "allow_contest") {
        input.checked = list(data.allowed_actions).includes(
          key === "allow_accept" ? "ACCEPT" : "CONTEST",
        );
        continue;
      }
      if (!(key in data)) continue;
      if (input.type === "checkbox") {
        input.checked = key === "pii_checked" ? false : data[key] === true;
        continue;
      }
      if (
        [
          "external_deadline",
          "merchant_deadline",
          "internal_deadline",
        ].includes(key)
      ) {
        input.value = isoInput(data[key]);
        continue;
      }
      input.value = Array.isArray(data[key])
        ? data[key].join(", ")
        : String(data[key] ?? "");
    }
  }
  function openAgentProposal(id) {
    const proposal = proposalsFor(S.activity, S.current).find(
      (p) => p.id === id,
    );
    if (!proposal) {
      S.agentNotice = "该提案已不适用于当前案件版本，请重新检查。";
      renderAgentPanel();
      return;
    }
    if (proposal.owner !== S.role || !permitted(proposal.action)) {
      S.agentNotice = `此提案需 ${label(proposal.owner)} 核对并确认。`;
      renderAgentPanel();
      return;
    }
    openDialog(proposal.action, proposal.data || {});
    if (!S.dialog || S.dialog.action !== proposal.action) return;
    prefillProposalData(proposal.data || {});
    S.dialog.proposal = proposal;
    if (S.activity?.run?.id && proposal.scope) S.dialog.proposalOrigin = {run_id:S.activity.run.id,proposal_id:proposal.id,scope:proposal.scope,original_revision:proposal.expected_revision};
    S.dialog.proposalInitialData = collectData($("actionForm"));
    $("dialogEyebrow").textContent = "OCEANPILOT PROPOSAL → HUMAN CONFIRMATION";
    $("dialogTitle").textContent = proposal.title || label(proposal.action);
    $("dialogContext").innerHTML =
      `<strong>OceanPilot 已准备 · 由 ${esc(label(S.role))} 确认</strong><br>${esc(proposal.reason || "")}<br>${esc(proposal.case_id)} · 绑定版本 v${esc(proposal.expected_revision)}<br>逐项核对下方内容。编辑后将以修改后的内容创建案件命令。<details><summary>查看已保存提案及引用</summary><pre class="code-block">${esc(JSON.stringify(proposal.data || {}, null, 2))}</pre>${citations(proposal.basis_citations)}</details>`;
  }
  function caseHref(id, targetSurface = surface) {
    return `/v2/${targetSurface}/cases/${encodeURIComponent(id)}`;
  }
  function writeNavigation() {
    if (S.current && S.isCasePage) {
      const url = new URL(location.href);
      url.pathname = caseHref(S.current.id);
      url.searchParams.delete("case");
      url.searchParams.set("tab", S.tab);
      history.replaceState(null, "", url);
      document.title = `${S.current.id} · ${surface === "merchant" ? "我的案件" : "OceanPayment 争议运营"}`;
    }
    document.querySelectorAll("[data-surface]").forEach((link) => {
      const destination = link.dataset.surface;
      link.href = S.current && S.isCasePage && destination !== "governance"
        ? caseHref(S.current.id, destination) : `/v2/${destination}`;
    });
  }
  function syncStatus(message, failed = false) {
    const node = $("syncStatus");
    if (!node) return;
    node.textContent = message;
    node.classList.toggle("reconnecting", failed);
  }
  function invalidateConfirmation(c) {
    if (!S.dialog || S.dialog.case_id !== c.id || S.dialog.revision === c.revision) return;
    S.dialog.stale = true;
    $("dialogError").textContent = "另一端已更新此案件。你填写的内容已保留，但旧版本确认已失效；请重新核对最新进度后发起操作。";
    $("dialogError").hidden = false;
    $("confirmCheckbox").checked = false;
    $("submitDialog").disabled = true;
  }
  async function reconcileUpdates() {
    const ticket = ++S.reconcileTicket;
    const actorRole = S.role;
    const id = S.caseId || S.current?.id;
    if (!S.isCasePage) {
      await loadCasePage();
      if (ticket !== S.reconcileTicket || actorRole !== S.role) return;
      renderMetrics(); renderQueue();
      return;
    }
    if (!id || surface === "governance") return;
    const results = await Promise.allSettled([
      api(`/cases/${encodeURIComponent(id)}`),
      api(`/cases/${encodeURIComponent(id)}/plan`),
      api(`/cases/${encodeURIComponent(id)}/agent`),
    ]);
    if (ticket !== S.reconcileTicket || actorRole !== S.role || id !== (S.caseId || S.current?.id)) return;
    if (results[0].status === "rejected") {
      if ([403, 404].includes(results[0].reason.status)) {
        S.caseError = results[0].reason;
        S.current = null; S.plan = null; S.activity = null;
        renderDetail(); renderAgentPanel();
      }
      throw results[0].reason;
    }
    const c = results[0].value.case || results[0].value;
    if (S.current?.id === id && c.revision < S.current.revision) return;
    const changed = S.current?.id !== id || c.revision !== S.current?.revision
      || (results[1].status === "fulfilled" && JSON.stringify(results[1].value) !== JSON.stringify(S.plan));
    preserveAgentDraft();
    invalidateConfirmation(c);
    S.current = c; S.caseError = null;
    const plan = results[1].status === "fulfilled" ? results[1].value : null;
    S.plan = plan?.revision === c.revision ? plan : null;
    if (changed) {
      const detail = $("caseDetail");
      const openDetails = [...(detail.querySelectorAll?.("details") || [])].map((d) => d.open);
      renderDetail();
      [...(detail.querySelectorAll?.("details") || [])].forEach((d, i) => { if (openDetails[i]) d.open = true; });
      writeNavigation();
    }
    if (results[2].status === "fulfilled") {
      acceptAgentActivity(results[2].value, currentAgentContext());
      if (changed) renderAgentPanel();
    } else {
      S.activity = null;
      S.agentNotice = "案件进度已更新，智能体记录暂不可用，恢复连接后自动重试。";
      renderAgentPanel();
      throw results[2].reason;
    }
    if (results[1].status === "rejected") throw results[1].reason;
    // Separate GETs may straddle a concurrent write. Never display a mismatched plan as current.
    if (S.plan === null || (S.activity.case_revision || c.revision) !== c.revision) {
      throw new Error("案件正在变化，正在重新读取一致版本");
    }
  }
  function stopUpdates() {
    S.syncEpoch++;
    S.syncController?.abort();
    S.syncController = null;
    S.syncTask = null;
  }
  function startUpdates() {
    if (globalThis.OCEAN_V2_NO_BOOT || surface === "governance" || S.isLibraryPage || S.syncTask) return;
    const epoch = ++S.syncEpoch;
    S.syncTask = (async () => {
      let failures = 0;
      while (epoch === S.syncEpoch) {
        const controller = new AbortController();
        S.syncController = controller;
        const params = new URLSearchParams({ timeout: "20" });
        if (S.syncCursor) params.set("cursor", S.syncCursor);
        if (S.caseId) params.set("case_id", S.caseId);
        try {
          syncStatus(failures ? "正在恢复同步…" : "自动同步中");
          const update = await api(`/updates?${params}`, { timeoutMs: 26000, signal: controller.signal });
          if (epoch !== S.syncEpoch) break;
          if (update.reset || update.changed_case_ids?.length) await reconcileUpdates();
          if (epoch !== S.syncEpoch) break;
          // Advance only after applying the change: failed reads are replayed on reconnect.
          S.syncCursor = update.cursor;
          failures = 0;
          syncStatus("已自动同步");
        } catch (error) {
          if (epoch !== S.syncEpoch) break;
          if ([401, 403, 404].includes(error.status)) { syncStatus("同步已停止，请核对访问权限", true); break; }
          failures++;
          syncStatus("连接中断 · 自动重连", true);
          await new Promise((resolve) => setTimeout(resolve, Math.min(1000 * failures, 5000)));
        }
      }
    })();
  }
  async function openCase(id, { withAgent = true } = {}) {
    const ticket = ++S.selection;
    preserveAgentDraft();
    if (S.agentPoll) clearTimeout(S.agentPoll);
    S.activityTicket++;
    S.agentPollCount = 0;
    S.activity = null;
    S.agentBusy = false;
    S.agentMessageTicket++;
    S.agentNotice = "";
    S.plan = null;
    S.current = null;
    S.caseError = null;
    renderAgentPanel();
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
      renderAgentPanel();
      if (withAgent) await refreshAgent({ ensure: false });
    } catch (error) {
      if (ticket !== S.selection) return;
      S.current = null;
      S.caseError = error;
      renderDetail();
      renderAgentPanel();
      setNotice(error.message, true);
    }
  }
  function renderReadError(error, casePage = false) {
    const title = error.status === 403 ? "没有此案件的访问权限" : error.status === 404 ? "找不到这个案件" : "暂时无法读取案件";
    return `<div class="empty-state access-error" role="alert"><div class="empty-symbol">${error.status === 403 ? "⊘" : "!"}</div><h2>${title}</h2><p>${esc(error.message)}</p><div class="action-bar">${casePage ? `<a class="button secondary" href="/v2/${surface}">返回我的案件列表</a>` : ""}${![403,404].includes(error.status) ? '<button class="button primary" data-reload>重新读取</button>' : ""}</div></div>`;
  }
  async function loadCasePage() {
    const ticket = ++S.listTicket;
    const params = new URLSearchParams({ limit: String(S.limit), offset: String(S.offset), q: S.search, queue: S.queue, assigned_to: S.assignedTo });
    const result = await api(`/cases?${params}`);
    if (ticket !== S.listTicket) return result;
    S.cases = list(result.cases); S.total = Number(result.total ?? S.cases.length);
    S.queueCounts = result.queue_counts || result.counts || null;
    S.listError = null;
    return result;
  }
  async function refresh(force = false) {
    if (S.loading && !force) return;
    S.loading = true; $("refreshButton").disabled = true;
    const ticket = ++S.refreshEpoch;
    try {
      const results = await Promise.allSettled([
        S.isCasePage || S.isLibraryPage || surface === "governance" ? Promise.resolve(null) : loadCasePage(),
        ["ADMIN", "SUPERVISOR"].includes(S.role) ? api("/governance") : Promise.resolve(null),
        api("/capabilities"),
        Object.keys(S.commandSchemas).length ? Promise.resolve(null) : api("/command-schemas"),
      ]);
      if (ticket !== S.refreshEpoch) return;
      if (results[0].status === "rejected") throw results[0].reason;
      if (results[2].status === "fulfilled") S.capabilities = results[2].value;
      if (results[3]?.status === "fulfilled" && results[3].value) S.commandSchemas = results[3].value.commands || {};
      if (results[1].status === "fulfilled") S.governance = results[1].value;
      $("intakeButton").hidden = surface !== "operations" || S.isLibraryPage || !permitted("INTAKE");
      renderMetrics(); renderQueue();
      if (S.isLibraryPage) { $("metrics").hidden = true; $("workspaceGrid").hidden = true; }
      if (surface === "governance") renderGovernance();
      else if (S.isCasePage && S.caseId) {
        if (S.current?.id === S.caseId) await reconcileUpdates();
        else await openCase(S.caseId);
      } else { S.current = null; S.plan = null; S.activity = null; renderAgentPanel(); }
      startUpdates();
    } catch (error) {
      S.listError = error; renderQueue();
      if (S.isCasePage && !S.current) { S.caseError = error; renderDetail(); }
      setNotice(`读取失败：${error.message}`, true);
      if (![401,403,404].includes(error.status)) startUpdates();
    } finally {
      if (ticket === S.refreshEpoch) { S.loading = false; $("refreshButton").disabled = false; }
    }
  }
  function field(name, title, value = "", type = "text", options = {}) {
    const contract = S.dialog?.contract;
    options = { ...options };
    const requiredFields = list(contract?.required_fields);
    const definitions = contract?.fields || contract?.field_schema?.properties || {};
    const rule = (Array.isArray(definitions) ? definitions.find((item) => item.name === name) : definitions[name]) || requiredFields.find((item) => typeof item === "object" && item.name === name) || {};
    const optional = contract && Array.isArray(contract.required_fields) ? !requiredFields.some((item) => (typeof item === "string" ? item : item.name) === name) : Boolean(options.optional);
    const choiceValues = contract?.choices?.[name] || rule.enum || rule.options || options.choices;
    if (choiceValues) type = "select";
    const required = optional ? "" : " required";
    if (choiceValues && !list(choiceValues).some(choice => String(Array.isArray(choice) ? choice[0] : typeof choice === "object" ? choice.value : choice) === String(value))) value = "";
    const hint = options.hint || rule.description;
    const minlength = rule.min_length ?? rule.minLength;
    const common = `name="${esc(name)}"${required}${minlength !== undefined && type !== "number" ? ` minlength="${Number(minlength)}"` : ""}${rule.pattern ? ` pattern="${esc(rule.pattern)}"` : ""} aria-describedby="field-error-${esc(name)}"`;
    const maxlength = rule.max_length ?? rule.maxLength ?? options.max ?? (type === "textarea" ? 4000 : 1000);
    const minimum = rule.minimum ?? (rule.exclusiveMinimum !== undefined ? rule.exclusiveMinimum + 1 : undefined) ?? rule.min ?? options.min;
    const maximum = rule.maximum ?? rule.max;
    let input;
    if (type === "checkbox") input = `<input name="${esc(name)}" type="checkbox"${value ? " checked" : ""}>`;
    else if (type === "select") input = `<select ${common}>${!value ? '<option value="">请选择</option>' : ""}${list(choiceValues).map((choice) => {
      const [key, display] = Array.isArray(choice) ? choice : typeof choice === "object" ? [choice.value, choice.label || label(choice.value)] : [choice, label(choice)];
      return `<option value="${esc(key)}"${String(value) === String(key) ? " selected" : ""}>${esc(display)}</option>`;
    }).join("")}</select>`;
    else if (type === "textarea") input = `<textarea ${common} maxlength="${Number(maxlength)}">${esc(value)}</textarea>`;
    else input = `<input ${common} type="${esc(type)}" value="${esc(value)}"${type === "number" ? ' step="1"' : ` maxlength="${Number(maxlength)}"`}${minimum !== undefined ? ` min="${esc(minimum)}"` : ""}${maximum !== undefined ? ` max="${esc(maximum)}"` : ""}>`;
    return `<label class="form-field${type === "checkbox" ? " checkbox" : ""}" data-field="${esc(name)}"><span>${esc(title)}${optional ? "（可选）" : ""}</span>${input}${hint ? `<small>${esc(hint)}</small>` : ""}<small class="field-error" id="field-error-${esc(name)}" hidden></small></label>`;
  }
  function validateCommandData(data, contract) {
    if (!contract) return [];
    const errors = [], properties = contract.fields || {};
    for (const field of list(contract.required_fields)) { const name = typeof field === "string" ? field : field.name; if (!(name in data)) errors.push({field:name,message:"请填写此项。"}); }
    for (const [name,value] of Object.entries(data)) {
      const rule = properties[name] || {};
      const choices = contract.choices?.[name] || rule.enum;
      if (Array.isArray(choices) && !choices.some(choice => (typeof choice === "object" ? choice.value : choice) === value)) errors.push({field:name,message:"请选择当前允许的选项。"});
      if (typeof value === "string" && (value.length < (rule.min_length ?? rule.minLength ?? 0) || value.length > (rule.max_length ?? rule.maxLength ?? Infinity))) errors.push({field:name,message:`请按要求填写长度为 ${rule.min_length ?? rule.minLength ?? 0}–${rule.max_length ?? rule.maxLength ?? "不限"} 个字符的内容。`});
      if (typeof value === "number" && (!Number.isSafeInteger(value) || value < (rule.minimum ?? -Infinity) || value > (rule.maximum ?? Infinity) || value <= (rule.exclusiveMinimum ?? -Infinity))) errors.push({field:name,message:"请填写允许范围内的整数金额或数量。"});
      if (Array.isArray(value) && (value.length < (rule.minItems ?? 0) || value.length > (rule.maxItems ?? Infinity))) errors.push({field:name,message:"填写的项目数量不符合当前字段要求。"});
    }
    return errors;
  }
  function showFieldErrors(body) {
    const errors = body?.field_errors || body?.detail?.field_errors || (Array.isArray(body?.detail) ? body.detail : []);
    const entries = Array.isArray(errors) ? errors : Object.entries(errors).map(([field, message]) => ({ field, message }));
    for (const error of entries) {
      const name = error.field || list(error.loc).at(-1);
      const node = document.getElementById(`field-error-${name}`);
      if (node) { node.hidden = false; node.textContent = error.message || error.msg || "请核对此字段"; }
    }
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
      field("event_id", "上游事件 ID", uuid(), "text", {
        hint: "同一上游事件应复用相同 ID，以保证去重。",
      });
    switch (action) {
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
          )
        );
      case "MERCHANT_DECISION":
        return (
          field(
            "decision",
            "商户决定",
            data.decision || "",
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
      case "REVIEW_EVIDENCE_CONTENT":
        return field("evidence_id", "本案材料 ID", data.evidence_id || "") + field("decision", "核验判断", "", "select", { choices: [["SUPPORTED", "内容支持所述事实"], ["INSUFFICIENT", "内容仍不足"]] }) + reason() + field("applicable_facts", "所依据的正文原句", "", "textarea", { hint: "每行一条原文摘录。需能在所选正文行中逐字找到，不可填推测。" }) + field("locators", "原文行号", "", "textarea", { hint: "每行一个定位，如 line:1。请先在本案文件与材料中展开正文。" });
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
          field("decision", "审核结论", data.decision || "", "select", {
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
      case "ASSIGN_CASE":
        return field("user_id", "获授权的案件负责人", "", "select", { choices: list(c.participants).filter(p => p.role === "OPERATOR").map(p => [p.user_id, p.display_name || p.user_id]) }) + reason();
      case "RESOLVE_RESPONSE":
        return field("resolution", "核实后的处理方式", "", "select", { choices: ["RESTORE_DECISION", "RESTORE_EVIDENCE", "CONFIRM_LOSS", "FOLLOW_UP"] }) + reason() + field("authorization_reference", "授权与核实依据", "") + field("external_deadline", "经确认的有效外部截止时间", "", "datetime-local", { optional: true });
      case "FINAL_REVIEW":
        return field("decision", "最终审核结论", "", "select", { choices: ["APPROVE", "RETURN_MATERIALS", "RETURN_DOCUMENT", "RECOMMEND_ACCEPT", "HOLD"] }) + field("package_id", "待审核证据包", data.package_id || pkg?.id || "", "select", { choices: list(c.packages).filter(p => p.status === "DRAFT").map(p => [p.id, `v${p.version} · ${p.id}`]), optional: true }) + reason() + field("pii_checked", "批准前已检查敏感信息与材料引用", false, "checkbox", { optional: true });
      case "VERIFY_OUTCOME":
        return field("event_id", "待核实上游事件", data.event_id || "", "select", { choices: list(c.upstream_events).map(e => [e.event_id || e.id, `${e.event_id || e.id} · ${label(e.outcome)}`]) }) + field("decision", "核实结论", "", "select", { choices: ["CONFIRM", "REJECT"] }) + reason() + field("authorization_reference", "核实授权依据", "");
      case "REOPEN_CASE":
        return reason() + field("authorization_reference", "重开授权依据", "") + field("event_reference", "触发重开的事件引用", "");
      case "REUSE_EVIDENCE":
        return field("evidence_ids", "确认复用的材料 ID", list(data.evidence_ids).join(", "), "textarea", { hint: "填写明确适用于当前阶段的材料 ID，用逗号分隔。" }) + reason();
      case "PROCESS_ACCEPT":
        return field("mode", "接受责任处理方式", "", "select", { choices: ["MOCK", "NO_ACTION_REQUIRED"] }) + field("reference", "渠道处理依据 / 记录引用", "") + reason();
      case "QUERY_SUBMISSION":
        return field("request_id", "待查询提交请求", "", "select", { choices: list(c.submissions).map(item => item.request_id || item.id) }) + field("result", "核实后的受理状态", "", "select", { choices: ["ACCEPTED", "NOT_ACCEPTED", "UNKNOWN"] }) + reason();
      case "RESOLVE_TASK":
        return field("task_id", "需要处置的任务", data.task_id || "", "select", { choices: list(c.tasks).filter(t => t.status === "OPEN").map(t => [t.id, `${label(t.type)} · ${t.id}`]) }) + field("resolution", "处置方式", "", "select", { choices: ["CANCELLED", "WAIVED", "SUPERSEDED"] }) + reason() + field("replacement_task_id", "替代任务 ID", "", "text", { optional: true });
      case "RECORD_OUTCOME":
        return event() + field("outcome", "上游业务结果", data.outcome || "UNKNOWN", "select", { choices: ["UNKNOWN", "WON", "LOST", "PARTIAL", "ACCEPTED_RESPONSIBILITY", "WITHDRAWN", "OTHER"] }) + field("disposition", "这个事件意味着什么", "", "select", { choices: ["WAIT", "VERIFY", "ACTION", "NEXT_STAGE", "FINAL"] }) + field("source", "结果来源", data.source || "") + reason() + field("occurred_at", "源事件发生时间", "", "datetime-local", { optional: true }) + field("received_at", "实际收到事件的时间", "", "datetime-local", { optional: true }) + field("stage_number", "事件所属轮次", c.stage_number || 1, "number", { min: 1 }) + field("basis_reference", "结果与分流判断依据", "") + field("authorization_reference", "终局 / 更正授权依据", "", "text", { optional: true }) + field("corrects_event_id", "本次更正的原事件 ID", "", "text", { optional: true }) + field("mapped_outcome", "OTHER 经核实对应的业务结果", "", "select", { optional: true, choices: ["", "WON", "LOST", "PARTIAL", "ACCEPTED_RESPONSIBILITY", "WITHDRAWN"] }) + field("next_stage", "明确要求的后续阶段", "", "select", { optional: true, choices: ["", "REPRESENTMENT", "PRE_ARBITRATION", "ARBITRATION"] }) + field("supported_minor", "部分支持金额（最小货币单位）", "", "number", { optional: true, min: 0 }) + field("liable_minor", "部分承担金额（最小货币单位）", "", "number", { optional: true, min: 0 }) + field("currency", "部分结果金额币种", "", "text", { optional: true });
      case "NEXT_STAGE":
        return field("stage", "上游明确要求的后续阶段", "", "select", { choices: ["REPRESENTMENT", "PRE_ARBITRATION", "ARBITRATION"] }) + event() + field("source", "上游来源", "") + field("occurred_at", "源事件发生时间", "", "datetime-local", { optional: true }) + field("received_at", "实际收到事件的时间", "", "datetime-local", { optional: true }) + field("external_deadline", "渠道明确给出的截止时间", "", "datetime-local", { optional: true });
      case "RECORD_FINANCIAL":
        return (
          event() +
          field("kind", "资金事件类型", "CREDIT", "select", {
            choices: ["DEBIT", "CREDIT", "REFUND", "FEE", "ADJUSTMENT"],
          }) +
          field(
            "amount_minor",
            "金额（最小货币单位）",
            c.amount_minor || 0,
            "number",
          ) +
          field("currency", "币种", c.currency || "USD") +
          field("source", "资金事件来源", "MOCK_UPSTREAM") +
          field("reference", "核对凭证 / 流水引用", "")
        );
      case "RECONCILE":
        return (
          field("status", "核对结论", "RECONCILED", "select", {
            choices: ["RECONCILED", "DISCREPANCY", "NOT_APPLICABLE"],
          }) +
          field(
            "expected_net_minor",
            "预期净影响（最小货币单位，有符号）",
            0,
            "number",
            {
              hint: "扣款与费用为负，返还为正。填写经核对的预期净影响。",
            },
          ) +
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
  async function openLibraryTemplate(templateId) {
    if (!permitted("INTAKE")) { setNotice("请由 OP 运营专员选择模板并确认演练建案。", true); return; }
    try {
      const result = await api(`/case-library/${encodeURIComponent(templateId)}`);
      if (!result.template) throw new Error("该条目仅作来源参考，没有可执行演练模板。");
      const reference = result.reference;
      const original = result.template.template || {};
      const scheme = String(original.scheme || reference.scheme).toUpperCase();
      if (!["VISA", "MASTERCARD", "MC"].includes(scheme))
        throw new Error("此模板保留为参考或专项测试，当前 Visa / Mastercard 双卡流程不创建该类型案件。");
      const reasons = String(original.reason_code || reference.reason_code).split(/\s*\/\s*/).filter(Boolean);
      openDialog("INTAKE", { case_template_id: templateId, scheme: scheme === "MC" ? "MASTERCARD" : scheme, reason_code: reasons[0], reason_codes: reasons });
      if (S.dialog?.action !== "INTAKE") return;
      $("dialogTitle").textContent = "从指南模板创建演练案件";
      $("dialogContext").innerHTML = `<strong>${esc(templateId)} · ${esc(reference.title)}</strong><br>原始来源、核验状态与缺失字段保留为参考。下方交易编号和事件编号为本次演练新生成，请填写演练金额、币种并核对卡组织和原因码。创建后先由风控确认适用权利、证据要求与期限，不自动继承 Mock 期限。`;
      $("submitDialog").textContent = "确认创建演练案件";
    } catch (error) { setNotice(error.message, true); }
  }
  function renderCaseReference(c) {
    const r = c?.library_reference;
    if (!r) return "";
    const grade = { SOURCE_EXPLICIT: "指南原文示例", RULE_DERIVED: "依据规则还原", SYNTHETIC_DEMO: "合成演练" }[r.evidence_level] || r.evidence_level;
    return `<details class="case-source-reference"><summary>案例来源 · ${esc(r.template_id)} · ${esc(grade)}</summary><strong>${esc(r.title)}</strong><p>${esc(r.summary || "")}</p><p>来源核验：${esc(label(r.verification_status))} · ${list(r.conflict_ids).length} 项来源冲突。交易字段为本次演练确认输入。</p>${citations(r.citations)}${surface === "operations" ? `<a href="/v2/operations/library?reference=${encodeURIComponent(r.template_id)}">查看完整案例来源 →</a>` : ""}</details>`;
  }
  function openDialog(action, data = {}) {
    if (S.busy) return;
    if (action === "INTAKE") {
      if (globalThis.OceanV21Intake) globalThis.OceanV21Intake.open();
      else setNotice("上游事件入口暂不可用，请刷新页面后重试。", true);
      return;
    }
    if (S.pending) {
      setNotice(
        "上一条命令结果尚未确认，请先使用原命令重试。",
        true,
        '<button class="button secondary small" data-retry>使用原命令重试</button>',
      );
      return;
    }
    if (action === "DEMO") {
      setNotice("演练管理仅在独立导演工作空间提供。", true);
      return;
    }
    const gate = actionContract(action);
    const contract = gate ? { ...S.commandSchemas[action], ...gate } : S.commandSchemas[action];
    if (action !== "DEMO" && (!permitted(action) || (contract && (!contract.enabled || (contract.revision !== undefined && contract.revision !== S.current?.revision))))) {
      setNotice(`${label(action)}：${roleHint(action)}`, true);
      return;
    }
    if (action !== "INTAKE" && action !== "DEMO" && !S.current) {
      setNotice("请先选择一个案件。", true);
      return;
    }
    if (action === "REGISTER_EVIDENCE") {
      globalThis.OceanV21Collaboration?.openFiles(data);
      return;
    }
    S.dialog = {
      action,
      case_id: S.current?.id,
      revision: S.current?.revision,
      identity: identity(),
      contract,
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
    for (const key of ["amount_minor", "expected_net_minor", "supported_minor", "liable_minor", "stage_number"])
      if (key in values) { if (values[key] === "") delete values[key]; else values[key] = Number(values[key]); }
    for (const key of [
      "external_deadline",
      "merchant_deadline",
      "internal_deadline", "occurred_at", "received_at", "follow_up_at",
    ]) {
      if (values[key]) {
        const timestamp = new Date(values[key]);
        if (!Number.isFinite(timestamp.getTime())) throw new Error(`请填写有效的${key.includes("external") ? "外部截止" : key.includes("merchant") ? "商户截止" : "内部截止"}时间。`);
        values[key] = timestamp.toISOString();
      }
      else delete values[key];
    }
    if ("required_evidence" in values) {
      if (values.required_evidence)
        values.required_evidence = values.required_evidence
          .split(/[,，\n]/)
          .map((s) => s.trim())
          .filter(Boolean);
      else values.required_evidence = [];
    }
    for (const key of ["applicable_facts", "locators"]) if (typeof values[key] === "string") values[key] = values[key].split(/\n/).map(value=>value.trim()).filter(Boolean);
    if (typeof values.evidence_ids === "string") values.evidence_ids = values.evidence_ids.split(/[,，\n]/).map((value) => value.trim()).filter(Boolean);
    for (const key of Object.keys(values))
      if (values[key] === "") delete values[key];
    return values;
  }
  function savePending() {
    if (S.pending)
      storage.set(`oceanpilot.v21.pending.${S.session?.user?.id || "anonymous"}`, JSON.stringify(S.pending));
    else storage.remove(`oceanpilot.v21.pending.${S.session?.user?.id || "anonymous"}`);
  }
  async function executePending() {
    if (!S.pending || S.busy) return;
    const pending = S.pending;
    if (
      pending.identity.actor !== S.session?.user?.id ||
      pending.identity.role !== S.role
    ) {
      setNotice(
        "此命令属于另一登录账号，请使用原账号恢复执行。",
        true,
      );
      return;
    }
    S.busy = true;
    $("submitDialog").disabled = true;
    try {
      const result = await api(
        pending.endpoint || "/commands",
        {
          method: "POST",
          body: JSON.stringify(pending.requestBody || pending.payload),
        },
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
      if (c && pending.payload.action === "INTAKE" && !globalThis.OCEAN_V2_NO_BOOT) {
        location.assign(caseHref(c.id));
        return;
      }
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
        showFieldErrors(error.body);
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
    if (d.identity.actor !== S.session?.user?.id || d.identity.role !== S.role) {
      $("dialogError").textContent = "登录账号已变化，请重新发起操作。";
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
        if (result.case && !globalThis.OCEAN_V2_NO_BOOT) {
          location.assign(caseHref(result.case.id));
          return;
        }
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
    let data;
    try { data = collectData($("actionForm")); }
    catch (error) { $("dialogError").textContent = error.message; $("dialogError").hidden = false; return; }
    if (d.action === "RECORD_OUTCOME") data.final = data.disposition === "FINAL";
    const validationErrors = validateCommandData(data, d.contract);
    if (validationErrors.length) { showFieldErrors({field_errors: validationErrors}); $("dialogError").textContent = "请核对标出的字段后再确认。"; $("dialogError").hidden = false; return; }
    const currentContract = actionContract(d.action);
    if (d.action !== "INTAKE" && (!currentContract?.enabled || currentContract.revision !== undefined && currentContract.revision !== d.revision)) {
      $("dialogError").textContent = currentContract?.blocked_reason || "此操作当前不可执行，请重新核对案件。";
      $("dialogError").hidden = false; return;
    }
    if (d.action === "CONFIRM_RULE" && !data.allowed_actions?.length) {
      $("dialogError").textContent =
        "请根据已核对的规则来源明确选择至少一项允许的商户权利。";
      $("dialogError").hidden = false;
      return;
    }
    if (d.action === "RECORD_OUTCOME") data.final = data.disposition === "FINAL";
    if ((d.action === "FINAL_REVIEW" && data.decision === "APPROVE" || d.action === "APPROVE_PACKAGE") && !data.pii_checked) {
      $("dialogError").textContent = "批准前必须完成人工敏感信息检查。"; $("dialogError").hidden = false; return;
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
    const unchangedProposal =
      d.proposal &&
      !d.proposal.required_inputs?.length &&
      d.proposal.owner === S.role &&
      JSON.stringify(data) === JSON.stringify(d.proposalInitialData);
    if (d.proposalOrigin && !unchangedProposal) payload.proposal_origin = d.proposalOrigin;
    S.pending = {
      payload,
      identity: d.identity,
      ...(unchangedProposal
        ? {
            endpoint: `/cases/${encodeURIComponent(d.case_id)}/agent/proposals/${encodeURIComponent(d.proposal.id)}/execute`,
            requestBody: {
              command_id: payload.command_id,
              expected_revision: d.revision,
              confirmed: true,
            },
          }
        : {}),
    };
    savePending();
    await executePending();
  }
  async function logout() {
    if (S.busy) { setNotice("当前操作结果尚未确认，请先等待回执。", true); return; }
    try {
      await api("/session/logout", { method: "POST" });
      stopUpdates(); S.session = null; S.csrfToken = "";
      location.replace(`/v2/login?next=${encodeURIComponent(`/v2/${surface}`)}`);
    } catch (error) { setNotice(error.message, true); }
  }
  function bindEvents() {
    document.addEventListener("click", async (event) => {
      const button = event.target.closest("button");
      if (!button) return;
      if (button.dataset.agentCase) {
        await openCase(button.dataset.agentCase);
        S.agentCollapsed = false;
        renderAgentPanel();
        if (button.dataset.agentProposal)
          openAgentProposal(button.dataset.agentProposal);
        return;
      }
      if (button.dataset.agentProposal) {
        openAgentProposal(button.dataset.agentProposal);
        return;
      }
      if (button.hasAttribute("data-agent-collapse")) {
        S.agentCollapsed = !S.agentCollapsed;
        renderAgentPanel();
        return;
      }
      if (button.hasAttribute("data-agent-run")) {
        await runAgent();
        return;
      }
      if (button.dataset.agentPrepared) {
        S.agentPrepared = button.dataset.agentPrepared;
        renderAgentPanel();
        return;
      }
      if (button.dataset.agentPrompt) {
        await sendAgentMessage(button.dataset.agentPrompt);
        return;
      }
      if (button.dataset.case) {
        location.assign(caseHref(button.dataset.case));
        return;
      }
      if (button.dataset.queue) {
        if (S.isCasePage) {
          location.assign(`/v2/${surface}?queue=${encodeURIComponent(button.dataset.queue)}`);
          return;
        }
        S.queue = button.dataset.queue; S.offset = 0;
        await refresh(true);
        $("workspaceGrid").classList.add("show-queue");
        return;
      }
      if (button.hasAttribute("data-reload")) { await refresh(true); return; }
      if (button.dataset.page) {
        S.offset = Math.max(0, S.offset + (button.dataset.page === "next" ? S.limit : -S.limit));
        await refresh(true); return;
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
        location.assign(`/v2/${surface}`);
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
    document.addEventListener("submit", (event) => {
      if (event.target.id !== "agentMessageForm") return;
      event.preventDefault();
      sendAgentMessage();
    });
    document.addEventListener("input", (event) => {
      if (event.target.id === "agentMessage") preserveAgentDraft();
    });
    document.addEventListener("keydown", (event) => {
      if (
        event.target.id === "agentMessage" &&
        event.key === "Enter" &&
        !event.shiftKey &&
        !event.isComposing
      ) {
        event.preventDefault();
        sendAgentMessage();
      }
    });
    $("refreshButton").addEventListener("click", () => S.isLibraryPage
      ? globalThis.OceanV2Library.mount({ api, openTemplate: undefined }) : Promise.allSettled([refresh(), globalThis.OceanV21Intake?.refresh()]));
    $("logoutButton").addEventListener("click", logout);
    $("intakeButton").addEventListener("click", () => globalThis.OceanV21Intake?.open());
    $("caseSearch").addEventListener("input", (event) => {
      S.search = event.target.value; S.offset = 0;
      clearTimeout(S.searchTimer);
      S.searchTimer = setTimeout(() => refresh(true), 250);
    });
    $("assignedFilter")?.addEventListener("change", (event) => {
      S.assignedTo = event.target.value; S.offset = 0; refresh(true);
    });
    $("actionForm").addEventListener("submit", submitDialog);
    $("closeDialog").addEventListener("click", closeDialog);
    $("cancelDialog").addEventListener("click", closeDialog);
    $("actionDialog").addEventListener("cancel", (event) => {
      if (S.busy) event.preventDefault();
      else S.dialog = null;
    });
  }
  async function initialize() {
    try {
      const session = await api("/session");
      if (!session.user?.id) throw Object.assign(new Error("请先登录你的账号。"), { status: 401 });
      S.session = session; S.csrfToken = session.csrf_token || "";
      S.role = session.user.role;
      S.merchantId = session.user.merchant_id || list(session.user.merchant_ids)[0] || "";
      const permittedSurface = S.role === "MERCHANT" ? "merchant" : session.surface || "operations";
      if (surface !== permittedSurface && !(surface === "governance" && ["ADMIN", "SUPERVISOR"].includes(S.role)))
        throw Object.assign(new Error("此账号不能访问这个工作空间，请返回自己的案件列表。"), { status: 403 });
      $("accountName").textContent = session.user.display_name || session.user.id;
      $("workspaceHome").href = `/v2/${permittedSurface}`;
      $("brandHome").href = `/v2/${permittedSurface}`;
      $("workspaceName").textContent = S.role === "MERCHANT" ? "我的案件" : "我的工作队列";
      S.assignedTo = S.role === "OPERATOR" ? "me" : "";
    } catch (error) {
      if (error.status === 401) {
        if (!globalThis.OCEAN_V2_NO_BOOT) location.replace(`/v2/login?next=${encodeURIComponent(location.pathname + location.search)}`);
        return;
      }
      $("workspaceGrid").innerHTML = `<section class="access-error"><h2>${error.status === 403 ? "无法访问此工作空间" : "暂时无法验证账号"}</h2><p>${esc(error.message)}</p><a class="button primary" href="/v2/${S.role === "MERCHANT" ? "merchant" : "operations"}">返回我的工作空间</a></section>`;
      $("pageTitle").textContent = "访问未完成";
      $("metrics").hidden = true; $("intakeButton").hidden = true;
      $("identityNote").textContent = S.session?.user?.display_name || "请重新登录后继续。";
      $("logoutButton").addEventListener("click", logout);
      return;
    }
    const initialURL = new URL(location.href);
    const legacyCase = initialURL.searchParams.get("case");
    if (!routeCase && legacyCase && surface !== "governance") {
      initialURL.pathname = caseHref(legacyCase);
      initialURL.searchParams.delete("case");
      location.replace(initialURL);
      return;
    }
    S.queue = [...queueViews, ["PROCESSING", "处理中"]].some(([key]) => key === initialURL.searchParams.get("queue"))
      ? initialURL.searchParams.get("queue") : "ALL";
    document.body.classList.add(S.isCasePage ? "case-page" : "list-page");
    document.body.dataset.surface = surface;
    $("assignedFilterGroup").hidden = surface === "merchant";
    $("assignedFilter").value = S.assignedTo;
    $("caseDetail").hidden = !S.isCasePage;
    document.querySelector(".case-queue").hidden = S.isCasePage;
    $("metrics").hidden = S.isCasePage;
    $("agentInbox").hidden = true;
    const status = document.createElement("span");
    status.id = "syncStatus"; status.className = "sync-status";
    status.setAttribute("role", "status"); status.textContent = S.isLibraryPage ? "来源资料" : "正在连接自动同步…";
    $("refreshButton").before(status);
    $("refreshButton").textContent = S.isLibraryPage ? "重新载入资料" : "重新同步";
    const details =
      surface === "merchant"
        ? [
            "OceanPilot 商户客户端",
            "MERCHANT × OCEANPILOT",
            S.isCasePage ? "我的案件" : "我的争议案件",
            S.isCasePage ? "查看处理进度、补齐证据，并与 OceanPayment 协作。" : "查看待办与最新反馈，选择一笔案件继续处理。",
          ]
        : surface === "governance"
          ? [
              "平台治理",
              "GOVERNANCE WORKSPACE",
              "让自动化，始终有边界。",
              "查看集成状态、规则来源、权限与知识审核。",
            ]
          : [
              "OceanPayment 争议运营",
              "OCEANPAYMENT × OCEANPILOT",
              S.isCasePage ? "案件处理" : "争议案件",
              S.isCasePage ? "从商户响应到审核、上游结果与资金核对。" : "掌握全部案件的处理进度，找到需要团队接手的下一步。",
            ];
    if (S.isLibraryPage) {
      details[0] = "Visa / Mastercard 案例库";
      details[2] = "指南案例与演练模板";
      details[3] = "使用已上传的提纯资料，查看原文依据、规则还原与合成演练。";
    }
    $("surfaceBreadcrumb").textContent = details[0];
    $("eyebrow").textContent = details[1];
    $("pageTitle").textContent = details[2];
    $("pageDescription").textContent = details[3];
    document.title = `OceanPilot V2 · ${details[0]}`;
    $("avatar").textContent = S.role === "MERCHANT" ? "M" : S.role === "AGENT" ? "AI" : "OP";
    $("identityNote").textContent = `${S.session.user.display_name || S.session.user.id} · ${label(S.role)}${surface === "merchant" ? " · 仅访问获授权的商户案件" : " · 按任务与案件权限协作"}`;
    $("intakeButton").hidden = true;
    $("workspaceGrid").hidden = surface === "governance";
    $("workspaceGrid").classList.toggle(
      "merchant-layout",
      surface === "merchant",
    );
    $("agentPanel").hidden = surface === "governance" || !S.isCasePage;
    renderCollaborationRoles();
    $("governanceView").hidden = surface !== "governance";
    $("queueNav").hidden = surface === "governance" || S.isLibraryPage;
    $("queueNavLabel").hidden = surface === "governance" || S.isLibraryPage;
    const requestedTab = new URL(location.href).searchParams.get("tab");
    if (
      tabs.some(([key]) => key === requestedTab) &&
      !(
        surface === "merchant" &&
        !["overview", "tasks", "evidence", "collaboration", "outcome"].includes(
          requestedTab,
        )
      )
    )
      S.tab = requestedTab;
    try {
      S.pending = JSON.parse(storage.get(`oceanpilot.v21.pending.${S.session?.user?.id || "anonymous"}`) || "null");
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
    if (surface === "operations") {
      const link = document.createElement("a");
      link.className = "button secondary"; link.id = "caseLibraryLink";
      link.href = "/v2/operations/library"; link.textContent = "Visa / Mastercard 案例库";
      $("intakeButton").before(link);
    }
    if (S.isLibraryPage) {
      document.body.classList.add("library-page");
      document.querySelector(".page-heading > div:first-child").hidden = true;
      $("caseLibraryLink").hidden = true;
      const host = document.createElement("section"); host.id = "libraryView";
      $("workspaceGrid").before(host);
      $("workspaceGrid").hidden = true; $("metrics").hidden = true;
      $("collaborationRoles").hidden = true;
      globalThis.OceanV2Library.mount({ api, openTemplate: undefined });
    }
    bindEvents();
    if (surface === "operations" && S.role === "OPERATOR" && globalThis.OceanV21Intake) {
      let host = null;
      if (!S.isCasePage && !S.isLibraryPage) { host = document.createElement("section"); host.id = "intakeEvents"; $("workspaceGrid").before(host); }
      globalThis.OceanV21Intake.mount({ host, api, onCaseOpen: (id) => location.assign(caseHref(id)) });
    }
    window.addEventListener("scroll", fitAgentPanel, { passive: true });
    window.addEventListener("resize", fitAgentPanel, { passive: true });
    window.addEventListener("pagehide", () => { preserveAgentDraft(); stopUpdates(); });
    window.addEventListener("pageshow", () => startUpdates());
    window.addEventListener("online", () => { stopUpdates(); startUpdates(); });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") { stopUpdates(); startUpdates(); }
    });
    refresh();
  }
  globalThis.OceanV2 = {
    state: S,
    reconcileUpdates,
    refresh,
    caseHref,
    startUpdates,
    stopUpdates,
    esc,
    uuid,
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
    renderAgentPanel,
    renderAgentInbox,
    agentSource,
    proposalsFor,
    refreshAgent,
    sendAgentMessage,
    runAgent,
    openAgentProposal,
    acceptAgentActivity,
  };
  if (!globalThis.OCEAN_V2_NO_BOOT) initialize();
})();
