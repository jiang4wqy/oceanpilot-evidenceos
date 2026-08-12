# OceanPilot EvidenceOS

![OceanPilot EvidenceOS：证据驱动的跨境商户成功协作系统](docs/assets/submission/oceanpilot-hero.png)

OceanPilot 是一个面向跨境商户成功协作的比赛原型。它把群聊中的支付异常变成可版本化案件，并用同一份持久化数据串联补证、确定性诊断、责任建议、人工确认和审计。

> **安全边界：** 当前所有可运行链路均使用 synthetic 数据。项目不连接 Oceanpayment 生产系统，不执行支付、退款、风控放行、资金移动或生产配置修改。诊断和路由是建议，不是业务动作。

GitHub：<https://github.com/jiang4wqy/oceanpilot-evidenceos>

## 当前可运行闭环

```text
飞书问题描述
  -> 自动建案并绑定会话
  -> 根据 readiness 逐步补问
  -> 证据达标后执行确定性规则
  -> 输出候选原因、置信度、证据引用与责任域
  -> 高风险结果等待人工确认
  -> 记录审批审计，不改变核心案件或执行资金动作
  -> /demo/cases/{case_id} 展示同一案件的只读 Cockpit
```

当前实现的支付异常规则：

| Rule | 场景 | 责任团队 |
|---|---|---|
| `THREEDS_INCOMPLETE_V1` | 3DS / callback 未完成 | `TECHNICAL_SUPPORT` |
| `RISK_DECLINE_V1` | 风控拒绝 | `RISK` |
| `CONFIG_MISMATCH_MERCHANT_V1` | 商户侧配置不匹配 | `TECHNICAL_SUPPORT` |
| `CONFIG_MISMATCH_PSP_V1` | PSP 资料配置不匹配 | `PSP_SUPPORT` |

HTTP synthetic 来源固定为 `MERCHANT / USER_REPORTED`，调用方不能伪造来源可信度、置信度、责任团队或案件状态。低置信度、来源质量不足、风险决策、证据冲突或策略缺口会进入 `HUMAN_REVIEW`。

## 综合智能体叙事

支付异常是已经打通的纵向切口，不是产品终点。`/demo` 展示综合 Merchant Success OS 能力地图：

- 支付异常：`LIVE / SYNTHETIC`，使用真实项目代码与持久化数据；
- 商户入网、退款/拒付、对账运营：`CONCEPT PREVIEW`，只表达未来产品方向，不调用后端、不生成结论。

仓库中的三张早期提交图记录了 Foundation 阶段的设计快照，其中 `501 / 717 tests / 5 paths` 等文字已经不是当前运行事实。当前能力以本 README、[架构文档](docs/architecture.md) 和测试结果为准。

## 运行表面

| Surface | 当前行为 |
|---|---|
| `GET /health` | SQLite 健康检查 |
| `POST /api/v1/cases` | 创建 synthetic `PAYMENT_INCIDENT` |
| `GET /api/v1/cases/{case_id}` | 读取案件、证据、readiness 和当前诊断 |
| `POST /api/v1/cases/{case_id}/evidence` | 追加证据，支持 replay/conflict |
| `POST /api/v1/cases/{case_id}/diagnose` | 持久化诊断；同 revision/policy replay |
| `POST /api/v1/feishu/events` | 验签、去重、建案、补问 |
| `POST /api/v1/feishu/card-actions` | 验签、补证与人工确认审计 |
| `GET /api/v1/demo/cases/{case_id}` | Cockpit 安全白名单 JSON |
| `/demo` | 综合智能体能力地图 |
| `/demo/cases/{case_id}` | 同一 persisted case 的只读驾驶舱 |

所有 API 错误使用 `application/problem+json`，含当前 HTTP 请求生成的 request/trace ID，不回显证据正文、凭据、SQL 或底层审计身份。

## Quick Start

要求 Windows PowerShell 与 Python 3.12：

```powershell
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
$env:OCEANPILOT_DB_PATH = "work/oceanpilot.db"
./.venv/Scripts/python.exe -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000/demo
```

### 四规则 direct API fallback

服务运行后，在另一个 PowerShell 窗口执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./examples/demo.ps1
```

脚本依次演示 3DS/callback、风险拒绝、商户配置不匹配和 PSP 配置不匹配；失败返回非零退出码。

### Signed Feishu fixture fallback

它走真实签名校验和 callback 路由，但用 synthetic transport 代替外部飞书 HTTPS：

```powershell
$env:PYTHONPATH = "src"
py -3.12 -B examples/signed_fixture_demo.py `
  --work-dir "$env:TEMP/oceanpilot-signed-fixture"
```

目标目录必须是新目录或空目录。成功摘要固定包含 7 步补证、`THREEDS_INCOMPLETE_V1 / 0.87 / TECHNICAL_SUPPORT / MEDIUM`、`CONFIRMED` 和 `business_action_executed=false`。

## 可选真实飞书配置

凭据只通过环境变量注入：

```powershell
$env:FEISHU_APP_ID = "<app-id>"
$env:FEISHU_APP_SECRET = "<app-secret>"
$env:FEISHU_VERIFICATION_TOKEN = "<verification-token>"
$env:FEISHU_ENCRYPT_KEY = "<encrypt-key>"
$env:OCEANPILOT_FEISHU_DEMO_CHAT_ID = "<test-group-chat-id>"
$env:OCEANPILOT_FEISHU_DEMO_MERCHANT_REF = "<synthetic-merchant-ref>"
$env:OCEANPILOT_FEISHU_DB_PATH = "work/oceanpilot-feishu.db"
```

飞书平台需把事件和卡片回调指向公网 HTTPS 的 `/api/v1/feishu/events` 与 `/api/v1/feishu/card-actions`。仓库不包含真实值。完整步骤见 [演示 Runbook](docs/demo.md)。

## 架构与安全

核心案件与飞书 callback 使用两个独立 SQLite 数据库：

- core DB 原子持久化案件、证据、诊断、引用和审计；
- Feishu DB 持久化 receipt、会话绑定、租约与确认审批；
- Cockpit 用两个短读事务聚合并明确标注 `READ_ONLY_BEST_EFFORT`，不宣称跨库分布式事务；
- 浏览器 DTO 排除 `source_ref`、`content_hash`、底层 request/trace、metadata、actor/action/approval ID 和凭据；
- 页面无表单和 mutation 请求，动态文本仅用 `textContent`。

详见 [docs/architecture.md](docs/architecture.md)。

## Verification

本地发布门：

```powershell
$env:PYTHONPATH = "src"
py -3.12 -B -m pytest -p no:cacheprovider -q
ruff check src tests examples scripts
py -3.12 -B -m compileall -q src tests examples scripts
git diff --check
```

当前分支已配置 Python 3.12 GitHub Actions，但远端 CI 必须在分支成功推送后才可声称绿色。格式基线仍有历史文件需要机械整理，状态记录在 [roadmap](docs/roadmap/incomplete-work.md)，不与逻辑提交混写。

## 当前没有声明的能力

- Oceanpayment 生产数据或真实商户数据接入；
- 自动支付、退款、风控放行、资金操作、调账或生产配置修改；
- A2A、MCP、工单/SLA、运营看板、鉴权、限流和生产部署；
- 真实飞书测试群联调通过，除非 checkpoint 中另有带时间的外部证据；
- GitHub CI 绿色或当前提交已匿名发布，除非远端实际可访问。

比赛状态、fallback 顺序和外部阻断见 [PR4 checkpoint](docs/reviews/checkpoint-feishu-demo.md)。公开代码仅供比赛评审，未授予复用许可。
