# OceanPilot — 跨境拒付协作 Agent 集群设计

- 状态：草案，供团队浏览与对齐（**尚未开始实现**）
- 日期：2026-08-06
- 定位：把现有「证据驱动协作内核」重定向并做深到 **跨境拒付（chargeback / dispute）申诉** 场景，并演进为 **专属处理器 + Agent 集群（多智能体）** 架构
- 边界：全程 **synthetic 数据**；不执行支付、退款、风控放行、资金操作或真实配置变更；人工确认只记录建议、不改变案件状态、不触发业务动作

---

## 0. 一句话目标

在 **飞书之外也能独立使用、飞书内也能用** 的前提下，用一套 **确定性内核 + 可插拔大模型 + 多智能体协作** 的系统，把跨境拒付从「人工 case-by-case、证据散乱、依赖个人经验」变成「自动建案 → 逐项补证 → 按银行规则打包 → 带证据引用的胜诉评估 → 责任路由 → 人工确认 → 全程时限提醒 → 审计留痕」。

---

## 1. 背景与方向变化

### 1.1 会议确定的核心

- **核心定位**：面向跨境支付异常，把「问题 / 证据 / 判断 / 交接」链路产品化，可嵌入飞书，解决出海商户收款异常时「查问题慢、证据散乱、依赖个人经验」。
- **收窄到拒付场景**：Oceanpayment 作为 PSP，夹在商户、发卡行、收单行、卡组织之间——**商户不能直接对接银行申诉**，必须由 PSP 按上游银行要求索证、打包、提交。
- **痛点**：拒付处理全靠人工；商户普遍不做证据留存，举证有效性不足；不同银行规则不一；**15 天举证 / 45 天审核，任一环节超期直接判负**。
- **Agent 价值**：资料自动匹配申诉、全流程节点提醒；全链路协作预计 **80% 标准流程可由 agent 完成**：
  - 商户端拒付助手（实时侦测/拦截拒付倾向、引导留证）
  - Oceanpayment 内部 Agent（A2A 信息匹配、按银行规则打包）
  - 申诉 Agent（对接上游渠道、跟进进展）
- **知识库**：沉淀不同银行的规章、举证要求、注意事项，供 agent 调用，弥补人工经验有限。
- **数据**：商户资料在自有封闭系统，独立库、无外部接入；将提供 **脱敏真实案例** 训练（真实案例比 AI 生成更有价值）。

### 1.2 三条本次明确的方向指令

1. **主要在飞书之外使用，但保留飞书场景** → 内核必须 **渠道无关**，飞书是「其中一个 channel adapter」，不是核心。
2. **大模型先用 Claude，但保留调用 API 的方式** → 引入 **可插拔的模型提供层（ModelProvider）**，默认 Claude（`claude-opus-4-8`，官方 Anthropic SDK），保留按「任务 / 保密等级」路由到其他 API 或本地模型的能力。
3. **目标演进为「Agent 专属处理器 + Agent 集群」** → 在确定性内核之上加一层多智能体协作。

### 1.3 与已有实现的关系（不是推翻）

现有系统已实现的「建案 → 缺证补问 → 证据达标 → 确定性规则诊断 → 责任路由 → 人工确认 → 审计」正是会议描述的系统核心功能。**本设计把它作为可信内核复用**，主要新增：拒付领域内容、银行知识库、时限生命周期、渠道无关化、可插拔模型层、Agent 集群。

---

## 2. 范围与非目标

**In scope（可用 synthetic 现在做）**
- 渠道无关内核 + 渠道适配器（HTTP/API、飞书；预留 Web）
- 拒付领域模型 + reason-code 确定性规则 + 15/45 天时限状态机
- 银行规则知识库（结构 + 合成条目 + RAG 检索）
- Agent 集群（Supervisor + 专属处理器），可用 synthetic 端到端跑通
- 可插拔 ModelProvider（Claude 默认；本地/外部模型为可替换实现）
- 高/中/低保密的模型部署与加密 **建议方案**（文档 + 可注入配置）

**Out of scope / 需公司输入或入围后**
- 真实 Oceanpayment 数据、真实银行 API、真实上游申诉渠道
- 真实银行规章内容（先用合成占位，schema 设计成可灌入真实数据）
- 真实脱敏案例（公司后续提供）
- 公司具体操作流程（会议列为待确认）、具体保密等级
- 生产部署、真机联调、资金相关任何动作

**硬边界（始终成立）**
- synthetic only；不执行任何资金/业务动作；人工确认只写审计、不改状态
- 不宣称生产就绪、真实集成或 exactly-once 分布式事务
- 凭据只走环境变量；日志/审计/DB 不含凭据、原始用户ID、证据正文、签名、token

---

## 3. 关键设计决策

### D1. 混合架构：确定性内核 + Agent 集群（不是纯 LLM）

- **确定性内核 = 系统事实源 + 信任边界**：案件聚合、证据契约、readiness、reason-code 规则、责任路由、时限状态机、审计、CAS/replay。可复算、可审计、无幻觉。
- **Agent 集群 = 模糊接口 + 协作层**：理解大白话、抽取/校验证据、匹配银行规则、起草申诉、生成解释。**Agent 只“提议”，内核 + 人“裁定”。**
- 理由：拒付是资金相邻 + 合规场景，胜诉评估/证据打包/申诉不能靠 LLM 拍板；这也是参赛差异化（可审计的证据系统，不是又一个 LLM 客服）。

### D2. 渠道无关内核，channel 只是薄适配器

- 内核只认「归一化输入（NormalizedInbound）」和「归一化输出（Delivery）」，不认飞书/Web/API 细节。
- 每个 channel adapter 负责：鉴权/验签 → 解析为 NormalizedInbound → 调 CaseService/Agent 编排 → 把结果渲染成该渠道的载体（飞书卡片 / JSON / Web 组件）。
- 飞书退化为「可选 channel」；未配置飞书时其它渠道照常工作（已在现有代码验证）。

### D3. 可插拔模型层，Claude 默认、保留 API 路由

- 定义 `ModelProvider` 端口；默认实现 `ClaudeProvider`（官方 Anthropic SDK，`claude-opus-4-8`，adaptive thinking + effort）。
- **按「任务复杂度 + 保密等级」路由**，而非全局一刀切（见 §7、§8）。
- 保留替换实现：Anthropic 第一方 API / Bedrock / Vertex / Foundry / 本地开源模型端点。

### D4. 共享 Case 状态当「总线」，A2A = 读写同一版本化案件

- Agent 之间不自由聊天，而是通过 **同一个版本化 Case + 追加审计/事件日志** 协作 → 天然幂等、可审计、可重放。
- Supervisor 编排相位；专属 agent 做窄任务；高风险/低置信进入人工闸门。

### D5. 时限驱动状态机

- 15 天举证 / 45 天审核 / 节点提醒 / 超期判负是一等公民；由时钟 **激活** agent 与提醒，而非被动等人。

---

## 4. 拒付领域模型

### 4.1 案件与状态

- 聚合：`DisputeCase`（在现有 Merchant Success Case 上扩展；新增 `case_type = CHARGEBACK`）。
- 状态机（示意，最终以领域评审为准）：
  `INTAKE → NEED_EVIDENCE → EVIDENCE_READY → ASSESSED → PACKAGED → REPRESENTMENT_SUBMITTED → AWAITING_ISSUER → RESOLVED(WON/LOST/EXPIRED)`
  - 与现有 `NEW/NEED_INFO/EVIDENCE_READY/DIAGNOSED/HUMAN_REVIEW` 对齐扩展；人工确认仍只写审计。

### 4.2 拒付 reason-code（合成占位，待公司真值）

按卡组织争议大类建模（示意）：欺诈（Fraud / EMV-3DS liability）、未收到商品/服务（Not Received）、货不对板（Not as Described）、重复扣款（Duplicate）、已退款未入账（Credit Not Processed）、取消订阅/授权（Canceled Recurring）、技术类（Authorization / Processing Error）。
- 每个 reason-code 绑定：**所需证据清单**、**胜诉要点**、**推荐责任团队**、**默认时限**。

### 4.3 证据契约（沿用现有 evidence contract，扩拒付专属码）

- 沿用「来源/时间/版本/可用性/引用」绑定；飞书/HTTP 提交固定 `MERCHANT / USER_REPORTED / synthetic=true`（低来源质量 → 触发人工复核，已在现有引擎验证）。
- 新增拒付证据码（示意）：交易凭证、AVS/CVV 结果、3DS 认证结果、物流单号与签收、IP/设备指纹、退款记录、服务条款/退款政策、商户与持卡人沟通记录、发货照片、订阅授权凭证。

### 4.4 银行规则知识库（新）

- 结构：`bank_id / card_network / reason_code → { 必需证据, 可选证据, 格式与顺序模板, 提交窗口, 备注 }`。
- 用法：打包 agent 通过 **RAG 检索** 目标发卡行/卡组织规则，生成 representment 包并做完整性校验。
- 数据：先合成条目；schema 设计成可直接灌入公司真实规章。

### 4.5 时限生命周期（新）

- `evidence_due_at`（建案 + 15 天）、`review_deadline_at`（提交 + 45 天）；节点提醒（T-7/T-3/T-1）、临期升级、超期 → `EXPIRED(LOST)`。
- 需引入时钟/调度（见 §6、§9）。

---

## 5. 系统架构（分层）

依赖方向由外向内，领域/应用层不依赖框架/SDK/渠道（沿用现有 import-boundary 约束）。

```
Channels        ┌ HTTP/API ┐ ┌ Feishu ┐ ┌ Web(预留) ┐        ← 薄适配器：鉴权/验签、DTO、渲染
                └────┬─────┘ └───┬────┘ └────┬──────┘
                     └───────────┴───────────┘
Agent 编排       Supervisor / Router（相位机 + 人工闸门）        ← 应用层
Agent 集群       ①Intake ②Evidence ③Assess ④Bank-Rule/Packager ⑤Appeal ⑥Deadline ⑦Prevention
                     │            │            │
Ports            CaseCommandPort · ModelProvider · KnowledgeBase · Clock/Scheduler · Messenger · BindingStore
                     │
Domain           案件/证据契约/reason-code 规则/胜诉评估/责任路由/时限状态机/审计（确定性、可复算）
                     │
Adapters         SQLite(案件/审计) · 向量库(银行KB) · Claude/本地模型 · 渠道出站 · 调度器
```

关键不变量（沿用并扩展现有实现）：
- 诊断/评估身份 = `(case_id, evidence_revision, policy_version)`；相同身份 replay，不新增快照/审计。
- 证据 revision CAS；stale 输入不覆盖；跨案件证据引用拒绝并回滚。
- 快照/假设/证据引用/路由/审计原子提交；新证据只历史化旧结论。
- 低置信/冲突/风险/低来源质量/无规则 → 人工复核。

---

## 6. Agent 集群设计（专属处理器）

### 6.1 拓扑

```
            ┌──────────── Supervisor / Router（按相位调度 + 人工闸门） ────────────┐
   ┌────────┼──────────┬────────────┬───────────────┬──────────────┬────────────┐
 ①Intake  ②Evidence  ③Assess     ④Bank-Rule/Packager ⑤Appeal     ⑥Deadline   ⑦Prevention
  意图/建案 缺口/补问   胜诉评估      RAG银行规则→打包    起草/提交跟进  时限/提醒    倾向侦测(后期)
   └──────────────── 共享 Case+Evidence 聚合（单一事实源）+ 审计/事件日志 ────────────────┘
                          ⑧ 合规/安全护栏（横切：脱敏 / 模型分级 / 禁资金动作 / 审计）
```

### 6.2 各 agent 职责 / 工具 / I/O / 模型档

| # | Agent | 职责 | 主要工具（端口） | 建议模型档 |
|---|---|---|---|---|
| ① | Intake/Triage | 大白话→判定 reason-code 家族→建案绑定 | CaseCommandPort, BankKB(分类) | 中 |
| ② | Evidence Collector | 按 reason-code+银行规则算清单，逐项补问、校验、找缺口 | readiness 引擎, BankKB, Messenger | 中 |
| ③ | Dispute Assessor | 证据达标→跑确定性规则→候选原因+胜诉可能性+证据引用+薄弱点 | DiagnosisEngine(确定性) | 高（仅解释走 LLM） |
| ④ | Bank-Rule Matcher/Packager（内部 A2A） | 匹配目标行/卡组织模板→按序打包 representment→完整性校验 | BankKB(RAG), Packager | 高 |
| ⑤ | Appeal/Representment | 起草申诉文书；对接上游渠道（先 mock/人工闸门）；跟进状态 | ModelProvider(起草), ChannelConnector(mock) | 高 |
| ⑥ | Deadline/SLA | 持 15/45 天时钟；节点提醒、临期升级、超期判负 | Clock/Scheduler, Messenger | 低/无 LLM |
| ⑦ | Prevention（后期） | 事前侦测拒付倾向、提醒留证 | 信号源(公司数据) | 中 |
| ⑧ | 护栏（横切） | PII 脱敏、模型分级路由、禁资金动作、审计、人工闸门 | Redactor, PolicyGate, Audit | — |

**编排要点**：确定性闸门 + 人在环；③的规则判定与胜诉结构走确定性引擎，只有「解释文字/文书起草」走 LLM；⑤提交与⑥超期判负必须人工确认。对齐会议「80% agent + 高风险人工」。

---

## 7. 模型提供层（Claude 默认，可插拔）

### 7.1 端口

```python
class ModelProvider(Protocol):
    def complete(self, *, task: TaskSpec, messages, tools=None,
                 effort="high", schema=None) -> ModelResult: ...
```
- 应用层只依赖 `ModelProvider`；具体实现（Claude / 本地 / 其它 API）在组合层注入。
- `TaskSpec` 携带 **任务类型 + 数据敏感度**，供路由选择实现与档位。

### 7.2 默认实现：Claude（官方 Anthropic SDK）

- 模型：默认 `claude-opus-4-8`（Opus 4.8，1M context）；批量/低敏可降 `claude-sonnet-5`，简单分类可 `claude-haiku-4-5`。
- 思考：`thinking={"type":"adaptive"}`；深度用 `output_config={"effort": ...}`（low/medium/high/xhigh/max）。**不使用 `budget_tokens`/`temperature`（4.8 会 400）**。
- 工具调用：优先 SDK tool runner；需要人在环处用手写 agentic loop（逐步执行、可拦截/审批）。
- 长输出/长上下文用 streaming + `get_final_message()`。
- 认证：`ANTHROPIC_API_KEY`（或 `ant auth login` profile）；凭据只走环境变量。
- 提示缓存：冻结 system + 确定性工具顺序，把易变内容放末尾，降本降延迟。

### 7.3 保留其它 API / 本地（按保密等级切换实现，见 §8）

- 企业云网关：`AnthropicBedrockMantle` / `AnthropicVertex` / `AnthropicFoundry`（同一 messages 接口，模型 ID 前缀/形态各异）。
- 高保密隔离：本地开源模型端点实现同一 `ModelProvider` 端口（自有 HTTP client），置于隔离环境。
- 说明：Anthropic 也提供 Managed Agents（Anthropic 跑 agent loop + 托管工具容器）与 self-hosted sandboxes；本项目为保留 on-prem 控制与合规，**默认采用「Claude API + 自持 agent loop（本仓 tool-use 编排）」**，Managed Agents 作为可选加速路径。

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

## 9. 与现有代码的映射（复用 vs 新增）

| 能力 | 现状 | 动作 |
|---|---|---|
| 建案/证据/诊断/路由/审计/CAS/replay | ✅ 已实现（内核） | 复用；扩拒付领域内容 |
| 分层边界（domain/application 不依赖外部） | ✅ 有 import-boundary 测试 | 沿用；ModelProvider/KB/Scheduler 走端口 |
| 渠道适配（飞书回调/卡片、可选 503） | ✅ 已实现 | 抽象出 channel 接口，飞书降为一个 adapter |
| reason-code 规则表 | 现 4 条通用规则 | 扩充为拒付 reason-code 规则（需公司真值校准） |
| 银行规则知识库 + RAG | ❌ | 新增（结构+合成+向量库） |
| 时限/调度 | ❌ | 新增 Clock/Scheduler 端口 + 提醒 |
| 多 Agent 编排 / Supervisor | ❌ | 新增（应用层，工具化内核） |
| ModelProvider（Claude 可插拔） | ❌ | 新增端口 + ClaudeProvider |
| 安全分级/脱敏 | 部分（sentinel/固定安全错误） | 扩为脱敏 agent + 分级路由 + 加密方案 |

> 注意：原设计文档写过「不加通用 Workflow Engine / 不接 A2A」——本设计是 **有意识的范围升级**，需在评审中记录并更新架构文档。

---

## 10. 分阶段路线（务实，适配「公司数据未到」）

- **P0（已有）**：确定性内核 + 飞书/HTTP 通道 + 安全 sentinel + CI。
- **P1｜内核工具化 + 渠道无关化 + Claude 接入**：抽 channel 接口；`ModelProvider`+`ClaudeProvider`；Supervisor + ①②③，跑通 **合成拒付** 闭环 + 人工闸门。
- **P2｜银行知识库 + 打包 + 时限**：BankKB(RAG) + ④打包 + ⑤起草；⑥时限 agent + 提醒。
- **P3｜A2A/上游/防控/安全分级**：⑤真·A2A（先 mock 上游）；⑦倾向侦测；脱敏 agent + 高/中/低分级部署 + 加密方案落地。
- 横切从 P1 起：审计、护栏、禁资金动作、人工闸门、`ModelProvider` 抽象。

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
| 多 agent 不确定性 | 共享版本化状态 + 审计 + 重放（内核已具备） |
| 真价值依赖公司数据 | 先合成打通；KB/证据 schema 设计成可灌真实数据 |
| 合规/隐私 | 分级路由 + 脱敏 + 加密 + 凭据仅环境变量 |
| 成本/延迟 | 按任务/敏感度选模型档 + effort + 提示缓存；确定性引擎承担重校验 |
| 范围膨胀（A2A/KB/时限/安全） | 分阶段；每步 synthetic 可演示、可回退 |

---

## 13. 参赛叙事（差异化）

不是「又一个 LLM 客服」，而是 **可审计、可复算、带证据引用的拒付证据系统**：确定性内核保证正确与合规，Agent 集群把 80% 标准流程自动化并可嵌入飞书，安全分级让它在不同保密要求下都能落地。人工只在高风险与最终提交处确认——「确认建议并记录，不执行业务动作」。
