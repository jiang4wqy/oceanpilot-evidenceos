# `adapters/` — 端口实现 / driven adapters

**最外层之一。** 这里放 `application/` 里 Protocol 端口的**具体实现**:模型、存储、渠道、外部系统。可以自由 import 框架/SDK/stdlib。要换实现(如把 mock 上游换成真实工单),只动这一层。

## 模型层 `model/`
| 文件 | 说明 |
|---|---|
| `claude.py` | `ClaudeProvider`,Anthropic SDK,默认 `claude-opus-4-8`;不发 temperature/budget_tokens。 |
| `local.py` | `LocalModelProvider`,OpenAI 兼容 `/v1/chat/completions`,HIGH 档隔离模型;失败统一包成 `ModelProviderError`(不泄露)。 |
| `deepseek.py` | DeepSeek OpenAI-compatible Provider 构造器；仅从环境变量读取凭据，复用分级路由与脱敏。 |
| `composition.py` | `build_chargeback_model_provider`:按安全档位组装 `RoutingModelProvider`（LOW=所选外部模型，MEDIUM=脱敏后外部模型，HIGH=本地隔离模型或脱敏外部模型）。 |
| `fake.py` | `ScriptedModelProvider`,离线确定性,供演示/测试。 |

## 持久化 `persistence/`
| 文件 | 说明 |
|---|---|
| `sqlite.py` | 连接工具:`connect_sqlite`、`immediate_transaction`(每调用独立连接,线程安全)。 |
| `chargeback_sqlite.py` | `SqliteChargebackCaseStore`:追加式证据、理由确认后不可变、单调 revision、乐观 CAS、幂等重放、原子审计。**独立 db 文件**。 |
| `chargeback_schema.py` | 拒付表 DDL(`chargeback_cases/evidence/audit`,synthetic=1)。 |
| `chargeback_memory.py` | 进程内实现(演示/测试用)。 |
| `schema.py` | 基础版案件表 DDL。 |

## 渠道 `channels/`
`http/channel.py`(纯 JSON 参考渠道)、`feishu/channel.py`(飞书交互卡片;自包含)。都实现 `application.channels.Channel`。

## 其它端口实现
- `knowledge/bank_rules.py` — `InMemoryBankRules`(银行/卡组织证据模板;真实数据可经 `ingestion/` 直接替换)。
- `ingestion/{schema,loader,samples}.py` — 公司参考数据的严格封闭导入(见 `docs/data/`)。
- `signals/synthetic.py` — 预防风险的合成信号源。
- `upstream/mock.py` — 上游申诉提交的 mock(永不触真实系统)。
- `clock.py` — `SystemClock`。
- `redaction.py` — `RegexRedactor`。
- `feishu/*` — 飞书客户端、签名校验、卡片、回调存储。
- `diagnosis/rules.py`、`evidence/synthetic.py` — 基础版规则引擎与合成证据。
