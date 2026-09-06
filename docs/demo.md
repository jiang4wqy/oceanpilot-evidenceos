# OceanPilot 双端演示 Runbook

当前主演示结束在 **人工登记复核＋案件复核摘要（合成示例）**。全部案例假定已进入正式争议流程；普通支付失败、3DS 挑战失败、回调异常属于 Foundation `PAYMENT_INCIDENT` 支持场景，不能直接当作拒付。

系统仅登记合成材料元数据，未读取真实文件正文。材料就绪度是内部清单登记情况，不代表内容一致、交易真实、胜诉率或真实业务准确率。规则库是未核验摘要，必须显示具体卡组织、原因码、版本、来源与核验限制。默认最终发送在后端关闭；即使设置发送开关，也不能绕过尚未完成的冻结版本批准与回执恢复验收。

## 1. 本地离线启动与恢复

已有项目依赖时，可使用统一启动入口，不会在启动时安装依赖。默认端口为 `8026`，默认模式为 `offline`：

```bash
.venv/bin/python scripts/run_local_demo.py --mode offline
.venv/bin/python scripts/run_local_demo.py --mode live --port 8026
```

当前本地共享环境也可直接使用 `../oceanpilot-latest/.venv/bin/python scripts/run_local_demo.py --mode live`。脚本使用调用它的 Python 环境，固定项目工作目录与 `src` 导入路径；从其他目录启动时，传入脚本的绝对路径即可。它在启动时读取项目根目录 `.env`，已有 shell 环境变量优先；`--mode` 始终决定本次模型模式。live 仅使用 DeepSeek，缺少非空 `DEEPSEEK_API_KEY` 时明确报“配置未就绪”并退出，不会把离线结果称为实时。密钥不会写到启动回执或命令参数中。

该入口默认保留 `work/local-demo/core.db`、`work/local-demo/oceanpilot-chargeback.db`、`work/local-demo/oceanpilot-rules.db`；`.env` 或 shell 已指定的三库路径优先。live 与 offline 使用同一配置路径，切换模式不会重置案件。默认页面为 `http://127.0.0.1:8026/demo` 和 `http://127.0.0.1:8026/business`。按 `Ctrl-C` 停止后重新运行即可；脚本不创建守护服务、不自动重启，也不抢占已使用的端口。最终发送保持关闭。设置 live 只表示实时配置已启用，仍需按页面每次回答的 `MODEL` / `FALLBACK` 来源判断调用结果。

首次安装需要本地已有依赖或联网安装；安装完成后的离线演示不调用外网模型。使用 Python 3.12：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
export OCEANPILOT_DB_PATH=work/oceanpilot.db
export OCEANPILOT_CHARGEBACK_LIVE_MODEL=0
export OCEANPILOT_MOCK_SEND_ENABLED=0
.venv/bin/python -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8002
```

Windows PowerShell 将 Python 路径换为 `.\.venv\Scripts\python.exe`，环境变量写为：

```powershell
$env:OCEANPILOT_DB_PATH = "work/oceanpilot.db"
$env:OCEANPILOT_CHARGEBACK_LIVE_MODEL = "0"
$env:OCEANPILOT_MOCK_SEND_ENABLED = "0"
.\.venv\Scripts\python.exe -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8002
```

打开两个同源页面：用户端 `http://127.0.0.1:8002/demo`，业务端 `http://127.0.0.1:8002/business`。两端读取同一个案件编号与版本。`/admin` 是独立运行维护入口，不是业务复核端。`/health` 用于检查服务，`/docs` 查看实际接口合同。

可选 Docker：

```bash
docker build -t oceanpilot-evidenceos .
docker run --rm -p 127.0.0.1:8000:8000 -e OCEANPILOT_CHARGEBACK_LIVE_MODEL=0 -e OCEANPILOT_MOCK_SEND_ENABLED=0 -v "$(pwd)/work:/app/work" oceanpilot-evidenceos
```

容器映射的页面端口是 8000。保留 `work` 挂载才可在容器移除后恢复持久化案件；本地服务也要保留同一数据库目录。数据库路径配置见 `.env.example`。

现场只使用预先验证的一种实时供应商：DeepSeek。凭据与 live smoke 见 [DeepSeek 接入指南](deepseek-setup.md)；没有通过实际 live 验证就使用上述离线路径。区分每次回答的 `MODEL`（实时）、`DETERMINISTIC`（确定性规则）和 `FALLBACK`（异常降级）；配置了供应商不等于本次回答来自模型。模型故障后保留当前案件，在明确提示下重试；改为离线模式并重启时使用同一数据库路径。

## 2. 主讲顺序：完整 A，再展示 B

| 步骤 | 用户端 `/demo` | 业务端 `/business` | 要证明的结果 |
|---|---|---|---|
| 建立上下文 | 选择“新建 A 样例副本”，确认合成正式争议前提 | 按同一案件编号找到 A | A 为 Visa 10.4，内部材料登记 5/6，关键缺口为 3DS (`auth.threeds`) |
| 解释缺口 | 查看已知信息、已登记材料、缺失项及为什么缺 | 可读取同版状态 | 关键缺失阻断正式评估；“结束补证”也不能跳过 |
| 登记一项材料 | 登记合成 3DS 材料元数据，确认操作并核对回执 | 刷新同案，检查版本已变化 | 6/6 仅表示内部登记清单齐全，仍须人审，正文状态为 `NOT_READ` |
| 查看规则 | 进入实际匹配的 Visa 10.4 规则后返回同案 | 核对版本、来源与 `UNVERIFIED_SUMMARY` | 内部六项清单与规则摘要要求范围分别说明；不能把 AVS/CVV 宣称为官方必需材料 |
| 人工复核 | 显示当前处理阶段及下一位责任人 | 复核当前版本，选择登记清单、内部门槛或规则引用来源的审核范围，再确认写入 | 只确认登记范围；不输入“已核验真实文件”“交易真实”等越界结论 |
| 导出结果 | 查看审核状态与历史 | 生成并下载“案件复核摘要（合成示例）”HTML，可同时下载 JSON | 案件、材料、缺口、规则、审核、下一步与未核验事项来自同一快照；导出不调用模型 |
| 展示 B | 新建 B 副本 | 查看 B 的历史批准与当前阻断 | B 曾登记复核通过，随后撤回关键 3DS；旧批准已失效，当前不能通过登记复核 |

主讲不需要反复点击六次补证。A/B/C 副本全部由真实后端命令创建；再次排练新建副本，不清空数据库，也不在浏览器把进度改成 100%。

A 的人工复核说明示例：

> 当前版本内部材料登记清单已复核；未读取真实文件正文，真实性、内容一致性及规则正式适用性仍待核验。

B 可尝试结束补证或再次批准，结果应保持关键材料阻断。允许记录退回补证或驳回，不允许借此批准缺失版本。

## 3. C 与会前边界检查

C 是 Visa 13.1 商品未收到的合成正式争议，仍缺签收证明；用于自测和企业追问。查看规则、补问、审核下一步及摘要，不应复用 Visa 10.4 文案。再使用现有 Mastercard 4853 场景检查引用；没有精确映射时明确显示“无精确匹配”，不把默认清单当正式规则。

| 状态 | 允许的工作 | 不能做的工作 |
|---|---|---|
| 关键材料缺失 | 解释缺口、登记材料、退回补证 | 正式评估、批准当前登记清单；结束补证不能绕过 |
| 仅普通材料缺失 | 有限分析并列出缺口 | 宣称清单完整或允许最终提交 |
| 人工登记冲突、来源不明或规则疑点未解决 | 留下字段、旧新值、来源、版本、处理人及审核说明 | 无声覆盖矛盾或自动继续通过 |
| 清单齐全、门槛满足 | 业务人员复核当前版本，生成摘要 | 自动宣称文件正文/真实性已核验 |
| 无精确规则 | 说明内部清单范围、交由人工确认规则 | 用默认模板充当正式适用依据 |

摘要允许诚实记录阻断或未审核状态，并非只有通过案件才能导出。任何内容变化会使旧审核历史化；保存的旧摘要保持原版本，不能伪装为当前结论。生成期间案件、审核或规则变化时，应按错误提示刷新并重新生成。

## 4. 回执、重试与 API 排练

权威字段见 [工作台 API 合同](implementation/2026-09-06-workspace-contract.md)。演示角色通过 `X-Demo-Role: MERCHANT|BUSINESS` 区分，这不是生产身份认证。可选 `X-Demo-Actor` 使用 ASCII 名称，例如 `demo-reviewer`；省略时使用后端演示身份。

- `POST /api/v1/workspace/commands` 接收 `command_id`、`action`、`data`、`confirmed:true`；已有案件写入还需 `case_id` 与 `expected_revision`。
- `COPY_SAMPLE` 的数据是 `{"sample":"A"}`（或 B/C）。创建新副本使用新命令编号。对同一次操作重试，保留原命令编号和完整内容，成功回执不会重复创建案件或业务记录。`REVIEW` 还必须携带预览时的 `expected_rule_fingerprint`，规则变化时重新预览确认。
- 成功后核对 `receipt` 中案件、版本和操作编号；超时先查 `GET /api/v1/workspace/commands/{command_id}`。返回 `UNKNOWN` 表示尚无已提交回执，不代表不存在进行中的请求；可使用原命令重试，不能换编号盲目新建。
- 版本冲突时刷新案件并重新确认当前输入；不要把旧批准静默套在新版本上。
- 业务端以 `POST /api/v1/workspace/cases/{id}/summaries` 和 `{"expected_revision":当前版本}` 生成摘要，再访问返回的 `html_url`/`json_url`。
- 默认 `POST /api/v1/chargeback/cases/{id}/appeal` 返回 503；开关设为 1 仍返回 501。冻结版本批准、持久化幂等与 Mock 回执恢复未联合验收，不加入发送演示。

可离线运行完整公开 HTTP transcript（临时数据库，不改变服务中的案件）：

```bash
.venv/bin/python examples/chargeback_transcript.py
```

该脚本演示 A → 登记 → BUSINESS 审核 → 同版 HTML/JSON 下载，并核对 B/C；显式注入离线 provider，即使 shell 配有 live 开关也不访问模型。更窄的 `examples/chargeback_demo.py` 只检查 Supervisor 补问与材料就绪度，不包含持久化审核和导出。

```bash
.venv/bin/python examples/chargeback_demo.py
.venv/bin/python scripts/eval_chargeback.py
```

离线评测只衡量内置合成语句的分类及预设清单缺口分离度。历史 `won/lost` 标签为人工构造，并非真实结果；所有合成案件均需人工复核，不能把测试比例包装成真实准确率或业务收益。

## 5. 辅助能力与验收记录

Foundation `examples/demo.ps1` 保留技术异常 → 确定性诊断的独立回归路径；飞书签名回调测试是 synthetic seam 验证。真实 tenant 尚未完成；本轮不从零配置飞书，也不新增任意文件识别平台。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\examples\demo.ps1 -BaseUrl http://127.0.0.1:8002
```

```bash
.venv/bin/python -m pytest -p no:cacheprovider -q
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/python -m compileall -q src tests
git diff --check
```

记录实际 commit、测试结果、离线演练结果及 live 验证状态。历史交付报告和截图保留历史口径，不能代替本次双端与摘要验收。
