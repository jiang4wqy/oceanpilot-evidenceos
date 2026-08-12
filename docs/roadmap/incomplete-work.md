# OceanPilot Status Register

本文件记录当前事实状态，替代早期 Foundation 阶段的“诊断 501”待办清单。

## 已完成并由本地测试验证

- 诊断 snapshot CAS、唯一键 replay、stale revision、同案引用、原子 audit 和 rollback；
- Gate 2 persistence review；
- `CaseService.diagnose()`、最多三次重算、四条确定性规则与安全 Problem Details；
- API checkpoint；
- 四规则 synthetic internal/HTTP E2E 和 PowerShell demo；
- 飞书 callback verifier、receipt/lease/fencing、binding、机器人抑制和安全 outbound client；
- 群消息自动建案、七步补证、3DS/risk 真实诊断卡；
- current diagnosis 人工确认、actor hash、语义去重、approval audit，且不改变 core case；
- `/demo` 综合能力地图与 read-only case Cockpit；
- signed fixture fallback；
- HTTP/log/audit/SQLite/snapshot/static 跨表面安全 sentinel；
- Python 3.12 GitHub Actions 配置。

## 当前 Task 7 发布门

| Item | Status | Evidence |
|---|---|---|
| Signed callback fallback | Local PASS | `examples/signed_fixture_demo.py` |
| Four-rule API fallback | Local PASS | `examples/demo.ps1` + E2E tests |
| Security sentinels | Local PASS | `tests/security/` |
| Full pytest/Ruff/compileall/diff | Local PASS | PR4 checkpoint records fresh counts |
| Clean temporary copy | Local PASS | 候选树 `950937084251e96fc65fa3b2672df30315917682` 的独立 Python 3.12 venv 中 `1035 passed`，且两级 fallback、Ruff/compileall、依赖审计与非 UTF-8 控制台 PDF 重建通过；见 PR4 checkpoint |
| GitHub Actions | Fix pending revalidation | Run `31610488039` exposed a `cp1252` console error after PDF generation; the ASCII-output fix and regression test await a new remote run |
| Real Feishu test group | NOT RUN | Requires public HTTPS callback and valid tenant state |
| Anonymous current commit | NOT VERIFIED | Current commit has not been pushed |

## 仍需完成

### External release conditions

- 安全整合已经分叉的本地/远端 feature history，不强推覆盖远端；
- 推送安全新分支并创建/关联 PR；
- 观察 GitHub Actions 绿色；
- 用匿名会话验证目标 commit 的 README；
- 在真实飞书测试群完成一次带时间证据的 message → confirmation → Cockpit smoke；
- 记录 Gate 3 主链审查和 Gate 4 发布审查。

### Formatting baseline

`ruff format --check src tests examples` 仍会报告历史文件。它必须作为独立机械提交处理，不与 Task 7 逻辑、测试或文档混写；机械提交后需再次全量回归。

### Production hardening outside competition scope

- authn/authz、rate limiting、production logging/metrics/tracing；
- secret manager、依赖和 secret scanning enforcement；
- backup/restore、schema migration tooling、cloud database 和 disaster recovery；
- Oceanpayment production adapter、真实商户数据治理；
- ticket/SLA/notification、A2A/MCP、运营 dashboard；
- 任何支付、退款、风控放行、资金、调账或配置执行器。

## 不得倒退的边界

- 全程 synthetic；
- 缺证不能诊断；
- 无规则命中不能伪造结论；
- 人工确认只记录 acknowledgement；
- caller 不能伪造证据可信度或 route；
- 凭据、原始 actor/tenant/chat/thread 值和 callback 正文不能进入公开响应、日志或 core audit，也不能作为原文持久化；receipt 只保留最小事件标识和 payload hash；
- fallback 必须明确标注本地 synthetic，不能冒充真实飞书联调。
