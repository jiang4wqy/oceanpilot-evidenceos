# OceanPilot 全能 AI 运营中枢与支付异常主线设计

日期：2026-08-15

状态：已批准直接实施

视觉方向：C · Ivory Ledger

## 1. 目标

OceanPilot 在比赛 Demo 中呈现为“跨境商户成功全能 AI 助手”，但只把一个能力做深：支付异常识别与争议协作。首屏负责建立产品全貌，深层页面必须用现有 API、持久化状态、确定性规则、人审和审计证明能力，不以静态 KPI 或概念文案冒充实现。

成功标准：

1. 评委在 20 秒内看懂 OceanPilot 的能力版图、实现状态和本次主演示入口。
2. “支付异常”是唯一 Live 焦点，其他未实现能力明确标注“已设计”或“规划接入”。
3. 主流程符合支付与拒付业务逻辑：只有已捕获/已结算交易收到 Issuer 正式争议通知或人工确认的正式拒付通知后，才允许创建拒付案件。
4. 复用当前持久化案件闭环，不重写补证、评估、打包、人审、mock 提交或案件审计。
5. 建立可浏览的独立规则数据库原型，并能从打包结果追溯规则版本和来源。
6. 所有业务数据和动作明确为 Synthetic Demo；不得声称真实 Oceanpayment 接入、真实胜诉率或真实卡组织提交。

## 2. 已选方案与替代方案

采用“事件驱动单案主线”：

`AI 中枢 → 支付异常 → 已结算交易的正式争议通知 → Visa 10.4 → 持久化案件 → 通用补证 → 卡组织规则校验与打包 → 人工批准 → mock 提交 → 案件处理审计 + 本次 mock 回执`

不采用以下方案：

- 3DS 失败直接升级拒付：交易未授权、未捕获、未结算，通常不存在可拒付原交易，业务逻辑错误。
- 案件中心直达：改动最少，但无法解释案件来源和全能 AI 助手定位。
- 双控制台全景巡游：覆盖面广，但 3–5 分钟内会稀释主线；运维控制台只作为收尾或评委追问入口。

保留一个对照分支：3DS/回调异常进入现有 `PAYMENT_INCIDENT` 诊断与技术支持复核，不创建拒付案件。该分支用于证明 OceanPilot 会正确分流，不进入主演示的完整补证流程。

## 3. 复用原则

### 3.1 直接复用

- HEAD 的 Oceanpayment 品牌外壳、侧栏、顶栏和响应式基础。
- HEAD 的持久化案件中心、独立新建案件、逐项补证和重新读取。
- HEAD 的证据就绪度、规则打包、人工闸门、mock connector、案件审计和 Agent 判断依据。
- HEAD 的交易预警 `/prevention/assess` 与敏感信息阻断 `/safety/scan`。
- `fe520eb` 的完整导航层级、高密度交易表、Processing Path 和诊断三段式结构。
- `6de1898` 的任务式引导、从交易进入案件以及来源交易上下文。
- 现有 `KnowledgeBase → BankRuleEntry → PackagerAgent` 规则注入缝隙。

### 3.2 只复用容器，不复用内容

- 旧概览指标条、趋势图、关注列表和相似交易区域。
- 旧交易列表的表格结构。
- 旧诊断页的卡片、路径和三段式布局。

这些区域原来的授权率、交易量、增长率、固定告警、置信度、时间线和日志均为前端硬编码，不恢复。

### 3.3 明确不做

- 不回滚任何历史提交或整体替换 `demo.py`。
- 不接入 RAG、向量库、PDF/OCR 自动导入或规则管理后台。
- 不增加真实退款、重新扣款、风控放行、工单或卡组织提交。
- 不把 Evidence Readiness 命名为胜诉率。
- 不宣称规则数据库驱动了整个补证链。

## 4. 信息架构

商户端导航恢复为完整但诚实的产品结构：

1. **AI 运营中枢**：能力地图、实现状态、Synthetic Demo 边界、唯一 Live 支付异常。
2. **支付异常**：合成异常交易队列、交易处理路径、事实/解释/建议动作。
3. **异常与争议**：复用当前案件中心、新建案件、案件诊断和案件详情。
4. **交易风险**：复用现有交易前风险提示。
5. **规则知识**：新增 9 条规则摘要的搜索、筛选和详情。
6. **审计与运维**：复用当前案件审计、安全检查，并提供 8003 运维控制台入口；不伪装成全局审计数据库。

其他能力以能力卡展示，不创建空白可点击页面：商户成功、增长洞察、客户支持、自动化编排和企业集成均标注“已设计/规划接入”。

## 5. 视觉系统

采用 Ivory Ledger：暖象牙白主画布、深石墨侧栏、帝王蓝 AI 主色、朱红异常色。

核心令牌：

```css
--canvas: #F5F2EB;
--surface: #FEFCF8;
--sidebar: #171A23;
--text: #1A2030;
--text-muted: #697180;
--border: #D8D4CA;
--ai: #5266EB;
--ai-soft: #E8EAFB;
--critical: #C94E4A;
--critical-soft: #F8E5E2;
--success: #2D7E63;
--warning: #9A6A23;
--rule: #8A6A2F;
```

约束：

- 中性色承担至少 85% 面积。
- 帝王蓝只用于 AI Core、当前导航、主按钮和推理路径。
- 支付异常固定使用朱红，不与品牌色混用。
- 规则来源使用低饱和金棕，成功与警告使用独立语义色。
- 不使用大面积霓虹、蓝绿渐变或装饰性玻璃拟态。
- 正文至少 12 px，主要交互具有键盘焦点和非颜色状态说明。

## 6. 主流程与页面状态

### 6.1 AI 运营中枢

首屏展示 OceanPilot AI Core 和六个能力域。支付异常节点显示 `LIVE DEMO · 1 synthetic`，其余节点展示 `已实现`、`已设计` 或 `规划接入`。首屏不展示无来源授权率、失败率、交易量或业务提升百分比。点击支付异常后进入异常队列，并自动聚焦主场景：一笔已捕获、已结算的 Visa CNP 合成交易收到 Issuer 正式“非本人交易”争议通知。

### 6.2 支付异常与正确分流

主演示交易的处理路径：

`Checkout ✓ → Risk ✓ → 3DS — 未启用/无认证记录 → Authorization ✓ → Capture ✓ → Settlement ✓ → Issuer Dispute Notice !`

诊断三段式：

- Observed Facts：已结算、Visa CNP、收到 Issuer 正式争议通知、当前只有交易收据，无 3DS 认证记录。
- System Interpretation：支付链路成功；异常是事后欺诈争议，候选 Visa 10.4。
- Recommended Action：由人工创建争议案件，按内部准备清单收集认证、AVS/CVV、设备/IP 和历史交易；不自动退款或提交。

只有 `CAPTURED/SETTLED` 且存在 `ISSUER_DISPUTE_NOTICE` 或经人工确认的正式拒付通知时显示“升级为争议案件”。普通 `CUSTOMER_COMPLAINT` 只能进入预争议分流，不能直接锁定 Visa 10.4 或生成卡组织申诉包。

3DS 对照场景调用现有 Foundation `PAYMENT_INCIDENT` 链：创建 Incident、写入结构化证据、执行确定性诊断、路由技术支持/人工复核。该场景明确显示“不可创建拒付案”。

### 6.3 交易到案件的桥

点击“升级为争议案件”打开现有新建案件页，并：

- 预选 Visa 10.4 Synthetic 场景。
- 将 Payment ID、订单、金额、结算状态和投诉事实填入可编辑描述。
- 显示“本次会话来源交易”提示。
- 仍由用户点击“确认创建案件”，绝不自动建案。

当前 Chargeback Store 不持久化原始描述或来源交易。V1 保持会话级关联并明确标注，不扩展案件数据库；刷新后案件仍可读取，但来源交易快捷返回可能消失。持久化关联是后续独立数据模型任务。

### 6.4 争议闭环

案件创建后完全复用当前状态机：

`OPEN → NEED_EVIDENCE → ASSESSED → Package Preview → Human Gate → Mock Submitted`

- 主场景描述明确，当前启发式会高置信识别并自动确认 `FRAUD_CARD_NOT_PRESENT`，主线直接进入 `NEED_EVIDENCE`。只有低置信输入才进入 `REASON_PROPOSED → 人工确认/更正` 分支。
- 起始材料仅包含交易收据，页面显示仍缺 5 项。
- 逐项补证后重新读取后端状态。
- Fraud 属于高风险类别，即使证据就绪度达到 100%，仍保留人工复核。
- 未批准的 mock appeal 必须显示阻断原因；批准需填写 actor ID。

页面必须明确区分两套口径：

- **内部案件准备清单**：当前领域策略的 6 项，用于逐项补证和 Evidence Readiness；AVS/CVV 是内部准备项，不宣称为 Visa 官方必需证据。
- **卡组织打包摘要**：Rules DB 中 Visa 10.4 的 4 项 Demo 摘要，用于 package 校验和来源追溯。

两者名称、数量和用途必须同时显示，不能合并成一份“Visa 官方必需材料”。

Package、批准和 mock receipt 当前不是 Chargeback SQLite 审计事件。UI 必须称为“案件处理审计 + 本次 mock 回执”，不得称为完整提交审计。

## 7. 专有规则数据库原型

### 7.1 边界

新增独立 `oceanpilot-rules.db`，不向 Foundation 或 Chargeback 现有数据库加表。Foundation 启动会严格校验表集合，独立库可避免破坏现有初始化约束。

V1 真实逻辑是：

`通用 reason 补证 → package 时输入 card_network → 规则库匹配 → Packager 校验/排序/打包 → 规则详情追溯`

逐项补证仍由 `domain.chargeback._POLICIES` 驱动；规则库只在打包阶段参与。页面必须使用“卡组织规则校验与打包”，不能使用“规则库驱动全流程”。

### 7.2 三表模型

`rule_documents`

- `document_id`
- `scheme`
- `title`
- `publisher`
- `source_url`
- `source_version`

`rule_versions`

- `rule_version_id`
- `document_id`
- `scheme_reason_code`
- `display_name`
- `category`
- `region`
- `version_label`
- `source_section`
- `effective_date`
- `internal_reason_code`
- `demo_role`
- `internal_window_days`
- `verification_status`
- `limitation`

`rule_requirements`

- `requirement_id`
- `rule_version_id`
- `requirement_type`：`ASSERTION` 或 `EVIDENCE`
- `necessity`：`REQUIRED` 或 `RECOMMENDED`
- `sequence`
- `description_zh`
- `internal_evidence_code`

所有外键启用，种子使用稳定 ID，初始化幂等，`PRAGMA user_version=1`。`(rule_version_id, requirement_type, sequence)` 唯一，防止要求排序不确定。

### 7.3 首批种子

共 9 条规则摘要、3 个可驱动 Demo 映射、3 家卡组织、3 份来源文档：

- Demo Mapped：Visa 10.4、Visa 13.1、Mastercard 4853。
- Display Only：Visa 12.6、13.2、13.3、13.6、Amex C04、C05。

九条种子全部标记 `UNVERIFIED_SUMMARY`。未经直接核验的 `effective_date` 和官方响应期限保持 `NULL`；`internal_window_days` 只表示 Demo 内部准备窗口。

外部 Markdown 仅作为人工整理输入，不成为运行时依赖。ACME 银行测试规则、示例案例、VAMP/ECP 和 ODPM 跨渠道映射不进入评委目录。

统一免责声明：

> 演示规则摘要；生产使用前须按卡组织、地区、版本和生效日期，以正式 Standards、后台公告及收单机构有效版本复核。

### 7.4 API

- `GET /api/v1/chargeback/rules?scheme=&q=`：返回规则摘要、统计和免责声明。
- `GET /api/v1/chargeback/rules/{rule_version_id}`：返回来源、版本、断言、证据、内部映射和限制。
- Package 响应增加 `rule_version_id`、`verification_status` 和 `submission_window_basis=INTERNAL_DEMO`。

无新增 POST、PUT、DELETE，无管理后台。

新增两个边界：Repository 实现现有 `KnowledgeBase.lookup()`；只读 `RuleCatalog` port 提供 `list/get`。`BankRuleEntry → RepresentmentPackage → ChargebackPackageResponse` 逐层透传可选的 `rule_version_id`、`verification_status` 和 `submission_window_basis`。

数据库映射规则：

- `lookup()` 只选择 `DEMO_MAPPED`；`DISPLAY_ONLY` 永不驱动 Package。
- 只有 `EVIDENCE + REQUIRED + internal_evidence_code 非空` 构成 `required_evidence/template_order`。
- `RECOMMENDED` 不阻断就绪；`ASSERTION` 映射到 `required_assertions`。
- V1 由 Repository 严格解码 DB 行并直接组装 `BankRuleEntry`。现有 ingestion loader 丢弃 provenance 字段，不用于加载这 9 条富规则。

查找优先级：`现有银行专属 override → Rules DB 的 DEMO_MAPPED 卡组织规则 → 现有 InMemory network/default`。只有最终实际来源是 `default` 时，UI 才显示“内部默认模板”。成功查询但无匹配才允许 InMemory 回退；SQLite 异常映射为 `DatabaseUnavailable / 503`，不得静默伪装成未命中。

配置新增 `Settings.rules_db_path: Path | None = None` 和 `OCEANPILOT_RULES_DB_PATH`，默认使用主数据库同目录的 `oceanpilot-rules.db`。独立建表与种子仅在 FastAPI lifespan 内执行，`create_app()` 与模块 import 不创建数据库文件；复用 SQLite 连接和事务配置，但不修改 Foundation `REQUIRED_TABLES`。

## 8. 错误与空状态

- AI 中枢和合成交易 fixture 永远显示 `Synthetic Demo`。
- Payment Incident API 失败时保留已知事实，显示“诊断暂不可用”，不伪造结论。
- 不符合升级条件的交易禁用建案按钮并解释原因。
- 案件列表、规则列表或详情读取失败时显示可重试错误，不回退假数据。
- 规则未命中且最终实际来源为 `default` 时显示内部默认模板与复核提示；数据库不可用显示服务错误，不降级为“未命中”。
- 规则详情不存在返回安全 404，不回显数据库内部信息。
- mock 提交未批准、材料未齐或连接器失败时保留当前案件状态，并显示明确阻断原因。

## 9. 3–5 分钟评委脚本

1. `0:00–0:25`：AI 中枢与能力状态；点击唯一 Live 支付异常。
2. `0:25–1:10`：查看已结算交易路径、事实/解释/建议动作；说明 3DS 失败不会进入拒付。
3. `1:10–1:35`：人工确认升级，创建 Visa 10.4 合成案件。
4. `1:35–2:35`：展示内部清单 1 项已有、5 项缺失；逐项补一项后，演示快捷方式继续逐项调用现有 `/evidence` API，并以每次后端返回状态补齐剩余项，绝不在前端直接修改就绪度。
5. `2:35–3:20`：查看证据就绪度、高风险人工复核和规则详情来源。
6. `3:20–4:05`：生成材料包；先展示未批准阻断，再人工批准进入 mock connector。
7. `4:05–4:35`：查看案件审计与本次 mock 回执，返回 AI 中枢。

## 10. 验证与测试

### 后端

- 规则三表 schema、外键、`user_version`、9/3 种子数量与幂等初始化。
- Repository 精确匹配、要求顺序、未知规则和 InMemory 回退。
- Rules list/detail API、筛选、搜索和安全 404。
- Package 的 `rule_version_id` 可反查详情。
- 更新 `test_lifespan_openapi.py` 的冻结路径集合。
- Rules DB 在 lifespan 前不存在，进入 lifespan 后才创建。
- SQLite 故障返回 503，且不触发 InMemory 未命中回退。
- 现有 InMemory、Packager、案件状态机和持久化测试继续通过。

### 前端

- Demo HTML 包含完整导航、能力状态、Synthetic Demo、支付异常路径和规则免责声明。
- 3DS 场景无“升级争议”动作；已结算争议场景有人工建案动作。
- Visa 10.4 描述能进入现有缺证流程。
- 规则列表可打开详情，Package 可跳转相同 rule version。
- 案件中心仍只展示后端可读取的持久化案件。
- 键盘搜索、焦点、窄屏 1024/768 和 `prefers-reduced-motion` 可用。

### 完整门禁

```text
pytest
ruff check src tests
ruff format --check src tests
compileall src tests
git diff --check
/health、/demo、/admin、rules list/detail HTTP smoke
浏览器主流程与控制台错误检查
```

## 11. 实施顺序

1. 独立规则库 schema、repository、种子、配置和测试。
2. Rules API 与 Package 追溯字段。
3. 恢复完整导航和 Ivory Ledger 令牌。
4. AI 中枢、支付异常页和正确分流。
5. 将 Visa 10.4 来源上下文接入现有新建案件页。
6. 规则知识页与 Package 跳转。
7. 文档、测试、浏览器 QA 和服务启动。
