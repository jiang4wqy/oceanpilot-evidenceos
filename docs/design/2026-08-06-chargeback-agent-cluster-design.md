# OceanPilot — 跨境拒付协作 Agent 集群设计

- 状态：`v0.2.1` synthetic 原型已实现；本文同时保留目标设计与当前实现边界
- 日期：2026-08-06
- 定位：以 **跨境拒付（chargeback / dispute）申诉** 为唯一产品主线；EvidenceOS Foundation 是可信底座，支付异常仅作为扩展验证切片
- 边界：全程 **synthetic 数据**；不执行真实支付、退款、风控放行、资金操作、真实配置变更或上游提交；Foundation 人工确认只写审计，拒付人工批准最多驱动 synthetic mock connector

---

## 0. 一句话目标

帮助跨境 PSP 在举证窗口内把一次拒付稳定地推进为「识别理由 → 逐项补证 → 评估是否值得申诉 → 按银行规则打包 → 人工批准 → 提交与跟进」，并让每个判断都有证据依据和审计记录。

---

## 1. 背景与方向变化

### 1.1 会议确定的核心

- **核心定位**：Oceanpayment 作为 PSP，夹在商户、发卡行、收单行和卡组织之间；**商户不能直接对接银行申诉**，必须由 PSP 在时限内索证、评估、打包和提交。OceanPilot 只聚焦这条拒付申诉协作链。
- **痛点**：拒付处理全靠人工；商户普遍不做证据留存，举证有效性不足；不同银行规则不一；**15 天举证 / 45 天审核，任一环节超期直接判负**。
- **Agent 价值**：资料自动匹配申诉、全流程节点提醒；全链路协作预计 **80% 标准流程可由 agent 完成**：
  - 商户端拒付助手（实时侦测/拦截拒付倾向、引导留证）
  - Oceanpayment 内部 Agent（A2A 信息匹配、按银行规则打包）
  - 申诉 Agent（对接上游渠道、跟进进展）
- **知识库**：沉淀不同银行的规章、举证要求、注意事项，供 agent 调用，弥补人工经验有限。
- **数据**：商户资料在自有封闭系统，独立库、无外部接入；将提供 **脱敏真实案例** 训练（真实案例比 AI 生成更有价值）。

### 1.2 三条本次明确的方向指令

1. **渠道无关内核 + 飞书协作工作台** → HTTP/Web 承载完整引擎与演示，飞书承载内部补证、审批和临期协作；飞书不是业务规则的事实源。
2. **大模型先用 Claude，但保留调用 API 的方式** → 引入 **可插拔的模型提供层（ModelProvider）**，默认 Claude（`claude-opus-4-8`，官方 Anthropic SDK），保留按「任务 / 保密等级」路由到其他 API 或本地模型的能力。
3. **目标演进为「Agent 专属处理器 + Agent 集群」** → 在确定性内核之上加一层多智能体协作。

### 1.3 与已有实现的关系（不是推翻）

现有 Foundation 已验证「版本化建案 → 缺证补问 → 确定性判断 → 人工确认 → 审计」的技术原则。拒付主线采用这些原则，但当前仍使用独立的数据模型和 SQLite；不能表述为已经复用完整 EvidenceItem 或 diagnosis snapshot。支付异常切片保留为底层可扩展性证明，不与拒付并列为产品主体。

---

## 2. 范围与非目标

**In scope（`v0.2.1` 已用 synthetic 实现）**
- 渠道无关内核 + HTTP/API/Web 运行入口 + 飞书解析/渲染适配器 seam（拒付适配器尚未接入签名回调）
- 拒付领域模型 + reason-code 确定性规则 + 15/45 天时限状态机
- 银行规则知识库 port、合成条目与确定性精确匹配（不含 RAG）
- Agent 集群（Supervisor + 专属处理器），可用 synthetic 端到端跑通
- 可插拔 ModelProvider（离线默认 Scripted fallback；Claude/local 为显式启用的实现）
- 高/中/低保密的模型部署与加密 **建议方案**（文档 + 可注入配置）

**Out of scope / 需公司输入或入围后**
- 真实 Oceanpayment 数据、真实银行 API、真实上游申诉渠道
- 真实银行规章内容（先用合成占位，schema 设计成可灌入真实数据）
- 真实脱敏案例（公司后续提供）
- 公司具体操作流程（会议列为待确认）、具体保密等级
- RAG/向量库、Scheduler/Messenger 出站通知、生产部署、真实 tenant 联调、资金相关任何动作

**硬边界（始终成立）**
- synthetic only；不执行任何真实资金/业务动作；Foundation 人工确认只写审计，拒付批准只调用 mock connector
- 不宣称生产就绪、真实集成或 exactly-once 分布式事务
- 凭据只走环境变量；日志/审计/DB 不含凭据、原始用户ID、证据正文、签名、token

---

## 3. 关键设计决策

### D1. 混合架构：确定性内核 + Agent 集群（不是纯 LLM）

- **确定性内核 = 系统事实源 + 信任边界**：拒付案件、证据类型与 readiness、reason-code 规则、责任路由、时限计算、审计和 revision CAS。Foundation 另验证了更完整的 EvidenceItem 与 diagnosis replay；当前不把该能力自动归到拒付结果上。
- **Agent 集群 = 模糊接口 + 协作层**：理解大白话、抽取/校验证据、匹配银行规则、起草申诉、生成解释。**Agent 只“提议”，内核 + 人“裁定”。**
- 理由：拒付是资金相邻 + 合规场景，胜诉评估/证据打包/申诉不能靠 LLM 拍板；这也是参赛差异化（可审计的证据系统，不是又一个 LLM 客服）。

### D2. 渠道无关内核，channel 只是薄适配器

- 内核只认「归一化输入（NormalizedInbound）」和「归一化输出（Delivery）」，不认飞书/Web/API 细节。
- 每个 channel adapter 负责：鉴权/验签 → 解析为 NormalizedInbound → 调 CaseService/Agent 编排 → 把结果渲染成该渠道的载体（飞书卡片 / JSON / Web 组件）。
- HTTP/Web 当前驱动完整拒付链；`FeishuChannel` 已作为 parser/renderer seam 测试，但尚未接入 Foundation 的签名 event/card-action 路由。未配置飞书时其它渠道照常工作。

### D3. 可插拔模型层，离线默认、Claude 可显式启用

- 定义 `ModelProvider` 端口；提供 `ClaudeProvider`（官方 Anthropic SDK）和本地 provider。应用默认注入离线 `ScriptedModelProvider`；只有 `OCEANPILOT_CHARGEBACK_LIVE_MODEL` 显式开启时才构造 live 分级 provider。
- **按「任务复杂度 + 保密等级」路由**，而非全局一刀切（见 §7、§8）。
- 保留替换实现：Anthropic 第一方 API / Bedrock / Vertex / Foundry / 本地开源模型端点。

### D4. 共享 Case 状态当「总线」，A2A = 读写同一版本化案件

- Agent 之间不自由聊天，而是通过 **同一个版本化 Case + 追加审计** 协作。拒付案件写入具备 revision CAS 和可审计性，但这不等于 assessment/package/appeal/agent trace 已具备 snapshot replay。
- Supervisor 编排相位；专属 agent 做窄任务；高风险/低置信进入人工闸门。

### D5. 时限驱动状态机（目标态）

- 15 天举证 / 45 天审核 / 节点提醒 / 超期处理是一等公民。当前 `DeadlineTracker` 已实现可注入时钟与提醒/逾期标志计算；真正激活 agent、发送提醒或改变生产工作流仍需 Scheduler/Messenger 与真实流程输入。

---

## 4. 拒付领域模型

### 4.1 案件与状态

- 目标聚合：`DisputeCase`（在现有 Merchant Success Case 上扩展；目标增加 `case_type = CHARGEBACK`）。
- 目标状态机（示意，最终以真实流程和领域评审为准）：
  `INTAKE → NEED_EVIDENCE → EVIDENCE_READY → ASSESSED → PACKAGED → REPRESENTMENT_SUBMITTED → AWAITING_ISSUER → RESOLVED(WON/LOST/EXPIRED)`
  - `v0.2.1` 当前 Supervisor 只持久化并驱动 `NEEDS_INTAKE / REASON_PROPOSED / NEED_EVIDENCE / ASSESSED`。Package 与 Appeal 是独立 HTTP 操作，不会把案件持久化为上述后续目标 phase；真实状态机仍待公司流程校准。

### 4.2 拒付 reason-code（合成占位，待公司真值）

按卡组织争议大类建模（示意）：欺诈（Fraud / EMV-3DS liability）、未收到商品/服务（Not Received）、货不对板（Not as Described）、重复扣款（Duplicate）、已退款未入账（Credit Not Processed）、取消订阅/授权（Canceled Recurring）、技术类（Authorization / Processing Error）。
- 每个 reason-code 绑定：**所需证据清单**、**胜诉要点**、**推荐责任团队**、**默认时限**。

### 4.3 证据契约边界

- Foundation 沿用「来源/时间/版本/可用性/引用」绑定；其飞书/HTTP 提交固定 `MERCHANT / USER_REPORTED / synthetic=true`，低来源质量触发人工复核。
- `v0.2.1` 拒付集群当前只持久化“证据类型是否具备”，未复用完整 EvidenceItem 来源/正文/文件实体契约。拒付证据码包括交易凭证、3DS 结果、物流签收、退款记录、服务条款、沟通记录等 synthetic 枚举；文件对象和真实来源质量仍是 backlog。

### 4.4 银行规则知识库

- 结构：`bank_id / card_network / reason_code → { 必需证据, 可选证据, 格式与顺序模板, 提交窗口, 备注 }`。
- 当前用法：打包 agent 通过 `KnowledgeBase` port 调用 `InMemoryBankRules`，按银行 + 卡组织 + reason-code 做确定性层级精确匹配，生成 representment 包并做完整性校验。
- 目标用法：真实规则到位并完成质量验收后，可在同一 port 后增加 RAG/向量检索；`v0.2.1` 不包含 RAG 或向量库。
- 数据：当前只有合成条目；schema/loader 已可灌入公司提供并通过安全审查的规则。

### 4.5 时限生命周期

- 当前：`DeadlineTracker` 计算举证窗口（建案 + 15 天）、审核窗口（mock 提交 + 45 天）、T-7/T-3/T-1 提醒标志和 overdue/auto-lost 建议。审核窗口逾期只标记升级，不自动判商户败诉。
- 未实现：持久化 `evidence_due_at/review_deadline_at` 目标状态、定时扫描、出站提醒、临期升级和生产状态变更。需在公司流程确认后增加 Scheduler/Messenger（见 §6、§9）。

---

## 5. 系统架构（分层）

依赖方向由外向内，领域/应用层不依赖框架/SDK/渠道（沿用现有 import-boundary 约束）。

```
Channels        ┌ HTTP/API + Web ┐ ┌ Feishu adapter seam ┐  ← 飞书尚未接入签名回调
                └────────┬───────┘ └──────────┬──────────┘
                         └────────────────────┘
Agent 编排       Supervisor / Router（相位机 + 人工闸门）        ← 应用层
用户可见角色     ①受理与补证 ②评估与材料 ③审批与时限协作
内部处理器       Intake · Evidence · Assess · Packager · Appeal · Deadline
                     │            │            │
Ports            ChargebackCaseStore · ModelProvider · KnowledgeBase · Clock
                     │
Domain           案件/证据契约/reason-code 规则/胜诉评估/责任路由/时限状态机/审计（确定性、可复算）
                     │
Adapters         SQLite(案件/审计) · InMemoryBankRules · Claude/本地模型 · mock 上游

Planned          RAG/向量库 · Scheduler/Messenger · 真实上游/外部 A2A · 真实飞书 tenant
```

当前不变量分为两组，不能混写：

- **Foundation 诊断链：** 诊断 identity 为 `(case_id, evidence_revision, policy_version)`；相同 identity replay；证据 revision CAS、跨案件引用回滚，诊断快照/假设/引用/路由/审计原子提交。
- **拒付集群：** 独立 SQLite 持久化 case、reason、evidence、collection-finalized 与 append-only audit，并以案件 revision 做乐观 CAS。低置信/缺关键证据进入人工闸门；模型不能改变确定性胜诉评估。
- **拒付当前不声明：** assessment/package/appeal/agent trace 的 snapshot identity、持久化 replay 或真实上游 exactly-once；这些结果按当前案件状态计算，Appeal 最多调用 synthetic mock connector。

---

## 6. 协作角色与内部处理器

### 6.1 拓扑

```
             ┌──────── Supervisor / Router（按相位调度 + 人工闸门） ────────┐
             │                                                           │
 ①受理与补证                 ②评估与材料                   ③审批与时限协作
 Intake + Evidence           Assess + Packager              Appeal + Deadline
             └──────── 共享拒付案件 + append-only audit ────────────────┘
                         合规/安全护栏（横切）
```

### 6.2 内部处理器职责

| # | Agent | 职责 | 主要工具（端口） | 建议模型档 |
|---|---|---|---|---|
| ① | Intake/Triage | 大白话→判定 reason-code 家族→建案绑定 | CaseCommandPort, BankKB(分类) | 中 |
| ② | Evidence Collector | 按 reason-code 算清单，逐项补问、校验、找缺口 | readiness 引擎, BankKB | 中 |
| ③ | Dispute Assessor | 证据达标→跑确定性规则→候选原因+胜诉可能性+证据引用+薄弱点 | DiagnosisEngine(确定性) | 高（仅解释走 LLM） |
| ④ | Bank-Rule Matcher/Packager（内部 A2A） | 精确匹配 synthetic 银行/卡组织模板→按序打包 representment→完整性校验；RAG 待后续 | BankKB, Packager | 高 |
| ⑤ | Appeal/Representment | 起草申诉文书；人工闸门后只调用 mock 上游 | ModelProvider(起草), ChannelConnector(mock) | 高 |
| ⑥ | Deadline/SLA | 计算 15/45 天窗口、提醒节点和逾期标志；不发送真实提醒 | Clock（Scheduler/Messenger 待后续） | 低/无 LLM |
| ⑧ | 护栏（横切） | PII 脱敏、模型分级路由、禁资金动作、审计、人工闸门 | Redactor, PolicyGate, Audit | — |

Prevention 是交易前扩展示例，不属于拒付申诉主链，也不计入上述用户可见角色。**编排要点**：确定性闸门 + 人在环；评估结构走确定性引擎，只有解释文字和文书起草走 LLM；人工批准后最多调用 mock connector；Deadline 当前只计算时限结果，不改变生产状态。会议提出的「80% agent + 高风险人工」是待真实流程与数据验证的目标，不是 `v0.2.1` 的业务效果结论。

---

## 7. 模型提供层（离线默认，Claude 可插拔）

### 7.1 端口

```python
class ModelProvider(Protocol):
    def complete(self, *, task: TaskSpec, messages, tools=None,
                 effort="high", schema=None) -> ModelResult: ...
```
- 应用层只依赖 `ModelProvider`；具体实现（Claude / 本地 / 其它 API）在组合层注入。
- `TaskSpec` 携带 **任务类型 + 数据敏感度**，供路由选择实现与档位。

### 7.2 可选 live 实现：Claude（官方 Anthropic SDK）

- 模型：默认 `claude-opus-4-8`（Opus 4.8，1M context）；批量/低敏可降 `claude-sonnet-5`，简单分类可 `claude-haiku-4-5`。
- 思考：`thinking={"type":"adaptive"}`；深度用 `output_config={"effort": ...}`（low/medium/high/xhigh/max）。**不使用 `budget_tokens`/`temperature`（4.8 会 400）**。
- 工具调用：优先 SDK tool runner；需要人在环处用手写 agentic loop（逐步执行、可拦截/审批）。
- 长输出/长上下文用 streaming + `get_final_message()`。
- 认证：`ANTHROPIC_API_KEY`；凭据只走环境变量。无 key 或未开启 live 开关时不会调用外部模型。
- 提示缓存：冻结 system + 确定性工具顺序，把易变内容放末尾，降本降延迟。

### 7.3 保留其它 API / 本地（按保密等级切换实现，见 §8）

- 企业云网关：`AnthropicBedrockMantle` / `AnthropicVertex` / `AnthropicFoundry`（同一 messages 接口，模型 ID 前缀/形态各异）。
- 高保密隔离：本地开源模型端点实现同一 `ModelProvider` 端口（自有 HTTP client），置于隔离环境。
- 说明：live 目标路径采用「Claude API + 自持 agent loop」；`v0.2.1` 应用运行时仍默认离线 Scripted provider。Managed Agents 仅是设计期可选方向，当前仓库未接入。

---

## 8. 安全与部署分级（会议重点）

**按每一步数据敏感度路由，而非全局一刀切：**

| 保密等级 | 触及原始 PII/交易明细的步骤 | 推理/起草步骤 | 说明 |
|---|---|---|---|
| 高 | 本地隔离模型（内网/VPC，独立节点） | 本地隔离模型 | 数据不出域；接受资源开销 |
| 中 | 先脱敏/打码 agent 去隐私 | 脱敏后调外部开源/云模型 | 平衡效果与合规（去隐私会影响数据，需评估） |
| 低 | 外部模型（模板/文案类） | 外部模型 | 追求效果 |

- **脱敏 agent（⑧护栏）**：调外部模型前对 PII/账号/卡号/金额做占位替换；出站前还原仅在受控边界。
- **存储加密**：飞书企业版 + HDFS 场景的传输/静态加密与访问控制；原始资料留在公司封闭系统，agent 只拿受限/脱敏视图。
- **凭据/日志**：环境变量注入；日志/审计/DB 不含凭据、原始用户ID、证据正文；需要关联时存 hash。
- **交付物**：一份「安全建议方案」文档（分级部署 + 加密外部方案），配可注入配置开关。

---

## 9. `v0.2.1` 与现有代码的映射

| 能力 | 当前实现 | 剩余边界 |
|---|---|---|
| Foundation 建案/证据/诊断/路由/审计/CAS/replay | ✅ 已实现并持久化 | 继续作为独立 Foundation 内核；不把其 diagnosis snapshot 语义自动套到拒付结果 |
| 拒付案件/证据/审计 | ✅ 独立 SQLite + revision CAS + append-only audit | assessment/package/appeal/agent trace 尚无 snapshot replay 持久化 |
| 分层边界 | ✅ import-boundary 测试；ModelProvider/KB/Clock/Store 均走 port | 真实外部 adapter 仍未接入 |
| HTTP/Web 渠道 | ✅ 完整 synthetic 闭环与 `/demo` | 不代表真实业务入口 |
| Foundation 飞书签名回调 | ✅ synthetic `PAYMENT_INCIDENT` 闭环 | 未做真实 tenant smoke |
| 拒付 `FeishuChannel` | ✅ parser/renderer seam + 渠道单测 | 未接入签名 event/card-action 路由 |
| reason-code 与证据规则 | ✅ synthetic 确定性规则表 | #21 等待公司真值校准 |
| 银行规则知识库 | ✅ `KnowledgeBase` + `InMemoryBankRules` 精确匹配 | 真实规则、RAG/向量库未实现 |
| 时限 | ✅ Clock + 15/45 天与提醒标志计算 | Scheduler/Messenger、真实通知和状态变更未实现 |
| 多 Agent / Supervisor | ✅ Intake/Evidence/Assess + shared-case internal A2A | 不声明外部 A2A 或通用 Workflow Engine |
| Package/Appeal/Prevention | ✅ synthetic 打包、人工闸门 + mock 上游、synthetic 预防建议 | 真实上游与真实交易信号未接入 |
| ModelProvider | ✅ Claude/local/router/redactor；无 key 时 deterministic fallback | live 凭据与生产模型部署由运行环境决定，不入库 |
| 安全分级/观测 | ✅ sentinel、脱敏、分级建议、PII-free 请求日志、进程内指标 | 生产鉴权、限流、日志/metrics backend 与运行保障未实现 |
| 数据导入 | ✅ #21 schema/loader/fixtures | 真实/脱敏公司数据、流程与保密等级仍 blocked |

> 注意：这里的 internal A2A 指 agents 通过同一版本化案件协作，不是已接入外部 A2A 协议或平台。项目仍未加入通用 Workflow Engine，也未接真实外部 A2A。

---

## 10. 分阶段路线状态（适配「公司数据未到」）

- **P0 — completed synthetic：** Foundation 确定性内核、HTTP、签名飞书 callback seam、安全 sentinel 与 CI。
- **P1 — completed synthetic：** channel 抽象、`ModelProvider`/Claude/local 实现、Supervisor + ①②③、人工闸门和离线 fallback。
- **P2 — partially completed synthetic：** 内存精确 BankKB + ④打包 + ⑤起草/mock appeal + ⑥时限计算已完成；RAG、Scheduler/Messenger 和真实通知未完成。
- **P3 — partially completed synthetic：** shared-case internal A2A、mock 上游、⑦ synthetic 倾向侦测、脱敏与安全分级实现/方案已完成；真实外部 A2A、上游、信号源和生产部署未完成。

当前下一步不是继续扩写 synthetic 能力，而是按独立 Issue 推进：#21 公司数据校准；拒付飞书签名路由与 tenant smoke；RAG（若真实规则体量证明需要）；Scheduler/Messenger；真实外部连接；生产化。任何一项开始前都需先冻结输入、安全边界和验收标准。

---

## 11. 待确认（依赖公司）

1. 公司拒付处理 **具体操作流程**（会议列为待确认）。
2. 真实 **reason-code 清单** 与每类 **证据模板**。
3. 各 **银行/卡组织规章**（灌入知识库）。
4. **保密等级**（定高/中/低，决定模型部署与脱敏强度）。
5. 真实 **脱敏案例**（体量与对接方式，风控部门沟通）。
6. 上游申诉渠道对接方式（决定 ⑤ 是 mock 还是真连，及是否需要新增外部权限）。

---

## 12. 风险与对策

| 风险 | 对策 |
|---|---|
| LLM 幻觉影响资金相邻决策 | 确定性闸门 + 证据引用 + 人工确认；agent 只提议 |
| 多 agent 不确定性 | 共享版本化案件 + append-only audit；仅 Foundation diagnosis 声明 identity replay，拒付结果不越界声称 snapshot replay |
| 真价值依赖公司数据 | 先合成打通；KB/证据 schema 设计成可灌真实数据 |
| 合规/隐私 | 分级路由 + 脱敏 + 加密 + 凭据仅环境变量 |
| 成本/延迟 | 按任务/敏感度选模型档 + effort + 提示缓存；确定性引擎承担重校验 |
| 范围膨胀（A2A/KB/时限/安全） | 分阶段；每步 synthetic 可演示、可回退 |

---

## 13. 参赛叙事（差异化）

不是「又一个 LLM 客服」，而是 **可审计、可复算、带证据依据的 synthetic 拒付证据系统**：确定性内核约束评估，Agent 集群负责理解、补问、解释与 mock 协作。会议提出的「80% 标准流程自动化」和飞书/企业系统落地是待真实流程、规则、数据与 tenant 验证的目标，不是当前业务效果声明；当前人工闸门只记录 Foundation 建议或允许 synthetic mock 提交，不执行业务动作。
