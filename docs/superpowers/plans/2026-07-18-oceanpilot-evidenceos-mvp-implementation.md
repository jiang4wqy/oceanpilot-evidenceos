# OceanPilot EvidenceOS MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在两天范围内交付一个只使用合成数据的本地 OceanPilot 支付异常纵向原型，完整打通案件创建、确定性补问、追加式证据、可追溯诊断、责任域建议、TicketDraft、人工闸门和审计。

**Architecture:** 采用同步的 `FastAPI → CaseService → 纯领域策略/确定性规则 → 原生 sqlite3` 单向依赖。领域层是证据归并、Readiness、状态迁移和诊断规则的唯一实现；应用层编排一个命令一条 SQLite 连接；存储层只暴露原子命令方法和 CAS，不提供通用 `save()`；HTTP 层只做 DTO 映射与安全错误转换。

**Tech Stack:** Python 3.12.x、FastAPI 0.139.2、Pydantic 2.13.4、Uvicorn 0.51.0、Python 标准库 `sqlite3`、pytest 9.1.1、HTTPX 0.28.1、Ruff 0.15.22。

## Global Constraints

- 唯一批准规格为 `docs/superpowers/specs/2026-07-18-oceanpilot-evidenceos-design.md`，基线提交为 `78e7064`；实现若要偏离，先停止并提交偏差说明。
- Python 固定为 `>=3.12,<3.13`；MVP 只使用标准库 `sqlite3`，不引入 ORM、`transitions`、消息队列、Agent 框架或模型 SDK。
- 全链路使用同步 `def`；不得在 `async def` 路由中直接调用同步 sqlite3。
- 应用由 `create_app()` 工厂创建，初始化和自检只使用 FastAPI `lifespan`，禁止 `@on_event`。
- 每个应用命令只创建一条 SQLite 连接；PRAGMA 在事务前启用并验证；写事务使用显式 `BEGIN IMMEDIATE/COMMIT/ROLLBACK`；MVP 不开启 WAL。
- 任何规则、AI、MCP 或网络计算不得位于数据库事务内。
- 所有写 DTO 使用 `extra="forbid"`、`allow_inf_nan=False`、`hide_input_in_errors=True`；只对会掩盖业务错误的字段使用严格类型，不启用无差别全局 strict。
- `EvidenceItem` 在领域内冻结且仓储无更新/删除方法；`EvidenceItem`、`DiagnosisSnapshot`、`TicketDraft`、`AuditEvent` 显式使用 `synthetic=true`。`Hypothesis` 与 `RoutingDecision` 按批准字段集不重复存该字段，只能作为同一 synthetic `DiagnosisSnapshot` 的不可变子对象存在，并由父快照及同案件外键传播合成属性。
- UUID 使用 v4；服务端使用 `uuid.uuid4()`；外部 `evidence_id` 验证版本并规范化后参与哈希和持久化。
- 只实现 `PAYMENT_INCIDENT`；不实现真实飞书 Agent/A2A/MCP、Oceanpayment API、支付推荐算法、退款、重试扣款、配置修改、真实派单、认证、前端或公网部署。
- 所有示例、测试和数据库均为合成数据；服务默认只监听 `127.0.0.1`。
- HTTP 4xx/5xx 全部使用 RFC 9457 `application/problem+json`；不得序列化原始 `exc.errors()`、`input`、未经审查的 `ctx`、异常文本、SQL 或堆栈。
- Gate 必须严格按领域 → SQLite/事务 → FastAPI 主链 → E2E/安全/发布执行；任一 Gate 未通过，不进入下一 Gate。
- 新行为的 TDD 顺序固定为：先写测试、运行确认因目标行为缺失而失败、写最小实现、运行确认通过、审查差异、提交。跨层聚合回归或独立 Gate 可能因前序任务已实现全部行为而首跑即绿；这时记录其为 characterization/regression lock，不制造假红、不改生产代码。
- 所有 PowerShell 命令直接调用 `.venv\Scripts\python.exe`，不依赖激活虚拟环境。

依赖版本于 2026-07-18 从 PyPI 官方元数据核验。实现时使用精确版本，避免两个任务安装到不同主版本：

```toml
dependencies = [
  "fastapi==0.139.2",
  "pydantic==2.13.4",
  "uvicorn==0.51.0",
]

[project.optional-dependencies]
dev = [
  "httpx==0.28.1",
  "pytest==9.1.1",
  "ruff==0.15.22",
]
```

参考：<https://pypi.org/project/fastapi/>、<https://pypi.org/project/pydantic/>、<https://pypi.org/project/pytest/>、<https://pypi.org/project/ruff/>。

---

## File Ownership and Write Coordination

### Python 技术轨独占

```text
pyproject.toml
.gitignore
.github/workflows/ci.yml
src/**
tests/**
examples/**
```

### 总控轨独占

```text
README.md
docs/architecture.md
docs/demo.md
docs/submission/**
docs/reviews/**
docs/superpowers/specs/**
docs/superpowers/plans/**
GitHub 仓库描述、分支规范化、远程创建与最终发布
```

### 共享仓库协议

两个任务继续使用 `C:\Users\lenovo\Documents\飞书比赛`，但不能同时写入或暂存：

1. 每个写入窗口开始前运行 `git status --short`，预期为空。
2. 技术轨只暂存其独占路径，提交后发送 SHA、测试命令和结果，然后暂停写入。
3. 总控轨在暂停窗口执行只读复审，必要时只修改总控独占文件并单独提交。
4. 任一任务发现对方未提交修改时停止，不使用 `git reset --hard`、`git checkout --` 或清理命令。
5. 只读检查可以并行；Git 写入、暂存、提交和分支操作必须串行。

---

## Target File Map

```text
pyproject.toml                         # 构建、依赖、pytest、Ruff 配置
.gitignore                            # venv、缓存、DB、日志、密钥和临时输出
.github/workflows/ci.yml              # Python 3.12 最小 CI
src/oceanpilot/__init__.py            # 包版本
src/oceanpilot/config.py              # Settings 与本地数据库路径
src/oceanpilot/main.py                # create_app、lifespan、middleware、装配
src/oceanpilot/domain/enums.py        # 全部闭合枚举
src/oceanpilot/domain/errors.py       # 纯领域异常
src/oceanpilot/domain/security.py     # 递归敏感信息与 Luhn 拦截
src/oceanpilot/domain/models.py       # UUID/time 类型和领域模型
src/oceanpilot/domain/evidence_policy.py # 字段字典、哈希、ActiveEvidenceView、Readiness
src/oceanpilot/domain/state_machine.py   # 显式迁移白名单
src/oceanpilot/domain/diagnosis.py       # 可信度和诊断草稿纯函数
src/oceanpilot/application/commands.py   # 框架无关应用命令
src/oceanpilot/application/errors.py     # 稳定应用错误
src/oceanpilot/application/ports.py      # 仅 Store 协议；诊断协议归领域层
src/oceanpilot/application/case_service.py # 用例、重试、两阶段诊断
src/oceanpilot/adapters/persistence/schema.py # SQLite DDL
src/oceanpilot/adapters/persistence/sqlite.py # 连接、事务、原子 Store
src/oceanpilot/adapters/diagnosis/rules.py    # 四个规则 ID 的表驱动引擎
src/oceanpilot/adapters/evidence/synthetic.py # 内部合成场景适配器
src/oceanpilot/api/schemas.py          # 请求/响应 DTO
src/oceanpilot/api/errors.py           # RFC 9457 和全局处理器
src/oceanpilot/api/dependencies.py     # RequestContext、CaseService 注入
src/oceanpilot/api/health.py           # GET /health
src/oceanpilot/api/cases.py            # 四个 /api/v1/cases 路由
tests/conftest.py                       # tmp_path DB、TestClient、固定时钟/UUID
tests/domain/**                         # 纯领域和应用编排测试
tests/repository/**                     # 真实文件 SQLite、回滚、CAS、并发
tests/api/**                            # lifespan、契约、OpenAPI、三个场景
tests/security/**                       # 五输出面敏感哨兵扫描
examples/demo.ps1                       # 本地 API 合成演示
README.md                               # 诚实状态、启动、边界、验证
docs/architecture.md                    # 当前/目标两张架构图
docs/demo.md                            # 演示步骤、证明项/未证明项
docs/submission/registration-copy.md   # Part 1/Part 2 可粘贴文本与字数
docs/reviews/gate-{1,2,3,4}.md          # 每道门的证据报告
```

## Frozen Cross-Task Interfaces

后续任务必须复用这些名字，不得在 API、领域和存储层各造一套近似类型。

```python
# domain/models.py
UUID4Str = Annotated[str, Field(strict=True), AfterValidator(normalize_uuid4)]
AwareDateTime = Annotated[
    datetime,
    Field(strict=True),
    AfterValidator(require_timezone),
]

def require_true(value: bool) -> bool:
    if value is not True:
        raise ValueError("synthetic must be true")
    return value

SyntheticTrue = Annotated[StrictBool, AfterValidator(require_true)]

class EvidenceCreate(FrozenDomainModel):
    evidence_id: UUID4Str
    evidence_code: EvidenceCode
    availability: EvidenceAvailability
    typed_value: StrictStr | StrictBool | AwareDateTime | None = None
    observed_at: AwareDateTime | None = None
    source_ref: Annotated[str, Field(strict=True, min_length=1, max_length=128)]

class EvidenceOrigin(FrozenDomainModel):
    source_type: SourceType
    source_reliability: SourceReliability
    synthetic: SyntheticTrue = True

class ConfidenceResult(FrozenDomainModel):
    raw_score: Decimal
    display_score: Decimal
    review_reasons: frozenset[ReviewReason]
```

```python
# domain/evidence_policy.py
def create_evidence_item(
    request: EvidenceCreate,
    *,
    case_id: UUID4Str,
    origin: EvidenceOrigin,
    collected_at: AwareDateTime,
) -> EvidenceItem: ...

def canonical_evidence_hash(
    request: EvidenceCreate,
    origin: EvidenceOrigin,
) -> str: ...

def build_active_evidence_view(
    evidence: Sequence[EvidenceItem],
) -> ActiveEvidenceView: ...

def assess_readiness(
    view: ActiveEvidenceView,
) -> ReadinessAssessment: ...
```

```python
# domain/state_machine.py
def assert_command_allowed(status: CaseStatus, command: CaseCommand) -> None: ...
def status_after_creation(readiness: ReadinessAssessment) -> CaseStatus: ...
def status_after_evidence(
    current: CaseStatus,
    readiness: ReadinessAssessment,
) -> CaseStatus: ...
def status_after_diagnosis(draft: DiagnosisDraft) -> CaseStatus: ...
```

```python
# domain/diagnosis.py; adapters/diagnosis/rules.py implements this protocol
def calculate_confidence(
    decisive_evidence: Sequence[EvidenceItem],
    *,
    required_coverage: Decimal,
    consistency: Decimal,
) -> ConfidenceResult: ...

class DiagnosisEngine(Protocol):
    def evaluate(
        self,
        case: MerchantSuccessCase,
        view: ActiveEvidenceView,
        *,
        policy_version: str,
    ) -> DiagnosisDraft: ...
```

```python
# application/ports.py
class CaseStoreSession(Protocol):
    def healthcheck(self) -> None: ...
    def get_case_view(self, case_id: UUID4Str) -> CaseView | None: ...
    def load_case_snapshot(self, case_id: UUID4Str) -> CaseInputSnapshot | None: ...
    def create_case_atomic(
        self,
        *,
        case: MerchantSuccessCase,
        audit: AuditEvent,
    ) -> CaseView: ...
    def append_evidence_atomic(
        self,
        *,
        expected_case_revision: int,
        expected_evidence_revision: int,
        evidence: EvidenceItem,
        readiness: ReadinessAssessment,
        target_status: CaseStatus,
        audit_events: Sequence[AuditEvent],
    ) -> AppendEvidenceResult: ...
    def find_diagnosis(
        self,
        *,
        case_id: UUID4Str,
        evidence_revision: int,
        policy_version: str,
    ) -> DiagnosisSnapshot | None: ...
    def commit_diagnosis_atomic(
        self,
        *,
        expected_case_revision: int,
        expected_evidence_revision: int,
        snapshot: DiagnosisSnapshot,
        target_status: CaseStatus,
        audit_events: Sequence[AuditEvent],
    ) -> CommitDiagnosisResult: ...

class CaseStoreFactory(Protocol):
    def __call__(self) -> AbstractContextManager[CaseStoreSession]: ...
```

```python
# application/case_service.py
class CaseService:
    def __init__(
        self,
        store_factory: CaseStoreFactory,
        diagnosis_engine: DiagnosisEngine,
        *,
        clock: Callable[[], AwareDateTime],
        uuid_factory: Callable[[], UUID4Str],
        policy_version: str = "POLICY_V1",
        engine_version: str = "RULES_V1",
    ) -> None: ...

    def create_case(self, command: CreateCaseCommand) -> CommandResult[CaseView]: ...
    def get_case(self, case_id: UUID4Str) -> CaseView: ...
    def add_evidence(self, command: AddEvidenceCommand) -> CommandResult[CaseView]: ...
    def diagnose(self, command: DiagnoseCaseCommand) -> CommandResult[DiagnosisView]: ...
```

`CaseStoreSession` 只允许上述原子方法；禁止新增 `save_case()`、`update_evidence()`、`delete_evidence()` 或返回裸 sqlite3 连接的端口。

---

### Task 0: Freeze the Time-Critical Registration Copy and Open a Clean Write Window

**Owner:** 总控轨

**Files:**
- Create: `docs/submission/registration-copy.md`
- Do not modify: `src/**`, `tests/**`, `pyproject.toml`

**Interfaces:**
- Produces: 已批准、可立即粘贴的 Part 1/Part 2 报名文字，以及技术轨开始 Task 1 所需的干净工作树。
- Consumes: 已批准规格 `78e7064` 的 §13.1/§13.2；不依赖任何代码、GitHub 远程或后续 Gate。

- [ ] **Step 1: Verify the approved plan is committed before implementation begins**

Run:

```powershell
git status --short
git ls-files --error-unmatch docs/superpowers/plans/2026-07-18-oceanpilot-evidenceos-mvp-implementation.md
git log -1 --format="%H %s"
```

Expected: the plan is tracked, the tree is clean, and the latest commit is the reviewed plan commit. If not, stop; do not hand the write lock to the Python technical track.

- [ ] **Step 2: Save the two approved paragraphs verbatim**

Create `docs/submission/registration-copy.md` with `apply_patch` and this exact content:

```markdown
# OceanPilot 报名表可粘贴文本

> 来源：已批准规格 `docs/superpowers/specs/2026-07-18-oceanpilot-evidenceos-design.md` §13。当前 GitHub 链接尚未经过匿名访问验证，不填写仓库链接，不等待代码完成即可先提交下列文字。

## Part 1｜命题前置分析与洞察（50–300 字）

Oceanpayment 官方资料显示，其平台支持 500+ 支付方式并覆盖 200 多个国家和地区；支付方式适用性又与国家、行业、虚拟商品、订阅场景及设备有关。同类平台的动态支付方式也会按位置、币种、金额和支付流程判断可用性。ODPM 已具备交易、挡掉交易、退款、拒付、风控、报表、日志和可视化能力，因此机会并非“再造数据看板”，而是让分散在模块与角色间的证据进入同一协作链。我们判断，应建立统一的“商户成功案件”和证据契约：由 AI 先识别关键缺口并向正确角色补问，再受控查询数据，以可追溯证据驱动诊断、路由和知识复用。

- Character count: 262

## Part 2｜整体解决方案设计（300–600 字）

OceanPilot 是一套证据驱动的跨境商户成功运营助手，总体覆盖接入前支付方式推荐，以及上线后的协作补问、异常诊断、工单与 SLA、知识沉淀和案件质量看板。商户或 OP 人员从飞书 IM/机器人描述问题，飞书 Agent 负责语义理解、字段抽取和角色化追问；受理、证据与协作 Agent 围绕同一案件进行结构化 A2A 交接，只读 MCP 仅负责受控查询订单、回调、风控、退款、报表与知识工具；多维表格承载版本化案件、证据、责任人与审计状态，Workflow 执行确定性路由、通知、审批和超时升级。核心创新是“商户成功案件 + 案件证据契约”：资料不足时 AI 不直接下结论，而是定位关键证据缺口；满足最低条件后，才输出带来源引用、可信度、责任域、下一动作和人审原因的建议。系统将诊断证据引用率 100%、高风险操作人审率 100% 设为硬约束；入围后用企业允许的数据验证补问轮次、到证时间、首次路由与改派、交接次数、人工升级、重复问题和知识复用。两天原型计划以 FastAPI、Pydantic、SQLite 和合成适配器打通支付异常切片；取得企业材料后，可复用案件与证据内核，在替换适配器、校准规则并补充场景策略的基础上，分阶段扩展至支付推荐、退款、拒付和对账。AI 处理模糊性，Workflow 守住确定性，高风险动作始终由人工确认。

- Character count: 572

## 当前事实边界

- 上述文字是总体方案；当前尚无可验证代码原型，本轮原型计划仅实现支付异常切片与合成数据验证。
- 飞书 Agent、A2A、MCP、真实 Oceanpayment 接口、真实派单、SLA 计时/超时升级和支付动作均未在当前原型实现。
- GitHub URL 只有在 Gate 4 匿名访问验证通过后才能补入报名表。
```

- [ ] **Step 3: Recompute counts from the saved artifact**

Run:

```powershell
$registration = Get-Content -LiteralPath docs/submission/registration-copy.md -Raw -Encoding utf8
$part1 = [regex]::Match($registration, '(?s)## Part 1[^\r\n]*\r?\n\r?\n(.+?)\r?\n\r?\n- Character count:').Groups[1].Value
$part2 = [regex]::Match($registration, '(?s)## Part 2[^\r\n]*\r?\n\r?\n(.+?)\r?\n\r?\n- Character count:').Groups[1].Value
if ($part1.Length -ne 262) { throw "Part 1 count mismatch: $($part1.Length)" }
if ($part2.Length -ne 572) { throw "Part 2 count mismatch: $($part2.Length)" }
"Part 1=$($part1.Length); Part 2=$($part2.Length)"
```

Expected: `Part 1=262; Part 2=572`. Also compare both paragraphs byte-for-byte with approved spec §13 before committing.

- [ ] **Step 4: Commit only the registration copy**

```powershell
git add -- docs/submission/registration-copy.md
git diff --cached --check
git diff --cached -- docs/submission/registration-copy.md
git commit -m "docs: freeze OceanPilot registration copy"
```

Expected: only the registration artifact is committed; it makes no claim that future architecture is already implemented.

- [ ] **Step 5: Release the write lock to the technical track**

Run `git status --short`; expected output is empty. Send the registration commit SHA, counts `262/572`, and the explicit instruction “Task 1 may start; GitHub URL remains blank pending Gate 4” to the Python technical track. The form submission itself remains a user action unless the user separately authorizes browser submission.

---

### Task 1: Scaffold the Reproducible Python 3.12 Project

**Owner:** Python 技术轨

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/oceanpilot/__init__.py`
- Create: package `__init__.py` files under `domain/`, `application/`, `api/`, `adapters/`, and `adapters/{diagnosis,evidence,persistence}/`
- Create: `tests/domain/test_project_contract.py`

**Interfaces:**
- Produces: editable `oceanpilot` package at version `0.1.0`; exact dependency and test commands used by every later task.
- Consumes: none.

- [ ] **Step 1: Create build metadata and the first failing package contract test**

Write `tests/domain/test_project_contract.py` first:

```python
import sys


def test_runtime_is_python_312() -> None:
    assert sys.version_info[:2] == (3, 12)


def test_package_exposes_version() -> None:
    from oceanpilot import __version__

    assert __version__ == "0.1.0"
```

Write `pyproject.toml` with this exact project contract:

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "oceanpilot-evidenceos"
version = "0.1.0"
description = "Synthetic local prototype for evidence-driven payment incident collaboration"
requires-python = ">=3.12,<3.13"
dependencies = [
  "fastapi==0.139.2",
  "pydantic==2.13.4",
  "uvicorn==0.51.0",
]

[project.optional-dependencies]
dev = [
  "httpx==0.28.1",
  "pytest==9.1.1",
  "ruff==0.15.22",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-config --strict-markers"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
```

- [ ] **Step 2: Create a clean environment and verify the test fails before the package exists**

Run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests/domain/test_project_contract.py -q
```

Expected: `test_package_exposes_version` fails with `ModuleNotFoundError` or missing `__version__`; Python version assertion passes.

- [ ] **Step 3: Add the minimum package and ignore rules**

Write `src/oceanpilot/__init__.py`:

```python
"""OceanPilot EvidenceOS synthetic prototype."""

__version__ = "0.1.0"
```

Every subpackage `__init__.py` contains only a one-line module docstring. `.gitignore` must contain:

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
*.db
*.db-*
*.sqlite
*.sqlite3
*.log
.env
.env.*
!.env.example
work/
dist/
build/
*.egg-info/
```

- [ ] **Step 4: Verify installation, tests, lint, and compilation**

Run:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest tests/domain/test_project_contract.py -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
```

Expected: Python `3.12.x`; `2 passed`; Ruff and compileall exit `0`.

- [ ] **Step 5: Commit only scaffold files**

```powershell
git add -- pyproject.toml .gitignore src tests/domain/test_project_contract.py
git diff --cached --check
git commit -m "chore: scaffold Python project"
```

Expected: commit succeeds and `git status --short` is empty.

---

### Task 2: Add Safe Domain Types, Enums, and Immutable Models

**Owner:** Python 技术轨

**Files:**
- Create: `src/oceanpilot/domain/enums.py`
- Create: `src/oceanpilot/domain/errors.py`
- Create: `src/oceanpilot/domain/security.py`
- Create: `src/oceanpilot/domain/models.py`
- Create: `tests/conftest.py`
- Create: `tests/domain/test_models.py`
- Create: `tests/domain/test_sensitive_input.py`

**Interfaces:**
- Produces: `UUID4Str`, `AwareDateTime`, `SyntheticTrue`, all closed enums, frozen `EvidenceCreate`/`EvidenceItem`, case/diagnosis/readiness/view/audit models, and `assert_no_sensitive_data()`.
- Consumes: Pydantic 2.13.4 only; no FastAPI or sqlite3 imports.

- [ ] **Step 1: Write failing tests for UUID, time, strict fields, freezing, and sensitive values**

The tests must include these exact assertions:

```python
from datetime import datetime
from decimal import Decimal
from uuid import uuid1, uuid4

import pytest
from pydantic import ValidationError

from oceanpilot.domain.enums import (
    EvidenceAvailability,
    EvidenceCode,
    SourceReliability,
    SourceType,
)
from oceanpilot.domain.models import (
    ConfidenceResult,
    EvidenceCreate,
    EvidenceItem,
    EvidenceOrigin,
    normalize_uuid4,
)
from oceanpilot.domain.security import SensitiveDataRejected, assert_no_sensitive_data


def test_uuid4_is_normalized_and_uuid1_is_rejected() -> None:
    value = str(uuid4()).upper()
    assert normalize_uuid4(value) == value.lower()
    with pytest.raises(ValueError):
        normalize_uuid4(str(uuid1()))


def test_evidence_create_rejects_unknown_field_and_naive_time() -> None:
    with pytest.raises(ValidationError):
        EvidenceCreate.model_validate({
            "evidence_id": str(uuid4()),
            "evidence_code": EvidenceCode.TRANSACTION_OCCURRED_AT,
            "availability": EvidenceAvailability.AVAILABLE,
            "typed_value": "2026-07-18T12:00:00",
            "observed_at": datetime(2026, 7, 18, 12, 0),
            "source_ref": "demo",
            "unexpected": True,
        })


def test_naive_observed_time_is_rejected_without_other_errors() -> None:
    with pytest.raises(ValidationError):
        EvidenceCreate.model_validate({
            "evidence_id": str(uuid4()),
            "evidence_code": EvidenceCode.CONTEXT_ENVIRONMENT,
            "availability": EvidenceAvailability.AVAILABLE,
            "typed_value": "PROD",
            "observed_at": "2026-07-18T12:00:00",
            "source_ref": "demo",
        })


def test_uuid_field_does_not_coerce_boolean() -> None:
    with pytest.raises(ValidationError):
        EvidenceCreate.model_validate({
            "evidence_id": True,
            "evidence_code": EvidenceCode.CONTEXT_ENVIRONMENT,
            "availability": EvidenceAvailability.AVAILABLE,
            "typed_value": "PROD",
            "source_ref": "demo",
        })


def test_aware_domain_time_is_accepted() -> None:
    model = EvidenceCreate.model_validate({
        "evidence_id": str(uuid4()),
        "evidence_code": EvidenceCode.CONTEXT_ENVIRONMENT,
        "availability": EvidenceAvailability.AVAILABLE,
        "typed_value": "PROD",
        "observed_at": datetime.fromisoformat("2026-07-18T12:00:00+08:00"),
        "source_ref": "demo",
    })
    assert model.observed_at is not None
    assert model.observed_at.utcoffset() is not None


@pytest.mark.parametrize("value", [1, False, "true"])
def test_synthetic_true_rejects_bool_coercion(value: object) -> None:
    with pytest.raises(ValidationError):
        EvidenceOrigin(
            source_type=SourceType.SYNTHETIC_ADAPTER,
            source_reliability=SourceReliability.SYNTHETIC_TEST,
            synthetic=value,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_confidence_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValidationError):
        ConfidenceResult(
            raw_score=value,
            display_score=Decimal("0.50"),
            review_reasons=frozenset(),
        )


def test_evidence_item_is_frozen(valid_evidence_item: EvidenceItem) -> None:
    with pytest.raises(ValidationError):
        valid_evidence_item.typed_value = "changed"


@pytest.mark.parametrize("sentinel", [
    "Bearer secret-demo-token",
    "cvv=123",
    "password=hunter-demo",
    "4242424242424242",
])
def test_sensitive_sentinels_are_rejected(sentinel: str) -> None:
    with pytest.raises(SensitiveDataRejected):
        assert_no_sensitive_data({"value": sentinel})
```

Create this base fixture in `tests/conftest.py`; later tasks extend the same file instead of defining incompatible evidence helpers:

```python
from datetime import datetime

import pytest

from oceanpilot.domain.enums import (
    EvidenceAvailability,
    EvidenceCode,
    EvidenceValueType,
    SourceReliability,
    SourceType,
)
from oceanpilot.domain.models import EvidenceItem


@pytest.fixture
def valid_evidence_item() -> EvidenceItem:
    observed = datetime.fromisoformat("2026-07-18T12:00:00+08:00")
    return EvidenceItem(
        case_id="00000000-0000-4000-8000-000000000010",
        evidence_id="00000000-0000-4000-8000-000000000011",
        schema_version="1",
        evidence_code=EvidenceCode.CONTEXT_ENVIRONMENT,
        availability=EvidenceAvailability.AVAILABLE,
        value_type=EvidenceValueType.STRING,
        typed_value="PROD",
        source_type=SourceType.SYNTHETIC_ADAPTER,
        source_ref="synthetic:fixture",
        source_reliability=SourceReliability.SYNTHETIC_TEST,
        observed_at=observed,
        collected_at=observed,
        synthetic=True,
        content_hash="0" * 64,
    )
```

- [ ] **Step 2: Run the domain tests and confirm import failures**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/domain/test_models.py tests/domain/test_sensitive_input.py -q
```

Expected: collection fails because the domain modules do not exist.

- [ ] **Step 3: Implement the exact base validation and enum contracts**

`normalize_uuid4()` and time validation use pure after validators:

```python
def normalize_uuid4(value: str) -> str:
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError("must be a UUID") from exc
    if parsed.version != 4:
        raise ValueError("must be UUIDv4")
    return str(parsed)


def require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone is required")
    return value
```

`DomainModel` and `FrozenDomainModel` use:

```python
class DomainModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        hide_input_in_errors=True,
    )


class FrozenDomainModel(DomainModel):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        hide_input_in_errors=True,
        frozen=True,
    )
```

`enums.py` must define these closed `StrEnum` classes and values exactly:

```text
CaseType: PAYMENT_INCIDENT, ONBOARDING_RECOMMENDATION
CaseStatus: NEW, NEED_INFO, EVIDENCE_READY, DIAGNOSED, HUMAN_REVIEW
CaseCommand: CREATE_CASE, ADD_EVIDENCE, DIAGNOSE
EvidenceAvailability: AVAILABLE, CONFIRMED_UNAVAILABLE
EvidenceValueType: STRING, BOOLEAN, DATETIME, COUNTRY, CURRENCY
SourceType: MERCHANT, INTERNAL_OPERATOR, SYSTEM_OF_RECORD, SYNTHETIC_ADAPTER
SourceReliability: SYSTEM_OF_RECORD, VERIFIED_DOCUMENT, SYNTHETIC_TEST,
                   OPERATOR_CONFIRMED, USER_REPORTED
StopReason: READY, NEED_MORE_EVIDENCE, CONFIRMED_UNKNOWN, UNSUPPORTED,
            SECURITY_BLOCKED
TargetRole: MERCHANT_BUSINESS, MERCHANT_TECH, INTERNAL_OPS, INTERNAL_RISK,
            INTERNAL_FINANCE
ReviewReason: LOW_CONFIDENCE, CONFLICTING_EVIDENCE, RISK_DECISION,
              SECURITY_SIGNAL, FINANCIAL_ACTION, POLICY_GAP,
              INSUFFICIENT_SOURCE_QUALITY
ResponsibleTeam: BUSINESS, TECHNICAL_SUPPORT, RISK, FINANCE,
                 CUSTOMER_SUPPORT, PSP_SUPPORT
Priority: LOW, MEDIUM, HIGH
DiagnosisStatus: CURRENT, SUPERSEDED
WriteOutcome: CREATED, REPLAY
AuditEventType: CASE_CREATED, EVIDENCE_ADDED, DIAGNOSIS_SUPERSEDED,
                DIAGNOSIS_CREATED, ROUTING_PROPOSED, STATE_TRANSITIONED
AuditActorType: MERCHANT, INTERNAL_SYSTEM, SYNTHETIC_ADAPTER
```

`EvidenceCode` must contain the following 16 dotted values exactly:

```text
context.environment
transaction.reference
transaction.occurred_at
transaction.country
transaction.currency
payment.method
integration.type
integration.platform
integration.plugin_version
symptom.status
symptom.error_code
authentication.status
authentication.result_code
callback.delivery_status
risk.decision_code
configuration.check_result
```

`models.py` must define every model named in the Frozen Cross-Task Interfaces plus `MerchantSuccessCase`, `EvidenceItem`, `ActiveEvidenceSlot`, `ActiveEvidenceView`, `ReadinessAssessment`, `HypothesisDraft`, `DiagnosisDraft`, `Hypothesis`, `DiagnosisSnapshot`, `RoutingDecision`, `TicketDraft`, `AuditEvent`, `CaseView`, `CaseInputSnapshot`, `DiagnosisView`, `AppendEvidenceResult`, `CommitDiagnosisResult`, and generic `CommandResult[T]`.

Core model field sets are frozen as follows:

```text
MerchantSuccessCase: case_id,case_type,status,schema_version,case_revision,
  evidence_revision,synthetic,summary,merchant_ref,created_at,updated_at,
  current_diagnosis_id,readiness
EvidenceItem: case_id,evidence_id,schema_version,evidence_code,availability,
  value_type,typed_value,source_type,source_ref,source_reliability,observed_at,
  collected_at,synthetic,content_hash
ActiveEvidenceSlot: evidence_code,selected_evidence,known_unknown,conflicting
ActiveEvidenceView: slots,review_reasons
ReadinessAssessment: ready,missing_fields,known_unknown_fields,next_question,
  question_reason,target_role,completion_ratio,stop_reason
HypothesisDraft: cause_code,explanation,evidence_refs,confidence_score,
  confidence_method,next_verification_action,rule_id
DiagnosisDraft: hypotheses,routing_decision,ticket_draft,requires_human,
  review_reasons
Hypothesis: hypothesis_id,cause_code,explanation,evidence_refs,confidence_score,
  confidence_method,next_verification_action,rule_id
DiagnosisSnapshot: diagnosis_id,case_id,evidence_revision,policy_version,
  engine_version,status,hypotheses,routing_decision,ticket_draft,requires_human,
  review_reasons,synthetic,created_at
RoutingDecision: responsible_team,priority,reason,evidence_refs,requires_human,
  review_reasons
TicketDraft: title,summary,evidence_summary,missing_material,hypotheses,
  next_action,responsible_team,synthetic
AuditEvent: event_id,event_type,event_version,case_id,request_id,trace_id,
  actor_type,action,from_status,to_status,case_revision,evidence_revision,
  occurred_at,result,reason_code,sanitized_metadata,synthetic
CaseInputSnapshot: case,evidence,current_diagnosis
CaseView: case,evidence,current_diagnosis
DiagnosisView: case_id,case_status,case_revision,evidence_revision,diagnosis
CommandResult[T]: outcome,value
AppendEvidenceResult: outcome,case_view
CommitDiagnosisResult: outcome,case_view,diagnosis
```

All IDs use `UUID4Str`; server timestamps use `AwareDateTime`; every always-synthetic field uses `SyntheticTrue` rather than `Literal[True]` so JSON integer `1`, string `"true"`, and `false` cannot coerce; revision fields are strict integers `>=0`; confidence fields are finite `Decimal` in `0..1`. `EvidenceCreate`, `EvidenceOrigin`, `EvidenceItem`, `ActiveEvidenceSlot`, `ActiveEvidenceView`, `HypothesisDraft`, `DiagnosisDraft`, `Hypothesis`, `DiagnosisSnapshot`, `RoutingDecision`, `TicketDraft`, and `AuditEvent` inherit `FrozenDomainModel`. Tests lock the four cross-task Draft/View field sets above with `model_fields` equality so Task 3, Task 4, and Task 11 cannot silently diverge.

`security.py` recursively visits mappings, sequences, model dumps, and scalar strings. It rejects Bearer/Authorization material, key/password/token/CVV assignments, and every 13–19 digit candidate passing Luhn. It raises only `SensitiveDataRejected("sensitive data is not accepted")`; the exception must not contain the rejected value.

- [ ] **Step 4: Run the focused tests and inspect the model schema**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/domain/test_models.py tests/domain/test_sensitive_input.py -q
.\.venv\Scripts\python.exe -c "from oceanpilot.domain.models import EvidenceItem; print(EvidenceItem.model_json_schema()['additionalProperties'])"
.\.venv\Scripts\python.exe -m ruff check src/oceanpilot/domain tests/domain
```

Expected: all tests pass; schema command prints `False`; Ruff exits `0`.

- [ ] **Step 5: Commit domain foundations**

```powershell
git add -- src/oceanpilot/domain tests/conftest.py tests/domain/test_models.py tests/domain/test_sensitive_input.py
git diff --cached --check
git commit -m "feat: add safe evidence domain models"
```

---

### Task 3: Implement Canonical Evidence, ActiveEvidenceView, and Readiness

**Owner:** Python 技术轨

**Files:**
- Create: `src/oceanpilot/domain/evidence_policy.py`
- Create: `tests/domain/test_evidence_policy.py`
- Create: `tests/domain/test_readiness.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces: `canonical_evidence_hash`, `create_evidence_item`, `build_active_evidence_view`, `assess_readiness`.
- Consumes: Task 2 models and enums.

- [ ] **Step 1: Write failing parameterized tests for field validation and deterministic evidence folding**

Extend `tests/conftest.py` with one stable factory:

```python
from datetime import datetime

from oceanpilot.domain.enums import (
    EvidenceAvailability,
    EvidenceCode,
    SourceReliability,
    SourceType,
)
from oceanpilot.domain.evidence_policy import create_evidence_item
from oceanpilot.domain.models import EvidenceCreate, EvidenceItem, EvidenceOrigin


@pytest.fixture
def evidence_factory():
    def make(
        *,
        code: str = "context.environment",
        value: str | bool | datetime = "PROD",
        evidence_id: str = "00000000-0000-4000-8000-000000000011",
        reliability: SourceReliability = SourceReliability.SYNTHETIC_TEST,
        availability: EvidenceAvailability = EvidenceAvailability.AVAILABLE,
    ) -> EvidenceItem:
        request = EvidenceCreate(
            evidence_id=evidence_id,
            evidence_code=EvidenceCode(code),
            availability=availability,
            typed_value=(
                value if availability is EvidenceAvailability.AVAILABLE else None
            ),
            observed_at=datetime.fromisoformat("2026-07-18T12:00:00+08:00"),
            source_ref="synthetic:fixture",
        )
        origin = EvidenceOrigin(
            source_type=SourceType.SYNTHETIC_ADAPTER,
            source_reliability=reliability,
            synthetic=True,
        )
        return create_evidence_item(
            request,
            case_id="00000000-0000-4000-8000-000000000010",
            origin=origin,
            collected_at=datetime.fromisoformat("2026-07-18T12:00:01+08:00"),
        )

    return make
```

Tests must prove all five §5.3 fold rules. Include this conflict test and a same-value tie-break test:

```python
def test_different_available_values_become_conflict(evidence_factory) -> None:
    first = evidence_factory(
        code="context.environment",
        value="PROD",
        evidence_id="00000000-0000-4000-8000-000000000001",
    )
    second = evidence_factory(
        code="context.environment",
        value="SANDBOX",
        evidence_id="00000000-0000-4000-8000-000000000002",
    )

    view = build_active_evidence_view([first, second])

    assert view.slots[EvidenceCode.CONTEXT_ENVIRONMENT].conflicting is True
    assert view.review_reasons == frozenset({ReviewReason.CONFLICTING_EVIDENCE})


def test_same_value_uses_quality_then_lowest_id(evidence_factory) -> None:
    low = evidence_factory(value="PROD", reliability=SourceReliability.USER_REPORTED)
    high_b = evidence_factory(
        value="PROD",
        reliability=SourceReliability.SYNTHETIC_TEST,
        evidence_id="00000000-0000-4000-8000-000000000002",
    )
    high_a = evidence_factory(
        value="PROD",
        reliability=SourceReliability.SYNTHETIC_TEST,
        evidence_id="00000000-0000-4000-8000-000000000001",
    )

    selected = build_active_evidence_view([low, high_b, high_a]).slots[
        EvidenceCode.CONTEXT_ENVIRONMENT
    ]
    assert selected.selected_evidence is not None
    assert selected.selected_evidence.evidence_id == high_a.evidence_id
```

Readiness tests must cover: the exact 1→7 priority order, core slots 1–4 requiring AVAILABLE observations, `integration.type=PLUGIN` activating two conditional slots, confirmed-unavailable non-core slots counting as answered, stable `completion_ratio`, `known_unknown_fields`, and same input producing the same result. A conflicting slot counts as answered and AVAILABLE for readiness, but never as usable rule evidence; when every core slot has at least one AVAILABLE observation and any slot conflicts, readiness permits `Diagnose` so the engine can create a no-hypothesis `CONFLICTING_EVIDENCE` human-review snapshot. A core slot with only `CONFIRMED_UNAVAILABLE` remains not ready.

- [ ] **Step 2: Run tests and confirm the policy functions are missing**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/domain/test_evidence_policy.py tests/domain/test_readiness.py -q
```

Expected: collection or calls fail because policy functions are not implemented.

- [ ] **Step 3: Implement the field catalog, canonical hash, fold, and priority table**

#### Task 3 contract locks

These locks remove implementation choices from the technical track. They refine the approved specification without expanding the MVP. Task 2's `FrozenDomainModel` contract remains shallow assignment freezing; Task 3 must not reopen Task 2 models or claim deep immutability for their nested dictionaries.

**Field catalog.** `FIELD_CATALOG` is an externally immutable mapping with exactly the 16 `EvidenceCode` members in enum declaration order. Validation is case-sensitive, regex validators require a full-string match, and no validator performs trimming or case-folding. The rows are:

| Evidence code | Value type | Exact MVP validator |
|---|---|---|
| `context.environment` | `STRING` | one of `PROD`, `SANDBOX` |
| `transaction.reference` | `STRING` | `[A-Za-z0-9_.-]{1,64}` |
| `transaction.occurred_at` | `DATETIME` | timezone-aware `datetime` |
| `transaction.country` | `COUNTRY` | member of frozen `ISO_COUNTRY_ALPHA2` below |
| `transaction.currency` | `CURRENCY` | member of frozen `ISO_CURRENCY_ALPHA3` below |
| `payment.method` | `STRING` | one of `CARD`, `APPLE_PAY`, `GOOGLE_PAY`, `KLARNA`, `LOCAL_PAYMENT`, `OTHER` |
| `integration.type` | `STRING` | one of `API`, `PLUGIN` |
| `integration.platform` | `STRING` | one of `SHOPIFY`, `WOOCOMMERCE`, `MAGENTO`, `CUSTOM` |
| `integration.plugin_version` | `STRING` | `[A-Za-z0-9][A-Za-z0-9._+-]{0,31}` |
| `symptom.status` | `STRING` | one of `PENDING`, `FAILED`, `SUCCEEDED`, `DECLINED`, `UNKNOWN` |
| `symptom.error_code` | `STRING` | `[A-Za-z0-9_.-]{1,64}` |
| `authentication.status` | `STRING` | one of `REQUIRED`, `CHALLENGE_PENDING`, `AUTHENTICATED`, `FAILED`, `UNKNOWN` |
| `authentication.result_code` | `STRING` | `[A-Za-z0-9_.-]{1,64}` |
| `callback.delivery_status` | `STRING` | one of `NOT_RECEIVED`, `DELIVERED`, `FAILED`, `UNKNOWN` |
| `risk.decision_code` | `STRING` | `[A-Za-z0-9_.-]{1,64}` |
| `configuration.check_result` | `STRING` | one of `MERCHANT_SIDE_MISMATCH`, `PSP_PROFILE_MISMATCH`, `NO_MISMATCH`, `UNKNOWN` |

There is no `BOOLEAN` catalog row in MVP. The ISO membership data is frozen in `evidence_policy.py`; validation performs no runtime network access and adds no package dependency. The 2026-07-18 snapshot is cross-checked against the [ISO 3166 maintenance page](https://www.iso.org/iso-3166-country-codes.html), the [SIX ISO 4217 Maintenance Agency List One](https://www.six-group.com/en/products-services/financial-information/market-reference-data/data-standards.html), and `pycountry==26.2.16`'s current Debian `pkg-isocodes` copy. Implement these exact sets:

```python
ISO_COUNTRY_ALPHA2 = frozenset(
    "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI "
    "BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN "
    "CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK "
    "FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM "
    "HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN "
    "KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK "
    "ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP "
    "NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW "
    "SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF "
    "TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI "
    "VN VU WF WS YE YT ZA ZM ZW".split()
)
ISO_CURRENCY_ALPHA3 = frozenset(
    "AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BOV "
    "BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP "
    "CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF "
    "GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR "
    "KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT "
    "MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN "
    "PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE "
    "SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX "
    "USD USN UYI UYU UYW UZS VED VES VND VUV WST XAD XAF XAG XAU XBA XBB XBC "
    "XBD XCD XCG XDR XOF XPD XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWG".split()
)
```

Tests pin `len(ISO_COUNTRY_ALPHA2) == 249` and SHA-256 `e1c950d24ceb933ac49eaa44de8d1a7ffb6bf40bfe519a5a99d791cb50332197` for the UTF-8, space-joined, lexically sorted country codes. They pin `len(ISO_CURRENCY_ALPHA3) == 178` and SHA-256 `62185bf8d74197e249d7a609a697f81820def9ca894cc3e9121c82497358f453` for currencies. Representative membership tests accept `CN`, `US`, `EUR`, `USD`, `XAD`, `XCG`, and `ZWG`; reject reserved/nonmembers `ZZ`, `XK`, `ZZZ`, and the withdrawn `BGN`/`ZWL`. This is a prototype validation snapshot, not a promise of automatic ISO updates; a future data refresh must intentionally update both digests and tests.

`AVAILABLE` requires a non-null value of the catalog type; `CONFIRMED_UNAVAILABLE` requires `typed_value=None`. `create_evidence_item()` sets `schema_version=EVIDENCE_SCHEMA_VERSION`, where `EVIDENCE_SCHEMA_VERSION = "1"`, and derives `value_type` only from the catalog.

**Canonical hash.** The hash payload remains the exact nine-key dictionary shown below: no schema version, `collected_at`, or computed hash is added. Strings are Unicode NFC but are not trimmed or case-folded. Both `observed_at` and a DATETIME `typed_value` are normalized to UTC with literal `Z` and exactly six fractional digits; equivalent timezone offsets and canonically equivalent Unicode therefore hash identically. `None` and booleans remain JSON `null` and booleans. Tests must pin this golden vector:

```text
request = evidence_id 00000000-0000-4000-8000-000000000011,
          context.environment, AVAILABLE, typed_value PROD,
          observed_at 2026-07-18T12:00:00+08:00,
          source_ref synthetic:fixture
origin  = SYNTHETIC_ADAPTER / SYNTHETIC_TEST / synthetic true
canonical observed_at = 2026-07-18T04:00:00.000000Z
sha256 = a178af8643b1b7b495070d92ccdd0edad9d9bbdd51c5c54cbbb9425aaeb2558d
```

In addition to the golden digest, tests lock offset equivalence, composed/decomposed Unicode equivalence, and the exclusion of `collected_at` from `content_hash`.

**Active evidence fold.** `build_active_evidence_view()` always returns all 16 slots in `EvidenceCode` declaration order and is invariant to input permutation. Each slot has exactly these outcomes:

| Inputs for one code | `selected_evidence` | `known_unknown` | `conflicting` |
|---|---|---:|---:|
| none | `None` | `False` | `False` |
| only `CONFIRMED_UNAVAILABLE` | `None` | `True` | `False` |
| one normalized AVAILABLE value, with or without unavailable history | deterministic selected item | `False` | `False` |
| two or more unequal normalized AVAILABLE values | `None` | `False` | `True` |

For equal normalized AVAILABLE values, choose reliability in this exact descending order: `SYSTEM_OF_RECORD > VERIFIED_DOCUMENT > SYNTHETIC_TEST > OPERATOR_CONFIRMED > USER_REPORTED`; break a remaining tie by lexical ascending UUID string. String equality uses NFC without trimming/case-folding, DATETIME equality uses the UTC instant, and boolean equality is exact. AVAILABLE always beats unavailable history. A conflict adds only `ReviewReason.CONFLICTING_EVIDENCE` to the view-level reasons. Folding trusts already-created `EvidenceItem.content_hash`; it does not recompute or verify hashes.

**Readiness.** `assess_readiness()` accepts only `ActiveEvidenceView`. Passing `MerchantSuccessCase` would create a construction cycle because a case already requires `readiness`; do not restore that parameter. The immutable seven-row priority table uses the exact slot identifiers, `MERCHANT_TECH` target, and Chinese reason strings from §5.4: `定位同一笔交易`, `对齐订单、回调和风控时间线`, `区分配置与凭据环境`, `确认可观察症状`, `决定后续条件槽位`, `确定插件上下文`, `排查版本差异`.

The derived `symptom.signal` reads exactly `symptom.status`, `symptom.error_code`, `authentication.status`, `authentication.result_code`, `callback.delivery_status`, `risk.decision_code`, and `configuration.check_result`. Its precedence is: any selected or conflicting member means AVAILABLE; otherwise all seven members being `known_unknown` means confirmed unknown; otherwise missing. A partial mixture of known-unknown and missing members remains missing, because another symptom source can still answer the composite question. For every non-composite readiness row, selected/conflict means AVAILABLE, `known_unknown` means confirmed unknown, and neither means missing.

Rows 1–5 are always active. Rows 6–7 activate only when `integration.type` has a nonconflicting selected value equal to `PLUGIN`; a conflict, unavailable value, missing value, or `API` does not activate them. A conflicting row counts as answered and AVAILABLE for readiness, while remaining unusable by Task 4 rules. Pre-supplied evidence for an inactive plugin row does not affect completion, missing/known-unknown fields, or question selection.

`next_question` is the unanswered active row's slot identifier, selected by priority 1→7; its reason and target are the frozen row values. `missing_fields` and `known_unknown_fields` are lexically sorted tuples. Core confirmed-unknown rows 1–4 appear in `missing_fields`; confirmed-unknown non-core rows appear in `known_unknown_fields`. If no active row is unanswered, all three question fields are `None`, even when a core row is confirmed unknown.

`completion_ratio = answered active rows / active rows`, quantized to four decimal places with `ROUND_HALF_UP` (for example, `5/7 = Decimal("0.7143")`). Stop precedence is: any unanswered active row → `NEED_MORE_EVIDENCE`; otherwise any core confirmed unknown → `CONFIRMED_UNKNOWN`; otherwise → `READY`. `ready` is true only for `READY`. `UNSUPPORTED` and `SECURITY_BLOCKED` are reserved for outer policies and are not emitted here.

The minimum test matrix is: empty view; each progressive priority step; plugin activation at 5/7; all-answered plugin context; all seven symptom members unavailable; one symptom member unavailable while the rest remain missing; core confirmed unknown with no next question; core conflict; integration conflict with plugin rows inactive; inactive pre-supplied plugin evidence; AVAILABLE plus unavailable history; all reliability/UUID ties; normalized DATETIME and Unicode equality; unequal-value conflict; and input permutations producing identical view/readiness results.

The canonical hash payload contains exactly:

```python
payload = {
    "availability": request.availability.value,
    "evidence_code": request.evidence_code.value,
    "evidence_id": request.evidence_id,
    "observed_at": utc_rfc3339(request.observed_at),
    "source_ref": request.source_ref,
    "source_reliability": origin.source_reliability.value,
    "source_type": origin.source_type.value,
    "synthetic": origin.synthetic,
    "typed_value": canonical_typed_value(request.typed_value),
}
encoded = json.dumps(
    payload,
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
).encode("utf-8")
return sha256(unicodedata.normalize("NFC", encoded.decode()).encode()).hexdigest()
```

`FIELD_CATALOG` must implement the exact locked value types and validators above. `CONFIRMED_UNAVAILABLE` rejects a non-null `typed_value`; AVAILABLE requires it. `build_active_evidence_view()` is the only selection function used later: AVAILABLE beats unavailable, normalized equal values choose highest source quality then lexical lowest UUID, unequal available values produce a conflicting slot, and no value is overwritten.

Readiness uses the locked immutable seven-row table above. The function computes active slots first, then answered slots, then exact `missing_fields`, `known_unknown_fields`, next question, target role, ratio, and stop reason. Conflicts are answered-for-collaboration and AVAILABLE-for-readiness but unusable-for-rules, and take the explicit human-review path described above. The function must never consult insertion time or list order.

- [ ] **Step 4: Verify all catalog and readiness branches**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/domain/test_evidence_policy.py tests/domain/test_readiness.py -q
.\.venv\Scripts\python.exe -m ruff check src/oceanpilot/domain tests/domain
```

Expected: all focused tests pass; no branch depends on “latest evidence”.

- [ ] **Step 5: Commit the deterministic evidence policy**

```powershell
git add -- src/oceanpilot/domain/evidence_policy.py tests/conftest.py tests/domain/test_evidence_policy.py tests/domain/test_readiness.py
git diff --cached --check
git commit -m "feat: add deterministic evidence readiness policy"
```

---

### Task 4: Implement the State Machine, Confidence Gates, and Four Rules

**Owner:** Python 技术轨

**Files:**
- Create: `src/oceanpilot/domain/state_machine.py`
- Create: `src/oceanpilot/domain/diagnosis.py`
- Create: `src/oceanpilot/adapters/diagnosis/rules.py`
- Create: `tests/domain/test_state_machine.py`
- Create: `tests/domain/test_confidence.py`
- Create: `tests/domain/test_diagnosis_rules.py`

**Interfaces:**
- Produces: explicit allowlist transitions, Decimal confidence result, the single authoritative `DiagnosisEngine` protocol in `domain/diagnosis.py`, and `RuleDiagnosisEngine.evaluate()` implementing it.
- Consumes: Task 3 `ActiveEvidenceView`; does not generate UUIDs or timestamps.

- [ ] **Step 1: Write failing transition, score, and decision-table tests**

The confidence boundary tests must use `Decimal`, not binary float:

```python
def test_user_reported_is_low_confidence_and_low_source(evidence_factory) -> None:
    result = calculate_confidence(
        [evidence_factory(reliability=SourceReliability.USER_REPORTED)],
        required_coverage=Decimal("1"),
        consistency=Decimal("1"),
    )
    assert result.raw_score == Decimal("0.865")
    assert result.display_score == Decimal("0.87")
    assert result.review_reasons == frozenset({
        ReviewReason.LOW_CONFIDENCE,
        ReviewReason.INSUFFICIENT_SOURCE_QUALITY,
    })


def test_synthetic_source_scores_point_94_without_low_reasons(evidence_factory) -> None:
    result = calculate_confidence(
        [evidence_factory(reliability=SourceReliability.SYNTHETIC_TEST)],
        required_coverage=Decimal("1"),
        consistency=Decimal("1"),
    )
    assert result.raw_score == Decimal("0.940")
    assert result.display_score == Decimal("0.94")
    assert not result.review_reasons
```

Parameterize all accepted and excluded predicate values for exactly these IDs:

```text
THREEDS_INCOMPLETE_V1
RISK_DECLINE_V1
CONFIG_MISMATCH_MERCHANT_V1
CONFIG_MISMATCH_PSP_V1
```

Also assert: no matching rule yields empty hypotheses plus `POLICY_GAP`; any input view already carrying `CONFLICTING_EVIDENCE` short-circuits before rule matching to empty hypotheses/routing/ticket with `requires_human=true`, including a fixture whose nonconflicting selected values would otherwise match a rule; two matching rules independently yield the same conflict-only result; risk always adds `RISK_DECISION`; every hypothesis references every decisive predicate evidence ID.

State tests cover both readiness outcomes from every AddEvidence-capable status. In particular, start from `DIAGNOSED` and `HUMAN_REVIEW` with a ready snapshot, add nonconflicting `integration.type=PLUGIN`, and prove that newly missing `integration.platform/plugin_version` makes `status_after_evidence()` return `NEED_INFO`, not `EVIDENCE_READY`. Reopening still supersedes the old snapshot and clears its pointer in later service/store tasks; Task 4 only freezes the target-status calculation.

Confidence tests additionally require a nonempty decisive-evidence sequence; parameterize all five source qualities and prove mixed inputs use the minimum. At coverage/consistency `1`, lock `SYSTEM_OF_RECORD → 1.000/1.00`, `VERIFIED_DOCUMENT → 0.970/0.97`, `SYNTHETIC_TEST → 0.940/0.94`, `OPERATOR_CONFIRMED → 0.925/0.93`, and `USER_REPORTED → 0.865/0.87`; only the final row carries both confidence reasons. `required_coverage` must be a finite `Decimal` in `[0, 1]`; `consistency` must be a finite `Decimal` exactly equal to `0` or `1`. Empty evidence, non-Decimal input, NaN, infinities, values outside the coverage interval, and intermediate consistency values all raise exactly `ValueError("invalid confidence inputs")` without echoing the value. Lock these boundaries using the unrounded score: synthetic quality plus coverage `0.92` yields raw exactly `0.900` and is not low confidence; coverage `0.91` yields raw `0.895`/display `0.90` but remains low confidence; minimum source quality exactly `0.75` does not trigger insufficient quality.

Freeze the complete result matrix in tests: conflict view → empty/none/none/human/conflict-only; zero rules → empty/none/none/human/policy-gap-only; two or more rules → conflict-only with no extra risk/confidence reasons; exactly one rule → hypothesis confidence equals `display_score`, reasons are confidence reasons union forced rule reasons, and `requires_human=bool(reasons)`. A single matched rule always retains its unambiguous route and TicketDraft even when low confidence or risk-gated, and the routing human flag/reasons equal the parent draft. Assert synthetic non-risk `0.94` without human review, user-reported non-risk `0.87` with both confidence reasons and retained route/ticket, and user-reported risk with those two reasons plus `RISK_DECISION` and retained RISK route/ticket. Confidence consumes exactly the decisive refs; unrelated low-quality evidence cannot alter the output.

Each rule test pins the fixed `explanation`, `routing_reason`, and `ticket_title` from spec §9.1. For all four rows, assert the exact `RoutingDecision.responsible_team/priority`, `TicketDraft.next_action/responsible_team/synthetic`, `ticket.summary=explanation`, `missing_material=()`, `ticket.hypotheses=(emitted_hypothesis,)`, and `evidence_summary` in predicate declaration order as safe `code=value` strings; route and ticket teams are identical and `ticket.synthetic == case.synthetic is True`. Hypothesis and route refs are all and only decisive IDs, deduplicated and sorted by canonical UUID text. Keeping the same view/policy while changing case ID, summary, merchant reference, status, and revisions must not change evaluation; the case and view must remain unmodified.

- [ ] **Step 2: Run tests and verify missing state/engine failures**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/domain/test_state_machine.py tests/domain/test_confidence.py tests/domain/test_diagnosis_rules.py -q
```

Expected: failures for missing state and diagnosis implementations.

- [ ] **Step 3: Implement the allowlist, exact Decimal formula, and immutable rules table**

The state allowlist is data, not nested conditionals:

```python
ALLOWED_COMMANDS: Final = {
    CaseStatus.NEW: frozenset(),
    CaseStatus.NEED_INFO: frozenset({CaseCommand.ADD_EVIDENCE}),
    CaseStatus.EVIDENCE_READY: frozenset({CaseCommand.ADD_EVIDENCE, CaseCommand.DIAGNOSE}),
    CaseStatus.DIAGNOSED: frozenset({CaseCommand.ADD_EVIDENCE, CaseCommand.DIAGNOSE}),
    CaseStatus.HUMAN_REVIEW: frozenset({CaseCommand.ADD_EVIDENCE, CaseCommand.DIAGNOSE}),
}
```

Creation is handled by `status_after_creation()`. Diagnose in DIAGNOSED/HUMAN_REVIEW is allowed only for version replay at the service/store layer. For every AddEvidence-capable current state, `status_after_evidence()` follows the newly computed readiness: ready → `EVIDENCE_READY`, otherwise → `NEED_INFO`. Reopening a diagnosed/review case still invalidates the old snapshot at the service/store layer, but never bypasses newly activated missing slots. Unlisted transitions raise `InvalidTransition` without mutation.

Confidence uses an externally immutable mapping (not a `Final`-annotated mutable dict):

```python
SOURCE_QUALITY: Final[Mapping[SourceReliability, Decimal]] = MappingProxyType({
    SourceReliability.SYSTEM_OF_RECORD: Decimal("1.00"),
    SourceReliability.VERIFIED_DOCUMENT: Decimal("0.90"),
    SourceReliability.SYNTHETIC_TEST: Decimal("0.80"),
    SourceReliability.OPERATOR_CONFIRMED: Decimal("0.75"),
    SourceReliability.USER_REPORTED: Decimal("0.55"),
})

raw = (
    Decimal("0.50") * required_coverage
    + Decimal("0.30") * minimum_source_quality
    + Decimal("0.20") * consistency
)
display = raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

Review comparisons use `raw < Decimal("0.90")` and `minimum_source_quality < Decimal("0.75")`.

Before applying the formula, `calculate_confidence()` validates the frozen input domain: `decisive_evidence` is nonempty; `required_coverage` is a finite `Decimal` in `[0, 1]`; `consistency` is a finite `Decimal` and one of `{Decimal("0"), Decimal("1")}`. Every violation raises `ValueError("invalid confidence inputs")`; the message never includes input values. Source quality is the minimum across exactly the decisive evidence sequence.

`rules.py` defines a frozen `RuleDefinition` tuple with the four rows and exact route, priority, cause code, next action, required predicates, `explanation`, `routing_reason`, and `ticket_title` from spec §9.1; allowed predicate values and forced reasons are `frozenset`s. Tests prove the source-quality map cannot be assigned/deleted and the rules tuple/definitions cannot be mutated. `evaluate()` reads rule facts only from `ActiveEvidenceView`; case metadata must not affect output, and neither input is mutated. Before evaluating any predicate or confidence, `ReviewReason.CONFLICTING_EVIDENCE` in `view.review_reasons` returns `DiagnosisDraft(hypotheses=(), routing_decision=None, ticket_draft=None, requires_human=True, review_reasons=frozenset({ReviewReason.CONFLICTING_EVIDENCE}))`. Zero matches returns the analogous `POLICY_GAP`-only draft. Two or more matched rule IDs produce the same conflict-only draft without additional reasons.

For exactly one match, decisive evidence consists of all and only the selected items satisfying the rule predicates. Hypothesis and route refs are deduplicated canonical UUID strings in lexical order; confidence uses that same sequence. `HypothesisDraft.confidence_score=display_score`; its fixed text comes from the rule. The draft reasons are `confidence.review_reasons | rule.forced_review_reasons`, and `requires_human=bool(review_reasons)`. Because responsibility is unambiguous, always construct both route and TicketDraft even for low confidence, insufficient source quality, and `RISK_DECISION`; `RoutingDecision.requires_human/review_reasons` exactly equal the parent. `ticket.summary=rule.explanation`, `missing_material=()`, `hypotheses=(hypothesis,)`, `next_action=rule.next_verification_action`, `responsible_team=route.responsible_team`, `synthetic=case.synthetic`, and `evidence_summary` uses predicate declaration order as `evidence_code=value`. No random IDs or timestamps are generated in Task 4.

- [ ] **Step 4: Run Gate 1 behavior tests and deterministic replay check**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/domain/test_state_machine.py tests/domain/test_confidence.py tests/domain/test_diagnosis_rules.py -q
.\.venv\Scripts\python.exe -m pytest tests/domain -q
.\.venv\Scripts\python.exe -m ruff check src tests/domain
```

Expected: all domain tests pass; four rule IDs appear once in the immutable table; repeated evaluation is equal.

- [ ] **Step 5: Commit the deterministic diagnostic core**

```powershell
git add -- src/oceanpilot/domain/state_machine.py src/oceanpilot/domain/diagnosis.py src/oceanpilot/adapters/diagnosis tests/domain
git diff --cached --check
git commit -m "feat: add deterministic incident diagnosis rules"
```

---

### Task 5: Freeze Application Commands and Atomic Store Ports

**Owner:** Python 技术轨

**Files:**
- Create: `src/oceanpilot/application/commands.py`
- Create: `src/oceanpilot/application/errors.py`
- Create: `src/oceanpilot/application/ports.py`
- Create: `tests/domain/test_application_contracts.py`
- Create: `tests/domain/test_import_boundaries.py`

**Interfaces:**
- Produces: the exact `CaseStoreSession` and `CaseStoreFactory` protocols plus frozen commands/errors used by all later tasks.
- Consumes: Task 2–4 domain value types only. Task 5 production modules neither import nor re-export `DiagnosisEngine`; its contract test imports the sole protocol directly from `domain/diagnosis.py`, and Task 11 `CaseService` must do the same. `application/ports.py` must not define, alias, import, or re-export another engine protocol.

- [ ] **Step 1: Write failing signature and import-boundary tests**

Use `inspect.signature()` to assert the Frozen Cross-Task Interfaces. Assert `application.ports` has no `DiagnosisEngine` or `EvidenceSource` member, while `RuleDiagnosisEngine` structurally satisfies the sole protocol in `domain.diagnosis`. The AST boundary test walks `src/oceanpilot/domain/*.py` and rejects `fastapi`, `sqlite3`, `oceanpilot.api`, `oceanpilot.application`, and `oceanpilot.adapters`; it separately walks `src/oceanpilot/application/*.py` and rejects `fastapi`, `sqlite3`, `oceanpilot.api`, and `oceanpilot.adapters`. The application layer may import domain types but no outward adapter/framework.

Also assert forbidden CRUD names are absent:

```python
def test_store_has_only_atomic_write_contracts() -> None:
    names = set(CaseStoreSession.__dict__)
    assert "save" not in names
    assert "save_case" not in names
    assert "update_evidence" not in names
    assert "delete_evidence" not in names
    assert {
        "create_case_atomic",
        "append_evidence_atomic",
        "commit_diagnosis_atomic",
    } <= names
```

- [ ] **Step 2: Run tests and verify the application modules are missing**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/domain/test_application_contracts.py tests/domain/test_import_boundaries.py -q
```

Expected: import failure for `oceanpilot.application.commands` or `ports`.

- [ ] **Step 3: Implement framework-free commands, stable errors, and protocols**

Commands are frozen Pydantic models:

```python
class CreateCaseCommand(FrozenDomainModel):
    case_type: CaseType
    summary: Annotated[str, Field(strict=True, min_length=1, max_length=500)]
    merchant_ref: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    synthetic: SyntheticTrue
    request_id: UUID4Str
    trace_id: UUID4Str


class AddEvidenceCommand(FrozenDomainModel):
    case_id: UUID4Str
    evidence: EvidenceCreate
    origin: EvidenceOrigin
    request_id: UUID4Str
    trace_id: UUID4Str


class DiagnoseCaseCommand(FrozenDomainModel):
    case_id: UUID4Str
    request_id: UUID4Str
    trace_id: UUID4Str
```

Stable application errors are separate classes with these exact fixed safe messages:

| Error | Safe message |
|---|---|
| `CaseNotFound` | `case was not found` |
| `CaseTypeNotEnabled` | `case type is not enabled` |
| `CaseNotReady` | `case is not ready for diagnosis` |
| `EvidenceConflict` | `evidence id conflicts with existing content` |
| `ConcurrentCaseWrite` | `case changed during write` |
| `DiagnosisInputStale` | `diagnosis input is stale` |
| `DatabaseUnavailable` | `database is unavailable` |
| `PersistenceInvariantViolation` | `persistence invariant was violated` |

`ApplicationError` owns a no-argument constructor and a class-level message. Its `__str__()` returns `type(self).message`, never `args`, instance attributes, raw SQL, exception chaining, or input values. The seven ordinary subclasses add no constructor and therefore reject every positional or keyword payload. Tests pass a sentinel to each constructor and require `TypeError`; after valid construction they mutate `error.args` and shadow `error.message` on the instance, yet `str(error)` must remain the exact class-owned safe message. `CaseNotReady` is the sole structured exception and accepts only the keyword-only whitelist below; its fixed `__str__()` follows the same rule.

`CaseNotReady` has the frozen constructor contract:

```python
class CaseNotReady(ApplicationError):
    def __init__(
        self,
        *,
        case_id: UUID4Str,
        missing_fields: Sequence[str],
        current_revision: Revision,
    ) -> None: ...
```

It exposes read-only `case_id: UUID4Str`, `missing_fields: tuple[str, ...]`, and `current_revision: Revision`. Construction tuple-copies `missing_fields`, so later caller mutation cannot alter the error. The element type is deliberately `str`, not `EvidenceCode`, because readiness can contain the derived slot `symptom.signal`; `current_revision` means case revision, not evidence revision. Attribute reassignment is rejected, and `str(error)` is exactly `case is not ready for diagnosis`, with no ID, field, revision, SQL, or input value. Tests lock the signature/type hints, list-to-tuple anti-aliasing, read-only attributes, acceptance of `symptom.signal`, and fixed safe string.

Implement only the Store protocol signatures from Frozen Cross-Task Interfaces. `AddEvidenceCommand.origin` is an internal, frozen value: the HTTP mapper always constructs `MERCHANT/USER_REPORTED`, while the internal synthetic adapter constructs `SYNTHETIC_ADAPTER/SYNTHETIC_TEST`. No request DTO exposes origin fields. This command boundary is the independent internal ingress described by approved spec §5.3; no application protocol may import a demo-only `SyntheticScenario` type from an adapter.

- [ ] **Step 4: Verify protocols and the dependency direction**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/domain/test_application_contracts.py tests/domain/test_import_boundaries.py -q
.\.venv\Scripts\python.exe -m pytest tests/domain -q
.\.venv\Scripts\python.exe -m ruff check src tests/domain
```

Expected: all pass; domain imports contain no forbidden root.

- [ ] **Step 5: Commit and stop for Gate 1 review**

```powershell
git add -- src/oceanpilot/application tests/domain
git diff --cached --check
git commit -m "feat: freeze application and store contracts"
git status --short
```


Expected: clean status. Send the commit SHA and full Gate 1 command outputs to the total-control task. Do not start SQLite work until Task 6 records PASS.

---

### Task 6: Gate 1 Independent Domain Review

**Owner:** 总控轨

**Files:**
- Create on PASS: `docs/reviews/gate-1-domain.md`
- Read only: `pyproject.toml`, `src/oceanpilot/domain/**`, `src/oceanpilot/application/{commands,errors,ports}.py`, `src/oceanpilot/adapters/diagnosis/rules.py`, `tests/domain/**`

**Interfaces:**
- Produces: an evidence-backed PASS report or blocking findings.
- Consumes: the clean technical-track commit from Task 5.

- [ ] **Step 1: Verify the handoff and working tree before reviewing**

Run:

```powershell
$task5Sha = "94192a0a548d4e568c9a08b70312397230036930"
$expectedParent = "fcf21d6aeb9385e30ff48108fa0e91bca22c778a"

if ((git status --short).Count -ne 0) {
    throw "working tree is not clean"
}

$actualParent = (git rev-parse "${task5Sha}^").Trim()
if ($actualParent -ne $expectedParent) {
    throw "unexpected Task 5 parent: $actualParent"
}

$subject = (git show -s --format=%s $task5Sha).Trim()
if ($subject -ne "feat: freeze application and store contracts") {
    throw "unexpected Task 5 subject: $subject"
}

$expectedFiles = @(
    "A`tsrc/oceanpilot/application/commands.py"
    "A`tsrc/oceanpilot/application/errors.py"
    "A`tsrc/oceanpilot/application/ports.py"
    "A`ttests/domain/test_application_contracts.py"
    "A`ttests/domain/test_import_boundaries.py"
) | Sort-Object
$actualFiles = @(git diff-tree --no-commit-id --name-status -r $task5Sha) | Sort-Object
if (Compare-Object $expectedFiles $actualFiles) {
    throw "Task 5 file scope mismatch"
}

git show --check --oneline $task5Sha
if ($LASTEXITCODE -ne 0) { throw "Task 5 patch check failed" }

git merge-base --is-ancestor $task5Sha HEAD
if ($LASTEXITCODE -ne 0) {
    throw "Task 5 is not an ancestor of Gate-contract HEAD"
}

git diff --quiet "${task5Sha}..HEAD" -- src tests pyproject.toml .gitignore .github examples
if ($LASTEXITCODE -ne 0) {
    throw "technical files changed after Task 5 handoff"
}

$specBlob = (git rev-parse "HEAD:docs/superpowers/specs/2026-07-18-oceanpilot-evidenceos-design.md").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($specBlob)) {
    throw "cannot resolve the Gate-contract spec blob"
}
$planBlob = (git rev-parse "HEAD:docs/superpowers/plans/2026-07-18-oceanpilot-evidenceos-mvp-implementation.md").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($planBlob)) {
    throw "cannot resolve the Gate-contract plan blob"
}

"Task5=$task5Sha"
"GateContractHEAD=$(git rev-parse HEAD)"
"SpecBlob=$specBlob"
"PlanBlob=$planBlob"
```

Expected: status is empty; the reviewed Task 5 commit has the exact parent, subject, and five-file scope; its patch is clean; and no technical file changed between that commit and the current Gate-contract HEAD. Record both SHAs and both document blob IDs instead of presenting a later docs-only HEAD as the technical handoff.

- [ ] **Step 2: Run the complete Gate 1 evidence commands**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/domain/test_application_contracts.py tests/domain/test_import_boundaries.py -q
if ($LASTEXITCODE -ne 0) { throw "Task 5 contract tests failed" }
.\.venv\Scripts\python.exe -m pytest tests/domain -q
if ($LASTEXITCODE -ne 0) { throw "domain suite failed" }
.\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "full suite failed" }
.\.venv\Scripts\python.exe -m ruff check src tests/domain
if ($LASTEXITCODE -ne 0) { throw "Ruff failed" }
.\.venv\Scripts\python.exe -m compileall -q src tests/domain
if ($LASTEXITCODE -ne 0) { throw "compileall failed" }

$previousHashSeed = [Environment]::GetEnvironmentVariable("PYTHONHASHSEED", "Process")
try {
    foreach ($seed in @("1", "777")) {
        [Environment]::SetEnvironmentVariable("PYTHONHASHSEED", $seed, "Process")
        .\.venv\Scripts\python.exe -m pytest tests/domain/test_evidence_policy.py tests/domain/test_readiness.py tests/domain/test_diagnosis_rules.py -q
        if ($LASTEXITCODE -ne 0) {
            throw "determinism replay failed with PYTHONHASHSEED=$seed"
        }
    }
}
finally {
    [Environment]::SetEnvironmentVariable("PYTHONHASHSEED", $previousHashSeed, "Process")
}

function Assert-NoMatch {
    param([string]$Label, [string]$Pattern, [string[]]$Paths)
    $hits = & rg -n --glob "*.py" -- $Pattern @Paths
    $code = $LASTEXITCODE
    if ($code -eq 0) {
        $hits
        throw "$Label found forbidden matches"
    }
    if ($code -ne 1) { throw "$Label rg failed with exit $code" }
}

Assert-NoMatch "domain dependency boundary" '^(from|import)\s+(fastapi|sqlite3|oceanpilot\.(api|application|adapters))(\.|\s|$)' @("src/oceanpilot/domain")
Assert-NoMatch "application dependency boundary" '^(from|import)\s+(fastapi|sqlite3|oceanpilot\.(api|adapters))(\.|\s|$)' @("src/oceanpilot/application")
Assert-NoMatch "Task 5 outer protocol aliases" '\b(DiagnosisEngine|EvidenceSource|SyntheticScenario)\b' @("src/oceanpilot/application/commands.py", "src/oceanpilot/application/errors.py", "src/oceanpilot/application/ports.py")
Assert-NoMatch "domain nondeterminism" '\b(uuid4|random|secrets|requests|httpx|getenv)\b|datetime\.(now|utcnow)|time\.time|os\.environ' @("src/oceanpilot/domain/evidence_policy.py", "src/oceanpilot/domain/state_machine.py", "src/oceanpilot/domain/diagnosis.py", "src/oceanpilot/adapters/diagnosis/rules.py")

$engineDefinitions = @(rg -n '^class DiagnosisEngine\b' src/oceanpilot)
if ($LASTEXITCODE -ne 0 -or $engineDefinitions.Count -ne 1) {
    $engineDefinitions
    throw "DiagnosisEngine must have exactly one definition"
}

git diff --check 78e7064..HEAD
if ($LASTEXITCODE -ne 0) { throw "historical diff check failed" }
```

Expected: focused contracts, domain suite, full suite, Ruff, compileall, both deterministic replays, historical diff check, AST boundary tests, and independent static probes all pass. Each `Assert-NoMatch` must receive `rg` exit `1` with no output; any match or tool error fails the Gate.

- [ ] **Step 3: Inspect the non-negotiable Gate 1 invariants**

Confirm from code and tests:

1. `assess_readiness()` only accepts `ActiveEvidenceView`; rule matching, decisive evidence, and confidence facts also read only from that view. Case ID, status, summary, merchant reference, case revision, and evidence revision cannot affect rule choice or output; `synthetic=true` is the sole tested case-field propagation.
2. `EvidenceItem` is frozen and append-only; no Evidence UPDATE/DELETE method, generic save method, or raw SQLite connection exists in application ports.
3. All five source-quality scores, raw-score thresholds, minimum-source behavior, invalid Decimal inputs, and unrounded comparisons are directly test-backed. In particular, USER_REPORTED is `0.865 → 0.87` with exactly two confidence reasons and SYNTHETIC_TEST is `0.940 → 0.94`.
4. The immutable rule table contains exactly four rule IDs. Every accepted, excluded, missing, and `CONFIRMED_UNAVAILABLE` predicate path is independently tested. A single rule emits all-and-only decisive refs; zero, multiple, and conflicting matches emit no hypothesis.
5. Fixed explanations describe rule matches and required verification rather than asserting an unverified cause as fact. Ticket output remains a draft, contains no `source_ref` or `merchant_ref`, and preserves `synthetic=true`.
6. Commands have exact fields, required/no-default keyword-only constructors, frozen nested inputs, and safe Pydantic configuration. Stable application errors reject arbitrary payloads and cannot leak through `args` or instance-message shadowing; `CaseNotReady` is the sole structured exception.
7. `CaseStoreSession` and `CaseStoreFactory` have exactly the frozen signatures. Task 5 application modules neither define/import/re-export `DiagnosisEngine` nor expose `EvidenceSource` or `SyntheticScenario`.
8. Domain and application dependency direction is enforced for absolute, relative, aliased, and aggregate imports. No UUID/time generation or runtime randomness, environment, or network access enters the deterministic domain/rule path; FastAPI and SQLite remain outside it. Parsing and normalizing evidence timestamps is allowed.
9. Tests use independently frozen expected values rather than deriving expectations from `RULES`, `SOURCE_QUALITY`, `FIELD_CATALOG`, or actual output.

If any behavioral invariant is not directly test-backed, any dependency/determinism invariant is neither directly test-backed nor independently static-probe-backed, or a test oracle is tautological, record a blocking finding and do not create a PASS report.

- [ ] **Step 4: Record the Gate report with actual evidence**

On PASS, create `docs/reviews/gate-1-domain.md` using `apply_patch`. The report must contain: the reviewed Task 5 SHA, current Gate-contract HEAD, spec and plan blob IDs, timestamp, every command above, actual exit status/test count, the direct test names and/or independent static probes supporting each invariant, both `PYTHONHASHSEED` results, reviewed invariants, residual limitations, reviewer verdict `PASS`, and the sentence “Gate 2 SQLite work is now allowed.” Residual limitations must state that the MVP still uses synthetic data, rule thresholds are not calibrated on Oceanpayment history, and CaseService/SQLite/API/real Feishu or Oceanpayment integrations are not yet implemented. Do not invent counts or copy expected output as actual output.

- [ ] **Step 5: Commit the review report and release the write lock**

```powershell
git add -- docs/reviews/gate-1-domain.md
git diff --cached --check
git commit -m "docs: record Gate 1 domain review"
git status --short
```

Expected: clean status. Notify the technical track that Task 7 may begin.

---

### Task 7: Build the SQLite Schema, Connection Factory, and Transaction Primitive

**Owner:** Python 技术轨

**Files:**
- Create: `src/oceanpilot/adapters/persistence/schema.py`
- Create: `src/oceanpilot/adapters/persistence/sqlite.py`
- Create: `tests/repository/test_sqlite_schema.py`
- Create: `tests/repository/test_sqlite_connection.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces from `schema.py`: `SCHEMA_SQL` and immutable `REQUIRED_TABLES`.
- Produces from `sqlite.py`: `initialize_schema(path)`, `connect_sqlite(path)`, `immediate_transaction(connection)`, `SqliteCaseStoreSession` with `healthcheck()`, and the context-managed `SqliteCaseStoreFactory`.
- Consumes: Task 5 ports and domain models.

The Task 7 Session/Factory is intentionally a tested persistence-lifetime skeleton: the Session owns one connection and exposes `healthcheck()` only at this task; the Factory opens a fresh connection per context and always closes it. Tasks 8 and 9 add the remaining six business methods to that same Session. Do not add `NotImplemented` methods, generic CRUD, or raw-connection access, and do not claim full structural conformance to `CaseStoreSession` before Task 9.

- [ ] **Step 1: Write failing real-file schema and connection tests**

Tests use one real file per test, never `:memory:`. Add this complete shared fixture to `tests/conftest.py`:

```python
from pathlib import Path


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "oceanpilot.db"
```

All schema expectations in the tests are hard-coded test-local oracles. Tests must not import `SCHEMA_SQL` or `REQUIRED_TABLES` to derive expected table names, columns, keys, indexes, foreign keys, deferred clauses, or CHECK constraints. They must additionally prove:

1. `PRAGMA database_list` resolves the `main` database to `db_path.resolve()`, the file exists, and no connection uses `:memory:`.
2. A fresh initialized live connection reports `PRAGMA journal_mode = delete`, and a completed write followed by close leaves no `-wal`/`-shm` artifacts. A database deliberately pre-seeded in WAL mode is rejected with safe `DatabaseUnavailable`; checking only whether those files remain after close is insufficient because they may disappear while the persisted mode remains `wal`.
3. Fresh initialization creates exactly the six hard-coded table names. Test-local `PRAGMA table_info`, `index_list`/`index_info`, `foreign_key_list`, normalized `sqlite_schema.sql`, and invalid inserts independently lock the primary keys, UNIQUE keys, composite foreign keys, deferred clauses, and critical CHECK constraints from the DDL below.
4. `healthcheck()` rejects each missing required business table and a controlled `PRAGMA foreign_key_check` violation. Both paths expose only `DatabaseUnavailable()` and never the SQLite sentinel.
5. Each Factory context receives a distinct real connection. Normal exit and an exception raised inside the context both close the connection; executing SQL on each captured connection afterwards raises `sqlite3.ProgrammingError`.

They must assert:

```python
def test_connection_enables_required_pragmas(db_path) -> None:
    connection = connect_sqlite(db_path)
    try:
        assert connection.row_factory is sqlite3.Row
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        connection.close()


def test_connect_error_is_mapped_without_sqlite_message(db_path, monkeypatch) -> None:
    def fail_connect(*args, **kwargs):
        raise sqlite3.OperationalError("SQLITE-SENTINEL-DO-NOT-ECHO")

    monkeypatch.setattr(sqlite3, "connect", fail_connect)
    with pytest.raises(DatabaseUnavailable) as caught:
        connect_sqlite(db_path)
    assert str(caught.value) == "database is unavailable"
    assert "SENTINEL" not in str(caught.value)


def test_successful_transaction_uses_begin_immediate_and_persists(db_path) -> None:
    connection = connect_sqlite(db_path)
    connection.execute("CREATE TABLE tx_probe (value TEXT NOT NULL)")
    traced: list[str] = []
    connection.set_trace_callback(traced.append)
    with immediate_transaction(connection):
        connection.execute("INSERT INTO tx_probe(value) VALUES (?)", ("demo",))
    connection.close()

    reopened = connect_sqlite(db_path)
    try:
        assert reopened.execute("SELECT value FROM tx_probe").fetchone()[0] == "demo"
    finally:
        reopened.close()
    assert "BEGIN IMMEDIATE" in traced
    assert "COMMIT" in traced


def test_failed_transaction_rolls_back_every_write(db_path) -> None:
    initialize_schema(db_path)
    connection = connect_sqlite(db_path)
    connection.execute("CREATE TABLE tx_probe (value TEXT NOT NULL)")
    with pytest.raises(RuntimeError):
        with immediate_transaction(connection):
            connection.execute("INSERT INTO tx_probe(value) VALUES (?)", ("demo",))
            raise RuntimeError("force rollback")
    assert connection.execute("SELECT count(*) FROM tx_probe").fetchone()[0] == 0
    connection.close()


def test_commit_time_foreign_key_failure_rolls_back(db_path) -> None:
    connection = connect_sqlite(db_path)
    connection.executescript("""
        CREATE TABLE parent (id TEXT PRIMARY KEY);
        CREATE TABLE child (
            parent_id TEXT NOT NULL,
            FOREIGN KEY (parent_id) REFERENCES parent(id)
                DEFERRABLE INITIALLY DEFERRED
        );
    """)
    with pytest.raises(sqlite3.IntegrityError):
        with immediate_transaction(connection):
            connection.execute("INSERT INTO child(parent_id) VALUES (?)", ("missing",))
    assert connection.in_transaction is False
    assert connection.execute("SELECT count(*) FROM child").fetchone()[0] == 0
    connection.close()
```

Also test PRAGMA execution failure and a `foreign_keys` read-back of `0` after a real connection has been obtained; both paths must close that connection and raise fixed `DatabaseUnavailable` without a cause or raw SQLite sentinel. `initialize_schema()` must close its connection after success and after controlled DDL/self-check failure. Corrupt-file, controlled `Path.mkdir` `PermissionError`, and controlled schema-error tests all map to the same safe error without a chained sentinel.

- [ ] **Step 2: Run tests and confirm persistence modules are absent**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repository/test_sqlite_schema.py tests/repository/test_sqlite_connection.py -q
```

Expected: collection fails specifically because `oceanpilot.adapters.persistence.schema` and/or `.sqlite` is missing. Run Ruff and compileall on the two new test files before accepting RED so syntax, fixture, or collection mistakes cannot masquerade as the required `ModuleNotFoundError`.

- [ ] **Step 3: Implement connection safety and the exact six-table schema**

`connect_sqlite()` must be exactly equivalent to:

```python
def connect_sqlite(path: Path) -> sqlite3.Connection:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            str(path),
            timeout=5.0,
            isolation_level=None,
            autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        foreign_keys_row = connection.execute("PRAGMA foreign_keys").fetchone()
        journal_mode_row = connection.execute("PRAGMA journal_mode").fetchone()
        if (
            foreign_keys_row is None
            or foreign_keys_row[0] != 1
            or journal_mode_row is None
            or journal_mode_row[0] != "delete"
        ):
            connection.close()
            raise DatabaseUnavailable()
        return connection
    except sqlite3.Error:
        if connection is not None:
            connection.close()
        raise DatabaseUnavailable() from None
```

The live `journal_mode` read is mandatory: it both rejects a persisted WAL database and forces SQLite to inspect a corrupt file before returning the connection. The fixed message is identical for open, permission, corruption, foreign-key, journal-mode, and PRAGMA failures; no raw sqlite message is chained or logged. Tests use a trackable real connection or wrapper to prove that every failure after connect closes it.

`immediate_transaction()` begins and ends transactions explicitly:

```python
@contextmanager
def immediate_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
```

`COMMIT` deliberately remains inside the `try`: a deferred foreign-key violation can occur at commit time, and that path must explicitly roll back before returning the connection to a caller.

`SCHEMA_SQL` defines exactly these keys and constraints:

```sql
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    case_type TEXT NOT NULL CHECK (case_type = 'PAYMENT_INCIDENT'),
    status TEXT NOT NULL CHECK (status IN ('NEW','NEED_INFO','EVIDENCE_READY','DIAGNOSED','HUMAN_REVIEW')),
    schema_version TEXT NOT NULL,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 0),
    evidence_revision INTEGER NOT NULL CHECK (evidence_revision >= 0),
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    summary TEXT NOT NULL CHECK (length(summary) BETWEEN 1 AND 500),
    merchant_ref TEXT NOT NULL CHECK (length(merchant_ref) BETWEEN 1 AND 128),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    current_diagnosis_id TEXT,
    readiness_json TEXT NOT NULL,
    FOREIGN KEY (case_id, current_diagnosis_id)
        REFERENCES diagnosis_snapshots(case_id, diagnosis_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS evidence_items (
    case_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    evidence_code TEXT NOT NULL,
    availability TEXT NOT NULL CHECK (availability IN ('AVAILABLE','CONFIRMED_UNAVAILABLE')),
    value_type TEXT NOT NULL,
    typed_value_json TEXT,
    source_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    source_reliability TEXT NOT NULL,
    observed_at TEXT,
    collected_at TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    PRIMARY KEY (case_id, evidence_id),
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE TABLE IF NOT EXISTS diagnosis_snapshots (
    case_id TEXT NOT NULL,
    diagnosis_id TEXT NOT NULL,
    evidence_revision INTEGER NOT NULL CHECK (evidence_revision >= 0),
    policy_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('CURRENT','SUPERSEDED')),
    routing_json TEXT,
    ticket_json TEXT,
    requires_human INTEGER NOT NULL CHECK (requires_human IN (0,1)),
    review_reasons_json TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    created_at TEXT NOT NULL,
    PRIMARY KEY (case_id, diagnosis_id),
    UNIQUE (case_id, evidence_revision, policy_version),
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE TABLE IF NOT EXISTS hypotheses (
    case_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    diagnosis_id TEXT NOT NULL,
    cause_code TEXT NOT NULL,
    explanation TEXT NOT NULL,
    confidence_score REAL NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
    confidence_method TEXT NOT NULL CHECK (confidence_method = 'HEURISTIC_V1'),
    next_verification_action TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    PRIMARY KEY (case_id, hypothesis_id),
    UNIQUE (case_id, diagnosis_id, rule_id),
    FOREIGN KEY (case_id, diagnosis_id)
        REFERENCES diagnosis_snapshots(case_id, diagnosis_id)
);

CREATE TABLE IF NOT EXISTS hypothesis_evidence_refs (
    case_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    PRIMARY KEY (case_id, hypothesis_id, evidence_id),
    FOREIGN KEY (case_id, hypothesis_id)
        REFERENCES hypotheses(case_id, hypothesis_id),
    FOREIGN KEY (case_id, evidence_id)
        REFERENCES evidence_items(case_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    case_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_version TEXT NOT NULL,
    request_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    case_revision INTEGER NOT NULL CHECK (case_revision >= 0),
    evidence_revision INTEGER NOT NULL CHECK (evidence_revision >= 0),
    occurred_at TEXT NOT NULL,
    result TEXT NOT NULL,
    reason_code TEXT,
    sanitized_metadata_json TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic = 1),
    PRIMARY KEY (case_id, event_id),
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);
```

`schema.py` owns only `SCHEMA_SQL` and `REQUIRED_TABLES`; `sqlite.py` imports those constants and owns `initialize_schema()`, connection, transaction, Session, and Factory lifetimes. This direction avoids a schema/connection import cycle. `initialize_schema()` creates the parent directory, opens one connection, calls `executescript(SCHEMA_SQL)` only for initialization, requires the fresh table set to equal `REQUIRED_TABLES`, performs `PRAGMA foreign_key_check`, and closes in `finally`. A parent-directory `OSError` or any SQLite DDL/self-check error is raised as `DatabaseUnavailable() from None`. Business methods never call `executescript()`.

`SqliteCaseStoreSession.healthcheck()` must prove the initialized schema is usable, not merely execute `SELECT 1`: it requires every member of `REQUIRED_TABLES` to exist, runs `SELECT case_id FROM cases LIMIT 0`, then `PRAGMA foreign_key_check`; a missing required table, sqlite error, or any foreign-key-check row maps to fixed `DatabaseUnavailable() from None`. Extra non-business tables do not make an otherwise healthy initialized database fail.

Task 7 implements and tests the Factory lifetime now, using the same shape retained by Tasks 8 and 9:

```python
class SqliteCaseStoreSession:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def healthcheck(self) -> None:
        ...


class SqliteCaseStoreFactory:
    def __init__(self, path: Path) -> None:
        self._path = path

    @contextmanager
    def __call__(self) -> Iterator[SqliteCaseStoreSession]:
        connection = connect_sqlite(self._path)
        try:
            yield SqliteCaseStoreSession(connection)
        finally:
            connection.close()
```

- [ ] **Step 4: Run schema, rollback, and PRAGMA tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repository/test_sqlite_schema.py tests/repository/test_sqlite_connection.py -q
.\.venv\Scripts\python.exe -m pytest tests/domain -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
rg -n ":memory:" src/oceanpilot/adapters/persistence tests/repository
rg -ni "pragma\s+journal_mode\s*=\s*wal" src/oceanpilot/adapters/persistence
git diff --check
```

Expected: focused, domain, full, Ruff, compileall, and diff checks pass. Both `rg` commands return exit `1` with no output. Every test DB is a real file; a live fresh connection reports `delete`; pre-seeded WAL is safely rejected; no production code enables WAL.

- [ ] **Step 5: Commit the persistence foundation**

```powershell
git add -- `
  src/oceanpilot/adapters/persistence/schema.py `
  src/oceanpilot/adapters/persistence/sqlite.py `
  tests/repository/test_sqlite_schema.py `
  tests/repository/test_sqlite_connection.py `
  tests/conftest.py
git diff --cached --check
git diff --cached --name-status
git commit -m "feat: add SQLite schema and transaction primitive"
git show --check --oneline HEAD
git status --short
```

Before committing, compare the cached name-status against the exact five paths above and require no unstaged tracked diff. After committing, require the parent to equal the exact Task 7 handoff SHA recorded in `.superpowers/sdd/task-7-brief.md`, the exact subject above, the exact five-file scope, `git show --check` success, and clean status.

---

### Task 8: Implement Atomic Case Creation and Evidence Append

**Owner:** Python 技术轨

**Files:**
- Modify: `src/oceanpilot/adapters/persistence/sqlite.py`
- Create: `tests/repository/test_case_store.py`
- Create: `tests/repository/test_evidence_store.py`
- Create: `tests/repository/test_evidence_concurrency.py`

**Interfaces:**
- Produces: completes the existing Task 7 `SqliteCaseStoreSession` with `create_case_atomic`, `get_case_view`, `load_case_snapshot`, and `append_evidence_atomic`; the tested `SqliteCaseStoreFactory` lifetime remains unchanged.
- Consumes: Task 7 connection/transaction and Task 5 atomic ports.

- [ ] **Step 1: Write failing create, replay, conflict, reopen, rollback, and concurrent-CAS tests**

Required tests:

```text
create writes case + readiness + audit in one transaction
create rejects an audit with another case_id, wrong post-revision, wrong status, or event type and writes zero rows
case/evidence/audit round-trip converts SQLite synthetic INTEGER 1 to Python True before strict domain validation
decode_sqlite_bool rejects 2, "1", null, and any non-exact INTEGER 0/1 as PersistenceInvariantViolation
same evidence_id + same content_hash returns REPLAY with no revision/audit increase
same evidence_id + different content_hash raises EvidenceConflict
new evidence increments case_revision and evidence_revision exactly once
new evidence after DIAGNOSED/HUMAN_REVIEW supersedes CURRENT snapshot and clears current_diagnosis_id whether recomputed target is NEED_INFO or EVIDENCE_READY; evidence REPLAY does neither
adding integration.type=PLUGIN to a previously ready diagnosed/review case atomically persists NEED_INFO readiness, supersedes the snapshot, clears the pointer, and emits the matching transition audit
audit trigger failure rolls back evidence, state, both revisions, and snapshot lifecycle
two connections adding the same evidence persist one row
two different evidence writes from the same expected revision yield one success and one ConcurrentCaseWrite; Store itself never guesses a recomputation
append with target_status inconsistent with status_after_evidence(current_status, readiness) is rejected and rolls back
append rejects an audit batch with mixed request/trace IDs, wrong case/revisions/statuses, duplicate/missing event types, or an unexpected event and rolls back
```

Use a SQLite test trigger to force rollback instead of adding a production-only failure hook:

```sql
CREATE TRIGGER fail_audit BEFORE INSERT ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'forced audit failure');
END;
```

- [ ] **Step 2: Run the tests and confirm atomic methods are missing**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repository/test_case_store.py tests/repository/test_evidence_store.py tests/repository/test_evidence_concurrency.py -q
```

Expected: failures for missing Store methods.

- [ ] **Step 3: Add atomic business methods to the existing per-command session with no generic save**

Factory lifetime was implemented and tested in Task 7 and remains exactly:

```python
class SqliteCaseStoreFactory:
    def __init__(self, path: Path) -> None:
        self._path = path

    @contextmanager
    def __call__(self) -> Iterator[SqliteCaseStoreSession]:
        connection = connect_sqlite(self._path)
        try:
            yield SqliteCaseStoreSession(connection)
        finally:
            connection.close()
```

`create_case_atomic()` has no separate readiness parameter: it persists `case.readiness` as the single authority. Before mutation it validates exactly one `CASE_CREATED` event with the same `case_id`, post revisions `1/0`, `from_status=None`, `to_status=case.status`, and a single request/trace pair; then it performs `BEGIN IMMEDIATE → sensitive scan → case insert → audit insert → COMMIT`.

`append_evidence_atomic()` first requires `target_status == status_after_evidence(current.status, readiness)`; a mismatch raises `PersistenceInvariantViolation`. Its shared `validate_audit_batch()` requires every event to use the command case ID, one request/trace pair, post revisions `(expected_case_revision + 1, expected_evidence_revision + 1)`, and `from_status=current.status/to_status=target_status`. The allowed type set is exactly: `EVIDENCE_ADDED`; plus `DIAGNOSIS_SUPERSEDED` iff a current diagnosis is reopened; plus `STATE_TRANSITIONED` iff status changes. Each required type appears once and no other type is accepted. Validation occurs inside the transaction after loading current state but before the first mutation. It then performs this order:

```text
1. SELECT existing evidence by (case_id, evidence_id).
2. Same hash: return REPLAY immediately without audit/version writes.
3. Different hash: raise EvidenceConflict and roll back.
4. INSERT evidence.
5. If reopening, CURRENT diagnosis → SUPERSEDED.
6. CAS UPDATE cases WHERE case_revision=? AND evidence_revision=?;
   set readiness_json, target status, both revisions +1, updated_at,
   and current_diagnosis_id=NULL when reopening.
7. Require rowcount == 1, otherwise raise ConcurrentCaseWrite.
8. INSERT every audit event.
9. COMMIT and return a freshly loaded CaseView with outcome CREATED.
```

All SQL values use `?` placeholders. SQLite boolean columns are never passed directly into strict Pydantic models and never decoded with `bool(raw)`. A single `decode_sqlite_bool(name, raw)` requires `type(raw) is int` and `raw in (0, 1)`, then returns `raw == 1`; every `synthetic` field additionally requires the decoded value to be true. Any other shape raises safe `PersistenceInvariantViolation`. JSON booleans remain JSON booleans. Every `sqlite3.IntegrityError`, `OperationalError`, and unexpected row shape is converted to a stable application error without including the raw SQLite message. Repository entry points run `assert_no_sensitive_data()` on serializable domain payloads before writes.

- [ ] **Step 4: Verify idempotency, rollback, and two-connection behavior**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repository/test_case_store.py tests/repository/test_evidence_store.py tests/repository/test_evidence_concurrency.py -q
.\.venv\Scripts\python.exe -m ruff check src/oceanpilot/adapters/persistence tests/repository
```

Expected: all tests pass; replay leaves row/revision/audit counts unchanged; conflict and forced audit failure leave all business rows, statuses, revisions, snapshot lifecycle, and audit counts unchanged.

- [ ] **Step 5: Commit atomic case/evidence persistence**

```powershell
git add -- src/oceanpilot/adapters/persistence/sqlite.py tests/repository
git diff --cached --check
git commit -m "feat: add atomic case and evidence persistence"
```

---

### Task 9: Implement Diagnosis Snapshot CAS, Deduplication, and Evidence References

**Owner:** Python 技术轨

**Files:**
- Modify: `src/oceanpilot/adapters/persistence/sqlite.py`
- Create: `tests/repository/test_diagnosis_store.py`
- Create: `tests/repository/test_diagnosis_concurrency.py`
- Create: `tests/repository/test_cross_case_references.py`

**Interfaces:**
- Produces: `find_diagnosis` and `commit_diagnosis_atomic` with unique replay and stale-input detection.
- Consumes: Task 8 session and Task 4 snapshot models.

- [ ] **Step 1: Write failing tests for the two diagnosis races and composite foreign keys**

Tests must prove:

```text
same (case_id,evidence_revision,policy_version) returns the original snapshot
diagnosis/requires_human/synthetic round-trip decodes exact SQLite 0/1 before strict model validation
two concurrent identical diagnosis commits persist one snapshot and one audit set
evidence added after read causes commit to raise DiagnosisInputStale
an old unique snapshot plus a now-advanced evidence_revision is stale, not a replay
cross-case hypothesis_evidence_ref is rejected by SQLite
POLICY_GAP and conflict persist null route/ticket JSON
risk review persists a RISK route and review-only TicketDraft
any hypothesis/ref/audit failure rolls back the entire diagnosis and case state
snapshot.requires_human=true with target_status other than HUMAN_REVIEW is rejected and rolls back
snapshot.requires_human=false with target_status other than DIAGNOSED is rejected and rolls back
diagnosis rejects an audit batch with wrong case/revisions/statuses, mixed request/trace IDs, missing/extra/duplicate event types, or ROUTING_PROPOSED inconsistent with route presence
```

- [ ] **Step 2: Run focused repository tests and confirm diagnosis methods are missing**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repository/test_diagnosis_store.py tests/repository/test_diagnosis_concurrency.py tests/repository/test_cross_case_references.py -q
```

Expected: failures for missing `find_diagnosis`/`commit_diagnosis_atomic`.

- [ ] **Step 3: Implement the exact two-phase commit semantics**

`find_diagnosis()` reads by the frozen unique key and reconstructs immutable hypotheses, evidence refs, route, and draft. Hypothesis evidence-reference rows are always reconstructed with SQL `ORDER BY evidence_id`; repository row or insertion order must not affect the immutable tuple. Before any mutation, `commit_diagnosis_atomic()` requires `target_status=HUMAN_REVIEW` exactly when `snapshot.requires_human` is true, otherwise `target_status=DIAGNOSED`; a mismatch raises `PersistenceInvariantViolation`. After loading current state, the same `validate_audit_batch()` requires the same case ID/request/trace pair, post revisions `(expected_case_revision + 1, expected_evidence_revision)`, and `from_status=current.status/to_status=target_status`. Required types are exactly `DIAGNOSIS_CREATED`, `ROUTING_PROPOSED` iff `snapshot.routing_decision` exists, and `STATE_TRANSITIONED` iff status changes, each once. Any inconsistency rolls back. It then performs:

```text
BEGIN IMMEDIATE
→ read current case revisions
→ if current evidence_revision differs from expected, raise DiagnosisInputStale
→ look up existing unique diagnosis key; if present, return REPLAY
→ CAS-check case_revision and require EVIDENCE_READY
→ insert diagnosis snapshot
→ insert hypotheses
→ insert every same-case hypothesis_evidence_ref
→ CAS update case status/current_diagnosis_id/case_revision
→ insert audit events
→ COMMIT
```

If the unique key appeared during a same-input race, load and return it even though the first diagnosis legitimately increased `case_revision`. If `evidence_revision` changed at any point, raise `DiagnosisInputStale`; do not replay or retry with the old draft. Any other unexpected `case_revision` change raises `ConcurrentCaseWrite`. Never execute rule evaluation from this method.

- [ ] **Step 4: Run all repository tests and schema integrity checks**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repository -q
.\.venv\Scripts\python.exe -m ruff check src/oceanpilot/adapters/persistence tests/repository
.\.venv\Scripts\python.exe -m compileall -q src tests/repository
```

Expected: all pass; no test uses ordinary `:memory:`; hypothesis refs cannot cross cases.

- [ ] **Step 5: Commit diagnosis persistence and stop for Gate 2 review**

```powershell
git add -- src/oceanpilot/adapters/persistence/sqlite.py tests/repository
git diff --cached --check
git commit -m "feat: add diagnosis snapshot CAS persistence"
git status --short
```

Expected: clean status. Send SHA and repository test output to total control; do not start CaseService/API until Task 10 records PASS.

---

### Task 10: Gate 2 Independent Persistence and Concurrency Review

**Owner:** 总控轨

**Files:**
- Create on PASS: `docs/reviews/gate-2-persistence.md`
- Read only: `src/oceanpilot/adapters/persistence/**`, `tests/repository/**`

**Interfaces:**
- Produces: evidence that transaction boundaries, CAS, deduplication, and foreign keys match the approved design.
- Consumes: the clean Task 9 commit.

- [ ] **Step 1: Verify clean ownership and inspect every SQL write path**

```powershell
git status --short
git log -1 --oneline
rg -n "sqlite3\.connect|BEGIN|COMMIT|ROLLBACK|executescript|UPDATE evidence_items|DELETE FROM evidence_items|save_case" src/oceanpilot
```

Expected: one connection factory; `executescript` only in schema initialization; no Evidence UPDATE/DELETE; no generic save.

- [ ] **Step 2: Run the complete Gate 2 commands**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repository -q
.\.venv\Scripts\python.exe -m ruff check src tests/repository
.\.venv\Scripts\python.exe -m compileall -q src tests/repository
git diff --check
```

Expected: all commands exit `0`.

- [ ] **Step 3: Manually audit six failure boundaries**

Confirm with code plus test names: PRAGMA before transaction; all repositories share the session connection; no network/rules inside write transaction; audit failure rolls back aggregate writes; diagnosis stale input is not swallowed; unique diagnosis race replays one snapshot. Also verify every test path uses `tmp_path` and no `.db-wal`/`.db-shm` artifact remains.

- [ ] **Step 4: Record the Gate 2 report or block**

On PASS, create `docs/reviews/gate-2-persistence.md` via `apply_patch` with actual commit SHA, commands/results, schema/transaction findings, test count, limitations, verdict `PASS`, and “Gate 3 application/API work is now allowed.” On any missing proof, report the exact file and line and keep Gate 2 closed.

- [ ] **Step 5: Commit the report and release the technical write window**

```powershell
git add -- docs/reviews/gate-2-persistence.md
git diff --cached --check
git commit -m "docs: record Gate 2 persistence review"
git status --short
```

Expected: clean status. Notify the technical track that Task 11 may begin.

---

### Task 11: Implement CaseService Command Orchestration

**Owner:** Python 技术轨

**Files:**
- Create: `src/oceanpilot/application/case_service.py`
- Create: `tests/domain/test_case_service.py`
- Create: `tests/domain/test_diagnose_service.py`

**Interfaces:**
- Produces: all four `CaseService` methods from Frozen Cross-Task Interfaces.
- Consumes: Task 5 commands/ports, Task 8–9 atomic Store, Task 3–4 domain policies.

- [ ] **Step 1: Write failing service tests with deterministic fakes**

Create a `FakeCaseStoreSession` that implements the exact port without sqlite3. Tests must assert:

```text
create starts case_revision=1 and evidence_revision=0
unsupported ONBOARDING_RECOMMENDATION raises CaseTypeNotEnabled with no Store call
create/add call assert_no_sensitive_data before persistence
new evidence recomputes ActiveEvidenceView and Readiness before atomic append
adding integration.type=PLUGIN to a ready DIAGNOSED/HUMAN_REVIEW snapshot yields NEED_INFO, supersedes the snapshot, clears the current pointer, and emits DIAGNOSIS_SUPERSEDED plus the actual STATE_TRANSITIONED
ConcurrentCaseWrite reloads and recomputes within the same Store session, at most three attempts
same evidence replay preserves revisions and audit count
diagnose NEED_INFO raises CaseNotReady(case_id=case_id, missing_fields=lexical_missing_fields, current_revision=current_case_revision) before engine evaluation; derived symptom.signal is preserved
existing diagnosis unique key replays before engine evaluation
new diagnosis evaluates outside Store transaction and materializes stable UUID/time fields
DiagnosisInputStale is returned, not silently recalculated from newer evidence
HTTP-style MERCHANT/USER_REPORTED origin and internal SYNTHETIC_ADAPTER/SYNTHETIC_TEST origin are both preserved exactly; callers cannot mutate nested EvidenceCreate after command construction
```

Use a fixed aware UTC clock and a deterministic UUID iterator. Verify UUID call count so replay paths do not consume IDs or create audit records.

- [ ] **Step 2: Run service tests and confirm CaseService is absent**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/domain/test_case_service.py tests/domain/test_diagnose_service.py -q
```

Expected: import/collection failure for `case_service.py`.

- [ ] **Step 3: Implement one-connection command flows and no hidden domain logic**

Every public method opens exactly one session:

```python
with self._store_factory() as store:
    # all loads and atomic writes for this command use this store
```

`create_case()` performs: validate enabled case type and synthetic flag → scan strings → build an empty ActiveEvidenceView → compute readiness and creation status → instantiate the case with revisions `1/0` plus that readiness/status → build one `CASE_CREATED` audit → `create_case_atomic()`.

`add_evidence()` performs, within the same session and at most three CAS attempts:

```text
load current CaseInputSnapshot
→ construct the EvidenceItem from command.evidence plus the server-created command.origin
→ append to the snapshot in memory
→ rebuild ActiveEvidenceView and Readiness
→ compute target status with status_after_evidence
→ build audit(s), including snapshot invalidation when reopening
→ append_evidence_atomic with expected revisions
```

On `ConcurrentCaseWrite`, reload and recompute; after three failed CAS attempts raise the stable error. Evidence replay/conflict outcomes come from the Store and are never converted to a new write.

`diagnose()` performs in this order:

```text
load CaseInputSnapshot
→ if current state is DIAGNOSED/HUMAN_REVIEW, find same-version snapshot and replay
→ require EVIDENCE_READY; otherwise raise CaseNotReady(case_id=snapshot.case.case_id, missing_fields=snapshot.case.readiness.missing_fields, current_revision=snapshot.case.case_revision)
→ find same unique diagnosis key and replay if present
→ build ActiveEvidenceView
→ evaluate RuleDiagnosisEngine outside any transaction
→ inject diagnosis/hypothesis/event UUIDv4 and clock values
→ commit_diagnosis_atomic with original revisions
```

The service must not catch `DiagnosisInputStale`. A unique-key race returned as `REPLAY` is safe; an evidence revision change is not.

Audit event types are closed for the MVP: `CASE_CREATED`, `EVIDENCE_ADDED`, `DIAGNOSIS_SUPERSEDED`, `DIAGNOSIS_CREATED`, `ROUTING_PROPOSED`, and `STATE_TRANSITIONED`. A new evidence command always emits `EVIDENCE_ADDED`; reopening emits `DIAGNOSIS_SUPERSEDED`; any actual state change emits `STATE_TRANSITIONED`. A new diagnosis emits `DIAGNOSIS_CREATED`, plus `ROUTING_PROPOSED` only when a route exists, plus `STATE_TRANSITIONED`. Replays emit no events. All events use the command's `request_id/trace_id`, new server UUIDv4, post-command revisions, safe reason codes, and sanitized metadata only.

- [ ] **Step 4: Verify orchestration and all pre-API tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/domain/test_case_service.py tests/domain/test_diagnose_service.py -q
.\.venv\Scripts\python.exe -m pytest tests/domain tests/repository -q
.\.venv\Scripts\python.exe -m ruff check src tests/domain tests/repository
```

Expected: all pass; fake-store call order proves rule evaluation occurs before `commit_diagnosis_atomic` begins its transaction.

- [ ] **Step 5: Commit the application service**

```powershell
git add -- src/oceanpilot/application/case_service.py tests/domain
git diff --cached --check
git commit -m "feat: orchestrate evidence case commands"
```

---

### Task 12: Add Settings, Lifespan, Request Context, Safe Errors, and Health

**Owner:** Python 技术轨

**Files:**
- Create: `src/oceanpilot/config.py`
- Create: `src/oceanpilot/api/schemas.py`
- Create: `src/oceanpilot/api/errors.py`
- Create: `src/oceanpilot/api/dependencies.py`
- Create: `src/oceanpilot/api/health.py`
- Create: `src/oceanpilot/main.py`
- Create: `tests/api/test_lifespan.py`
- Create: `tests/api/test_health.py`
- Create: `tests/api/test_problem_details.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces: `Settings`, `RequestContext`, `ProblemDetails`, `register_exception_handlers`, `create_app`, `/health`.
- Consumes: Task 7 Store factory and Task 11 CaseService.

`api/dependencies.py` freezes three dependency functions: `get_request_context(request) -> RequestContext`, `get_store_factory(request) -> CaseStoreFactory`, and `get_case_service(request) -> CaseService`. Health depends on `get_store_factory`; case routes depend on `get_case_service`. Tests override those functions directly and clear overrides in `finally`.

- [ ] **Step 1: Write failing lifespan and error-contract tests**

The fixtures must be complete, function-scoped, and must not initialize SQLite merely by constructing a service. Add these imports and fixtures to `tests/conftest.py`:

```python
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from oceanpilot.adapters.diagnosis.rules import RuleDiagnosisEngine
from oceanpilot.adapters.persistence.sqlite import SqliteCaseStoreFactory
from oceanpilot.api.dependencies import get_case_service
from oceanpilot.application.case_service import CaseService
from oceanpilot.config import Settings
from oceanpilot.main import create_app


@pytest.fixture
def settings(db_path) -> Settings:
    return Settings(db_path=db_path)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def case_service(settings: Settings) -> CaseService:
    return CaseService(
        SqliteCaseStoreFactory(settings.db_path),
        RuleDiagnosisEngine(),
        clock=lambda: datetime(2026, 7, 18, 4, 0, tzinfo=UTC),
        uuid_factory=lambda: str(uuid4()),
        policy_version=settings.policy_version,
        engine_version=settings.engine_version,
    )


@pytest.fixture
def client(app: FastAPI, case_service: CaseService) -> Iterator[TestClient]:
    assert not app.state.settings.db_path.exists()
    app.dependency_overrides[get_case_service] = lambda: case_service
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
```

Required tests:

```text
DB file/schema do not exist before entering TestClient and exist inside lifespan
foreign_keys self-check runs during startup
GET /health returns 200 {"status":"ok"}
after successful startup, monkeypatched real sqlite3.connect OperationalError with a sentinel is mapped through the real Store factory to safe 503 DATABASE_UNAVAILABLE with no sentinel
unknown path 404 and POST /health 405 are application/problem+json
405 preserves only the standards-required Allow header while still replacing the body with safe ProblemDetails
a test-only route raising RuntimeError returns safe 500 without exception text
SensitiveDataRejected maps to 422 SENSITIVE_DATA_REJECTED, never 500
every error has type,title,status,detail,instance,code,trace_id
CaseNotReady serializes exactly the whitelisted extensions case_id, missing_fields, and current_revision; no other error includes them and no handler exposes exception __dict__, args, private, or arbitrary attributes
body status equals HTTP status and X-Trace-ID equals body trace_id
overrides are empty after fixture exit, including a failing test path
```

For the 500 test, add a route only to that test-created app instance; do not add a production debug endpoint.

- [ ] **Step 2: Run tests and confirm app modules are absent**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_lifespan.py tests/api/test_health.py tests/api/test_problem_details.py -q
```

Expected: imports fail for `oceanpilot.main` or API modules.

- [ ] **Step 3: Implement local Settings, lifespan, trace middleware, and safe handlers**

`Settings` is a frozen standard-library dataclass, avoiding `pydantic-settings`:

```python
@dataclass(frozen=True, slots=True)
class Settings:
    db_path: Path
    host: str = "127.0.0.1"
    policy_version: str = "POLICY_V1"
    engine_version: str = "RULES_V1"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(db_path=Path(os.getenv("OCEANPILOT_DB_PATH", "work/oceanpilot.db")))
```

`RequestContext` contains server-generated UUIDv4 `trace_id` and `request_id`. HTTP middleware creates both, stores the context in `request.state`, records duration/result without reading the request body, and sets `X-Trace-ID` on successful and ordinarily handled responses. Every Problem Details handler also explicitly reads the same context and sets `headers={"X-Trace-ID": trace_id}`; this is mandatory for the unexpected-500 path because Starlette's outer `ServerErrorMiddleware` can otherwise return the exception handler response without the function-middleware header mutation.

`ProblemDetails` declares the common required fields plus optional strict extensions `case_id: UUID4Str | None`, `missing_fields: tuple[StrictStr, ...] | None`, and `current_revision: Revision | None`. Those three properties appear in its JSON Schema but are not required. Handlers always serialize with `exclude_none=True`: ordinary problems omit them, while only `CASE_NOT_READY` sets all three. This keeps the runtime response and shared OpenAPI schema aligned without allowing arbitrary extension dictionaries.

`create_app(settings: Settings | None = None) -> FastAPI` builds a new app each call, immediately assigns `app.state.settings` and the factory objects without opening a connection, and lets lifespan own initialization. Its `asynccontextmanager` lifespan calls `initialize_schema()`, opens a Store session, performs read-only `healthcheck()`, closes it, and then yields. A startup self-check failure aborts startup before the app listens; `/health` maps a database failure occurring after successful startup to safe 503. The 503 adapter test therefore starts with a valid DB, enters `TestClient`, then monkeypatches `sqlite3.connect` to raise `OperationalError("DB-SENTINEL")` while leaving the real `get_store_factory` dependency in place; `/health` must return 503 `DATABASE_UNAVAILABLE` without the sentinel. A separate dependency-override test may still prove override cleanup. The app registers only `health` at this task; case routes arrive in Task 13. It must contain no `@on_event` and no import-time DB access.

`RequestValidationError` conversion iterates `exc.errors()` but copies only mapped `type` values and a sanitized location. Client-controlled unknown keys must never be converted with `str(part)`:

```python
KNOWN_LOCATION_SEGMENTS = frozenset({
    "body", "path", "query", "case_id", "case_type", "summary", "merchant_ref",
    "synthetic", "evidence_id", "evidence_code", "availability", "typed_value",
    "observed_at", "source_ref",
})


def safe_error_location(error: Mapping[str, object]) -> str:
    if error.get("type") == "extra_forbidden":
        return "body.<extra>"
    safe_parts: list[str] = []
    for part in error.get("loc", ()):
        if isinstance(part, int):
            safe_parts.append(str(part))
        elif part in KNOWN_LOCATION_SEGMENTS:
            safe_parts.append(part)
        else:
            safe_parts.append("<field>")
    return ".".join(safe_parts)


for error in exc.errors():
    reason = SAFE_VALIDATION_REASONS.get(error.get("type"), "invalid_value")
    safe_errors.append({"field": safe_error_location(error), "reason": reason})
```

It never copies `msg`, `input`, `ctx`, `url`, a client-controlled unknown location segment, or the original error mapping. Tests use Bearer/password sentinels as unknown field names and nested keys and assert neither appears. Handlers are registered for `RequestValidationError`, `SensitiveDataRejected` (exactly HTTP 422 and code `SENSITIVE_DATA_REJECTED`), stable application/domain errors, Starlette `HTTPException`, and unexpected `Exception`. The `CaseNotReady` handler reads only its three declared properties and emits exactly `case_id`, `missing_fields`, and `current_revision` as extensions; it never serializes `exception.__dict__`, `args`, private fields, or arbitrary attributes. All other error types omit these extensions, and the approved detail remains fixed. The HTTPException handler may copy only a syntactically safe `Allow` header for 405; it drops all other upstream headers unless separately specified by the contract. No handler uses `str(exc)` in body or logs. Every response explicitly sets `media_type="application/problem+json"` and the matching `X-Trace-ID`; tests assert body/header identity separately for 404, 405, 422, 500, and 503.

- [ ] **Step 4: Verify lifecycle and all 404/405/500/503 paths**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_lifespan.py tests/api/test_health.py tests/api/test_problem_details.py -q
.\.venv\Scripts\python.exe -m ruff check src tests/api tests/conftest.py
```

Expected: all pass; 500 is observed because `raise_server_exceptions=False`; no response contains the injected exception sentinel.

- [ ] **Step 5: Commit the API foundation**

```powershell
git add -- src/oceanpilot/config.py src/oceanpilot/main.py src/oceanpilot/api tests/conftest.py tests/api
git diff --cached --check
git commit -m "feat: add safe FastAPI lifecycle and errors"
```

---

### Task 13: Expose the Four Case Routes and OpenAPI Contract

**Owner:** Python 技术轨

**Files:**
- Create: `src/oceanpilot/api/cases.py`
- Modify: `src/oceanpilot/api/schemas.py`
- Modify: `src/oceanpilot/api/health.py`
- Modify: `src/oceanpilot/main.py`
- Create: `tests/api/test_cases_api.py`
- Create: `tests/api/test_evidence_api.py`
- Create: `tests/api/test_diagnose_api.py`
- Create: `tests/api/test_openapi.py`

**Interfaces:**
- Produces: POST/GET cases, POST evidence, POST diagnose; exact 201/200 replay semantics.
- Consumes: Task 11 CaseService and Task 12 error/context dependencies.

- [ ] **Step 1: Write failing endpoint and OpenAPI tests**

Request models accept only:

```text
CreateCaseRequest: case_type, summary, merchant_ref, synthetic
EvidenceCreateRequest: evidence_id, evidence_code, availability,
                       typed_value, observed_at, source_ref
DiagnoseCaseRequest: optional empty object only; no body is accepted
```

Tests must cover:

```text
POST /api/v1/cases → 201 + Location + case_revision=1/evidence_revision=0
GET /api/v1/cases/{uuid4} → 200; missing valid UUID → 404
invalid/non-v4 path ID → 422 without raw input
first evidence → 201; same normalized UUID/content → 200; same ID/different content → 409
valid RFC3339 `observed_at` and `transaction.occurred_at.typed_value` strings are accepted
naive datetime strings and numeric Unix timestamps are 422 with no raw value echoed
synthetic=true is accepted; synthetic=1, false, and "true" are each 422
each card/token/password sentinel is 422 SENSITIVE_DATA_REJECTED with body/header trace identity and no sentinel echo
diagnosis creation → 201; same input/policy replay → 200
diagnose with no body succeeds; any body field is 422 and its name/value is not echoed
NEED_INFO diagnosis → 409 CASE_NOT_READY with exactly case_id, lexically ordered missing_fields, and current_revision equal to case_revision; derived symptom.signal is preserved and no exception-internal field is exposed
stale diagnosis → 409 DIAGNOSIS_INPUT_STALE
ONBOARDING_RECOMMENDATION → 409 CASE_TYPE_NOT_ENABLED
unknown fields/source reliability/client status/versions/routes are rejected with 422
OpenAPI contains exactly the five approved application paths and no delete/patch/refund/retry route
OpenAPI documents evidence/diagnose 200 replay and 201 creation separately
OpenAPI documents create 201 Location header
OpenAPI ProblemDetails schema contains optional, non-required case_id/missing_fields/current_revision properties, and the runtime diagnose 409 sets all three
every documented 422, business 404/409, and health/storage 503 uses only application/problem+json with the ProblemDetails schema, not FastAPI's default application/json HTTPValidationError
```

- [ ] **Step 2: Run endpoint tests and confirm routes are missing**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_cases_api.py tests/api/test_evidence_api.py tests/api/test_diagnose_api.py tests/api/test_openapi.py -q
```

Expected: approved case paths return 404 or route imports fail.

- [ ] **Step 3: Implement strict DTO mapping and synchronous route functions**

All DTOs use the safe BaseModel configuration. `CreateCaseRequest.synthetic` uses the shared `SyntheticTrue` (`StrictBool` plus pure `require_true` after validator), not `Literal[True]`, because Pydantic accepts integer `1` for a plain literal. `EvidenceCreateRequest.evidence_id` uses the shared UUID4 normalizer; source fields are absent. Its JSON `observed_at` is `StrictStr | None`, and `typed_value` is `StrictStr | StrictBool | None`. A pure `parse_rfc3339()` first requires `YYYY-MM-DDTHH:MM:SS[.fraction](Z|±HH:MM)`, then uses `datetime.fromisoformat(value.replace("Z", "+00:00"))`, and rejects a missing timezone. `to_command()` applies it to `observed_at` and, only for `transaction.occurred_at`, to `typed_value` before building frozen `EvidenceCreate`. Numeric Unix timestamps and naive strings are rejected. Model-level after validation calls `assert_no_sensitive_data()` on safe dumps.

`EvidenceCreateRequest.to_command()` constructs `EvidenceOrigin(source_type=MERCHANT, source_reliability=USER_REPORTED, synthetic=True)` itself and places it in `AddEvidenceCommand`; there are no origin/source-quality request fields. The internal synthetic adapter will use the same application command with `SYNTHETIC_ADAPTER/SYNTHETIC_TEST`, without adding an HTTP endpoint. `DiagnoseCaseRequest` is an empty safe DTO with `extra="forbid"`; the diagnose route accepts `Annotated[DiagnoseCaseRequest | None, Body()] = None`, so an absent body (or `{}`) is valid but `{"policy_version":"evil"}` and every other nonempty object is 422 rather than silently ignored.

Routes are normal synchronous functions:

```python
@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CreateCaseRequest,
    response: Response,
    service: Annotated[CaseService, Depends(get_case_service)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> CaseResponse:
    result = service.create_case(payload.to_command(context))
    response.headers["Location"] = f"/api/v1/cases/{result.value.case.case_id}"
    return CaseResponse.from_view(result.value)
```

Evidence and diagnose routes set `response.status_code` to `201` for `CREATED` and `200` for `REPLAY`. API functions never call `assess_readiness`, rules, sqlite3, revision setters, or route selection. Register the router with prefix `/api/v1/cases` from `create_app()`.

Freeze reusable OpenAPI response dictionaries in `api/schemas.py`. `PROBLEM_RESPONSE` contains only `content: {"application/problem+json": {"schema": ProblemDetails.model_json_schema()}}`; each case route explicitly overrides 422 and its applicable 404/409/503 entries, and `/health` documents its 503, so FastAPI's default `application/json/HTTPValidationError` is absent. Evidence and diagnose decorators additionally document 200 with their response model while their declared status remains 201. Create's 201 response documents a required string `Location` header. `tests/api/test_openapi.py` inspects the generated document's status keys, media-type keys, schemas, and header—not only its path names.

Response schema includes case identity/status/revisions/synthetic/timestamps/readiness, evidence list, and optional current diagnosis. Diagnosis response includes immutable hypotheses, evidence refs, confidence, route/ticket draft, review reasons, versions, and lifecycle.

- [ ] **Step 4: Verify all HTTP semantics and OpenAPI exclusions**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api -q
.\.venv\Scripts\python.exe -m ruff check src tests/api
.\.venv\Scripts\python.exe -c "from oceanpilot.main import create_app; print(sorted(create_app().openapi()['paths']))"
```

Expected paths exactly: `/health`, `/api/v1/cases`, `/api/v1/cases/{case_id}`, `/api/v1/cases/{case_id}/evidence`, `/api/v1/cases/{case_id}/diagnose`.

- [ ] **Step 5: Commit the complete API chain and stop for the API checkpoint**

```powershell
git add -- src/oceanpilot/api src/oceanpilot/main.py tests/api
git diff --cached --check
git commit -m "feat: expose payment incident case API"
git status --short
```

Expected: clean status. Send SHA, test output, and printed OpenAPI paths to total control; do not start the synthetic/security chain before Task 14 records a passing checkpoint.

---

### Task 14: Independent API Checkpoint Before E2E and Security Work

**Owner:** 总控轨

**Files:**
- Create on PASS: `docs/reviews/checkpoint-api.md`
- Read only: `src/oceanpilot/{main.py,api/**,application/case_service.py}`, `tests/api/**`

**Interfaces:**
- Produces: an intermediate API checkpoint; it does **not** declare formal Gate 3 PASS because the approved Gate also requires synthetic E2E, security sentinels, and audit review.
- Consumes: the clean Task 13 commit.

- [ ] **Step 1: Run the API checkpoint suite**

```powershell
git status --short
.\.venv\Scripts\python.exe -m pytest tests/domain tests/repository tests/api -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
```

Expected: clean status and all commands exit `0`.

- [ ] **Step 2: Perform adversarial API probes**

With `TestClient(app, raise_server_exceptions=False)`, independently probe: unknown route, wrong method, invalid UUID, unknown body field, sensitive card/token/password sentinels, disabled case type, missing case, evidence replay/conflict, not-ready diagnosis, forced unexpected exception, and unavailable DB. Assert every 4xx/5xx is `application/problem+json`, body/HTTP status match, `X-Trace-ID` equals the body trace ID (including 500), and no sentinel/SQL/exception text is present. Every sensitive sentinel must be exactly 422 with code `SENSITIVE_DATA_REJECTED`.

- [ ] **Step 3: Audit API thinness and actual OpenAPI**

```powershell
rg -n "assess_readiness|evaluate\(|sqlite3|case_revision\s*[+=]|responsible_team\s*=" src/oceanpilot/api
.\.venv\Scripts\python.exe -c "from oceanpilot.main import create_app; print('\n'.join(sorted(create_app().openapi()['paths'])))"
```

Expected: `rg` has no domain/storage logic matches; exactly five paths print. Inspect that `with TestClient(app)` is used, overrides clear in `finally`, and 500 tests set `raise_server_exceptions=False`.

- [ ] **Step 4: Record PASS or blocking findings**

On PASS, create `docs/reviews/checkpoint-api.md` via `apply_patch` with reviewed SHA, commands and actual outputs, adversarial cases, OpenAPI paths, limitations, verdict `PASS_CHECKPOINT`, and “Tasks 15–16 synthetic/security work is allowed; formal Gate 3 remains closed.” If any handler leaks `input`, `ctx`, exception text, raw errors, or omits the trace header on 500, stop the technical track.

- [ ] **Step 5: Commit the checkpoint and release the technical writer**

```powershell
git add -- docs/reviews/checkpoint-api.md
git diff --cached --check
git commit -m "docs: record API safety checkpoint"
git status --short
```

---

### Task 15: Add Closed Synthetic Scenarios and the Two Honest E2E Paths

**Owner:** Python 技术轨

**Files:**
- Create: `src/oceanpilot/adapters/evidence/synthetic.py`
- Create: `tests/api/test_three_synthetic_cases.py`
- Create: `examples/demo.ps1`

**Interfaces:**
- Produces: repeatable three-scenario/four-rule evidence fixtures, an internal `SYNTHETIC_TEST` service path, and a public HTTP `USER_REPORTED` demo whose different confidence outcomes are explicit.
- Consumes: the approved API and the `AddEvidenceCommand.origin` boundary; it does not add or implement an `EvidenceSource` application protocol.

- [ ] **Step 1: Write failing internal-service and HTTP end-to-end tests**

The three scenario groups are:

```text
3DS/authentication or callback incomplete → THREEDS_INCOMPLETE_V1
risk decline → RISK_DECLINE_V1
configuration mismatch → CONFIG_MISMATCH_MERCHANT_V1 and CONFIG_MISMATCH_PSP_V1 subcases
```

Every case performs `create → add all core and rule evidence → diagnose → inspect route/ticket/audit`. Parameterize four scenario subcases while reporting three business groups. The internal test pairs each `EvidenceCreate` returned by the synthetic adapter with the adapter's fixed `EvidenceOrigin(SYNTHETIC_ADAPTER, SYNTHETIC_TEST, true)`, builds `AddEvidenceCommand`, and calls `CaseService`; complete consistent evidence scores `0.94`, non-risk cases become `DIAGNOSED`, and risk remains `HUMAN_REVIEW/RISK_DECISION`. The HTTP test posts the same facts without origin fields; the API mapper fixes them to `MERCHANT/USER_REPORTED`, so matched cases retain their route/ticket suggestion but are `HUMAN_REVIEW` with `LOW_CONFIDENCE` and `INSUFFICIENT_SOURCE_QUALITY` (risk also has `RISK_DECISION`).

Both paths assert every hypothesis references the decisive evidence IDs; the parent `DiagnosisSnapshot`, explicit `TicketDraft`, and audit events have `synthetic=true`; every hypothesis/route belongs to that same synthetic parent snapshot; audit revisions/transitions match; and no unlisted rule appears. `Hypothesis` and `RoutingDecision` intentionally have no duplicate synthetic field. This prevents the internal `0.94` claim from being inferred from an HTTP path that can only produce `0.865` raw score.

- [ ] **Step 2: Run tests and confirm the synthetic adapter is missing**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_three_synthetic_cases.py -q
```

Expected: adapter import failure or missing scenario assertions.

- [ ] **Step 3: Implement the adapter and an explicitly HTTP-only demo**

`SyntheticScenario` is a closed enum local to `adapters/evidence/synthetic.py` with `THREEDS_INCOMPLETE`, `RISK_DECLINE`, `CONFIG_MERCHANT`, and `CONFIG_PSP`; no inward layer imports it. `SyntheticEvidenceSource.origin` is the fixed frozen `SYNTHETIC_ADAPTER/SYNTHETIC_TEST/true` object. `load(scenario)` returns complete frozen `EvidenceCreate` tuples with deterministic field codes/values and no real identifiers. It never calls a network service, writes the Store directly, or registers an HTTP endpoint; the E2E helper passes its output through `CaseService.add_evidence()`.

`examples/demo.ps1` assumes the local API is running, uses `$oceanBaseUrl = "http://127.0.0.1:8000"`, generates UUIDv4 values with `[guid]::NewGuid()`, creates the three scenario groups, prints status/readiness/rule IDs/review reasons/route/ticket, and prints this banner first:

```text
SYNTHETIC LOCAL DEMO — no Oceanpayment or Feishu connection; no payment action is executed.
```

The next line states `HTTP demo origin: MERCHANT / USER_REPORTED; expected review score 0.87, not the internal 0.94 fixture.` The script must never claim to exercise the internal adapter.

- [ ] **Step 4: Verify both E2E expectations and capture the HTTP demo**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
```

Expected: every command exits `0`; capture exact test counts and durations. Then start locally only on loopback:

```powershell
$env:OCEANPILOT_DB_PATH = "$PWD\work\demo.db"
.\.venv\Scripts\python.exe -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8000
```

In a second PowerShell, run `examples\demo.ps1`; capture output for the total-control task. Do not commit `work/demo.db` or logs.

- [ ] **Step 5: Commit only synthetic E2E and demo files**

```powershell
git add -- src/oceanpilot/adapters/evidence/synthetic.py tests/api/test_three_synthetic_cases.py examples/demo.ps1
git diff --cached --check
git commit -m "test: add honest synthetic end-to-end scenarios"
git status --short
```

Expected: clean status. Send SHA, exact commands/results, both path outcomes, demo output, and known limitations to total control. Do not create or push a GitHub remote.

---

### Task 16: Add Five-Surface Security Regression and Minimal Python 3.12 CI

**Owner:** Python 技术轨

**Files:**
- Create: `tests/security/test_no_sensitive_data_leak.py`
- Create: `.github/workflows/ci.yml`
- Modify only if a test proves a defect: the narrow production file responsible for that defect

**Interfaces:**
- Produces: distinct sentinel rejection proof across five output surfaces and a minimal clean-machine CI contract.
- Consumes: Tasks 12–15 complete runtime; does not add product capability.

- [ ] **Step 1: Write failing five-surface sentinel and trace tests**

Send distinct synthetic sentinels through API, CaseService, and Store boundaries: a Luhn-valid test number, `cvv=123`, a Bearer token, an API-key assignment, and a password assignment. Also place separate sentinels in an unknown top-level JSON field name and a nested unknown key. Scan exact sentinel bytes/strings across:

```text
HTTP response bodies
captured application logs
audit_events rows
SQLite database bytes
serialized test snapshots
```

For every API sentinel assert `422`, code `SENSITIVE_DATA_REJECTED` when the sensitive scanner triggered (or safe `VALIDATION_ERROR` for an unknown-key-only case), `application/problem+json`, `X-Trace-ID == body.trace_id`, and no original field name/value. Domain/Store failures use the single safe message and leave business/audit row counts unchanged.

- [ ] **Step 2: Run the focused tests and record the actual baseline**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/security/test_no_sensitive_data_leak.py -q
```

Expected: record the actual result. If every assertion is already green because Tasks 2/8/12 implemented the boundaries, keep the suite as a characterization/regression lock and do not edit production. If a precise boundary assertion fails, retain that red proof and do not weaken a sentinel or scan.

- [ ] **Step 3: Apply only proven hardening and add minimal CI**

If a test exposes a leak, fix only the responsible scanner, mapper, handler, log record, or repository pre-write check and add the exact regression. Validation-error location conversion must map only known DTO field names and integer indexes; an `extra_forbidden` segment is rendered as the constant `<extra>`, never `str(client_key)`. Create `.github/workflows/ci.yml`:

```yaml
name: ci
on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: python -m pip install -e ".[dev]"
      - run: python -m ruff check src tests
      - run: python -m compileall -q src tests
      - run: python -m pytest -q
```

Do not add unverified coverage, security, build, production, or deployment badges.

- [ ] **Step 4: Run the complete technical Gate 3 candidate suite**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/domain -q
.\.venv\Scripts\python.exe -m pytest tests/repository -q
.\.venv\Scripts\python.exe -m pytest tests/api -q
.\.venv\Scripts\python.exe -m pytest tests/security -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
```

Expected: every command exits `0`; capture exact test counts and durations. Inspect the CI YAML rather than claiming a remote CI run before publication.

- [ ] **Step 5: Commit the security/CI evidence and close technical writes**

```powershell
git add -- tests/security .github/workflows/ci.yml src
git diff --cached --check
git diff --cached --stat
git commit -m "test: add five-surface security regression"
git status --short
```

Expected: clean status. Send SHA and actual results to total control; formal Gate 3 remains closed until Task 17 independently reviews E2E, security, OpenAPI, and audit rows.

---

### Task 17: Gate 3 Independent API, E2E, Security, and Audit Review

**Owner:** 总控轨

**Files:**
- Create on PASS: `docs/reviews/gate-3-api-main-chain.md`
- Read only: `src/**`, `tests/**`, `examples/demo.ps1`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: the formal Gate 3 verdict required by approved spec §12.
- Consumes: clean Task 16 commit plus the earlier API checkpoint; no technical implementation edits are allowed during this review window.

- [ ] **Step 1: Run every Gate 3 proof from a clean tree**

```powershell
git status --short
git log -1 --oneline
.\.venv\Scripts\python.exe -m pytest tests/domain tests/repository tests/api tests/security -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
```

Expected: clean tree and all commands exit `0`; record exact test count and timing.

- [ ] **Step 2: Independently replay the three scenario groups and inspect audit rows**

Run the four parameterized subcases through the internal and HTTP paths. Query the six-table SQLite file read-only and verify: hypotheses reference same-case evidence; API origin is `USER_REPORTED`; internal origin is `SYNTHETIC_TEST`; all high-risk cases require human review; route/ticket are null for policy gaps/conflicts; revisions and audit events match the command sequence; no unreferenced causal conclusion exists.

- [ ] **Step 3: Repeat adversarial API, trace, OpenAPI, and claim checks**

Probe 404, 405, invalid UUID, strict synthetic boolean, valid/naive/numeric datetime, source-field injection, five sensitive sentinels (including malicious field names), 500, and 503. Every error has the RFC 9457 media type and matching body/header trace ID. Print the exact five OpenAPI paths and confirm the API layer contains no rule, sqlite3, revision, route-selection, refund, retry, or configuration mutation logic.

- [ ] **Step 4: Record PASS or blocking findings without overstating CI**

On PASS, create `docs/reviews/gate-3-api-main-chain.md` with `apply_patch`. Include reviewed SHA, commands/actual outputs, E2E matrix, audit findings, sentinel results, OpenAPI paths, limitations, and verdict `PASS`. State that local tests passed and CI is configured; do not claim GitHub Actions passed until a public run exists. Any missing evidence keeps Gate 3 closed and returns exact file/line findings to the technical track.

- [ ] **Step 5: Commit the formal Gate 3 report**

```powershell
git add -- docs/reviews/gate-3-api-main-chain.md
git diff --cached --check
git commit -m "docs: record Gate 3 main-chain review"
git status --short
```

Expected: clean status. Only a committed PASS authorizes Task 18 documentation and publication work.

---

### Task 18: Gate 4 Fact Audit, Public Documentation, Clean Reproduction, and GitHub Release

**Owner:** 总控轨

**Files:**
- Create: `README.md`
- Create: `docs/architecture.md`
- Create: `docs/demo.md`
- Modify: `docs/submission/registration-copy.md`
- Create: `docs/reviews/gate-4-release.md`
- Do not create: `LICENSE` unless the user separately authorizes a reuse license.

**Interfaces:**
- Produces: truthful public repository and paste-ready registration material.
- Consumes: all PASS gate reports through Task 17, Task 15–16 commands/results, and the already committed Task 0 registration copy.

- [ ] **Step 1: Independently rerun all release evidence before writing claims**

```powershell
git status --short
git log -1 --oneline
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
rg -n -i "sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_|AKIA[0-9A-Z]{16}|BEGIN .*PRIVATE KEY|Bearer\s+\S+|cvv\s*[:=]|password\s*[:=]|api[_-]?key\s*[:=]" . --glob "!.git/**" --glob "!.venv/**"
```

Use `importlib.metadata.metadata()` from the Python standard library to record the installed name, exact version, homepage/project URL, and declared license metadata for FastAPI, Pydantic, Uvicorn, HTTPX, pytest, and Ruff. Confirm `Test-Path LICENSE` is false and that README explicitly states no reuse license is currently granted. Expected: clean status; tests/Ruff/compile/pip-check/diff pass; dependency rows match the frozen versions; secret scan has no real-secret match. Synthetic sentinel literals required by security tests must be reviewed as fixtures, not misreported as leaks.

- [ ] **Step 2: Write README and architecture/demo documents from observed behavior**

README begins with this exact banner:

> 当前版本是使用合成数据的本地 FastAPI 原型，不接入 Oceanpayment、飞书 Agent、A2A 或 MCP，不执行任何支付及资金动作。

README must contain: problem statement; current capabilities; explicit non-capabilities; Python 3.12 installation; loopback launch; five endpoints; synthetic demo; security boundary; test commands and actual verified count; capability-status matrix; roadmap; official research sources; independent-project disclaimer; and “公开代码仅供比赛评审，当前未授予复用许可”。

Use only these status labels:

```text
已实现
合成原型
已定义契约、未实现
入围后验证
不在当前范围
```

`docs/architecture.md` contains two Mermaid diagrams: current solid-line implementation and target Feishu architecture with every future node dashed/Planned. It documents MerchantSuccessCase, Case Evidence Contract, state machine, trust boundaries, and AI/Workflow/human responsibilities.

`docs/demo.md` contains exact commands and for each step two fields: “本步骤证明” and “本步骤没有证明”. It never shows a fake Feishu interface, real Oceanpayment result, automatic dispatch, or production payment action.

- [ ] **Step 3: Revalidate the early registration text and factual status**

Do not rewrite the approved paragraphs saved in Task 0. Compare them byte-for-byte with spec §13.1/§13.2 and rerun the same count script; expected `262` and `572`. Before publication append only the intended URL `https://github.com/jiang4wqy/oceanpilot-evidenceos` and status `PENDING_PUBLIC_VERIFICATION`, with an instruction that the URL must not be pasted into the form yet. Do not call this status verified before the anonymous checks in Step 5.

Fact audit must explicitly verify:

```text
four rule IDs, three business scenario groups
0.90 score gate and 0.75 source-quality gate; no source-quality number is described as accuracy
dynamic questioning is deterministic slot policy, not implemented AI language understanding
route is a recommendation and TicketDraft is not a real ticket
Agent/A2A/MCP/payment recommendation/knowledge/dashboard are not implemented
current runtime only proposes responsible domain, priority, and TicketDraft; SLA timing, timeout escalation, notification, and real dispatch are not implemented
100% evidence-reference and high-risk-review claims are tested invariants, not business outcomes
no measured accuracy, time saving, success rate, or cost reduction claim
```

- [ ] **Step 4: Perform a clean-clone reproduction before public push**

Commit docs first:

```powershell
git add -- README.md docs/architecture.md docs/demo.md docs/submission/registration-copy.md
git diff --cached --check
git commit -m "docs: add truthful prototype documentation"
git status --short
```

Create a new temporary clone directory without deleting any existing directory:

```powershell
$oceanReleaseClone = Join-Path $env:TEMP ("oceanpilot-release-" + [guid]::NewGuid().ToString())
git clone . $oceanReleaseClone
py -3.12 -m venv (Join-Path $oceanReleaseClone ".venv")
& (Join-Path $oceanReleaseClone ".venv\Scripts\python.exe") -m pip install -e "${oceanReleaseClone}[dev]"
& (Join-Path $oceanReleaseClone ".venv\Scripts\python.exe") -m pytest -q $oceanReleaseClone
```

Expected: clean clone installs and all tests pass. Leave the temporary directory in place for evidence; do not recursively delete it during this task.

- [ ] **Step 5: Record Gate 4 and publish only after every check passes**

Create `docs/reviews/gate-4-release.md` via `apply_patch` with actual SHA, test counts/timing, clean-clone path and output, sensitive scan disposition, documentation claim audit, known limitations, and pre-publication verdict `READY_TO_PUBLISH`. Commit it:

```powershell
git add -- docs/reviews/gate-4-release.md
git diff --cached --check
git commit -m "release: record OceanPilot MVP verification"
git status --short
```

Before changing any branch or remote, perform a read-only ownership preflight:

```powershell
git remote -v
git branch --show-current
gh auth status
gh api user --jq .login
gh repo view jiang4wqy/oceanpilot-evidenceos
```

Expected: the authenticated login is `jiang4wqy` or an account explicitly authorized by the user; `origin` is absent or exactly the intended repository; and any existing repository is the intended empty target. If the account, remote, owner/name, or repository contents differ, stop. Do not overwrite, force-push, or repoint an unrelated remote. Only after this verification and a clean tree run `git branch -M main`.

If `gh repo view` reports that the repository does not exist, create the exact public repository:

```powershell
gh repo create jiang4wqy/oceanpilot-evidenceos --public --source . --remote origin --push
gh repo edit jiang4wqy/oceanpilot-evidenceos --description "Synthetic local prototype for evidence-driven cross-border payment incident collaboration"
```

If it already exists, verify exact identity and absence of every remote ref before touching `origin`:

```powershell
$expectedOrigin = "https://github.com/jiang4wqy/oceanpilot-evidenceos.git"
gh api repos/jiang4wqy/oceanpilot-evidenceos --jq '{full_name,visibility,size}'
$existingRefs = git ls-remote $expectedOrigin
if ($existingRefs) { throw "target repository is not empty" }
$actualOrigin = git remote get-url origin 2>$null
if ($LASTEXITCODE -ne 0) {
    git remote add origin $expectedOrigin
} elseif ($actualOrigin -ne $expectedOrigin) {
    throw "origin does not match the approved repository"
}
git push -u origin main
```

For a newly created repository, `gh repo create ... --remote origin --push` remains the only push command. For an existing repository, use the branch above. Stop instead of overwriting an unrelated or non-empty remote; never force-push.

After push, verify from an unauthenticated web request that both README and a source file are public:

```powershell
$readme = Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/jiang4wqy/oceanpilot-evidenceos/main/README.md"
$source = Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/jiang4wqy/oceanpilot-evidenceos/main/src/oceanpilot/main.py"
if ($readme.StatusCode -ne 200 -or $source.StatusCode -ne 200) { throw "public verification failed" }
```

Then update the Gate 4 report via `apply_patch` with the verified public URLs, timestamp, and `verified_artifact_sha` (the exact code/README commit anonymously fetched), and final verdict `PASS`. Do not write the report commit's own SHA into the report. In the registration copy change only the status marker from `PENDING_PUBLIC_VERIFICATION` to `PUBLIC_VERIFIED`; keep the 262/572 paragraphs byte-identical. Commit and push:

```powershell
git add -- docs/reviews/gate-4-release.md docs/submission/registration-copy.md
git diff --cached --check
git commit -m "release: verify public OceanPilot repository"
git push origin main
$reportCommit = git rev-parse HEAD
$remoteMain = (git ls-remote origin refs/heads/main).Split()[0]
if ($remoteMain -ne $reportCommit) { throw "remote main does not contain the verification report" }
git status --short
```

The final report identifies the artifact it tested; the post-commit `ls-remote` output proves the report commit itself was pushed without creating an impossible self-referential SHA. Only after that final push may the GitHub URL be pasted into the registration form. Do not add unverified badges, topics, releases, or license claims.

---

## Gate Stop Conditions

| Gate | Required task range | Required evidence | Stop condition |
|---|---:|---|---|
| Registration preflight | 0 | tracked approved plan, exact 262/572 copy, clean write handoff | untracked plan; count drift; future capability presented as current |
| Gate 1 | 1–6 | domain/application-contract tests, absolute and relative import boundaries, four rules, raw score math, safe errors, deterministic replay, review report | rule without all-and-only refs; inference presented as fact; synthetic or sensitive-value leak; mutable/CRUD port; forbidden import; promised path without an independent test |
| Gate 2 | 7–10 | real-file SQLite tests, rollback, FK, dedupe, CAS, concurrency, report | lost update; leaked sqlite error; non-atomic audit; cross-case ref |
| API checkpoint | 11–14 | five paths, lifespan, Problem Details, OpenAPI, adversarial review | unsafe 422/500; missing trace header; extra endpoint; override leak; API domain logic |
| Gate 3 | 11–17 | API checkpoint plus internal/HTTP E2E, audit trace, five-surface security, formal report | sentinel leak; dead synthetic path; false source/score claim; unreferenced diagnosis |
| Gate 4 | 18 | full tests, clean clone, fact audit, public verification | false capability claim; dirty tree; failed clean clone; unsafe remote target |

## Approved Spec Coverage Map

| Approved spec section | Implementation/verification task |
|---|---|
| §1–§2 product conclusion, five needs, MVP success and exclusions | Global Constraints; Tasks 0, 13, 15–18 |
| §3 originality and public-expression boundary | Task 18 README, architecture, fact audit |
| §4 current/target architecture, layering, lifecycle | Tasks 1, 5, 12, 18 |
| §5.1 versions and UUIDv4 policy | Tasks 2, 5, 7–9, 11 |
| §5.2 MerchantSuccessCase | Tasks 2, 8, 11, 13 |
| §5.3 EvidenceItem, field catalog, hash, ActiveEvidenceView | Tasks 2–3, 8, 13 |
| §5.4 ReadinessAssessment | Tasks 3, 8, 11, 13 |
| §5.5–§5.6 diagnosis, confidence, route, TicketDraft | Tasks 2, 4, 9, 11, 13, 15 |
| §5.7 future-only contracts | Task 18 labels them “已定义契约、未实现”; no runtime task |
| §6 state machine | Tasks 4, 8–9, 11 |
| §7 five endpoints and RFC 9457 | Tasks 12–14, 16–17 |
| §8 SQLite schema, transactions, dedupe and CAS | Tasks 7–10 |
| §9 four rules and AI/Workflow/human boundary | Tasks 4, 11, 15, 18 |
| §9.3 future A2A/MCP | Task 18 target architecture only; no runtime task |
| §10 validation, logging, audit and local runtime safety | Tasks 2, 7–9, 12, 16–18 |
| §11 three test layers, security and three scenario groups | Tasks 1–17 |
| §12 Gate 0–4 process | Approved spec plus Tasks 0, 6, 10, 14, 17–18 |
| §13 registration text | Task 0 saves exact approved paragraphs; Task 18 preserves them and changes the separate repository marker from pending to verified only after anonymous checks |
| §14 research basis | Task 18 official-source links and dependency disclosure |
| §15 five frozen decisions | Global Constraints and Gate Stop Conditions |

Self-review finding: all approved MVP requirements map to implementation or verification. Future Feishu/Oceanpayment capabilities map only to truthful documentation; no missing runtime task is hidden as an implementation promise.

## Plan Self-Review Checklist

- [ ] Every approved spec section maps to a task or an explicit out-of-scope constraint.
- [ ] There are exactly four rule IDs and three business scenario groups throughout this plan.
- [ ] Score gates are `0.90` and `0.75`; `SYNTHETIC_TEST=0.80` is only a source-quality mapping and is never called accuracy.
- [ ] All IDs are UUIDv4 and evidence normalization precedes hash/persistence.
- [ ] One application command uses one Store session/SQLite connection.
- [ ] Rules run outside transactions; every write uses atomic Store methods and CAS.
- [ ] No ordinary `:memory:` test, WAL, ORM, Agent framework, or real external integration is planned.
- [ ] API has exactly five approved paths and no high-risk action endpoint.
- [ ] Validation/error tests prove sensitive inputs are not echoed.
- [ ] All file ownership is exclusive and shared Git writes are serialized.
- [ ] No task delegates work by analogy or leaves error/test behavior unspecified.
- [ ] README and registration claims can be pointed to code/tests or are labeled future.

## Execution Handoff

Plan execution must begin only after this plan is approved. The recommended mode is the existing two-task arrangement: Python 技术轨 implements one technical task at a time; total control dispatches fresh independent reviewers at each Gate and owns all public claims. The alternative is inline execution by total control with `superpowers:executing-plans`, still honoring the same Gate stops and file ownership.
