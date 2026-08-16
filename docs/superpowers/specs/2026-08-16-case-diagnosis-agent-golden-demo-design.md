# 案件诊断 Agent 与黄金演示案件设计

## 1. 目标

OceanPilot 在比赛演示中先完整打通一条可复现的黄金案件：案件创建后进入“案件诊断”页，
AI 围绕当前案件自动分析；操作人员补充资料或输入审核结论后，AI 重新读取确定性快照，
说明材料内容、当前判断、下一步及原因，并引用已经登记的规则或支持文档。

本阶段不追求每个案件类型都有完整引用。通用 Agent 交互适用于全部 Synthetic 案件，只有
黄金案件必须具备完整证据、审核、引用、材料包、人工闸门、mock 回执和审计演示。后续案例
沿用同一合同逐步补齐规则映射和演示数据。

## 2. 已批准边界

- Agent 位于单个“案件诊断”页，不在案件中心列表保留第二套完整 Agent。
- 新建案件、确认原因、提交资料、确认审核结果后自动重新分析当前案件。
- 操作人员输入“审核通过”等结果时，AI 只生成拟写入提案；必须点击“确认写入案件”才持久化。
- 确定性内核继续决定案件阶段、证据缺口、就绪度、责任域和人工闸门。
- DeepSeek 负责理解输入、总结材料、解释判断和组织下一步，不得自行改变确定性字段。
- 规则引用必须来自后端提供的允许引用清单；模型不得生成未知规则 ID、条款号或链接。
- 全部数据为 Synthetic / Mock；不连接真实交易、退款、风控放行或卡组织提交。

## 3. 黄金演示案件

### 3.1 案件选择

固定使用现有模板 `Visa 10.4 · 非本人交易`：

- 内部理由：`FRAUD_CARD_NOT_PRESENT`；
- 卡组织：`VISA`；
- 精确规则版本：`visa-10-4-demo-v1`；
- 责任团队：`RISK`；
- 高风险类别：即使资料齐备也必须人工审核；
- 初始材料：仅有 `transaction.receipt`；
- 待补材料：`auth.threeds`、`auth.avs_result`、`auth.cvv_result`、
  `auth.device_ip_match`、`history.prior_transactions`。

选择该案件是因为现有仓库已经具备完整的证据政策、Visa 10.4 规则映射、材料包、人工审批、
mock connector 和审计展示。截图中的“授权异常”仍可作为普通案例存在，但不承担本轮完整引用演示。

### 3.2 真实性口径

内部清单共有六项，用于 OceanPilot Synthetic 案件准备和就绪度判断。Visa 10.4 演示材料包
只映射四项：3DS、设备/IP 关联、历史无争议交易和交易收据。AVS/CVV 是内部准备项，不得
宣称为 Visa 10.4 官方强制证据。

规则记录继续显示 `UNVERIFIED_SUMMARY` 和限制说明。内部 15 天窗口只代表原型准备窗口，
不得表述为 Visa 官方申诉期限。

## 4. 页面设计

### 4.1 案件中心

案件列表保留“查看诊断”入口；现有“问 Agent”改为“进入 AI 分析”，两者均进入同一案件
诊断页。案件列表不再承载完整聊天、判断卡片或执行轨迹。

### 4.2 案件诊断页

左侧保留：

- 发生了什么；
- 当前案件事实；
- 缺失资料与独立提交弹窗；
- 适用条款解析；
- 评估、材料包、人工审批、mock 回执和审计。

右侧原“本次案件 / 处理方式”区域升级为固定的“AI 案件分析”工作台，包含：

1. 当前案件与 DeepSeek / fallback 运行标识；
2. 最新分析更新时间和触发原因；
3. 审核状态、案件总结和判断原因；
4. 已确认事实、材料内容、缺口或冲突；
5. 下一步动作、责任团队、原因和人工确认提示；
6. 规则引用与支持文档引用；
7. 多轮案件消息；
8. 操作人员输入框；
9. “拟写入案件”确认卡片；
10. Agent 可视化执行轨迹。

窄屏时右侧工作台移至主内容下方，不使用横向滚动。资料提交弹窗保持现有三阶段进度和
成功回执。

## 5. 自动分析触发

以下事件成功后触发一次分析，重复事件按案件 revision 去重：

- 创建案件并成功读取；
- 人工确认争议原因；
- 每次资料提交成功；
- 人工确认写入审核结果；
- 用户主动点击“重新分析”。

仅浏览列表、搜索或切换标签不触发模型。案件诊断页重新打开时优先显示最新已确认分析
快照；只有案件 revision 已变化才重新请求。该约束避免列表逐案调用模型造成演示延迟。

## 6. 固定 JSON 合同

### 6.1 案件分析输出

```json
{
  "schema_version": "CASE_ANALYSIS_V1",
  "case_id": "case-id",
  "case_revision": 3,
  "trigger": "EVIDENCE_SUBMITTED",
  "case_summary": "持卡人否认该笔无卡交易，当前已收集交易收据与 3DS 结果。",
  "review_status": "NEEDS_MORE_INFO",
  "confirmed_facts": [
    {"fact": "争议交易收据已登记", "source_code": "transaction.receipt"}
  ],
  "material_contents": [
    {"evidence_code": "auth.threeds", "summary": "Synthetic 3DS 认证结果已登记"}
  ],
  "evidence_gaps": ["auth.avs_result", "auth.cvv_result"],
  "risk_or_conflicts": [],
  "decision_reason": "内部清单尚未齐备，且非本人交易属于强制人工审核类别。",
  "next_action": {
    "action": "补充 AVS 与 CVV 校验结果",
    "owner": "RISK",
    "why": "补齐内部授权验证上下文后才能完成材料审核。",
    "requires_confirmation": true
  },
  "citations": [
    {
      "reference_id": "visa-10-4-demo-v1",
      "reference_type": "RULE",
      "claim": "本案按 Visa 10.4 Synthetic 映射准备无卡交易争议材料"
    }
  ]
}
```

后端覆盖并校验 `case_id`、`case_revision`、确定性状态、证据代码、责任团队和允许引用。
模型输出与快照冲突时使用确定性值；解析失败时返回结构相同的 fallback。

### 6.2 操作人员输入提案

操作人员可输入：

> 审核通过。已核对 3DS 认证结果、AVS/CVV 结果、设备/IP 关联和历史无争议交易，材料内容一致。

AI 只返回提案：

```json
{
  "schema_version": "REVIEW_PROPOSAL_V1",
  "intent": "PROPOSE_REVIEW_DECISION",
  "case_id": "case-id",
  "case_revision": 8,
  "source_turn_id": "turn-id",
  "proposed_update": {
    "status": "APPROVED",
    "summary": "审核人员确认六项内部材料已齐备且内容一致。",
    "confirmed_materials": [
      "transaction.receipt",
      "auth.threeds",
      "auth.avs_result",
      "auth.cvv_result",
      "auth.device_ip_match",
      "history.prior_transactions"
    ]
  },
  "consistency_check": {
    "allowed": true,
    "conflicts": []
  },
  "next_action": {
    "action": "生成 Visa 10.4 Synthetic 材料包并预览",
    "why": "材料审核通过后仍需在最终发送前完成独立人工审批。"
  },
  "requires_confirmation": true
}
```

若确定性快照仍有缺失资料，`APPROVED` 必须降级为 `NEEDS_MORE_INFO`，并明确列出阻断项。
提案卡提供“确认写入案件”“修改输入”“取消”三个操作；未确认不得写数据库或改变页面状态。

### 6.3 确认写入响应

```json
{
  "result": "CREATED",
  "decision_id": "decision-id",
  "case_id": "case-id",
  "case_revision": 9,
  "review_status": "APPROVED",
  "audit_event_id": "audit-id",
  "reanalyze": true
}
```

相同 `source_turn_id` 重复确认返回 `REPLAYED`。案件 revision 变化时返回 409，要求基于最新
案件重新分析，不接受过期提案。

## 7. Prompt 设计

### 7.1 案件分析 Prompt

系统 Prompt 必须要求：

- 只使用给定案件快照、材料目录和允许引用清单；
- 只返回 `CASE_ANALYSIS_V1` JSON；
- 区分“确定性判断”“人工输入”和“AI 说明”；
- 不展示思维链、内部字段名、凭据或敏感数据；
- 不声称读取文件内容，只能总结后端明确提供的 Synthetic 材料元数据；
- 不得把内部 AVS/CVV 准备项描述为 Visa 官方必需证据；
- 每个下一步必须同时给出动作、责任人和原因；
- 每个引用 ID 必须来自 `allowed_reference_ids`。

### 7.2 审核输入解析 Prompt

系统 Prompt 必须要求：

- 识别审核意图和操作人员明确陈述的事实；
- 只返回 `REVIEW_PROPOSAL_V1` JSON；
- 不把“审核通过”直接等同于已写入或已发送；
- 有缺失关键材料、案件 revision 冲突或高风险阻断时不得提议最终通过；
- 不接受真实卡号、CVV 原值、密码、Token、个人身份信息或原始支付日志；
- `confirmed_materials` 只能来自当前案件已登记材料；
- 下一步说明必须引用确定性闸门。

### 7.3 确认后分析 Prompt

人工确认写入后重新生成 `CASE_ANALYSIS_V1`。此时审核状态显示“材料审核已通过”，但下一步
仍是“生成材料包并预览”，不得表述为已向 Visa 提交。最终 mock 发送继续使用现有独立审批。

## 8. 引用包

黄金案件必须返回两个经过后端登记的引用层级：

1. **规则引用：** `visa-10-4-demo-v1`，来源为 *Dispute Management Guidelines for
   Visa Merchants*，版本 `June 2024`，定位 `Condition 10.4 — Other Fraud,
   Card-Absent Environment`。页面同时显示 `UNVERIFIED_SUMMARY` 和限制说明。
2. **技术背景引用：** `oceanpayment-threeds-doc`，来源为 Oceanpayment 3DS 开发文档，
   只用于解释为什么需要保留 3DS 认证上下文，不参与卡组织资格、期限或责任转移判定。

技术背景引用可作为只读支持文档记录加入规则知识库，类型标记为 `TECHNICAL_CONTEXT`。
模型只能引用后端返回的 ID。普通案例没有匹配引用时显示“当前尚无已核验引用”，不得匹配
相似条款。

## 9. 持久化与审计

采用非破坏性 SQLite 扩展，保存已确认审核决定及其分析快照。每条记录至少包含：

- `decision_id`、`case_id`、`case_revision`；
- `source_turn_id` 和固定 JSON schema version；
- 审核状态、操作人员摘要、AI 解析快照；
- 允许引用 ID；
- `confirmed_by`、`confirmed_at`；
- 审计事件 ID。

确认写入、案件 revision 更新和审核审计必须原子提交。重复确认幂等重放；过期 revision、
跨案件 turn、未知材料代码、未知引用 ID 和敏感输入全部拒绝。重新打开案件时可读取最新已确认
审核决定和分析快照。

## 10. 完整演示脚本

| 步骤 | 操作 | 页面应展示 |
|---|---|---|
| 1 | 选择 `Visa 10.4 · 非本人交易` 并确认建案 | 自动进入案件诊断；AI 显示 1/6、风控团队和待补五项 |
| 2 | 打开规则引用 | Visa 10.4 版本、来源、限制说明和四项材料包映射 |
| 3 | 补交 3DS Synthetic 文件 | 正式弹窗、三阶段进度、成功回执；AI 自动更新材料内容 |
| 4 | 依次补交 AVS、CVV、设备/IP、历史交易 | 每次 revision 增加、缺口减少、AI 下一步变化 |
| 5 | 资料达到 6/6 | AI 说明内部清单已齐，但欺诈类仍需人工审核 |
| 6 | 输入“审核通过……” | 只出现拟写入卡片，展示材料摘要、判断原因、下一步和引用 |
| 7 | 点击“确认写入案件” | 审核决定与审计落库；AI 更新为“材料审核已通过” |
| 8 | 生成材料包并预览 | 展示 Visa 10.4 四项映射；AVS/CVV 只在内部清单区 |
| 9 | 输入审核人并执行现有最终审批 | 只发送至 in-process mock connector |
| 10 | 查看回执和审计 | 审核决定、引用、人工确认、mock 回执可追溯 |

整条流程从空 Synthetic SQLite 数据库可重复运行；失败返回非零或在页面显示明确恢复动作。

## 11. 异常与降级

- DeepSeek 超时、JSON 无效或引用越界：使用确定性 fallback，保留重新分析按钮。
- 资料提交失败：弹窗内显示错误，不伪造案件状态或 AI 分析。
- 提案确认发生 CAS 冲突：提示案件已变化，重新读取后再确认。
- 没有引用：显示空态，不生成占位条款。
- 支持文档不可访问：保留登记元数据和来源 URL，标记“外部来源暂不可访问”。
- 敏感输入：返回统一安全错误，不在响应、日志、审计或 SQLite 中回显原文。

## 12. 验收标准

- Agent 只存在于案件诊断主线，进入黄金案件后自动分析。
- 每次成功补交资料后，分析基于新的 case revision 更新。
- 输入“审核通过”只生成提案；确认前数据库、案件状态和审计均不变化。
- 缺资料时不能确认 `APPROVED`；资料齐备后仍保留欺诈类人工闸门。
- 确认后审核记录和分析快照可在重启后读取。
- Visa 10.4 与 Oceanpayment 3DS 引用均来自允许清单，可点击并显示来源与限制。
- 未映射普通案例不伪造引用。
- 重复确认幂等，过期 revision 拒绝，重复建案不会发生。
- 聚焦 domain/application/repository/API/demo 测试通过，浏览器无 JavaScript 错误。
