"""Self-contained synthetic payment-incident cockpit."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_PAYMENT_DEMO_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OceanPilot · 支付异常协作</title>
  <style>
    :root {
      color-scheme: light dark;
      --canvas: #f4f6f9; --surface: #fff; --ink: #172033; --muted: #657086;
      --line: #dfe4ec; --accent: #315ee7; --accent-soft: #eaf0ff;
      --good: #087f5b; --warn: #a15c00; --danger: #ba2525;
      font-family: Inter, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    @media (prefers-color-scheme: dark) { :root {
      --canvas: #0d1119; --surface: #151c27; --ink: #edf1f7; --muted: #9aa6b7;
      --line: #2a3443; --accent: #7195ff; --accent-soft: #1b2947;
      --good: #51cf9b; --warn: #f0b35b; --danger: #ff8787;
    } }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--canvas); color: var(--ink); line-height: 1.55; }
    header { display: flex; justify-content: space-between; align-items: center; padding: 16px 24px;
      border-bottom: 1px solid var(--line); background: var(--surface); }
    a { color: var(--accent); text-decoration: none; }
    main { width: min(1120px, calc(100% - 32px)); margin: 28px auto 48px; }
    h1 { margin: 6px 0; font-size: clamp(28px, 5vw, 48px); }
    h2 { margin: 0 0 12px; font-size: 17px; }
    p { margin: 6px 0; }
    .eyebrow { color: var(--accent); font-size: 12px; font-weight: 750; letter-spacing: .12em; }
    .boundary { margin: 18px 0 24px; padding: 12px 14px; border: 1px solid var(--line);
      border-left: 4px solid var(--accent); border-radius: 8px; color: var(--muted);
      background: var(--surface); }
    .scenarios { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    button { border: 1px solid var(--line); border-radius: 9px; padding: 11px 13px; font: inherit;
      background: var(--surface); color: var(--ink); cursor: pointer; text-align: left; }
    button:hover { border-color: var(--accent); }
    button.selected { border-color: var(--accent); background: var(--accent-soft);
      color: var(--accent); }
    button:disabled { opacity: .5; cursor: wait; }
    .toolbar { display: flex; gap: 10px; margin: 14px 0 22px; }
    .primary { background: var(--accent); color: white; border-color: var(--accent);
      font-weight: 700; }
    .grid { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(280px, .65fr);
      gap: 16px; }
    .stack { display: grid; gap: 16px; }
    .card { padding: 18px; border: 1px solid var(--line); border-radius: 12px;
      background: var(--surface); }
    .status { color: var(--muted); }
    .status[data-kind="success"] { color: var(--good); }
    .status[data-kind="error"] { color: var(--danger); }
    .progress { height: 8px; margin: 10px 0; border-radius: 6px; overflow: hidden;
      background: var(--line); }
    .progress span { display: block; width: 0; height: 100%; background: var(--accent); }
    dl { margin: 0; display: grid; gap: 9px; }
    dl div { border-top: 1px solid var(--line); padding-top: 8px; }
    dt { color: var(--muted); font-size: 12px; }
    dd { margin: 2px 0 0; overflow-wrap: anywhere; }
    ul { margin: 8px 0 0; padding-left: 20px; }
    code { font-size: 12px; overflow-wrap: anywhere; }
    .empty { color: var(--muted); }
    .tag { display: inline-block; padding: 3px 8px; border-radius: 999px; color: var(--accent);
      background: var(--accent-soft); font-size: 11px; font-weight: 750; letter-spacing: .07em; }
    @media (max-width: 820px) {
      .scenarios { grid-template-columns: 1fr 1fr; }
      .grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 520px) {
      .scenarios { grid-template-columns: 1fr; }
      header { padding: 12px 16px; }
    }
    :focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
  </style>
</head>
<body>
  <header><a href="/demo">← 返回拒付处理</a> <strong class="tag">SYNTHETIC</strong></header>
  <main>
    <p class="eyebrow">PAYMENT INCIDENT · VERIFIED VERTICAL SLICE</p>
    <h1>支付异常协作</h1>
    <p>从问题建案、角色化补证到确定性诊断与责任建议，所有结论均来自持久化内核响应。</p>
    <p class="boundary"><strong>演示边界：</strong>本页仅使用合成数据，不连接生产系统；
      系统不执行支付、退款、风控放行、资金移动或生产配置变更。
      人工确认由飞书签名演示链记录，本页不代替审批。</p>

    <section aria-labelledby="scenario-title">
      <h2 id="scenario-title">选择一个支付异常场景</h2>
      <div class="scenarios" id="scenario-list">
        <button type="button" data-scenario="3ds_callback_incomplete">3DS / 回调未完成</button>
        <button type="button" data-scenario="risk_decline">风控拒绝</button>
        <button type="button" data-scenario="merchant_configuration_mismatch">
          商户侧配置不匹配
        </button>
        <button type="button" data-scenario="psp_configuration_mismatch">PSP 侧配置不匹配</button>
      </div>
      <div class="toolbar">
        <button type="button" id="run" class="primary">运行合成闭环</button>
        <button type="button" id="reset">重置 / 新建案件</button>
      </div>
    </section>

    <div class="grid">
      <div class="stack">
        <section class="card" aria-labelledby="runtime-title">
          <h2 id="runtime-title">运行状态</h2>
          <p id="runtime" class="status" aria-live="polite">选择场景后开始。</p>
          <dl id="case-fields"></dl>
        </section>
        <section class="card" aria-labelledby="diagnosis-title">
          <h2 id="diagnosis-title">确定性诊断</h2>
          <div id="diagnosis" class="empty">证据达标后显示 API 返回的诊断。</div>
        </section>
        <section class="card" aria-labelledby="route-title">
          <h2 id="route-title">责任建议与下一动作</h2>
          <div id="route" class="empty">尚无责任建议。</div>
        </section>
      </div>
      <div class="stack">
        <section class="card" aria-labelledby="readiness-title">
          <h2 id="readiness-title">证据就绪度</h2>
          <div class="progress" aria-hidden="true"><span id="readiness-bar"></span></div>
          <dl id="readiness"></dl>
        </section>
        <section class="card" aria-labelledby="evidence-title">
          <h2 id="evidence-title">证据引用</h2>
          <ul id="evidence"><li class="empty">尚未提交证据。</li></ul>
        </section>
        <section class="card" aria-labelledby="audit-title">
          <h2 id="audit-title">诊断审计引用</h2>
          <dl id="audit"></dl>
          <p class="empty">审计引用证明结论持久化；不表示业务动作已执行。</p>
        </section>
      </div>
    </div>
  </main>
  <script>
    "use strict";
    const CASES_API = "/api/v1/cases";
    const OBSERVED_AT = "2026-08-05T04:00:00Z";
    const COMMON_FACTS = [
      ["transaction.occurred_at", OBSERVED_AT],
      ["context.environment", "PROD"],
      ["integration.type", "API"],
    ];
    const SCENARIOS = {
      three_ds_callback_incomplete: [
        ["symptom.status", "PENDING"],
        ["authentication.status", "REQUIRED"],
        ["callback.delivery_status", "NOT_RECEIVED"],
      ],
      risk_decline: [
        ["symptom.status", "DECLINED"],
        ["risk.decision_code", "RISK_DECLINE"],
      ],
      merchant_configuration_mismatch: [
        ["symptom.status", "PENDING"],
        ["payment.method", "CARD"],
        ["configuration.check_result", "MERCHANT_SIDE_MISMATCH"],
      ],
      psp_configuration_mismatch: [
        ["symptom.status", "PENDING"],
        ["payment.method", "CARD"],
        ["configuration.check_result", "PSP_PROFILE_MISMATCH"],
      ],
    };
    const labels = {
      three_ds_callback_incomplete: "3DS / 回调未完成",
      risk_decline: "风控拒绝",
      merchant_configuration_mismatch: "商户侧配置不匹配",
      psp_configuration_mismatch: "PSP 侧配置不匹配",
    };
    let selected = "three_ds_callback_incomplete";
    let running = false;
    let evidenceCodes = new Map();

    const byId = (id) => document.getElementById(id);
    const text = (value, fallback = "—") => {
      return value === null || value === undefined || value === "" ? fallback : String(value);
    };
    function clear(node) { node.replaceChildren(); }
    function addDefinition(container, label, value) {
      const row = document.createElement("div");
      const term = document.createElement("dt");
      const detail = document.createElement("dd");
      term.textContent = label;
      detail.textContent = text(value);
      row.append(term, detail);
      container.append(row);
    }
    function setRuntime(message, kind = "neutral") {
      const node = byId("runtime");
      node.textContent = message;
      node.dataset.kind = kind;
    }
    function setRunning(value) {
      running = value;
      document.querySelectorAll("button").forEach((button) => { button.disabled = value; });
    }

    async function publicRequest(method, path, body, failedStage) {
      const options = { method, headers: { Accept: "application/json" } };
      if (body !== undefined) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(body);
      }
      const response = await fetch(path, options);
      const problem = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw {
          failedStage,
          status: response.status,
          code: problem.code || "REQUEST_FAILED",
          traceId: response.headers.get("X-Trace-ID") || "unavailable",
        };
      }
      return problem;
    }

    function renderCase(view) {
      const fields = byId("case-fields");
      clear(fields);
      addDefinition(fields, "Case ID", view.case.case_id);
      addDefinition(fields, "状态", view.case.status);
      addDefinition(
        fields,
        "Case / evidence revision",
        `${view.case.case_revision} / ${view.case.evidence_revision}`,
      );
      renderReadiness(view.case.readiness);
      evidenceCodes = new Map(view.evidence.map((item) => [item.evidence_id, item.evidence_code]));
      const list = byId("evidence");
      clear(list);
      view.evidence.forEach((item) => {
        const row = document.createElement("li");
        row.textContent = `${item.evidence_code} · ${item.availability} · ${item.evidence_id}`;
        list.append(row);
      });
    }

    function renderReadiness(readiness) {
      const fields = byId("readiness");
      clear(fields);
      const ratio = Math.round(Number(readiness.completion_ratio) * 100);
      byId("readiness-bar").style.width = `${ratio}%`;
      addDefinition(fields, "完成度", `${ratio}%`);
      addDefinition(fields, "状态", readiness.ready ? "证据门槛已达标" : readiness.stop_reason);
      addDefinition(fields, "仍缺证据", readiness.missing_fields.join(" · ") || "无");
      addDefinition(fields, "下一补问", readiness.next_question);
      addDefinition(fields, "目标角色", readiness.target_role);
    }

    function referencedCodes(refs) {
      return refs.map((id) => evidenceCodes.get(id) || id).join(" · ");
    }

    function renderDiagnosis(result) {
      const diagnosis = result.diagnosis;
      const hypotheses = byId("diagnosis");
      clear(hypotheses);
      diagnosis.hypotheses.forEach((hypothesis) => {
        const card = document.createElement("article");
        const title = document.createElement("h3");
        const explanation = document.createElement("p");
        const metadata = document.createElement("p");
        const confidence = Math.round(Number(hypothesis.confidence_score) * 100);
        title.textContent = `${hypothesis.cause_code} · ${confidence}%`;
        explanation.textContent = hypothesis.explanation;
        const refs = referencedCodes(hypothesis.evidence_refs);
        metadata.textContent = `${hypothesis.rule_id} · 证据：${refs}`;
        card.append(title, explanation, metadata);
        hypotheses.append(card);
      });
      if (!diagnosis.hypotheses.length) {
        hypotheses.textContent = "没有确定性候选原因，必须人工复核。";
      }

      const route = byId("route");
      clear(route);
      const decision = diagnosis.routing_decision;
      if (decision) {
        const fields = document.createElement("dl");
        addDefinition(
          fields,
          "责任域 / 优先级",
          `${decision.responsible_team} / ${decision.priority}`,
        );
        addDefinition(fields, "路由理由", decision.reason);
        addDefinition(fields, "证据引用", referencedCodes(decision.evidence_refs));
        const review = decision.requires_human
          ? diagnosis.review_reasons.join(" · ")
          : "不要求";
        const nextAction = diagnosis.ticket_draft
          ? diagnosis.ticket_draft.next_action
          : "等待人工决定";
        addDefinition(fields, "人工复核", review);
        addDefinition(fields, "安全下一动作", nextAction);
        route.append(fields);
      } else {
        route.textContent = "内核未返回责任建议，不做推测。";
      }

      const audit = byId("audit");
      clear(audit);
      addDefinition(audit, "写入结果", result.outcome);
      addDefinition(audit, "Diagnosis ID", result.audit_reference.diagnosis_id);
      addDefinition(audit, "Case revision", result.audit_reference.case_revision);
      addDefinition(audit, "Evidence revision", result.audit_reference.evidence_revision);
    }

    async function runScenario() {
      if (running) return;
      setRunning(true);
      resetOutput();
      try {
        setRuntime(`正在建案：${labels[selected]}`);
        const caseToken = crypto.randomUUID();
        let view = await publicRequest("POST", CASES_API, {
          case_type: "PAYMENT_INCIDENT",
          summary: `Synthetic ${selected} incident`,
          merchant_ref: `synthetic-${caseToken}`,
          synthetic: true,
        }, "CREATE_CASE");
        renderCase(view);

        const facts = [
          ["transaction.reference", `synthetic-${caseToken}`],
          ...COMMON_FACTS,
          ...SCENARIOS[selected],
        ];
        for (const [code, value] of facts) {
          setRuntime(`正在补证：${code}`);
          view = await publicRequest("POST", `${CASES_API}/${view.case.case_id}/evidence`, {
            evidence_id: crypto.randomUUID(),
            evidence_code: code,
            availability: "AVAILABLE",
            typed_value: value,
            observed_at: OBSERVED_AT,
            source_ref: "synthetic:payment-cockpit",
          }, "ADD_EVIDENCE");
          renderCase(view);
        }

        if (!view.case.readiness.ready) {
          throw {
            failedStage: "READINESS",
            status: 409,
            code: "CASE_NOT_READY",
            traceId: "unavailable",
          };
        }
        setRuntime("证据已达标，正在请求确定性诊断。");
        const result = await publicRequest(
          "POST",
          `${CASES_API}/${view.case.case_id}/diagnose`,
          undefined,
          "DIAGNOSE",
        );
        renderDiagnosis(result);
        setRuntime("支付异常闭环完成；结论和审计引用均来自持久化 API。", "success");
      } catch (error) {
        const failure = [
          `运行停止 · 阶段 ${text(error.failedStage)}`,
          `HTTP ${text(error.status)}`,
          text(error.code),
          `Trace ${text(error.traceId)}`,
        ].join(" · ");
        setRuntime(failure, "error");
      } finally {
        setRunning(false);
      }
    }

    function resetOutput() {
      evidenceCodes = new Map();
      ["case-fields", "readiness", "diagnosis", "route", "audit"].forEach((id) => clear(byId(id)));
      byId("readiness-bar").style.width = "0";
      const list = byId("evidence");
      clear(list);
      const empty = document.createElement("li");
      empty.className = "empty";
      empty.textContent = "尚未提交证据。";
      list.append(empty);
      setRuntime("已重置。再次运行会创建新的合成案件。");
    }

    document.querySelectorAll("[data-scenario]").forEach((button) => {
      button.addEventListener("click", () => {
        selected = button.dataset.scenario;
        document.querySelectorAll("[data-scenario]").forEach((item) => {
          item.classList.toggle("selected", item === button);
        });
        setRuntime(`已选择：${labels[selected]}`);
      });
    });
    document.querySelector('[data-scenario="3ds_callback_incomplete"]').classList.add("selected");
    byId("run").addEventListener("click", runScenario);
    byId("reset").addEventListener("click", resetOutput);
  </script>
</body>
</html>
"""


@router.get("/demo/payment-incident", include_in_schema=False, response_class=HTMLResponse)
def payment_incident_demo_page() -> HTMLResponse:
    return HTMLResponse(_PAYMENT_DEMO_HTML)
