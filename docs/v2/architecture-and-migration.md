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

Agent 由案件事件观察、持久化工具运行与提案、可选真实模型对话组成。案件命令提交后立即运行规则检索、材料检查、期限扫描、同商户相似案件检索、行动规划和草稿准备。每个案件版本只有一份不可变工具记录；关键事件的模型解读在后台合并排队，避免阻塞业务写入。对话生成期间案件变化会拒绝旧版本结果。模型只能产生供复核的文字，操作提案由领域规则生成，提交仍需匹配负责人、人工确认和版本检查。

`OCEANPILOT_CHARGEBACK_LIVE_MODEL=1` 与本机 DeepSeek 配置使 V2 复用现有模型适配器。界面分别显示确定性工具记录、真实模型回答与降级回答，保留实际 model、source、trigger 和引用。新表 `v2_dispute_agent_runs` / `v2_dispute_agent_conversations` 与 V1 并存；Agent 观察失败不会撤销或重复已提交的业务命令。材料就绪度仍仅说明合成清单登记情况，未进行真实正文 OCR、真实性或胜诉率判断。详见 [Agent 协作](agent-workflow.md)。

知识候选只在结案后生成，先去除案件/商户标识及常见 PII，再由 Admin 审核。只有批准候选可参与相似模式检索，不能自动发布规则。

## 企业后续确认边界

各渠道 OP 精确角色、真实上游事件 schema、商户授权与无回复处置、正式规则/SLA/延期权利、提交和回执语义、账本费用与核对口径仍待企业确认。比赛代码以明确 Mock 或 NEEDS_CONFIRMATION 表达；不得将演示结果宣称为生产认证、真实提交、真实资金结算或胜诉率改善。


## 双端独立案件页与来源案例库

商户与运营分别使用 `/v2/merchant/cases/{id}` 和 `/v2/operations/cases/{id}`；根入口仅显示列表。旧 `?case=` 地址会规范化到独立案件页。OceanPilot 嵌入案件页，按案件与 `MERCHANT/OPERATIONS` 对话范围保存上下文；旧商户对话迁到商户侧，旧自动分析和未知角色默认保留在运营侧。确定性规则观察共享，商户读取时移除运营内部草稿。

`GET /api/v2/updates` 使用 SQLite 已提交的案件审计、Agent 运行及本端对话位置返回增量游标。长轮询不持有数据库事务等待，不调用模型；重启和断线后可以续读。前端应用变化后才推进游标；模型 pending 状态单独短轮询收尾。远端更新保留输入，并使旧版人工确认失效。

当前默认参考数据来自仓库 `docs/chargeback-case-library/03_case_library.json` 和 `06_seed_cases.json`：62 条参考、28 条模板。最高编号 074 不等于实际条数。完整源数据与 SHA 清单打包进 wheel，adapter 返回独立副本并校验资源哈希。来源性质、原核验状态、冲突与页码保留；运行态参考不自动成为生产规则。

运营目录 `/v2/operations/library` 展示实际资料；26 条 Visa/Mastercard 模板可通过 `INTAKE.case_template_id` 创建明确确认的演练交易。Amex 与产品安全模板仅保留预览。来源快照与用户填写的演练交易字段分别保存。模板建案及后续阶段不继承 Golden Demo 的六条 Mock 规则和默认时限，需风控确认当前适用的权利、证据与明确期限。

Agent 按当前卡组织、原因码检索指南参考，把 `REFERENCE_KNOWLEDGE` 与 `CASE_RULE_SNAPSHOT` 引用分开。新工具运行和每次对话保存真实检索记录；历史运行保持不变。现有六条 Mock fixture 继续服务 A–D Golden Demo，不代表参考库仅有六条。

案例库 provider 可通过同一检索接口替换，真实交易接入沿用独立的建案流程；旧案来源与规则快照不随新资料静默变化。现有 FastAPI 架构保留，未迁移到 Sites 的 JavaScript Workers，也未创建独立的 Figma 文件或公开站点。
