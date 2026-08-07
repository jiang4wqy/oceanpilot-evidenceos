# `tests/` — 测试与门禁 / test suite & gate

约 1050+ 用例,离线确定性(不联网)。提交前必须整套 gate 全绿。

## 完整门禁(与 CI 一致)

```bash
# 建议使用项目 venv 的解释器,例如 /path/to/venv/bin
python -m pytest -p no:cacheprovider -q      # 全量单测(含 import-boundary)
ruff check src tests                          # lint
ruff format --check src tests                 # 格式
python -m compileall -q src tests             # 字节编译
```

CI 定义见 `.github/workflows/ci.yml`;每次 push 与 PR 各跑一遍(本分支有开放 PR → 每 commit 两条 CI)。

## 目录(镜像源码分层)

| 目录 | 覆盖 |
|---|---|
| `domain/` | 领域内核:`chargeback`(胜诉率门控)、`evidence_catalog`/`reason_catalog`(穷尽性)、`security`(敏感数据)。含 **`test_import_boundaries.py`**(强制依赖规则)。 |
| `agents/` | 应用层 agent 与编排:intake/evidence/assess/prevention、supervisor、理由确认、finalize、事实抽取、打包、申诉。 |
| `channels/` | 渠道无关服务 + HTTP/飞书适配器 + Delivery 时限/事实渲染。 |
| `repository/` | `SqliteChargebackCaseStore`:追加式、CAS、幂等、审计、确认/finalize 持久化。 |
| `model/` | 模型 provider(Claude 组装、本地、脚本、路由/脱敏);`test_claude_live.py` 无 key 时 skip。 |
| `api/` | 拒付路由 + OpenAPI 路径断言。 |
| `foundation/` | 基础版 API 契约 + OpenAPI 精确路径/方法集合。 |
| `ingestion/`,`knowledge/`,`security/`,`feishu/`,`e2e/` | 数据导入、银行知识库、安全、飞书回调、端到端演示。 |

## 约定与坑

- **测试模块 basename 必须唯一。** 仓库无 `tests/**/__init__.py`,pytest 默认导入模式下**重名会导致 collection 冲突**。给新文件起唯一名(例:`test_chargeback_delivery_deadline.py` 避开已有的 `test_chargeback_deadline.py`)。
- **默认离线、确定性。** 应用默认用 `ScriptedModelProvider`;真实模型需显式开关 `OCEANPILOT_CHARGEBACK_LIVE_MODEL`,因此即使环境里有 `ANTHROPIC_API_KEY`,测试仍不联网。
- **改端点必改断言。** 新增/删除路由要同步 `api/test_lifespan_openapi.py` 与 `foundation/test_foundation_api.py` 的路径集合。
- **加错误类必改契约。** 新增 `ApplicationError` 子类要同步 `domain/test_application_contracts.py`(消息字典 + 子类集合)。
- **TDD。** 先写测试,再写实现,每个切片单独过 gate。

## 只跑子集

```bash
python -m pytest -p no:cacheprovider -q tests/domain tests/agents
python -m pytest -p no:cacheprovider -q tests/repository/test_chargeback_case_store.py
```
