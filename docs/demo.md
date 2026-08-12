# OceanPilot 比赛演示 Runbook

## 1. 演示边界

本演示只处理 synthetic `PAYMENT_INCIDENT`。它展示证据补问、确定性诊断、责任建议、人工确认审计和只读 Cockpit，不连接 Oceanpayment 生产系统，不执行支付、退款、风控放行、资金移动、调账或生产配置修改。人工确认只记录 acknowledgement，不改变核心案件状态。

## 2. 三层 fallback

按以下顺序选择现场路径，外部条件失败时立即降级，不临场修改代码：

1. **真实飞书测试群：** 测试应用、测试群和公网 HTTPS callback 均可用时采用。
2. **Signed fixture：** 走相同的签名校验、HTTP callback、编排、SQLite 和 Cockpit，外部发送替换为 synthetic transport，不访问网络。
3. **Direct API：** PowerShell 脚本依次展示 3DS、风控拒绝、商户配置不匹配和 PSP 配置不匹配。

第二、三层必须明确称为本地 synthetic fallback，不能称为真实飞书联调。

## 3. 本地准备

需要 Windows PowerShell、Python 3.12，以及一个新建的虚拟环境：

```powershell
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
$env:PYTHONPATH = "src"
```

启动核心服务：

```powershell
$env:OCEANPILOT_DB_PATH = "$env:TEMP/oceanpilot-showcase.db"
./.venv/Scripts/python.exe -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8000
```

浏览器打开 `http://127.0.0.1:8000/demo`。重复演示前使用新的数据库路径，避免把上一轮 persisted case 当作新结果。

## 4. Signed fixture fallback

目标目录必须不存在或为空；runner 不会覆盖已有文件：

```powershell
$env:PYTHONPATH = "src"
py -3.12 -B examples/signed_fixture_demo.py `
  --work-dir "$env:TEMP/oceanpilot-signed-fixture-new"
```

预期最后一行是稳定 JSON，关键值为：

```json
{
  "mode": "SIGNED_FIXTURE",
  "synthetic": true,
  "evidence_steps": 7,
  "case_status": "HUMAN_REVIEW",
  "matched_rule_id": "THREEDS_INCOMPLETE_V1",
  "display_confidence": "0.87",
  "responsible_team": "TECHNICAL_SUPPORT",
  "priority": "MEDIUM",
  "confirmation_state": "CONFIRMED",
  "case_unchanged_by_confirmation": true,
  "approval_audit_count": 1,
  "business_action_executed": false
}
```

runner 每次运行时随机生成 signing material，使用仓库内 message/evidence/confirmation fixture，并在任何步骤失败时返回非零退出码。

## 5. Direct API fallback

保持本地服务运行，在第二个 PowerShell 窗口执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./examples/demo.ps1
```

预期四个摘要分别命中：

| Rule | Confidence | Team | Priority |
|---|---:|---|---|
| `THREEDS_INCOMPLETE_V1` | `0.87` | `TECHNICAL_SUPPORT` | `MEDIUM` |
| `RISK_DECLINE_V1` | `0.87` | `RISK` | `HIGH` |
| `CONFIG_MISMATCH_MERCHANT_V1` | `0.87` | `TECHNICAL_SUPPORT` | `MEDIUM` |
| `CONFIG_MISMATCH_PSP_V1` | `0.87` | `PSP_SUPPORT` | `MEDIUM` |

## 6. 真实飞书测试应用配置

只复用或创建企业自建测试应用，不使用生产应用：

1. 启用机器人能力，并只申请接收测试群消息、向测试群发送消息/卡片所需的最小权限。
2. 把机器人加入唯一测试群，记录测试群 chat ID。
3. 在事件订阅中设置公网 HTTPS callback：`https://<host>/api/v1/feishu/events`，订阅群消息接收事件。
4. 在交互卡片回调设置中使用：`https://<host>/api/v1/feishu/card-actions`。
5. 确保证书有效、服务可从公网访问，并让平台 URL verification 成功后再上台。
6. 只通过当前进程环境变量注入配置：

```powershell
$env:FEISHU_APP_ID = "<test-app-id>"
$env:FEISHU_APP_SECRET = "<test-app-secret>"
$env:FEISHU_VERIFICATION_TOKEN = "<verification-token>"
$env:FEISHU_ENCRYPT_KEY = "<encrypt-key>"
$env:OCEANPILOT_FEISHU_DEMO_CHAT_ID = "<test-group-chat-id>"
$env:OCEANPILOT_FEISHU_DEMO_MERCHANT_REF = "synthetic-showcase-merchant"
$env:OCEANPILOT_FEISHU_DB_PATH = "$env:TEMP/oceanpilot-feishu-showcase.db"
$env:OCEANPILOT_DB_PATH = "$env:TEMP/oceanpilot-core-showcase.db"
```

仓库、命令历史截图、日志和录屏不得出现真实值。配置环境变量后重启服务；缺少任一凭据时飞书 runtime 不启动，callback 会安全返回 `503 FEISHU_UNAVAILABLE`。

## 7. 舞台操作顺序

1. 打开 `/demo`，用能力地图说明支付异常是已打通的纵向切口，其余模块是 `CONCEPT PREVIEW`。
2. 在测试群发送一条 synthetic 3DS/callback 异常描述。
3. 按卡片顺序补齐七项证据；指出 readiness 未达标前系统不会诊断。
4. 最后一项证据提交后展示诊断卡：`THREEDS_INCOMPLETE_V1`、`0.87`、`TECHNICAL_SUPPORT`、`MEDIUM` 和人工复核原因。
5. 点击人工确认；强调它只写 approval audit，不执行任何业务动作。
6. 打开 `/demo/cases/{case_id}`，展示同一 persisted case 的 evidence ledger、引用、责任建议、confirmation 和安全 audit timeline。
7. 重放同一 event 或重复点击确认，展示没有重复案件、证据、诊断或审批。

## 8. 清理与故障处理

- **callback 503：** 检查四个飞书凭据和两个 demo 范围变量是否在启动服务前设置，然后重启。
- **callback 401：** 检查平台 verification token、encrypt key、系统时间和公网代理是否保留原始请求体及签名头。
- **消息被忽略：** 确认来自配置的测试群、发送者不是机器人，并且消息位于预期 thread。
- **旧卡片提示刷新：** 当前 diagnosis 已变化；从最新诊断卡继续，不重复确认旧卡。
- **Cockpit confirmation 为 `UNAVAILABLE`：** core DB 可读但飞书 DB 不可读；切换到 signed fixture 或 direct API fallback。
- **端口或数据库占用：** 停止旧服务，改用新的端口和全新 temp 数据库路径。

演示结束后停止本地服务。临时数据库只含 synthetic 数据，可在确认路径位于系统临时目录后删除；不要对仓库目录做递归清理。

## 9. 发布验证状态

| Item | Meaning |
|---|---|
| Signed fixture | 本地可完全验证，不依赖飞书或网络 |
| Direct API | 本地可完全验证，需启动 loopback 服务 |
| Real Feishu group | 必须有测试租户、公网 HTTPS 和带时间的成功证据才能标记 PASS |
| GitHub CI | 分支推送并实际运行后才能标记绿色 |
| Anonymous repository | 必须从未登录会话读取目标 commit 后才能标记 VERIFIED |

最新实际结果记录在 [PR4 checkpoint](reviews/checkpoint-feishu-demo.md)，以该报告为准。
