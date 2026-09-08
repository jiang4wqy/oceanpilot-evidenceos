# OceanPilot V2 · 实现与迁移

V2 以 OceanPayment 为正式争议的案件运营主体。Merchant 决策和举证，OP 运营发布任务与登记上游事件，Risk Officer 审核材料和规则，Supervisor 终审与核对结案，Admin 审核知识。Agent 读取快照、引用规则、解释缺口并提出绑定版本的下一步。

分支策略：从稳定 master `250e7d9` 建立 `oceanpilot-v2`，所有 V2 工作在该分支集成。按用户 2026-09-08 补充要求，不创建 PR，也不合并 master；master 保留原稳定 Demo。

实现依据：用户提供的 2026-09-08 `OCEANPILOT_V2_ARCHITECTURE.md`、`OceanPilot_V2_推进说明文档.docx` 和关联推进方案。以下是代码中的实际边界，不代表企业生产接入已经完成。

## 迁移判断

| 分类 | 组件 | 处理 |
|---|---|---|
| KEEP | V1 evidence/reason catalog、确定性材料规则 | V2 直接复用证据类型、中文解释和材料清单，保留原单元测试 |
| KEEP | 模型 providers、V1 chargeback/workspace、旧 SQLite 表 | 保留兼容运行与既有历史，避免将旧商户自建材料案件伪装为上游正式案件 |
| KEEP | FeishuRequestVerifier 和签名/时窗策略 | V2 复用，新增可信 tenant/sender/chat 绑定与不透明卡片引用 |
| REFACTOR | 工作入口与案件所有权 | 新主入口为 `/v2/operations`，商户协作入口 `/v2/merchant`；正式 intake 仅 OP |
| ADD | `domain/dispute.py`、`application/disputes.py` | 多维状态、明确角色动作、审核、包、提交、结果、资金、关闭和知识命令 |
| ADD | `domain/dispute_rules.py` | 精确渠道/阶段/版本匹配，冻结来源；未知规则不推算截止日 |
| ADD | `adapters/persistence/disputes.py` | 新 `v2_dispute_*` 表；单事务保存聚合、revision、审计和命令回执 |
| ADD | `api/disputes.py`、`web/v2/*` | 严格命令 DTO、角色隔离、双工作台和治理视图 |
| ADD | V2 Feishu adapter | 真实可执行签名 callback seam、持久化卡片/回执、同案协作审计；没有发送外部消息 |
| RETIRE | 商户主动建正式争议、商户自审、首次提交即完成 | 从 V2 主流程移除；V1 `/demo`、`/business` 仅作历史兼容演示 |

采用新增聚合的渐进迁移：V1 记录缺少上游案件身份、商户授权和正式规则来源，不能自动转成 V2 正式记录。V1/V2 共用已有 chargeback SQLite 文件但使用独立表；不会删除或改写旧案。服务初始化在 FastAPI lifespan 中执行。

## 依赖与命令边界

```text
Web / strict HTTP / signed Feishu
    → DisputeService
        → domain states + permissions + rule/plan functions
        → DisputeStore port
            ← SQLite adapter
```

每个命令包含 `command_id`、`case_id`、`expected_revision`、`action`、`data` 和 `confirmed`。高风险动作只有授权人明确确认后执行；确定性闸门仍会拒绝缺证、旧版本、未知规则和不完整终局。幂等回执与审计和案件变更在同一 SQLite 事务内保存。重试复用原 `command_id`，不要把网络异常当成提交失败后另建发送。

上游事件按来源和事件 ID 去重，同一事件不能重新绑定到另一案件；`upstream_case_id` 将不同通知关联到同案。人工确认规则必须显式列出 `allowed_actions`，商户决定逐项校验已有权利。资金净影响以商户侧记录：借记、退款和费用为负，贷记为正，调整项使用明确有符号金额；跨币种核对需要另外确认，当前拒绝混币种。

`CaseStage`、`WorkStatus`、`MerchantDecision`、`BusinessOutcome`、`Finality`、`FinancialStatus` 分别保存。Accept 不创建额外退款，未响应不自动接受。技术回执、业务接收与业务终局分别记录；非终局事件保留阶段历史并重新匹配规则与 SLA。

结案需同时满足终局确认、已核对或经人工说明资金不适用、必要任务完成、结果已通知，以及必要审核/提交/来源审计材料齐全。WON/LOST 本身不能关闭案件。

## 规则与数据来源

内置六条精确 Mock fixture：Visa 10.4、Visa 13.1、Mastercard 4853，分别覆盖 FORMAL_DISPUTE 和 REPRESENTMENT。均复用仓库合成 evidence policy；`source_type=SYNTHETIC_DEMO`、`production_eligible=false`，`VERIFIED` 仅表示 fixture 本身经过测试。

Mock 时限为收到事件后的 72/96/120 个 UTC 小时，用于演示商户、OP、上游三个截止时间；不是卡组织法定/业务时限。其他渠道、理由、阶段或失效日期必须人工确认来源、版本、证据项与明确截止日。旧案保存快照，不因新规则静默变化。

Agent 是可离线运行的确定性工作流规划器，复用相同领域快照和门槛。界面明确显示 `DETERMINISTIC / case-planner-v2`；V1 DeepSeek provider 继续保留，但 V2 不将确定性计划冒充实时模型输出。材料就绪度仅说明合成清单登记情况，未进行真实正文 OCR、真实性或胜诉率判断。

知识候选只在结案后生成，先去除案件/商户标识及常见 PII，再由 Admin 审核。只有批准候选可参与相似模式检索，不能自动发布规则。

## 企业后续确认边界

各渠道 OP 精确角色、真实上游事件 schema、商户授权与无回复处置、正式规则/SLA/延期权利、提交和回执语义、账本费用与核对口径仍待企业确认。比赛代码以明确 Mock 或 NEEDS_CONFIRMATION 表达；不得将演示结果宣称为生产认证、真实提交、真实资金结算或胜诉率改善。
