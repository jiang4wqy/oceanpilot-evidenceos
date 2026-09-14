# V2.1 数据取源与案件起点

本清单记录当前代码中“案例知识”、“演练模板”和“运行案件”的实际读写边界。它们不是同一类数据，不能互相覆盖。

## 取源清单

| 用途 | 实际来源 | 读取者 | 边界 |
|---|---|---|---|
| 完整案例与来源知识 | `src/oceanpilot/data/chargeback_case_library/03_case_library.json` | `/api/v2/case-library`、运营案例库、Agent 参考检索 | 只读参考；不自动成为案件规则或生产事实 |
| 可执行演练模板 | `src/oceanpilot/data/chargeback_case_library/06_seed_cases.json` | 案例库的“创建演练案件”入口 | 只提供场景预览；交易、金额、币种和时间由本次演练显式确认 |
| 合成交易 registry | V2 争议 SQLite 的 `v21_synthetic_transactions` | 导演页、标准化接收服务 | 导演只登记测试事实；不能代替运营接收或业务审批 |
| 标准化上游事件 | V2 争议 SQLite 的 `v21_intake_events` | `/api/v2/intake/events` | 校验交易归属、去重与事件关联后才可立案 |
| 运行案件 | V2 争议 SQLite 的 `v2_dispute_cases` 及关联表 | OP/商户页面、案件 Agent、审核与提交命令 | 唯一的当前状态来源；案例说明和预期结果不得覆盖 |
| 已确认规则快照 | 运行案件的 `rule_snapshot` | 计划、权限门禁、材料清单和后续阶段 | 结构化来源只作候选；需风控明确确认后才冻结到本案 |
| 旧 V1 数据 | `Settings.db_path` 对应的 core SQLite | 保留的 `/demo`、`/business`、`/admin` | V2 案件主链不从 V1 表读取争议状态 |

## 加载诊断

`/api/v2/governance` 只向管理员和主管返回 `data_sources`，并在治理页展示：

- 03/06 的实际路径、schema、SHA-256 和记录数；
- evidence level、核验状态、来源冲突和数据缺口数；
- core、V2 争议和规则 SQLite 的实际路径、用途、可用状态与文件大小；
- 本次启动的加载错误。当核心案例文件无法加载或 schema 不受支持时，服务仍会 fail closed，不会生成伪造的空资料库。

## 从案例创建新案的轨迹

1. 运营人员在案例库选择一个明确允许演练的模板。
2. 导演登记本次演练的合成交易；运营人员从标准化事件入口接收它。
3. 接收服务核对 registry、去重并生成新案件 ID，保存 `template_id → source_event_id → case_id` 关系。
4. 新案件初始必须是 `RECEIVED / NONE / UNKNOWN / NOT_FINAL`，证据、提交和资金事件均为空。
5. 同卡组织和原因码的结构化参考以 `rule_candidates` 显示，保留版本、核验和冲突状态。候选不携带来源案例结局，也不会自动变成本案规则。
