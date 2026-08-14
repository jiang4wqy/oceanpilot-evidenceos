# OceanPilot Deferred Work Register

> **当前状态（`v0.2.1`）：** 跟踪 Foundation Tasks 9–18 的 Issues #3–#9 与拒付集群
> Issues #10–#20、#22–#36 均已关闭。已发生的交付包括 Foundation 诊断与签名飞书
> callback seam、synthetic 拒付 HTTP/Web 闭环、Docker、基础结构化日志/进程内指标和
> 比赛演示；关闭 tracker 不补写未发生的 Gate 3/Gate 4 或真实 tenant smoke。真实数据、
> 真实外部系统和生产就绪性从未被声明为已完成。

## Current Remaining Work

数据依赖主线由 [#21](https://github.com/jiang4wqy/oceanpilot-evidenceos/issues/21)
跟踪：导入 schema、loader 与 synthetic fixture 已完成；Issue 保持 `status:blocked`，
因为公司尚未提供可接受的真实/脱敏输入。2026-08-08 的非数据维护迭代另由 #38（文档
事实同步）、#39（飞书外部标识落库哈希）与 #40（演示 CI 门禁）跟踪；这些维护项不把
下表的真实集成 backlog 改写为已完成能力。

| 工作项 | 跟踪状态 | 当前已有 | 尚未完成 / 完成边界 |
|---|---|---|---|
| 公司数据校准 | #21 — open / blocked | reason-code、银行规则、脱敏案例的严格 schema、loader 与 synthetic 单测 | 公司流程、保密等级、真实 reason-code/证据模板/银行规则与脱敏案例；任何导入前仍需安全审查 |
| 拒付飞书真实接线 | Unscheduled backlog | `FeishuChannel` 解析/渲染适配器及渠道 seam 测试 | 接入现有签名 event/card-action 路由、公网 HTTPS 与真实 tenant smoke；当前签名回调只服务 Foundation `PAYMENT_INCIDENT` |
| 银行规则检索 | Unscheduled backlog | `KnowledgeBase` port、内存精确层级匹配与可灌入 schema | 真实规则校准、RAG/向量检索与质量验收 |
| SLA 主动作业 | Unscheduled backlog | 可注入 Clock、15/45 天 deadline 与 T-7/T-3/T-1 提醒标志计算 | Scheduler/Messenger、出站通知、升级和生产状态变更；当前不发送真实提醒 |
| 外部协作与上游 | Unscheduled backlog | shared-case internal A2A 编排、人工闸门与 synthetic mock connector | 真实外部 A2A、Oceanpayment/MCP/工单/上游申诉连接；不执行真实业务动作 |
| 生产化 | Unscheduled backlog | 本地 SQLite、PII-free 请求日志、进程内指标、Docker demo | 鉴权、限流、生产可观测性后端、云数据库/备份、部署与运行保障 |
| 证据文件实体 | Unscheduled backlog（见已关闭 tracker #33） | 当前只记录证据类型是否具备 | 文件对象、对象存储、内容扫描、生命周期与访问控制 |

未排期项不是承诺中的 active work；开始实现前应分别创建 Issue、冻结范围和验收标准。

## Historical Foundation Milestone Register

以下表格原样保留 Foundation 里程碑制定时的任务快照，用于追溯当时的依赖、所有权和
验收口径。表内“当前已有”“未完成”“当前材料”等词均指制定该计划时的状态，**不是
`v0.2.1` 的当前 backlog 或完成声明**；尤其不据此补写未发生的 Gate 3/Gate 4 sign-off。

| 模块 | 正式任务 | 优先级 | 当前已有 | 未完成内容 | 不完成的用户影响 | 后续依赖 | 预计改动文件 | 可独立分工工作轨 | 可执行完成验收 |
|---|---:|---:|---|---|---|---|---|---|---|
| diagnosis persistence | Task 9 | P0 | 六表 schema、`CaseStoreSession` 端口、诊断通用 hydrator、案件/证据原子事务 | 诊断 snapshot CAS、唯一键 replay、stale 输入优先级、同案证据引用、原子审计和失败回滚 | diagnose 只能返回 501，无法保存或可靠重放诊断 | 已完成 Tasks 7–8；完成后交 Gate 2 | `src/oceanpilot/adapters/persistence/sqlite.py`；`tests/repository/test_diagnosis_store.py`；`test_diagnosis_concurrency.py`；`test_cross_case_references.py` | **Track P9 / Persistence writer**：独占上述 Store 与三份测试；不修改 API/CaseService | `.\.venv\Scripts\python.exe -m pytest tests/repository/test_diagnosis_store.py tests/repository/test_diagnosis_concurrency.py tests/repository/test_cross_case_references.py -q --basetemp .superpowers/sdd/pytest-roadmap-task9` |
| Persistence Gate 2 | Task 10 | P0 | 案件/证据真实文件 SQLite 测试、rollback/FK/concurrency 证据；Gate 1 已 PASS | 独立审查 Task 9 的连接、事务、CAS、去重、跨案件引用和残留 WAL/SHM，并提交 Gate 2 报告 | 无独立证据证明完整 persistence 边界，后续诊断/API 写窗口不能安全开启 | diagnosis persistence Task 9 clean commit | `docs/reviews/gate-2-persistence.md`；只读审查 `src/oceanpilot/adapters/persistence/**` 与 `tests/repository/**` | **Track G2 / Independent reviewer**：不写技术代码，只在所有证明成立时写 PASS 报告 | `.\.venv\Scripts\python.exe -m pytest tests/repository -q --basetemp .superpowers/sdd/pytest-roadmap-gate2; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; if (-not (Select-String -Quiet -LiteralPath docs/reviews/gate-2-persistence.md -Pattern '\bPASS\b')) { throw 'Gate 2 PASS missing' }` |
| Full service orchestration | Task 11 | P0 | Foundation `CaseService.create_case/get_case/add_evidence`、commands、规则引擎与 Store port；当前单次 CAS | `diagnose()` 编排、诊断 replay、最多三次 evidence CAS 重算、snapshot 失效与完整竞态语义 | 不能产生可持久化诊断；并发写需要调用方重试 | Task 9 与 Gate 2 PASS | `src/oceanpilot/application/case_service.py`；`tests/domain/test_case_service.py`；`tests/domain/test_diagnose_service.py` | **Track S11 / Service writer**：用 fake Store 锁定调用顺序；不改 SQL 或 HTTP | `.\.venv\Scripts\python.exe -m pytest tests/domain/test_case_service.py tests/domain/test_diagnose_service.py -q --basetemp .superpowers/sdd/pytest-roadmap-task11` |
| Full API safety contract | Tasks 12–14 | P0 | lifespan、health、五条路径、严格 DTO、固定三字段安全错误、基础 404/405/422/500/503 映射 | RFC 9457 `application/problem+json`、request/trace context 与 header、白名单扩展、完整 OpenAPI error/replay schema、真实 diagnose 路由、对抗 checkpoint | API 可本地演示，但缺少完整可观测性与对抗性合同，不能作为生产接口 | Task 11 完成；Task 14 必须由独立 reviewer 执行 | `src/oceanpilot/{config.py,main.py,api/**}`；`tests/{conftest.py,api/**}`；`docs/reviews/checkpoint-api.md` | **Track A12-13 / API writer** 后接 **Track A14 / API reviewer**；reviewer 只读技术文件 | `.\.venv\Scripts\python.exe -m pytest tests/api -q --basetemp .superpowers/sdd/pytest-roadmap-api; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; if (-not (Select-String -Quiet -LiteralPath docs/reviews/checkpoint-api.md -Pattern 'PASS_CHECKPOINT')) { throw 'API checkpoint missing' }` |
| Three synthetic E2E cases | Task 15 | P1 | 一个本地 Foundation PowerShell 流程；四条 deterministic rules 已有领域测试 | 3DS/callback、risk decline、configuration mismatch 三个业务组（四个 rule subcases）的 internal synthetic adapter 与 HTTP 闭环；检查 route/ticket/audit/source-quality 差异 | 评委只能看到基础数据链，无法查看三种诊断业务闭环 | API checkpoint PASS 且 diagnose 已启用 | `src/oceanpilot/adapters/evidence/synthetic.py`；`tests/api/test_three_synthetic_cases.py`；`examples/demo.ps1` | **Track E15 / Scenario writer**：独占 synthetic adapter、E2E 测试和演示，不新增 HTTP 来源注入接口 | `.\.venv\Scripts\python.exe -m pytest tests/api/test_three_synthetic_cases.py -q --basetemp .superpowers/sdd/pytest-roadmap-e2e` |
| security / CI | Tasks 16–17 | P1 | 领域敏感扫描、安全固定错误、当前本地测试与 Task 3 的 717-test 基线 | 五表面 sentinel 回归（响应/日志/审计/DB bytes/serialized snapshots）、最小 Python 3.12 GitHub Actions、正式 Gate 3 E2E/API/security/audit 独立审查 | 敏感数据和主链回归缺少跨表面自动证据；不能声称远程 CI 结果 | Task 15；完整 API；Task 17 必须与 writer 分离 | `tests/security/test_no_sensitive_data_leak.py`；`.github/workflows/ci.yml`；必要时仅修已证明缺陷的窄生产文件；`docs/reviews/gate-3-api-main-chain.md` | **Track S16 / Security writer** 后接 **Track G3 / Independent reviewer**；禁止未由测试证明的广泛 hardening | `.\.venv\Scripts\python.exe -m pytest tests/domain tests/repository tests/api tests/security -q --basetemp .superpowers/sdd/pytest-roadmap-gate3; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; if (-not (Select-String -Quiet -LiteralPath docs/reviews/gate-3-api-main-chain.md -Pattern '\bPASS\b')) { throw 'Gate 3 PASS missing' }` |
| Final release | Task 18 | P2 | Foundation README、architecture、deferred-work register 与本地 demo；报名段落已冻结 | 全量事实审计、clean-clone 重现、依赖/secret 扫描、最终 demo 文档、报名事实同步、经用户授权的远程身份/空仓校验、匿名公开读取和 Gate 4 报告 | 当前材料不能作为最终提交版本，GitHub URL 不能当作已公开验证地址 | Gate 2、API checkpoint、Gate 3 全部 PASS；远程写入需用户明确授权 | `README.md`；`docs/{architecture.md,demo.md}`；`docs/submission/registration-copy.md`；`docs/reviews/gate-4-release.md`；不创建 `LICENSE`，除非另行授权 | **Track R18 / Release controller**：独占事实文档与远程发布；先只读核验账号、remote 与目标仓，再决定是否写远程 | `.\.venv\Scripts\python.exe -m pytest -q --basetemp .superpowers/sdd/pytest-roadmap-release; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; if (-not (Select-String -Quiet -LiteralPath docs/reviews/gate-4-release.md -Pattern '\bPASS\b')) { throw 'Gate 4 PASS missing' }; if ([string]::IsNullOrWhiteSpace($env:OCEANPILOT_PUBLIC_README_URL)) { throw 'verified public README URL is required' }; $r = Invoke-WebRequest -UseBasicParsing -Uri $env:OCEANPILOT_PUBLIC_README_URL; if ($r.StatusCode -ne 200) { throw 'public README verification failed' }` |

## Historical Sequencing and Ownership Rules

1. Task 9 writer 完成并停写后，Gate 2 reviewer 才开始；Gate 2 没有 PASS 时不得启动完整诊断编排。
2. Task 11 先让服务层获得真实 diagnose 语义，再由 API writer 替换 501 占位；API reviewer 与 writer 分离。
3. 三个 synthetic E2E 场景建立在真实诊断链上，不用内存 snapshot 或伪返回抢跑。
4. Security writer 只修 sentinel 测试实际暴露的窄缺陷；Gate 3 reviewer 独立复跑主链。
5. Release controller 最后同步 README、报名文案和公开状态。未通过匿名读取验证前，不把仓库 URL 标为可提交。

## Current Verification Note

Foundation 的 19 文件格式漂移已在独立机械提交中修复；`ruff check src tests` 与
`ruff format --check src tests` 当前通过。不要把该已解决的历史债务重新列为 backlog。

TestClient 仍会报告一条固定依赖组合产生的 Starlette/httpx 弃用警告。依赖升级需独立
验证，不能在文档事实同步中静默改版本。
