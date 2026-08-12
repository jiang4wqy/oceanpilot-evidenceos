"use strict";

document.documentElement.classList.add("js-ready");

const byId = (id) => document.getElementById(id);
const setText = (id, value) => { const node = byId(id); if (node) node.textContent = value ?? "—"; };
const formatTime = (value) => value ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "medium" }).format(new Date(value)) : "—";
const listText = (items, empty = "无") => items && items.length ? items.join(" · ") : empty;

function addDefinition(container, label, value) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label; detail.textContent = value ?? "—";
  wrapper.append(term, detail); container.append(wrapper);
}

function addCitations(container, citations) {
  const list = document.createElement("ul"); list.className = "citation-list";
  citations.forEach((citation) => {
    const item = document.createElement("li"); const link = document.createElement("a");
    link.href = `#evidence-${citation.evidence_id}`; link.textContent = citation.evidence_code;
    item.append(link); list.append(item);
  });
  container.append(list);
}

function renderCase(data) {
  setText("case-title", data.case.summary); setText("case-summary", "同一持久化案件的安全只读视图");
  setText("merchant-ref", data.case.merchant_ref); setText("case-id", data.case.case_id);
  setText("case-status", data.case.status); setText("case-revision", String(data.case.case_revision));
  setText("evidence-revision", String(data.case.evidence_revision));
  setText("completion-ratio", `${Math.round(Number(data.readiness.completion_ratio) * 100)}%`);
  setText("readiness-state", data.readiness.ready ? "证据门槛已达标" : "仍需补充证据");
  const readiness = byId("readiness-details");
  addDefinition(readiness, "Stop reason", data.readiness.stop_reason);
  addDefinition(readiness, "Missing", listText(data.readiness.missing_fields));
  addDefinition(readiness, "Known unknown", listText(data.readiness.known_unknown_fields));
  addDefinition(readiness, "Target role", data.readiness.target_role);
  addDefinition(readiness, "Next question", data.readiness.next_question);
  addDefinition(readiness, "Question reason", data.readiness.question_reason);

  const evidenceList = byId("evidence-list");
  data.evidence.forEach((evidence) => {
    const card = document.createElement("article"); card.className = "evidence-card"; card.id = `evidence-${evidence.evidence_id}`;
    [["证据代码", evidence.evidence_code], ["值", evidence.typed_value ?? evidence.availability], ["来源", `${evidence.source_type} · ${evidence.source_reliability}`], ["状态 / 时间", `${evidence.active_state} · ${formatTime(evidence.collected_at)}`]].forEach(([label, value]) => {
      const group = document.createElement("div"); const small = document.createElement("span"); const strong = document.createElement(label === "证据代码" ? "code" : "strong");
      small.textContent = label; strong.textContent = value; group.append(small, strong); card.append(group);
    });
    evidenceList.append(card);
  });

  const diagnosisContent = byId("diagnosis-content"); const responsibility = byId("responsibility-content");
  if (!data.diagnosis) {
    const empty = document.createElement("article"); empty.textContent = "尚未诊断。"; diagnosisContent.append(empty);
    const pending = document.createElement("article"); pending.textContent = "待人工分配。"; responsibility.append(pending);
  } else {
    setText("diagnosis-meta", `${data.diagnosis.policy_version} · ${data.diagnosis.engine_version} · ${data.diagnosis.status}`);
    if (!data.diagnosis.hypotheses.length) { const empty = document.createElement("article"); empty.textContent = "无确定性候选，需要人工复核。"; diagnosisContent.append(empty); }
    data.diagnosis.hypotheses.forEach((hypothesis) => {
      const card = document.createElement("article"); const title = document.createElement("h3"); const explanation = document.createElement("p"); const meta = document.createElement("p");
      title.textContent = `${hypothesis.cause_code} · ${Math.round(Number(hypothesis.confidence_score) * 100)}%`;
      explanation.textContent = hypothesis.explanation; meta.textContent = `${hypothesis.rule_id} · ${hypothesis.confidence_method} · ${hypothesis.next_verification_action}`;
      card.append(title, explanation, meta); addCitations(card, hypothesis.citations); diagnosisContent.append(card);
    });
    if (data.diagnosis.routing) {
      const card = document.createElement("article"); const title = document.createElement("h3"); const reason = document.createElement("p"); const next = document.createElement("p");
      title.textContent = `${data.diagnosis.routing.responsible_team} · ${data.diagnosis.routing.priority}`;
      reason.textContent = data.diagnosis.routing.reason; next.textContent = `下一动作：${data.diagnosis.next_action ?? "待人工决定"}；复核原因：${listText([...data.diagnosis.review_reasons])}`;
      card.append(title, reason, next); addCitations(card, data.diagnosis.routing.citations); responsibility.append(card);
    } else { const pending = document.createElement("article"); pending.textContent = "待人工分配；系统没有伪造责任团队。"; responsibility.append(pending); }
  }

  const confirmation = byId("confirmation-content"); confirmation.textContent = ({
    CONFIRMED: `CONFIRMED · ${formatTime(data.confirmation.occurred_at)} · 确认仅记录建议，没有执行任何业务动作。`,
    AWAITING_CONFIRMATION: "AWAITING CONFIRMATION · 当前诊断等待人工确认。",
    UNAVAILABLE: "UNAVAILABLE · 飞书确认读取未连接或暂不可用，不能据此判断是否已确认。",
    NOT_REQUIRED: "NOT REQUIRED · 当前诊断不要求人工确认。",
    NOT_APPLICABLE: "NOT APPLICABLE · 当前没有可确认的诊断。",
  })[data.confirmation.state];

  const timeline = byId("timeline-list"); data.timeline.forEach((event) => {
    const item = document.createElement("li"); const time = document.createElement("time"); const title = document.createElement("strong"); const detail = document.createElement("p");
    time.dateTime = event.occurred_at; time.textContent = formatTime(event.occurred_at); title.textContent = `${event.event_type} · ${event.result}`;
    detail.textContent = `${event.from_status ?? "START"} → ${event.to_status ?? "UNCHANGED"} · case r${event.case_revision} / evidence r${event.evidence_revision}${event.reason_code ? ` · ${event.reason_code}` : ""}`;
    item.append(time, title, detail); timeline.append(item);
  });
  if (data.audit_truncated) { const item = document.createElement("li"); item.textContent = "时间线仅展示前 200 条安全事件。"; timeline.append(item); }
}

async function loadCase() {
  const loading = byId("case-loading"); const caseId = location.pathname.split("/").filter(Boolean).at(-1);
  try {
    const response = await fetch(`/api/v1/demo/cases/${encodeURIComponent(caseId)}`, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("safe-load-failure");
    renderCase(await response.json()); loading.hidden = true;
  } catch (_) { loading.textContent = "案件读取失败。请检查案件链接或稍后重试。"; loading.classList.add("error"); }
}

if (document.body.dataset.page === "case") loadCase();
