# OceanPilot 案件诊断 Agent 黄金演示交接文档

> 更新时间：2026-08-16（Asia/Shanghai）
> 状态：黄金案件主链已实现、已通过聚焦测试并完成本地 DeepSeek Live 浏览器联调
> 数据边界：本文所有案件、材料、审核人、回执和审计编号均为 Synthetic / Mock

## 1. 接手者先看这里

- GitHub 仓库：<https://github.com/jiang4wqy/oceanpilot-evidenceos>
- 本地仓库：`C:\Users\lenovo\Documents\Codex\2026-08-04\zhao\work\oceanpilot-master`
- 当前工作分支：`wip/rules-ui-evidence-handoff-20260815`
- 目标分支：`master`
- 本地演示入口：<http://127.0.0.1:8016/demo>
- 本次交接时监听端口为 `8016`、PID 为 `78568`；PID 只是当前会话数据，重启后会变化。
- 最终批准规格：[`docs/superpowers/specs/2026-08-16-case-diagnosis-agent-golden-demo-design.md`](superpowers/specs/2026-08-16-case-diagnosis-agent-golden-demo-design.md)
- DeepSeek 配置指南：[`docs/deepseek-setup.md`](deepseek-setup.md)

本次实现的核心不是让大模型替代支付规则，而是把模型放在确定性案件内核之上：

```text
操作人员输入 / 案件事件
        ↓
确定性案件快照（阶段、证据、责任域、人工闸门）
        ↓
DeepSeek / Offline Fallback（理解、总结、解释、生成提案）
        ↓
固定 JSON 校验 + 后端确定性字段覆盖
        ↓
页面展示分析、引用、下一步和可视化轨迹
        ↓
人工确认后才写审核决定；最终仍只进入本地 mock connector
```

## 2. 产品目标与不可跨越的边界

比赛演示主线已经收敛为：

`描述异常 → 建案 → 确认原因 → 补齐材料 → AI 分析 → 输入审核结论 → 生成拟写入卡 → 人工确认落库 → 材料包 → 最终人工审批 → Mock 回执 → 审计`

必须保持以下口径：

- OceanPilot 的长期愿景是支付运营、争议协作、风险提示、规则知识、审计和商户成功的一体化智能体。
- 当前可现场证明的纵向切片是“支付异常 / 拒付争议处理”，不能宣称全平台生产能力已经完成。
- DeepSeek 只负责理解自然语言、总结材料、解释判断、生成下一步和审核提案。
- 阶段、证据缺口、材料就绪度、责任团队、引用允许清单、人工闸门和 CAS revision 均由确定性内核或后端校验决定。
- 输入“审核通过”不会直接写数据库；只有点击“确认写入案件”才会提交审核决定。
- 不连接真实支付、退款、风控放行、资金操作或卡组织提交。
- 不读取 Synthetic 演示文件正文，不上传对象存储；资料弹窗只记录已经定义的 `evidence_code`。
- 不展示模型思维链，只展示经过定义的执行轨迹。

## 3. 黄金演示案件的完整数据

### 3.1 固定业务身份

| 字段 | 值 |
|---|---|
| 模板 | `Visa 10.4 · 非本人交易` |
| 内部争议原因 | `FRAUD_CARD_NOT_PRESENT` |
| 卡组织 | `VISA` |
| 精确规则版本 | `visa-10-4-demo-v1` |
| 技术背景引用 | `oceanpayment-threeds-doc` |
| 责任团队 | `RISK` / 风控团队 |
| 人工闸门 | 强制开启；资料齐全也不能由 AI 自动通过 |
| 数据类型 | `Synthetic` |

### 3.2 六项内部准备清单

| 顺序 | evidence code | 页面标签 | 作用 |
|---:|---|---|---|
| 1 | `transaction.receipt` | 交易收据 | 模板初始已有；卡组织材料包映射 |
| 2 | `auth.threeds` | 3DS 认证结果 | 卡组织材料包映射；技术背景引用 |
| 3 | `auth.avs_result` | AVS 地址验证结果 | 只属于 OceanPilot 内部准备项 |
| 4 | `auth.cvv_result` | CVV 校验结果 | 只属于 OceanPilot 内部准备项 |
| 5 | `auth.device_ip_match` | 设备/IP 匹配 | 卡组织材料包映射 |
| 6 | `history.prior_transactions` | 历史交易记录 | 卡组织材料包映射 |

Visa 10.4 材料包只包含四项：3DS、设备/IP、历史交易、交易收据。AVS/CVV 不得描述为 Visa 10.4 官方强制证据。

### 3.3 本次真实浏览器联调记录

| 数据 | 值 |
|---|---|
| 案件 ID | `c033a407-2654-444d-adf8-a3a5d68a7049` |
| 审核前 revision | `8` |
| 审核后 revision | `9` |
| 审核输入 | `审核通过，已核对 3DS、AVS/CVV、设备/IP 关联、历史交易与交易收据，全部 Synthetic 材料内容一致。` |
| Synthetic 审核人 | `judge_reviewer_01` |
| 审核写入审计 ID | `1c3d9592-7293-46cc-94c3-50a9798f71e5` |
| Mock 提交回执 | `mock-sub-0001` |
| 模型运行模式 | `DeepSeek Live · deepseek-chat` |

案件基础审计在页面中显示为：

1. 版本 0：案件创建；
2. 版本 1：争议原因识别；
3. 版本 2：争议原因确认；
4. 版本 3：交易收据；
5. 版本 4：3DS；
6. 版本 5：AVS；
7. 版本 6：CVV；
8. 版本 7：设备/IP；
9. 版本 8：历史交易；
10. 版本 9：专用审核决定确认；专用审核审计 ID 见上表。

这些 ID 只存在本机被 Git 忽略的 Synthetic SQLite 数据库中，不会随代码上传。新环境应从空数据库重新演示，不要依赖这些固定 ID。

## 4. 引用数据与真实性限制

### 4.1 Visa 10.4 演示规则

- `reference_id`：`visa-10-4-demo-v1`
- 标题：`VISA 10.4 · 非本人交易（无卡环境）`
- 来源：*Dispute Management Guidelines for Visa Merchants*
- 版本：`June 2024`
- 定位：`Condition 10.4 — Other Fraud, Card-Absent Environment`
- 状态：`UNVERIFIED_SUMMARY`
- 限制：商户指南演示摘要；不自动判定 CE3.0、3DS 责任转移、正式申诉资格或官方期限。

### 4.2 Oceanpayment 3DS 技术背景

- `reference_id`：`oceanpayment-threeds-doc`
- 来源：<https://dev.oceanpayment.com/en/docs/compliance-and-security/threeds/>
- 类型：`TECHNICAL_CONTEXT`
- 作用：解释为什么要保留 3DS 认证上下文。
- 限制：不参与卡组织资格、责任转移或期限判断。

规则知识库 schema 已升级到 v2，当前测试固定为 10 条规则，其中 3 条 `DEMO_MAPPED`。旧 v1 只读种子库会重建为 v2，不删除案件、证据、Agent turn 或审核数据。

## 5. 已完成的实现

### 5.1 DeepSeek Provider 与固定 JSON 合同

- 新增 OpenAI-compatible DeepSeek Provider，只从环境变量读取凭据。
- `OCEANPILOT_MODEL_PROVIDER` 支持 `claude` 和 `deepseek`。
- LOW 直接调用所选外部模型；MEDIUM 先脱敏；HIGH 优先本地模型，否则使用脱敏外部兜底。
- Provider 不可用、超时、JSON 无效或安全校验失败时使用确定性 fallback。
- Intake、Assess、Evidence、Prevention、Packager、Appeal 和 Case Copilot 均使用固定 JSON 输出约束。
- 模型输出不允许改变确定性字段；页面核心评估区不再直接显示可能包含“胜诉概率”的自由模型说明。

### 5.2 Agent API

已实现：

- `POST /api/v1/agent/turns`
  - 无 `case_id`：自然语言建案；
  - 有 `case_id`：分析现有案件，不重复建案；
  - 支持 `card_network` 和自动触发类型；
  - 返回运行模式、案件 revision、审核状态、材料摘要、判断原因、引用、审核提案和执行轨迹。
- `POST /api/v1/agent/cases/{case_id}/review-decisions`
  - 按 `source_turn_id` 确认拟写入审核决定；
  - 首次成功为 `CREATED`，重复确认是 `REPLAYED`；
  - stale revision 或跨案件 turn 返回冲突；
  - 确认成功后 revision 加一并返回审核审计 ID。

完整 schema 和示例 JSON 不在此重复，直接查看批准规格和 [`src/oceanpilot/api/agent.py`](../src/oceanpilot/api/agent.py)。

### 5.3 审核持久化

SQLite 非破坏性增加三张表：

- `chargeback_agent_turns`
- `chargeback_review_decisions`
- `chargeback_review_audit`

已实现：

- Agent turn、完整响应 JSON 和审核提案持久化；
- 自动分析按案件 revision 重放；普通 `USER_MESSAGE` 不参与自动快照重放；
- 同一 `source_turn_id` 幂等；
- stale revision、跨案件确认、未知 turn 和非法审核状态拒绝；
- 案件 revision 更新、审核决定和专用审核审计在一个事务中提交；
- SQLite 重新打开后仍能读取最新审核状态。

### 5.4 单案 Agent 与资料提交页面

- Agent 已从案件中心列表移到单个“案件诊断”页右侧。
- 案件中心只保留“进入 AI 分析”入口，不再存在第二套聊天工作台。
- 新建案件后直接进入单案诊断并自动分析。
- Agent 页面展示运行模式、触发原因、revision、案件总结、审核状态、材料内容、判断原因、责任域、下一步、引用和执行轨迹。
- 输入审核结论只生成“拟写入案件”卡，卡片提供“确认写入案件 / 修改输入 / 取消”。
- 原因确认、每次资料提交和审核确认后自动重新分析。
- 自动分析进行中时，人工输入会进入单条队列，不再被静默丢弃；队列已占用时新输入保留并给出明确提示。
- 原因尚未确认时显示“待确认原因 / 确认原因后生成材料清单”，不再错误显示“资料已齐全”。
- 资料补交必须经过独立弹窗：选择演示文件名、核对边界、明确提交、三阶段进度、成功回执。
- 资料持久化成功后立即释放弹窗锁；DeepSeek 重分析继续独立执行，因此成功回执出现后可以立刻关闭弹窗。

### 5.5 材料包与最终人审

- 黄金案件能够生成 `VISA 10.4` Synthetic 材料包。
- 页面清晰区分六项内部准备清单和四项卡组织打包摘要。
- 卡组织规则必须由操作人员明确选择，不按原因码猜测。
- 最终提交必须填写复核人并点击“人工确认并模拟提交”。
- 只进入 in-process mock connector，返回 mock receipt；不会访问真实卡组织。

## 6. 本地启动与密钥配置

不要把密钥写入代码、Markdown、测试、命令历史或 Git。`.env` 已被 `.gitignore` 忽略。

```powershell
Copy-Item .env.example .env
```

在本机 `.env` 中填写值，文档和代码中只保留变量名：

```dotenv
OCEANPILOT_MODEL_PROVIDER=deepseek
OCEANPILOT_CHARGEBACK_LIVE_MODEL=1
DEEPSEEK_API_KEY=<仅写本机密钥>
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn oceanpilot.main:create_app `
  --factory --env-file .env --host 127.0.0.1 --port 8016
```

打开：<http://127.0.0.1:8016/demo>

若不配置密钥，系统应显示 `Offline Fallback`，但确定性业务主线仍应可演示。

## 7. 推荐现场演示脚本

1. 进入案件中心，点击“新建案件”。
2. 选择 `Visa 10.4 · 非本人交易`，确认创建。
3. Agent 自动分析案件；明确确认 `FRAUD_CARD_NOT_PRESENT`。
4. 页面登记模板已有的交易收据，显示其余五项缺口。
5. 对 3DS、AVS、CVV、设备/IP、历史交易分别打开资料弹窗，使用 Synthetic 文件并明确提交。
6. 到达 6/6 后输入审核通过说明；重点展示它只生成拟写入卡。
7. 点击“确认写入案件”；展示新 revision、审核通过状态和审核审计 ID。
8. 明确选择 Visa；展示 `visa-10-4-demo-v1` 与 `oceanpayment-threeds-doc` 两条引用及限制。
9. 进入“评估与材料包”，展示六项内部清单、四项 Visa 打包摘要和“非胜诉概率”口径。
10. 输入复核人，点击“人工确认并模拟提交”，展示 mock receipt 和案件审计。

## 8. 验证证据

本次交接前最后一次聚焦回归：

```text
39 passed, 1 skipped
```

覆盖：

- `tests/repository/test_case_review_store.py`
- `tests/api/test_agent_api.py`
- `tests/knowledge/test_rule_repository.py`
- `tests/api/test_demo_page.py`

跳过项是 `DEEPSEEK_API_KEY` 未注入 pytest 进程时的 live 用例；这不是失败。本地浏览器已另行验证 `DEEPSEEK_LIVE`。

页面专项测试：

```text
17 passed
```

静态检查：

```text
ruff: PASS
git diff --check: PASS
```

本地浏览器真实验证结果：

- 忙碌时审核输入显示“已排队”，随后自动执行；
- 生成“拟写入案件 · 审核已通过”；
- 确认后 revision `8 → 9`；
- 返回审核审计 ID；
- `REVIEW_CONFIRMED` 自动重分析；
- Visa 双层引用数量为 2；
- 材料包摘要为 4 项；
- Mock 提交返回 `mock-sub-0001`；
- 页面核心评估区不再显示“高概率胜诉”。

## 9. 本次上传的文件范围

### 9.1 代码与配置

- `.env.example`、`pyproject.toml`
- `src/oceanpilot/main.py`
- `src/oceanpilot/api/agent.py`
- `src/oceanpilot/api/demo.py`
- `src/oceanpilot/application/case_copilot.py`
- `src/oceanpilot/application/case_review.py`
- `src/oceanpilot/application/model_output.py`
- `src/oceanpilot/application/chargeback_agents.py`
- `src/oceanpilot/application/chargeback_packager.py`
- `src/oceanpilot/application/chargeback_appeal.py`
- `src/oceanpilot/adapters/model/deepseek.py`
- `src/oceanpilot/adapters/model/composition.py`
- `src/oceanpilot/adapters/model/local.py`
- `src/oceanpilot/adapters/persistence/chargeback_schema.py`
- `src/oceanpilot/adapters/persistence/chargeback_review_sqlite.py`
- `src/oceanpilot/adapters/knowledge/rule_schema.py`
- `src/oceanpilot/adapters/knowledge/rule_seed.py`
- `src/oceanpilot/adapters/knowledge/rule_repository.py`

### 9.2 测试

- `tests/api/test_agent_api.py`
- `tests/api/test_demo_page.py`
- `tests/repository/test_case_review_store.py`
- `tests/knowledge/test_rule_repository.py`
- `tests/model/test_deepseek_provider.py`
- `tests/model/test_deepseek_live.py`
- `tests/model/test_model_composition.py`
- 六个既有 chargeback agent 测试文件中的固定 JSON 合同测试。

### 9.3 文档

- `README.md`
- `docs/architecture.md`
- `docs/security/deployment-tiers.md`
- `docs/deepseek-setup.md`
- `src/oceanpilot/README.md`
- `src/oceanpilot/adapters/README.md`
- 本交接文档。

最终黄金规格已经在提交 `251396a` 中；本次推送分支时会一并上传。

## 10. 明确未上传的并行工作

共享工作树中还存在其他线程的 submission 文档、DOCX、截图和构建脚本修改。这些内容没有经过本任务的完整验收，不应夹带进本次功能提交：

- `docs/submission/2026-08-16-oceanpilot-40-final-proposal.md`
- `docs/submission/OceanPilot-40强完整参赛方案.docx`
- `docs/submission/assets/*` 的并行截图修改
- `scripts/build_final_proposal_docx.py`

未跟踪的 `docs/superpowers/specs/2026-08-16-case-center-copilot-evidence-submit-design.md` 描述的是早期“案件中心右侧 Agent”方案，已经被最终批准的“单案诊断页 Agent”规格取代，因此本次不提交。

## 11. 尚未完成或值得继续优化的部分

按优先级排序：

1. **卡组织持久化。** 当前案件模型没有持久保存 `card_network`。从黄金模板开始连续演示时 Visa 上下文存在；刷新或重新打开历史案件后，需要操作人员再次明确选择 Visa 才会显示两条引用。不要通过原因码猜测卡组织。下一步应采用非破坏性 schema 扩展持久化明确选择值。
2. **审核审计的重新打开展示。** 确认端点即时返回 `audit_event_id`，数据库也保存专用审核审计，但重新打开案件时页面只恢复审核状态，不恢复显示最新审核审计 ID。可增加只读查询或在 Agent 响应中附带最新决定元数据。
3. **完整 CI。** 当前已跑聚焦测试和 Ruff；推送后仍需确认 GitHub Actions 对 Python 3.12 全量测试为绿色。
4. **Clean clone。** 应在新目录执行 clone、安装、空 SQLite 启动和完整演示，证明没有依赖本机残留数据。
5. **飞书真实群联调。** 本次只完成本地 Web 黄金主链；真实飞书事件、重复事件、卡片点击和最终展示排练仍需要对应测试应用凭据和群聊环境。
6. **现场截图与视频。** 应从空数据库重新跑一遍并截取：1/6 缺口、资料弹窗、6/6 人审、拟写入卡、双层引用、四项材料包、mock 回执、审计。
7. **来源核验。** `UNVERIFIED_SUMMARY` 必须保持。若要升级为已核验规则，需要团队成员完成来源文件、版本、定位和引用权利的正式复核，不能只改标签。

## 12. 接手者操作清单

1. `git fetch origin`，检出 `wip/rules-ui-evidence-handoff-20260815`。
2. 阅读最终规格和本交接文档，不再按早期“案件中心右侧 Agent”方案修改布局。
3. 确认 `.env` 未被 Git 跟踪；不要读取、打印或复制现有密钥。
4. 运行聚焦测试，再运行全量 pytest。
5. 从空 Synthetic SQLite 数据库执行十步演示脚本。
6. 核对六项内部清单与四项 Visa 打包摘要的区别。
7. 核对输入“审核通过”在点击人工确认前没有改变 revision。
8. 核对重复确认返回 `REPLAYED`，stale revision 返回 409。
9. 核对无卡组织时引用为空；明确选择 Visa 后恰好出现两条允许引用。
10. CI 全绿后再合并到 `master`。

## 13. 建议使用的 skills

- `brainstorming`：任何新的业务行为、字段或页面改动前先明确设计和边界。
- `diagnosing-bugs`：处理异步队列、SQLite CAS、重放或页面状态不同步问题。
- `ui-ux-pro-max`：修改案件诊断页、弹窗、无障碍状态或比赛截图前做 UX 检查。
- `tdd`：新增持久化字段、审核审计查询或卡组织恢复逻辑时先写回归测试。
- `handoff`：再次跨会话或跨开发者移交时更新交接文档，并继续脱敏所有密钥和个人信息。

## 14. 安全提醒

- 不要读取、打印、提交或在对话中再次粘贴 DeepSeek 密钥。
- 不要把 `.env`、`work/*.db`、WAL/SHM、Uvicorn 日志或 Synthetic 本地附件加入 Git。
- 不要向模型发送真实卡号、CVV 原值、密码、Token、个人身份信息或原始支付日志。
- 不要把 Mock 回执描述为真实 Visa 提交结果。
- 不要把内部 15 天准备窗口描述为 Visa 官方申诉期限。
