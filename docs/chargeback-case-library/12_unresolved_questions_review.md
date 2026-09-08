# 12 五个待确认问题 × 资料核对（12_unresolved_questions_review.md）

> 生成时间：2026-09-08
> 核对范围：SRC-01 Visa《Dispute Management Guidelines for Visa Merchants June 2024》(67 页)、SRC-02 Mastercard《Chargeback Guide Merchant Edition 19 May 2026》(1582 页)、SRC-03《卡组织争议处理规则与案例映射.md》(703 行)。
> 判定口径：**有** = 书中直接回答；**部分** = 书中只有卡组织侧依据，OceanPayment 侧仍缺失；**没有** = 书中未回答。

## 结论速览

| # | 问题 | 书中是否已回答 | 结论 |
|---|---|---|---|
| 1 | OceanPayment 在不同支付通道下的精确角色名称及与收单行/上游机构的关系 | **没有**（仅卡组织通用角色定义可借鉴） | NEEDS_CONFIRMATION |
| 2 | 实际争议信息进入 OceanPayment 的来源系统与字段 | **部分**（卡组织侧消息字段有，OceanPayment 接入来源没有） | NEEDS_CONFIRMATION |
| 3 | 商户 Accept / Contest 的真实操作权限与确认方式 | **部分**（规则层"可接受/可抗辩"场景有，产品权限没有） | NEEDS_CONFIRMATION |
| 4 | Visa / Mastercard 各阶段实际执行的 SLA、延期与超时处理规则 | **部分**（Mastercard 有明确天数；Visa 没有；"实际执行"均没有） | NEEDS_CONFIRMATION |
| 5 | OceanPayment 最终向哪个具体上游主体提交材料、结果如何回传 | **没有**（仅卡组织流程方向可借鉴） | NEEDS_CONFIRMATION |

---

## 问题 1：OceanPayment 在不同支付通道下的精确角色名称，以及与收单行/上游机构的关系

**书中是否已回答：没有。**

书中只有卡组织的**通用四方模型**，不涉及任何具体公司：

- Visa 指南 Glossary（SRC-01 P60–64）定义了 Acquirer（"签约商户/支付服务商、向持卡人提供现金发放或向预付卡充值并（间接）将交易送入 Interchange 的客户"）、Issuer、Merchant、Cardholder 及欧洲区特别定义；"flash title transfer" 不构成商户（P64）。
- Mastercard 指南（SRC-02 P33–34）定义了 On-Us transaction、Domestic transaction、第三方处理交易（Third Party Processed Transaction）及其争议受理条件（EEA/Gibraltar/UK）。
- SRC-03 §1 从"收单机构 / PSP / 商户争议运营"视角整理了五家卡组织的机制对比。

**书中没有的**：OceanPayment 作为具体主体，在 Visa/Mastercard/Amex 体系中到底是 Acquirer、Acquirer 的支付服务商客户、还是 Payment Facilitator / PSP，以及它在不同通道（卡收单、BNPL、DCB、本地钱包）下的角色名称与责任——三份资料完全未提。

**建议获取答案的渠道（Optimized tool selection）**：与 OceanPayment 法务/收单团队确认其卡组织注册主体与资质类型；查阅其与收单行的合同；以 SRC-01 P60–64 的 Acquirer 定义逐条对照定位。

---

## 问题 2：实际争议信息进入 OceanPayment 的来源系统与字段

**书中是否已回答：部分。**

**书中有（卡组织侧字段标准）**：

- Visa：争议通知到达时商户应拿到"全部细节与文件"（SRC-01 P12）；Dispute 定义为"issuer 退回给 acquirer 的交易"（P62）。
- Mastercard：First Chargeback 消息要素明确——DMS First Chargeback/1442，DE 24 = 450（全额）/453（部分）（SRC-02 P36 Table 1）；清算字段 DE 3/DE 15（Settlement Date）/DE 43（终端国家）；退款匹配用 Trace ID，2026-06-02 起可用 TLID（DE 105）（SRC-02 P152–153、P638）；仲裁/回执字段（P1409）。
- 即：**卡组织上游会传什么字段，书里有**；案例库的 `dispute_facts`（issuer_notice / reason_code / dispute_received_at / response_deadline）就是按这些字段设计的。

**书中没有的**：争议信息从哪个具体系统（收单后台、Mastercom、Visa Resolve Online、China Switch 平台，或 OceanPayment 自建同步管道）进入 OceanPayment、用什么协议、字段映射关系。

**建议获取答案的渠道**：与收单机构核对上游对接文档（Mastercom Claims Manager API、Visa Resolve Online 文件格式）；参考 SRC-02 P33（Mastercom 为争议处理入口）与 P849（中国大陆走 China Switch 平台）规划适配器。

---

## 问题 3：商户在不同场景下 Accept / Contest 的真实操作权限与确认方式

**书中是否已回答：部分。**

**书中有（规则层的场景与边界）**：

- 可接受的场景：无授权（4808/11.3）、证据全缺的欺诈（10.4 CE 不成立）、重复扣款实锤（12.6/4834）——案例库中各案例 `should_accept_or_contest` 字段已按规则给出建议。
- 商户救济路径：Visa "接受（支付争议金额）或拒绝（准备支持文件提交 processor）"（SRC-01 P9）；Mastercard 二次呈请（Second Presentment）、预仲裁 Accept/Take no action/Reject 三选一、超时不动作 30 天自动接受（SRC-02 P36–37、P930–931）。
- 人工确认的要求：支持文档不得含完整 PAN（仅后四位）、证据格式、翻译、上传时限（SRC-02 P155–157 等）——这些是"确认方式"的规则侧约束。

**书中没有的**：OceanPayment 产品里**谁有权点 Accept/Contest**（商户管理员？运营？审核角色？）、需要几级确认、权限矩阵与审计要求——这是产品设计问题，卡组织不规定。

**建议获取答案的渠道**：产品/运营团队定义权限矩阵；参考案例库 `process_flow.human/reviewer/submit_condition` 与 CB-CASE-066（Agent 提案+用户确认）、CB-CASE-061（阻断提交）的演示设定。

---

## 问题 4：Visa / Mastercard 各阶段实际执行的 SLA、延期与超时处理规则

**书中是否已回答：部分。**

**书中有**：

- **Mastercard 各阶段天数明确**（SRC-02 各章）：
  - Issuer Chargeback：4808/4834 类 90 天、4853 类 120 天、4837 类 120 天、QMAP 120 天、Coercion 30 天；中国大陆境内多为 90 天（5–90 窗口）。
  - Second Presentment：其他 45 天（Ch2）或 30 天（Ch4 模板）；Costa Rica 10 工作日 / Kazakhstan 30 天 / 中国大陆 30 天 / Nigeria 2 工作日 / Tanzania 20 天。
  - 预仲裁 30 天；响应 15 天（Change of Reason 章节为 30 天）；仲裁 10 天（部分章节 15 天）。
  - 超时规则：收单 30 天不动作自动接受；SP 文档迟到不采纳；预仲裁/仲裁当日及之后补交文档不采纳；SMS 自动冲销码 19（证据 10 天未提交触发）。
- **Visa 没有具体天数**：只写"争议周期每步都有明确时限，未按时回复可能导致不利结果""视收单而定"（SRC-01 P12）——**书中明确未给出数字**。
- **延期机制**：Mastercard Hardship Variances（自然灾害可移除 DMS 时限校验，SMS 不支持，SRC-02 P39）。
- **冲突需注意**：SP 45/30、响应 15/30、仲裁 10/15 存在章节差异（案例库 CONFLICT-006/007/008），**"实际执行"以哪版为准书中无法判定**。

**书中没有的**：Visa 的实际天数；"实际执行"的 SLA（收单机构内部承诺的处理时长、宽限期、重试窗口）——两本书都是卡组织上限，不是 OceanPayment 上游的实际执行口径。

**建议获取答案的渠道**：从收单机构拿 Visa 有效版本与双方 SLA 协议；Mastercard 侧按案例库冲突清单向业务确认生效版本；系统实现按 `rule_version + effective_date` 参数化。

---

## 问题 5：OceanPayment 最终向哪个具体上游主体提交材料，以及结果如何回传

**书中是否已回答：没有（仅流程方向可借鉴）。**

**书中有（卡组织流程方向）**：

- 商户/收单向哪提交：商户提交 processor/acquirer（SRC-01 P9）；Mastercard 争议经 **Mastercom**（SRC-02 P33）；中国大陆境内走 China Switch / 中国大陆争议解决平台，结算以 EREC 记录 advice reason code 7007800（SRC-02 P849、P1409、P1499）；Visa 认证经 Visa Resolve Online 提交（SRC-01 P59）。
- 结果如何到账：预仲裁接受后 GCMS "On-Behalf" Fee Collection/1740（码 7800）或 MCBS Billing Event 自动划款（SRC-02 P486 等）；仲裁裁定发布方式与上诉（P1409–1410）。

**书中没有的**：OceanPayment 作为中间层，材料到底提交给哪个具体上游主体（收单机构？Mastercom 直连？Visa Resolve Online？），以及结果（回执/裁定/资金划拨）通过什么渠道、以什么格式回传进 OceanPayment。

**建议获取答案的渠道**：与收单机构确认提交流程与回执接口；对照 SRC-02 P486/P1409 的消息要素设计"提交回执"与"裁定结果"两个适配器。

---

## 附：与案例库的联动

- 上述 5 项的确认结果应回写到案例库 `provenance.conflict_status / verification_status` 与 `10_conflicts_and_data_gaps.md` 的 NEEDS_CONFIRMATION 清单（问题 1/5 对应新增 GAP，问题 2/3/4 对应 GAP-009/GAP-001/CONFLICT-006~008）。
- 确认前，案例库中涉及"实际 SLA、具体上游主体、操作权限"的演示设定（合成案例的 deadline、revision、幂等、权限模型）继续以 SYNTHETIC_DEMO 标注，`production_eligible=false`。
