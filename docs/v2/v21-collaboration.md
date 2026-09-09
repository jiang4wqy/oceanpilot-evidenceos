# V2.1 共享协作、内容材料与 Agent 合同

本模块落实源计划 C01–C03、I01–I05 中的本地可执行链路。共享聊天、已读、人工接手及计时提醒保存在独立的 SQLite 追加日志，材料登记继续走案件命令。普通聊天不会使已完成审批失效；材料、规则和授权变更仍由案件引擎执行版本校验。

## 线程与身份

主入口 `SHARED` 是同一案件的商户、获授权 OceanPayment 人员与 OceanPilot 共同会话。内部讨论显式选择 `OP_INTERNAL`；商户请求该范围返回 404。每次访问调用案件权限策略，身份来自服务端会话和参与者目录，URL、客户端角色头、请求体不能授予权限。

旧 `MERCHANT` / `OPERATIONS` Agent 会话保持原可见范围，只读保存于 `legacy_conversations`，不进入新共享上下文。原本已公开的案件任务发布、商户决定、通知和共享 COMMENT 按来源事件 ID 导入共享线程；面向商户的补证或建议接受反馈可以共享，内部 PASS 审核、文书草稿和账务引用不导入。重复启动和命令重放不产生重复公开消息。

`GET /api/v2/cases/{id}/collaboration?scope=SHARED&after=0` 返回最多 200 条追加事件中的消息、当前人工事项、文件、参与者及阅读回执。`cursor` 是已返回位置；`has_more` 为真时继续请求该位置。既有长轮询增加 `collaboration_changed`，也置 `conversation_changed`，无需重新拉取全案来感知普通消息。内部事件不会推进商户可见游标。

消息显示 `actor_type`（MERCHANT / OCEANPAYMENT / OCEANPILOT / SYSTEM）和真实模型/确定性来源。`AVAILABLE_IN_PORTAL` 表示门户可读，不代表飞书或邮件投递成功。已读需要用户实际更新游标，按参与者记录；读取一条阅读回执不会递归生成新回执。

## 消息与人工接手

`POST .../messages` 使用 `{command_id, scope, message, ask_agent}`；不要求业务 revision 或高风险确认。用户消息先持久化，`ask_agent=true` 再同步调用 Agent。相同身份、范围和载荷的命令重放不重复请求模型；修改任何身份或载荷被拒绝。模型超时/不安全输出采用明确 FALLBACK；模型运行中业务版本变化时返回 `CASE_CHANGED`，保留提问，丢弃失效回复。

`POST .../handoffs` 建立有原因、责任人和跟进时间的人工事项；默认交给本案已分配 OP。只能指定服务端参与者目录内有资格的人。相同未解决原因不会重复建任务。`POST .../handoffs/{id}` 支持 `CLAIM`、`RESOLVE`，须先接手再解决。商户不能代替 OP 接手。未解决事项供关闭硬闸门读取，不能靠结案批量抹去。

30 秒后台扫描使用实际时间，也支持注入测试时钟。当前开放商户任务看商户期限；OP 工作看内部期限；外部截止触发权利核实。已完成商户任务不会继续催商户，关闭案件不扫描。提醒按案件、阶段、截止类型、实际期限和档位持久去重；人工事项过跟进时间保留升级记录。时间观察不写业务 revision，也不推断胜诉、失权或接受。

## 真实合成文件

当前支持 **UTF-8 `.txt`、`.json`、单行交易 `.csv`**，最大 2 MiB。HTTP 用 JSON base64 传输，原始字节保存 SQLite BLOB，记录 hash、上传人、材料版本、抽取正文和行位置；按需下载时再次鉴权。HTML、可执行标记、MIME/后缀不符、空文件、非 UTF-8 内容均明确拒绝。PDF、扫描 OCR、多格式真实性鉴定尚未实现，不声称已识别。

结构化合成材料共同字段：`transaction_id`、`currency`、`amount_minor`，须与当前案件一致。JSON 可将其余事实放入 `facts` 对象；TXT 每行 `field: value`，CSV 为同名列。

| 材料代码 | 内容检查的事实字段 |
|---|---|
| transaction.receipt | ordered_at、item_description |
| fulfillment.tracking | tracking_number、shipped_at |
| fulfillment.proof_of_delivery | delivered_at、recipient_confirmation |
| fulfillment.address_match | address_match_result |
| comms.customer | communicated_at、customer_message、merchant_reply |
| billing.refund_record | refunded_at、refund_amount_minor |
| product.description | item_description |
| policy.terms_refund | policy_text、accepted_at |
| subscription.cancellation_record | cancellation_status、requested_at |
| history.prior_transactions | prior_transaction_count |
| billing.duplicate_check | comparison_result |
| auth.avs_result / auth.cvv_result | verification_result（仅结果，不接收验证凭据） |
| auth.threeds | authentication_result |
| auth.device_ip_match | device_match_result |

示例（合成演练，字段应由实际上传文件提供）：

```json
{
  "transaction_id": "填写本案合成交易编号",
  "currency": "USD",
  "amount_minor": 12500,
  "facts": {
    "delivered_at": "2026-09-01T08:00:00Z",
    "recipient_confirmation": "合成签收回执中的实际确认信息"
  }
}
```

`SUPPORTED` 仅说明受支持格式的事实字段及本案关联检查通过，不证明真实性或人工审核通过。缺少签收事实、交易/币种/金额冲突、未送达等得到 `INSUFFICIENT`；未配置内容合同的证据类型为 `NEEDS_MANUAL`。只出现材料代码不能补齐内容要求。原始文件可预览并由人核查。原文件 hash 重复不能当成新材料填满清单。

文件通过 `REGISTER_EVIDENCE` 绑定本案。领域层从服务端对象 provider 获取权威 code/hash/content_check，忽略客户端自报的核查结论；非 SUPPORTED 对象不能绕过送审或审核闸门。修改文件会使相关旧审核/包失效，原版本保留。下载仅限本案已登记版本（包括历史版本），孤立上传对象不能被猜 ID 下载。

## Agent 依据与提案

共享模型上下文包含经过权限过滤的共享消息 ID、当前材料摘录/行位置及内容检查结果，不拼接 OP_INTERNAL 或旧私聊。内部 Agent 可以读取共享往来和内部范围，但回复留在内部。模型解释、核查和起草，确定性工具继续决定权限、期限、金额、状态和可执行提案。

指南库引用与人工批准模式都属于参考知识，不覆盖本案冻结规则。批准模式按同商户、卡组织、原因码、阶段和规则版本筛选，要求脱敏且人工明确批准；待审核候选不能检索。引用保留知识 ID、批准时间和规则版本。验收包括案件 A 真正结案→候选待审时 B 不命中→独立批准→B 的模型上下文真实引用该 ID。

确定性案件计划提案明确 `scope=SHARED` 与 `scope_origin=DETERMINISTIC_CASE_PLAN`。编辑后的命令携带 `proposal_origin`；服务端验证 run/proposal/case/版本/action/owner/scope，审计保存原始数据、实际数据、修改字段及确认人。模型回答不能自行执行提案，也不能提升权限。

## 初始化与运行边界

FastAPI lifespan 中先初始化 disputes、可信身份、Agent，再调用 `initialize_dispute_collaboration(app, db_path)`。它绑定 `state.dispute_collaboration`、`disputes.evidence_objects`、`disputes.collaboration`、`agent.collaboration_provider`，并启动计时器；退出 lifespan 关闭计时器。构造应用不打开数据库。

测试只用隔离数据库、合成文件、脚本模型及独立测试账号；未读取真实密钥，未调用付费模型，未发送外部协作消息。实际企业规则、正式资金和上游接口验证不在这些本地通过证据内。飞书真实测试空间的送达/回流仍须独立授权和联调，不能据门户消息或 callback JSON 宣称完成。

## 新材料与未知内容类型的人工核验

V2.1 应用绑定文件 provider 后，新登记或替换材料必须引用实际上传且属于本案的 `object:` 对象。填写 `synthetic://`、网页地址或文件路径不能代替文件，接口返回 `422 EVIDENCE_FILE_REQUIRED`。旧的仅元数据记录保持历史可读；升级前已成功命令的相同请求仍使用原幂等回执，不能借重放改写材料。

未知材料代码仍先检查正文里的交易编号、币种、金额和矛盾状态。共同事实缺失或冲突时为 `INSUFFICIENT`，必须补正原文；仅当共同事实匹配、缺少该材料类型专用内容合同，才进入 `NEEDS_MANUAL`，并产生本案风控人员的 `CONTENT_REVIEW` 任务。

风控查看已保存正文和行号后，通过普通命令入口执行 `REVIEW_EVIDENCE_CONTENT`。请求必须带当前 `expected_revision` 与 `confirmed=true`，数据为：

```json
{
  "evidence_id": "本案材料 ID",
  "decision": "SUPPORTED",
  "reason": "说明所引用的正文事实如何支持当前材料要求",
  "applicable_facts": ["已保存正文中的准确原句或片段"],
  "locators": ["line:1"]
}
```

`decision` 也可为 `INSUFFICIENT`。服务端核对实际对象、hash、交易关联和材料代码，并要求核验人与上传者不同；每段摘录都必须存在于指定正文行。客户端不能自报核验结论、编造原句、指定其他案件对象，或通过这个动作推翻已知内容合同发现的缺失与冲突。较早保存的未知对象若没有可验证的交易关联事实，需要重新上传，不能直接认定通过。

人工结论随材料保存核验人、理由、摘录、位置和对象版本；原始文件及其自动检查保持不变。核验后仍由商户送审、风控进行正式材料审核、主管独立终审。替换文件会失效旧内容结论及相关审核、冻结包，保留历史版本，并按新文件重新检查。此流程不表示文件真实性鉴定，也不会替代商户意愿或主管批准。

## Agent 读者投影与实际模型探针

Agent 内核可以保留完整的确定性工具观察，返回给读者时必须再次经过权限投影。相似案件引用按当前真实账号的案件参与关系逐案校验，工具步骤的 `matches` 与 `count` 同步过滤。共享模型回答面向多名可能拥有不同案件权限的参与者，因此完全不使用其他案件的私有记录；可使用单独发布且脱敏批准的参考知识。OP 内部模型只使用该操作者当前获准的案件范围。

商户与 SHARED 的 SLA 工具输出、确定性回答及模型上下文只带商户时限，不重新返回案件详情已删除的 internal/external deadline。历史 run 不改写原审计事实，读取时同样投影；历史答案中可识别的无权案件引用和内部时限也遮蔽。新回答的保存与返回使用同一投影，旧私聊依然只读，不自动搬到共享线程。独立账号、历史 run、旧对话和实际注入模型上下文的专项回归在 `tests/application/test_dispute_agent_reader_scope.py`。

2026-09-09 的一次明确授权真实模型探针使用新建隔离数据库、真实 session 和 normalized intake，关闭后台模型事件与飞书。一次 SHARED 请求 HTTP 200，`source=MODEL`、`provider=DEEPSEEK`、实际响应 `model=deepseek-v4-flash`（配置别名 `deepseek-chat`），耗时 8.91 秒，保留 11 条来源引用。检查确认共享往来进入模型输入，OP_INTERNAL 标记与运营私有上下文没有进入模型输入，双方可见同一回答，业务 revision 不变。安全摘要保存在本机 `work/v21-live-agent.json`；该探针不代表飞书真实租户 Gate 5 已通过。
