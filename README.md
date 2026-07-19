# OceanPilot EvidenceOS

![OceanPilot EvidenceOS：证据驱动的跨境商户成功协作系统；缺证先补问、过门再判断、高风险动作由人工确认](docs/assets/submission/oceanpilot-hero.png)

**证据驱动的跨境商户成功协作系统。** OceanPilot 用同一份“商户成功案件”串联问题、证据、判断与交接：缺证先补问，达到证据门槛后再进入候选判断，高风险动作由人工确认。

> **当前边界：** 已验证建案、证据存储、完整度判断与审计边界；诊断编排、人工路由、飞书 Agent 与 Oceanpayment 数据接入均为规划能力。当前原型仅使用合成数据，不执行任何支付、退款、风控放行或资金动作。

### 三个核心设计

- **商户成功案件（Merchant Success Case）：** 用持续演进、可版本化的案件聚合问题上下文与协作状态，减少截图和聊天记录反复转发。
- **案件证据契约（Case Evidence Contract）：** 每条证据绑定来源、时间、版本与引用；资料不足时先定位缺口，不让系统直接猜测。
- **受控协作闭环：** 完整方案中由 AI 处理模糊表达和补问，确定性规则约束状态与责任路由，高风险动作必须人工确认；当前基础原型只验证案件与证据内核。

## What OceanPilot Is

OceanPilot EvidenceOS 是一个面向跨境支付异常协作的独立参赛原型。它把零散的问题描述整理为版本化案件，把每条输入转换为可追溯证据，再由确定性的领域策略计算资料完整度和案件状态。当前重点不是给出未经验证的“AI 结论”，而是先证明一条较窄但可检查的链路：创建 synthetic payment incident 案件、追加证据、读取同一案件视图，并对尚未完成的诊断能力明确停机。

这个基础版本适合用于代码审查、架构讨论和后续分工。所有商户、交易和证据内容均为合成示例；仓库不包含真实商户数据或外部系统凭据。

## Current Foundation Scope

| Capability | Status | Current behavior |
|---|---|---|
| `GET /health` | Available | 检查本地 SQLite Store 是否可访问 |
| Create case | Available | 创建唯一启用的 synthetic `PAYMENT_INCIDENT` 案件 |
| Read case | Available | 返回案件、readiness、证据、revision 和当前诊断指针 |
| Append evidence | Available | 追加受限证据；同 ID 同内容 replay，同 ID 异内容 conflict |
| Diagnosis | Deferred (HTTP 501) | 固定返回安全的 `FEATURE_DEFERRED`，不执行规则、不写诊断结果 |
| Production readiness | Not claimed | 尚未完成完整安全合同、诊断链、外部集成、部署和运行保障 |

公开 HTTP 输入必须使用规范 UUIDv4，`synthetic` 必须是布尔值 `true`。HTTP 层固定证据来源为 `MERCHANT / USER_REPORTED / synthetic=true`，调用方不能注入来源可信度、状态、revision 或路由结论。

## Architecture

当前运行链路保持单向依赖：

```text
HTTP / OpenAPI
    -> CaseService
    -> domain evidence policies and state machine
    -> CaseStore port
    -> local SQLite
```

API 只负责严格输入映射、状态码和安全错误；readiness、状态变化和证据规范化由领域层负责；SQL、事务、revision 条件更新和审计落库由 Store 负责。诊断路由不会绕过这些边界生成临时结果。完整组件和数据流见 [docs/architecture.md](docs/architecture.md)。

## Quick Start

要求 Windows PowerShell 与 Python 3.12。以下命令只在 `127.0.0.1` 启动本地服务：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:OCEANPILOT_DB_PATH = "work/oceanpilot.db"
.\.venv\Scripts\python.exe -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8000
```

启动过程由 FastAPI lifespan 创建 SQLite schema 并执行一次 Store 健康检查。构造或导入应用本身不会打开数据库连接。

## API Walkthrough

服务运行后，在另一个 PowerShell 窗口执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\examples\demo.ps1
```

脚本按顺序验证：

1. `GET /health` 返回 `200`；
2. `POST /api/v1/cases` 创建一个 synthetic 支付异常案件并返回 `201`；
3. `POST /api/v1/cases/{case_id}/evidence` 追加 `context.environment=PROD` 并返回 `201`；
4. `GET /api/v1/cases/{case_id}` 读取持久化后的案件视图；
5. `POST /api/v1/cases/{case_id}/diagnose` 返回预期的 `501 FEATURE_DEFERRED`。

首次追加证据返回 `201`；同一 `evidence_id` 和规范化内容重放返回 `200`；同一 ID 携带不同内容返回安全 `409 EVIDENCE_CONFLICT`。演示脚本不启动或关闭服务器，也不访问外部服务。

## What Is Deliberately Deferred

- 诊断快照的 CAS 持久化、唯一键 replay、stale 输入检查和原子审计；
- `CaseService.diagnose()`、规则编排以及并发冲突后的有限重算；
- 完整 RFC 9457 Problem Details、全链路 request/trace ID 和完整 OpenAPI 错误矩阵；
- 三个闭环 synthetic 业务场景及其内部适配器路径；
- 五表面敏感数据回归、远程 CI 运行证据、鉴权、限流、日志和指标；
- 飞书 Agent、A2A、MCP、Oceanpayment API、工单、SLA、通知、自动派单或支付动作；
- 容器、云数据库和发布运维。

逐项依赖、文件所有权与可执行验收命令见 [docs/roadmap/incomplete-work.md](docs/roadmap/incomplete-work.md)。延期能力不会用内存假结果或展示文案代替。

## Verification

Task 3 后的本地基线已新鲜验证为 `717 passed`。Foundation 路径、Ruff lint、compileall、五路径 OpenAPI 和 diff 检查均通过；TestClient 运行会出现一条来自固定版本 Starlette/httpx 组合的上游弃用警告。这里不声称远程 CI 已运行。

可重复执行：

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest -q --basetemp .superpowers/sdd/pytest-foundation-readme
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -c "from oceanpilot.main import create_app; assert len(create_app().openapi()['paths']) == 5"
git diff --check
```

`ruff format --check src tests` 当前会指出 19 个在本次文档里程碑之前已经提交的 Python 文件。Task 4 不修改 Python，也不把机械格式化混入公开材料提交；该格式基线作为后续独立清理项保留。

## Competition Context

本项目用于 [2026 AI 先锋未来人才大赛](https://activity.feishu.cn/future-talent#challenge) 的 Oceanpayment 企业命题探索，关注跨境商户接入与上线后问题协作。当前实现只覆盖 synthetic `PAYMENT_INCIDENT` 基础切片，不代表 Oceanpayment 官方产品，也未获得其真实接口、流程或生产数据验证。

领域证据契约、状态机、原子事务和规则表属于本参赛方案中的组合设计；其中使用的通用工程方法不被表述为团队独创算法。公开代码当前仅供比赛评审，未授予复用许可。
