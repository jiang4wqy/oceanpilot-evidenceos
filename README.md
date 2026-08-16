# OceanPilot — 跨境商户成功 AI 运营中枢

![OceanPilot：证据驱动的跨境拒付申诉协作 Agent；缺证先补问、过门再评估、高风险步骤由人工确认](docs/assets/submission/oceanpilot-hero.png)

**面向跨境商户成功与支付运营建立统一 AI 工作入口，并用“支付异常 → 争议协作”证明一条可运行的深度主线。** OceanPilot 用一个版本化案件串联拒付理由、证据缺口、证据就绪评估、规则校验与打包、人工审批和案件处理审计；AI 负责理解、补问和起草，确定性规则与人工负责裁定。

> **当前边界：** 全部业务数据和动作均为 Synthetic Demo。Web 主演示从 AI 总窗口进入原版案件中心，由演示者选择 Visa 10.4 合成模板，完成“受理 → 通用补证 → 评估 → 条款引用与打包 → 人审 → mock 申诉”。3DS 失败或回调异常仍只属于 Foundation `PAYMENT_INCIDENT` 支持分支；Web 入口和直连建案 API 尚未接入真实交易状态或 Issuer 通知来源校验。真实飞书 tenant、Oceanpayment 数据、经生产核验的卡组织规则和上游申诉均未接入，系统不执行任何真实资金或业务动作。

## 方案展示

![OceanPilot：AI 驱动的跨境支付全生命周期商户成功智能体（拒付是验证底座的高复杂度样本，不是产品边界）](docs/assets/showcase/oceanpilot-lifecycle-overview.png)

> **项目简介：** OceanPilot 先把一次跨境支付问题组织成版本化案件，再用证据契约识别缺口；资料过门后才形成带依据、规则版本、责任域和下一动作的判断，让 AI 提议、规则约束、人工裁定。本次比赛只把“支付异常 → 拒付申诉”做成端到端 Live Demo；全生命周期是同一底座之上的推广路径，不是当前已实现能力。

![AI 应用创新性对比：从聊天里猜答案到围绕证据形成可审计决策](docs/assets/showcase/oceanpilot-ai-innovation-comparison.png)

> **插图 1｜AI 应用创新性对比：** 从“聊天里猜答案”到“围绕证据形成可审计决策”。

![业务价值直观对比：同一个拒付案件的协作摩擦如何被收敛](docs/assets/showcase/oceanpilot-business-value-comparison.png)

> **插图 2｜业务价值直观对比：** 同一个拒付案件，协作摩擦如何被收敛。图中企业试点指标为试点目标，非当前已实现收益。

### 三个核心设计

- **拒付案件作为单一协作对象：** 用版本化案件聚合拒付理由、证据状态、评估、审批和审计，减少截图与聊天记录反复转发。
- **证据门槛先于申诉判断：** 按 reason-code 逐项定位缺口，关键证据不足时不生成乐观结论，转入补证或人工复核。
- **AI 提议、规则约束、人类裁定：** AI 理解模糊表达并起草材料；确定性规则计算证据就绪度和缺口；人工批准高风险步骤。

## What OceanPilot Is

OceanPilot 是一个面向跨境 PSP 与商户运营的独立参赛原型。AI 运营中枢展示商户成功、支付运营、风险合规、争议协作、规则知识和审计运维等能力域，但只把“支付异常”标记为本次可完整演示的 Live Demo。它把正式拒付处理固定为一条可检查的业务链：识别理由、补齐证据、计算证据就绪度、按卡组织演示规则校验和打包、人工批准，并分别展示案件处理审计与本次 mock 回执。

这个版本适合用于代码审查、架构讨论和比赛演示。所有商户、交易、银行规则和证据内容均为合成示例；仓库不包含真实商户数据或外部系统凭据，离线评测结果也只说明 synthetic fixture 上的可重复行为。

## Current Runtime Scope

| Capability | Status | Current behavior |
|---|---|---|
| Chargeback mainline | Available (synthetic) | 正式争议受理、reason 确认、逐项补证、确定性评估、规则校验与打包、人工闸门后的 mock 申诉、案件处理审计与本次 mock 回执 |
| Web console and demos | Available (synthetic) | `/demo` AI 运营中枢与支付异常单案主线、跨平台 Python transcript、Docker 一键启动与 synthetic 离线评测 |
| EvidenceOS Foundation | Supporting slice | `PAYMENT_INCIDENT` 建案/补证、确定性诊断持久化与 identity replay，用于验证底层证据与审计能力 |
| Foundation Feishu callbacks | Supporting slice | 经签名校验的建案、补问、诊断卡和人工确认审计；与拒付主线共享签名与回执基础设施 |
| Basic observability | Available (synthetic) | PII-free request/trace 日志与进程内决策指标；不是生产日志平台或持久化 metrics backend |
| Chargeback Feishu callbacks | Available (synthetic) | `/chargeback` 显式建案、理由/补证卡片、签名与 replay 防护、哈希 chat↔case 绑定；未做真实 tenant smoke |
| Rules knowledge prototype | Available (unverified summaries) | 独立 SQLite 规则库原型提供 9 条可浏览摘要，其中 3 条可参与 Demo 打包；通用补证仍由领域策略驱动，真实规则、脱敏案例与 RAG 尚未接入 |
| Real integrations | Planned | 真实 Oceanpayment、外部 A2A/MCP/工单、上游申诉与公网 Feishu tenant smoke |
| Production readiness | Not claimed | 尚未完成鉴权、限流、生产可观测性后端、云数据库、备份、部署和运行保障 |

## 产品主线：支付异常到争议协作

OceanPilot 主演示 Web 界面以“AI 总窗口 → 支付异常 → 原版案件中心”为入口，由演示者明确选择 Visa 10.4 合成模板后建案。Foundation 仍保留 3DS 失败、回调异常等 `PAYMENT_INCIDENT` 能力验证，但它不是当前 Web 主线。Web、直连建案 API 与 Chargeback 飞书入口均为 synthetic 协作 seam，尚未接入真实交易状态或 Issuer 通知来源校验，不能视为生产受理门禁：

```text
已结算交易收到正式拒付通知
  → 识别理由      抽取安全事实并提出 reason-code；不确定时由人工确认
  → 通用补证      由领域策略逐项提示缺口；关键材料不足时停止评估
  → 申诉评估      确定性规则计算证据就绪度、薄弱点与人工路由
  → 条款引用      明确选择卡组织后，只读解析并展示具体规则版本
  → 规则校验      在打包阶段用同一规则版本校验与排序材料
  → 材料打包      按命中的 Demo 模板组织 representment 材料
  → 人工批准      人类核对依据和申诉草稿
  → 模拟提交      当前只调用 synthetic mock connector
  → 结果核对      分开展示案件处理审计与本次 mock 回执
```

三条设计取向：**(1) 渠道无关内核**，完整链路由 HTTP/Web 驱动，飞书复用同一 `ChargebackChannelService` 承载受理与补证协作；**(2) 模型可插拔**，离线运行默认 Scripted/确定性 fallback，只有显式开启 live 开关才按安全档位路由到 Claude 或本地隔离模型；**(3) 混合决策**——确定性内核决策、LLM 只解释/建议、人类拍板。系统绝不执行真实支付、退款、风控或上游提交；人工批准只可能调用 synthetic mock connector。

- 设计文档：[docs/design/2026-08-06-chargeback-agent-cluster-design.md](docs/design/2026-08-06-chargeback-agent-cluster-design.md)
- 安全与部署分级：[docs/security/deployment-tiers.md](docs/security/deployment-tiers.md)
- 给公司的数据需求：[docs/data/2026-08-07-chargeback-data-request.md](docs/data/2026-08-07-chargeback-data-request.md)
- 离线可跑的演示：`examples/chargeback_demo.py`（agent 集群）、`examples/chargeback_transcript.py`（HTTP 全链路 transcript）
- 一键起服务：`docker build -t oceanpilot-evidenceos . && docker run --rm -p 127.0.0.1:8000:8000 oceanpilot-evidenceos`
- Web 控制台：`http://127.0.0.1:8002/demo`
- 离线评测报告（分类准确率 + synthetic 规则分离度）：`python scripts/eval_chargeback.py`

## Web 控制台 / Console

![OceanPilot 拒付申诉控制台：侧栏 + 案件工作台 + 活动流；确定性内核判定的证据就绪度、逐项证据与决策来源](docs/assets/console.png)

客户端以“AI 运营中枢 → 支付异常 → 原版案件中心”为主演示路径。首屏展示完整能力版图和实现状态，但只有支付异常标记为 `LIVE DEMO · synthetic`；点击只做导航，不自动建案。案件诊断或评估在明确选择卡组织后通过只读端点解析实际 `rule_version_id`，Package 复用同一版本引用；两处均可进入规则知识页并返回案件上下文，返回后已生成的 Package 不会丢失。规则知识页提供 9 条 `UNVERIFIED_SUMMARY` 摘要及来源追溯。

- 启动后打开根路径 `/`（自动跳转到 `/demo`）。
- Docker：`docker run --rm -p 127.0.0.1:8000:8000 oceanpilot-evidenceos`，浏览器开 `http://127.0.0.1:8000/demo`。
- 远程服务器：SSH 端口转发 `ssh -L 8000:127.0.0.1:8000 <user>@<host>`，本地开 `http://localhost:8000/demo`。
- 客户端顶栏提供全局搜索（`⌘K`）；技术端点不出现在客户导航中。
- 当前 AI 总窗口、原版案件主线与规则知识交互说明：[docs/superpowers/specs/2026-08-15-oceanpilot-ai-operations-design.md](docs/superpowers/specs/2026-08-15-oceanpilot-ai-operations-design.md)。

## 技术原则：证据先行闭环

![证据先行：先补齐事实，再给出判断](docs/assets/submission/fig-01-evidence-loop.png)

OceanPilot 的核心不是增加一个信息入口，而是让 AI、确定性规则与人工共同遵守同一套案件证据口径：资料不足先定位缺口，达到门槛后才输出评估，高风险步骤始终由人工确认。

> 图例边界：这是报名阶段的 Foundation 规划图。绿色实线为当时的基础原型，海洋蓝虚线为离线规则资产，浅灰虚线与琥珀色节点为当时的规划路径；`v0.2.1` 的实际运行边界以本文状态表与 `docs/architecture.md` 为准。

## Architecture

当前运行时包含一条拒付产品主线和一条 Foundation 能力验证切片，两者都保持单向依赖：

```text
Chargeback HTTP / Web console
    -> ChargebackChannelService -> Supervisor / deterministic kernel
    -> ChargebackCaseStore -> chargeback SQLite
    -> internal evidence policy -> readiness / missing evidence
    -> Packager -> independent rules SQLite -> in-memory fallback
    -> Appeal -> human gate -> mock upstream connector

Foundation HTTP / signed Feishu callbacks
    -> CaseService -> domain evidence policies / DiagnosisEngine
    -> CaseStore port -> foundation SQLite
```

API 只负责严格输入映射、状态码和安全错误；领域/应用层负责 readiness、评估和编排；SQL、事务、revision 条件更新和案件处理审计落库由 Store 负责。通用逐项补证继续由领域策略驱动；独立规则库在诊断/评估页只读解析和展示具体引用，只有打包阶段才使用对应 Demo 摘要、要求顺序和版本来源进行校验与排序，不能表述为“规则库驱动全流程”。Foundation 诊断快照会持久化并 replay；拒付 assessment/package/appeal 当前按最新案件状态计算，Package、人工批准和 mock 回执不属于 Chargeback SQLite 审计事件。完整组件和数据流见 [docs/architecture.md](docs/architecture.md)。

## Foundation：底层能力验证切片

![一个支付异常如何变成可追溯的协作案件](docs/assets/submission/fig-03-case-walkthrough.png)

Foundation 以合成支付异常验证版本化证据、确定性诊断、审计和签名飞书回调，不是当前产品主线。其公开 HTTP 输入使用严格 UUIDv4 和 `synthetic=true`，调用方不能注入来源可信度、状态、revision 或路由结论。

![当前可验证原型与入围后完整方案的分层架构](docs/assets/submission/fig-02-layered-architecture.png)

> **事实边界（图为报名期分层规划）：** 图中曾标为规划的 Foundation 诊断主链与飞书回调已实现为 synthetic demo；拒付主线也已接入同一签名事件/卡片入口，但尚未做真实 tenant smoke。真实 Oceanpayment 数据、外部 A2A/MCP/工单均未接入。

## 开发者指南 / Developer guide

**先读源码导航**：[`src/oceanpilot/README.md`](src/oceanpilot/README.md) 讲清六边形分层与唯一依赖规则,每层再各有一份 README：

| 层 | 文档 |
|---|---|
| 领域内核 | [`src/oceanpilot/domain/README.md`](src/oceanpilot/domain/README.md) |
| 应用/端口 | [`src/oceanpilot/application/README.md`](src/oceanpilot/application/README.md) |
| 适配器 | [`src/oceanpilot/adapters/README.md`](src/oceanpilot/adapters/README.md) |
| HTTP 接口 | [`src/oceanpilot/api/README.md`](src/oceanpilot/api/README.md) |
| 测试与门禁 | [`tests/README.md`](tests/README.md) |

**配置**：所有环境变量见根目录 [`.env.example`](.env.example)(存储路径、DeepSeek/Claude、本地模型、飞书凭据);凭据只经环境变量注入,绝不入库。运行/安装见下方 Quick Start。

**提交前门禁**(与 CI 一致)：

```bash
python -m pytest -p no:cacheprovider -q
ruff check src tests && ruff format --check src tests
python -m compileall -q src tests
```

## 提交材料索引

- [报名表 Part 1 / Part 2 可粘贴文本](docs/submission/registration-copy.md)
- [两页开题报告补充材料（PDF）](artifacts/OceanPilot-开题报告补充材料.pdf)
- [外部研究与事实边界](docs/submission/sources.md)
- [当前未完成能力与后续路线](docs/roadmap/incomplete-work.md)
- [飞书集成配置指南](docs/feishu-setup.md)
- [本地演示 runbook](docs/demo.md)

> 公共仓库仅供比赛评审；未授予复用许可。当前原型仅使用合成数据。Foundation 与拒付主线均已在签名 callback seam 跑通；真实 tenant smoke 和生产部署仍未完成。

## Quick Start

要求 Python 3.12。以下命令只在 `127.0.0.1` 启动本地服务。

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:OCEANPILOT_DB_PATH = "work/oceanpilot.db"
.\.venv\Scripts\python.exe -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8002
```

需要启用 DeepSeek 时，将 `.env.example` 复制为不会被 Git 跟踪的 `.env`，填写
`DEEPSEEK_API_KEY`，并设置 `OCEANPILOT_MODEL_PROVIDER=deepseek`、
`OCEANPILOT_CHARGEBACK_LIVE_MODEL=1`。启动时显式加载该文件：

```powershell
.\.venv\Scripts\python.exe -m uvicorn oceanpilot.main:create_app --factory --env-file .env --host 127.0.0.1 --port 8002
```

密钥存放、轮换、live 测试和安全路由见 [DeepSeek 本地接入指南](docs/deepseek-setup.md)。

Linux / macOS：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
export OCEANPILOT_DB_PATH=work/oceanpilot.db
.venv/bin/python -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8002
```

启动过程由 FastAPI lifespan 创建 SQLite schema 并执行一次 Store 健康检查。构造或导入应用本身不会打开数据库连接。飞书回调为可选：设置 `FEISHU_APP_ID/APP_SECRET/VERIFICATION_TOKEN/ENCRYPT_KEY` 后启用（凭据只走环境变量），配置步骤见 [docs/feishu-setup.md](docs/feishu-setup.md)，演示脚本见 [docs/demo.md](docs/demo.md)。未配置飞书时核心 API 与 `/health` 正常，飞书路由返回固定安全 `503`。

## API Walkthrough

服务运行后，在另一个 PowerShell 窗口执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\examples\demo.ps1 -BaseUrl http://127.0.0.1:8002
```

脚本按顺序验证：

1. `GET /health` 返回 `200`；
2. `POST /api/v1/cases` 创建一个 synthetic 支付异常案件并返回 `201`；
3. `POST /api/v1/cases/{case_id}/evidence` 追加 `context.environment=PROD` 并返回 `201`；
4. `GET /api/v1/cases/{case_id}` 读取持久化后的案件视图；
5. `POST /api/v1/cases/{case_id}/diagnose` 返回真实 `DiagnosisResponse`（首次 `201`，相同诊断身份 replay `200`）。

首次追加证据返回 `201`；同一 `evidence_id` 和规范化内容重放返回 `200`；同一 ID 携带不同内容返回安全 `409 EVIDENCE_CONFLICT`。演示脚本不启动或关闭服务器，也不访问外部服务。

## What Is Deliberately Deferred

已完成（截至 `v0.2.1`）：Foundation 诊断快照 CAS 持久化、identity replay、stale 检查与原子审计；RFC 9457 Problem Details、request/trace 关联头与 OpenAPI 错误矩阵；经签名校验的 Foundation 飞书事件/卡片回调；synthetic 拒付 Supervisor、补证、评估、打包、mock 申诉、时限计算、预防建议、审计/agent trace；Web 控制台、Docker、跨平台 transcript、基础结构化日志/进程内指标和离线评测。

仍然延期：

- 真实 Oceanpayment 数据/API、真实银行规则、外部 A2A、MCP、工单、上游申诉、自动派单或任何资金动作；
- RAG/向量检索，以及 company-data 校准；
- 公网 HTTPS 部署与拒付真实 tenant smoke；
- 定时任务、出站 SLA 通知和超期后的生产工作流变更；
- 鉴权、限流、生产可观测性后端、云数据库、备份和发布运维。

逐项依赖、文件所有权与可执行验收命令见 [docs/roadmap/incomplete-work.md](docs/roadmap/incomplete-work.md)。延期能力不会用内存假结果或展示文案代替。

## Verification

`v0.2.1` 标签的本地全量套件基线为 `1095 passed, 3 skipped`：无 PowerShell 环境跳过一个 `demo.ps1` 语法测试，无 `ANTHROPIC_API_KEY` 跳过两个可选 live Claude 测试。Ruff lint、`ruff format --check`、compileall、19 路径 OpenAPI 合同与 diff 检查均通过；TestClient 运行会出现一条来自固定版本 Starlette/httpx 组合的上游弃用警告。GitHub Actions（Python 3.12）在 [`.github/workflows/ci.yml`](.github/workflows/ci.yml) 中定义；分支新增测试后的准确数量与远程结果以对应 commit 的实际门禁为准。

可重复执行（Linux / macOS；Windows 用 `.\.venv\Scripts\python.exe`）：

```bash
.venv/bin/python --version
.venv/bin/python -m pytest -p no:cacheprovider -q
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/python -m compileall -q src tests
.venv/bin/python -m pytest tests/api/test_lifespan_openapi.py -q
git diff --check
```

Foundation 遗留的 `ruff format` 格式漂移已在一个独立的机械提交中统一处理（不与功能/文档改动混合），`ruff format --check src tests` 现已通过。

## Competition Context

本项目用于 [2026 AI 先锋未来人才大赛](https://activity.feishu.cn/future-talent#challenge) 的 Oceanpayment 企业命题探索，关注跨境商户接入与上线后问题协作。当前实现覆盖 synthetic `PAYMENT_INCIDENT` Foundation 与 synthetic 拒付申诉集群，不代表 Oceanpayment 官方产品，也未获得其真实接口、流程、银行规则或生产数据验证。

领域证据契约、状态机、原子事务和规则表属于本参赛方案中的组合设计；其中使用的通用工程方法不被表述为团队独创算法。公开代码当前仅供比赛评审，未授予复用许可。
