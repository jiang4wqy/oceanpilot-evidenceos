# 飞书全群知识助手：当前生产入口

2026-09-14 产品负责人确认：群机器人只做面向全群的知识库问答；具体案件和业务操作全部留在登录后的网站。此范围替代 #65 原先的群内案件操作验收。网页的商户、运营、风控和风控经理权限保持不变。

## 数据与能力边界

机器人只有公开知识对象和独立消息队列，没有案件、账号、附件、业务命令或内部讨论服务的引用。所有人使用统一帮助与 `/v2/login` 按钮。网站自行鉴权；不宣称飞书 SSO 或飞书托管。旧业务卡片点击及网页上的旧飞书案件 outbox 调用被生产入口拒绝。

文字问题需要已授权群和 @bot；明确授权的单聊可不带 @。群里的个人身份不授予案件权限。附件不会下载或解析，具体案件、敏感输入和业务指令被引导到网站。敏感文本模式检测是辅助防线，不是完整脱敏证明；主要隔离来自机器人无法访问私有业务数据。

知识清单必须逐条包含 `visibility=PUBLIC_GROUP`、`approved=true`、非空 `approval_reference`、来源、版本与正文。仅接受 `PRODUCT_GUIDE` 或 `PUBLIC_REFERENCE`，不加载运行案件或原先同商户的脱敏知识。批准意味着允许对**整个群**公开，不仅是作者可见或完成脱敏。知识源应由负责人核实其事实、适用范围与公开许可。

`feishu-public-knowledge.example.json` 是待审核模板，不是已经批准的语料。默认没有公开语料，不会自动把仓库的全部规则／参考案例公开。

## 本机配置

签名与握手仍使用 `FEISHU_APP_ID`、`FEISHU_ENCRYPT_KEY`、`FEISHU_VERIFICATION_TOKEN`。新配置与旧商户绑定完全独立：

```text
OCEANPILOT_FEISHU_PUBLIC_KNOWLEDGE_PATH=/absolute/private/path/public-knowledge.json
OCEANPILOT_FEISHU_PUBLIC_GROUPS_JSON={"groups":[{"tenant_key":"synthetic-tenant","chat_id":"synthetic-chat","authorized":true,"allow_replies":true,"authorization_reference":"explicit-owner-approval"}]}
OCEANPILOT_FEISHU_PUBLIC_OUTBOUND=authorized-test
OCEANPILOT_FEISHU_KNOWLEDGE_MODEL=enabled
```

上面仅是结构示例，真实标识和凭据仅放本机配置。外发还需要 `FEISHU_APP_SECRET`；群授权和回复许可必须明确，旧 `OCEANPILOT_V21_FEISHU_TEST_TARGETS_JSON` 不生效。模型开关独立显式开启，只复用网站已配置的模型 provider，不给模型业务服务或工具。缺少模型配置时仍可做检索摘录，但不会标成 AI 生成。

当前检索为词项／中文双字片段匹配，最多返回三个获准来源，不宣称向量检索。模型只接收通过保守检查的问题和检索到的公开来源；只允许引用已检索来源，工具调用、未知引用、敏感输出或格式错误退回来源摘录。这不能保证所有模型结论在语义上都正确，仍需实际问题集核验。

回答状态：`HELP`、`WEBSITE_HANDOFF`、`NO_MATCH`、`RETRIEVAL_ONLY`、`MODEL_WITH_RETRIEVAL`、`RETRIEVAL_FALLBACK`。卡片明确区分模型答案、未调用模型的摘录和模型失败后的摘录。

## 消息队列与恢复

生产 initializer 在业务数据库同级创建独立 `feishu-public-knowledge.db`，不访问业务表。签名验证在任何分发之前执行。回调只入队，模型和飞书调用在后台进行，避免把模型延迟计入回调握手。

队列保存域隔离 event/group 哈希、公开批准依据和语料指纹。待处理问题和 provider 原消息标识使用从 Encrypt Key 域隔离派生的 AES-GCM 密钥加密；被拒问题直接替换为固定网站引导请求，不保存原文。密钥不写数据库。答案和实际 provider 回执留在私有队列供验收，不上传 GitHub。

重复事件返回已有状态；相同 event ID 改变内容返回冲突。固定 event 哈希用作 provider UUID；发送中的工作不会被其他 worker 抢占重发。超时或崩溃中的发送变为 `UNCERTAIN`，不自动重试，也不伪造 `SENT`。过期准备任务变为 `BLOCKED`，保留人工诊断而非无限循环。当前没有公开重试 API。

发出前再次检查群授权和语料指纹。撤销批准／更新语料会阻断旧待发工作；不要通过改数据库绕过。修改群配置需重启 A 管理的服务，已发出的群消息不能因后续撤销自动收回。使用新问题验证新的批准语料，不能把未知发送结果简单当作失败重发。

## 验收仍须真实租户完成

必须分别记录：获准群问题、实际回复及 provider 回执、来源引用、无匹配／模型失败、越权群／旧卡片／附件拒绝、重复与重启、网站两种账号登录和独立 C 验收。测试里的模拟回执不满足这些条件。

演示候选流程：全群通用问题 → 引用公开来源的回答 → 打开网站登录 → 用既有账号进入授权工作台。没有获得可公开语料批准或没有真实回执时，不能宣称公开知识 AI 已上线。
