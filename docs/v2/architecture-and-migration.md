# OceanPilot V2 · 实现与迁移

V2 以 OceanPayment 为正式争议的案件运营主体。商户（MERCHANT）决策和举证，风控专员（OPERATOR）依既定规则经办、核查材料、跟进补件并上报风险；风控经理（SUPERVISOR）负责案件规则与期限确认、全局进度、分配、独立终审和核对结案。IT 管理员（ADMIN）仅管理账号、系统配置诊断与合成交易登记，不读取运行案件、不拥有业务命令。Agent 读取获授权快照、引用规则、解释缺口并提出绑定版本的下一步。

## 四角色迁移（2026-09-14）

启动身份库时，旧 RISK_OFFICER → OPERATOR、DIRECTOR → ADMIN。账号 ID、用户名、密码哈希和商户授权保持不变；迁移账号的旧会话撤销，新角色重新登录。只有这四类账号可以新建或登录；AGENT 是保留的系统身份。

启动案件库时，仅迁移参与者当前角色及 OPEN/IN_PROGRESS 任务的旧 RISK_OFFICER 责任字段。每个变更案件增加一次 revision 与 ROLE_MIGRATION 审计，旧审核、已完成任务、消息及命令回执保持原样，历史角色展示为“历史风控专员”。重复启动无重复迁移；旧版本操作和提案须刷新后重新确认。

SUPERVISOR 可读取全部案件，不受专员商户范围和案件参与者限制；OPERATOR/MERCHANT 继续执行原对象授权。CONFIRM_RULE、ASSIGN_CASE 和 APPROVE_KNOWLEDGE 仅 SUPERVISOR 可执行。经理可把案件分配给已获该商户授权的专员或风控经理，分配时加入案件参与者。ADMIN 即使保留旧商户授权或参与者记录，也不能读取案件；列表和更新为空，指定案件返回 404，业务命令返回 403。网站、SQL 队列、自动更新及飞书入口执行相同边界。

独立复核按真实 actor_id 判断，经理没有豁免：本案经办、材料审核与包作者不能终审，重新分配案件不清除原经办记录；账务登记人不能核对自己的资金事件。可交由另一位独立经理复核，不能改用 IT 管理员绕过。商户接受／抗辩仍需本人决定或已有明确授权，经理终审不代表可编造银行终局。

GET /api/v2/cases 仅为 SUPERVISOR 增加 assignee_progress：按负责人提供 user_id、display_name、role、total、pending（未完成任务数）、urgent（现有 URGENT 队列条件）、review（初审或包终审中）和 closed。统计覆盖全部案件，不受分页、搜索或负责人筛选影响；零案件的启用专员也列出。IT 治理页只展示技术配置与账号入口，不把无业务权限伪装成“零案件”的业务指标。

2026-09-15 的责任收紧还会在启动案件库时，将旧 OPEN/IN_PROGRESS 的 RULE_CONFIRMATION 待办调整为 SUPERVISOR、清空旧专员指派并进入经理待办；每案增加 revision 与 MANAGER_AUTHORITY_MIGRATION 审计，记录原责任人。已完成任务、旧审核和回执不改写，重复启动无重复迁移；旧卡片和提案需刷新。账号不自动升职；历史经办人若是 IT 管理员，应由经理显式重新分配，保留历史审计。本轮未重启既有运行实例。

此处“规则确认”是对本案来源、证据要求、可选动作与期限快照的确认，不是新增的企业全局规则编写／发布／审批系统。

管理入口改为 /v2/admin 和 /api/v2/admin/accounts、/api/v2/admin/accounts/{user_id}/status、/api/v2/admin/transactions。旧 /v2/director 返回 308，旧管理 API 返回 410。账号创建与启停在 v21_account_audit 中记录真实管理员，不保存密码。

升级前按部署方式备份争议 SQLite（运行中使用 SQLite backup API，或停服后完整备份数据库及 WAL）。回退时先停服，恢复旧代码与同一次备份，再启动；不要只回退代码而保留已迁移账号。迁移本身不重置账号和密码。

分支策略：V2 最初从稳定 master `250e7d9` 建立 `oceanpilot-v2` 集成；2026-09-14 起通过独立整合分支和 PR 将已验收的 V2 变更回合到仓库默认分支 `master`，不直接推送默认分支。

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

知识候选只在结案后生成，先去除案件/商户标识及常见 PII，再由风控经理审核。只有批准候选可参与相似模式检索，不能自动发布规则或直接成为大群公开知识。

## 企业后续确认边界

各渠道 OP 精确角色、真实上游事件 schema、商户授权与无回复处置、正式规则/SLA/延期权利、提交和回执语义、账本费用与核对口径仍待企业确认。比赛代码以明确 Mock 或 NEEDS_CONFIRMATION 表达；不得将演示结果宣称为生产认证、真实提交、真实资金结算或胜诉率改善。


## 双端独立案件页与来源案例库

商户与运营分别使用 `/v2/merchant/cases/{id}` 和 `/v2/operations/cases/{id}`；根入口仅显示列表。旧 `?case=` 地址会规范化到独立案件页。OceanPilot 嵌入案件页，按案件与 `MERCHANT/OPERATIONS` 对话范围保存上下文；旧商户对话迁到商户侧，旧自动分析和未知角色默认保留在运营侧。确定性规则观察共享，商户读取时移除运营内部草稿。

`GET /api/v2/updates` 使用 SQLite 已提交的案件审计、Agent 运行及本端对话位置返回增量游标。长轮询不持有数据库事务等待，不调用模型；重启和断线后可以续读。前端应用变化后才推进游标；模型 pending 状态单独短轮询收尾。远端更新保留输入，并使旧版人工确认失效。

当前默认参考数据来自仓库 `docs/chargeback-case-library/03_case_library.json` 和 `06_seed_cases.json`：62 条参考、28 条模板。最高编号 074 不等于实际条数。完整源数据与 SHA 清单打包进 wheel，adapter 返回独立副本并校验资源哈希。来源性质、原核验状态、冲突与页码保留；运行态参考不自动成为生产规则。

运营目录 `/v2/operations/library` 展示实际资料；全部 62 条参考均可在明确确认后创建独立的合成演练交易。只有匹配现有 Mock 规则的入口会自动确认规则并发布商户待办；原文参考、Amex、专项场景及其他未覆盖规则先建案，再由运营人工确认规则。来源快照与用户填写的演练交易字段分别保存，建案及后续阶段不继承参考案例的证据、决定、结果或未确认期限。

Agent 按当前卡组织、原因码检索指南参考，把 `REFERENCE_KNOWLEDGE` 与 `CASE_RULE_SNAPSHOT` 引用分开。新工具运行和每次对话保存真实检索记录；历史运行保持不变。现有六条 Mock fixture 继续服务 A–D Golden Demo，不代表参考库仅有六条。

案例库 provider 可通过同一检索接口替换，真实交易接入沿用独立的建案流程；旧案来源与规则快照不随新资料静默变化。现有 FastAPI 架构保留，未迁移到 Sites 的 JavaScript Workers，也未创建独立的 Figma 文件或公开站点。
