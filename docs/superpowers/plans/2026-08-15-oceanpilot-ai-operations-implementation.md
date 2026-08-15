# OceanPilot 方案 A 实施计划

依据：[2026-08-15-oceanpilot-ai-operations-design.md](../specs/2026-08-15-oceanpilot-ai-operations-design.md)

## 验收目标

1. `/demo` 仅新增 AI 总窗口。
2. 支付异常卡直接进入 GitHub 基线 `overview`。
3. 原版 `overview/create/diagnosis/flow/prev` 的结构与视觉保持。
4. 不保留 `incidents` 详情页；增加基线风格的规则知识页。
5. 诊断与 Package 通过后端返回的 `rule_version_id` 精确深链同一规则，并能返回案件上下文。
6. 独立规则库、Rules API、Package provenance 和 mock 事实边界继续通过。
7. 全量测试、静态检查、HTTP 与浏览器验收通过后运行最新版服务。

## 任务 1：恢复前端基线

- 以 `26e1fa8` 的 `demo.py` 为前端主体。
- 删除当前额外的 Ivory Ledger 全局覆盖和事件页；规则页改造成 GitHub 基线视觉。
- 验证原版页面、导航、主题和案件闭环重新存在。

## 任务 2：新增唯一 AI 总窗口

- 增加 `v-hub` 和一个侧栏入口。
- 使用基线组件与令牌构建能力总览。
- 支付异常是唯一 Live 按钮，直接 `showView("overview")`。
- 规则数据库显示 Backend Ready 与 9/3 数量，并可进入规则知识页。
- 增加响应式、键盘与无障碍断言。

## 任务 3：保留后端规则能力

- 保留三表 schema、稳定种子和独立数据库。
- 保留 RuleCatalog、SQLite lookup 和 InMemory fallback。
- 保留 list/detail API 与 Package provenance。
- 验证缺表、损坏、规范化和遗留行清理。

## 任务 4：规则知识与 Deep Link

- 在基线 SPA 中保留 `v-rules`，读取 list/detail API。
- 诊断页按用户明确选择的 card network 调用只读 `rule-reference` API，取得实际 `rule_version_id`，不生成材料包或改变案件状态。
- Package 引用直接使用响应中的 `rule_version_id`。
- 统一实现 `showRuleReference(ruleVersionId, returnContext)`：清理筛选、进入规则页、打开同一规则、聚焦高亮。
- 保存案件来源页面和上下文，提供返回按钮。
- 未解析到具体条款时显示空态，不按 reason code 猜测。

## 任务 5：保留事实边界

- `win_likelihood` 标记为弃用兼容别名和非预测概率。
- agent trace 使用“材料就绪度”。
- mock appeal 响应固定返回 Synthetic 与 in-process mock connector 标识。
- 文档明确 direct API/Feishu seam 不是生产受理门禁。

## 任务 6：更新测试与文档

- Demo 测试冻结 hub → overview、不存在 incidents，以及规则精确 deep-link/返回上下文。
- 后端规则、OpenAPI 和 Package 测试继续保留。
- README 与 Demo Runbook 改为方案 A 路径。
- 删除本轮不再实现的 incidents UI 描述，并明确 rules UI 使用基线视觉。

## 任务 7：完整验证与运行

- Ruff format/check、聚焦 pytest、全量 pytest、compileall、diff check。
- 重启 8002 客户端服务，HTTP smoke 关键入口。
- 浏览器验证总窗口、原版案件闭环、375/768/1024/1440 和控制台。
- 通过后保留为未提交工作树；只有用户明确授权时才 commit 或 push。
