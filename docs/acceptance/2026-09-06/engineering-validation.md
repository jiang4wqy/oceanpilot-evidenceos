# 工程发布验证 · 2026-09-06

验证对象为 `oceanpilot-workspace` 当前待提交工作树。此记录只覆盖本轮实际运行的工程检查，不代替浏览器验收或真实模型联调记录。

## 检查结果

| 检查 | 本轮结果 |
| --- | --- |
| 全量 pytest | **1429 passed，6 skipped**；收集 1435 项，耗时 10.31 秒；运行于最后两处页面措辞调整之前 |
| 最终页面回归 | **41 passed**，耗时 2.86 秒；覆盖最终措辞调整后的页面运行时、渲染和页面 API |
| `ruff check src tests` | 通过 |
| `ruff format --check src tests` | 通过，201 个文件格式正确 |
| wheel 构建 | 最终源码重建通过，`oceanpilot_evidenceos-0.3.0-py3-none-any.whl`，315368 字节 |
| wheel 文件完整性 | 115 个 Python 模块、17 个前端资源均包含且与源文件逐字节一致；无缺失、过期前端资源或 ZIP 校验错误 |
| 待提交文件密钥模式检查 | 扫描 88 个变更或新增文本文件，0 个候选匹配；扫描仅输出路径与行号，不输出匹配内容 |
| 本地运行数据 | Git 未跟踪实际 `.env`、数据库及其 sidecar 文件；仅保留 `.env.example`。wheel 也不含 `.env` 或数据库 |

pytest 使用已有项目虚拟环境的 Python 3.12.13，命令为：

```sh
PYTHONPATH=src '/Users/luxinyu/Desktop/飞书 ai 大赛/work/oceanpilot-latest/.venv/bin/python' -m pytest -p no:cacheprovider
PYTHONPATH=src '/Users/luxinyu/Desktop/飞书 ai 大赛/work/oceanpilot-latest/.venv/bin/python' -m pytest -p no:cacheprovider tests/web tests/api/test_demo_page.py
'/Users/luxinyu/Desktop/飞书 ai 大赛/work/oceanpilot-latest/.venv/bin/ruff' check src tests
'/Users/luxinyu/Desktop/飞书 ai 大赛/work/oceanpilot-latest/.venv/bin/ruff' format --check src tests
```

六项跳过的原因如下。该测试进程没有装载模型密钥，不能将这些跳过记为真实模型调用通过。

| 跳过项 | 数量 | 原因 |
| --- | ---: | --- |
| Agent API 的 DeepSeek live 测试 | 1 | `DEEPSEEK_API_KEY` 未设置 |
| DeepSeek provider live 测试 | 2 | `DEEPSEEK_API_KEY` 未设置 |
| Claude provider live 测试 | 2 | `ANTHROPIC_API_KEY` 未设置 |
| PowerShell 演示脚本测试 | 1 | 当前运行环境没有 PowerShell |

测试产生一条 Starlette 关于 TestClient 使用 httpx 的弃用提醒，未影响测试结果；本轮未升级运行依赖。

最终仅将 `assessment.js` 与 `web_i18n.py` 中旧复核提示改为“未覆盖当前规则与材料版本，只作历史记录”，避免把缺少规则指纹的历史记录误说成数据确实发生变化。相应页面断言已同步；随后重跑 41 项页面测试与 `src tests` 的 Ruff 检查，并重新构建及核对 wheel，未重复全量 pytest。

## 构建与扫描范围

测试虚拟环境未安装 `setuptools.build_meta`，第一次构建因此失败。随后使用现有 Codex bundled runtime（Python 3.12.14、setuptools 84.0.0、wheel 0.48.0），执行 `pip wheel --no-deps --no-build-isolation --no-index`，成功在系统临时目录构建；没有下载、安装或升级依赖。

最终 wheel SHA-256：`21447a9cd6fe40b1f62f36d2ef9adee535c4ebddc69d308f13e0897e1dbba48c`。检查覆盖全部源码模块及 `.js`、`.css`、`.html`、`.data-uri` 资源，包括新增 Workspace、摘要渲染、模型 deadline、正式争议前提模块及商户疑点页面脚本；已删除的 `support.js` 未混入产物。两处最终页面措辞也已在 wheel 中确认。

密钥检查只针对 Git 待提交文本，覆盖常见供应商令牌、私钥头和长凭据字面量模式，属于有限模式扫描，不能替代完整安全审计；未读取项目外部凭据文件。

额外执行的全仓 `ruff check .` 和 `ruff format --check .` 发现一个既存问题：未参与本次业务改动的 `scripts/build_final_proposal_docx.py` 存在导入排序和格式问题。该文件保持原状，不计入已通过的 `src tests` 验收范围。

本轮没有运行浏览器交互或外网模型调用，也没有提交或推送代码。
