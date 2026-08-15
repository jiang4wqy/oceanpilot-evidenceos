# OceanPilot AI 总窗口与规则库设计

日期：2026-08-15

状态：用户已批准方案 A，可直接实施

前端基线：当前仓库的 GitHub 前端基线 `26e1fa8`

## 1. 已批准决策

本轮前端只做一个大型新增：在 `/demo` 增加“全能 AI 总窗口”。

支付异常是总窗口中唯一重点入口。点击后直接执行 `showView("overview")`，进入 GitHub 基线已有的案件中心。案件中心、新建案件、案件诊断、案件详情和交易风险页面保留原有结构、配色、排版和交互；同时增加一个使用相同视觉体系的规则知识页，用于承接诊断与 Package 的精准条款引用。

主路径：

`AI 总窗口 → 支付异常卡 → 原版案件中心 → 原版新建/补证/评估/打包/人审/mock 流程`

## 2. 目标与成功标准

1. 评委在 20 秒内看懂 OceanPilot 是全能 AI 助手，并能找到唯一的支付异常 Demo 入口。
2. 新总窗口融入 GitHub 基线视觉，不进行全站换肤。
3. 点击支付异常直接进入现有 `overview`，不经过额外事件队列。
4. `overview/create/diagnosis/flow/prev` 的页面主体不因本轮发生结构性变化。
5. 独立规则数据库、Rules API 和 Package provenance 保留，并提供可搜索、可定位、可返回案件上下文的客户端规则知识页。
6. 所有数据与动作保持 Synthetic/Mock 边界，不声称真实 Oceanpayment、真实胜诉率或真实卡组织提交。

## 3. 前端范围

### 3.1 主要新增页面

新增 `v-hub`，并将其作为 `/demo` 首屏。侧栏只增加“AI 运营中枢”入口，原有“案件中心 / 新建案件 / 交易风险”继续存在。

总窗口包括：

- 产品定位与 Synthetic Demo 提示。
- OceanPilot AI Core 状态。
- 六个能力域的静态能力卡。
- 支付异常卡作为唯一 Live 可点击节点。
- 规则数据库状态卡，显示“9 条摘要 / 3 条 Demo Mapped / Backend Ready”，并可进入规则知识页。
- 确定性规则、人审、mock connector、审计等底层能力状态。

总窗口不展示没有来源的交易量、授权率、失败率、胜诉率或增长百分比。

### 3.2 支付异常入口

支付异常卡只调用：

`showView("overview")`

它不创建案件、不预选模板、不修改案件状态，也不进入 `incidents` 中间页。评委进入案件中心后，继续使用基线已有的新建案件与闭环。

### 3.3 规则知识页与精准引用

新增 `v-rules`，读取真实 Rules list/detail API，不在 HTML 内复制规则数据。页面支持卡组织筛选、文本搜索、规则列表和详情。

诊断或 Package 只能使用后端实际返回的 `rule_version_id` 形成引用，不能仅按 reason code 猜测规则。统一导航调用：

`showRuleReference(ruleVersionId, returnContext)`

该函数必须：

- 清除或协调会遮蔽目标规则的筛选条件。
- 进入 `v-rules`。
- 打开同一 `rule_version_id` 的详情。
- 将键盘焦点移到规则详情并显示短暂高亮。
- 保存来源案件、来源页面和卡组织，提供“返回案件诊断/案件详情”。

诊断页通过当前明确选择的卡组织调用只读 `GET /cases/{case_id}/rule-reference` 解析具体条款；该端点不生成材料包，也不写案件状态。若卡组织未选择、规则未映射或响应没有 `rule_version_id`，显示“未解析到具体条款”，不得制造链接。Package 输出直接复用其响应中的 `rule_version_id`。

### 3.4 明确不新增

本轮 `/demo` 不包含：

- `v-incidents` 或 `data-v="incidents"`。
- 合成事件队列、Processing Path、三段式事件诊断。
- 3DS Foundation 的前端执行页。
- Ivory Ledger 全局令牌覆盖。

这些内容需要后续单独讨论，不在方案 A 中暗中保留。

## 4. 视觉与交互

总窗口和规则知识页复用基线已有的 CSS 令牌、明暗主题、侧栏、顶栏、`panel`、`page-head`、按钮和响应式体系。新增样式只作用于 `v-hub` 能力网格、规则列表/详情和引用高亮，不重定义 `:root` 全局颜色。

要求：

- 总窗口保持原版深色侧栏、蓝色强调和卡片密度。
- 支付异常除颜色外必须有“LIVE / 当前演示”文字，不依赖颜色单独表达。
- 其他能力卡明确标注“已实现 / Backend Ready / 规划接入”，无内容的卡不可伪装成可操作页面。
- 支付异常入口使用原生按钮，支持键盘、焦点状态和可访问名称。
- 375、768、1024 和 1440 px 无水平溢出；遵守 `prefers-reduced-motion`。

## 5. 原版案件闭环

以下 GitHub 基线能力继续原样承担详细演示：

- 持久化案件中心。
- 独立新建案件与 Visa 10.4 Synthetic 模板。
- 原因识别与人工确认。
- 逐项补证与重新读取。
- Evidence Readiness（非胜诉概率）。
- 卡组织规则校验与材料包。
- 诊断/评估中的条款引用与 Package 引用均可返回同一 Rules DB 详情。
- 人工闸门与 in-process mock connector。
- 案件处理审计与本次会话 mock 回执。
- 交易风险与敏感信息检查。

本轮不把正式 Issuer 通知或结算状态门禁包装成整个系统已经具备的生产约束。直连建案 API 与 Chargeback 飞书 seam 仍是 synthetic 协作接口，尚未校验交易状态和通知来源。

## 6. 独立规则数据库

规则能力继续使用独立 `oceanpilot-rules.db`，不修改 Foundation 或 Chargeback 现有数据库表集合。

三表：

- `rule_documents`：来源文档。
- `rule_versions`：规则版本、原因码、范围、内部映射、核验状态和限制。
- `rule_requirements`：断言或证据要求、必要性、顺序和内部 evidence code。

数据库要求：

- `PRAGMA user_version=1`。
- 外键开启，稳定 ID，初始化幂等并清理非种子遗留行。
- 9 条 `UNVERIFIED_SUMMARY`，其中 3 条 `DEMO_MAPPED`。
- Demo Mapped：Visa 10.4、Visa 13.1、Mastercard 4853。
- Display Only：Visa 12.6、13.2、13.3、13.6、Amex C04、C05。
- 未核验的生效日期和官方期限保持空值；15 天只代表内部 Demo 准备窗口。

规则查找优先级：

`银行 override → Rules DB 的 DEMO_MAPPED 网络规则 → InMemory network/default`

数据库损坏或缺表返回 503，不伪装成 404 或普通未命中。`card_network` 和 `bank_id` 在匹配前统一规范化。

## 7. Rules API 与 Package provenance

保留：

- `GET /api/v1/chargeback/rules?scheme=&q=`。
- `GET /api/v1/chargeback/rules/{rule_version_id}`。
- `GET /api/v1/chargeback/cases/{case_id}/rule-reference?card_network=`。
- Package 响应的 `rule_version_id`、`verification_status`、`submission_window_basis`。

这些后端能力同时驱动 `/demo` 的规则知识页。列表和详情始终来自 API；点击诊断或 Package 引用时，以同一 `rule_version_id` 精确定位，不能依赖前端静态映射。`/docs` 和直接 API 仍可作为技术核验入口。

`win_likelihood` 仅作为弃用兼容字段存在，OpenAPI 必须说明它等同 Evidence Readiness、不是胜诉预测。申诉响应必须固定声明 `synthetic=true` 与 `connector_kind="IN_PROCESS_MOCK"`。

## 8. 错误与事实边界

- 总窗口固定显示 Synthetic Demo。
- 支付异常卡只导航，不自动建案或执行资金动作。
- 案件列表错误继续使用原版安全空态。
- 规则 API 404/503 不在前端伪造数据。
- 引用解析失败时保留案件事实并显示“未解析到具体条款”，不跳转到相似规则。
- 所有规则均为演示摘要，生产使用须按卡组织、地区、版本、生效日期和收单机构有效版本复核。
- 人工批准只调用进程内 mock connector，不代表真实上游提交。

## 9. 评委演示脚本

1. `0:00–0:30`：展示 AI 总窗口、能力版图和 Synthetic 边界。
2. `0:30–0:45`：点击唯一 Live“支付异常”，直接进入原版案件中心。
3. `0:45–1:30`：从原版新建案件选择 Visa 10.4 Synthetic 模板并创建。
4. `1:30–2:40`：展示缺失材料、逐项补证与 Evidence Readiness。
5. `2:40–3:30`：在诊断/评估中打开精准条款引用，返回案件后生成材料包，再从 Package 引用定位到同一规则。
6. `3:30–4:15`：先展示未批准阻断，再进行人工批准与 mock 回执。
7. `4:15–4:40`：查看案件审计；如评委追问，继续搜索少量 Visa/Mastercard/Amex 摘要或通过 `/docs` 核验 API。

## 10. 验收

### 前端

- 存在 `id="v-hub"` 和“AI 运营中枢”。
- 支付异常按钮直接包含 `showView('overview')`。
- 不存在 `v-incidents`；存在使用基线视觉的 `v-rules` 与规则导航。
- 诊断与 Package 引用使用响应中的同一 `rule_version_id`，可聚焦详情并返回案件上下文。
- 基线 `overview/create/diagnosis/flow/prev` 均保留。
- 基线全局 CSS 令牌不被 Ivory Ledger 覆盖。
- 嵌入 JavaScript 语法正确，浏览器控制台无错误。

### 后端

- 规则三表、9/3 种子、幂等和污染清理通过。
- list/detail、筛选、搜索、安全 404 和数据库 503 通过。
- Package provenance 可反查规则。
- mock 响应和 legacy readiness 的 OpenAPI 边界通过。

### 完整门禁

- `pytest`。
- `ruff check src tests`。
- `ruff format --check src tests`。
- `compileall src tests`。
- `git diff --check`。
- HTTP smoke：`/health`、`/demo`、`/admin`、Rules list/detail。
- 浏览器检查 375/768/1024/1440、键盘入口和主闭环。

## 11. 明确延期

以下内容等待后续讨论：

- 支付异常事件队列与交易级 Processing Path。
- 3DS 对照场景的前端诊断。
- 原始交易到案件的持久化关联。
- 全局视觉换肤或新的配色系统。
