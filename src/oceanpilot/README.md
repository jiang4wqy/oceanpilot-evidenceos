# `oceanpilot` — 源码导航 / architecture map

本包采用**六边形架构（Hexagonal / Ports & Adapters）**。读代码前先记住**一条依赖规则**,其余都是它的推论。

## 唯一依赖规则

```
domain  ←  application  ←  adapters / api
（内层不知道外层的存在）
```

- **`domain/`** 与 **`application/*.py`（顶层）** 严禁 import `fastapi` / `sqlite3` / `oceanpilot.api` / `oceanpilot.adapters`。
- 由 `tests/domain/test_import_boundaries.py` **自动强制**;违反 → 测试红。
- 外层通过内层定义的 **Protocol 端口**接入(依赖倒置),具体实现留在 `adapters/`。

> 一句话:业务规则在里面且可单测,IO/框架/厂商在外面且可替换。

## 分层职责

| 层 | 目录 | 职责 | 可依赖 |
|---|---|---|---|
| **领域 Domain** | [`domain/`](domain/README.md) | 纯业务内核:确定性决策、枚举、目录、安全校验。无 IO、无框架。 | 仅 stdlib + domain |
| **应用 Application** | [`application/`](application/README.md) | 编排 + 端口(Protocol)。agent 集群、渠道无关服务、时限、脱敏。 | domain + application |
| **适配器 Adapters** | [`adapters/`](adapters/README.md) | 端口的具体实现:模型 provider、SQLite 存储、飞书/HTTP 渠道、知识库、导入。 | 任意 |
| **接口 API** | [`api/`](api/README.md) | FastAPI 路由 + 严格 DTO。把 HTTP 映射到应用服务。 | 任意 |
| **组装根** | `main.py` | `create_app()` 组装所有依赖(唯一 new 具体类的地方)。 | 任意 |
| **配置** | `config.py` | `Settings.from_env()` 读环境变量。见根目录 `.env.example`。 | stdlib |

## 两条业务链路

1. **支付异常协作(基础版 foundation)** — 建案 → 补证 → 达标诊断 → 责任路由 → 人工确认审计。入口 `api/cases.py`、`application/case_service.py`、`domain/{models,state_machine,diagnosis,evidence_policy}.py`。
2. **跨境拒付申诉集群(chargeback cluster,2026-08 pivot)** — 本轮重点。见下。

## 拒付集群的一次案件流

```
描述问题
  → Intake:抽结构化事实 + 判定拒付理由（不确定→REASON_PROPOSED 待人工确认/更正）
  → Evidence:按理由逐项补证（带 SLA 倒计时；可“无法提供→转人工复核”）
  → Assess:确定性内核算胜诉率（缺关键证据门控）、责任团队、是否需人工
  → Package:按银行/卡组织模板结构化打包
  → Appeal:生成 representment 申诉信；**人工确认后**才提交上游（mock）
```

**混合原则贯穿全程:确定性内核决策,LLM 只解释/建议(不可达时有确定性兜底),人类拍板。** 系统绝不执行支付/退款/风控/提交动作,最强动作是"建议人工复核"。

### 关键模块速查

| 关注点 | 文件 |
|---|---|
| 拒付判定内核(胜诉率/关键证据门控) | `domain/chargeback.py` |
| 证据/理由 中文目录(不漏原始码) | `domain/evidence_catalog.py`,`domain/reason_catalog.py` |
| 预防(pre-dispute)风险内核 | `domain/chargeback_prevention.py` |
| 敏感数据校验(PII/卡号) | `domain/security.py` |
| agent 集群(Intake/Evidence/Assess/Prevention) | `application/chargeback_agents.py` |
| 编排(状态机 + A2A 总线) | `application/chargeback_supervisor.py` |
| 渠道无关核心(Inbound→Delivery) | `application/channels.py`,`application/chargeback_channel_service.py` |
| 打包 / 申诉 | `application/chargeback_packager.py`,`application/chargeback_appeal.py` |
| SLA / 时限 | `application/chargeback_deadline.py`,`application/scheduling.py` |
| 模型 provider(Claude/本地/脚本/路由/脱敏) | `adapters/model/*.py` |
| 持久化(拒付) | `adapters/persistence/chargeback_sqlite.py` |
| 渠道适配器(HTTP/飞书) | `adapters/channels/**` |
| HTTP 路由 | `api/chargeback.py`,`api/chargeback_schemas.py` |

## 运行与开发

见仓库根 `README.md` 的「开发者指南」;测试与门禁见 [`tests/README.md`](../../tests/README.md)。设计背景见 `docs/design/2026-08-06-chargeback-agent-cluster-design.md`,安全分级见 `docs/security/deployment-tiers.md`。
