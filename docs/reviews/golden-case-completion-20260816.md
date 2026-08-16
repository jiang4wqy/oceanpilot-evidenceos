# OceanPilot 黄金案件完整承接验收报告

日期：2026-08-16  
分支：`agent/golden-case-completion-20260816`  
固定基线：`d7dce99590143ec550093d3ad79f457afcd81ce6`  
交付提交：以 fork 上同名分支的 HEAD 为准；报告所在提交不能稳定地自引用其自身 SHA。

## 结论

黄金案件已从原基线的失败状态完成到可重复演示状态。证据撤回、卡组织持久化、当前 revision 审核决定恢复、Agent 自动重分析、规则引用、材料包与人工闸门已在同一案件链路中验证。原基线 `4 failed, 1163 passed, 6 skipped` 的回归已修复，当前全量测试为 `1195 passed, 6 skipped`。

## 实施范围

- 原子撤回最近有效资料，包含 revision、审计、并发冲突、回滚和旧库迁移。
- 持久化 `VISA/MASTERCARD/AMEX` 卡组织选择；首次选择或变更采用 CAS，幂等重放不增加 revision。
- Agent、规则引用、材料包和 mock 申诉统一读取案件已持久化卡组织，不按原因码猜测。
- 恢复最新且与当前 revision 一致的审核决定，页面重开后仍显示审核人和审核审计 ID。
- 撤回或卡组织变化后，不把旧审核决定、评估、规则引用、材料包或 mock 回执显示为当前结论。
- OpenAPI 冻结合同、10 条规则目录断言、Ruff 格式和 UUID4 敏感信息扫描回归已同步修复。

## 自动化门禁

执行环境为 macOS、本地 Python 3.12 虚拟环境、Offline Fallback 模型路径。

- 聚焦 domain/application/repository/API/demo：`913 passed, 1 skipped`。
- 完整 pytest：`1195 passed, 6 skipped`，无失败。
- Ruff check：通过。
- Ruff format check：`177 files already formatted`。
- `compileall`：通过。
- `git diff --check`：通过。
- Offline 示例与评测脚本：`chargeback_demo.py`、`chargeback_transcript.py`、`eval_chargeback.py` 均通过。

跳过项仅包括未提供外部模型凭据的 live 测试和当前 macOS 环境没有 PowerShell 的单项脚本测试；不影响 Offline Synthetic 黄金链路。

## 空库黄金案件验收

使用独立临时 SQLite、Offline Fallback 和全新 Synthetic 案件执行，不复用用户数据库，不记录真实交易或个人信息。

1. 黄金模板建案时明确保存 `VISA`，并自动登记模板内可用的 Synthetic 交易收据，初始材料为 1/6。
2. 每个补证入口只打开独立弹窗；选择前最终提交按钮禁用，关闭或 Escape 不写入案件。
3. 逐项提交后从 1/6 到 6/6，只有最终确认调用后端；每次均显示进度和成功回执。
4. Agent 在 6/6 时生成审核提案，确认前数据库不变；人工确认后 revision 增加并返回审核审计 ID。
5. 返回案件中心并重新打开案件后，审核状态、审核人、revision 和审核审计 ID 均恢复。
6. Visa 10.4 规则引用可追溯到 `visa-10-4-demo-v1`，Agent 同时展示 Oceanpayment 3DS 技术语境引用。
7. 材料包严格包含 4 项：交易收据、3DS 认证结果、设备/IP 匹配、历史交易记录；AVS/CVV 只属于内部准备清单，不进入卡组织材料包。
8. 未批准提交被人工闸门阻断；填写审核人并明确确认后，得到本地 Mock 成功回执。
9. 撤回最近资料前显示二次确认；取消无副作用，确认后 revision 从 9 增至 10，案件回到 5/6 和 `NEED_EVIDENCE`。
10. SQLite 中最新 Agent turn 为 `EVIDENCE_WITHDRAWN`，审计 detail 只记录证据代码；页面上的旧评估、引用、材料包和 Mock 回执已清除。

## 浏览器与视口

在真实本地 HTTP 服务中检查 375、768、1024、1440 四档宽度，页面高度 900。

- 四档 `documentElement` 与 `body` 均无横向溢出。
- 375px 下补证弹窗主体宽 340px，边界为 left 10px / right 350px，未裁切。
- 弹窗初始最终提交按钮禁用；Escape 关闭后焦点恢复到原“补交资料”按钮。
- 中文语言标记为 `zh-CN`，移动端导航可访问。
- 浏览器控制台错误：0。

## 迁移与持久化

- 旧 SQLite 在事务内补充可空 `card_network` 并扩展审计事件约束。
- 迁移保留案件、证据、Agent turn、审核决定和审计记录。
- 卡组织 CAS、幂等重放、重启恢复、撤回并发、事务失败回滚和历史审核失效均有确定性测试覆盖。

## 事实边界

- 全部案件、资料、审核人、回执和审计都是 Synthetic/Mock。
- “材料就绪度”是内部准备清单完成度，不是胜诉概率、准确率或生产业务效果。
- Visa 摘要保持 `UNVERIFIED_SUMMARY`；15 天仅为原型内部准备窗口。
- Mock connector 不代表真实卡组织提交。
- 未进行真实飞书 tenant、真实 Oceanpayment 交易接口、正式规则来源或生产权限联调。
- 未读取、提交或输出 `.env`、模型密钥、飞书凭据或真实敏感信息。

## 发布检查

- 目标远端：`zelin-michael-zhu/oceanpilot-evidenceos`。
- 目标分支：`agent/golden-case-completion-20260816`。
- 不修改 `wip/rules-ui-evidence-handoff-20260815`，不更新 PR #51，不创建新 PR。
- 推送后的 GitHub Actions 与 clean clone 结果在最终交付消息中以远端实际 SHA 和运行链接为准。
