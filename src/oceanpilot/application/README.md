# `application/` — 编排与端口 / orchestration & ports

**用例编排层。** 组合领域内核、定义外部依赖的 **Protocol 端口**、驱动 agent 集群。

依赖规则:本层**顶层 `*.py`** 只能 import domain 与本层,**禁止** import `fastapi`/`sqlite3`/`oceanpilot.api`/`oceanpilot.adapters`(测试强制)。因此所有 IO(模型、存储、渠道、上游)都以 Protocol 声明在这里,实现放 `adapters/`。

## 端口(Protocol,由 adapters 实现)

| 端口 | 文件 | 实现示例 |
|---|---|---|
| `ModelProvider` | `model_provider.py` | `adapters/model/{claude,local,fake,composition}.py` |
| `ChargebackCaseStore` | `chargeback_ports.py` | `adapters/persistence/chargeback_{sqlite,memory}.py` |
| `KnowledgeBase`(银行规则) | `knowledge_base.py` | `adapters/knowledge/bank_rules.py` |
| `UpstreamConnector` | `upstream.py` | `adapters/upstream/mock.py` |
| `Clock` | `scheduling.py` | `adapters/clock.py` |
| `SignalSource` | `prevention_ports.py` | `adapters/signals/synthetic.py` |
| `Channel` | `channels.py` | `adapters/channels/{http,feishu}/channel.py` |
| 飞书端口 | `feishu_ports.py` | `adapters/feishu/*` |

## 拒付集群

| 模块 | 职责 |
|---|---|
| `chargeback_agents.py` | agent 集群:`IntakeAgent`(理由分类 + 结构化事实抽取)、`EvidenceAgent`(逐项补证)、`ChargebackAssessAgent`(解释内核评估)、`PreventionAgent`。每个都"内核决策 + 模型解释 + 确定性兜底"。 |
| `chargeback_supervisor.py` | 编排状态机 + A2A 总线:`ChargebackCaseState` 为共享黑板,`advance()` 驱动 `REASON_PROPOSED→NEED_EVIDENCE→ASSESSED`;含人工确认与 `collection_finalized` 出口。 |
| `channels.py` | 渠道无关契约:`NormalizedInbound`(入)/`Delivery`(出)/`Channel`(Protocol)。 |
| `chargeback_channel_service.py` | 渠道无关核心:把 `NormalizedInbound` 经 supervisor + store 变成 `Delivery`。HTTP 与飞书共用这一处逻辑。 |
| `chargeback_packager.py` / `chargeback_appeal.py` | 按银行模板结构化打包;生成 representment 申诉信,**人工确认硬闸门**后才调用上游。 |
| `chargeback_deadline.py` | 确定性 SLA/时限(举证窗口、逾期、提醒),clock 注入。 |
| `redaction.py` | 按安全档位脱敏后再外发的策略。 |

## 基础版

`case_service.py`(支付异常案件用例)、`feishu_orchestrator.py`(飞书协作编排,依赖 `feishu_ports`)、`commands.py`/`ports.py`/`errors.py`。
