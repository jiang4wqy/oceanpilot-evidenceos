# OceanPilot V2

**两个操作端、三个参与角色：商户客户端与 OceanPayment 运营端分别嵌入 OceanPilot 案件智能体。**

开发分支：`oceanpilot-v2`，从稳定 `master` 的 `250e7d9` 创建。V2 直接在此分支集成与验收；当前不创建 PR、不合并 master。master 保留原稳定比赛 Demo，后续是否合并单独决定。

上游通知由 OP 受理；OceanPilot 在案件变化后检查规则、材料、期限和相似案件，准备沟通稿与绑定版本的操作提案。商户在客户端确认 Accept / Contest 并提供事实和证据，OceanPayment 完成人工审核、包终审、上游处理与资金核对。两端都能看到智能体做过的工作、待确认事项和持续对话。

> 比赛演示边界：业务演练为合成交易；指南案例库保留原文示例、规则衍生和合成资料的原有分类及来源，不能自动当作生产规则。上游仅 **Mock / Disabled**。金额核对是合成账本记录，不执行退款、扣款或真实提交。Header 角色用于本地演示，不是生产身份认证。材料仅登记合成元数据，未读取真实文件正文。Feishu 签名 callback seam 已实现，真实租户联调未完成，未发送外部消息。

## 运行

Python 3.12；在本机回环地址启动：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
PYTHONPATH=src OCEANPILOT_DB_PATH=work/v2.db \
  .venv/bin/python -m uvicorn oceanpilot.main:create_app \
  --factory --host 127.0.0.1 --port 8002
```

| 入口 | 作用 |
|---|---|
| `/` → `/v2/operations` | OceanPayment 争议运营：案件队列、Agent 协作、复核、提交、结果、资金 |
| `/v2/merchant` | 商户自己的案件列表与待办 |
| `/v2/merchant/cases/{id}` | 商户独立案件页、补证决定与本端 AI 对话 |
| `/v2/operations/cases/{id}` | 运营独立案件页、审核提交与内部 AI 对话 |
| `/v2/operations/library` | 62 条指南参考、28 个模板；26 个适用当前双卡演练建案 |
| `/v2/governance` | 规则来源、角色权限、集成状态、人工审核知识 |
| `/docs` | V2 严格命令 HTTP 合同及兼容 V1 API |
| `/demo`、`/business`、`/admin` | 保留的 V1 历史演示和运维入口 |

工作台中的“演示案例”由 OP 角色生成独立样例，保留旧样例和数据库历史。切换演示角色时，API 会重新检查当前身份、案件所属商户和命令版本。

## 指南案例与双端协作

优先从“Visa / Mastercard 案例库”查阅已上传的提纯资料。文件编号到 074，实际去重后 62 条；每条保留来源、页码、核验状态和冲突。选择可用模板并确认交易字段后，生成有来源快照的独立演练案件。OceanPilot 在新检查及对话中实际检索同卡组织、同原因码的案例依据。

两端通过持久游标自动同步案件与各自的 AI 记录，保留未发送输入。商户对话与运营内部对话分开保存；需要共享的内容通过案件协作消息发送。远端变更会使旧确认失效，不能沿用旧版本执行。

[双端操作指南](docs/v2/dual-workspace-guide.md) · [本轮验收：1840 项通过](docs/v2/dual-surface-acceptance.md) · [来源资料](docs/chargeback-case-library/03_case_library.json)

## 四个 Golden Demo

| 场景 | 初始状态 | 演示重点 |
|---|---|---|
| A 正常抗辩 | OP 已发布商户任务 | Contest → 补齐材料 → 人工审核 → 包终审 → Mock 提交 → 终局 → 核对 → 通知 → 结案 |
| B 缺证阻断 | 商户已 Contest，缺签收与物流材料 | Agent 显示缺口；不能送审或通过，补证后继续 |
| C SLA 风险 | 商户截止时间已过，等待人工升级 | 未响应与 Accept 独立；不推断授权，不自动接受 |
| D 财务异常 | 已 Mock 提交、WON 终局、资金差异 | WON 不等于结案；主管核对差异后，通知商户再关闭 |

[完整演示步骤与命令](docs/v2/demo.md) · [架构、迁移判断和来源边界](docs/v2/architecture-and-migration.md) · [飞书 callback 配置与本地验收](docs/v2/feishu.md)

## 已实现能力

- **多维案件状态：** Stage、Work Status、Merchant Decision、Outcome、Finality、Financial Status 独立保存。
- **明确权限：** OP 建案和运营；Merchant 本商户响应举证；Risk Officer 规则与材料复核；Supervisor 包终审、资金核对与结案；Admin 知识治理。Agent 没有独立提交、终审或结案权限。
- **可追溯规则和计划：** 精确匹配 scheme / channel / reason / stage / 生效日期。内置六条 Mock fixture，只有合成规则使用 72/96/120 UTC 小时演示期限。其他条件进入 NEEDS_CONFIRMATION，旧案保留规则快照。
- **人工复核与冻结包：** 缺必需证据不能通过；材料变化使旧审核和包失效；Risk 审核与 Supervisor 最终确认分离。提交保留版本、digest、技术回执、业务接收与幂等编号。
- **完整后处理：** 非终局进入新阶段并重算规则/SLA；终局后登记借记、贷记、退款及费用，用整数最小货币单位核对。资金未核对、有差异或未通知时不能关闭。
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
5. 真实租户飞书联调、生产认证、部署和运行保障。

这些内容保留为可替换的集成与规则边界。当前版本适合本地比赛演示与工程验收，未声称生产上线。

## 保留的 V1 资料

[原 README 与运行范围](docs/v2/v1-readme.md) · [原架构](docs/architecture.md) · [历史提交材料](docs/submission/registration-copy.md) · [DeepSeek 配置](docs/deepseek-setup.md)

公共仓库用于比赛评审；未授予复用许可。历史报告、截图和数据需求保留原日期口径，不能替代 V2 当前代码和验收记录。
