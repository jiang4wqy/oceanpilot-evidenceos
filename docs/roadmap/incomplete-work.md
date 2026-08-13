# OceanPilot Current Status and Deferred Work

本页是 living status，不复述已经过期的 Foundation TODO。当前产品愿景是综合商户成功智能体；仓库已验证支付异常和拒付申诉两个 synthetic 纵向切片，8 月 16 日展示先支付异常。

## 已完成的竞赛代码能力

| Area | Current verified state |
|---|---|
| Payment persistence | 诊断 snapshot CAS、identity replay、stale 拒绝、同案证据引用、原子诊断审计和 rollback |
| Payment service/API | readiness gate、最多三次有限重算、真实严格 DiagnosisResponse、安全 Problem Details 与 request/trace ID |
| Payment scenarios | 3DS/回调、风控拒绝、商户侧配置不匹配、PSP 侧配置不匹配；HTTP E2E 与 `/demo/payment-incident` |
| Feishu local path | signed local fixture，以及从真实出站补问卡按钮驱动的公共 callback E2E：消息建案、七次补证、诊断卡、人工确认审计、事件/动作 replay、无外网 |
| Feishu privacy | 外部 chat/actor 标识哈希、receipt payload hash、callback body/凭据不持久化 |
| Chargeback slice | 独立持久化智能体集群、SLA、评估、打包、草稿、mock upstream、人工门、审计、指标和 `/demo` |
| Release automation | Python 3.12 CI 配置、全量测试/lint/format/compile、fixture、PowerShell demo、package/PDF smoke 与 diff gate |

这些状态只说明当前仓库中的 synthetic 行为已通过相应本地测试/检查；不自动证明目标提交的远程 Actions 绿色、匿名公开可读或正式发布完成。

## 尚待完成

| Priority | Work | Why it remains open | Completion evidence |
|---:|---|---|---|
| P0 | 真实飞书测试群 smoke | signed local fixture、可点击卡片 E2E 和公网 callback 预检均已完成；仍缺真实租户发起的群消息/卡片证据 | 时间戳、真实测试群消息/卡片、重复事件/点击去重、一次审批审计、安全日志/DB scan |
| P0 | 最终 clean-copy 与远程 CI | 工作流配置存在不等于 exact head 已远程执行 | clean checkout 全门通过；GitHub Actions 在 exact PR head 绿色 |
| P0 | 匿名 README 与 PR 审查 | 当前分支还需发布和对 `master` 的无回退核对 | exact commit README 匿名 HTTP 200；PR 不删除 v0.2.1 拒付/console/安全能力 |
| P1 | 真实 Oceanpayment 数据适配 | 未获得生产接口、数据合同和授权 | 只读 sandbox/测试环境合同、脱敏数据、权限与审计通过验收 |
| P1 | 真实上游工单/申诉集成 | 当前拒付 submission 只进入 mock | sandbox adapter、人审权限、幂等/补偿、安全审计和业务方验收 |
| P1 | 鉴权、限流和生产可观测性 | 当前是本地比赛原型 | 身份/权限模型、rate limit、日志/指标/告警、运行手册与演练 |
| P2 | A2A、MCP、SLA、通知与自动派单 | 属于综合智能体扩展面，当前没有运行证据 | 独立规格、最小切片、测试与真实业务验收 |
| P2 | 云数据库与部署运维 | 当前三个独立本地 SQLite store | 部署架构、备份恢复、迁移、容量/并发和灾备证据 |
| P2 | 商业效果验证 | 报名指标是目标，不是实测结果 | 真实基线、试点样本、指标定义、置信区间和业务方确认 |

## 不会用 demo 文案代替的能力

- 真实支付、退款、风控放行、资金移动、调账或生产配置变更；
- Oceanpayment、银行、卡组织或工单系统的真实上游提交；
- 真实飞书群/生产凭据/生产数据；
- 已验证 ROI、资料到齐时间或首次责任域命中率；
- production ready 或 Gate 4 PASS。

## 发布顺序

1. 完成 living docs/PDF 事实一致性和本地全门。
2. 导出 exact tree 做 clean-copy 重现、依赖/secret/sensitive-data 扫描。
3. 推送 integration branch，等待 exact head 的 GitHub Actions。
4. 匿名读取 exact commit README，审查 PR 对 `master` 无反向回退。
5. 真实飞书群 smoke 单独执行；在此之前 Gate 4 保持未完成。

详细设计与任务依赖见：

- [Payment incident mainline integration design](../superpowers/specs/2026-08-12-payment-incident-mainline-integration-design.md)
- [Payment incident mainline integration plan](../superpowers/plans/2026-08-13-payment-incident-mainline-integration.md)
- [Combined checkpoint](../reviews/checkpoint-payment-incident-mainline.md)
