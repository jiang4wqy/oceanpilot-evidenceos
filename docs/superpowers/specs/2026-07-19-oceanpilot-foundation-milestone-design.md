# OceanPilot 基础可运行框架里程碑设计

日期：2026-07-19
状态：待书面复核
基线提交：`0cbff779a0f728a1c4e12da7834112933c26cd80`

## 1. 决策与目的

当前目标从“立即完成全部生产级 MVP”缩减为“先交付一个诚实、可运行、适合上传 GitHub 的基础框架”。本里程碑保留已经完成的领域模型、规则引擎、状态机、应用端口、SQLite schema 以及案件/证据原子持久化，不返工 Tasks 0–8。

本阶段只要求：

1. 应用能够启动并初始化本地 SQLite；
2. 健康检查可用；
3. 创建案件、读取案件、追加证据三个基础流程可用；
4. 诊断路由存在，但明确返回“功能延期”，不伪造诊断结果；
5. README、架构说明、演示脚本和未完成清单能够让队友与评委快速理解项目；
6. 所有未完成能力都记录当前状态、风险、依赖和后续验收标准。

原正式设计与实施计划继续保留，作为后续完整实现依据。本文件只覆盖当前基础框架里程碑，不宣称原 Tasks 9–18 已完成。

## 2. 选择的方案

采用“薄应用层 + 可运行 API + 显式延期诊断”的方案。

```text
HTTP / OpenAPI
    ↓
基础 CaseService（创建、读取、追加证据）
    ↓
既有领域策略与状态机
    ↓
既有 SQLite Store（案件/证据原子事务）
```

诊断接口不绕过应用层、不直接调用规则后丢弃结果，也不使用内存假持久化。它固定返回安全的 `501 FEATURE_DEFERRED`，直到诊断 CAS 持久化和完整编排通过后再启用。

## 3. 本里程碑交付范围

### 3.1 应用启动与配置

- 提供 `Settings`，默认数据库路径为 `work/oceanpilot.db`；
- 提供 `create_app()`，无导入时数据库副作用；
- 使用 FastAPI lifespan 初始化 schema 并执行一次 Store 健康检查；
- 提供 `GET /health`，数据库可用时返回 `200 {"status":"ok"}`；
- 继续冻结 Python 3.12、FastAPI、Pydantic 和原生 `sqlite3`，不新增框架依赖。

### 3.2 基础案件服务

只实现三个方法：

- `create_case(command)`：构造初始 readiness、状态、revision 和 `CASE_CREATED` 审计，再调用既有原子 Store；
- `get_case(case_id)`：读取完整案件视图，不存在时返回稳定的 `CaseNotFound`；
- `add_evidence(command)`：从当前 snapshot 规范化证据、重算 readiness/目标状态、生成所需审计，并调用既有原子 Store。

本阶段只做单次 CAS 尝试；并发冲突返回稳定 `409`。最多三次重算重试、诊断编排及策略版本回放延期。

### 3.3 HTTP 路由

| 路由 | 当前行为 | 状态 |
|---|---|---|
| `GET /health` | SQLite 健康检查 | 可用 |
| `POST /api/v1/cases` | 创建 synthetic payment incident 案件 | 可用 |
| `GET /api/v1/cases/{case_id}` | 返回案件、readiness、证据与 revisions | 可用 |
| `POST /api/v1/cases/{case_id}/evidence` | 追加一条受限证据，支持 Store replay/conflict | 可用 |
| `POST /api/v1/cases/{case_id}/diagnose` | 固定返回安全 `501 FEATURE_DEFERRED` | 显式占位 |

请求只接收必要字段，未知字段拒绝；案件与证据 ID 必须是规范 UUIDv4；`synthetic` 必须为严格布尔 `true`。API 不直接计算 readiness、不执行 SQL，也不修改 revision。

### 3.4 基础错误与输出

- 4xx/5xx 使用稳定、安全的 JSON 错误结构，至少包含 `status`、`code`、`detail`；
- 不返回异常文本、SQL、验证输入或敏感哨兵；
- 映射基础错误：案件不存在 `404`、证据冲突/并发写 `409`、数据库不可用 `503`、诊断延期 `501`；
- 完整 RFC 9457、全链路 trace/request ID、完整 OpenAPI 错误媒体类型矩阵延期，但必须在未完成清单中标明。

### 3.5 GitHub 展示材料

- `README.md`：问题、方案、当前能力、快速启动、API 示例、诚实限制；
- `docs/architecture.md`：组件边界、数据流、已完成与延期边界；
- `docs/roadmap/incomplete-work.md`：逐模块未完成清单；
- `examples/demo.ps1`：初始化、健康检查、创建案件、追加证据、读取案件，并展示诊断接口的延期响应。

## 4. 明确不做

本里程碑不实现：

- 诊断快照的 SQLite CAS、去重、历史回放和跨案件引用事务；
- `CaseService.diagnose()` 与完整规则编排；
- 并发诊断竞态、诊断 stale-vs-replay 优先级；
- 三个完整 synthetic 闭环案例；
- 生产级日志、指标、鉴权、限流、WORM/JCS/哈希链；
- 部署、容器、云数据库或外部支付系统连接；
- 全量五表面安全回归与 GitHub Actions release gate。

不得使用假结果掩盖以上缺口，也不得在 README 或报名材料中写“完整实现”“生产可用”或“全自动诊断已上线”。

## 5. 未完成内容登记要求

`docs/roadmap/incomplete-work.md` 必须使用下表结构，并逐项填写，不允许只有泛化 TODO：

| 模块 | 当前已有 | 未完成内容 | 不完成的影响 | 后续依赖 | 完成验收 |
|---|---|---|---|---|---|
| 诊断持久化 | schema、端口、通用 hydrator | CAS、唯一键 replay、stale 检查、原子审计 | diagnose 不能启用 | 原 Task 9 | repository/concurrency/FK 测试通过 |
| Persistence Gate | 案件/证据事务测试 | 独立 Gate 2 报告 | 不能宣称完整持久化通过 | 诊断持久化 | Gate 2 报告为 PASS |
| 应用编排 | commands、基础 service | 诊断编排、三次 CAS 重算 | 并发体验和诊断缺失 | 原 Task 9、11 | service 单元测试与竞态测试通过 |
| API 安全合同 | 基础安全错误 | RFC 9457、trace、完整 404/405/422/500/503 | 尚非生产级 API | 原 Task 12–14 | API 对抗测试与 OpenAPI 审计通过 |
| 演示场景 | 基础 PowerShell 流程 | 三个闭环 synthetic 案例 | 评委看不到完整业务闭环 | 诊断链 | 三案例 E2E 通过 |
| 安全与 CI | 领域敏感扫描、现有测试 | 五表面回归、GitHub Actions | 自动化保障不完整 | 完整 API | security suite 与 CI 通过 |
| 发布材料 | 基础 README/architecture | 最终事实审计、报名文案同步 | 不能作为最终提交版本 | Gates 2–3 | Gate 4 PASS |

文档还需列出对应的正式任务编号、建议优先级、预计改动文件和可独立分工的工作轨，便于后续继续拆给其他对话框。

## 6. 文件边界

基础框架预计新增或修改：

```text
src/oceanpilot/application/case_service.py
src/oceanpilot/config.py
src/oceanpilot/api/__init__.py
src/oceanpilot/api/schemas.py
src/oceanpilot/api/errors.py
src/oceanpilot/api/dependencies.py
src/oceanpilot/api/health.py
src/oceanpilot/api/cases.py
src/oceanpilot/main.py
tests/foundation/**
README.md
docs/architecture.md
docs/roadmap/incomplete-work.md
examples/demo.ps1
```

不修改领域规则、状态机、SQLite schema、现有 repository 测试和正式比赛设计。若基础服务无法在这些边界内复用既有 Store，应停止并记录依赖，不得绕过架构。

## 7. 最小验收

基础框架完成的判定条件：

1. `create_app()` 可在临时 SQLite 文件上启动和关闭；
2. 健康检查、创建、读取、追加证据的最小 happy path 通过；
3. 诊断路由稳定返回 `501 FEATURE_DEFERRED`，README 同步说明；
4. 原有 641 个测试无回归；
5. 新增 foundation 测试、Ruff、format、compileall、`git diff --check` 全部通过；
6. OpenAPI 中只出现五条批准路径；
7. 演示脚本不依赖外部网络服务；
8. 未完成清单覆盖第 5 节全部模块，并给出后续可验证终点。

## 8. 后续恢复完整实现的顺序

1. 完成原 Task 9 诊断持久化；
2. 执行 Task 10 Gate 2；
3. 补齐 Task 11 诊断编排与 CAS 重试；
4. 将 diagnose 占位替换为真实接口并完成 Tasks 12–14 安全合同；
5. 完成三案例、Security/CI 与 Gates 3–4；
6. 最后更新 README 和报名材料中的能力表述。

这个顺序保证基础框架不会成为另一套临时代码：后续只扩展应用服务和诊断持久化，不重写领域模型、SQLite schema 或公开路由。
