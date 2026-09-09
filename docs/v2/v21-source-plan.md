# OceanPilot V2.1 源码审查与修复推进计划

**审查对象：** `jiang4wqy/oceanpilot-evidenceos` / `oceanpilot-v2`  
**固定提交：** `759e3b321bea1a21f0ea85aae227f8f4389421e4`  
**资料口径：** 2026-09-07 企业会议、用户补充的企业回复截图、2026-09-08 推进说明／架构文件／拒付处理流程与验证。  
**任务范围：** 诊断与计划；本次未修改代码、创建分支／PR、合并 master、变更用户数据库或发送外部消息。

## 0. 审查结论与证据边界

建议不是重做一个 V3，而是做一次 **V2.1 服务流程修复**：保留已有案件内核，将两个独立授权的业务界面、同案共享沟通、内容级证据核查和完整异常出口接起来。

当前代码已经具备同一 case_id、商户范围过滤、双端独立案件 URL、自动同步、版本冲突拒绝、事务性命令幂等、包冻结和多维状态。因此不能说“完全没有关联”或“所有按钮都无效”。核心问题是身份由演示页面决定、完整内部数据直接返回、主会话语义不对、按钮与案件状态脱节、多个业务分支缺乏正确出口。

本报告依据固定提交的核心 API、领域模型、业务服务、持久化、Agent、前端及集成文档进行**静态源码审查与路径推演**，没有运行用户本地网页、完整测试套件或真实飞书租户。不能将本报告称作“所有运行时 Bug 已穷尽”或“逐按钮实测已通过”。仓库中 `1865 passed, 6 skipped` 是既有作者验收记录，不是本次重跑结果。布局溢出、浏览器报错、网络断线和并发时序仍须按第 7 节实测。

登记项使用三种证据口径：**源码确认**、**明确演示边界／产品缺口**、**结构风险／待实测**。同一项可能同时具有已确认实现行为与待确认生产适用性；不要把所有项统称为已复现故障。

## 1. 先修订业务合同，不照搬原方案的简化分支

### 1.1 以本次资料为基线

OP 是正式案件运营主体；商户负责决定与事实材料，OP 负责审核、授权提交、结果、资金和结案。OP 应看到授权案件中的商户材料与共享往来，而不应在普通操作中冒充商户。商户也不应获得 OP 内部草稿、内部审核操作或治理权限。

企业回复确认邮件或商户后台通知、邮件或后台收材料。飞书是新增协作适配器，不是企业现有唯一入口。企业精确支付角色、正式规则／SLA、接受授权和资金口径仍保持待确认，不能把会议举例中的期限泛化为全渠道规则。

### 1.2 原方案也需更正

原推进说明将较完整 Shared Case Thread 排在 P1，但老师在会议中明确将共同对话和 Agent 贯穿事项作为核心；本轮必须升为 P0。原架构流程图把最终确认否分支统一回补证、非终局统一新阶段，粒度不足。以用户补充的 HTML 中“核实／同阶段等待／确认新阶段”与明确的否决原因分流为准，不能只修代码而保留错误验收合同。

对于原本确实按私有范围保存的历史对话，迁移时不自动公开；新共享线程明确提示读者范围，重要历史内容经授权发布。

## 2. 目标产品：同一个案件，不同权限视图，共同推进

```text
可信登录身份 / 用户—商户—团队关系
                  |
           同一 Case Engine
                  |
       +----------+----------+
       |                     |
 MerchantCaseView      OperationsCaseView
 决定／材料／结果       审核／提交／结果／资金
       |                     |
       +--- Case Shared Thread ---+
             商户 · OP · OceanPilot
                         |
             OP_INTERNAL（独立权限）
```

不是给两端分别复制一份案件；不是每案建独立数据库；也不是任意跨端切换。可以继续共用后端聚合、基础组件和同步服务，但返回的数据、可用动作与沟通范围必须由服务端决定。

### 2.1 最小领域补充

- Case 保留 merchant_id、transaction/upstream link，补 assigned_op_user_id 和明确 Stage 身份。
- CaseParticipant 表达用户与案件关系；企业授权策略约束内部团队访问，不由前端自报 role。
- Task 保留 assignee、deadline、状态、原因、阶段和解决记录，不只是一条全局 OPEN 文案。
- Message 使用 SHARED／OP_INTERNAL，保留 actor_type、message_id、关联证据／任务、阅读及交付状态。
- Evidence 保留 object_id/hash/version、上传人、适用阶段与可见性；文件引用不等于已验证内容。
- Agent 读取授权上下文，产出 run／finding／proposal；高风险命令继续采用人工确认、当前版本校验与审计。

### 2.2 商户页面

商户首页只显示自己的待决定、待补材料、处理中和已结束案件。进入案件后首屏回答：为什么发生争议、金额多少、何时需要回应、目前由谁处理、我现在要做什么。

以“当前任务＋清单材料＋共享沟通”为中心。每个阶段一个主要操作：选择决定、继续材料、提交给 OP、查看补证要求或等待处理。Accept 后不再引导抗辩材料；送审后显示 OP 待办和最近反馈。结果提供可解释的资金摘要，而非向商户暴露全部内部账本。

移除 OP／治理／V1 跨端导航、正式建案、规则配置、初审／终审、上游提交和内部资金修改。普通消息不需要财务命令式大弹窗确认；高风险决定仍须明确确认。

### 2.3 OP 页面

列表按“我的待办／待分流／待商户／待风控／待主管／待上游／待资金／已结束”组织，显示实际处理人和下一步，而不只是堆状态枚举与所有按钮。详情聚焦本阶段的任务、共享沟通、证据和 AI 建议；内部审查、包与账务在相应工作阶段展开。

OP 可以查看并协助商户材料；代录邮件材料标明来源与代录人，代记商户决定必须留有效授权。支持阅读商户视图时，应是经过授权、明确标记的只读预览，不取得商户身份。主管应能直接退回终审，不靠切换成运营或商户绕开分工。

## 3. 缺陷与缺口登记表

以下共登记 42 项，不代表 42 个已运行复现的 Bug。P0 指本轮真实服务场景演示的前置项；P1 在核心路径修复后推进。每项源码位置以本次固定 SHA 为准。

| 编号 | 优先级 | 审查类型 | 问题 |
|---|---|---|---|
| A01 | P0 | 源码确认／演示设计边界 | 切换页面就切换业务身份 |
| A02 | P0 | 源码确认 | 商户接口返回完整案件聚合，缺少字段级投影 |
| A03 | P0 | 源码确认／产品缺口 | 固定演示商户与角色名代替真实参与者、负责人 |
| C01 | P0 | 源码确认／与反馈不一致 | 本端私有 AI 对话成了默认入口，共享沟通被放到另一页签 |
| C02 | P0 | 源码确认 | AI 上下文没有读取共享案件往来 |
| C03 | P0 | 源码确认／产品缺口 | 已读与人工升级没有完整状态闭环 |
| C04 | P1 | 源码确认 | 商户沟通页将所有非商户消息标为 OceanPayment |
| W01 | P0 | 源码确认 | NO_RESPONSE 后没有同阶段恢复抗辩或接受的正规出口 |
| W02 | P0 | 源码确认 | 可能把已响应的 CONTEST 覆盖成 NO_RESPONSE |
| W03 | P0 | 源码确认 | 审核建议接受被当成退回补证 |
| W04 | P0 | 源码确认／合同缺口 | 最终审核只有批准，没有否决／退回／暂缓 |
| W05 | P0 | 源码确认 | 所有已知非终局结果都强制进入新阶段 |
| W06 | P0 | 源码确认 | OTHER 可以直接被标为终局并通过关闭门槛 |
| W07 | P0 | 源码确认 | 撤回／结果事件只能在 WAITING_UPSTREAM 状态登记 |
| W08 | P1 | 源码确认／合同缺口 | 终局后更正与关闭后重开没有正规路径 |
| W09 | P0 | 源码确认 | 规则变化后没有重新验证既有抗辩资格 |
| W10 | P0 | 源码确认 | 后续阶段期限从操作当下 now 重新起算 |
| W11 | P1 | 源码确认／业务适用性待确认 | 新阶段沿用活跃材料和上一阶段结果，缺少明确适用性判定 |
| W12 | P0 | 源码确认／集成合同缺口 | 接受责任后缺少渠道接受／不抗辩处理回执 |
| W13 | P1 | 源码确认 | 完成结果／改变决定时批量将所有开放任务标记完成 |
| W14 | P1 | 源码确认 | 仅允许接受责任的规则也强制非空举证清单 |
| U01 | P0 | 源码确认 | 操作按钮大多按角色显示而非案件可执行条件 |
| U02 | P0 | 源码确认 | 商户手动决定入口不按当前规则过滤 Accept／Contest |
| U03 | P0 | 源码确认 | 历史通知导致关闭检查错误显示已通知 |
| U04 | P1 | 源码确认 | 待终审阶段的进度条可能回到第一步 |
| U05 | P1 | 源码确认 | 失效的审核记录仍显示普通通过 |
| U06 | P1 | 源码确认 | 必要任务复选框没有实际控制效果 |
| U07 | P0 | 源码确认 | 结果表单默认 OTHER，却无法选择 UNKNOWN |
| U08 | P1 | 源码确认 | 表单、HTTP DTO 与领域层验证不一致 |
| U09 | P1 | 源码确认 | 不存在或无权访问的案件可能继续显示正在读取 |
| U10 | P1 | 源码确认 | 已审核知识候选仍显示人工审核按钮 |
| I01 | P0 | 源码确认／声明中的功能边界 | 没有时间驱动的主动 SLA 工作，且同版本运行被复用 |
| I02 | P0 | 源码确认 | SLA 风险主要看商户期限，不看当前真正待办 |
| I03 | P0 | 现有明确演示边界／核心能力缺口 | 材料只有元数据，没有文件内容与内容级 AI 核查 |
| I04 | P1 | 源码路径缺口／需联调验收 | 知识候选获批不等于已进入实际 Agent 检索 |
| I05 | P1 | 源码确认／审计缺口 | 编辑 AI 提案后，实际命令没有保留明确的提案来源链接 |
| I06 | P1 | 源码确认 | 正常早期案件也显示不能结案等全生命周期阻断 |
| X01 | P0 | 现有明确演示边界／集成缺口 | Feishu 只有入站回调，不是可用的双向协作 |
| X02 | P1 | 源码确认／接入边界缺口 | 接收上游事件目前基本等于人工创建正式拒付 |
| X03 | P1 | 现有明确演示边界／测试缺口 | Mock 提交只覆盖立即送达并受理 |
| F01 | P1 | 源码确认／业务信息缺口 | 部分胜诉与商户实际资金影响表达不足 |
| E01 | P1 | 源码确认结构／性能需实测 | 更新时重复读取全量案件与完整快照 |

### A01 · 切换页面就切换业务身份

**级别／证据：** P0 · 源码确认／演示设计边界  
**定位：** [SHELL](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/shell.html)；[WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)

**源码行为：** SHELL 的三个跨端入口始终存在；WEB.initialize 根据 surface 选择 MERCHANT、OPERATOR 或 ADMIN；API.v2_identity 信任 X-Demo-* 请求头，HTML 页面路由不依赖登录身份。

**影响：** 商户点击运营或治理入口，不是向服务端申请权限，而是进入会自行使用对应演示身份的页面。不能把这种浏览器演示控制当成商户登录后的权限隔离。仓库已声明非生产认证，本项不表示已发生真实数据泄露。

**修复目标：** 将演示导演台移到独立入口；商户和 OP 使用服务端确定的独立会话。页面 URL、请求体和客户端角色头不能授予权限。企业 SSO 可后续接入，但基本可信身份和对象级授权是本轮前置条件。

**验收场景：** 以商户会话访问运营／治理页面和命令接口，不得升级身份；修改客户端角色、直接访问 URL 均无效。

### A02 · 商户接口返回完整案件聚合，缺少字段级投影

**级别／证据：** P0 · 源码确认  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[STORE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/adapters/persistence/disputes.py)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)

**源码行为：** SERVICE.get_case 只校验 merchant_id 后返回整个 case；list_cases 返回完整存储快照；STORE.execute_atomic 的命令回执也带完整 case。

**影响：** 已有本商户范围校验，但本案内部审核、包草稿、审计和内部资金引用等字段仍可能下发给商户浏览器。隐藏标签页不等于没有发送内部数据。

**修复目标：** 定义 MerchantCaseView、OperationsCaseView 和队列摘要；在服务端按字段白名单投影。统一覆盖列表、详情、命令回执、计划、AI 活动、更新流以及未来的附件／导出。内部共用聚合可以保留。

**验收场景：** 自动断言商户的所有响应中不含内部字段；商户 A 不能读取商户 B 的案件、消息、材料或 AI 记录。

### A03 · 固定演示商户与角色名代替真实参与者、负责人

**级别／证据：** P0 · 源码确认／产品缺口  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[DOMAIN](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute.py)

**源码行为：** WEB 固定 synthetic-merchant-001；actor 由角色拼接。SERVICE case.owner 是 OCEANPAYMENT；_task 没有具体 assignee、任务截止时间和接手状态。

**影响：** 已有 case_id 和 merchant_id，但尚不能完整表达“这个商户用户与哪位 OP 专员协作、谁等待谁、谁负责处理升级”。

**修复目标：** 增加用户—商户—案件参与关系、OP 负责人、风控／主管任务分配与任务到期时间；至少用两个商户、两个运营人员和独立审核人演练。OP 是否能跨团队查看全部案件由企业授权策略决定，不猜测。

**验收场景：** 同商户多用户、不同商户及不同 OP 处理人并行操作，任务能明确归属和交接。

### C01 · 本端私有 AI 对话成了默认入口，共享沟通被放到另一页签

**级别／证据：** P0 · 源码确认／与反馈不一致  
**定位：** [AGENT](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/dispute_agent.py)；[WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[MIGRATION](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/docs/v2/architecture-and-migration.md)

**源码行为：** AGENT.get_activity 和 converse 按 MERCHANT／OPERATIONS 分开保存与读取 conversations；WEB 单独渲染 collaboration 标签页。

**影响：** 不是没有同案同步，而是老师要求的共同协作语义没有成为主交互。商户对 AI 的案件提问默认不进入 OP 可见的公共往来。

**修复目标：** 以一个 Case Shared Thread 作为主会话；商户案件咨询、OP 回复与 AI 协助在同一线程。OP 内部备忘、策略讨论和未发布草稿保留 OP_INTERNAL。旧私有记录不追溯性自动公开，需明确迁移／发布策略。

**验收场景：** 商户提问、AI 回答、OP 接手和退回补证，在另一独立会话自动出现且来源清楚；OP_INTERNAL 不向商户泄露。

### C02 · AI 上下文没有读取共享案件往来

**级别／证据：** P0 · 源码确认  
**定位：** [AGENT](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/dispute_agent.py)

**源码行为：** AGENT._minimal_context 包含本端 conversation_history、规则、材料清单、任务和 latest_review_feedback，但没有 case.collaboration。

**影响：** OP 在共享沟通里补充的重要说明，不能直接成为下一次模型解释的输入；这与贯穿双方对话的协作目标不符。

**修复目标：** 将经权限过滤的共享消息、关联材料和最新人工作业结论纳入上下文，保留 message_id 与引用；内部消息只在内部上下文可用。避免简单拼接全部历史。

**验收场景：** OP 在共享线程明确要求某个补充事实，商户随后追问时 AI 能引用该消息，不重新给泛化清单。

### C03 · 已读与人工升级没有完整状态闭环

**级别／证据：** P0 · 源码确认／产品缺口  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)；[DOMAIN](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute.py)

**源码行为：** SERVICE._collaboration 将 read_status 固定为 UNREAD；已读更新、接手和解决升级事项未出现在当前命令合同中。

**影响：** 无法可靠呈现谁看到了、谁接手了、何时答复；“人工升级”容易只剩文字提示。

**修复目标：** 增加按参与者的阅读游标、交付状态及 HumanHandoff 任务，记录负责人、创建原因、接手时间、下次跟进时间与解决结论。阅读动作不应使业务审批版本失效。

**验收场景：** AI 遇到未知规则创建可追踪任务；指定 OP 接手、回复、解决后状态同步；已读不能凭发出消息推定。

### C04 · 商户沟通页将所有非商户消息标为 OceanPayment

**级别／证据：** P1 · 源码确认  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)

**源码行为：** WEB.renderMerchantFeedbackPage 只判断是否 MERCHANT，其余均显示 OceanPayment；latestCaseFeedback 也只排除 MERCHANT。

**影响：** Agent／系统消息可能被误看成 OP 真人承诺，弱化可信来源和人机责任边界。

**修复目标：** 统一 actor_type 与显示规则，区分商户、OP 真人、OceanPilot 和系统事件；草稿、建议、确认、已执行用不同标签。

**验收场景：** 同一线程至少显示四类来源；AI 输出不能冒充人工审核结论。

### W01 · NO_RESPONSE 后没有同阶段恢复抗辩或接受的正规出口

**级别／证据：** P0 · 源码确认  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[RULE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute_rules.py)

**源码行为：** SERVICE._on_merchant_decision 记录 NO_RESPONSE 后进入 WAITING_UPSTREAM；同函数只允许 MERCHANT_ACTION_REQUIRED／EVIDENCE_COLLECTING／MERCHANT_REVISION_REQUIRED 接受下一次决定。

**影响：** 商户迟到但仍有外部处理权利时，不能通过现有决定命令恢复；计划仍引导记录上游结果。

**修复目标：** 增加核实剩余权利与恢复处理动作，允许经确认恢复决定／举证、授权接受、确认失权或继续跟进；不靠制造结果或新阶段解锁。

**验收场景：** 商户目标过期但外部期限未过，NO_RESPONSE 后可经授权恢复 CONTEST；无需虚构上游事件。

### W02 · 可能把已响应的 CONTEST 覆盖成 NO_RESPONSE

**级别／证据：** P0 · 源码确认  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** 同一决定命令允许 EVIDENCE_COLLECTING 状态；NO_RESPONSE 只检查商户截止时间已过，未要求之前没有有效决定。

**影响：** “没有作出决定”与“已抗辩但材料迟交”被混为一谈，会错误改写商户立场。

**修复目标：** 分别定义 decision_response_status 与 evidence_task_status。已有有效决定时禁止按未响应覆盖，保留历史与真实超时任务类型。

**验收场景：** 商户早已选择 CONTEST、后续材料迟交，只触发材料超时／升级，不改变 merchant_decision。

### W03 · 审核建议接受被当成退回补证

**级别／证据：** P0 · 源码确认  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)

**源码行为：** SERVICE._on_review 中 REVISION 和 ACCEPT 走相同 MERCHANT_REVISION_REQUIRED／REVISION 路径；WEB 新商户反馈展示只专门匹配 REVISION 审核记录。

**影响：** 商户收到“需要补充材料”，而不是“请确认是否接受责任”。

**修复目标：** 分开 RequestRevision 和 RecommendAccept；后者创建决定确认任务，显示理由和责任信息，不自动替商户接受，也不强制补证。

**验收场景：** 风控建议接受后，商户可查看明确建议并授权接受，或在允许范围继续抗辩；没有虚假的补证要求。

### W04 · 最终审核只有批准，没有否决／退回／暂缓

**级别／证据：** P0 · 源码确认／合同缺口  
**定位：** [API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[DOMAIN](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute.py)；[WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)

**源码行为：** API.ApprovalData 与 SERVICE._on_approve_package 只有批准并冻结；SUPERVISOR 没有修改证据或初审权限可充当规范退回出口。

**影响：** 主管发现问题不能通过自己的正式职责完成退回。换角色改材料不是业务解决方案。

**修复目标：** 新增 FinalReviewDecision：批准、退回材料、退回文书、建议接受、暂缓／升级。每条分支明确责任人、包版本失效与时限处理。

**验收场景：** 主管从待终审状态直接退回文书，OP 修改后产生新包并重新终审；不能绕过双人审核。

### W05 · 所有已知非终局结果都强制进入新阶段

**级别／证据：** P0 · 源码确认  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)

**源码行为：** SERVICE._on_record_outcome 对非 UNKNOWN 且 final=false 的结果设置 pending_next_stage 并进入 TRIAGED，即使前端选择暂不创建后续阶段。

**影响：** 无法表示同阶段继续等待、无需行动或尚待明确下一步的非终局事件。

**修复目标：** 将 outcome、finality、action_required、next_stage 分开；只有经确认的新阶段事件才创建新 Stage。保留 WAITING_UPSTREAM 和 NEEDS_CONFIRMATION。

**验收场景：** 一次非终局已知事件可以保持当前阶段等待；实际新阶段事件才生成阶段与新期限。

### W06 · OTHER 可以直接被标为终局并通过关闭门槛

**级别／证据：** P0 · 源码确认  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[DOMAIN](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute.py)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)

**源码行为：** SERVICE 只禁止 UNKNOWN+final=true；DOMAIN.close_blockers 也只额外排除 UNKNOWN，没有要求 OTHER 的含义映射和终局证明。

**影响：** 未解释的其他结果可被一个复选框推进财务和关闭，与反馈中“OTHER 不默认关闭”不一致。

**修复目标：** UNKNOWN／未映射 OTHER 保持待核实；确有其他终局类型时，先形成明确映射、终局依据和授权确认，再评估关闭条件。

**验收场景：** OTHER+final=true 但无可识别终局依据被拒绝；有正式映射的自定义结果按其合同处理。

### W07 · 撤回／结果事件只能在 WAITING_UPSTREAM 状态登记

**级别／证据：** P0 · 源码确认  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)

**源码行为：** SERVICE._on_record_outcome 开头限制 work_status 必须为 WAITING_UPSTREAM。

**影响：** 上游在材料收集、审核等时点发来的正式撤回或更正无法按实际到达时点处理。

**修复目标：** 增加标准化上游事件处理器；验证事件来源、案件／阶段关联与覆盖关系，独立于当前 UI 操作页签处理合法异步事件。停止或取消被新事件取代的任务并留痕。

**验收场景：** 材料收集中到达有效撤回，无须先假提交；可核验并走终局／资金或待核实分支。

### W08 · 终局后更正与关闭后重开没有正规路径

**级别／证据：** P1 · 源码确认／合同缺口  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[DOMAIN](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute.py)

**源码行为：** SERVICE._apply 禁止 CLOSED 后大多数业务命令；结果登记仅 WAITING_UPSTREAM；没有 Reopen 或关联后续案件合同。

**影响：** 有效更正、迟到资金事件或结案争议缺少处理方式，原 HTML 已要求核验重开或关联后续案件。

**修复目标：** 引入授权更正／重开，保留原终局、通知与结案历史；也可创建与原案关联的后续案件。是否重开由事件类型和企业政策决定。

**验收场景：** 已关闭案件收到有效更正后可留痕处理，不能直接改数据库或删除原结案记录。

### W09 · 规则变化后没有重新验证既有抗辩资格

**级别／证据：** P0 · 源码确认  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** CONFIRM_RULE 可在举证／初审时改变 allowed_actions，并保留 merchant_decision=CONTEST；后续 SUBMIT_EVIDENCE／REVIEW／BUILD_PACKAGE／SUBMIT 仅检查规则就绪等，不重新要求 CONTEST 在允许动作内。

**影响：** 当新规则只允许 ACCEPT，旧的 CONTEST 仍有继续走向提交的源码路径。

**修复目标：** 集中验证 eligibility；规则改变后重新评估决定、任务、清单与包，必要时进入权利待核实。高风险动作执行时重新检查当前资格，而非只在商户第一次选择时检查。

**验收场景：** 先 CONTEST，再把规则改成仅 ACCEPT，系统阻止继续抗辩提交并生成重新确认任务。

### W10 · 后续阶段期限从操作当下 now 重新起算

**级别／证据：** P0 · 源码确认  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)；[RULE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute_rules.py)

**源码行为：** SERVICE._advance_stage 调用 rule_matcher(..., now)；StageData／OutcomeData 没有源事件 occurred_at／received_at 或明确渠道截止字段。

**影响：** 迟到录入同一上游阶段时，演示期限会被向后移动；不能表达真实事件起算与收到通知之间的差异。

**修复目标：** 保留事件发生时间、OP 实际收到时间、渠道给定截止时间和时区；按该规则选定的起算依据计算，内部操作时间只做审计。未知时限进入待确认。

**验收场景：** 同一事件立即录入与延迟一天录入，正式外部截止一致；不得因建阶段动作产生新权利。

### W11 · 新阶段沿用活跃材料和上一阶段结果，缺少明确适用性判定

**级别／证据：** P1 · 源码确认／业务适用性待确认  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[RULE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute_rules.py)

**源码行为：** SERVICE._advance_stage 保存历史，但不清空当前 evidence 或 business_outcome；RULE.case_plan 按所有 active evidence 的 code 判断齐全。

**影响：** 界面可能把上一阶段结果当当前结果；旧材料只要同代码就计入新阶段准备度。材料允许复用，但不能默认所有材料跨阶段有效。

**修复目标：** 明确 current_stage_outcome 与 last_known_outcome；材料增加阶段适用性与复用批准记录，历史快照只读。重用材料时验证是否支持当前抗辩点。

**验收场景：** 进入新阶段显示当前结果待确认；旧材料经确认适用才贡献准备度，历史仍可查。

### W12 · 接受责任后缺少渠道接受／不抗辩处理回执

**级别／证据：** P0 · 源码确认／集成合同缺口  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)

**源码行为：** SERVICE._on_merchant_decision 对 ACCEPT／AUTHORIZED_WAIVER 直接转 WAITING_UPSTREAM；没有单独的渠道接受处理任务／确认记录。

**影响：** 商户决定已经有记录，但“按渠道执行接受或不抗辩”这个业务步骤没有充分建模。不能凭决定就推断已退款或已承担最终金额。

**修复目标：** 增加接受处理任务与明确 Mock 回执：授权、责任金额、已有退款／扣回核查、渠道动作或无需动作的规则依据。仍由上游／确认规则决定终局。

**验收场景：** Accept 后不补证、不自动二次退款；有授权与渠道处理记录，资金与终局仍分别验证。

### W13 · 完成结果／改变决定时批量将所有开放任务标记完成

**级别／证据：** P1 · 源码确认  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** SERVICE._complete_tasks(types=None) 被商户决定及已知结果等路径调用，统一将 OPEN 改 COMPLETED。

**影响：** 作废、被替代、无需处理与真正执行完成没有区分，可能掩盖未解决升级事项。

**修复目标：** 任务使用 COMPLETED／CANCELLED／SUPERSEDED／WAIVED 等明确语义，按任务类型和事件影响处理，并记录操作者、原因与关联版本。

**验收场景：** 结果到达取消不再需要的补证任务时显示取消而不是已提交；独立未解决事项不会被无依据抹平。

### W14 · 仅允许接受责任的规则也强制非空举证清单

**级别／证据：** P1 · 源码确认  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)

**源码行为：** SERVICE._on_confirm_rule 无条件要求 required_evidence 是非空列表。

**影响：** 即使 allowed_actions 只有 ACCEPT，也需要编造抗辩证据要求才能完成规则确认。

**修复目标：** 根据支持动作和阶段验证材料要求；接受授权信息与抗辩证据清单分别建模。

**验收场景：** 仅可接受的已确认规则允许没有抗辩证据项，但接受授权所需字段仍必填。

### U01 · 操作按钮大多按角色显示而非案件可执行条件

**级别／证据：** P0 · 源码确认  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** WEB.actionButton／permitted 主要读取角色 action 列表；review、outcome、operations evidence 等页签大量按钮未传 disabled 状态。

**影响：** 提前建包、无包终审、未冻结提交、非终局核对、未满足条件关闭等操作都可能先让用户打开表单，最后由后端 409 拒绝。不是普遍没绑定事件，而是缺少可执行状态。

**修复目标：** 由服务端提供每案 available_actions：visible／enabled／blocked_reason／owner／required_fields／revision。前端从它渲染，不复制一套业务状态机；后端执行仍重新校验。

**验收场景：** 所有可见启用按钮在对应角色、合法有效输入与当前版本下可执行；不可执行的按钮隐藏、禁用说明或转交负责人。

### U02 · 商户手动决定入口不按当前规则过滤 Accept／Contest

**级别／证据：** P0 · 源码确认  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[AGENT](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/dispute_agent.py)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** WEB.renderMerchantOverviewPage 和 commandFields 的 MERCHANT_DECISION 固定给出两项选择，未读取 allowed_actions；Agent 提案反而有按规则过滤。

**影响：** 同一案件的手动 UI 与 Agent 推荐不一致；用户可以选到后端必拒绝的决定。

**修复目标：** 共用服务端动作合同，展示实际可选决定及不允许的理由；不把未知权利当两项都可用。

**验收场景：** 仅 ACCEPT、仅 CONTEST、未知规则三种情况的手动入口与 Agent 提案一致。

### U03 · 历史通知导致关闭检查错误显示已通知

**级别／证据：** P0 · 源码确认  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[DOMAIN](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute.py)

**源码行为：** WEB.renderOutcome 在当前 merchant_notification_completed=false 时仍可因历史 collaboration 通知记录而设 notified=true；SERVICE 对新资金和重新核对会重置标志。

**影响：** 页面四项看似满足，后端却拒绝关闭。底层关闭闸门仍在工作，但 UI 与服务器状态矛盾。

**修复目标：** 通知完成基于当前结果／资金版本的有效 delivery 记录；前端直接展示服务端 close_gate，不从历史消息重新推断。

**验收场景：** 通知后再新增资金事件，界面立即显示需重新通知；完成新版本通知才恢复绿色。

### U04 · 待终审阶段的进度条可能回到第一步

**级别／证据：** P1 · 源码确认  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)

**源码行为：** WEB.renderOverview 的生命周期位置计算没有涵盖 SUBMISSION_PENDING_CONFIRMATION，该状态落入默认 pos=0。

**影响：** 刚生成包等待终审，却显示回到接收分流，强化流程混乱感。

**修复目标：** 进度展示按真实分支和阶段映射，不能把接受、异常、新阶段强行套一条线性进度。

**验收场景：** 从初审通过到建包待终审进度不倒退；Accept 不显示已经完成抗辩材料审核。

### U05 · 失效的审核记录仍显示普通通过

**级别／证据：** P1 · 源码确认  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** SERVICE._invalidate 将旧 review.valid=false；WEB.renderReview 只显示 decision／reviewer／时间，没有展示有效性和失效原因。

**影响：** 旧 PASS 与当前有效通过容易混淆，用户不知道为何需要重新审核。

**修复目标：** 显式标明当前有效／历史已失效、证据版本、失效事件，优先显示当前待办审核。

**验收场景：** 已通过后材料变更，原记录明确显示失效且说明原因，不能继续暗示可提交。

### U06 · 必要任务复选框没有实际控制效果

**级别／证据：** P1 · 源码确认  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** WEB.PUBLISH_TASK 的 required 是默认必选 checkbox；SERVICE._task 始终 required=True，没有消费请求中的 required 值。

**影响：** 这是具体的无效配置项：表面有选项，实际不能有意义地改变结果。

**修复目标：** 确认是否需要可选任务；需要则贯通字段和关闭闸门，不需要则删除复选框，写清该任务必需。

**验收场景：** 用户可见的配置都真实影响数据／行为；不存在可更改但被静默忽略的字段。

### U07 · 结果表单默认 OTHER，却无法选择 UNKNOWN

**级别／证据：** P0 · 源码确认  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** WEB.RECORD_OUTCOME choices 不含 UNKNOWN，默认 OTHER；API.OutcomeData 支持 UNKNOWN。NEXT_STAGE 表单也固定默认 REPRESENTMENT，未排除当前或倒退阶段。

**影响：** 用户难以正确记录结果不明；默认值引导走 OTHER 或非法阶段，和后端合同不一致。

**修复目标：** 结果不明为明确选项；结果／终局必须依据事件，不默认成功或其他终局。阶段选项依据当前阶段和适用动作生成。

**验收场景：** UNKNOWN 可持续核实且不关闭；当前 REPRESENTMENT 不默认再次选择同阶段。

### U08 · 表单、HTTP DTO 与领域层验证不一致

**级别／证据：** P1 · 源码确认  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** WEB 普通 textarea 上限 4000，很多 DTO 字段上限 1000／2000；OP 决定的 authorization_reference 在表单可选但域层有条件必填。OutcomeData.reason 默认空字符串，而领域在字段出现时要求非空。

**影响：** 用户按页面合法输入仍可能被拒绝；遗漏本应可选的 API 字段反而产生 422。

**修复目标：** 统一字段合同、条件必填、长度和本地校验，明确短缺字段而非笼统失败；编写 DTO—form—domain 一致性测试。

**验收场景：** 边界长度、空值和授权条件在前后端一致，错误定位到具体输入项。

### U09 · 不存在或无权访问的案件可能继续显示正在读取

**级别／证据：** P1 · 源码确认  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)

**源码行为：** WEB.openCase 出错后清空 current 并调用 renderDetail；renderDetail 对空 current 渲染正在读取。

**影响：** 虽然有全局错误提示，主界面仍像永远加载中。

**修复目标：** 显式区分 LOADING／NOT_FOUND_OR_FORBIDDEN／RETRYABLE_ERROR／EMPTY；拒绝跨商户请求时不泄露案件存在性。

**验收场景：** 不存在／无权案件显示结束态和返回入口；断网显示重试，不留无限加载文案。

### U10 · 已审核知识候选仍显示人工审核按钮

**级别／证据：** P1 · 源码确认  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** WEB.renderGovernance 只检查 APPROVE_KNOWLEDGE 权限，不检查候选是否 PENDING_REVIEW；SERVICE 拒绝再次审核。

**影响：** 已批准／已驳回候选仍可进入必然失败的审核操作。

**修复目标：** 候选按状态展示只读结论或待审核动作；重新评审必须是新的、明确的流程。

**验收场景：** 已审核项只有查看记录，不能误点再次审核；重新提交候选保留历史版本。

### I01 · 没有时间驱动的主动 SLA 工作，且同版本运行被复用

**级别／证据：** P0 · 源码确认／声明中的功能边界  
**定位：** [AGENT](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/dispute_agent.py)；[AGENT-DOC](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/docs/v2/agent-workflow.md)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** AGENT.observe 对同 case_revision 返回既有 run；AGENT-DOC 明确没有后台周期监控／自动商户发送。

**影响：** 无人改案时，时间流逝不会产生新的持久化监测任务或主动提醒；点击重新分析也不会重写该版本工具运行。

**修复目标：** 将 time_tick／deadline_due 作为独立调度触发，运行记录绑定观察时间，不只绑定业务 revision；幂等键采用案件＋阶段＋截止类型＋提醒档位。业务版本与消息／观察游标分开。

**验收场景：** 不更改任何案件字段、只推进测试时钟，仍能按期提醒和升级；重复扫描不重复轰炸。

### I02 · SLA 风险主要看商户期限，不看当前真正待办

**级别／证据：** P0 · 源码确认  
**定位：** [RULE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute_rules.py)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[AGENT](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/dispute_agent.py)

**源码行为：** RULE.case_plan 和 SERVICE._on_monitor_sla 主要使用 merchant deadline；plan/findings 没有充分按已提交、已接受、已关闭状态排除商户催办。

**影响：** OP 审核／外部提交风险没有被分别驱动，商户已经完成工作仍可能出现超时提示。

**修复目标：** 把 merchant／internal／external 三类截止绑定阶段与任务责任人；等待上游增加复查时间；已完成任务不再催办，正式失权不能由内部超时推断。

**验收场景：** 商户及时提交后仅 OP 任务到期报警；关闭后没有材料催办；外部超期转权利核实。

### I03 · 材料只有元数据，没有文件内容与内容级 AI 核查

**级别／证据：** P0 · 现有明确演示边界／核心能力缺口  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[DOMAIN](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute.py)；[README](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/README.md)

**源码行为：** REGISTER_EVIDENCE 登记 code/title/reference/notes，content_verified=False；missing_evidence 基于 active code；README 明确未上传或解析正文。

**影响：** 当前完整度是登记清单，不是文件可用性、交易关联或事实一致性；并非一个已实现上传按钮坏掉，而是功能尚未实现。

**修复目标：** 本轮至少支持少量可控类型的合成材料真实上传、对象存储、hash／版本、预览；优先文本型 PDF／文本／结构化样例。AI 输出事实与材料位置、缺口和冲突。扫描件 OCR、全格式识别可延期。

**验收场景：** 同类型两份材料因内容不同得到不同检查结果；空文件／无关文件／重复文件不能仅凭 code 算完成。

### I04 · 知识候选获批不等于已进入实际 Agent 检索

**级别／证据：** P1 · 源码路径缺口／需联调验收  
**定位：** [API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)；[AGENT](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/dispute_agent.py)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** API.plan 会附加批准候选；AGENT.observe 使用 domain.case_plan，_similar_cases 返回同商户案件元信息，_retrieve_knowledge 使用参考案例 provider；已读路径未见获批模式进入模型上下文。

**影响：** 治理页面存在知识审批，但后续案件是否真正用上获批经验尚不能由界面或 README 保证。

**修复目标：** 统一知识检索接口，显式纳入已脱敏且获批的案例模式，按范围、阶段、规则版本检索；带知识来源和批准版本，不自动改变正式规则。

**验收场景：** 案件 A 结案并获批一个特定模式，案件 B 检索到该知识 ID 并引用；未批准候选不可命中。

### I05 · 编辑 AI 提案后，实际命令没有保留明确的提案来源链接

**级别／证据：** P1 · 源码确认／审计缺口  
**定位：** [WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** WEB.submitDialog 在用户编辑提案内容时改走普通 /commands；当前 DisputeCommand 和审计事件没有 origin_proposal_id／agent_run_id／human_diff。

**影响：** 能知道执行过命令，但难以证明哪部分由 AI 准备、哪部分由人修改及确认。

**修复目标：** 增加可信关联元数据并由服务端校验提案所属案件、版本与作用域；保存人类修改摘要，不把客户端传来的任意 ID 当可信证据。

**验收场景：** 点击 AI 提案并修改文案后，审计能追溯原 run、proposal、实际 payload 及确认人。

### I06 · 正常早期案件也显示不能结案等全生命周期阻断

**级别／证据：** P1 · 源码确认  
**定位：** [RULE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute_rules.py)；[WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)

**源码行为：** RULE.case_plan 对所有非终局案添加终局未确认不能结案；WEB 把 blockers 用作当前案件推进建议的警示。

**影响：** “当前不能关闭”被误读为“当前无法推进”，大量正常信息占据注意力。

**修复目标：** 区分 current_action_blockers、future_close_gates 与风险提醒。主界面只显示阻挡当前下一步的原因，其余在相应阶段展开。

**验收场景：** 新案件能正常发布任务时，不以终局／资金未完成为当前阻断；临近关闭时才展示关闭清单。

### X01 · Feishu 只有入站回调，不是可用的双向协作

**级别／证据：** P0 · 现有明确演示边界／集成缺口  
**定位：** [FEISHU](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/docs/v2/feishu.md)；[API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)；[README](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/README.md)

**源码行为：** FEISHU 文档明确 outbound Disabled；@OceanPilot 返回 case_plan 到 HTTP callback JSON，并未调用飞书发消息 API。Email 在治理接口为 PORT_DEFINED_ONLY。

**影响：** 不能把本地 callback 成功等同于商户真的收到了卡片或机器人回答；也没有真实邮件协作闭环。

**修复目标：** 比赛优先打通一个经授权的测试飞书空间：发卡、正确 thread/case 关联、回调权限、回复／更新、状态回执、重试。Email 先保留明确 mock／人工导入，不能假装已接企业邮箱。

**验收场景：** 真实测试群可见新案卡片，点击／提问后案件更新且群里收到回答；不发送给真实业务商户。

### X02 · 接收上游事件目前基本等于人工创建正式拒付

**级别／证据：** P1 · 源码确认／接入边界缺口  
**定位：** [API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** API.IntakeData 没有明确 event_type；SERVICE._intake 总是 FORMAL_DISPUTE；交易／商户关系由输入字段提供，没有真实交易查询核验。

**影响：** 不能完整区分预警、查询、正式拒付、阶段更新与资金事件，也不能凭表单声称已保证只处理 OP 自身业务。

**修复目标：** 先建立标准事件信封与本地 synthetic registry 校验；真实来源适配器后接。未知／无法关联事件进待核实，不误建正式案。

**验收场景：** 查询／预警不生成正式拒付；重复事件不重复建案；商户与交易不匹配进入隔离审核。

### X03 · Mock 提交只覆盖立即送达并受理

**级别／证据：** P1 · 现有明确演示边界／测试缺口  
**定位：** [SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)；[README](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/README.md)

**源码行为：** SERVICE._on_submit 直接记录 DELIVERED／MOCK_ACCEPTED 并进入 WAITING_UPSTREAM，未见拒收／受理不明／查询回执等操作分支。

**影响：** 现有命令级幂等很好，但不能据此声称已覆盖外部渠道不确定提交语义。

**修复目标：** 扩展 Mock 故障情景：技术失败、业务拒收、回执超时、已受理但响应丢失；先查询再决定允许重提，不因网络超时重复发送。

**验收场景：** 模拟响应丢失后复用同一业务请求身份，确认已受理时不重提；未受理且仍有权利才重试。

### F01 · 部分胜诉与商户实际资金影响表达不足

**级别／证据：** P1 · 源码确认／业务信息缺口  
**定位：** [API](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)；[WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)；[SERVICE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)

**源码行为：** OutcomeData 只有 outcome／final 等，没有支持金额、责任金额或部分裁定结构；merchant result 页主要展示争议金额和资金状态，缺少可理解的资金摘要。

**影响：** PARTIAL 是标签而非可解释业务结果；商户不知道最终承担或返还多少。

**修复目标：** 在企业确认口径前，明确用 synthetic 金额维度演示 disputed／supported／liable／fee／refund／net，保留币种和原始事件依据；不要让人手填一个净值就宣称完成真实账务对账。

**验收场景：** 部分支持场景能解释争议额与责任额之差；费用、退款及扣回不会混淆或重复计入。

### E01 · 更新时重复读取全量案件与完整快照

**级别／证据：** P1 · 源码确认结构／性能需实测  
**定位：** [STORE](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/adapters/persistence/disputes.py)；[WEB](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)

**源码行为：** STORE.list_cases 返回全部 JSON 聚合；WEB.reconcileUpdates 在更新后重新 GET /cases；command receipts 也保存完整 snapshot。

**影响：** 随着案件、证据、消息、审计增多，读写放大和响应体增长明显。这里是源码可见扩展性风险，不是已经测得具体延迟。

**修复目标：** 列表使用权限过滤后的分页摘要，详情独立查询，消息增量更新，业务快照／日志适度拆分；优化前后用固定 synthetic 数据规模基准比较。

**验收场景：** 验证分页与跨商户过滤正确，测量数据量增长时响应体、P95 延迟和 SQLite 锁等待，报告实测而非预设提升倍数。

## 4. 按钮与动作合同：不要让用户靠 409 学习工作流

每个交互都登记：页面、身份、案件阶段／状态、显示条件、启用条件、业务命令、字段合同、成功后的双端状态、失败后出口、是否留审计。按钮点击事件绑定成功不等于业务可用。

| 操作 | 正确出现／启用条件 | 成功后的可观察结果 | 必须避免 |
|---|---|---|---|
| 接收上游事件 | 已认证且授权的 OP；有效来源与交易关联 | 建案或归入既有案，生成处理建议 | 商户建正式案、预警误建正式拒付 |
| 发布商户任务 | 规则／权利／期限已确认，任务内容经核对 | 商户收到同案任务与截止时间 | 无清单先推送、重复通知生成重复任务 |
| 接受责任 | 当前允许 Accept，用户有授权 | 记录决定与授权，进入接受处理，不强制补证 | 自动退款、立即结案 |
| 提出抗辩 | 当前具备资格且有有效授权 | 生成当前阶段材料任务 | 权利未知仍默认可选、改规则后沿用旧资格 |
| 上传／补充材料 | Contest 且任务允许修改 | 可预览文件及版本；AI 内容检查；状态同步 | 仅填代码算真实文件已齐 |
| 修订／撤回材料 | 允许修改且有权限；已送审／冻结时走显式修订 | 旧审核／包失效并明确安排重新审核 | 静默覆盖冻结提交版本 |
| 提交材料给 OP | 必需内容满足当前规则，或有明确批准的例外合同 | 当前版本进入 OP 审核队列 | 重复送审；把材料登记等同上游提交 |
| 初审通过 | 当前待审核，授权风控已查看材料 | 创建建包待办，留审核依据 | 商户自审；缺证照样通过 |
| 退回补证 | 当前处于可退回审核，列明具体缺口 | 商户收到任务、对应材料、期限与说明 | 只改变状态、不生成可做任务 |
| 建议接受 | 有事实理由，经授权风控提出 | 商户／授权人收到新的决定请求 | 自动接受或统一解释为补证 |
| 生成包 | 当前有效初审通过，资格仍有效 | 生成可预览的不可混淆版本 | 所有阶段都给建包按钮 |
| 最终审核 | 当前包待审核，独立授权审核人 | 批准冻结／具体原因退回／暂缓升级 | 只有“批准”没有正确否分支 |
| Mock 提交 | 冻结包、有效批准、当前权利和外部期限均成立 | 明确技术状态和业务受理状态 | 网络失败直接当未受理重发 |
| 登记上游事件／结果 | 事件已核验、案／阶段关联正确 | 同阶段等待／核实／新阶段／终局 | 强制先处于已提交状态才接撤回 |
| 进入新阶段 | 有明确适用的新阶段事件及授权 | 新 Stage、原始事件期限、材料适用性复核 | 所有非终局都新建阶段 |
| 登记资金 | 授权 OP、有效事件引用、币种合同正确 | 可追溯 synthetic 账本；核对／通知失效规则生效 | 误执行真实划扣；重复入账 |
| 财务核对 | 当前业务终局，资料齐备且有权核对 | 匹配／差异／有理由不适用 | 只改绿标志即宣称真实资金到账 |
| 通知商户 | 对应当前需通知的结果／资金版本 | 记录渠道、内容、版本与交付状态 | 历史通知永久满足新版本要求 |
| 关闭 | 服务端完整 close_gate 通过 | OP／系统结案，商户只收到结果 | OTHER 未澄清关闭、用批量完成掩盖未解决任务 |
| 发消息／@AI | 参与者有该线程权限 | 消息出现于同案线程，AI／人工来源明确 | 每句聊天弹出高风险命令确认 |
| 转人工 | AI 无法确认／用户请求且任务未重复创建 | 明确接手人、响应目标、解决记录 | 只有“建议联系人工”文字 |
| 知识提取／审核 | 结案后脱敏；候选待审；审核独立 | 批准模式才进入检索 | 已审核条目仍展示必然失败的按钮 |

不需要把所有以上动作放到同一个页面。默认展示下一步主要动作，其他允许动作放“更多操作”，不可用动作给具体原因或责任人。

## 5. AI 怎样真正产生可展示的业务价值

### 5.1 必须串起的一条主线

收到上游合成事件 → AI 读取已确认规则并准备案件计划 → OP 确认发布 → 商户在同案提交实际合成文件 → AI 把证据映射到材料要求并发现具体缺口 → 共享线程解释并转人工处理未知项 → 商户修订 → OP 内容审核 → AI 准备文书及材料索引 → 独立主管审核 → Mock 提交及结果／资金闭环。

AI 展示的应是“做了什么、根据什么、改变了哪个任务、还需要谁确认”，而不是每个页面重复输出长摘要。保留确定性规则引擎负责权限／状态／金额／期限，模型负责解释、语义核查、文书和协调，不要求模型替代确定性判断。

### 5.2 内容级核查的最小范围

先使用授权的合成材料。支持一组确定格式：订单文本、可解析物流凭证、商户客户沟通、退款记录。保存原文件和抽取片段的位置。检查交易编号、金额／币种、时间、订单／物流关联，以及当前清单是否获得实际支持；无法读取或事实不足则明确标记待人工。

不把“文件已上传”当“事实已验证”，不把“清单齐全”当“符合提交条件”，不把“内部审核通过”当“胜诉”。不生成没有依据的胜率。扫描件 OCR、所有文件格式与真实性鉴定不是本轮必须覆盖的范围。

### 5.3 主动性与审计

事件触发与时间触发分开。业务事件后做增量分析；时间到期触发到责任人的提醒／升级。高风险动作保持 Proposal → Human Confirmation → Command → Revision/Eligibility Check → Audit。普通聊天和阅读不应无意义地刷新业务审批版本，但材料、规则、授权等实质变化必须使相关批准失效。

评估 AI 可用材料核查错误、缺口识别、证据引用、转人工正确性、人工修改量和操作耗时。没有企业历史结果数据时，不报告真实胜诉率提升、拒付率下降或节省人力倍数。

## 6. 推进顺序：按跨端业务切片验收，不按页面堆功能

### Gate 0 — 固定基线与修订合同

确认运行页面的 build SHA 与仓库 SHA 一致；记录 URL、服务端版本、数据库和模型／集成模式。备份演示数据，固定上述问题登记表与动作合同。冻结新增驾驶舱、更多模型和更多样例。先写反映企业流程的失败用例，再修实现。

**退出条件：** 明确哪些是本轮范围、哪些是 mock／待企业确认；旧验收不再把“默认私有对话”当共同协作成功。

### Gate 1 — 身份、数据与页面边界

修 A01–A03；服务端投影与权限覆盖所有返回通道。两个商户与 OP／风控／主管分别使用独立会话，正式业务页无角色切换器和跨端业务操作导航。复用现有商户范围过滤，不重写为两套数据库。

**退出条件：** 跨身份、跨商户、内部字段泄露、直访链接和附件权限测试全部通过。只隐藏按钮不能过 Gate。

### Gate 2 — 一案双端的共同任务与沟通

实现 C01–C03 和 U01 的最低闭环：OP 发布 → 商户收到 → 共享对话 → 选择 Contest → 补材料 → OP 看到同案更新。引入实际负责人和任务。OP 内部空间单独授权。优先做一条完整 vertical slice，再复制到其他阶段。

**退出条件：** 两个人各用自己的浏览器、不切角色，能够共同推进同一个案；消息、材料、任务和身份没有串案。

### Gate 3 — 修复异常分支和高风险闸门

优先处理 W01–W07、W09–W10、W12 与 U02/U03/U07；补最终否决、未响应恢复、OTHER 核实、非终局等待、异步撤回、规则变化资格检查。同步修订任务生命周期。其余 W 项纳入支持阶段的验收，未实现阶段明确不开放，不靠图上画了就声称支持。

**退出条件：** 各分支有负责人、有下一次动作、有时限或复查时间，有可达出口；不能通过假结果、假阶段、切身份解除阻断。

### Gate 4 — AI 有材料依据并能真正协调

落实 I01–I03 与 C02；先做可控真实文件链路和共享上下文，再做事件／时间驱动 AI。实现可追溯转人工、建议发布和人工修订。模型超时明确降级，不阻塞已提交业务命令。

**退出条件：** 用缺证、矛盾信息、无法确认三种情况证明 AI 的不同作用，而不是只演示“回答一段话”。

### Gate 5 — 飞书测试闭环、结果与资金说明

经授权的测试租户实现 X01；保留 Portal 为系统入口和真相来源。为 X03 扩展 Mock 故障回执。完成 F01 可理解金额说明和结果／资金／通知版本联动。邮件及真实上游保持显式边界。

**退出条件：** 现场看到一条真正到达测试飞书空间的卡片及回流；断线／重复 callback 不重复业务动作；未联调能力不标“已接入”。

### Gate 6 — 完整按钮回归与冻结

完成其余可见 UI 问题，按第 7 节执行真实多会话 E2E；保留安全／幂等／冻结／规则测试。报告逐场景通过情况与遗漏范围，不只报告测试总数。完成后停止加功能，准备离线 mock 备用。

**退出条件：** 人不需要讲解按钮使用顺序就能处理正常案；异常案没有死路；任何显示成功的动作在双方可见状态和审计中一致。

### 并行分工建议

后端负责人维护领域合同、权限、事件和任务；前端负责人依照同一 available_actions 与角色视图实现交互；AI／集成负责人负责共享上下文、文件核查、时间任务和飞书。每次合流都以同一个跨端场景验收，不能各自宣称模块完成后最后才发现接不起来。

不建议先重写全部页面，再补业务；也不建议先增加案例库、模型数量、复杂 BI 或大量新的角色。先保留现有 SQLite 事务／幂等／CAS、规则来源、包冻结、同步和模型适配器，在能力边界内渐进拆分较大的前端及服务模块。

## 7. 必须执行的验收用例

下面是验收计划，不是本次已运行结果。所有场景使用隔离测试库、合成交易和独立身份，不指向生产。

| 场景 | 预期 |
|---|---|
| 两商户 A/B、A 两案件、多个 OP 身份 | 不能跨商户、串案、复用错误身份；OP 分工按授权规则 |
| 商户直访 OP/治理 URL、改客户端角色字段 | 服务端不提升权限、不返回内部数据 |
| 商户 GET、POST 回执、列表、AI、更新、文件／导出 | 都使用正确字段投影；不是只拦一个详情接口 |
| OP 与商户两个浏览器完成正常链 | 全程无需切换角色；共享消息／材料／任务实时一致 |
| OP 内部消息＋商户共享问题 | 内部内容不出现在商户页面／响应／模型上下文，共享上下文可追溯 |
| 空文件／无关文件／重复文件／矛盾材料 | 不因存在证据代码自动算有效齐全；AI 指向具体依据 |
| 建包后主管否决 | 合法退回目标，旧包失效，新包重新批准 |
| 先 CONTEST 后规则仅允许 ACCEPT | 当前资格阻止抗辩提交，保留原决定及重新确认记录 |
| NO_RESPONSE 后仍有提交权利 | 可核实后恢复；已回复但迟交材料不改成 NO_RESPONSE |
| Accept／授权放弃 | 无抗辩补证，不自动退款；有接受处理依据 |
| 非终局但无新阶段 | 同阶段等待，不强制创建 NEXT_STAGE |
| UNKNOWN／未映射 OTHER | 不作为终局，不允许直接关闭 |
| 举证中收到有效上游撤回 | 合法异步处理，不需要假提交 |
| 后续阶段迟到录入 | 截止来自源事件／明确渠道要求，不从点击时间延期 |
| 旧材料跨阶段复用 | 需要适用性检查；前序结果不冒充当前阶段结果 |
| 通知后新增资金变化 | 当前通知失效，前后端显示一致，重新通知后才关闭 |
| 终局资金差异／开放必要任务 | 拒绝关闭；问题解决而非强制标完成 |
| 关闭后有效更正 | 授权重开或关联后续案，原记录保留 |
| 仅推进时钟、无业务变化 | 正确责任人收到提醒；重复扫描不重复提醒；已关闭不催办 |
| 同时发消息与审核表单 | 普通消息不会不合理地作废审批；实质材料变更必须阻断旧批准 |
| 提交响应丢失／重复 callback／重启恢复 | 幂等业务效果，查证已受理后不重发；模型故障不撤销业务成功 |
| AI 提案被人编辑 | 保留原提案、修改和执行链；没有自动扩大权限 |
| 知识候选待审／批准 | 未批准不可检索；批准后新案例实际引用其知识 ID |
| 所有可见启用按钮逐状态 | 合法输入成功；不可执行时禁用／隐藏／转交，说明明确 |
| 案件不存在、断网、模型失败 | 区分错误状态，输入不丢，不显示虚假的“已完成” |
| 1440/1024/390 宽度、缩放、键盘操作 | 不遮挡主按钮；无横向不可操作区；错误可读。结果需要实测记录 |

建议增加用户可用性测试：让未参与开发的同学扮演商户／OP，要求其无需口头指导找出“现在谁负责、下一步是什么、缺什么”。记录误点击、绕路、操作耗时及求助次数；验收目标由团队设定，不提前声称已改善百分比。

## 8. 保留／改造／新增／退场

**保留并加强：** 同案 ID、商户范围过滤、SQLite 原子命令、CAS/revision、幂等与重放、审核与冻结包校验、来源／版本、自动同步、可替换模型适配器、指南参考资料、明确 mock 边界。

**改造：** API 身份与响应投影；前端角色导航与可执行动作；当前混合的任务／状态分支；Agent 上下文与时效性；案例结果和财务呈现；通知／任务版本。

**新增：** 可信独立会话、CaseParticipant、可分配待办、Shared Thread／OP_INTERNAL、真实合成文件对象与核查、最终否分支、剩余权利核实、异步事件更正、时间调度与完整人类接手、测试飞书出站。

**退出正式工作区：** 任意角色切换器、V1 历史业务入口、用注册元数据冒充文件核查的展示、跨阶段无条件操作集合、无依据胜率、未联调却标送达的集成状态。历史工具可保留在明确隔离的演示／维护入口。

## 9. 交给 Codex 的执行要求

本文件是修复目标与验收合同，不要求机械创建指定类名，也不要求推倒现有架构。实现者先核对当前分支与 SHA，若分支已有新提交，逐项验证本报告所述行为是否仍存在，不盲目回退后续改进。

先输出本轮实际缺陷清单、依赖顺序和要新增的失败测试，再按 Gate 修复。业务代码变更由团队另行授权；本次任务只给出计划。不要创建 PR 或合并 master，除非用户另行要求。不得修改生产数据、发送真实商户消息、调用真实支付／上游接口或把合成效果当企业验证结果。

每轮交付提供：修复条目编号、源码定位、失败→通过的测试证据、双端操作录像／截图、实际接口与状态、残余风险及未联调边界。不要用“测试数量多”替代与老师业务需求一致的验收。

## 10. 依据与版本

用户附件：

1. `OceanPilot_V2_推进说明文档(1).docx`：业务所有权、阶段、开发优先级与完成标准。
2. `OCEANPILOT_V2_ARCHITECTURE(1).md`：一内核／双业务端／协作层；原图简化分支需要本轮修订。
3. `拒付处理流程与验证(3).html`：接受、非终局等待、异常、资金、关闭与更正设计。
4. `朱泽林, Jakey, 卢薪宇, 蒋灏然（鹿出草莓酱）的视频会议(5).txt`：尤其 12:38–18:15 的共享对话／AI 协作要求，以及 38:30–38:54 的贯穿事项跟踪。
5. 本次五张截图：流程修改建议、企业处理边界、通知与收件渠道、飞书协作讨论。截图里的简化角色口径不自动替代分渠道企业协议。

固定提交源码：
- [SHELL · src/oceanpilot/web/v2/shell.html](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/shell.html)
- [WEB · src/oceanpilot/web/v2/app.js](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/web/v2/app.js)
- [API · src/oceanpilot/api/disputes.py](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/api/disputes.py)
- [SERVICE · src/oceanpilot/application/disputes.py](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/disputes.py)
- [DOMAIN · src/oceanpilot/domain/dispute.py](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute.py)
- [RULE · src/oceanpilot/domain/dispute_rules.py](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/domain/dispute_rules.py)
- [AGENT · src/oceanpilot/application/dispute_agent.py](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/application/dispute_agent.py)
- [STORE · src/oceanpilot/adapters/persistence/disputes.py](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/src/oceanpilot/adapters/persistence/disputes.py)
- [AGENT-DOC · docs/v2/agent-workflow.md](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/docs/v2/agent-workflow.md)
- [FEISHU · docs/v2/feishu.md](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/docs/v2/feishu.md)
- [ACCEPTANCE · docs/v2/dual-surface-acceptance.md](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/docs/v2/dual-surface-acceptance.md)
- [README · README.md](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/README.md)
- [MIGRATION · docs/v2/architecture-and-migration.md](https://github.com/jiang4wqy/oceanpilot-evidenceos/blob/759e3b321bea1a21f0ea85aae227f8f4389421e4/docs/v2/architecture-and-migration.md)

外部安全原则仅作实现建议，不替代企业业务事实：[OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) —— 默认拒绝、最小权限、逐请求与对象级校验、服务端授权。
