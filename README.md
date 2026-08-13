# OceanPilot EvidenceOS

![OceanPilot EvidenceOS：证据驱动的跨境商户成功协作系统；缺证先补问、过门再判断、高风险动作由人工确认](docs/assets/submission/oceanpilot-hero.png)

**证据驱动的综合商户成功智能体。** OceanPilot 用“案件 + 证据契约”串联问题、证据、判断与交接：缺证先补问，达到证据门槛后再判断，高风险动作由人工确认。

> **当前事实边界：** 仓库已验证两个本地、离线、synthetic 纵向切片：支付异常协作与拒付申诉。真实 Oceanpayment 数据、真实飞书测试群、真实上游提交与生产部署均未验证。系统不执行支付、退款、风控放行、资金移动、生产配置变更或真实上游提交。

## 项目定位

OceanPilot 的商业愿景是覆盖商户接入与上线后协作的综合智能体，而不是只解决一个支付报错。当前比赛版本用两条可检查的纵向链路证明这套架构：

1. **支付异常协作：** 建案 → 角色化补证 → 证据达标 → 确定性诊断 → 责任建议 → 人工确认审计。
2. **拒付申诉：** 原因识别 → 证据门槛 → 胜诉评估 → 材料打包 → 申诉草稿 → 人工门与审计。

8 月 16 日展示先讲支付异常，再回到拒付控制台说明它不是一次性脚本，而是同一证据驱动架构下的第二个业务切片。

### 三个核心设计

- **商户成功案件（Merchant Success Case）：** 用持续演进、可版本化的案件聚合上下文与协作状态。
- **案件证据契约（Case Evidence Contract）：** 证据绑定来源、时间、版本与引用；资料不足时先定位缺口。
- **受控协作闭环：** AI 负责理解与建议，确定性规则守住状态、门槛和路由，人工确认只记录审计，不等于执行业务动作。

## 当前已验证能力

| Capability | Status | Current behavior |
|---|---|---|
| Payment case core | Available (synthetic) | 创建/读取 `PAYMENT_INCIDENT` 案件，追加证据，计算 readiness，持久化 revision 和审计 |
| Diagnosis | Available (synthetic) | 四条确定性规则；诊断 snapshot CAS、证据引用、责任路由、人工复核原因和 identity replay |
| Payment cockpit | Available (synthetic) | `/demo/payment-incident` 通过公开 API 演示 3DS/回调、风控拒绝、商户侧和 PSP 侧配置不匹配 |
| Feishu callbacks | Available (synthetic) | 签名/Token/时窗校验，消息建案、角色化补问、诊断卡和人工确认审计；未配置时固定安全 `503` |
| Signed local fixture | Available (offline) | 随机运行时凭据、真实 verifier/route/store、事件和动作 replay、一次审批审计；无外网，确认前后 core case 不变 |
| Chargeback cluster | Available (synthetic) | `/demo` 演示拒付识别、补证、评估、打包、申诉草稿、人工门、审计和安全护栏；上游为 mock |
| Real integrations | Not verified | 真实 Oceanpayment、A2A、MCP、工单、真实飞书群和真实上游提交仍待接入/联调 |
| Production readiness | Not claimed | 鉴权、限流、生产日志/指标、部署与运行保障尚未完成 |

公开支付 API 固定证据来源为 `MERCHANT / USER_REPORTED / synthetic=true`。调用方不能注入来源可信度、状态、revision、置信度或路由结论。

## 两个演示入口

启动服务后：

- `/demo/payment-incident`：8 月 16 日主展示，四类支付异常的一键 synthetic 闭环。
- `/demo`：拒付申诉智能体控制台，也是根路径 `/` 的默认落点。

两页互相链接，均显示 synthetic 与禁止业务动作边界。支付 cockpit 展示的 readiness、规则、置信度、复核原因、责任团队、证据引用、下一动作和审计引用全部来自公开 API 响应，不在页面伪造。

## 证据先行闭环

OceanPilot 让 AI、确定性规则与人工遵守同一套证据口径：资料不足先定位缺口，达到门槛后才输出带引用的候选原因，高风险建议始终由人工确认。

```text
问题建案 → 证据补问 → 证据门槛 → 确定性诊断 → 责任路由 → 人工确认
```

当前竞赛分支已实现持久化诊断、支付 cockpit、拒付 console 和 signed local Feishu fixture；真实数据适配、真实飞书测试群、A2A、MCP、工单和生产 Workflow 仍在边界之外。仓库中的早期报名图片保留为历史设计材料，不作为当前能力事实源。

## 架构

```text
Payment cockpit / signed Feishu fixture / chargeback console
    -> FastAPI and callback adapters
    -> application services and agent supervisors
    -> evidence policies, state machines and deterministic rules
    -> store ports
    -> separate payment / chargeback / Feishu SQLite stores
```

API 只负责严格输入映射、状态码和安全错误；领域层负责 readiness、状态变化和规则；Store 负责事务、CAS、replay/conflict 与审计。完整组件和一致性边界见 [docs/architecture.md](docs/architecture.md)。

## Quick Start

要求 Python 3.12。以下命令只在 `127.0.0.1` 启动本地服务。

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:OCEANPILOT_DB_PATH = "work/oceanpilot.db"
.\.venv\Scripts\python.exe -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8000
```

Linux / macOS：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
export OCEANPILOT_DB_PATH=work/oceanpilot.db
.venv/bin/python -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8000
```

详细演示顺序、PowerShell 四规则脚本和 signed local Feishu fixture 命令见 [docs/demo.md](docs/demo.md)。真实飞书控制台配置见 [docs/feishu-setup.md](docs/feishu-setup.md)。

## API 与验证

当前 API 文档包含 **19 条 OpenAPI paths**；`/demo` 与 `/demo/payment-incident` 是演示页面，刻意不进入 OpenAPI。

README 不冻结易变化的总测试数，也不把工作流配置等同于远程 Actions 绿灯。可重复执行：

```bash
.venv/bin/python -m pytest -p no:cacheprovider -q
.venv/bin/ruff check src tests examples scripts
.venv/bin/ruff format --check src tests examples scripts
.venv/bin/python -m compileall -q src tests examples scripts
.venv/bin/python -c "from oceanpilot.main import create_app; assert len(create_app().openapi()['paths']) == 19"
git diff --check
```

GitHub Actions 定义在 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)。远程 CI、匿名 README 和发布状态以目标提交实际结果为准；本文不声称 Gate 4 已通过。

## 明确延期

- 真实 Oceanpayment API/生产数据、A2A、MCP、工单、SLA、通知和自动派单；
- 真实飞书测试群联调（需要公网 HTTPS 回调证据）；
- 支付、退款、风控放行、资金移动、生产配置变更和真实上游提交；
- 鉴权、限流、生产可观测性、容器/云数据库与发布运维；
- 经真实业务数据验证的效率、命中率或商业效果。

逐项状态见 [docs/roadmap/incomplete-work.md](docs/roadmap/incomplete-work.md)。

## 开发与提交材料

- [源码导航](src/oceanpilot/README.md)
- [领域内核](src/oceanpilot/domain/README.md)
- [应用层](src/oceanpilot/application/README.md)
- [适配器](src/oceanpilot/adapters/README.md)
- [HTTP 接口](src/oceanpilot/api/README.md)
- [测试与门禁](tests/README.md)
- [报名表可粘贴文本](docs/submission/registration-copy.md)
- [两页开题报告补充材料](artifacts/OceanPilot-开题报告补充材料.pdf)
- [本地演示 runbook](docs/demo.md)

## Competition Context

本项目用于 [2026 AI 先锋未来人才大赛](https://activity.feishu.cn/future-talent#challenge) 的 Oceanpayment 企业命题探索。当前仅以两个 synthetic 切片证明综合智能体架构，不代表 Oceanpayment 官方产品，也未获得其真实接口、流程、生产数据或业务效果验证。

公共仓库仅供比赛评审，未授予复用许可。领域证据契约、状态机、原子事务和规则表属于本参赛方案中的组合设计；通用工程方法不表述为团队独创算法。
