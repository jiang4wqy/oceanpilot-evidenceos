# V2.1 验证记录（实施中）

本文件记录已完成的验证及尚未完成的验收。编号与验收口径见 [推进计划](v21-source-plan.md) 和 [需求矩阵](v21-requirements.md)。V2 既往测试通过不等于 V2.1 已验收。

## 基线及环境

- 分支：`oceanpilot-v2`；实施前 HEAD：`759e3b321bea1a21f0ea85aae227f8f4389421e4`。
- `master` 基线：`250e7d904fce451e6fe72b2192cba393b717c636`；本次不提交 PR、不合入 master。
- 已用 SQLite backup API 备份本机三份业务/规则数据库；备份及清单保存在未跟踪的 `work/v21-baseline-20260909T043928Z/`，文件权限 0600。
- 原演示服务继续使用 8012。V2.1 验证服务使用独立的 8014 与 `work/v21-qa/` 数据目录；测试不会清空原案件。
- V2.1 账号由服务端创建。普通 HTTP 请求的角色头和地址不授予权限。启动时记录 source SHA-256、Git HEAD、代码是否修改及数据实例标识，登录后可用 `/api/v2/runtime` 核对。
- 规则提炼库保留原来源与版本，正式规则待确认状态不因选中一个模板而自动通过。交易 registry、账务和上游回执仍为显式 synthetic/mock。

## 已有失败证据与阶段结果

- A01：基线 6 项伪造角色头/未登录页面测试失败；实施后通过。真实会话测试现覆盖登录、CSRF、跨角色地址、双商户、两名运营、停用/过期/登出、参与人撤权和商户字段投影。
- W01–W14/X03/F01：首批 22 个基线失败场景修复后通过，并扩展至 55 个领域场景。包括未响应恢复、有效抗辩不被逾期覆写、接受处理、非终局分支、未知结果核验、更正/重开、来源时间、材料适用性和部分支持金额。
- 共享协作模块包含实际账号会话、共享/内部隔离、旧私聊只读、消息/已读不改业务版本、人工接手、基于内容的文件校验和批准知识的实际检索验证。详见 [模块说明](v21-collaboration.md)。
- 8014 首次真实浏览器验证通过任务发布→商户抗辩→双向共享消息；内部备注仅运营可见。真实 JSON 文件在两端对应同一对象，未发送草稿保留。390px 下两端无横向溢出。
- 8014 多身份完整浏览器流程已走通：导演登记合成交易→标准化事件→运营发布→商户抗辩及上传 5 份真实 JSON→独立风控审核→主管终审→Mock 提交→UNKNOWN 核验→非终局等待→明确终局 WON→合成资金→主管核对→运营通知→主管结案。期间发现胜诉填写币种误触发部分支持金额校验，已修复并增加真实 HTTP 边界回归。
- 独立审查 27 项真实 HTTP 回归通过。复现并修复纯材料引用绕过、Agent 相似案件越过参与人权限，以及商户 Agent 输出内部期限；同时验证未知材料的独立人工内容核验出口、替换使旧审核失效、暂缓后恢复与通知版本更新。纯引用不能满足新材料要求，文件原文摘录和行号须可验证。
- 全量回归为 **2,137 passed / 6 skipped**，118.52 秒。旧角色头、私聊和完整列表快照测试已迁移到真实会话与新版合同。跳过项是 5 项未向全量进程注入密钥的外部模型测试，以及 1 项本机未安装 PowerShell 的脚本测试；真实 V2.1 DeepSeek 调用已在隔离探针中单独验证。Ruff lint、271 文件格式检查、字节编译和 diff 检查通过；既有四个离线演示／评估脚本均成功。
- 新旧提案执行均有审计边界：新提案确认保存可信 run／proposal／原始字段／规范化字段／人工修改／确认人；旧无来源命令仍可按原指纹精确重放。DTO 自动默认值不被误记作人工修改。
- 冻结计划保留原文用于 Markdown 强制换行的行尾双空格，与本地原件逐字节一致，SHA-256 已核验。其余已暂存文件的 `git diff --check` 通过；提交文件未包含本机 `.env` 密钥值、账号凭据或数据库。
- 飞书出站 outbox、超时／重试、签名回调和回复／更新的本地实现与 142 项相关回归已完成；测试使用模拟传输，无真实外部消息。
- 真实 DeepSeek 共享消息探针 **1 次模型调用通过**：HTTP 200、`source=MODEL`、`provider=DEEPSEEK`、实际模型 `deepseek-v4-flash`（配置别名 `deepseek-chat`）、8.91 秒、11 条引用。实际模型上下文含共享消息和引用资料，不含 OP 内部消息或内部／外部期限；双方看到同一回复，业务 revision 未变化。隔离数据、关闭后台模型事件和飞书，未反复重试。
- 实际浏览器验证已补齐内容不足文件的拒绝／撤回、未知文件的独立原文核验、结案公开资金、跨商户／跨端 403，以及真实断网后恢复内部范围并以同一命令 ID 用键盘重试，最终只有一条消息。1440／1024／390px 无横向溢出，另测 200% 等效布局；最后交互无 JavaScript 错误。详细限制见 [界面验收](ui-validation-v21.md)。
- `2.1.0.dev0` wheel 构建成功；从临时解包目录独立导入，验证打包页面、独立账号、登录、角色边界、队列和 62 条来源库，未包含本机密钥／账号密码／数据库。容器验证交由 GitHub CI，本机没有 Docker。
- 最后两项 UI 边界已修复：真实 `PENDING_REVIEW` 候选显示审核入口，已审核保持只读；异常阶段定位准确，接受路径不显示材料／终审已完成。新增 8 项 DOM 回归，相关 49 项通过；随后重新构建 wheel，逐文件核对最终 UI 资源与源码完全一致。没有为这两项重复完整浏览器链。
- UI 最终模块回归 **87 项通过**，包括上述新增 8 项；该结果与此前 2,137 项全量回归分开记录。

## E01：固定合成规模实测

运行 `PYTHONPATH=src .venv/bin/python scripts/benchmark_v21_queue.py`。每案 25 条合成审计与 5 条合成证据，两商户各占一半。两种读取方式各预热一次、测量 20 次。测试使用临时数据库，结束后自动清除。

| 总案件 / 当前商户可见 | 旧完整列表响应 | 新 25 条摘要响应 | 旧 P95 | 新 P95 |
|---|---:|---:|---:|---:|
| 100 / 50 | 2,342,601 B | 17,024 B | 5.693 ms | 2.822 ms |
| 1,000 / 500 | 23,426,901 B | 17,077 B | 58.066 ms | 13.791 ms |

P95 包含本机 SQL 读取和 JSON 编码，不含 HTTP 传输、浏览器绘制或外部模型。在受控 SQLite 排他锁占用 50 ms 的探针中，被阻塞读取分别耗时 66.448/66.531 ms；这是一项实际锁竞争测量，不是生产数据库锁等待监控。完整输入与结果见 [基准 JSON](benchmarks/v21-queue-20260909.json)。

## 仍需完成

- 将候选版本推送 V2 分支并检查 GitHub CI 的独立环境与容器运行结果。
- 真实飞书测试应用和群尚未配置；真实发卡、点击／提问、群内回复／更新的 Gate 5 不能以 mock 或 callback HTTP 成功代替。
- 已完成自动化浏览器验收；实际业务使用者的无引导试用尚未执行，未把前者表述为后者。

V2.1 目标仍在进行中；本记录不构成完成声明。

## 42 项验收证据映射

本表按冻结计划编号连接现有证据，不新增或改变原始要求。“自动化”指已有定向断言；“浏览器”指 [V2.1 双端浏览器报告](ui-validation-v21.md) 中记录的实际交互；“源码核对”仅证明当前实现，不能替代未执行的专项界面验收。测试总数与整体结论以上文最终记录为准，表中不将本地 mock 升格为真实外部联调。

### A：身份、数据范围与负责人

| 编号 | 已验证边界 | 证据与层级 |
| --- | --- | --- |
| A01 | 角色请求头不能登录或切换身份；真实 session、CSRF、跨角色地址、登出、过期和账号撤销生效。列表、详情、命令及更新均重新校验范围。 | 自动化：[身份与访问 HTTP](../../tests/api/test_v21_identity.py)，包含 `client_role_headers_do_not_authenticate`、`csrf_logout_expiry_and_account_revocation`、`scope_applies_to_list_detail_plan_commands_and_updates`；浏览器：[独立多身份流程与商户 B 拒绝访问](ui-validation-v21.md)。 |
| A02 | 商户案件、计划、Agent 当前及历史输出裁去内部自由文本和内部时限；相似案件逐案检查真实读者权限。共享模型不接收其他私案或 OP_INTERNAL，旧存储保留但读取时投影。 | 自动化：[身份字段投影](../../tests/api/test_v21_identity.py)、[Agent 读者与实际模型输入](../../tests/application/test_dispute_agent_reader_scope.py)、[独立 HTTP 复现回归](../../tests/review/test_v21_independent_review.py)；一次真实模型边界：[模块记录](v21-collaboration.md)。 |
| A03 | 案件参与者与负责人来自服务端账号；非参与人及已撤权人员不能读写，任意自报 assignee 不获接受，人工跟进默认关联本案负责人。 | 自动化：[参与人撤权](../../tests/api/test_v21_identity.py)、[真实负责人分配 `task_real_assignee_is_selected_from_case_participants`](../../tests/workflow/test_dispute_v21.py)、[HTTP 人工接手](../../tests/api/test_dispute_collaboration_api.py)；浏览器：[真实运营、风控、主管账号](ui-validation-v21.md)。 |

### C：共享沟通与人工协作

| 编号 | 已验证边界 | 证据与层级 |
| --- | --- | --- |
| C01 | 同一案件的 SHARED 是双端共同线程，OP_INTERNAL 隔离；旧私聊只读，不自动共享。消息、已读与回复不增加业务 revision。 | 自动化：[共享线程、旧历史及版本](../../tests/application/test_dispute_collaboration.py)、[真实会话 HTTP](../../tests/api/test_dispute_collaboration_api.py)、[旧 Agent 消息入口兼容](../../tests/api/test_dispute_agent_api.py)；浏览器：[双端消息与独立草稿](ui-validation-v21.md)。 |
| C02 | Agent 实际读取共享消息、内容文件及引用；OP 内部消息不进入共享模型，晚到模型回复不覆盖新版本，模型失败保留问题并显示降级。 | 自动化：[共享上下文、迟到及 fallback](../../tests/application/test_dispute_collaboration.py)、[实际注入模型上下文](../../tests/application/test_dispute_agent_reader_scope.py)；真实单次 DeepSeek 探针：[来源、11 条引用及共享边界记录](v21-collaboration.md)。 |
| C03 | 已读游标单调且不会因读取回执无限写入；人工事项有请求、接手、解决、逾期升级和历史。共享消息不使业务批准失效，scope 内更新能唤醒另一端。 | 自动化：[已读／handoff／clock／updates](../../tests/application/test_dispute_collaboration.py)、[实际负责人接手与解决 HTTP](../../tests/api/test_dispute_collaboration_api.py)；浏览器：[断网后原范围、原消息 ID 恢复](ui-validation-v21.md)。 |
| C04 | 真人商户、OceanPayment 和 OceanPilot 使用不同 actor/source；模型、确定性工具及 fallback 不混标。 | 自动化：[共享消息 distinct sources](../../tests/application/test_dispute_collaboration.py)、[前端 `agent_sources_distinguish_model_answers_tools_and_fallback`](../../tests/web/test_v2_rendering.py)；浏览器：[双端聊天截图与消息显示](ui-validation-v21.md)。 |

### W：案件状态与业务出口

| 编号 | 已验证边界 | 证据与层级 |
| --- | --- | --- |
| W01 | NO_RESPONSE 后可经授权在同阶段恢复；恢复检查剩余权利与时限，拒绝过期恢复，不凭“未响应”代记接受。 | 自动化：[V2.1 `w01_authorized_same_stage_restore`、`w01_restoration_rejects_expired_rights_and_preserves_decision`](../../tests/workflow/test_dispute_v21.py)。 |
| W02 | 已响应 CONTEST 的材料逾期只形成证据逾期任务，不能覆盖成 NO_RESPONSE，商户立场保持不变。 | 自动化：[V2.1 `w02_contest_lateness_never_becomes_no_response`](../../tests/workflow/test_dispute_v21.py)。 |
| W03 | 风控建议接受保留为建议，商户决定不被代改；通过显式恢复路径继续案件，不能误用退回补证语义。 | 自动化：[V2.1 `w03_review_accept_is_recommendation_not_revision`](../../tests/workflow/test_dispute_v21.py)、[独立 HTTP `accept_recommendation_keeps_merchant_decision_and_allows_explicit_recovery`](../../tests/review/test_v21_independent_review.py)。 |
| W04 | 终审支持批准、材料退回、文书退回和暂缓；文书退回不伪造材料审核完成，旧包及旧终审不能直接复用；HOLD 有可执行恢复出口。 | 自动化：[V2.1 多种 `w04` 场景](../../tests/workflow/test_dispute_v21.py)、[独立 HTTP `final_hold_has_recoverable_document_return_and_no_unexecutable_approval_choice`](../../tests/review/test_v21_independent_review.py)；浏览器：[独立主管终审](ui-validation-v21.md)。 |
| W05 | 已知非终局结果可 WAIT 留在同阶段，ACTION 有后续任务出口；只有明确 NEXT_STAGE 分流才需要新阶段。 | 自动化：[V2.1 `w05_known_nonterminal_can_wait_in_same_stage`、`w05_action_disposition_stays_same_stage_and_has_followup_exit`](../../tests/workflow/test_dispute_v21.py)；浏览器：[WON / WAIT 保持原轮次](ui-validation-v21.md)。 |
| W06 | 未映射 OTHER、UNKNOWN 不能自行成为可关闭终局；自定义结果映射仍需风控核验，拒绝核验可恢复先前等待状态。 | 自动化：[V2.1 `w06` 场景](../../tests/workflow/test_dispute_v21.py)、[独立 HTTP 未知来源、更正及终局核验](../../tests/review/test_v21_independent_review.py)；浏览器：[UNKNOWN 核验主动作及拒绝恢复](ui-validation-v21.md)。 |
| W07 | 非等待阶段也能保存异步撤回／结果，但先进入人工核验；错轮次事件和多个待核验事件不能错误决定当前案或退回已确认终局。 | 自动化：[V2.1 `w07` 场景](../../tests/workflow/test_dispute_v21.py)、[撤回 HTTP](../../tests/api/test_dispute_intake_http.py)、[来源事件关联](../../tests/application/test_dispute_intake.py)。 |
| W08 | 关闭后更正必须先显式重开，保留原结果与关联；重开后不能跳过更正关系，不能暗改旧账本。 | 自动化：[V2.1 `w08_close_requires_explicit_reopen_then_correction`、`reopened_case_cannot_skip_correction_relationship`](../../tests/workflow/test_dispute_v21.py)、[标准化更正关联与重试](../../tests/application/test_dispute_intake.py)。 |
| W09 | 规则变化重新检查抗辩资格，并使旧冻结包失效；即使新规则仍允许抗辩，也不能以旧包直接提交。UI gate 与业务执行同样拒绝失效规则依据。 | 自动化：[V2.1 `w09` 与 `ui_gate_and_execution_reject_the_same_stale_rule_authority`](../../tests/workflow/test_dispute_v21.py)。 |
| W10 | 后续阶段以来源 occurred/received 时间及新阶段规则锚点计算时限；缺少所需来源时间时不能用操作当下或另一个时间字段代替。 | 自动化：[V2.1 `w10`、`stage_deadline_anchor_comes_from_new_stage_rule_not_previous_stage`、`stage_missing_rule_required_received_time_does_not_substitute_occurred_time`](../../tests/workflow/test_dispute_v21.py)。 |
| W11 | 新阶段隔离旧材料及旧结果；材料只有在显式确认适用后才满足当前清单，旧阶段冻结快照保持原样。 | 自动化：[V2.1 `w10_w11_stage_uses_source_time_and_isolates_evidence_outcome`](../../tests/workflow/test_dispute_v21.py)、[阶段历史快照](../../tests/workflow/test_dispute_engine.py)。 |
| W12 | 接受责任必须记录渠道处理及其 Mock 回执；禁用、无动作依据、失去响应与查询同原 request 均有明确状态，不生成资金入账假象。 | 自动化：[V2.1 各 `w12` 场景](../../tests/workflow/test_dispute_v21.py)。这里验证的是 Mock 渠道合同，没有真实卡组织处理回执。 |
| W13 | 终局仅取消或取代相应任务，不把所有开放事项标“完成”；取消、豁免、取代保留责任与原因，任务豁免不能替代材料或审核授权。 | 自动化：[V2.1 `w13_terminal_cancels_evidence_not_independent_required_tasks`、`w13_task_resolution_is_truthful_and_cannot_waive_review_authority`、`evidence_change_supersedes_review_task_without_claiming_it_completed`](../../tests/workflow/test_dispute_v21.py)。 |
| W14 | 明确仅允许 ACCEPT 的规则可以有空抗辩证据清单，不强制虚造材料；规则权利仍须人工明确。 | 自动化：[V2.1 `w14_accept_only_rule_does_not_require_contest_materials`](../../tests/workflow/test_dispute_v21.py)、[未知规则必须明确 allowed_actions](../../tests/workflow/test_dispute_engine.py)。 |

### U：界面动作、表单与反馈

| 编号 | 已验证边界 | 证据与层级 |
| --- | --- | --- |
| U01 | 动作由服务端 available_actions 决定，错误角色和不满足 gate 的动作不能靠打开弹窗执行；返回禁用理由与执行错误一致。 | 自动化：[HTTP gate 与命令一致](../../tests/api/test_v21_identity.py)、[前端 controls/use_server_actions](../../tests/web/test_v2_rendering.py)、[规则失效 gate](../../tests/workflow/test_dispute_v21.py)；浏览器：[实际主动作及确认](ui-validation-v21.md)。 |
| U02 | 手动决定表单使用规则的允许选项；未知规则不预选权利，不能强塞 CONTEST 到 ACCEPT-only 表单。飞书决定卡亦按相同权利过滤。 | 自动化：[前端 `unknown_rules_never_preselect_merchant_rights`、`v21_action_schema_filters_decisions_and_applies_constraints`](../../tests/web/test_v2_rendering.py)、[飞书允许动作卡片](../../tests/channels/test_dispute_feishu.py)。 |
| U03 | 关闭显示当前结果／资金版本对应的通知状态；历史消息不会恢复“已通知”。新资金事件使旧通知失效，必须再次通知。 | 自动化：[前端 close_gate](../../tests/web/test_v2_rendering.py)、[V2.1 `f01_partial_amounts_and_notification_versions`](../../tests/workflow/test_dispute_v21.py)、[独立 HTTP later_money_requires_new_notification](../../tests/review/test_v21_independent_review.py)。 |
| U04 | 待终审、未知结果核验、提交不确定、上游需动作、未响应核实等分支不落回接收；生命周期只标当前环节。Accept／授权放弃使用独立路径，不显示材料／终审节点或材料准备度，不伪示前序都已完成。 | 新增定向自动化：[前端 `test_lifecycle_positions_new_branches_without_inventing_completed_approvals` 的 7 个分支](../../tests/web/test_v2_rendering.py)；领域：[V2.1 `w04` 场景](../../tests/workflow/test_dispute_v21.py)。此前浏览器已走通[初审→建包→主管终审→提交](ui-validation-v21.md)；最终分支修正此次以运行时 DOM 回归验证，未重复整条真实浏览器链。 |
| U05 | 材料变更使旧审核和旧包失效；前端明确显示“历史审核 · 已失效”，不能继续凭旧 PASS 提交。 | 自动化：[前端历史失效审核](../../tests/web/test_v2_rendering.py)、[材料变更与冻结内容](../../tests/workflow/test_dispute_engine.py)、[替换已人工核验文件后重新核验](../../tests/review/test_v21_independent_review.py)。 |
| U06 | 本轮采用“任务必需”的固定语义：已移除发布任务中无效的 required 复选框，旧 DTO 字段只保留接口兼容，不再提供可更改却忽略的配置。 | 源码核对：[dialogFields 的 PUBLISH_TASK](../../src/oceanpilot/web/v2/app.js)；相关发布与确认路径：[前端提案确认](../../tests/web/test_v2_rendering.py)、[提案发布 HTTP 与 DTO 默认值](../../tests/api/test_dispute_agent_api.py)。不声称旧复选框的 true/false 行为已通过。 |
| U07 | 结果表单可明确选择 UNKNOWN，进入风控核验；未选的可选部分支持币种／金额不默认为事实，OTHER 不能直接成为终局。 | 自动化：[前端结果默认值与空金额](../../tests/web/test_v2_rendering.py)、[V2.1 UNKNOWN/OTHER](../../tests/workflow/test_dispute_v21.py)、[独立 HTTP 结果金额边界](../../tests/review/test_v21_independent_review.py)；浏览器：[UNKNOWN 核验](ui-validation-v21.md)。 |
| U08 | 表单使用服务端字段约束，非法日期、越界金额、缺项及类型错误受到校验；被拒输入不部分修改案件，旧命令不因新增 DTO 默认字段改变回放 fingerprint。 | 自动化：[前端字段／日期／金额](../../tests/web/test_v2_rendering.py)、[V2.1 invalid_input/CAS/replay](../../tests/workflow/test_dispute_v21.py)、[标准化 DTO HTTP](../../tests/api/test_dispute_intake_http.py)、[严格 DTO](../../tests/api/test_dispute_api.py)。 |
| U09 | 无权或不存在的案件进入明确错误结束态，不持续 spinner、不回退到其他可见案；异步旧响应不会覆盖当前选择。 | 自动化：[前端 missing_case、late_case、case_page_never_falls_back](../../tests/web/test_v2_rendering.py)；浏览器：[跨商户及跨端 403 结束态](ui-validation-v21.md)。 |
| U10 | PENDING_REVIEW 候选为获准审核角色显示人工审核按钮；APPROVED／REJECTED 只读。未批准模式不可检索，批准后按范围使用。 | 新增定向自动化：[前端 `test_governance_pending_review_has_action_but_decided_candidates_are_read_only`](../../tests/web/test_v2_rendering.py)；后端：[知识批准 HTTP](../../tests/api/test_dispute_api.py)、[关闭后独立知识审批](../../tests/workflow/test_dispute_engine.py)、[批准模式实际检索](../../tests/application/test_dispute_collaboration.py)。按钮差异此次为运行时 DOM 回归，未声称另做真实浏览器审批。 |

### I：Agent 工具、内容、知识与审计

| 编号 | 已验证边界 | 证据与层级 |
| --- | --- | --- |
| I01 | 只推进注入时钟即可生成持久 SLA 提醒；同一阈值重复 tick、服务重启均不重复，提醒不改变案件业务版本。无需先执行人工命令触发观察。 | 自动化：[clock-only、持久去重及重启](../../tests/application/test_dispute_collaboration.py)。这是受控时钟与本地调度验收，不代表真实群提醒已发送。 |
| I02 | 材料逾期与决定未响应分开；当前商户材料任务到期只生成对应提醒，人工事项逾期只升级一次，已解决事项停止升级。 | 自动化：[V2.1 `w02_contest_lateness_never_becomes_no_response`](../../tests/workflow/test_dispute_v21.py)、[当前任务 clock 提醒与 handoff 停止](../../tests/application/test_dispute_collaboration.py)。 |
| I03 | 真实 UTF-8 TXT/JSON/CSV 内容保存为鉴权对象，绑定案件、代码、hash、事实及行号；空／伪装／重复／缺失／矛盾内容不能冒充合格。未知类型有独立 Risk 的原句定位核验出口，仍需后续材料及终审；纯引用和无关共同事实不能绕过。 | 自动化：[真实文件与内容](../../tests/application/test_dispute_collaboration.py)、[对象下载 HTTP](../../tests/api/test_dispute_collaboration_api.py)、[独立原句核验与替换失效](../../tests/review/test_v21_independent_review.py)、[领域对象绑定与提交 gate](../../tests/workflow/test_dispute_v21.py)；浏览器：[真实上传、撤回、替换、line:4 人工核验](ui-validation-v21.md)。未声称支持 PDF/OCR。 |
| I04 | 已关闭且脱敏人工批准的模式进入下一案真实检索，保留知识 ID 与批准版本；未批准、其他商户、其他阶段／规则版本不可命中。指南 62 条参考／28 个模板及来源冲突作为参考，不覆盖冻结规则。 | 自动化：[实际批准模式闭环](../../tests/application/test_dispute_collaboration.py)、[案例库真实检索／旧 run 不伪造／来源冲突](../../tests/application/test_dispute_agent_knowledge.py)、[知识审批 API](../../tests/api/test_dispute_api.py)。 |
| I05 | 编辑提案保留服务端验证的 run、proposal、scope、原版本、原载荷、实际载荷、确认人及差异；未编辑提案记录 edited=false，DTO 默认值不误算人工修改；原无 lineage 命令按旧 fingerprint 重放。 | 自动化：[编辑与来源篡改](../../tests/application/test_dispute_collaboration.py)、[未编辑／旧命令 lineage HTTP](../../tests/api/test_dispute_agent_api.py)、[前端编辑与未编辑的路由选择](../../tests/web/test_v2_rendering.py)。 |
| I06 | 早期案件仍能发布当前任务；关闭 gate 在结果／资金／通知未完成时仍独立阻断，前端按当前动作显示负责人及禁用原因。 | 自动化：[早期 Agent 发布提案](../../tests/api/test_dispute_agent_api.py)、[当前 gate 与命令一致](../../tests/api/test_v21_identity.py)、[前端当前动作／关闭 gate](../../tests/web/test_v2_rendering.py)；浏览器：[按阶段完成主动作](ui-validation-v21.md)。这些证据验证当前动作可推进与关闭条件独立，不将完整关闭条件解释为早期都不可操作。 |

### X、F、E：接入、资金与规模

| 编号 | 已验证边界 | 证据与层级 |
| --- | --- | --- |
| X01 | **仅本地通过；真实 Gate 5 待配置。** 已验证签名、token、时窗、可信用户／群／案件绑定、独立业务审计、SHARED 普通消息、持久 outbox、确认发送、失去回执重试、并发发送、授权撤销及同案 reply/update。模拟回执不代表真实投递。 | 自动化：[签名回调](../../tests/channels/test_dispute_feishu.py)、[真实本地账号＋mock transport outbox](../../tests/channels/test_dispute_feishu_outbox.py)、[官方消息协议 transport](../../tests/feishu/test_client.py)；边界：[飞书文档](feishu.md)。尚无获授权真实测试群、真实发卡／点击／提问／回执，不能标记 Gate 5 通过。 |
| X02 | 导演登记显式合成交易事实，运营接收标准化事件；ALERT/INQUIRY 不建正式案，错配或未知交易隔离，重试保留原 envelope，撤回／更正关联已有案；旧 INTAKE/demo HTTP 不能绕过 registry 和真实角色。 | 自动化：[标准化 inbox/registry](../../tests/application/test_dispute_intake.py)、[真实账号入口及旧路径封口](../../tests/api/test_dispute_intake_http.py)；浏览器：[导演→运营标准化建案](ui-validation-v21.md)。外部 webhook／email 仍无生产接入声明。 |
| X03 | Mock 接口覆盖不确定、技术已收但业务拒绝、断网查询、相同请求重试与过期后禁重发；未查询原请求不能盲发第二次。 | 自动化：[V2.1 `x03_uncertain_submission_queries_before_any_resend`、`submission_unknown_then_expired_window_prevents_retry` 及 `w12` 失去回执](../../tests/workflow/test_dispute_v21.py)。仅为 Mock 故障合同，不是卡组织联调。 |
| F01 | 部分支持／责任分配有明确金额与币种；退款、费用、返还和净影响分开，资金变化使核对及通知失效；商户仅显示公开资金摘要。币种单填的 WON/LOST 可正确全额分配，PARTIAL 缺分配或币种错误拒绝。 | 自动化：[V2.1 `f01` 场景](../../tests/workflow/test_dispute_v21.py)、[独立 HTTP 金额及重新通知](../../tests/review/test_v21_independent_review.py)、[商户公开 financial_summary](../../tests/web/test_v2_rendering.py)；浏览器：[合成资金→主管核对→通知→关闭](ui-validation-v21.md)。无真实银行入账验证。 |
| E01 | 列表返回分页摘要和范围内统计；当前案件更新不重复下载全量列表，cursor 保留离线变化且按读者过滤。已量测固定合成规模的响应字节、SQL＋编码 P95 与受控锁等待。 | 自动化：[摘要分页／统计](../../tests/api/test_v21_identity.py)、[只读 cursor／范围／重启／锁预算](../../tests/application/test_dispute_updates.py)、[前端不全量刷新](../../tests/web/test_v2_rendering.py)；实测：[基准 JSON](benchmarks/v21-queue-20260909.json) 与 [基准脚本](../../scripts/benchmark_v21_queue.py)。不外推生产网络、浏览器绘制或模型延迟。 |
