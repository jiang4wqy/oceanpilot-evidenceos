# DeepSeek 演示配置、模型来源与故障恢复

正式演示配置固定选择 DeepSeek；Claude 与本地 provider 保留兼容和测试能力。演示过程中不切换供应商。没有可用凭据或外网时，使用同一系统的离线合成模式。

## 本地配置

从仓库根目录复制 `.env.example` 为 `.env`。本机 `.env` 必须被 Git 忽略，只放项目授权的凭据，不把配置内容复制到终端输出、聊天、文档或截图。

```dotenv
OCEANPILOT_CHARGEBACK_LIVE_MODEL=1
OCEANPILOT_MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

在本机编辑器填写 `DEEPSEEK_API_KEY`。若旧密钥已经泄露，先撤销并替换；不要写入源码。

安装并启动（macOS/Linux）：

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m uvicorn oceanpilot.main:create_app --factory \
  --env-file .env --host 127.0.0.1 --port 8002
```

Windows 使用 `.venv\Scripts\python.exe`；PowerShell 换行使用反引号。打开 `http://127.0.0.1:8002/demo`。

应用代码和普通测试不会自动加载 `.env`。设置为实时模式但选定供应商没有凭据时，系统使用离线模式，不能显示成实时成功。

## 区分配置和实际结果

运行时配置只说明选定供应商。本次结果另有实际来源：

| 实际结果 | `source` | `offline` | `failure_code` |
| --- | --- | --- | --- |
| 模型请求成功且结构、动作通过校验 | `MODEL` | `false` | 空 |
| 明确离线的确定性说明，无模型请求 | `DETERMINISTIC` | `true` | 空 |
| 实时调用或输出校验失败后的确定性说明 | `FALLBACK` | `false` | 固定故障代码 |

普通案件读取和材料预览也使用确定性规则，不调用模型。模型异常后会保留可操作的确定性结果，但这不能被记录为实时模型成功。历史分析回放保留原分析的来源。

## 超时、并发与重试合同

- 每次模型调用最多等待 **12秒**。
- 同一业务请求内顺序进行的模型调用共享 **20秒**预算，后续调用只能使用剩余时间。
- DeepSeek HTTP路径不自动重试；Claude兼容SDK显式配置 `timeout=12`、`max_retries=0`。
- `DeadlineModelProvider` 对等待设置实际截止时间；每个服务进程最多4个并行模型调用。已超时但上游尚未结束的调用仍占用槽位，满额时立即返回 `BUSY`，避免持续创建后台任务。
- 超时后忽略迟到的模型结果。后台线程只调用模型，不持有案件写入函数，不会在超时后补写案件。停止等待不保证供应商已经停止生成或停止计费。
- 20秒约束模型等待，不是数据库事务、排队或浏览器网络的完整SLA。浏览器错误恢复应先读取已保存案件状态，再决定是否重试；重复建案由后端幂等机制控制。

`model_request_budget()` 的上下文可以跨FastAPI的同步处理线程和模型工作线程传播。后续增加模型入口时，也须接入同一预算及deadline包装器。

## 固定故障代码与恢复

| 代码 | 含义 | 操作 |
| --- | --- | --- |
| `TIMEOUT` | 单次调用或请求模型预算耗尽 | 查看确定性结果；需要时明确重新分析 |
| `RATE_LIMITED` | 上游429限流 | 稍后由用户重试，不在后台循环重试 |
| `BUSY` | 模型并发槽已满 | 保留确定性结果，等待上游请求结束 |
| `UNAVAILABLE` | 连接、鉴权或其他供应商故障 | 检查本地配置；需要时重启为离线模式 |
| `INVALID_RESPONSE` | JSON、字段、返回结构不合规 | 使用明确标记的降级说明 |
| `INVALID_ACTION` | 非法动作、错误目标或试图取消人工确认 | 丢弃模型动作，保留后端允许的建议 |
| `UNSAFE_OUTPUT` | 输出含不允许的敏感信息 | 丢弃该输出，使用确定性说明 |

异常文本固定为 `model provider request failed`；不得把上游响应正文、URL、凭据和请求内容回传给前端或日志。Copilot拒绝重复JSON键、额外字段、非法枚举、非当前缺口材料目标及 `requires_confirmation=false`；最终推荐始终需要人工确认。材料仅登记合成元数据，不因此证明材料正文一致、交易真实或胜诉概率。

## 离线备用

不传 `.env` 并显式关闭实时开关，启动同一应用：

```bash
OCEANPILOT_CHARGEBACK_LIVE_MODEL=0 .venv/bin/python -m uvicorn \
  oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8002
```

已有依赖、规则、合成数据和本地数据库应事先准备好；不要依赖现场下载。离线模式仍可进行案件登记、确定性材料清单、人工审核和本地摘要操作。

## 实时验证与验收记录

只有本项目已授权的有效凭据存在时，才对合成内容执行最小实时验证：

```bash
.venv/bin/dotenv -f .env run -- .venv/bin/python -m pytest \
  tests/model/test_deepseek_live.py -q
```

确认成功调用、结构解析、确定性结果保持和人审边界；记录供应商与验证时间，不记录密钥。缺少凭据时，测试会跳过，必须写明“实时模型尚未验证”，不能用离线测试替代。普通离线验收包括超时、429、错误JSON、非法动作、人工确认和FastAPI预算跨线程传播。

2026-09-06 本轮检查：新工作副本未配置环境密钥或 `.env`；用户随后确认主项目目录中已有授权配置。从该项目的 `oceanpilot ds API.rtf` 仅在内存装载凭据，完成 **1次真实DeepSeek合成Copilot调用**：`deepseek-chat`，耗时2.35秒，结果来源 `MODEL`，无故障代码，动作属于允许枚举且 `requires_confirmation=true`。使用12秒单次及20秒请求预算；未输出密钥或模型正文。此记录验证最小连通与结构/确认边界，不代表长期可用性或真实业务准确率。

DeepSeek沿用官方的OpenAI兼容Chat Completions协议；接口说明见 [DeepSeek API文档](https://api-docs.deepseek.com/)。兼容SDK的自动重试与超时行为见 [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python#retries)。

本轮追加浏览器验收：真实 DeepSeek 页面请求返回 `MODEL`，关键材料缺口及人工确认仍保留；重启后同版结果可恢复。独立合成延迟注入在12.03秒返回 `TIMEOUT/FALLBACK`，并非 DeepSeek 真实故障。见[验收记录](acceptance/2026-09-06/README.md)。
