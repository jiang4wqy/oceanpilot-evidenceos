# OceanPilot Demo Runbook

比赛版本展示综合商户成功智能体的两个本地 synthetic 切片。8 月 16 日先展示支付异常，再展示拒付申诉。全程不使用 Oceanpayment 或真实飞书生产数据，不执行支付、退款、风控放行、资金移动、生产配置变更或真实上游提交。

## 1. Prerequisites

- Python 3.12
- 从仓库根目录创建环境并安装：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Windows 将 `.venv/bin/python` 替换为 `.\.venv\Scripts\python.exe`。

## 2. 启动本地服务

```bash
export OCEANPILOT_DB_PATH=work/oceanpilot.db
.venv/bin/python -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8000
```

Windows PowerShell：

```powershell
$env:OCEANPILOT_DB_PATH = "work/oceanpilot.db"
.\.venv\Scripts\python.exe -m uvicorn oceanpilot.main:create_app --factory --host 127.0.0.1 --port 8000
```

## 3. 8 月 16 日主展示：支付异常 cockpit

浏览器打开：

```text
http://127.0.0.1:8000/demo/payment-incident
```

建议演示顺序：

1. 指出页面顶部 `SYNTHETIC` 和禁止业务动作边界。
2. 运行“3DS / 回调未完成”，观察 readiness 从缺证推进到达标。
3. 展示 API 返回的候选原因、置信度、复核原因、责任域、证据引用、下一动作和审计引用。
4. Reset 后选“风控拒绝”，说明同一内核可以路由到不同责任域。
5. 视时间展示商户侧或 PSP 侧配置不匹配。
6. 点击“返回拒付处理”，进入第二个切片。

cockpit 只调用：

- `POST /api/v1/cases`
- `POST /api/v1/cases/{case_id}/evidence`
- `POST /api/v1/cases/{case_id}/diagnose`

所有运行结论来自公开 API；页面不注入 source reliability，不伪造规则、confidence、route、revision 或 audit。任一步失败就停止，不制造下游状态。

## 4. 四规则 HTTP PowerShell demo

服务运行时，在另一个 Windows PowerShell 窗口执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\examples\demo.ps1
```

脚本从 health 开始，以全新 synthetic case 顺序验证四个规则子场景；失败时返回非零退出码，不访问外部服务。

## 5. Signed local Feishu fallback

无需真实飞书网络或凭据。指定一个不存在或空目录：

```bash
.venv/bin/python -B examples/signed_fixture_demo.py --work-dir work/signed-feishu-run
```

runner 使用随机运行时凭据与外部标识，通过真实签名 verifier、callback routes、schemas、orchestrator、stores 和 card renderer，完成：

```text
signed message
  -> create/bind case
  -> seven signed evidence actions
  -> readiness + diagnosis card
  -> signed human confirmation
  -> one approval audit
  -> message/action replay without duplicate side effects
```

它使用 in-process outbound transport，不访问外网；非空工作目录会在修改前 fail closed。稳定 JSON 摘要必须包含 `business_action_executed:false`、`case_unchanged_by_confirmation:true`、消息 replay、确认 replay 和一次 approval audit。

确认只记录建议审批，不改变 payment core case，也不执行支付、退款、风控放行、资金移动或生产配置变更。

## 6. 真实飞书测试群排练（外部门）

完成 [飞书配置指南](feishu-setup.md) 的最小权限应用和公网 HTTPS callback 后，在专用测试群按
以下台词与点击顺序排练：

1. 主讲人发送：`3DS 验证后支付一直停在处理中，回调也没有收到`。
2. 解释机器人先建案并按 readiness 补问，不直接猜原因。
3. 连续点击每张新卡的“提交当前合成示例”，共 7 次；说明这些是服务端受控的演示证据，
   不是 Oceanpayment 生产数据，也不能由调用方填写可信度或责任域。
4. 在诊断卡上讲清候选原因、0.87 置信度、证据引用、责任域和 `HUMAN_REVIEW`。
5. 点击“确认人工复核”；说明这里只新增一条审批审计，案件本身不变，业务动作执行为 false。
6. 重复点击一次旧补证卡或确认按钮，展示 evidence revision/审批数不增加。

目标时长 90 秒：15 秒描述异常，45 秒补证与解释，20 秒诊断卡，10 秒确认与幂等。若真实飞书
或公网隧道异常，立即切换上一节 signed local fixture，不把 fallback 说成真实群联调。

## 7. 拒付申诉切片

打开：

```text
http://127.0.0.1:8000/demo
```

选择示例拒付场景并自动补证到评估，展示：原因识别、证据清单/SLA、确定性胜诉评估、责任团队、材料打包、申诉草稿、人工门、审计与安全扫描。

拒付上游是 `MockUpstreamConnector`。即使页面显示 synthetic/mock submission，也不是 Oceanpayment、银行或卡组织真实提交。

## 8. Full local gate

```bash
.venv/bin/python -m pytest -p no:cacheprovider -q
.venv/bin/ruff check src tests examples scripts
.venv/bin/ruff format --check src tests examples scripts
.venv/bin/python -m compileall -q src tests examples scripts
.venv/bin/python -m pip check
git diff --check
```

API 事实检查：

```bash
.venv/bin/python -c "from oceanpilot.main import create_app; assert len(create_app().openapi()['paths']) == 19"
```

## 9. 尚未完成的现场证据

真实飞书测试群需要公网 HTTPS callback、最小权限测试应用和时间戳证据。当前仓库只证明 signed local fixture；未完成真实群 smoke 时不得宣称飞书真机联调或 Gate 4 PASS。
