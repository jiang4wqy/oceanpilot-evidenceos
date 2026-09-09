# OceanPilot V2.1

**两个操作端、三个参与角色：商户客户端与 OceanPayment 运营端分别嵌入 OceanPilot 案件智能体。**

开发分支：`oceanpilot-v2`，从稳定 `master` 的 `250e7d9` 创建。V2 直接在此分支集成与验收；当前不创建 PR、不合并 master。master 保留原稳定比赛 Demo，后续是否合并单独决定。

上游通知由 OP 受理；OceanPilot 在案件变化后检查规则、材料、期限和相似案件，准备沟通稿与绑定版本的操作提案。商户在客户端确认 Accept / Contest 并提供事实和证据，OceanPayment 完成人工审核、包终审、上游处理与资金核对。两端都能看到智能体做过的工作、待确认事项和持续对话。

> V2.1 当前处于验收阶段，进度与限制见 [验证记录](docs/v2/v21-validation.md)。使用服务端独立账号、同案共享线程和实际文件内容检查。交易、账务和上游仍为 **Synthetic / Mock / Disabled**；指南参考不能自动当作生产规则。飞书双向 outbox 与签名回调已完成本地测试，真实测试群闭环尚未验证。

## 运行

Python 3.12；在本机回环地址启动：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
PYTHONPATH=src OCEANPILOT_DB_PATH=work/v2.db \
  .venv/bin/python -m uvicorn oceanpilot.main:create_app \
  --factory --host 127.0.0.1 --port 8002
```

首次启动前，在将要使用的争议数据库中创建独立演示账号：

```bash
PYTHONPATH=src .venv/bin/python -m oceanpilot.v21_accounts \
  --db work/oceanpilot-chargeback.db --output work/v21-accounts.json
```

密码只写入指定本地文件。上述数据库路径对应默认配置；如设置 `OCEANPILOT_CHARGEBACK_DB_PATH`，账号命令的 `--db` 必须使用相同路径。登录 `/v2/login`；同时演示商户与运营时使用独立浏览器配置文件，普通标签页会共用会话。已有默认账号不会被命令覆盖。

| 入口 | 作用 |
|---|---|
| `/v2/login` | 独立账号登录，URL／客户端角色头不授予权限 |
| `/` → `/v2/operations` | OceanPayment 争议运营：案件队列、Agent 协作、复核、提交、结果、资金 |
| `/v2/merchant` | 商户自己的案件列表与待办 |
| `/v2/merchant/cases/{id}` | 商户独立案件页、补证决定与本案共享沟通 |
| `/v2/operations/cases/{id}` | 运营独立案件页、审核提交、共享沟通与明确隔离的内部讨论 |
| `/v2/operations/library` | 62 条指南参考、28 个模板；26 个适用当前双卡演练建案 |
| `/v2/governance` | 规则来源、角色权限、集成状态、人工审核知识 |
| `/v2/director` | 隔离的演示准备页：管理账号和登记合成交易，不代替业务决策 |
| `/docs` | V2 严格命令 HTTP 合同及兼容 V1 API |
| `/demo`、`/business`、`/admin` | 保留的 V1 历史演示和运维入口 |

新案由导演登记合成交易，再由运营接收标准化上游事件。正式争议经关联核验后才立案；预警／查询保留事件，无法匹配的进入待核对队列。旧直接建案和演示 API 返回明确迁移提示，不能绕过交易关联核验。

## 指南案例与双端协作

优先从“Visa / Mastercard 案例库”查阅已上传的提纯资料。文件编号到 074，编号并不连续，实际收录 62 条；每条保留来源、页码、核验状态和冲突。资料选择与交易登记、上游事件核验分开进行，已有案件保留来源快照。OceanPilot 在新检查及对话中实际检索同卡组织、同原因码的案例依据。

两端通过持久游标同步案件、共享消息和阅读状态，保留未发送输入。共享线程对本案参与者与 OceanPilot 可见，内部讨论单独授权；旧私聊只读并保留原可见范围。普通消息不修改审批版本，材料、规则与结果等业务变化仍使旧确认失效。

[V2.1 双端操作指南](docs/v2/dual-workspace-guide-v21.md) · [V2.1 验证进度](docs/v2/v21-validation.md) · [旧 V2 验收记录](docs/v2/dual-surface-acceptance.md) · [来源资料](docs/chargeback-case-library/03_case_library.json)

## 四个 Golden Demo

| 场景 | 初始状态 | 演示重点 |
|---|---|---|
| A 正常抗辩 | OP 已发布商户任务 | Contest → 补齐材料 → 人工审核 → 包终审 → Mock 提交 → 终局 → 核对 → 通知 → 结案 |
| B 缺证阻断 | 商户已 Contest，缺签收与物流材料 | Agent 显示缺口；不能送审或通过，补证后继续 |
| C SLA 风险 | 商户截止时间已过，等待人工升级 | 未响应与 Accept 独立；不推断授权，不自动接受 |
| D 财务异常 | 已 Mock 提交、WON 终局、资金差异 | WON 不等于结案；主管核对差异后，通知商户再关闭 |

上表保留四种演练目标；V2.1 使用独立身份、合成交易登记和实际文件完成这些流程。旧快捷生成命令仅用于历史领域 fixtures，不作为新版 HTTP 入口。

[旧 V2 演示步骤](docs/v2/demo.md) · [V2.1 来源与验收矩阵](docs/v2/v21-requirements.md) · [飞书配置与本地验收](docs/v2/feishu.md)

## 已实现能力

- **多维案件状态：** Stage、Work Status、Merchant Decision、Outcome、Finality、Financial Status 独立保存。
- **明确权限：** OP 建案和运营；Merchant 本商户响应举证；Risk Officer 规则与材料复核；Supervisor 包终审、资金核对与结案；Admin 知识治理。Agent 没有独立提交、终审或结案权限。
- **可追溯规则和计划：** 精确匹配 scheme / channel / reason / stage / 生效日期。内置六条 Mock fixture，只有合成规则使用 72/96/120 UTC 小时演示期限。其他条件进入 NEEDS_CONFIRMATION，旧案保留规则快照。
- **人工复核与冻结包：** 缺必需证据不能通过；材料变化使旧审核和包失效；Risk 审核与 Supervisor 最终确认分离。提交保留版本、digest、技术回执、业务接收与幂等编号。
- **完整后处理：** 非终局明确区分同阶段等待、核验、行动与有依据的新阶段；未知结果不能直接终局。终局后登记借记、贷记、退款及费用，用整数最小货币单位核对。资金未核对、有差异、通知过期或人工作业未解决时不能关闭。
- **真实文件内容：** UTF-8 TXT／JSON／单行交易 CSV 上传、哈希、版本、正文与事实定位。未知类型须由独立风控核验原文摘录与行号，只有引用的材料不能填满当前清单。
- **同案协作：** Portal、标准化 Feishu 事件进入同一 timeline/audit。飞书使用签名、token、时窗、可信商户与聊天绑定、不透明卡片引用和持久化回执。
- **知识治理：** 结案后提取脱敏候选，独立 Admin 人工审核；只有批准候选可用于相似模式检索。
- **持久化安全：** 新增 V2 SQLite 表保留 V1；案件、revision、审计、幂等命令回执在同一事务中提交，支持重启恢复和并发版本冲突拒绝。

**OceanPilot 案件智能体：** 每次案件命令提交后，六项工具检查、缺口、草稿和提案都保存为独立运行记录；实际业务命令继续检查确认人、当前版本与角色权限。启用 DeepSeek 后，关键案件事件在后台触发模型解读，用户也可直接追问和要求起草文本。界面区分规则工具、真实模型和失败降级，显示实际返回的模型名称。相似案件限定同商户；外部模型只接收经过检查与脱敏的问题及必要案件上下文。

默认离线运行，不需要密钥。启用真实模型时在本机被 Git 忽略的 `.env` 中设置 `DEEPSEEK_API_KEY`、`OCEANPILOT_MODEL_PROVIDER=deepseek`、`OCEANPILOT_CHARGEBACK_LIVE_MODEL=1`，启动命令增加 `--env-file .env`。工具观察立即完成，后台模型请求不会阻塞材料登记。详情见 [Agent 协作与验证](docs/v2/agent-workflow.md)。

## 测试与复现

```bash
PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider -q
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/python -m compileall -q src tests
PYTHONPATH=src .venv/bin/python scripts/eval_dispute_v2.py
```

[验收记录](docs/v2/acceptance.md) 将测试结果与合成 benchmark 分开报告。规则匹配、来源覆盖、缺证检测、危险动作阻挡、状态转换、版本安全、SLA 和审计测试只说明所列 fixtures 上的行为，不代表生产业务效果。

V2 默认使用 `OCEANPILOT_V2_UPSTREAM_MODE=mock`；设为 `disabled` 后仍能查看、复核和制作包，最终模拟提交将被拒绝。任何其他 mode 在启动时拒绝，未提供生产提交适配器。

## 仍需企业确认

1. 各渠道的 OceanPayment 角色及真实争议来源字段。
2. 商户接受/抗辩授权、未响应处置、正式规则与 SLA。
3. 上游提交对象、技术/业务回执、结果和阶段映射。
4. 财务流水、退款、费用、币种和净影响的正式核对口径。
5. 真实租户飞书联调、企业 SSO／生产部署和运行保障。

这些内容保留为可替换的集成与规则边界。当前版本适合本地比赛演示与工程验收，未声称生产上线。

## 保留的 V1 资料

[原 README 与运行范围](docs/v2/v1-readme.md) · [原架构](docs/architecture.md) · [历史提交材料](docs/submission/registration-copy.md) · [DeepSeek 配置](docs/deepseek-setup.md)

公共仓库用于比赛评审；未授予复用许可。历史报告、截图和数据需求保留原日期口径，不能替代 V2 当前代码和验收记录。
