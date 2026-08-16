# ruff: noqa: E501

"""Small browser-side internationalisation runtime for the two local consoles."""

import json

COMMON_TRANSLATIONS = {
    "语言": "Language",
    "中文": "中文",
    "英文": "English",
    "商户": "Merchant",
    "状态": "Status",
    "争议原因": "Dispute reason",
    "案件": "Case",
    "案件号": "Case ID",
    "待确认": "Pending confirmation",
    "待确认原因": "Reason to confirm",
    "待补资料": "Evidence required",
    "评估完成": "Assessment complete",
    "待识别": "Identification pending",
    "未调用": "Not called",
    "正常": "Healthy",
    "关注": "Attention",
    "异常": "Degraded",
    "提示": "Notice",
    "预警": "Warning",
    "严重": "Critical",
    "只读": "Read only",
    "已启用": "Enabled",
    "等待数据": "Waiting for data",
    "等待首次刷新": "Waiting for first refresh",
    "读取中": "Loading",
    "正在读取": "Loading",
    "正在读取…": "Loading…",
    "正在从案件库读取…": "Loading from the case store…",
    "读取失败": "Load failed",
    "未知": "Unknown",
    "待处理": "Pending",
    "无需人工复核": "No manual review",
    "需人工复核": "Manual review required",
    "申诉已提交": "Appeal submitted",
    "申诉被阻断": "Appeal blocked",
    "评估次数": "Assessments",
    "低风险交易": "Low-risk transactions",
    "中风险交易": "Medium-risk transactions",
    "高风险交易": "High-risk transactions",
    "辅助说明": "Assisted explanation",
    "规则说明": "Rule explanation",
    "非本人交易": "Unauthorized transaction",
    "未收到商品": "Product not received",
    "未收到商品/服务": "Product/service not received",
    "商品或服务与描述不符": "Product/service not as described",
    "商品与描述不符": "Product not as described",
    "重复扣款": "Duplicate processing",
    "退款未入账": "Credit not processed",
    "订阅取消后仍扣款": "Charged after subscription cancellation",
    "授权异常": "Authorization error",
    "交易收据": "Transaction receipt",
    "AVS 验证结果": "AVS result",
    "AVS 地址验证结果": "AVS result",
    "CVV 验证结果": "CVV result",
    "CVV 校验结果": "CVV result",
    "3DS 认证记录": "3DS authentication record",
    "3DS 认证结果": "3DS authentication result",
    "设备与 IP 关联": "Device and IP correlation",
    "设备/IP 匹配": "Device/IP match",
    "物流跟踪号/轨迹": "Tracking number/history",
    "签收证明": "Proof of delivery",
    "收货地址匹配": "Delivery address match",
    "商品页面": "Product page",
    "商品描述": "Product description",
    "退款记录": "Refund record",
    "条款与退款政策": "Terms and refund policy",
    "客户沟通记录": "Customer communications",
    "取消订阅记录": "Subscription cancellation record",
    "历史交易记录": "Prior transaction history",
    "重复扣款核验": "Duplicate charge verification",
    "重复扣款核查": "Duplicate-charge check",
}


CLIENT_TRANSLATIONS = {
    **COMMON_TRANSLATIONS,
    "案件诊断系统": "Case diagnostics",
    "工作台": "Workspace",
    "案件中心": "Case center",
    "新建案件": "Create case",
    "交易风险": "Transaction risk",
    "商户工作台": "Merchant workspace",
    "搜索案件号或争议原因": "Search case ID or dispute reason",
    "未找到匹配案件，请检查案件号或争议原因。": "No matching case found. Check the case ID or dispute reason.",
    "只展示已在当前系统中创建并可重新读取的案件；待补资料案件可进入诊断。": "Only cases created and retrievable in this system are shown. Open a case that needs evidence to diagnose it.",
    "历史案件": "Case history",
    "待处理案件": "Pending cases",
    "状态说明": "Status guide",
    "案件号或争议原因": "Case ID or dispute reason",
    "全部状态": "All statuses",
    "操作": "Action",
    "需要人工确认争议原因": "A person must confirm the dispute reason",
    "进入诊断查看缺失清单": "Open diagnostics to see missing evidence",
    "可查看案件评估结果": "Assessment result available",
    "案件诊断": "Case diagnosis",
    "查看当前案件为什么无法继续，并在本页直接补交系统确认缺失的资料。": "See why this case cannot continue and submit the evidence the system confirms is missing.",
    "返回案件中心": "Back to case center",
    "提交成功": "Submitted",
    "完成并返回案件": "Done and return to case",
    "发生了什么": "What happened",
    "诊断结论": "Diagnosis",
    "正在读取案件状态": "Loading case status",
    "诊断结果将以案件库中的当前状态为准。": "The diagnosis reflects the current state in the case store.",
    "当前阶段": "Current stage",
    "建议下一步": "Recommended next step",
    "请按下方清单补交资料。": "Submit the evidence listed below.",
    "需要补交的资料": "Evidence to submit",
    "正在核对案件资料": "Checking case evidence",
    "清单只显示后端当前确认缺失的材料。": "This list only shows evidence currently confirmed missing by the backend.",
    "本次案件": "Current case",
    "记录校验": "Record validation",
    "后端可读": "Backend readable",
    "案件库可读": "Readable from case store",
    "资料状态": "Evidence status",
    "处理方式": "How to proceed",
    "1. 查看当前状态": "1. Review the current status",
    "2. 按后端清单逐项补交": "2. Submit each backend-listed item",
    "3. 提交后立即重新读取案件": "3. Reload the case after submission",
    "选择常见案件模板，确认案件说明后创建；此流程与失败案件诊断互相独立。": "Choose a common template and confirm the case description. Case creation is separate from failed-case diagnosis.",
    "案件信息": "Case information",
    "创建案件": "Create case",
    "创建后": "After creation",
    "新案件会进入案件详情。系统将识别已有材料，并显示后续案件处理缺口。": "The new case opens in case details. The system identifies available evidence and shows remaining gaps.",
    "案件详情": "Case details",
    "查看新建案件的处理阶段、材料缺口和评估结果。": "Review the case stage, evidence gaps, and assessment result.",
    "尚未选择案件。": "No case selected.",
    "案件处理": "Case handling",
    "材料就绪评估": "Evidence readiness assessment",
    "规则评估": "Rule assessment",
    "查看案件处理记录": "View case activity",
    "处理记录": "Activity",
    "建案后自动记录。": "Recorded automatically after case creation.",
    "判断依据": "Decision basis",
    "交易预警": "Transaction alert",
    "在交易完成前识别拒付风险，并提示应提前留存的材料。": "Identify chargeback risk before payment completion and see what evidence to retain.",
    "交易信息": "Transaction information",
    "实时评估": "Real-time assessment",
    "未完成 3DS": "3DS not completed",
    "AVS 地址不匹配": "AVS address mismatch",
    "跨境交易": "Cross-border transaction",
    "交易金额": "Transaction amount",
    "例如 4200": "For example, 4200",
    "开始评估": "Start assessment",
    "规则与运营": "Rules and operations",
    "查看信息安全拦截和案件处理概览，确认系统始终在授权边界内运行。": "Review security blocks and case-handling metrics to confirm the system stays within its authorized boundary.",
    "敏感信息检查": "Sensitive-data check",
    "卡号不入库": "Card numbers are not stored",
    "请退款到卡号 4111 1111 1111 1111": "Please refund card 4111 1111 1111 1111",
    "检查内容": "Check content",
    "检测到卡号后立即阻断，结果不会回显原文。": "Card numbers are blocked immediately and the original text is never echoed.",
    "案件概览": "Case overview",
    "本次演示": "Current session",
    "Visa 13.1 · 未收到货": "Visa 13.1 · Product not received",
    "已有 2 项 · 仍缺 3 项": "2 available · 3 missing",
    "客户声称未收到商品；商户目前只有交易收据和物流轨迹，尚未取得签收证明、地址匹配及客服沟通。": "The customer says the product was not received. The merchant has a receipt and tracking history but no proof of delivery, address match, or customer communications.",
    "Visa 10.4 · 非本人交易": "Visa 10.4 · Unauthorized transaction",
    "已有 1 项 · 仍缺 5 项": "1 available · 5 missing",
    "持卡人声称这笔交易不是本人、属于盗刷；商户目前只有交易收据，缺少 3DS、AVS/CVV、设备/IP 和历史交易关联。": "The cardholder says the transaction was unauthorized. The merchant only has a receipt and lacks 3DS, AVS/CVV, device/IP, and prior-transaction evidence.",
    "Mastercard 4853 · 商品不符": "Mastercard 4853 · Product not as described",
    "客户声称收到的商品与下单页面描述不符；商户目前只有交易收据和商品页面，缺少签收、沟通和政策材料。": "The customer says the product differs from the order page. The merchant has a receipt and product page but lacks delivery, communications, and policy evidence.",
    "未建案": "Not created",
    "确认原因": "Confirm reason",
    "补充材料": "Add evidence",
    "评估结果": "Assessment result",
    "风控团队": "Risk team",
    "客服团队": "Customer support",
    "业务团队": "Business team",
    "技术支持": "Technical support",
    "财务团队": "Finance team",
    "支付支持": "Payment support",
    "案件识别": "Case intake",
    "材料校验": "Evidence validation",
    "人工确认": "Human confirmation",
    "规则识别": "Rule classification",
    "案件创建": "Case created",
    "争议原因识别": "Dispute reason classified",
    "争议原因确认": "Dispute reason confirmed",
    "材料已补充": "Evidence added",
    "材料收集结束": "Evidence collection finalized",
    "低风险": "Low risk",
    "中风险": "Medium risk",
    "高风险": "High risk",
    "CVV 不匹配": "CVV mismatch",
    "设备与 IP 异常": "Device and IP mismatch",
    "高额交易": "High-value transaction",
    "高风险行业": "High-risk merchant category",
    "收货与账单地址不符": "Shipping and billing address mismatch",
    "历史争议较多": "Frequent prior disputes",
    "数字商品": "Digital goods",
    "系统管理": "System administration",
    "安全检查": "Security check",
    "案件库暂时无法读取，请稍后刷新。": "The case store is temporarily unavailable. Refresh and try again.",
    "查看案件": "View case",
    "查看诊断": "View diagnosis",
    "案件库有效实体": "Persisted case entity",
    "无待补项": "Nothing missing",
    "暂无有效案件记录": "No valid case records",
    "列表不使用预置案件；只有成功写入案件库且可重新读取的案件才会显示。": "This list has no placeholder cases. Only cases successfully stored and retrievable are shown.",
    "进入诊断": "Open diagnosis",
    "暂无待处理案件": "No pending cases",
    "争议原因尚未确认": "Dispute reason not confirmed",
    "系统已给出初步判断，需要人工确认后才能继续收集材料。": "The system has proposed a reason. A person must confirm it before evidence collection continues.",
    "请先确认争议原因，系统将在确认后生成缺失材料清单。": "Confirm the dispute reason first. The system will then generate the missing-evidence list.",
    "案件材料已齐全": "Case evidence is complete",
    "当前案件存在明确的证据缺口，下方清单来自后端当前状态。": "This case has confirmed evidence gaps. The list below comes from current backend state.",
    "当前没有待补资料。": "No evidence is currently missing.",
    "请按清单逐项补交；每次提交后系统会重新读取案件状态。": "Submit each listed item. The system reloads the case after every submission.",
    "可返回案件中心查看其他案件。": "Return to the case center to view another case.",
    "资料已齐全": "Evidence complete",
    "材料已齐全": "Evidence complete",
    "请先确认争议原因": "Confirm the dispute reason first",
    "原因确认后，系统才会生成本案件的待补资料清单。": "The missing-evidence list is generated after the reason is confirmed.",
    "清单来自案件后端；提交后会立即重新校验。": "The list comes from the case backend and is revalidated immediately after submission.",
    "本案件暂无待补资料": "No evidence is missing for this case",
    "当前状态以后端返回结果为准。": "The current status reflects the backend response.",
    "确认争议原因": "Confirm dispute reason",
    "确认后再继续补交材料": "Confirm before submitting evidence",
    "提交后系统将重新校验案件状态": "The system revalidates the case after submission",
    "补交资料": "Submit evidence",
    "没有待补资料。": "No evidence is missing.",
    "补全材料": "Complete evidence",
    "检查结果": "Review result",
    "生成材料": "Generate package",
    "1. 选择常见案件模板": "1. Choose a common case template",
    "2. 确认案件说明": "2. Confirm the case description",
    "创建完成后会进入案件详情，并列出案件处理所需材料。": "After creation, case details will show the evidence required for handling.",
    "确认创建案件": "Create case",
    "创建失败：案件说明不能为空。": "Case creation failed: the description cannot be empty.",
    "已确认": "Confirmed",
    "金额": "Amount",
    "充裕": "Plenty of time",
    "已逾期": "Overdue",
    "紧迫": "Urgent",
    "临近": "Due soon",
    "举证时限": "Evidence deadline",
    "尚未选择": "Not selected",
    "尚未打开案件详情": "No case details open",
    "请返回案件中心选择案件，或通过“新建案件”创建一个案件。": "Return to the case center to select a case, or create a new one.",
    "下一项证据": "Next evidence item",
    "材料尚未齐全": "Evidence is incomplete",
    "每补交一项，系统都会自动重新检查并提示下一项。": "After every submission, the system rechecks the case and identifies the next item.",
    "本次无法提供，提交人工复核": "Cannot provide this item; send for manual review",
    "材料收集已完成。请查看下方评估结果并选择下一步。": "Evidence collection is complete. Review the assessment below and choose the next step.",
    "（接受系统判定）": "Accept system classification",
    "关键": "Critical",
    "规则证据就绪度 · 非胜诉概率": "Rule-based evidence readiness · not win probability",
    "该分数仅表示规则要求的材料就绪程度，不代表真实胜诉概率；说明文字仅作辅助。": "This score only measures evidence readiness under the rules. It is not a real win probability; explanations are advisory only.",
    "生成申诉材料包": "Generate representment package",
    "预览申诉草稿": "Preview appeal draft",
    "人工确认并模拟提交": "Confirm and simulate submission",
    "案件未就绪": "Case not ready",
    "材料包": "Package",
    "可提交": "Ready to submit",
    "未就绪": "Not ready",
    "需证明": "Assertions",
    "随附": "Attachments",
    "依据": "Source",
    "合成默认规则": "Synthetic default rules",
    "边界：": "Limitation:",
    "模拟提交成功": "Simulated submission successful",
    "申诉": "Appeal",
    "暂无（运行一个案子后出现）": "None yet (run a case to generate metrics)",
    "需人工复核率": "Manual review rate",
    "辅助说明使用率": "Assisted-explanation usage",
    "请求无效": "Invalid request",
    "未发现明显风险因子": "No material risk factors found",
    "建议人工复核": "Manual review recommended",
    "通过": "Passed",
    "已拦截": "Blocked",
}


ADMIN_TRANSLATIONS = {
    **COMMON_TRANSLATIONS,
    "运行维护中心": "Operations center",
    "监控中心": "Monitoring",
    "运行总览": "Operations overview",
    "API 监控": "API monitoring",
    "故障预判": "Failure prediction",
    "业务指标": "Business metrics",
    "审计与配置": "Audit and configuration",
    "运行维护": "Operations",
    "监控客户服务": "Monitoring client service",
    "立即刷新": "Refresh now",
    "客户服务暂时不可达。请确认 8002 端口已启动，再检查网络和服务日志。": "The client service is unavailable. Confirm port 8002 is running, then check the network and service logs.",
    "集中查看服务、数据库、API 与业务流程的当前状态。": "Monitor the current state of services, databases, APIs, and business workflows.",
    "客户服务": "Client service",
    "应用与数据库综合状态": "Combined application and database health",
    "近 15 分钟请求": "Requests in the last 15 minutes",
    "不记录请求正文和敏感数据": "Request bodies and sensitive data are not recorded",
    "P95 延迟": "P95 latency",
    "风险阈值 800 ms": "Risk threshold: 800 ms",
    "5xx 错误": "5xx errors",
    "出现即进入严重预警": "Any occurrence triggers a critical alert",
    "故障风险预判": "Failure-risk prediction",
    "阈值判断": "Threshold rules",
    "关键接口": "Key endpoints",
    "近 15 分钟": "Last 15 minutes",
    "按接口查看调用量、错误率和延迟，未调用接口单独标记。": "Review calls, error rates, and latency by endpoint. Unused endpoints are marked separately.",
    "全部接口分组": "All endpoint groups",
    "接口": "Endpoint",
    "调用量": "Calls",
    "错误率": "Error rate",
    "平均延迟": "Average latency",
    "最近状态": "Latest status",
    "在明显报错前发现延迟、错误率和业务积压的上升信号。": "Detect rising latency, errors, and workflow backlog before an obvious outage.",
    "当前预警": "Current alerts",
    "可解释规则": "Explainable rules",
    "预判只使用确定性阈值，不是故障概率。": "Prediction uses deterministic thresholds, not failure probability.",
    "观察有效案件实体、人工复核、申诉阻断和交易风险等流程指标。": "Monitor persisted cases, manual reviews, blocked appeals, and transaction risk.",
    "拒付处理指标": "Chargeback workflow metrics",
    "当前进程": "Current process",
    "尚无业务数据": "No business data",
    "尚无业务数据；客户端产生评估或申诉后会自动出现。": "No business data yet. Metrics appear after the client creates an assessment or appeal.",
    "案件库有效实体": "Persisted case entities",
    "每 5 秒重新读取": "Reloaded every 5 seconds",
    "创建时间": "Created",
    "确认监控采集边界、运行参数和外部连接状态。": "Confirm telemetry boundaries, runtime settings, and external connection status.",
    "监控边界": "Monitoring boundaries",
    "请求遥测": "Request telemetry",
    "仅记录规范化路由、方法、状态码和耗时；不记录请求正文、卡号或原始 URL。": "Only normalized routes, methods, status codes, and latency are recorded. Request bodies, card numbers, and raw URLs are excluded.",
    "滚动窗口": "Rolling window",
    "近 15 分钟进程内统计；服务重启后自动清空，不声明长期历史。": "In-process statistics cover the last 15 minutes and reset after a restart; no long-term history is claimed.",
    "使用可解释阈值识别 5xx、错误率、P95 延迟及业务积压，不输出虚构概率。": "Explainable thresholds identify 5xx errors, error rate, P95 latency, and workflow backlog without invented probabilities.",
    "外部连接": "External connections",
    "Oceanpayment 真实 API、生产数据和上游申诉接口尚未接入；当前为本地合成链路。": "Oceanpayment production APIs, production data, and upstream appeal interfaces are not connected. This is a local synthetic flow.",
    "案件库可重新读取": "Retrievable from case store",
    "当前案件库暂无有效实体；维护端不会生成占位案件。": "No valid entities are in the case store. The operations console does not generate placeholder cases.",
    "暂未发现明显故障前兆": "No material failure indicators detected",
    "数据库正常，且当前请求错误率与延迟未触发阈值。": "The database is healthy and current error rate and latency remain below their thresholds.",
    "继续观察请求量、5xx、P95 延迟和业务阻断趋势。": "Continue monitoring request volume, 5xx errors, P95 latency, and workflow blocks.",
    "服务健康检查": "Service health check",
    "创建拒付案件": "Create chargeback case",
    "读取案件详情": "Read case details",
    "补充案件材料": "Submit case evidence",
    "确认争议原因": "Confirm dispute reason",
    "生成申诉材料包": "Generate representment package",
    "提交申诉": "Submit appeal",
    "交易风险评估": "Transaction risk assessment",
    "敏感信息检查": "Sensitive-data check",
    "飞书事件回调": "Feishu event callback",
    "飞书卡片回调": "Feishu card callback",
    "未登记接口": "Unregistered endpoint",
    "基础服务": "Core services",
    "拒付案件": "Chargeback cases",
    "交易预警": "Transaction alerts",
    "安全控制": "Security controls",
    "外部集成": "External integrations",
    "其他接口": "Other endpoints",
    "基于近 15 分钟请求、数据库健康和业务计数的阈值预警，不是故障概率。": "Threshold alerts use the last 15 minutes of requests, database health, and business counts; they are not failure probabilities.",
    "无卡欺诈（未授权交易）": "Card-not-present fraud (unauthorized transaction)",
}


_RUNTIME = r"""
(function(){
  const TABLE=__TABLE__;
  const TITLES={zh:__TITLE_ZH__,en:__TITLE_EN__};
  const TEXT_SOURCE=new WeakMap();
  const ATTR_SOURCE=new WeakMap();
  const COOKIE=__COOKIE__;
  let language=readLanguage();
  let applying=false;
  function readLanguage(){
    const hit=document.cookie.split(";").map(x=>x.trim()).find(x=>x.startsWith(COOKIE+"="));
    const value=hit?decodeURIComponent(hit.split("=").slice(1).join("=")):localStorage.getItem(COOKIE);
    return value==="en"?"en":"zh";
  }
  function persist(value){
    localStorage.setItem(COOKIE,value);
    document.cookie=COOKIE+"="+encodeURIComponent(value)+";path=/;max-age=31536000;SameSite=Lax";
  }
  function pattern(source){
    let m;
    if((m=source.match(/^(\d+) 件有效实体 · 更新于 (.+)$/)))return `${m[1]} persisted records · Updated ${m[2]}`;
    if((m=source.match(/^(\d+) 件$/)))return `${m[1]} cases`;
    if((m=source.match(/^仍缺 (\d+) 项资料$/)))return `${m[1]} evidence items missing`;
    if((m=source.match(/^仍缺 (\d+) 项$/)))return `${m[1]} missing`;
    if((m=source.match(/^待补交 (\d+) 项$/)))return `${m[1]} items pending`;
    if((m=source.match(/^(.+) · 仍缺 (\d+) 项资料$/)))return `${translate(m[1])} · ${m[2]} evidence items missing`;
    if((m=source.match(/^需要商户补充 (\d+) 项信息$/)))return `${m[1]} items required from the merchant`;
    if((m=source.match(/^案件仍缺 (\d+) 项材料，暂不能完成评估$/)))return `${m[1]} evidence items are still missing; assessment cannot finish`;
    if((m=source.match(/^还剩 (\d+) 天$/)))return `${m[1]} days remaining`;
    if((m=source.match(/^证据 (\d+)\/(\d+)$/)))return `Evidence ${m[1]}/${m[2]}`;
    if((m=source.match(/^版本 (\d+)$/)))return `Revision ${m[1]}`;
    if((m=source.match(/^阶段：(.+)$/)))return `Stage: ${translate(m[1])}`;
    if((m=source.match(/^判定争议原因：(.+)（已确认）$/)))return `Dispute reason: ${translate(m[1])} (confirmed)`;
    if((m=source.match(/^材料就绪度 ([0-9.]+)（规则评估）$/)))return `Evidence readiness ${m[1]} (rule assessment)`;
    if((m=source.match(/^补交：(.+)$/)))return `Submit: ${translate(m[1])}`;
    if((m=source.match(/^下一项优先补交：(.+)$/)))return `Submit next: ${translate(m[1])}`;
    if((m=source.match(/^请求证据：(.+)$/)))return `Requested evidence: ${translate(m[1])}`;
    if((m=source.match(/^负责团队 · (.+)$/)))return `Owner · ${translate(m[1])}`;
    if((m=source.match(/^说明来源 · (.+)$/)))return `Explanation source · ${translate(m[1])}`;
    if((m=source.match(/^辅助 (\d+) · 规则 (\d+)$/)))return `Assisted ${m[1]} · Rules ${m[2]}`;
    if((m=source.match(/^拒付风险 · 评分 (.+)$/)))return `Chargeback risk · Score ${m[1]}`;
    if((m=source.match(/^建议现在留存：(.+)。$/)))return `Retain now: ${m[1].split("、").map(translate).join(", ")}.`;
    if((m=source.match(/^建议：(.+)$/)))return `Recommendation: ${translate(m[1])}`;
    if((m=source.match(/^更新于 (.+)$/)))return `Updated ${m[1]}`;
    if((m=source.match(/^仅生成草稿 · (.+)$/)))return `Draft only · ${translate(m[1])}`;
    if((m=source.match(/^(.+) · 完整度 (.+)$/)))return `${translate(m[1])} · Completeness ${m[2]}`;
    if((m=source.match(/^·\s*(.+)$/)))return `· ${translate(m[1])}`;
    if(source.includes(" · ")){const parts=source.split(" · ");const translated=parts.map(translate);if(translated.some((part,index)=>part!==parts[index]))return translated.join(" · ");}
    return source;
  }
  function translateTo(source,targetLanguage=language){
    source=String(source==null?"":source);
    if(targetLanguage!=="en")return source;
    return TABLE[source]||pattern(source);
  }
  function translate(source){return translateTo(source,language);}
  function preserveWhitespace(source,translated){
    const left=(source.match(/^\s*/)||[""])[0],right=(source.match(/\s*$/)||[""])[0];
    return left+translated+right;
  }
  function translateTextNode(node){
    if(!node.parentElement||node.parentElement.closest("script,style,[data-no-i18n]"))return;
    let source=TEXT_SOURCE.get(node);
    if(source===undefined){source=node.nodeValue;TEXT_SOURCE.set(node,source);}
    const trimmed=source.trim();if(!trimmed)return;
    const next=language==="en"?preserveWhitespace(source,translate(trimmed)):source;
    if(node.nodeValue!==next)node.nodeValue=next;
  }
  function translateElement(element){
    if(element.matches("[data-no-i18n]")||element.closest("[data-no-i18n]"))return;
    let sources=ATTR_SOURCE.get(element);if(!sources){sources={};ATTR_SOURCE.set(element,sources);}
    ["placeholder","title","aria-label"].forEach(name=>{
      if(!element.hasAttribute(name))return;
      if(!(name in sources))sources[name]=element.getAttribute(name);
      element.setAttribute(name,language==="en"?translate(sources[name]):sources[name]);
    });
    if(element.matches("[data-i18n-value]")){
      if(!("value" in sources))sources.value=element.value;
      element.value=language==="en"?translate(sources.value):sources.value;
    }
  }
  function apply(root=document.body){
    if(!root||applying)return;applying=true;
    document.documentElement.lang=language==="en"?"en":"zh-CN";document.title=TITLES[language];
    if(root.nodeType===Node.TEXT_NODE)translateTextNode(root);
    else if(root.nodeType===Node.ELEMENT_NODE){translateElement(root);const walker=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT);let node;while((node=walker.nextNode()))node.nodeType===Node.TEXT_NODE?translateTextNode(node):translateElement(node);}
    const selector=document.getElementById("languageSelect");if(selector)selector.value=language;
    applying=false;
  }
  function setLanguage(value,save=true){
    const next=value==="en"?"en":"zh";if(next===language){apply();return;}
    const previousLanguage=language;language=next;if(save)persist(language);apply();window.dispatchEvent(new CustomEvent("oceanpilot:languagechange",{detail:{language,previousLanguage}}));
  }
  function init(){
    const selector=document.getElementById("languageSelect");if(selector)selector.addEventListener("change",event=>setLanguage(event.target.value));
    apply();
    const observer=new MutationObserver(records=>{for(const record of records){for(const node of record.addedNodes)apply(node);}});observer.observe(document.body,{childList:true,subtree:true});
    setInterval(()=>{const cookieLanguage=readLanguage();if(cookieLanguage!==language)setLanguage(cookieLanguage,false);},1000);
  }
  window.oceanI18n={apply,getLanguage:()=>language,setLanguage,translate,translateTo};
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();
"""


def build_i18n_script(
    translations: dict[str, str],
    *,
    title_zh: str,
    title_en: str,
    preference_key: str,
) -> str:
    """Return the self-contained browser runtime with a safely encoded dictionary."""

    return (
        _RUNTIME.replace(
            "__TABLE__", json.dumps(translations, ensure_ascii=False, separators=(",", ":"))
        )
        .replace("__TITLE_ZH__", json.dumps(title_zh, ensure_ascii=False))
        .replace("__TITLE_EN__", json.dumps(title_en, ensure_ascii=False))
        .replace("__COOKIE__", json.dumps(preference_key))
    )


CLIENT_I18N_SCRIPT = build_i18n_script(
    CLIENT_TRANSLATIONS,
    title_zh="Oceanpayment · 商户工作台",
    title_en="Oceanpayment · Merchant Workspace",
    preference_key="oceanpilot_client_language",
)

ADMIN_I18N_SCRIPT = build_i18n_script(
    ADMIN_TRANSLATIONS,
    title_zh="Oceanpayment · 维护中心",
    title_en="Oceanpayment · Operations Center",
    preference_key="oceanpilot_admin_language",
)
