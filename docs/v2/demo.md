# V2 Golden Demo Runbook

先按根目录 README 启动 Python 3.12 服务，打开 `/v2/operations`。全程为本地合成演示；不要填写真实卡号、CVV、密钥或真实持卡人信息。页面显示的角色切换是演示身份，不是生产登录。

## A：完整 Contest 闭环

1. **OP 运营**：新建 A 演示案件。系统经过 INTAKE、精确 Mock 规则匹配与 PUBLISH_TASK；记录案件 ID。查看 Agent 计划、72/96/120 小时合成期限及来源。
2. **Merchant**：打开 `/v2/merchant?case_id=案件ID`，确认商户 ID 与该案相同，选择 Contest。在证据页按清单登记每项合成材料，填写 `synthetic://...` 引用。检查缺口消失后，提交材料给 OP。
3. **Risk Officer**：在 OP 页切换风险审核角色，检查同案本版材料、来源和清单，选择 PASS 并填写审核理由。材料缺失时不能通过。
4. **OP 运营**：生成包，查看草稿、证据索引与规则来源。
5. **Supervisor**：检查包内容、版本和 PII 范围，明确确认完成脱敏检查并批准冻结包。Risk 审核人和最终审批人必须为不同身份。
6. **OP 运营**：提交已冻结包。显示 `MOCK`、技术 `DELIVERED`、业务 `MOCK_ACCEPTED`、request/receipt/idempotency ID；案件进入 WAITING_UPSTREAM，结果仍是 UNKNOWN。
7. **OP 运营**：登记合成上游结果 WON、终局 true、独立 event ID 和来源；再登记 CREDIT 金额 12800 USD 最小单位（128.00 USD）。金额字段使用整数最小货币单位。
8. **Supervisor**：核对状态 RECONCILED，预期净影响 12800，填写人工核对理由与合成账本引用。此时仍需通知。
9. **OP 运营**：将结果和资金摘要发布到 Portal。
10. **Supervisor**：确认结案。审计展示所有角色、动作和版本。结案后的业务数据不能继续改写。
11. **OP / Agent**：生成脱敏知识候选；**Admin** 在治理页面人工审核。只有批准候选才会出现在后续同类案件计划的相似模式中。

正常操作每次读取服务器返回的新 revision。重试使用同一 command ID；遇到版本冲突先刷新，重新审核具体动作，不盲目执行旧提案。

## B：缺证与协作

新建 B，切换商户查看 Visa 13.1 缺少物流和签收证明。点击提交材料被门槛阻止；Agent 显示缺项、来源、原因与下一步。可在 Portal 协作线程留言，再补齐合成材料，送 Risk Officer 审核；审核可退回补证、建议接受或通过。建议接受不会代替商户授权。

飞书适配器可为同一案生成缺证/提醒/审核反馈卡，并在已配置的可信签名 callback seam 上处理协作；本地验收不发送真实飞书消息。未配置时 UI 正确显示未配置状态。配置和可复现测试见 [Feishu 文档](feishu.md)。

## C：截止风险与未响应

新建 C：商户期限已经超过，存在 SLA_ESCALATION 待办，merchant decision 仍为 NONE。OP 执行监测或记录 NO_RESPONSE，需要检查过期时间并说明原因。系统不会将未回复改成 ACCEPT，不创建退款；交由人工确认剩余权利和上游后续事件。

若上游返回未知结果，可登记 UNKNOWN + 非终局；案件保持等待确认，不能关闭。

## D：终局后资金差异

新建 D 已通过实际命令创建完整 Contest、两次人审、冻结包、Mock 提交和 WON 终局；故意将预期金额与账本金额设置相差 100 最小单位，显示 DISCREPANCY。

尝试结案应被阻挡。检查合成账本 CREDIT 12800 后，由 Supervisor 重新核对预期 12800 并提供理由；OP 发布结果，Supervisor 才能关闭。核对操作保存判断，不篡改原账本。

另可在 A 已提交后登记 OTHER + 非终局 + REPRESENTMENT，查看原阶段快照和新阶段期限。PRE_ARBITRATION 等无 fixture 阶段会进入 NEEDS_CONFIRMATION；Risk Officer 必须填写明确来源、版本、允许动作、证据项和期限，才能继续发布任务。

## Accept 分支

在 A 商户端选择 Accept，记录明确理由与授权身份。无需继续收集抗辩材料；案件等待上游结果。仍须登记终局、人工核对资金、通知并关闭。Accept 本身不会创建退款事件。OP 代商户记录决定时必须提供授权引用。

## 机器复现

```bash
PYTHONPATH=src .venv/bin/python scripts/eval_dispute_v2.py
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/workflow tests/api/test_dispute_api.py \
  tests/domain/test_dispute_rules.py tests/channels/test_dispute_feishu.py -q
```

脚本使用临时数据库，经相同领域命令执行 A–D，并检查禁止动作、版本、来源、SLA、缺证、财务关闭与审计。退出码非零表示有验收失败。不会使用实时模型或外部提交。

V1 的 `/demo` 与 `/business` 仍可用于历史排练，V1 记录不会出现在 V2 正式争议列表中。
