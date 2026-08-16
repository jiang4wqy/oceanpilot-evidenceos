# OceanPilot AI 运营中枢 — 双端 Dashboard 设计

> **历史探索稿。** 本文中的 Ivory Ledger、事件队列与 Processing Path 未进入当前实现。
> 当前实现边界以 `docs/superpowers/specs/2026-08-15-oceanpilot-ai-operations-design.md`
> 为准：GitHub 原版案件工作台 + AI 总窗口 + 基线风格规则知识页。

## 1. 产品定位与选择

OceanPilot 在比赛 Demo 中呈现为“跨境商户成功全能 AI 助手”，但不把未实现能力包装成可运行产品。首屏展示完整能力版图，唯一可完整演示的深度节点是支付异常；进入后以高密度、证据导向的运营工作台完成一条正式争议主线。

```text
AI 运营中枢
  → 支付异常
  → 已结算交易收到 Issuer 正式争议通知
  → 持久化拒付案件
  → 通用补证与 Evidence Readiness
  → 卡组织规则校验与打包
  → 人工批准
  → mock connector
  → 案件处理审计 + 本次 mock 回执
```

视觉方向采用 **C · Ivory Ledger**：暖象牙白画布、深石墨侧栏、帝王蓝 AI 主色与朱红异常色。它保留支付运营所需的信息密度，同时让 AI 中枢、异常状态和规则来源具有清晰而克制的层级。

## 2. 信息架构

### 商户客户端（端口 8002）

- **AI 运营中枢**：能力地图、实现状态、Synthetic Demo 边界和唯一 Live Demo 入口。
- **支付异常**：合成异常队列、处理路径、Observed Facts、System Interpretation 与 Recommended Action。
- **异常与争议**：持久化案件中心、新建案件、原因识别、逐项补证、Evidence Readiness、打包、人审和 mock 提交。
- **交易风险**：复用现有交易前风险提示与应留存证据。
- **规则知识**：9 条 `UNVERIFIED_SUMMARY` 的搜索、筛选、详情和来源追溯。
- **审计与运维**：案件处理审计、安全检查和 8003 运维控制台入口；不伪装成全局审计数据库。

商户成功、增长洞察、客户支持、自动化编排和企业集成只在能力地图中标注“已设计”或“规划接入”，不创建内容空白却可点击的页面。

### 运行维护端（端口 8003）

- 运行总览：服务、数据库、请求量、P95、5xx 和关键预警。
- API 监控：规范化路由、调用量、4xx/5xx、错误率、平均延迟、P95 和最近状态。
- 故障预判：以确定性阈值解释风险信号和处置建议。
- 业务指标：人工复核、申诉阻断、风险分级等流程压力。
- 审计与配置：采集边界、窗口语义与外部连接事实边界。

8003 是主演示后的收尾或评委追问入口，不在 3–5 分钟业务主线中来回切换。

## 3. 主要旅程

### 20 秒全貌建立

1. 首屏用 OceanPilot AI Core 和六个能力域解释产品全貌。
2. 支付异常显示 `LIVE DEMO · 1 synthetic`；其它节点明确展示实现状态。
3. 页面不展示无来源授权率、失败率、交易量、增长率或业务提升百分比。

### 已结算 Visa 10.4 正式争议

1. 打开已捕获、已结算的 Visa CNP synthetic fixture。
2. 处理路径显示：
   `Checkout ✓ → Risk ✓ → 3DS 未启用/无认证记录 → Authorization ✓ → Capture ✓ → Settlement ✓ → Issuer Dispute Notice !`。
3. 诊断三段式先分开陈述事实、解释与动作，不把推断写成观察事实。
4. 只有存在 Issuer 正式争议通知或经人工确认的正式拒付通知，才显示“升级为争议案件”。
5. 用户确认后带入来源交易上下文，但仍需再次点击“确认创建案件”；系统不自动建案。

普通客户投诉只进入预争议分流，不能直接锁定 Visa 10.4 或生成卡组织申诉包。

### 3DS / 回调异常支持分支

3DS challenge 失败发生在授权之前，通常没有已捕获、已结算的原交易，因此不能直接创建拒付案件。该场景进入现有 Foundation `PAYMENT_INCIDENT` 链：创建 Incident、写入结构化证据、执行确定性诊断，再路由技术支持或人工复核。授权超时或状态未知时，应先核对上游最终状态，避免重复扣款。

### 争议补证与打包

1. Visa 10.4 主场景以交易收据起步，内部准备清单显示仍缺 5 项并突出下一项。
2. 每次补证都调用现有 `/evidence` API 并使用后端返回状态；演示快捷方式也不能直接修改前端就绪度。
3. 只有材料收集完成或人工声明无法继续补证后，才进入确定性评估。
4. Evidence Readiness 只表示内部清单准备程度，不是胜诉概率。
5. 规则库在通用补证之后参与 package 校验、排序与来源追溯，不驱动前面的逐项补证。
6. 页面分开显示 6 项“内部案件准备清单”和 4 项“卡组织打包摘要”；AVS/CVV 不称为 Visa 官方必需证据。
7. 未批准或 package 未就绪时必须阻断；只有显式人工批准才能进入 in-process mock connector。
8. 结束页称为“案件处理审计 + 本次 mock 回执”。Package、批准和 mock receipt 不冒充 Chargeback SQLite 审计事件。

## 4. 设计 Token

这些色值是比赛原型的界面方向，不声明为 Oceanpayment 官方品牌规范。

```css
--canvas: #F5F2EB;
--surface: #FEFCF8;
--sidebar: #171A23;
--text: #1A2030;
--text-muted: #697180;
--border: #D8D4CA;
--ai: #4052C8;
--ai-soft: #E8EAFB;
--critical: #A93634;
--critical-soft: #F8E5E2;
--success: #22664C;
--warning: #795013;
--rule: #6D4E1B;
```

- 中性色承担至少 85% 面积；不使用大面积霓虹、蓝绿渐变或玻璃拟态。
- 帝王蓝只用于 AI Core、当前导航、主按钮和推理路径。
- 支付异常固定使用朱红；规则来源使用低饱和金棕。
- 正文至少 12 px；ID、响应码和时间使用等宽字体。
- 主要交互必须有键盘焦点和非颜色状态说明，并尊重 `prefers-reduced-motion`。
- 桌面 1440 优先，同时保证 1280、1024 和 768 窄屏可用。

## 5. 组件与内容规则

- **Capability Map**：同时表达能力范围和 `已实现 / 已设计 / 规划接入` 状态。
- **Synthetic Boundary**：AI 中枢和所有交易 fixture 始终显示 Synthetic Demo。
- **Global Search**：顶栏视觉重点，支持 `⌘K` 聚焦和回车定位。
- **Dense Table**：异常、案件和规则用高密度表格，不拆成重复大卡片。
- **Processing Path**：区分已通过、失败、未执行和事后争议通知。
- **Diagnostic Triad**：必须分开 Observed Facts、System Interpretation 和 Recommended Action。
- **Formal Dispute Gate**：不满足已结算与正式争议条件时禁用建案，并解释原因。
- **Missing Evidence Alert**：写清数量、缺什么、下一项和数据口径。
- **Rule Provenance**：规则详情显示 scheme、region、version、effective date、来源和 `UNVERIFIED_SUMMARY`；未知日期保持空值，不编造。
- **Confirmation Gate**：建案和 mock 提交均保留显式人工动作。
- **Audit vs Receipt**：案件处理审计与本次 mock 回执使用不同标题和容器。

## 6. 当前事实边界

- 交易队列和诊断均为 synthetic fixture；案件列表与补证状态来自真实本地 API 和 SQLite。
- 独立规则库是 9 条演示摘要的原型，只有 3 条 `DEMO_MAPPED` 记录可驱动 package；生产使用前必须按卡组织、地区、版本和生效日期复核。
- 通用补证由 `domain.chargeback` 领域策略驱动，规则库只参与打包阶段。
- 没有真实 Oceanpayment 数据/API、真实历史案件、生产卡组织规则或上游申诉连接。
- 系统不执行真实支付、退款、重新扣款、风控放行、配置变更或申诉提交。
- Evidence Readiness 不代表真实胜诉率；离线评测也不证明真实业务准确率或提升。
- 维护端请求监控是近 15 分钟进程内滚动窗口，不是生产可观测性平台。
- “故障预判”只使用可解释阈值，不输出模型生成的故障概率。
