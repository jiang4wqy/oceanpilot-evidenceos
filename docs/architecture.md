# OceanPilot Foundation Architecture

## 1. Scope

当前系统是一个使用合成数据的本地支付异常协作原型。它只启用 `PAYMENT_INCIDENT`，提供健康检查、案件创建/读取、证据追加、确定性诊断，以及一条经签名校验的飞书事件/卡片回调链路（建案 → 补问 → 达标诊断 → 人工确认审计）。诊断主链已接入并持久化（诊断入口不再返回 `501`）。仍然没有真实 Oceanpayment 数据、A2A、MCP、工单或支付系统连接；飞书回调只对合成案件生效，人工确认只写审计、不改变案件状态、不执行任何业务动作。

## 2. Current Runtime Shape

```mermaid
flowchart LR
    Client["Local client / OpenAPI"] --> API["FastAPI routes and strict DTOs"]
    Feishu["Feishu events / card actions"] --> Verify["Signature + token verify, idempotent claim"]
    Verify --> Orchestrator["FeishuOrchestrator"]
    Orchestrator --> Service["CaseService"]
    API --> Service
    Service --> Domain["Evidence policy, state machine, DiagnosisEngine"]
    Service --> Port["CaseStoreSession port"]
    Port --> SQLite["Local SQLite store"]
    Orchestrator --> FeishuStore["Feishu callback SQLite (separate file)"]
```

依赖方向由外向内。领域层不知道 FastAPI 或 SQLite；应用服务依赖领域模型和 Store port；SQLite adapter 实现 port；API 只把 HTTP 请求映射为应用命令。

## 3. Layer Ownership

| Layer | Owns now | Must not own |
|---|---|---|
| FastAPI API | 严格 DTO、UUIDv4/RFC3339 边界、依赖注入、状态码、固定安全错误 | readiness 计算、规则执行、SQL、revision 修改、路由选择 |
| `CaseService` | 创建/读取/追加证据的命令顺序，一次 Store session，一次 CAS 写入尝试 | HTTP 细节、SQL、伪诊断结果、外部网络调用 |
| Domain | 证据规范化、ActiveEvidenceView、readiness、状态机、置信度和四条确定性规则 | 数据库连接、当前时间/UUID 生成、Web 框架 |
| Store port / SQLite adapter | 连接生命周期、外键、自包含短事务、条件更新、replay/conflict、审计持久化 | 规则判断、网络调用、业务文案 |

API 因此永远不直接拥有 readiness、SQL 或 revisions。它返回的 `CaseView` 是应用服务与 Store 完成领域和事务处理后的结果。

## 4. Foundations Already Present Before This Milestone

原实施计划 Tasks 0–8 已留下可复用基础，而不是另起一套临时代码：

| Task | Existing asset |
|---:|---|
| 0 | 报名文案与能力声明边界被冻结；该文案的最终事实同步仍留到 Task 18 |
| 1 | Python 3.12 项目、固定依赖和测试工具链 |
| 2 | 严格 Pydantic 领域模型、枚举、UUIDv4、带时区时间和 immutable evidence |
| 3 | EvidenceItem 规范化、content hash、ActiveEvidenceView 与 readiness 策略 |
| 4 | 显式状态机、置信度门和四个 rule ID 的确定性规则表 |
| 5 | 冻结的应用 commands、稳定错误和原子 Store ports |
| 6 | 已提交的 Gate 1 独立领域审查报告 |
| 7 | 原生 `sqlite3` 连接、六表 schema、外键和事务 primitive |
| 8 | 案件创建与证据追加的原子事务、replay/conflict、rollback 和并发写检查 |

Foundation Tasks 1–3 在这些资产上新增薄 `CaseService`、FastAPI lifespan/安全错误，以及精确五条公开路径。没有复制或重写领域规则与 SQLite schema。

## 5. Lifecycle and Connections

`create_app()` 解析 `Settings`，构造 Store factory 与 `CaseService`，并立即挂到 `app.state`；这一阶段不创建数据库文件。进入 FastAPI lifespan 后才执行 schema 初始化，再打开一个 Store session 做健康检查。每个业务命令通过 factory 获得自己的连接并显式关闭；SQLite 连接启用外键并使用短事务。

默认数据库路径为 `work/oceanpilot.db`，可由 `OCEANPILOT_DB_PATH` 覆盖。服务示例只绑定 `127.0.0.1`。

## 6. Command Data Flows

### Create case

```text
strict CreateCaseRequest
  -> server request/trace IDs
  -> CaseService validates PAYMENT_INCIDENT and sensitive-data boundary
  -> domain computes empty readiness and creation status
  -> Store atomically inserts case + CASE_CREATED audit
  -> CaseView
```

新案件从 `case_revision=1`、`evidence_revision=0` 开始。

### Append evidence

```text
strict EvidenceCreateRequest
  -> server-owned MERCHANT / USER_REPORTED / synthetic origin
  -> load one CaseInputSnapshot
  -> normalize EvidenceItem and content hash
  -> rebuild ActiveEvidenceView and readiness
  -> compute target state
  -> Store atomically appends evidence + updates case/revisions + writes audits
  -> created CaseView or replay/conflict result
```

同一证据 ID 和同一规范化内容由 Store 判定 replay，不重复写入；同一 ID 的不同内容返回 `409 EVIDENCE_CONFLICT`。当前应用服务对并发 case revision 冲突只做一次尝试，不在隐藏循环中重算。

### Read case

`GET /api/v1/cases/{case_id}` 通过 `CaseService.get_case()` 和 Store hydrator 返回案件、readiness、按稳定顺序重建的证据以及可选当前诊断。缺失案件返回固定 `404 CASE_NOT_FOUND`。

### Diagnose

诊断主链已接入。`CaseService.diagnose()` 载入当前证据视图，强制 readiness，调用 `DiagnosisEngine`，并把诊断快照、假设、证据引用、责任路由与审计原子提交。诊断身份为 `(case_id, evidence_revision, policy_version)`：相同身份 replay 已持久化的快照，不新增 case revision、诊断记录或审计；证据 revision 用 compare-and-swap，stale 输入在重试预算耗尽后返回稳定冲突；跨案件证据引用回滚整个事务。新证据只让旧诊断历史化，不原地修改。

```text
POST /api/v1/cases/{case_id}/diagnose
  -> 首次诊断 201 CREATED
  -> 相同 (evidence_revision, policy_version) 200 REPLAYED
  -> 严格 DiagnosisResponse（候选、置信度、复核原因、责任路由、证据引用、审计引用）
```

低置信度、冲突证据、风险决策、低来源质量和无规则结果进入人工复核。飞书提交的证据固定为 `USER_REPORTED`（低来源质量），因此其诊断始终要求人工复核。

## 7. Storage Boundary

核心案件库的 SQLite schema 包含六张表：`cases`、`evidence_items`、`diagnosis_snapshots`、`hypotheses`、`hypothesis_evidence_refs` 和 `audit_events`。运行路径写入案件、证据、诊断快照及相应审计。飞书回调状态（事件/动作回执、chat↔case 绑定、确认审批审计）保存在一个**独立**的 SQLite 文件（`OCEANPILOT_FEISHU_DB_PATH`），不与核心案件库混表。

案件聚合和审计在同一事务中提交。证据追加使用预期 case/evidence revisions 做条件写入，避免静默覆盖；Store 从不调用规则或外部服务。schema 初始化不启用 WAL，也没有文件上传、WORM、JCS 或哈希链声明。

## 8. HTTP and Trust Boundary

| Method and path | Current result |
|---|---|
| `GET /health` | SQLite 可用时 `200 {"status":"ok"}` |
| `POST /api/v1/cases` | synthetic payment incident 创建成功时 `201` 和 `Location` |
| `GET /api/v1/cases/{case_id}` | 读取成功 `200` |
| `POST /api/v1/cases/{case_id}/evidence` | 首次写入 `201`；replay `200`；conflict `409` |
| `POST /api/v1/cases/{case_id}/diagnose` | 首次 `201`；相同身份 replay `200`；stale `409`；未达标 `409 CASE_NOT_READY` |
| `POST /api/v1/integrations/feishu/events` | 校验后处理消息事件；固定安全响应；未配置飞书返回 `503` |
| `POST /api/v1/integrations/feishu/card-actions` | 校验后处理证据/确认卡片动作；固定安全响应；未配置飞书返回 `503` |

请求模型拒绝未知字段、非 UUIDv4 ID、非严格 `true` 的 synthetic 值、NaN/Infinity、非闭合 typed value 和无时区/非精确 RFC3339 时间。可疑敏感输入在领域边界再次扫描。当前错误体固定为 `status`、`code`、`detail`，不复制原始验证输入、异常文本或 SQL。

RFC 9457 `application/problem+json`、request/trace 关联头和跨表面敏感数据回归已接入。鉴权、限流、生产日志与指标仍属后续生产化工作。

## 9. Deferred Extension Order

诊断持久化、服务编排、完整 API 安全合同、三个 synthetic E2E 场景、安全 sentinel 与 Python 3.12 CI、以及飞书事件/卡片回调链路均已接入（PR1–PR5）。剩余为入围后的生产化工作：真实 Oceanpayment / A2A / MCP / 工单接入、鉴权限流与生产日志、公网 HTTPS 部署与飞书真机联调、以及容器与云数据库运维。在这些完成前，不声明真实系统集成、自动派单、业务效果或生产就绪性。

各里程碑的文件所有权、影响与可运行验收命令见 [roadmap/incomplete-work.md](roadmap/incomplete-work.md)；飞书控制台配置见 [feishu-setup.md](feishu-setup.md)，本地演示见 [demo.md](demo.md)。
