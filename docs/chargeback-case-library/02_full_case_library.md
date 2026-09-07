# OceanPilot 拒付案例库（完整版）

> 生成时间：2026-09-07T11:48:36Z ｜ 案例总数：62（SOURCE_EXPLICIT 34 / RULE_DERIVED 13 / SYNTHETIC_DEMO 15）
> 证据纪律：SOURCE_EXPLICIT=原文明确案例；RULE_DERIVED=规则还原场景；SYNTHETIC_DEMO=项目合成案例（虚构）。
> 缺失值约定：NOT_STATED=原文未说明；NOT_APPLICABLE=不适用；NEEDS_CONFIRMATION=需业务确认。

## CB-CASE-001｜SOURCE_EXPLICIT｜油漆工泼漆——侵权损失不能用拒付追偿

- **一句话场景**：持卡人雇人刷墙 USD 500，工人打翻油漆毁沙发 USD 300，发卡行不能用 4853/4854 对 USD 300 拒付。
- **业务分类**：卡组织 Mastercard｜原因码 4853/4854（Cardholder Dispute / NEC）｜大类 Consumer Dispute｜行业 家装服务｜渠道 线下｜交易类型 服务｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P152; P460; P950; P1157｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：a cardholder contracts with a painter to paint his or her living room for USD 500. The painter accidentally spills paint on the couch, causing USD 300 worth of damage.
- **参与者**：cardholder=持卡人（房主）；issuer=发卡行；acquirer=收单行；merchant=油漆工/家装商户；platform=无
- **资金关系**：who_paid_whom：持卡人向商户支付 USD 500 服务费；who_initiated：持卡人向发卡行主张拒付；who_received_notice：商户（经收单行）；who_bears_risk：侵权损失 USD 300 不属于拒付受理范围
- **交易事实**：金额 USD 500（合同）；USD 300（损坏）｜时间 NOT_STATED｜商品 客厅粉刷服务｜渠道 卡支付｜认证 NOT_STATED｜履约 服务已完成；沙发受损｜退款 NOT_STATED
- **拒付事实**：触发 持卡人要求对沙发损坏 USD 300 拒付｜持卡人主张 商家造成额外损失｜通知 发卡行不得使用 4853/4854 拒付 USD 300｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 NOT_STATED｜建议 信息不足（依据：原文仅说明侵权不属拒付范围，未给出可执行建议）
- **所需证据**：
  - 规则界定（RULE，必填）——为何需要：明确侵权(torts)不在 4853/4854 受理范围；规则依据：SRC-02 P152/P460/P950/P1157；本案可得性：不适用；缺失后果：误拒付会导致收单方用 2713/Invalid Chargeback 抗辩
- **处理流程**：first_see：案件进入系统后即标记为规则排除类型 → auto：规则引擎识别 tort 类争议 → ops：运营人员无需处理 → agent：可解释为何该案不能拒付 → human：无需人工确认 → reviewer：无需审核 → submit_condition：不允许提交 → upstream_result：NOT_STATED → final_status：CLOSED_INELIGIBLE
- **结局**：未说明（依据：原文只说明不得拒付，无后续裁定）｜成功因素：N/A｜失败因素：N/A｜可否预防：NOT_STATED｜商户改进：为服务场景购买责任保险；条款中明确损失责任｜未决问题：侵权纠纷的替代解决路径原文未说明
- **OceanPilot 映射**：演示 ✓｜seed —｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：案件详情、Agent 解释、规则引擎
  - 演示步骤：打开案件→Agent 解释为何该案不可拒付
- **核心案例**：是（通俗规则示例，适合规则引擎边界测试与路演说明）

## CB-CASE-002｜SOURCE_EXPLICIT｜终身会员商户倒闭——服务中断按 18 个月折算拒付

- **一句话场景**：USD 1,000 终身会员，商户 3 个月后倒闭，可拒付金额 = 1000/18×(18−3) ≈ USD 833。
- **业务分类**：卡组织 Mastercard｜原因码 4853（Cardholder Dispute）｜大类 Consumer Dispute｜行业 订阅/会员服务｜渠道 订阅｜交易类型 服务（终身会员）｜数据来源类别 卡组织规则内置示例（含明确算式）
- **来源**：SRC-02｜定位：P178; P968; P1511｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：the cardholder purchased a lifetime membership for USD 1,000. The merchant goes out of business after three months. The amount to be charged back is USD 833
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=会员服务商户（已倒闭）；platform=无
- **资金关系**：who_paid_whom：持卡人向商户预付 USD 1,000；who_initiated：持卡人向发卡行主张拒付；who_received_notice：商户/收单行；who_bears_risk：商户承担未提供服务的对价（USD 833）
- **交易事实**：金额 USD 1,000（应付拒付 USD 833）｜时间 NOT_STATED（服务持续 3 个月后中断）｜商品 终身会员｜渠道 卡支付｜认证 NOT_STATED｜履约 服务中断（商户倒闭）｜退款 NOT_STATED
- **拒付事实**：触发 商户倒闭，服务中断｜持卡人主张 购买的服务未能继续提供｜通知 4853 拒付｜收到时间 NOT_STATED｜截止 120 天（服务中断，上限 540 天）｜商户立场 已倒闭无法响应｜建议 条件性（依据：原文给出可拒付金额算法，商户若仍在经营应以已提供部分对冲）
- **所需证据**：
  - 18 个月折算规则（CALCULATION_RULE，必填）——为何需要：确定服务中断类拒付金额；规则依据：SRC-02 P178/P968/P1511；本案可得性：是（原文自带算式）；缺失后果：金额算错会被 2713/2702 抗辩
- **处理流程**：first_see：案件金额自动按公式折算 → auto：系统计算 1000/18×15=833 → ops：运营确认金额与中断时间 → agent：解释折算规则与拒付金额 → human：确认服务中断事实 → reviewer：审核折算结果 → submit_condition：金额与时间证据齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：原文只给出可拒付金额，未给最终裁定）｜成功因素：金额计算正确｜失败因素：商户证明服务等价替代｜可否预防：NOT_STATED｜商户改进：分期确认收入；倒闭前退还会员余款｜未决问题：商户已倒闭时资金追回路径
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：案件详情、金额计算、Agent 解释
  - 演示步骤：展示自动折算金额→人工确认→提交
- **核心案例**：是（唯一带明确计算公式的金额案例）

## CB-CASE-003｜SOURCE_EXPLICIT｜花瓶海运——签署“发货即免责”弃权书后商户免责

- **一句话场景**：持卡人签弃权书（发货证明即约束持卡人），花瓶未到但商户能证明已发货，不可拒付；拒绝购买运输保险同理需弃权书+发货凭证。
- **业务分类**：卡组织 Mastercard｜原因码 4853（Cardholder Dispute）｜大类 Consumer Dispute｜行业 跨境电商（实物）｜渠道 线上｜交易类型 实物商品（海运）｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P178; P968; P1511｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：A cardholder purchases vases and arranges with the merchant to have the vases shipped to the United States... signs a waiver form... 'PROOF OF DISPATCH OF THE MERCHANDISE WILL BIND THE CARDHOLDER.'
- **参与者**：cardholder=持卡人（买方）；issuer=发卡行；acquirer=收单行；merchant=跨境电商商户；platform=承运方（海运）
- **资金关系**：who_paid_whom：持卡人向商户支付货款；who_initiated：持卡人主张未收到货；who_received_notice：商户/收单行；who_bears_risk：持卡人已通过弃权书自担运输风险
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 花瓶（运往美国）｜渠道 卡支付｜认证 NOT_STATED｜履约 已发货但未送达｜退款 NOT_STATED
- **拒付事实**：触发 花瓶未到货｜持卡人主张 商品未收到｜通知 4853 拒付｜收到时间 NOT_STATED｜截止 120 天（未收到商品类）｜商户立场 已发货且有弃权书｜建议 抗辩（依据：原文明确：签署弃权书即免除商户责任，商户应提交弃权书+发货证明抗辩）
- **所需证据**：
  - 持卡人签署的免责弃权书（WAIVER，必填）——为何需要：证明持卡人同意以发货证明为履约标准；规则依据：SRC-02 P178/P968/P1511；本案可得性：是；缺失后果：无弃权书则无法免除运输责任
  - 发货凭证（SHIPPING，必填）——为何需要：证明商品已实际发出；规则依据：同上；本案可得性：是；缺失后果：无法构成抗辩
- **处理流程**：first_see：系统标记该案含弃权书类证据 → auto：证据清单预置弃权书+发货凭证两项 → ops：上传两项证据 → agent：解释弃权书规则的适用条件 → human：确认为持卡人本人签署 → reviewer：审核后放行提交 → submit_condition：两项证据齐全且通过校验 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：原文说明商户免责（不可拒付），未给裁定记录）｜成功因素：弃权书有效+发货证明完整｜失败因素：弃权书被证伪或未经披露｜可否预防：是｜商户改进：跨境高风险运输一律让买家签署弃权书或购买保险｜未决问题：弃权书在各地区的效力差异
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：证据上传与抽取、案件详情、Agent 解释
  - 演示步骤：展示证据清单→上传弃权书与发货单→Agent 解释→提交
- **关联案例**：CB-CASE-029

## CB-CASE-004｜SOURCE_EXPLICIT｜空箱/砖块——收到无价值物品按“商品未提供”拒付

- **一句话场景**：持卡人收到空箱或装砖块、废纸的箱子，适用 Goods or Services Not Provided 拒付。
- **业务分类**：卡组织 Mastercard｜原因码 4853（Cardholder Dispute（Goods/Services Not Provided））｜大类 Consumer Dispute｜行业 电商（实物）｜渠道 线上｜交易类型 实物商品｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P178; P967; P1511｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：This chargeback applies when the cardholder receives an empty box or a box containing worthless items, such as a brick or a stack of paper.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=电商商户；platform=物流承运方
- **资金关系**：who_paid_whom：持卡人向商户支付货款；who_initiated：持卡人主张收到空箱；who_received_notice：商户/收单行；who_bears_risk：商户需证明实际交付了对应商品
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED（无价值物品替代）｜渠道 卡支付｜认证 NOT_STATED｜履约 已签收但内容为空箱/砖块｜退款 NOT_STATED
- **拒付事实**：触发 收到空箱/无价值物品｜持卡人主张 商品未收到｜通知 4853 拒付｜收到时间 NOT_STATED｜截止 120 天｜商户立场 NOT_STATED｜建议 抗辩（依据：商户可用签收/称重/监控等证据证明交付的是正确商品；原文未建议接受）
- **所需证据**：
  - 签收证明（DELIVERY，可选）——为何需要：证明包裹由持卡人签收；规则依据：SRC-02 P183/P972；本案可得性：视案件而定；缺失后果：降低抗辩可信度
  - 称重/监控/打包记录（LOGISTICS，可选）——为何需要：证明发出时内容物正确；规则依据：SRC-02 P178/P967；本案可得性：视案件而定；缺失后果：难以反驳“空箱”主张
- **处理流程**：first_see：系统提示该案需物流侧证据 → auto：调用物流记录与签收信息 → ops：补传称重/打包证据 → agent：解释空箱规则与举证方向 → human：确认证据真实性 → reviewer：审核 → submit_condition：至少具备签收+发货记录 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：原文仅界定拒付适用范围）｜成功因素：发货重量与物流记录完整｜失败因素：无任何物流证据｜可否预防：部分可预防｜商户改进：高价值商品称重留存、签收拍照｜未决问题：恶意“空箱索赔”的识别手段
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、证据上传、Agent 解释
  - 演示步骤：展示规则归属→上传物流证据
- **关联案例**：CB-CASE-045

## CB-CASE-005｜SOURCE_EXPLICIT｜退款收据被篡改——商户可用“疑似篡改单据”抗辩

- **一句话场景**：持卡人把退款收据涂改成更大金额，商户可合理说明篡改情况并二次呈请（码 2001）。
- **业务分类**：卡组织 Mastercard｜原因码 4853（抗辩码 2001）（Cardholder Dispute / Suspected Altered Documentation）｜大类 Consumer Dispute / Fraud｜行业 通用零售｜渠道 线上/线下｜交易类型 商品/服务｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P162; P184; P335; P694; P957; P1094; P1330｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：a refund receipt was altered to show a larger refund amount.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=无
- **资金关系**：who_paid_whom：持卡人向商户付款，商户部分/全额退款；who_initiated：持卡人提交被篡改单据主张拒付；who_received_notice：商户/收单行；who_bears_risk：若抗辩成立，争议金额回到持卡人
- **交易事实**：金额 NOT_STATED（退款金额被改大）｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 NOT_STATED｜退款 有退款但单据金额被篡改
- **拒付事实**：触发 退款金额争议｜持卡人主张 应退更多｜通知 拒付（退款未处理类）｜收到时间 NOT_STATED｜截止 30/45 天（地区而异）｜商户立场 退款已按正确金额处理，单据被篡改｜建议 抗辩（依据：原文给出明确抗辩路径：合理具体说明篡改事实，码 2001）
- **所需证据**：
  - 商户对篡改的合理具体说明（MERCHANT_NARRATIVE，必填）——为何需要：说明单据如何被部分篡改或伪造；规则依据：SRC-02 P162/P957；本案可得性：视案件而定；缺失后果：抗辩不成立
- **处理流程**：first_see：系统提示疑似单据篡改场景 → auto：比对上传单据与商户底账 → ops：撰写说明并上传底账 → agent：提示 2001 抗辩码与所需说明 → human：确认篡改事实 → reviewer：审核说明完整性 → submit_condition：说明+底账齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：原文仅描述抗辩路径）｜成功因素：底账清晰、说明具体｜失败因素：无法证明篡改｜可否预防：是｜商户改进：退款单据电子化防篡改（PDF/邮件留底）｜未决问题：Mastercard 对“合理具体”的判定标准
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、证据上传、Agent 解释
  - 演示步骤：上传底账→Agent 生成说明模板

## CB-CASE-006｜SOURCE_EXPLICIT｜退货欺诈——面霜换酸奶/零件被调换

- **一句话场景**：退回商品被替换（面霜变酸奶、零件被换低质件），商户可用疑似退货欺诈（码 2004）抗辩。
- **业务分类**：卡组织 Mastercard｜原因码 4853（抗辩码 2004）（Cardholder Dispute / Suspected Return Fraud）｜大类 Consumer Dispute｜行业 零售/电子商品｜渠道 线上｜交易类型 实物商品（退货）｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P163; P279; P958; P1042｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：Returned product was replaced with a substance that resembled the original product (for example, face moisturizer replaced with yogurt)... parts removed and replaced with lower quality parts.
- **参与者**：cardholder=持卡人（退货方）；issuer=发卡行；acquirer=收单行；merchant=商户；platform=退货物流
- **资金关系**：who_paid_whom：持卡人付款后申请退款；who_initiated：持卡人主张已退货应退款；who_received_notice：商户/收单行；who_bears_risk：商户承担退款，除非证明退货欺诈
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 面霜/含零件商品｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 退货件已到但内容被调换｜退款 NOT_STATED
- **拒付事实**：触发 退货退款争议｜持卡人主张 已退货未退款｜通知 拒付（退款未处理类）｜收到时间 NOT_STATED｜截止 30/45 天（地区而异）｜商户立场 退回商品被调换｜建议 抗辩（依据：原文给出 2004 抗辩路径：说明退回商品如何被改动）
- **所需证据**：
  - 退货开箱检验记录（RETURN_INSPECTION，必填）——为何需要：证明退回物品与原商品不符；规则依据：SRC-02 P163/P958/P1042；本案可得性：视案件而定；缺失后果：无法证明退货欺诈
- **处理流程**：first_see：系统标记退货类争议 → auto：关联退货物流记录 → ops：上传开箱记录 → agent：提示 2004 抗辩码 → human：确认调换事实 → reviewer：审核 → submit_condition：检验记录齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：原文仅描述抗辩路径）｜成功因素：开箱视频完整｜失败因素：退货验收缺失｜可否预防：是｜商户改进：退货全程录像、称重登记｜未决问题：调换举证责任边界
- **OceanPilot 映射**：演示 ✓｜seed —｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、证据上传、Agent 解释
  - 演示步骤：上传开箱视频→生成抗辩说明

## CB-CASE-007｜SOURCE_EXPLICIT｜部分授权与撤销——USD 100/75/74.99 规则

- **一句话场景**：授权请求 USD 100、部分批准 USD 75，部分撤销必须 ≤ USD 74.99，否则收单行对未撤销余额担责；全额批准后全额撤销则交易与批准全部取消。
- **业务分类**：卡组织 Mastercard｜原因码 4808（Authorization-related Chargeback）｜大类 Authorization｜行业 通用（规则）｜渠道 线上/线下｜交易类型 规则金额示例｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P64-65; P84; P934｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：An authorization is requested for USD 100, the issuer partially approved USD 75, the partial reversal must be USD 74.99 or less.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=无
- **资金关系**：who_paid_whom：持卡人向商户付款；who_initiated：发卡行发起授权类拒付；who_received_notice：收单行/商户；who_bears_risk：收单行对未撤销余额担责
- **交易事实**：金额 USD 100 / USD 75 / USD 74.99｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 授权+部分批准｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 授权类拒付（4808）｜持卡人主张 N/A（发卡行主张）｜通知 4808 拒付｜收到时间 NOT_STATED｜截止 90 天（其他交易）｜商户立场 授权已正确取得｜建议 抗辩（依据：若授权与撤销流程正确，可用 2008/2713 抗辩）
- **所需证据**：
  - 授权与撤销报文记录（AUTHORIZATION_LOG，必填）——为何需要：证明批准与撤销金额符合规则；规则依据：SRC-02 P64-65/P934；本案可得性：视案件而定；缺失后果：无法抗辩
- **处理流程**：first_see：系统自动比对授权/撤销数据 → auto：规则引擎校验金额关系 → ops：查看比对结果 → agent：解释 74.99 规则 → human：无需 → reviewer：确认后放行 → submit_condition：金额比对通过 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：原文仅说明责任归属规则）｜成功因素：撤销金额正确｜失败因素：撤销不足额｜可否预防：是｜商户改进：收单系统严格按批准额做部分撤销｜未决问题：边界 74.99 的适用地区差异
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎、案件详情、Agent 解释
  - 演示步骤：展示授权/撤销比对→自动判定

## CB-CASE-008｜SOURCE_EXPLICIT｜美国自动加油机 USD 1 授权与 500/175 门槛

- **一句话场景**：美国 MCC 5542 加油机以 USD 1 授权：公司卡 ≤ USD 500、其他卡 ≤ USD 175 不得拒付，超出部分只扣差额。
- **业务分类**：卡组织 Mastercard｜原因码 4808（Authorization-related Chargeback）｜大类 Authorization｜行业 加油/交通｜渠道 线下（无人终端）｜交易类型 规则金额示例｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P61; P885-886｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：US MCC 5542 AFD transactions authorized for USD 1: corporate cards ≤ USD 500 and other cards ≤ USD 175 cannot be charged back; only the excess amount.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=加油站；platform=无
- **资金关系**：who_paid_whom：持卡人向加油站付款；who_initiated：发卡行发起授权类拒付；who_received_notice：收单行/商户；who_bears_risk：超额部分商户担责
- **交易事实**：金额 USD 1（授权）/ USD 500 / USD 175（门槛）｜时间 NOT_STATED｜商品 加油｜渠道 卡支付（CAT 1/2/6）｜认证 USD 1 小额预授权｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 授权相关拒付｜持卡人主张 N/A（发卡行主张）｜通知 4808 拒付｜收到时间 NOT_STATED｜截止 90 天｜商户立场 金额在免授权门槛内｜建议 抗辩（依据：门槛内不可拒付，可 2713 抗辩；超额部分仅退差额）
- **所需证据**：
  - 交易记录（MCC/金额/授权）（TX_RECORD，必填）——为何需要：判断是否落在门槛内；规则依据：SRC-02 P61/P885-886；本案可得性：是；缺失后果：无法自动判定
- **处理流程**：first_see：系统按 MCC 与卡类型判定门槛 → auto：自动计算可拒付差额 → ops：无需 → agent：解释门槛规则 → human：无需 → reviewer：无需 → submit_condition：门槛规则命中 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则示例）｜成功因素：MCC/卡类型判定正确｜失败因素：数据缺失｜可否预防：是｜商户改进：正确标识 MCC 与 CAT 级别｜未决问题：门槛是否随版本调整
- **OceanPilot 映射**：演示 —｜seed —｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎

## CB-CASE-009｜SOURCE_EXPLICIT｜CAT 3 无人终端限额与公交 split clearing

- **一句话场景**：CAT 3 限额（香港 HKD 500 / 欧洲 EUR 50 / 其他 USD 40）超出可拒付；英国非接触公交 GBP 0.10 授权后 14 天内 split clearing 属正确标识不可拒付。
- **业务分类**：卡组织 Mastercard｜原因码 4808（Authorization-related Chargeback）｜大类 Authorization｜行业 交通/无人零售｜渠道 线下（无人终端）｜交易类型 小额非接触｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P115; P921-922; P56-57｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：CAT 3 limits: Hong Kong MCC 7523 HKD 500; Europe EUR 50; other CAT 3 USD 40 or local equivalent.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=交通/无人终端商户；platform=无
- **资金关系**：who_paid_whom：持卡人小额非接触支付；who_initiated：发卡行授权类拒付；who_received_notice：收单行/商户；who_bears_risk：超限部分商户担责
- **交易事实**：金额 HKD 500 / EUR 50 / USD 40 / GBP 0.10｜时间 NOT_STATED｜商品 公交/无人终端服务｜渠道 非接触/contactless transit aggregated｜认证 小额免密/CTA｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 授权类拒付（CAT 3 违规）｜持卡人主张 N/A｜通知 4808｜收到时间 NOT_STATED｜截止 90 天｜商户立场 交易在限额内且标识正确｜建议 抗辩（依据：限额内不可拒付；正确标识 split clearing 不可拒付（2707/2713））
- **所需证据**：
  - 终端标识与交易要素（TERMINAL_DATA，必填）——为何需要：证明 CAT 级别、MCC、金额、标识正确；规则依据：SRC-02 P115/P921-922；本案可得性：视案件而定；缺失后果：无法抗辩
- **处理流程**：first_see：自动判定 CAT3/限额 → auto：规则引擎校验 → ops：无需 → agent：解释限额表 → human：无需 → reviewer：无需 → submit_condition：规则命中 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则示例）｜成功因素：终端标识正确｜失败因素：标识缺失｜可否预防：是｜商户改进：终端配置符合 CAT 3 要求｜未决问题：限额调整节奏
- **OceanPilot 映射**：演示 —｜seed —｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎

## CB-CASE-010｜SOURCE_EXPLICIT｜分期 vs 循环扣款三连例

- **一句话场景**：每月 EUR 250×3 年购车=分期；每月 EUR 25 健身会员（无终止日）=循环；水电自动扣款=循环。定性决定适用 4850 还是循环拒付规则。
- **业务分类**：卡组织 Mastercard｜原因码 4853/4850（Cardholder Dispute / Installment Billing Dispute）｜大类 Consumer Dispute｜行业 汽车零售/健身/公用事业｜渠道 订阅/分期｜交易类型 周期扣款｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P312; P330; P1064; P1076｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：A cardholder contracted to pay EUR 250 on a monthly basis for three years for an automobile. This transaction is an installment transaction because an end date is specified.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=汽车商/健身房/公用事业；platform=无
- **资金关系**：who_paid_whom：持卡人按周期向商户付款；who_initiated：持卡人主张取消/未授权；who_received_notice：商户/收单行；who_bears_risk：定性错误导致规则错用
- **交易事实**：金额 EUR 250/月；EUR 25/月；NOT_STATED｜时间 NOT_STATED｜商品 汽车/健身会员/水电｜渠道 周期扣款｜认证 MIT/Recurring｜履约 持续提供｜退款 NOT_STATED
- **拒付事实**：触发 循环扣款争议｜持卡人主张 已取消仍扣款/非循环｜通知 4853（循环争议）｜收到时间 NOT_STATED｜截止 120 天｜商户立场 有终止日→分期；无终止日→循环｜建议 条件性（依据：先按合同终止日判定交易类型，再决定抗辩路径）
- **所需证据**：
  - 合同/扣款协议（AGREEMENT，必填）——为何需要：判断有无终止日；规则依据：SRC-02 P312/P330；本案可得性：视案件而定；缺失后果：无法正确定性
- **处理流程**：first_see：系统询问合同终止日 → auto：预分类 installment/recurring → ops：上传合同 → agent：解释两类定性标准 → human：确认定性 → reviewer：审核 → submit_condition：合同齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则示例）｜成功因素：定性正确｜失败因素：把分期误当循环｜可否预防：是｜商户改进：签约时明确终止日与取消条款｜未决问题：混合型订阅的定性
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：案件详情、规则引擎、Agent 解释
  - 演示步骤：上传合同→Agent 定性→确认
- **关联案例**：CB-CASE-027

## CB-CASE-011｜SOURCE_EXPLICIT｜Addendum 后续费用：房账餐费与租车停车罚单

- **一句话场景**：与有效原交易关联的后续单独收费属于 addendum（房账餐费、租车期间停车罚单）；两笔独立交易（早/午餐）或直接刷卡餐费则不是。
- **业务分类**：卡组织 Mastercard｜原因码 4853/4837（Cardholder Dispute / No Cardholder Authorization）｜大类 Consumer Dispute / Fraud｜行业 酒店/租车｜渠道 线下｜交易类型 后续附加收费｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P350; P353; P501; P1090; P1093; P1189｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：A transaction for a meal eaten in the hotel restaurant and charged to the cardholder's room, but not included in the final hotel folio... billed for a separate additional amount that represents unpaid parking tickets.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=酒店/租车行；platform=当地交管（罚单来源）
- **资金关系**：who_paid_whom：持卡人先付原交易，后被追加收费；who_initiated：持卡人主张未授权后续扣款；who_received_notice：商户/收单行；who_bears_risk：商户需证明持卡人对 addendum 负责
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED（罚单须在收到交管通知后 30 个日历日内呈报）｜商品 餐费挂房账/停车罚单｜渠道 卡支付｜认证 NOT_STATED｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 后续费用被拒付｜持卡人主张 未授权该笔后续收费｜通知 4853（Addendum）/4837｜收到时间 NOT_STATED｜截止 120 天｜商户立场 属有效原交易之后的 addendum｜建议 抗辩（依据：证明持卡人参与原交易且对后续费用负责（如租约+罚单发生时间））
- **所需证据**：
  - 原交易合同/租赁协议（ORIGINAL_AGREEMENT，必填）——为何需要：证明持卡人参与原交易；规则依据：SRC-02 P350/P353/P501；本案可得性：视案件而定；缺失后果：无法证明 addendum 关系
  - 违章记录（30 日内提交）（VIOLATION_RECORD，必填）——为何需要：证明罚单发生于租期内；规则依据：SRC-02 P353/P1093；本案可得性：视案件而定；缺失后果：抗辩失败
- **处理流程**：first_see：系统识别 addendum 类型 → auto：关联原交易 → ops：上传租约与罚单 → agent：解释 addendum 规则 → human：确认证据对应关系 → reviewer：审核 → submit_condition：两项证据齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则示例）｜成功因素：原交易+罚单时间线清晰｜失败因素：证据缺失｜可否预防：是｜商户改进：租约明确后续费用条款｜未决问题：各国罚单规则的差异
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：案件详情、证据上传、Agent 解释
  - 演示步骤：关联原交易→上传证据→提交

## CB-CASE-012｜SOURCE_EXPLICIT｜酒店 No-show 费：满房改宿错收费与 18:00 取消时限

- **一句话场景**：到店无房被安排他店却仍被收费可拒付；商户提前告知 18:00 前未取消收一晚房费+税则可抗辩；持卡人需以电话账单证明按时取消。
- **业务分类**：卡组织 Mastercard｜原因码 4853（Cardholder Dispute（No-Show））｜大类 Consumer Dispute｜行业 酒店｜渠道 预订｜交易类型 住宿预订（No-show）｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P368; P371; P381; P1103; P1106; P1112｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：the cardholder arrived at the hotel and no room was available... the merchant billed the cardholder in error... no-show fee if the reservation was not cancelled before 18:00 (merchant's local time).
- **参与者**：cardholder=持卡人（住客）；issuer=发卡行；acquirer=收单行；merchant=酒店；platform=替代住宿酒店
- **资金关系**：who_paid_whom：持卡人支付房费；who_initiated：持卡人主张错收/no-show 费不当；who_received_notice：酒店/收单行；who_bears_risk：错误收费由酒店承担
- **交易事实**：金额 一晚房费+税（no-show 费）｜时间 NOT_STATED（预订当日 18:00 为取消门槛）｜商品 住宿预订｜渠道 卡支付/预订担保｜认证 NOT_STATED｜履约 未入住/替代住宿｜退款 NOT_STATED
- **拒付事实**：触发 no-show 费争议｜持卡人主张 已取消预订或商户错收费｜通知 4853｜收到时间 NOT_STATED｜截止 120 天｜商户立场 有正式 Guaranteed Reservation 且已提前告知政策｜建议 条件性（依据：视取消证据与告知义务履行情况决定）
- **所需证据**：
  - 预订前政策告知证明（CANCELLATION_NOTICE，必填）——为何需要：证明已告知 18:00 前取消的收费政策；规则依据：SRC-02 P371/P1106；本案可得性：视案件而定；缺失后果：无法收取 no-show 费
  - 电话账单（取消时限内联系证明）（PHONE_BILL，条件性）——为何需要：持卡人主张已取消时，预仲裁阶段需证明在时限内联系过商户；规则依据：SRC-02 P381/P1112；本案可得性：视案件而定；缺失后果：取消主张不成立
- **处理流程**：first_see：系统判定 no-show 类 → auto：检查政策告知时间 → ops：上传告知与取消记录 → agent：解释 18:00 规则 → human：确认取消时间线 → reviewer：审核 → submit_condition：告知证明齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则示例）｜成功因素：告知完整+无取消记录｜失败因素：未提前告知｜可否预防：是｜商户改进：预订确认函中明示取消政策｜未决问题：时区与本地时间认定
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：案件详情、证据上传、Agent 解释
  - 演示步骤：展示政策告知证据→判定
- **关联案例**：CB-CASE-033

## CB-CASE-013｜SOURCE_EXPLICIT｜变更拒付原因：货到了但已损坏

- **一句话场景**：原拒付称货未收到，争议中货到达但损坏——发卡行可在预仲裁中变更为“货不对板”原因；为规避欺诈责任而换码无效。
- **业务分类**：卡组织 Mastercard｜原因码 4853（Change of Reason）（Cardholder Dispute）｜大类 Consumer Dispute｜行业 电商（实物）｜渠道 线上｜交易类型 实物商品｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P477; P1171｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：the original chargeback claims the goods were not received; however, during the course of the dispute the goods arrived damaged.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=电商商户；platform=物流方
- **资金关系**：who_paid_whom：持卡人向商户付款；who_initiated：发卡行变更原因继续争议；who_received_notice：商户/收单行；who_bears_risk：商户需应对新原因的举证
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED（延迟到达且损坏）｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 延迟到达且损坏｜退款 NOT_STATED
- **拒付事实**：触发 货物状态与原始主张变化｜持卡人主张 先称未收到，后称损坏｜通知 Change of Reason 预仲裁｜收到时间 NOT_STATED｜截止 预仲裁 30 天（自 SP 结算日）｜商户立场 二次呈请已补救原拒付｜建议 条件性（依据：商户应对新原因补充证据（如商品完好证明））
- **所需证据**：
  - 新原因所需支持文档（NEW_REASON_DOCS，必填）——为何需要：应对变更后的争议原因；规则依据：SRC-02 P477-478/P1171；本案可得性：视案件而定；缺失后果：新原因下败诉
- **处理流程**：first_see：系统标记 Change of Reason → auto：重新匹配规则与证据清单 → ops：补充新证据 → agent：解释变更规则 → human：确认新原因 → reviewer：审核 → submit_condition：新证据齐全 → upstream_result：NOT_STATED → final_status：PRE_ARBITRATION
- **结局**：未说明（依据：规则示例）｜成功因素：及时补充新证据｜失败因素：沿袭旧原因抗辩｜可否预防：是｜商户改进：监控物流状态并主动沟通｜未决问题：变更原因的时间上限
- **OceanPilot 映射**：演示 ✓｜seed —｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎、案件详情、Agent 解释
  - 演示步骤：模拟原因变更→证据清单刷新

## CB-CASE-014｜SOURCE_EXPLICIT｜墨西哥酒店币种错乱——报价 24,000 比索扣了 24,000 欧元

- **一句话场景**：报价比索按欧元扣款、报价欧元按比索扣款可拒付差额；仅“信息性”展示外币金额不构成拒付理由。
- **业务分类**：卡组织 Mastercard｜原因码 4834（Currency Errors）（Point-of-Interaction Error）｜大类 Processing Error｜行业 酒店/旅游｜渠道 线上预订｜交易类型 币种错误｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P741-742; P1371｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：A merchant located in Mexico quoted the hotel reservation for 24,000 Pesos. The cardholder's currency is Euros. The transaction was performed for 24,000 Euros.
- **参与者**：cardholder=持卡人（欧元账户）；issuer=发卡行；acquirer=收单行；merchant=墨西哥酒店；platform=无
- **资金关系**：who_paid_whom：持卡人按错误币种被扣款；who_initiated：持卡人主张币种错误；who_received_notice：商户/收单行；who_bears_risk：差额部分由商户承担
- **交易事实**：金额 24,000（比索/欧元）｜时间 NOT_STATED｜商品 酒店预订｜渠道 卡支付｜认证 NOT_STATED｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 币种错误｜持卡人主张 被以错误币种扣款｜通知 4834 Currency Errors｜收到时间 NOT_STATED｜截止 90 天｜商户立场 报价与扣款币种一致或仅信息展示｜建议 条件性（依据：确认报价币种与实际扣款币种，差额退还是抗辩）
- **所需证据**：
  - 显示金额与币种的收据（RECEIPT，必填）——为何需要：证明扣款币种与报价关系；规则依据：SRC-02 P741-742/P1371；本案可得性：视案件而定；缺失后果：无法判定差额
- **处理流程**：first_see：系统标记币种争议 → auto：按交易当日汇率计算差额 → ops：上传收据 → agent：解释币种规则与差额计算 → human：确认报价与扣款币种 → reviewer：审核 → submit_condition：差额计算确认 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则示例）｜成功因素：报价记录清晰｜失败因素：仅信息展示却被误判｜可否预防：是｜商户改进：支付页明确扣款币种并二次确认｜未决问题：信息性展示的认定标准
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎、案件详情、Agent 解释
  - 演示步骤：展示差额自动计算
- **关联案例**：CB-CASE-015

## CB-CASE-015｜SOURCE_EXPLICIT｜丹麦 ATM 选欧元却按克朗扣款

- **一句话场景**：法国持卡人在丹麦 ATM 选择欧元取现但交易按丹麦克朗执行可拒付；ATM 仅“信息性”显示欧元则不可拒付。
- **业务分类**：卡组织 Mastercard｜原因码 4834（ATM Cash and Currency Errors）（Point-of-Interaction Error）｜大类 Processing Error｜行业 银行/ATM｜渠道 线下（ATM）｜交易类型 ATM 取现币种错误｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P741; P872-873｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：A cardholder from France used an ATM located in Denmark. The ATM offered to dispense the cash in either Danish Krone or Euros. The cardholder chose Euros. The ATM transaction was performed in the Danish Krone.
- **参与者**：cardholder=法国持卡人；issuer=发卡行；acquirer=ATM 收单行；merchant=ATM 所有人；platform=无
- **资金关系**：who_paid_whom：持卡人从 ATM 取现；who_initiated：持卡人主张币种处理错误；who_received_notice：ATM 收单行；who_bears_risk：ATM 侧承担币种错误差额
- **交易事实**：金额 NOT_STATED（差额）｜时间 NOT_STATED｜商品 ATM 取现｜渠道 ATM｜认证 卡+选择币种｜履约 现金已取出但币种错误｜退款 NOT_STATED
- **拒付事实**：触发 币种错误｜持卡人主张 选择了欧元却按克朗执行｜通知 4834｜收到时间 NOT_STATED｜截止 欧洲发卡 ATM 120 天｜商户立场 交易按正确币种执行或仅信息展示｜建议 条件性（依据：正例可拒付差额；反例应抗辩）
- **所需证据**：
  - ATM 日志与币种选择记录（ATM_JOURNAL，必填）——为何需要：证明持卡人的币种选择与实际执行；规则依据：SRC-02 P872-873；本案可得性：视案件而定；缺失后果：无法判定
- **处理流程**：first_see：系统标记 ATM 币种争议 → auto：读取 ATM 日志 → ops：核对选择记录 → agent：解释正反例规则 → human：确认 → reviewer：审核 → submit_condition：日志齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则示例）｜成功因素：日志完整｜失败因素：仅信息展示被误读｜可否预防：是｜商户改进：ATM 界面明确所选币种｜未决问题：欧洲以外 ATM 规则差异
- **OceanPilot 映射**：演示 —｜seed —｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎
- **关联案例**：CB-CASE-014

## CB-CASE-016｜SOURCE_EXPLICIT｜双重入账与善意催款函流程

- **一句话场景**：持卡人既获拒付退款又收商户退款（双重入账），收单行须及时二次呈请注明退款；超期只能走流程外善意催款函，发卡行书面接受后按 Fee Collection/1740 划款。
- **业务分类**：卡组织 Mastercard｜原因码 2011（Refund previously issued）（Credit Previously Issued）｜大类 Processing Error（流程）｜行业 通用（流程）｜渠道 通用｜交易类型 退款/拒付流程｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P38; P68-69; P510-512; P935｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：a good faith collection letter is written correspondence from the acquirer to the issuer requesting the return of the refunded amount.
- **参与者**：cardholder=持卡人（被双重入账）；issuer=发卡行；acquirer=收单行；merchant=商户（已退款）；platform=无
- **资金关系**：who_paid_whom：商户退款+发卡行拒付退款双重入账；who_initiated：收单行追回多退资金；who_received_notice：发卡行；who_bears_risk：超期则追回困难
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 NOT_STATED｜退款 已退款
- **拒付事实**：触发 双重入账｜持卡人主张 N/A｜通知 拒付已发生｜收到时间 NOT_STATED｜截止 SP 30/45 天（地区而异）｜商户立场 已退款且应记录于 SP｜建议 抗辩（依据：在 SP 中记录退款；超期改用善意催款函）
- **所需证据**：
  - 退款记录（CRED MMDDYY ARD）（REFUND_RECORD，必填）——为何需要：在二次呈请中记载退款；规则依据：SRC-02 P38/P510/P935；本案可得性：视案件而定；缺失后果：Mastercard 可能判发卡行承担退款额、收单行承担罚费
- **处理流程**：first_see：系统检测退款与拒付并存 → auto：匹配退款与拒付 → ops：在 SP 中记录退款 → agent：解释双重入账规则 → human：确认退款归属 → reviewer：审核 → submit_condition：退款已记录 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则示例（含裁决倾向：及时正确记录→倾向收单行））｜成功因素：SP 中正确记录退款｜失败因素：SP 后才发现退款｜可否预防：是｜商户改进：退款即时同步系统｜未决问题：善意催款函的地区模板
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、退款匹配、Agent 解释
  - 演示步骤：展示退款匹配→SP 记录

## CB-CASE-017｜SOURCE_EXPLICIT｜第三方旅行重复扣款（Paid by Other Means）

- **一句话场景**：持卡人已向第三方旅行商户付款，又被商户刷卡扣同一笔；商户可证明两笔对应不同内容或收单拒收第三方支付。
- **业务分类**：卡组织 Mastercard｜原因码 4834（Duplicate / Paid by Other Means）（Point-of-Interaction Error）｜大类 Processing Error｜行业 旅游/OTA｜渠道 线上｜交易类型 重复付款｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P690; P1327-1328｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：travel purchased through a third-party travel merchant (for example an online travel merchant)... the supporting documentation must state that the merchant accepted the third-party travel payment and billed the cardholder's account.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=第三方旅行商户（OTA）
- **资金关系**：who_paid_whom：持卡人先付 OTA、又被商户扣卡；who_initiated：持卡人主张重复付款；who_received_notice：商户/收单行；who_bears_risk：商户需证明扣款正当
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 旅行服务｜渠道 卡+第三方渠道｜认证 NOT_STATED｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 重复付款｜持卡人主张 已通过其他方式支付｜通知 4834｜收到时间 NOT_STATED｜截止 90 天｜商户立场 卡扣款是唯一/对应不同商品｜建议 条件性（依据：证明卡扣款对应不同服务，或说明未接受第三方支付）
- **所需证据**：
  - 第三方支付凭证与卡扣款说明（PAYMENT_PROOF，必填）——为何需要：证明两笔支付对应关系；规则依据：SRC-02 P690/P1327-1328；本案可得性：视案件而定；缺失后果：抗辩失败
- **处理流程**：first_see：系统关联两笔支付 → auto：重复判定 → ops：上传对应说明 → agent：解释 paid by other means 规则 → human：确认对应关系 → reviewer：审核 → submit_condition：对应说明齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则示例）｜成功因素：对应关系清晰｜失败因素：无法区分两笔付款｜可否预防：是｜商户改进：收款渠道统一并标注订单号｜未决问题：OTA 退款链路
- **OceanPilot 映射**：演示 —｜seed —｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎、案件详情
- **关联案例**：CB-CASE-045

## CB-CASE-018｜SOURCE_EXPLICIT｜合理金额抗辩：持卡人签字的价目表

- **一句话场景**：EEA/英国金额不合理争议中，商户可出示持卡人签字的逐项价目表+据此计算的收据，证明金额在同意区间内。
- **业务分类**：卡组织 Mastercard｜原因码 4834（Unreasonable Amount）（Point-of-Interaction Error）｜大类 Processing Error｜行业 服务行业（维修等）｜渠道 线下｜交易类型 服务金额争议｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P770; P1395｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：An itemized price list signed by the cardholder and an itemized transaction receipt showing that the transaction amount was calculated on the basis of this price list.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=服务商户；platform=无
- **资金关系**：who_paid_whom：持卡人支付服务费；who_initiated：持卡人主张金额不合理；who_received_notice：商户/收单行；who_bears_risk：超约定区间部分商户担责
- **交易事实**：金额 NOT_STATED（区间约定）｜时间 NOT_STATED｜商品 维修等服务｜渠道 卡支付｜认证 无 PIN/CDCVM（区域条件）｜履约 已提供｜退款 NOT_STATED
- **拒付事实**：触发 金额不合理（EEA/Gibraltar/UK）｜持卡人主张 被扣金额不合理｜通知 4834 Unreasonable Amount｜收到时间 NOT_STATED｜截止 90 天｜商户立场 金额在持卡人同意的区间内｜建议 抗辩（依据：出示签字价目表与按表计算的收据（2700））
- **所需证据**：
  - 持卡人签字的逐项价目表（PRICE_LIST，必填）——为何需要：证明金额区间经持卡人同意；规则依据：SRC-02 P770/P1395；本案可得性：视案件而定；缺失后果：无法证明金额合理
  - 按价目表计算的收据（RECEIPT，必填）——为何需要：证明实际收费符合价目表；规则依据：同上；本案可得性：视案件而定；缺失后果：抗辩不完整
- **处理流程**：first_see：系统标记金额不合理类 → auto：提示所需两项证据 → ops：上传价目表与收据 → agent：解释 2700 抗辩 → human：确认签名与一致性 → reviewer：审核 → submit_condition：两项齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则示例）｜成功因素：价目表+收据齐全｜失败因素：事前未约定区间｜可否预防：是｜商户改进：服务前让客户确认价目表｜未决问题：区间约定的地区认定
- **OceanPilot 映射**：演示 —｜seed —｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎

## CB-CASE-019｜SOURCE_EXPLICIT｜15 分钟内“幽灵交易”欺诈合规案

- **一句话场景**：合法当面交易后 15 分钟内出现多笔持卡人否认的磁条/芯片当面交易（无 PIN/CDCVM），发卡行可提合规案（特定地区组合）。
- **业务分类**：卡组织 Mastercard｜原因码 Compliance Case（All Other Rules Violations）（Compliance）｜大类 Fraud｜行业 通用线下零售｜渠道 线下｜交易类型 当面重复交易欺诈｜数据来源类别 卡组织规则内置示例
- **来源**：SRC-02｜定位：P1495-1497｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：The issuer claims two or more face-to-face, magnetic stripe or chip (contact or contactless) transactions occurred, within 15 minutes of the original, cardholder authorized transaction.
- **参与者**：cardholder=持卡人；issuer=发卡行（Filing Customer）；acquirer=收单行；merchant=线下商户；platform=无
- **资金关系**：who_paid_whom：持卡人正常付款+后续幽灵交易；who_initiated：发卡行提合规案；who_received_notice：收单行；who_bears_risk：幽灵交易金额
- **交易事实**：金额 NOT_STATED｜时间 原交易后 15 分钟内｜商品 NOT_STATED｜渠道 磁条/芯片当面｜认证 无 PIN/CDCVM｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 同卡 15 分钟内多笔当面交易｜持卡人主张 仅授权第一笔｜通知 合规案（pre-compliance）｜收到时间 NOT_STATED｜截止 pre-compliance 30 天；升级 120 天内｜商户立场 NOT_STATED｜建议 信息不足（依据：原文仅规定提起条件）
- **所需证据**：
  - 原交易时间戳收据/授权日志（TIMESTAMP，必填）——为何需要：证明 15 分钟窗口；规则依据：SRC-02 P1495-1497；本案可得性：视案件而定；缺失后果：无法立案
  - 持卡人函件或 Form 0412（CARDHOLDER_STATEMENT，必填）——为何需要：证明否认后续交易；规则依据：同上；本案可得性：视案件而定；缺失后果：无法立案
- **处理流程**：first_see：系统标记合规案 → auto：校验 15 分钟窗口 → ops：准备合规案材料 → agent：解释合规案条件 → human：确认材料 → reviewer：审核 → submit_condition：条件满足 → upstream_result：NOT_STATED → final_status：PRE_COMPLIANCE
- **结局**：未说明（依据：规则示例）｜成功因素：窗口与否认证据齐全｜失败因素：窗口证据缺失｜可否预防：是｜商户改进：终端风控防同一卡短时多刷｜未决问题：该规则覆盖的地区组合扩展
- **OceanPilot 映射**：演示 —｜seed —｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎

## CB-CASE-020｜SOURCE_EXPLICIT｜网站取消政策“点击接受”披露示例

- **一句话场景**：官网用可点击的取消政策超链接+确认按钮展示条款，构成有效披露（原文以图片示例说明）。
- **业务分类**：卡组织 Visa｜原因码 13.7（Cancelled Merchandise/Services 相关）（Cancelled Merchandise/Services）｜大类 Consumer Dispute｜行业 通用电商｜渠道 线上｜交易类型 取消政策披露｜数据来源类别 卡组织指南披露示例（图片不在文本层）
- **来源**：SRC-01｜定位：P18｜置信度 MEDIUM｜需人工复核 否
- **原文摘录（≤50 词）**：The image below is an example of valid proper disclosure. It illustrates the details or text behind the cancellation policy hyperlink.
- **参与者**：cardholder=持卡人；merchant=电商商户；platform=网站
- **资金关系**：who_paid_whom：NOT_STATED；who_initiated：N/A（披露规范示例）；who_received_notice：N/A；who_bears_risk：未有效披露时商户在 13.7 类争议中不利
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 线上｜认证 NOT_STATED｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 N/A｜持卡人主张 N/A｜通知 N/A｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 已做有效披露｜建议 信息不足（依据：披露规范示例，非案件）
- **所需证据**：
  - 结账页政策披露截图（DISCLOSURE，必填）——为何需要：证明取消政策在结账前有效披露；规则依据：SRC-01 P17-18；本案可得性：视案件而定；缺失后果：13.7 类争议难以抗辩
- **处理流程**：first_see：系统提示需披露证据 → auto：无 → ops：上传披露截图 → agent：解释披露要求 → human：确认 → reviewer：审核 → submit_condition：披露截图齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：披露规范示例）｜成功因素：披露链路完整｜失败因素：结账后才展示政策｜可否预防：是｜商户改进：结账页前置政策+点击接受留痕｜未决问题：图片内容无法从文本层核对（MED 置信度）
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：证据上传、案件详情
  - 演示步骤：上传披露截图→校验
- **关联案例**：CB-CASE-030

## CB-CASE-021｜SOURCE_EXPLICIT｜质量争议示例：修车与酒店房间

- **一句话场景**：质量争议指客户不认可已收到商品/服务的状况（如修车、酒店房间质量）；可辅以中立第三方意见抗辩。
- **业务分类**：卡组织 Visa｜原因码 13.3（Not as Described or Defective）｜大类 Consumer Dispute｜行业 汽车维修/酒店｜渠道 线下｜交易类型 服务质量争议｜数据来源类别 卡组织指南内置示例
- **来源**：SRC-01｜定位：P43-44｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：Quality disputes are where the customer does not agree with the condition of merchandise or service received (e.g., a car repair situation or quality of a hotel room).
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=修车行/酒店；platform=无
- **资金关系**：who_paid_whom：持卡人支付服务费；who_initiated：持卡人主张质量不符；who_received_notice：商户/收单行；who_bears_risk：质量举证
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 修车/酒店住宿｜渠道 卡支付｜认证 NOT_STATED｜履约 已提供但质量争议｜退款 NOT_STATED
- **拒付事实**：触发 质量争议｜持卡人主张 服务状况不符预期｜通知 13.3｜收到时间 NOT_STATED｜截止 NOT_STATED（Visa 未给天数）｜商户立场 服务符合约定标准｜建议 条件性（依据：用发票/合同逐点反驳，必要时中立第三方意见）
- **所需证据**：
  - 发票/合同（INVOICE，必填）——为何需要：逐点反驳质量主张；规则依据：SRC-01 P43-44；本案可得性：视案件而定；缺失后果：抗辩乏力
  - 中立第三方意见（THIRD_PARTY_OPINION，可选）——为何需要：强化质量合格的证明；规则依据：SRC-01 P44；本案可得性：视案件而定；缺失后果：主观争议难以反驳
- **处理流程**：first_see：系统标记质量争议 → auto：证据清单预置 → ops：上传发票与鉴定 → agent：解释质量争议规则 → human：确认验收事实 → reviewer：审核 → submit_condition：发票齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则示例）｜成功因素：验收标准清晰｜失败因素：无验收标准｜可否预防：是｜商户改进：服务前明确验收标准并留证｜未决问题：主观质量争议的裁判尺度
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：案件详情、证据上传、Agent 解释
  - 演示步骤：展示证据清单→上传鉴定
- **关联案例**：CB-CASE-028

## CB-CASE-022｜SOURCE_EXPLICIT｜Visa Secure 三场景：ECI 5/6/7 的保护差异

- **一句话场景**：认证成功(ECI 5)→免欺诈争议；双方未参与(ECI 6)→免欺诈争议；商户未认证(ECI 7)→不保护。
- **业务分类**：卡组织 Visa｜原因码 10.4（Fraud 类保护规则）（Other Fraud – Card-Absent）｜大类 Fraud｜行业 电商｜渠道 线上｜交易类型 3DS 认证场景｜数据来源类别 卡组织指南内置规则示例
- **来源**：SRC-01｜定位：P14｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：The cardholder is successfully authenticated → The merchant is protected from fraud-related disputes... using ECI of '5'.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=电商商户；platform=Visa Secure/3DS
- **资金关系**：who_paid_whom：持卡人向商户付款；who_initiated：持卡人欺诈争议；who_received_notice：商户/收单行；who_bears_risk：ECI 7 时商户承担欺诈争议
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 CNP｜认证 Visa Secure（ECI 5/6/7）｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 欺诈争议｜持卡人主张 未参与交易｜通知 10.4｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 视 ECI 而定｜建议 条件性（依据：ECI 5/6 免欺诈争议；ECI 7 不保护，需其他证据）
- **所需证据**：
  - 认证结果（ECI 值）（AUTH_RESULT，必填）——为何需要：决定欺诈争议保护；规则依据：SRC-01 P14；本案可得性：是；缺失后果：无法判定保护状态
- **处理流程**：first_see：系统读取 ECI → auto：按 ECI 分类保护状态 → ops：无需 → agent：解释 ECI 保护差异 → human：无需 → reviewer：无需 → submit_condition：按 ECI 自动路由 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则示例）｜成功因素：ECI 正确读取｜失败因素：认证数据缺失｜可否预防：是｜商户改进：强制 3DS 提升 ECI｜未决问题：各区域责任转移差异
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：规则引擎、Agent 解释
  - 演示步骤：展示 ECI 路由
- **关联案例**：CB-CASE-040

## CB-CASE-023｜SOURCE_EXPLICIT｜分时度假 14 个日历日取消须全额退款

- **一句话场景**：持卡人在合同日期（或收到文件）后 14 个日历日内取消分时度假，商户必须全额退款，否则进入 13.7 争议。
- **业务分类**：卡组织 Visa｜原因码 13.7（Cancelled Merchandise/Services）｜大类 Consumer Dispute｜行业 分时度假/旅游｜渠道 线下/电话销售｜交易类型 取消退款｜数据来源类别 卡组织指南内置规则示例
- **来源**：SRC-01｜定位：P17; P49-50｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：You must provide a full credit when the cardholder has cancelled the transaction within 14 calendar days of the contract date.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=分时度假销售商；platform=无
- **资金关系**：who_paid_whom：持卡人预付款；who_initiated：持卡人在 14 天内取消；who_received_notice：商户；who_bears_risk：未按 14 天规则退款由商户担责
- **交易事实**：金额 NOT_STATED｜时间 合同日期后 14 日历日内｜商品 分时度假｜渠道 卡支付｜认证 NOT_STATED｜履约 已取消｜退款 未退款
- **拒付事实**：触发 14 天内取消未退款｜持卡人主张 已按时取消｜通知 13.7｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 取消超期或未收到取消｜建议 条件性（依据：14 天内取消必须退款；超期则可抗辩）
- **所需证据**：
  - 取消时间证明（CANCELLATION_TIME，必填）——为何需要：判断是否在 14 天内；规则依据：SRC-01 P17/P49-50；本案可得性：视案件而定；缺失后果：无法判定
- **处理流程**：first_see：系统校验 14 天窗口 → auto：日期比对 → ops：上传取消记录 → agent：解释 14 天规则 → human：确认日期 → reviewer：审核 → submit_condition：日期证据齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则示例（明确全额退款义务））｜成功因素：14 天内取消证据｜失败因素：超期取消｜可否预防：是｜商户改进：合同明确取消窗口并快速退款｜未决问题：各州/地区立法差异
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎、案件详情
  - 演示步骤：展示 14 天窗口校验
- **关联案例**：CB-CASE-033

## CB-CASE-024｜SOURCE_EXPLICIT｜Visa 合规违规四例（无争议权走 Compliance）

- **一句话场景**：未经同意加收费用、RDR 争议后重复退款、无原交易贷记后撤销、同日多笔手输仅承认一笔——均走 Compliance 而非争议流程。
- **业务分类**：卡组织 Visa｜原因码 Compliance（无 Dispute Condition）（Compliance）｜大类 Processing Error / Compliance｜行业 通用｜渠道 通用｜交易类型 合规违规｜数据来源类别 卡组织指南内置示例
- **来源**：SRC-01｜定位：P20｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：The merchant bills the cardholder for a delayed or amended charge without cardholder's consent.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=无
- **资金关系**：who_paid_whom：多场景；who_initiated：受损方向 Visa 提合规案；who_received_notice：对方机构；who_bears_risk：违规方
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 多场景｜渠道 多场景｜认证 NOT_STATED｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 规则违规但无争议权｜持卡人主张 N/A｜通知 Compliance｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 NOT_STATED｜建议 信息不足（依据：先 pre-compliance 给对方解决机会，未解决由 Visa 裁定）
- **所需证据**：
  - 违规事实证据（VIOLATION_PROOF，必填）——为何需要：支撑合规案；规则依据：SRC-01 P20；本案可得性：视案件而定；缺失后果：合规案不成立
- **处理流程**：first_see：系统标记合规类 → auto：无 → ops：准备合规案材料 → agent：解释合规与争议的区别 → human：确认 → reviewer：审核 → submit_condition：材料齐全 → upstream_result：Visa 审查 → final_status：COMPLIANCE
- **结局**：未说明（依据：规则示例）｜成功因素：违规证据充分｜失败因素：证据不足｜可否预防：是｜商户改进：遵守授权与入账规范｜未决问题：pre-compliance 时限
- **OceanPilot 映射**：演示 —｜seed —｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎

## CB-CASE-025｜SOURCE_EXPLICIT｜[示例案例] Visa 10.4 CNP 欺诈：SGD 899 未授权

- **一句话场景**：持卡人否认 SGD 899 电商交易；商户以 3DS/设备/IP/账号/历史交易等证据链应对 CE3.0。
- **业务分类**：卡组织 Visa｜原因码 10.4（Other Fraud – Card-Absent Environment）｜大类 Fraud｜行业 电子消费品｜渠道 线上（CNP）｜交易类型 CNP 欺诈｜数据来源类别 源文件自标注虚构演示案例
- **来源**：SRC-03｜定位：§3（第 3 章，约 60-90 行）｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：Amount: SGD 899 / Merchant: ABC Electronics / Channel: Ecommerce / CNP. Cardholder: "I did not make this purchase."
- **参与者**：cardholder=持卡人（否认交易）；issuer=发卡行；acquirer=收单行；merchant=ABC Electronics；platform=电商网站
- **资金关系**：who_paid_whom：持卡人（被扣款）→ 商户；who_initiated：持卡人向发卡行声称未参与；who_received_notice：商户；who_bears_risk：若无 CE3.0 证据则商户承担
- **交易事实**：金额 SGD 899｜时间 NOT_STATED｜商品 电子产品｜渠道 Ecommerce/CNP｜认证 未注明（可补 3DS）｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 持卡人不认可交易｜持卡人主张 我没有做这笔交易｜通知 10.4｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 NOT_STATED｜建议 条件性（依据：走 Fraud Evidence Matching → CE3.0 Eligibility → 历史交易匹配，而非简单上传 POD）
- **所需证据**：
  - 3DS/Device ID/IP/账号/邮箱/电话/账单地址/收货地址（IDENTITY，必填）——为何需要：证明交易与持卡人关联；规则依据：SRC-03 §3；本案可得性：视案件而定；缺失后果：无法进入 CE3.0
  - 历史未争议交易（HISTORY，必填）——为何需要：CE3.0 历史交易匹配；规则依据：SRC-03 §3；SRC-01 P26；本案可得性：视案件而定；缺失后果：CE3.0 不成立
- **处理流程**：first_see：系统按 10.4 匹配 CE3.0 规则 → auto：欺诈证据匹配 → ops：补充证据 → agent：解释 CE3.0 逻辑 → human：确认关联性 → reviewer：审核 → submit_condition：证据链完整 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：示例未给结局）｜成功因素：CE3.0 证据齐｜失败因素：无历史交易｜可否预防：是｜商户改进：交易时采集设备/地址信息｜未决问题：CE3.0 各要素权重
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：案件详情、证据上传与抽取、准备度评估、Agent
  - 演示步骤：展示 CE3.0 匹配→上传证据→准备度评分
- **核心案例**：是（CE3.0 欺诈证据链的最佳演示案件）
- **关联案例**：CB-CASE-040、CB-CASE-061

## CB-CASE-026｜SOURCE_EXPLICIT｜[示例案例] Visa 13.1：USD 1,200 iPhone 未收到

- **一句话场景**：持卡人称未收到 USD 1,200 的 iPhone；商户需以 Tracking→Delivery→Recipient→POD 完整证据链抗辩。
- **业务分类**：卡组织 Visa｜原因码 13.1（Merchandise/Services Not Received）｜大类 Consumer Dispute｜行业 电商（3C）｜渠道 线上｜交易类型 实物商品｜数据来源类别 源文件自标注虚构演示案例
- **来源**：SRC-03｜定位：§5（第 5 章）｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：Product: iPhone / Amount: USD 1,200 / Courier: DHL. Cardholder: "I never received the merchandise."
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=电商商户；platform=DHL 物流
- **资金关系**：who_paid_whom：持卡人 → 商户 USD 1,200；who_initiated：持卡人主张未收到；who_received_notice：商户；who_bears_risk：无法证明履约则商户担责
- **交易事实**：金额 USD 1,200｜时间 NOT_STATED｜商品 iPhone｜渠道 电商｜认证 NOT_STATED｜履约 争议中｜退款 NOT_STATED
- **拒付事实**：触发 未收到商品｜持卡人主张 我从未收到商品｜通知 13.1｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 NOT_STATED｜建议 条件性（依据：具备 Tracking+签收+收件人一致时可抗辩；仅“订单已妥投”状态不够）
- **所需证据**：
  - 物流轨迹（TRACKING，必填）——为何需要：证明运输过程；规则依据：SRC-03 §5；本案可得性：视案件而定；缺失后果：无法证明发货
  - 签收证明（含收件人）（POD，必填）——为何需要：证明交付给对应消费者；规则依据：SRC-03 §5；SRC-01 P40-41；本案可得性：视案件而定；缺失后果：证据链断裂
- **处理流程**：first_see：系统构建证据链视图 → auto：对接物流数据 → ops：补传 POD → agent：解释证据链要求 → human：确认收件人一致 → reviewer：审核 → submit_condition：证据链完整 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：示例未给结局）｜成功因素：POD 收件人一致｜失败因素：仅订单状态｜可否预防：是｜商户改进：高价值商品强制签收留档｜未决问题：代收情形的效力
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：案件详情、证据上传、准备度评估、Agent
  - 演示步骤：展示证据链→上传 POD→提交
- **核心案例**：是（未收到商品证据链的最佳演示案件）
- **关联案例**：CB-CASE-041、CB-CASE-060

## CB-CASE-027｜SOURCE_EXPLICIT｜[示例案例] Visa 13.2：取消 SaaS 后仍扣 USD 99

- **一句话场景**：6 月 1 日取消订阅，6 月 15 日仍被扣 USD 99；核心判断是争议交易发生时商户是否仍有有效扣款授权。
- **业务分类**：卡组织 Visa｜原因码 13.2（Cancelled Recurring Transaction）｜大类 Consumer Dispute｜行业 SaaS｜渠道 订阅｜交易类型 循环扣款｜数据来源类别 源文件自标注虚构演示案例
- **来源**：SRC-03｜定位：§6（第 6 章）｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：June 1: Customer cancelled SaaS subscription / June 15: Merchant charged USD 99.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=SaaS 商户；platform=订阅系统
- **资金关系**：who_paid_whom：持卡人被扣 USD 99；who_initiated：持卡人主张已取消；who_received_notice：商户；who_bears_risk：取消后扣款商户担责
- **交易事实**：金额 USD 99｜时间 6 月 15 日扣款（6 月 1 日已取消）｜商品 SaaS 订阅｜渠道 订阅扣款｜认证 MIT/Recurring｜履约 已取消｜退款 NOT_STATED
- **拒付事实**：触发 取消后仍扣款｜持卡人主张 已取消订阅｜通知 13.2｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 NOT_STATED｜建议 条件性（依据：若取消时间戳在扣款前且无有效授权，应接受并退款；若取消不符合政策可抗辩）
- **所需证据**：
  - 取消时间戳与确认（CANCELLATION，必填）——为何需要：判断扣款时授权是否有效；规则依据：SRC-03 §6；本案可得性：视案件而定；缺失后果：无法判定
  - 循环扣款协议/MIT 标识（RECURRING_AUTH，必填）——为何需要：证明扣款授权仍有效；规则依据：SRC-03 §6；本案可得性：视案件而定；缺失后果：抗辩无据
- **处理流程**：first_see：系统比对取消与扣款时间 → auto：时间线自动对比 → ops：上传协议 → agent：解释授权有效性判断 → human：确认取消政策 → reviewer：审核 → submit_condition：时间线证据齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：示例未给结局）｜成功因素：取消符合政策且扣款有据｜失败因素：取消后被扣｜可否预防：是｜商户改进：取消请求即时生效并邮件确认｜未决问题：结算周期内的扣款归属
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：案件详情、时间线视图、Agent
  - 演示步骤：展示取消/扣款时间线→判定
- **核心案例**：是（取消订阅时间线演示案件）
- **关联案例**：CB-CASE-010

## CB-CASE-028｜SOURCE_EXPLICIT｜[示例案例] Visa 13.3：全新 MacBook 实际是翻新机

- **一句话场景**：买全新 MacBook 收到翻新机；商户需证明 Delivered Product ≈ Product Description at Purchase。
- **业务分类**：卡组织 Visa｜原因码 13.3（Not as Described or Defective）｜大类 Consumer Dispute｜行业 电商（3C）｜渠道 线上｜交易类型 实物商品｜数据来源类别 源文件自标注虚构演示案例
- **来源**：SRC-03｜定位：§7（第 7 章）｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：消费者购买 Brand New MacBook，实际收到 Refurbished MacBook。
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=电商商户；platform=无
- **资金关系**：who_paid_whom：持卡人 → 商户；who_initiated：持卡人主张货不对板；who_received_notice：商户；who_bears_risk：货不对板商户担责
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 MacBook（宣称全新）｜渠道 电商｜认证 NOT_STATED｜履约 已收货但为翻新机｜退款 NOT_STATED
- **拒付事实**：触发 货不对板｜持卡人主张 收到的不是全新机｜通知 13.3｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 NOT_STATED｜建议 条件性（依据：若商品确为翻新机应接受并退货退款；若描述无误可抗辩）
- **所需证据**：
  - 商品页/SKU/描述（PRODUCT_DESC，必填）——为何需要：对比实际交付与描述；规则依据：SRC-03 §7；本案可得性：视案件而定；缺失后果：无法证明一致性
  - 发货/收货记录（DELIVERY_RECORD，必填）——为何需要：证明实际发出的商品；规则依据：SRC-03 §7；本案可得性：视案件而定；缺失后果：抗辩无据
  - 检验报告（INSPECTION，可选）——为何需要：证明商品状态；规则依据：SRC-03 §7；本案可得性：视案件而定；缺失后果：主观争议难反驳
- **处理流程**：first_see：系统标记货不对板 → auto：拉取 SKU 与发货记录 → ops：上传检验 → agent：解释一致性证明逻辑 → human：确认商品状态 → reviewer：审核 → submit_condition：证据齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：示例未给结局）｜成功因素：序列号一致｜失败因素：确为翻新机｜可否预防：是｜商户改进：发货前核验商品状态｜未决问题：瑕疵判定标准
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、证据上传、Agent
  - 演示步骤：展示描述 vs 交付对比
- **关联案例**：CB-CASE-021

## CB-CASE-029｜SOURCE_EXPLICIT｜[示例案例] Visa 13.6：承诺退款未到账

- **一句话场景**：商户承诺退款但持卡人未收到；系统应先关联 Original Transaction ↓ Refund Transaction，ARN 比客服聊天更关键。
- **业务分类**：卡组织 Visa｜原因码 13.6（Credit Not Processed）｜大类 Consumer Dispute｜行业 通用｜渠道 通用｜交易类型 退款未到账｜数据来源类别 源文件自标注虚构演示案例
- **来源**：SRC-03｜定位：§8（第 8 章）｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：消费者：Merchant promised refund, but I never received it.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=无
- **资金关系**：who_paid_whom：持卡人 → 商户；退款未达；who_initiated：持卡人主张退款未到；who_received_notice：商户；who_bears_risk：未退金额
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 NOT_STATED｜退款 承诺退款但未到账
- **拒付事实**：触发 退款未到账｜持卡人主张 商户承诺退款但我没收到｜通知 13.6｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 NOT_STATED｜建议 条件性（依据：若退款 ARN 可查且已结算则抗辩；否则尽快退款）
- **所需证据**：
  - 退款交易（ARN/日期/金额/卡号/结算状态）（REFUND_TX，必填）——为何需要：证明退款已发起并结算；规则依据：SRC-03 §8；本案可得性：视案件而定；缺失后果：无法证明退款
- **处理流程**：first_see：系统关联原交易与退款 → auto：退款匹配 → ops：核对退款状态 → agent：解释 ARN 重要性 → human：确认退款事实 → reviewer：审核 → submit_condition：退款记录齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：示例未给结局）｜成功因素：ARN 可查｜失败因素：仅聊天记录｜可否预防：是｜商户改进：退款即时生成 ARN 并留存｜未决问题：结算延迟处理
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、退款匹配、Agent
  - 演示步骤：展示原交易↔退款关联
- **关联案例**：CB-CASE-072

## CB-CASE-030｜SOURCE_EXPLICIT｜[示例案例] Visa 12.6：同一金额两笔被扣

- **一句话场景**：两笔 USD 100 相隔 1 分钟被扣；不能只看同商户同金额即判重复，需比对 Order ID/SKU/授权/清算。
- **业务分类**：卡组织 Visa｜原因码 12.6.1（Duplicate Processing）｜大类 Processing Error｜行业 通用｜渠道 线上｜交易类型 重复扣款｜数据来源类别 源文件自标注虚构演示案例
- **来源**：SRC-03｜定位：§9（第 9 章）｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：TXN001 USD 100 10:01 / TXN002 USD 100 10:02. 消费者：Charged twice.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=无
- **资金关系**：who_paid_whom：持卡人被扣两笔 USD 100；who_initiated：持卡人主张重复扣款；who_received_notice：商户；who_bears_risk：重复部分商户担责
- **交易事实**：金额 USD 100 × 2｜时间 10:01 / 10:02｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 重复扣款｜持卡人主张 被扣了两次｜通知 12.6｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 NOT_STATED｜建议 条件性（依据：比对 Order ID/SKU/Authorization/Capture 证明两笔是否独立）
- **所需证据**：
  - 订单/发票/服务对应关系（ORDER_MATCH，必填）——为何需要：证明两笔是独立交易或重复；规则依据：SRC-03 §9；本案可得性：视案件而定；缺失后果：无法判定重复
- **处理流程**：first_see：系统多字段比对 → auto：重复判定引擎 → ops：上传订单对应 → agent：解释重复判定规则 → human：确认两笔对应关系 → reviewer：审核 → submit_condition：比对完成 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：示例未给结局）｜成功因素：订单号区分清晰｜失败因素：仅凭金额判断｜可否预防：是｜商户改进：每笔扣款挂订单号｜未决问题：同一订单两笔的判定
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、重复判定、Agent
  - 演示步骤：展示多字段比对
- **关联案例**：CB-CASE-073

## CB-CASE-031｜SOURCE_EXPLICIT｜[示例案例] Mastercard 4853：USD 499 课程“无法访问”

- **一句话场景**：持卡人称课程无法访问，商户发现登录 17 次；证据链=Payment→Account→Login→Content Access→Consumption。
- **业务分类**：卡组织 Mastercard｜原因码 4853（Cardholder Dispute）｜大类 Consumer Dispute｜行业 在线教育｜渠道 线上（数字商品）｜交易类型 数字服务｜数据来源类别 源文件自标注虚构演示案例
- **来源**：SRC-03｜定位：§12（第 12 章）｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：消费者购买 Online Course / USD 499，声称"课程无法访问"；Merchant 发现 Login Count: 17。
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=在线课程商户；platform=课程平台
- **资金关系**：who_paid_whom：持卡人 → 商户 USD 499；who_initiated：持卡人主张服务不可用；who_received_notice：商户；who_bears_risk：无法证明履约则商户担责
- **交易事实**：金额 USD 499｜时间 NOT_STATED｜商品 在线课程｜渠道 电商｜认证 账号登录｜履约 可访问（登录 17 次）｜退款 NOT_STATED
- **拒付事实**：触发 服务不可用｜持卡人主张 课程无法访问｜通知 4853｜收到时间 NOT_STATED｜截止 120 天｜商户立场 登录记录显示已使用｜建议 抗辩（依据：登录/访问/消费日志构成强证据链）
- **所需证据**：
  - 登录/访问/消费记录（USAGE_LOG，必填）——为何需要：证明服务已被使用；规则依据：SRC-03 §12；本案可得性：是（Login Count 17）；缺失后果：无法反驳不可访问
- **处理流程**：first_see：系统拉取使用日志 → auto：构建消费证据链 → ops：确认日志 → agent：解释证据链价值 → human：确认账号归属 → reviewer：审核 → submit_condition：日志齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：示例未给结局）｜成功因素：消费日志完整｜失败因素：账号归属不清｜可否预防：是｜商户改进：数字商品记录访问与消费行为｜未决问题：账号共享情形的归属
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：案件详情、使用日志、Agent
  - 演示步骤：展示 17 次登录证据→抗辩
- **核心案例**：是（数字商品消费证据链演示案件）
- **关联案例**：CB-CASE-046

## CB-CASE-032｜SOURCE_EXPLICIT｜[示例案例] Amex C04：声称已退货但商户未收到

- **一句话场景**：持卡人声称已退货，商户称从未收到；需退货政策披露+商品未实际退回的证据。
- **业务分类**：卡组织 American Express｜原因码 C04（Goods/Services Returned or Refused）｜大类 Consumer Dispute｜行业 零售｜渠道 线上/线下｜交易类型 退货｜数据来源类别 源文件自标注虚构演示案例
- **来源**：SRC-03｜定位：§15（第 15 章）｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：消费者：I returned the merchandise. Merchant：We never received the return.
- **参与者**：cardholder=持卡人；issuer=Amex 发卡方；acquirer=收单方；merchant=商户；platform=退货物流
- **资金关系**：who_paid_whom：持卡人 → 商户；who_initiated：持卡人主张已退货；who_received_notice：商户；who_bears_risk：退货未到责任
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 退货物流未知｜退款 NOT_STATED
- **拒付事实**：触发 退货争议｜持卡人主张 我已退货｜通知 C04｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 未收到退货｜建议 条件性（依据：若无退货物流且政策已披露可抗辩；否则退款）
- **所需证据**：
  - 退货政策及披露（RETURN_POLICY，必填）——为何需要：证明政策并判断是否遵守；规则依据：SRC-03 §15；本案可得性：视案件而定；缺失后果：无政策则难抗辩
  - 商品未实际退回的证据（RETURN_PROOF，必填）——为何需要：反驳已退货主张；规则依据：SRC-03 §15；本案可得性：视案件而定；缺失后果：无法反驳
- **处理流程**：first_see：系统核对退货物流 → auto：物流查询 → ops：上传政策 → agent：解释 C04 举证方向 → human：确认无退货记录 → reviewer：审核 → submit_condition：证据齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：示例未给结局）｜成功因素：退货物流可查｜失败因素：政策未披露｜可否预防：是｜商户改进：退货政策显式披露｜未决问题：Amex 官方时限原文缺失
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、证据上传、Agent
  - 演示步骤：核对退货物流→判定
- **关联案例**：CB-CASE-033

## CB-CASE-033｜SOURCE_EXPLICIT｜[示例案例] Amex C05：取消预订但已过取消期限

- **一句话场景**：持卡人称已取消预订，商户称已过取消截止；需取消政策+时间戳证明。
- **业务分类**：卡组织 American Express｜原因码 C05（Goods/Services Cancelled）｜大类 Consumer Dispute｜行业 旅游/预订｜渠道 预订｜交易类型 取消争议｜数据来源类别 源文件自标注虚构演示案例
- **来源**：SRC-03｜定位：§16（第 16 章）｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：消费者：I cancelled my booking. Merchant：Cancellation deadline had already passed.
- **参与者**：cardholder=持卡人；issuer=Amex 发卡方；acquirer=收单方；merchant=预订商户；platform=预订系统
- **资金关系**：who_paid_whom：持卡人支付预订费；who_initiated：持卡人主张已取消；who_received_notice：商户；who_bears_risk：取消超期则持卡人担责
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 预订服务｜渠道 卡支付｜认证 NOT_STATED｜履约 已取消/超期｜退款 NOT_STATED
- **拒付事实**：触发 取消争议｜持卡人主张 我已取消预订｜通知 C05｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 取消截止已过｜建议 抗辩（依据：政策披露+取消时间戳证明超期）
- **所需证据**：
  - 取消政策及披露（CANCELLATION_POLICY，必填）——为何需要：证明截止时间已告知；规则依据：SRC-03 §16；本案可得性：视案件而定；缺失后果：无法收取消违约金
  - 取消时间戳（CANCELLATION_TIME，必填）——为何需要：证明取消晚于截止；规则依据：SRC-03 §16；本案可得性：视案件而定；缺失后果：抗辩无据
- **处理流程**：first_see：系统比对取消与截止时间 → auto：时间线对比 → ops：上传政策 → agent：解释超期取消规则 → human：确认时间 → reviewer：审核 → submit_condition：证据齐全 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：示例未给结局）｜成功因素：取消超期证据｜失败因素：政策未披露｜可否预防：是｜商户改进：取消政策结构化存储｜未决问题：Amex 官方规则原文缺失
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、时间线视图、Agent
  - 演示步骤：展示取消 vs 截止时间线
- **关联案例**：CB-CASE-012、CB-CASE-023

## CB-CASE-034｜SOURCE_EXPLICIT｜[真实案例] Mastercard × Sicredi：账单描述不清引发争议

- **一句话场景**：银行 Sicredi 用 Ethoca Consumer Clarity 向持卡人展示交易详情，把“不认识账单”的争议化解在拒付之前。
- **业务分类**：卡组织 Mastercard（Ethoca）｜原因码 预防类（对应 4837/4863 场景）（预防（No Cardholder Authorization 前置））｜大类 Fraud（预防）｜行业 银行/零售｜渠道 通用｜交易类型 Friendly Fraud 预防｜数据来源类别 卡组织官方营销案例（源标注真实案例）
- **来源**：SRC-03｜定位：§20（第 20 章）｜置信度 MEDIUM｜需人工复核 是
- **原文摘录（≤50 词）**：Mastercard 公开 Sicredi 使用 Ethoca Consumer Clarity 的案例：持卡人看到不清晰账单描述→Consumer Clarity 提供交易详情→持卡人认出交易→争议被避免。
- **参与者**：cardholder=持卡人；issuer=Sicredi（银行）；merchant=交易商户；psp=Ethoca；platform=Ethoca Consumer Clarity
- **资金关系**：who_paid_whom：持卡人 → 商户；who_initiated：持卡人因账单描述不清准备争议；who_received_notice：发卡行；who_bears_risk：争议被提前化解
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 卡支付｜认证 NOT_STATED｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 账单描述不清晰｜持卡人主张 不认识这笔交易｜通知 预防（未发起拒付）｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 N/A｜建议 信息不足（依据：属争议预防案例，映射到产品可做“交易详情解释”模块）
- **所需证据**：
  - 清晰账单描述与交易详情（DESCRIPTOR，必填）——为何需要：让持卡人认出交易；规则依据：SRC-03 §20；本案可得性：视案件而定；缺失后果：争议风险升高
- **处理流程**：first_see：系统在争议前展示交易详情 → auto：拉取交易上下文 → ops：无需 → agent：解释交易细节 → human：无需 → reviewer：无需 → submit_condition：N/A → upstream_result：争议被避免 → final_status：DISPUTE_AVOIDED
- **结局**：部分/其他（依据：源文件转述的营销案例：争议被避免（非仲裁结局））｜成功因素：详情展示及时｜失败因素：描述仍不清｜可否预防：是｜商户改进：优化商户名与描述｜未决问题：该工具覆盖范围与数据来源细节（需原链接核实）
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 —｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：案件详情、交易上下文、Agent
  - 演示步骤：展示友好欺诈预防故事
- **核心案例**：是（唯一真实案例，适合路演开场故事）
- **关联案例**：CB-CASE-071

## CB-CASE-040｜RULE_DERIVED｜Visa 10.4 CNP 欺诈：典型证据链场景（规则还原）

- **一句话场景**：持卡人否认一笔无卡交易。商户可提交认证记录+2 笔 120–365 天内清算的同设备历史交易（CE），或 16 项 Compelling Evidence 之一。
- **业务分类**：卡组织 Visa｜原因码 10.4（Other Fraud – Card-Absent Environment）｜大类 Fraud｜行业 电商｜渠道 线上｜交易类型 CNP 欺诈｜数据来源类别 规则还原场景（原文仅给原因码+规则，无完整故事）
- **来源**：SRC-01、SRC-03｜定位：SRC-01 P26/P54-58; SRC-03 §3｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：The cardholder is claiming that they did not authorize or participate in a transaction conducted in a card-absent environment.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=电商商户；platform=电商网站
- **资金关系**：who_paid_whom：持卡人被扣款；who_initiated：持卡人向发卡行否认交易；who_received_notice：商户；who_bears_risk：默认商户承担，除非 CE 成立
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 CNP｜认证 可选 3DS｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 持卡人不认可交易｜持卡人主张 我没有做这笔交易｜通知 10.4｜收到时间 NOT_STATED｜截止 NOT_STATED（Visa 未给天数）｜商户立场 NOT_STATED｜建议 条件性（依据：CE3.0/Compelling Evidence 满足则可抗辩，否则建议接受）
- **所需证据**：
  - 3DS/认证记录（AUTH，可选）——为何需要：认证成功可获保护；规则依据：SRC-01 P14/P26；本案可得性：视案件而定；缺失后果：转向 CE 证据
  - 2 笔同设备/同IP历史未争议交易（HISTORY，必填）——为何需要：CE 抗辩核心；规则依据：SRC-01 P26；本案可得性：视案件而定；缺失后果：CE 不成立
- **处理流程**：first_see：案件进入后按原因码匹配规则 → auto：规则引擎装载对应条件与证据清单 → ops：按清单收集证据 → agent：解释原因码与证据要求 → human：确认关键事实 → reviewer：审核后放行 → submit_condition：证据满足对应原因码要求 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则还原，无结局）｜成功因素：CE 要素齐全｜失败因素：无历史交易｜可否预防：是｜商户改进：采集设备指纹与历史交易｜未决问题：Visa 响应天数需收单机构确认
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：案件详情、证据上传、准备度评估、Agent
  - 演示步骤：展示 CE 匹配→准备度评分→提交/接受
- **核心案例**：是（欺诈类规则还原的基准场景）
- **关联案例**：CB-CASE-025、CB-CASE-061

## CB-CASE-041｜RULE_DERIVED｜Visa 13.1 商品/服务未收到：典型场景（规则还原）

- **一句话场景**：持卡人声称未收到商品。商户需证明该争议交易对应的商品确实履约给了该消费者（签收、自提、航班起飞、NFT 钱包哈希等）。
- **业务分类**：卡组织 Visa｜原因码 13.1（Merchandise/Services Not Received）｜大类 Consumer Dispute｜行业 电商/物流｜渠道 线上｜交易类型 实物商品/服务｜数据来源类别 规则还原场景（原文仅给原因码+规则，无完整故事）
- **来源**：SRC-01、SRC-03｜定位：SRC-01 P40-41; SRC-03 §5｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：The cardholder claims that merchandise or services that they ordered were not received by the expected date.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=物流商
- **资金关系**：who_paid_whom：持卡人付款；who_initiated：持卡人主张未收到；who_received_notice：商户；who_bears_risk：无法证明履约则商户
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 争议中｜退款 NOT_STATED
- **拒付事实**：触发 未收到商品/服务｜持卡人主张 没收到｜通知 13.1｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 NOT_STATED｜建议 条件性（依据：证据链（Tracking→Delivery→Recipient→POD）完整则抗辩）
- **所需证据**：
  - 物流轨迹/航班起飞证明（TRACKING，必填）——为何需要：证明运输；规则依据：SRC-01 P40-41；本案可得性：视案件而定；缺失后果：无法证明发货
  - 签收证明/自提记录/服务使用日志（POD，必填）——为何需要：证明交付给对应消费者；规则依据：SRC-01 P40-41；本案可得性：视案件而定；缺失后果：证据链断裂
- **处理流程**：first_see：案件进入后按原因码匹配规则 → auto：规则引擎装载对应条件与证据清单 → ops：按清单收集证据 → agent：解释原因码与证据要求 → human：确认关键事实 → reviewer：审核后放行 → submit_condition：证据满足对应原因码要求 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则还原）｜成功因素：POD 收件人一致｜失败因素：仅订单状态｜可否预防：是｜商户改进：签收留档｜未决问题：代收效力
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、证据上传、Agent
  - 演示步骤：证据链视图→上传 POD→提交
- **关联案例**：CB-CASE-026、CB-CASE-060

## CB-CASE-042｜RULE_DERIVED｜Visa 11.3 无授权/逾期清算：典型场景（规则还原）

- **一句话场景**：交易未获授权、超额、或未在时限内清算（2024-04-13 起并入 11.3）。大量依据是结构化交易数据，适合自动判责。
- **业务分类**：卡组织 Visa｜原因码 11.3（No Authorization / Late Presentment）｜大类 Authorization｜行业 通用｜渠道 线上/线下｜交易类型 授权问题｜数据来源类别 规则还原场景（原文仅给原因码+规则，无完整故事）
- **来源**：SRC-01、SRC-03｜定位：SRC-01 P31; SRC-03 §10｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：A transaction was processed without obtaining the required authorization, or the transaction was not processed within the required transaction processing time limit.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=无
- **资金关系**：who_paid_whom：交易入账；who_initiated：发卡行拒付；who_received_notice：收单行/商户；who_bears_risk：授权缺失由商户承担
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 授权｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 授权缺失/逾期清算｜持卡人主张 N/A（发卡行主张）｜通知 11.3｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 授权存在且按时清算｜建议 条件性（依据：自动比对授权响应/授权码/金额/清算日期决定接受或抗辩）
- **所需证据**：
  - 授权响应/授权码/金额/清算日期（AUTH_LOG，必填）——为何需要：证明授权有效且按时清算；规则依据：SRC-03 §10；SRC-01 P31；本案可得性：视案件而定；缺失后果：建议接受
- **处理流程**：first_see：案件进入后按原因码匹配规则 → auto：规则引擎装载对应条件与证据清单 → ops：按清单收集证据 → agent：解释原因码与证据要求 → human：确认关键事实 → reviewer：审核后放行 → submit_condition：证据满足对应原因码要求 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则还原）｜成功因素：结构化数据齐全｜失败因素：数据缺失｜可否预防：是｜商户改进：确保授权与清算合规｜未决问题：11.3 生效日切换逻辑
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎、案件详情
  - 演示步骤：展示自动判责结果

## CB-CASE-043｜RULE_DERIVED｜Visa 12.6 重复处理/已其他方式付款：典型场景（规则还原）

- **一句话场景**：同一凭证同交易日同金额处理多次（12.6.1），或持卡人已用其他方式付款（12.6.2）。需多字段比对而非仅凭金额。
- **业务分类**：卡组织 Visa｜原因码 12.6.1/12.6.2（Duplicate Processing / Paid by Other Means）｜大类 Processing Error｜行业 通用｜渠道 线上/线下｜交易类型 处理错误｜数据来源类别 规则还原场景（原文仅给原因码+规则，无完整故事）
- **来源**：SRC-01、SRC-03｜定位：SRC-01 P37-38; SRC-03 §9｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：The cardholder claims that a single transaction was processed more than once using the same Payment Credential on the same Transaction date, and for the same Transaction amount.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=无
- **资金关系**：who_paid_whom：持卡人付款（可能两次）；who_initiated：持卡人主张重复/已另行付款；who_received_notice：商户；who_bears_risk：重复部分商户
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 重复扣款｜持卡人主张 被扣两次/已其他方式付款｜通知 12.6｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 两笔独立｜建议 条件性（依据：比对 Order ID/SKU/Authorization/Capture/Invoice 判定）
- **所需证据**：
  - 订单/授权/清算多字段比对（ORDER_MATCH，必填）——为何需要：判定是否重复；规则依据：SRC-03 §9；本案可得性：视案件而定；缺失后果：无法判定
- **处理流程**：first_see：案件进入后按原因码匹配规则 → auto：规则引擎装载对应条件与证据清单 → ops：按清单收集证据 → agent：解释原因码与证据要求 → human：确认关键事实 → reviewer：审核后放行 → submit_condition：证据满足对应原因码要求 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则还原）｜成功因素：订单号区分｜失败因素：仅凭金额｜可否预防：是｜商户改进：扣款挂订单号｜未决问题：同订单两笔认定
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：重复判定、案件详情
  - 演示步骤：展示多字段比对
- **关联案例**：CB-CASE-030、CB-CASE-073

## CB-CASE-044｜RULE_DERIVED｜Visa 13.7 已取消商品/服务：典型场景（规则还原）

- **一句话场景**：持卡人取消商品/服务但账单未退款（含分时度假 14 天、担保预订 No-show 费）。商户需披露政策+证明取消不符合约定。
- **业务分类**：卡组织 Visa｜原因码 13.7（Cancelled Merchandise/Services）｜大类 Consumer Dispute｜行业 旅游/服务｜渠道 预订｜交易类型 取消退款｜数据来源类别 规则还原场景（原文仅给原因码+规则，无完整故事）
- **来源**：SRC-01｜定位：SRC-01 P49-50｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：A Timeshare cancellation was not processed within 14 days of the contract or receipt date.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=无
- **资金关系**：who_paid_whom：持卡人预付；who_initiated：持卡人主张取消未退款；who_received_notice：商户；who_bears_risk：未按政策退款商户
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 预订/商品｜渠道 卡支付｜认证 NOT_STATED｜履约 已取消｜退款 未退款
- **拒付事实**：触发 取消未退款｜持卡人主张 已取消｜通知 13.7｜收到时间 NOT_STATED｜截止 NOT_STATED｜商户立场 取消超期/不合规｜建议 条件性（依据：政策披露+取消时间判定）
- **所需证据**：
  - 取消/退款政策披露证明（POLICY，必填）——为何需要：证明政策已告知；规则依据：SRC-01 P17/P49-50；本案可得性：视案件而定；缺失后果：须退款
  - 取消时间/未按政策取消证明（TIMESTAMP，必填）——为何需要：证明取消不符合约定；规则依据：SRC-01 P49-50；本案可得性：视案件而定；缺失后果：抗辩无据
- **处理流程**：first_see：案件进入后按原因码匹配规则 → auto：规则引擎装载对应条件与证据清单 → ops：按清单收集证据 → agent：解释原因码与证据要求 → human：确认关键事实 → reviewer：审核后放行 → submit_condition：证据满足对应原因码要求 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则还原）｜成功因素：披露+超期证据｜失败因素：政策未披露｜可否预防：是｜商户改进：政策显式披露｜未决问题：各州立法差异
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、时间线视图
  - 演示步骤：展示取消时间线
- **关联案例**：CB-CASE-023、CB-CASE-033

## CB-CASE-045｜RULE_DERIVED｜Mastercard 4853 货不对板/瑕疵：典型场景（规则还原）

- **一句话场景**：持卡人称商品与描述不符或损坏。商户可抗辩：已修/已换/按约交付（2700）、单据篡改（2001）、退货欺诈（2004）、已退款（2011）、拒付无效。
- **业务分类**：卡组织 Mastercard｜原因码 4853（Cardholder Dispute）｜大类 Consumer Dispute｜行业 电商/零售｜渠道 线上｜交易类型 实物商品｜数据来源类别 规则还原场景（原文仅给原因码+规则，无完整故事）
- **来源**：SRC-02、SRC-03｜定位：SRC-02 P157-177/P953-967; SRC-03 §28｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：The cardholder engaged in the transaction; the merchandise or services were not as described or were defective.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=无
- **资金关系**：who_paid_whom：持卡人付款；who_initiated：持卡人主张货不对板；who_received_notice：商户；who_bears_risk：举证责任在商户
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 已收货但争议｜退款 NOT_STATED
- **拒付事实**：触发 货不对板｜持卡人主张 与描述不符/有缺陷｜通知 4853｜收到时间 NOT_STATED｜截止 120 天（SP 30/45 天地区而异）｜商户立场 已按约交付｜建议 条件性（依据：按 2700/2001/2004/2011/无效清单选择抗辩路径）
- **所需证据**：
  - 已修/已换/按约交付说明（MERCHANT_NARRATIVE，必填）——为何需要：2700 抗辩；规则依据：SRC-02 P160-170；本案可得性：视案件而定；缺失后果：转向其他抗辩
  - 专家/检验意见（INSPECTION，可选）——为何需要：强化质量/真实性证明；规则依据：SRC-02 P158-159；本案可得性：视案件而定；缺失后果：主观争议难反驳
- **处理流程**：first_see：案件进入后按原因码匹配规则 → auto：规则引擎装载对应条件与证据清单 → ops：按清单收集证据 → agent：解释原因码与证据要求 → human：确认关键事实 → reviewer：审核后放行 → submit_condition：证据满足对应原因码要求 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则还原）｜成功因素：修复记录清晰｜失败因素：无记录｜可否预防：是｜商户改进：质检留档｜未决问题：主观瑕疵判定尺度
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、证据上传、Agent
  - 演示步骤：选择抗辩路径→上传证据→提交
- **关联案例**：CB-CASE-028

## CB-CASE-046｜RULE_DERIVED｜Mastercard 4853 商品/服务未提供：典型场景（规则还原）

- **一句话场景**：持卡人称未收到商品（含空箱、延迟交付、商户停业）。时限：120 天（大陆 90 天）；延迟交付无约定日期须等 30 天后提。
- **业务分类**：卡组织 Mastercard｜原因码 4853（Cardholder Dispute（Goods or Services Not Provided））｜大类 Consumer Dispute｜行业 电商/服务｜渠道 线上｜交易类型 实物/服务｜数据来源类别 规则还原场景（原文仅给原因码+规则，无完整故事）
- **来源**：SRC-02｜定位：SRC-02 P177-184/P967-983｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：This chargeback applies when the cardholder receives an empty box or a box containing worthless items, such as a brick or a stack of paper.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=物流
- **资金关系**：who_paid_whom：持卡人付款；who_initiated：持卡人主张未收到；who_received_notice：商户；who_bears_risk：商户举证履约
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 未收到｜退款 NOT_STATED
- **拒付事实**：触发 未收到｜持卡人主张 没收到商品/服务｜通知 4853｜收到时间 NOT_STATED｜截止 120 天（大陆 90 天；停业礼品卡 540 天）｜商户立场 已提供｜建议 条件性（依据：交付照片/签收/QR 使用记录/机票已用等证据则抗辩）
- **所需证据**：
  - 交付证明（签收/QR/PIN 使用/航班已发生）（DELIVERY，必填）——为何需要：证明已提供；规则依据：SRC-02 P183/P972；本案可得性：视案件而定；缺失后果：抗辩无据
- **处理流程**：first_see：案件进入后按原因码匹配规则 → auto：规则引擎装载对应条件与证据清单 → ops：按清单收集证据 → agent：解释原因码与证据要求 → human：确认关键事实 → reviewer：审核后放行 → submit_condition：证据满足对应原因码要求 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则还原）｜成功因素：交付证明完整｜失败因素：无记录｜可否预防：是｜商户改进：交付留档｜未决问题：代收效力
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、证据上传
  - 演示步骤：上传交付证明→提交
- **关联案例**：CB-CASE-004、CB-CASE-031

## CB-CASE-047｜RULE_DERIVED｜Mastercard 4853 退款未处理：典型场景（规则还原）

- **一句话场景**：持卡人应得退款未处理（含 VAT 退税）。商户抗辩：退款本不欠（2700）/已退款（2011）/退货欺诈（2004）。退款须在 SP 中记录。
- **业务分类**：卡组织 Mastercard｜原因码 4853（Cardholder Dispute（Refund Not Processed））｜大类 Consumer Dispute｜行业 通用｜渠道 通用｜交易类型 退款｜数据来源类别 规则还原场景（原文仅给原因码+规则，无完整故事）
- **来源**：SRC-02｜定位：SRC-02 P273-276/P1036-1051｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：The cardholder claims that a refund or credit was expected but not processed.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=无
- **资金关系**：who_paid_whom：应退款未退；who_initiated：持卡人主张退款未处理；who_received_notice：商户；who_bears_risk：未退款商户
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 NOT_STATED｜退款 未处理
- **拒付事实**：触发 退款未处理｜持卡人主张 应退未退｜通知 4853｜收到时间 NOT_STATED｜截止 15–120 天（VAT 120 天）｜商户立场 退款不欠/已退｜建议 条件性（依据：已退款则 2011 并在 SP 记录；不欠则 2700）
- **所需证据**：
  - 退款记录（REFUND_RECORD，必填）——为何需要：证明已退或不该退；规则依据：SRC-02 P273-276；本案可得性：视案件而定；缺失后果：建议退款
- **处理流程**：first_see：案件进入后按原因码匹配规则 → auto：规则引擎装载对应条件与证据清单 → ops：按清单收集证据 → agent：解释原因码与证据要求 → human：确认关键事实 → reviewer：审核后放行 → submit_condition：证据满足对应原因码要求 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则还原）｜成功因素：退款记录可查｜失败因素：无记录｜可否预防：是｜商户改进：退款即时同步｜未决问题：部分退款处理
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：退款匹配、案件详情
  - 演示步骤：退款匹配→SP 记录→提交
- **关联案例**：CB-CASE-029、CB-CASE-072

## CB-CASE-048｜RULE_DERIVED｜Mastercard 4837 无持卡人授权：典型场景（规则还原）

- **一句话场景**：持卡人声称未授权交易。商户抗辩路径多：addendum 责任、AVS 匹配、认证（ECI 211/212/217/242）、Compelling Evidence、No-show、退款、14 项无效拒付。
- **业务分类**：卡组织 Mastercard｜原因码 4837（No Cardholder Authorization）｜大类 Fraud｜行业 通用｜渠道 线上/线下｜交易类型 欺诈/未授权｜数据来源类别 规则还原场景（原文仅给原因码+规则，无完整故事）
- **来源**：SRC-02、SRC-03｜定位：SRC-02 P489-563; SRC-03 §28｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：The cardholder claims that he or she did not authorize the transaction.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=无
- **资金关系**：who_paid_whom：交易扣款；who_initiated：持卡人否认授权；who_received_notice：商户；who_bears_risk：商户默认
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 可选 3DS/AVS｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 未授权｜持卡人主张 我没授权｜通知 4837｜收到时间 NOT_STATED｜截止 120 天（大陆 5–90 天）｜商户立场 持卡人参与了交易｜建议 条件性（依据：认证/CE/AVS/历史交易满足则可抗辩；guest checkout 无 CE）
- **所需证据**：
  - 3DS 认证（ECI 211/212/217/242）（AUTH，可选）——为何需要：认证抗辩；规则依据：SRC-02 P503；本案可得性：视案件而定；缺失后果：转向 CE
  - Compelling Evidence（注册/历史交易等）（COMP_EVID，可选）——为何需要：证明持卡人参与；规则依据：SRC-02 P505-509；本案可得性：视案件而定；缺失后果：无 CE 则建议接受
- **处理流程**：first_see：案件进入后按原因码匹配规则 → auto：规则引擎装载对应条件与证据清单 → ops：按清单收集证据 → agent：解释原因码与证据要求 → human：确认关键事实 → reviewer：审核后放行 → submit_condition：证据满足对应原因码要求 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则还原）｜成功因素：认证/CE 齐全｜失败因素：guest checkout｜可否预防：是｜商户改进：强制注册+3DS｜未决问题：First-Party Trust 扩展节奏
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：案件详情、CE 匹配、Agent
  - 演示步骤：展示认证/CE 匹配结果
- **关联案例**：CB-CASE-025、CB-CASE-040、CB-CASE-061

## CB-CASE-049｜RULE_DERIVED｜Mastercard 4808 授权相关拒付：典型场景（规则还原）

- **一句话场景**：发卡行主张授权类问题：未获授权、离线芯片超 7 天清算、退款超 5 天、账户状态化、拒绝后 Stand-in 批准、CAT 3 违规、Transit FRR/FRIL。
- **业务分类**：卡组织 Mastercard｜原因码 4808（Authorization-related Chargeback）｜大类 Authorization｜行业 通用｜渠道 通用｜交易类型 授权｜数据来源类别 规则还原场景（原文仅给原因码+规则，无完整故事）
- **来源**：SRC-02｜定位：SRC-02 P54-150/P880-947｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：Authorization-related chargeback message reason code 4808/08.
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户；platform=无
- **资金关系**：who_paid_whom：交易入账；who_initiated：发卡行拒付；who_received_notice：收单行；who_bears_risk：授权违规方
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 授权｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 授权类拒付｜持卡人主张 N/A｜通知 4808｜收到时间 NOT_STATED｜截止 90 天（SP 30/45 天）｜商户立场 授权正确取得｜建议 条件性（依据：2008 授权已取得/2713 一次授权多笔清算/2011 已退款）
- **所需证据**：
  - 授权记录（AUTH_LOG，必填）——为何需要：2008/2713 抗辩；规则依据：SRC-02 P64-73/P889-890；本案可得性：视案件而定；缺失后果：建议接受
- **处理流程**：first_see：案件进入后按原因码匹配规则 → auto：规则引擎装载对应条件与证据清单 → ops：按清单收集证据 → agent：解释原因码与证据要求 → human：确认关键事实 → reviewer：审核后放行 → submit_condition：证据满足对应原因码要求 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则还原）｜成功因素：授权记录完整｜失败因素：记录缺失｜可否预防：是｜商户改进：授权合规｜未决问题：SP 时限 30/45 差异
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎、案件详情
  - 演示步骤：展示授权比对
- **关联案例**：CB-CASE-007、CB-CASE-008

## CB-CASE-050｜RULE_DERIVED｜Mastercard 4834 POI 错误（重复扣款等）：典型场景（规则还原）

- **一句话场景**：POI 错误九类：重复扣款、金额错、cash back 未给、ATM 未出钞、loss/theft/damage、币种错、退款纠错汇损、不当附加费、不合理金额。
- **业务分类**：卡组织 Mastercard｜原因码 4834（Point-of-Interaction Error）｜大类 Processing Error｜行业 通用/ATM/零售｜渠道 通用｜交易类型 处理错误｜数据来源类别 规则还原场景（原文仅给原因码+规则，无完整故事）
- **来源**：SRC-02｜定位：SRC-02 P685-776/P1324-1407｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：Point-of-Interaction Error (Message Reason Codes 4834/34).
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=商户/ATM；platform=无
- **资金关系**：who_paid_whom：交易扣款；who_initiated：持卡人主张处理错误；who_received_notice：商户；who_bears_risk：处理错误方
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 POI 错误｜持卡人主张 扣款有误｜通知 4834｜收到时间 NOT_STATED｜截止 90/120 天（子类而异）｜商户立场 处理正确｜建议 条件性（依据：2700 对应纠正证据；差额类只退差额）
- **所需证据**：
  - 终端/交易记录（按子类）（TX_RECORD，必填）——为何需要：证明处理正确；规则依据：SRC-02 P685-776；本案可得性：视案件而定；缺失后果：建议接受
- **处理流程**：first_see：案件进入后按原因码匹配规则 → auto：规则引擎装载对应条件与证据清单 → ops：按清单收集证据 → agent：解释原因码与证据要求 → human：确认关键事实 → reviewer：审核后放行 → submit_condition：证据满足对应原因码要求 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则还原）｜成功因素：记录完整｜失败因素：记录缺失｜可否预防：是｜商户改进：终端与清算数据质量｜未决问题：4834/4831 过渡
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎、案件详情
  - 演示步骤：展示子类判定
- **关联案例**：CB-CASE-014、CB-CASE-017、CB-CASE-073

## CB-CASE-051｜RULE_DERIVED｜Mastercard 4870/4871 芯片责任转移：典型场景（规则还原）

- **一句话场景**：伪卡/遗失被盗卡在非芯片终端交易，责任向未处理芯片的一方转移。商户抗辩：DE 55 已提供、非芯片责任交易、FNS>35、未上报欺诈库等。
- **业务分类**：卡组织 Mastercard｜原因码 4870/4871（Chip Liability Shift (Counterfeit / Lost-Stolen-NRI)）｜大类 Fraud｜行业 线下零售｜渠道 线下｜交易类型 欺诈｜数据来源类别 规则还原场景（原文仅给原因码+规则，无完整故事）
- **来源**：SRC-02｜定位：SRC-02 P578-636/P1241-1288｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：Chip Liability Shift (Message Reason Codes 4870/70 and 4871).
- **参与者**：cardholder=持卡人；issuer=发卡行；acquirer=收单行；merchant=线下商户；platform=无
- **资金关系**：who_paid_whom：交易扣款；who_initiated：持卡人否认交易；who_received_notice：商户；who_bears_risk：按芯片责任规则转移
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 芯片卡/磁条｜认证 EMV/PIN｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 芯片责任转移拒付｜持卡人主张 未授权｜通知 4870/4871｜收到时间 NOT_STATED｜截止 120 天｜商户立场 芯片数据已提交｜建议 条件性（依据：DE 55 已提供或非责任转移交易则抗辩）
- **所需证据**：
  - DE 55/芯片数据/终端能力（EMV_DATA，必填）——为何需要：责任判定；规则依据：SRC-02 P588-589；本案可得性：视案件而定；缺失后果：责任转移
- **处理流程**：first_see：案件进入后按原因码匹配规则 → auto：规则引擎装载对应条件与证据清单 → ops：按清单收集证据 → agent：解释原因码与证据要求 → human：确认关键事实 → reviewer：审核后放行 → submit_condition：证据满足对应原因码要求 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：规则还原）｜成功因素：DE 55 完整｜失败因素：fallback 未标识｜可否预防：是｜商户改进：终端升级支持芯片｜未决问题：4871 章节 4870 代码残留
- **OceanPilot 映射**：演示 —｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎

## CB-CASE-052｜RULE_DERIVED｜Amex C08/C02：未收到商品与退款未处理（规则映射还原）

- **一句话场景**：Amex 无官方原文时仅据 SRC-03 映射：C08=未收到商品、C02=退款未处理；证据要求按 Visa/MC 同类场景类比，需 Amex 原文确认。
- **业务分类**：卡组织 American Express｜原因码 C08 / C02（Goods/Services Not Received / Credit Not Processed）｜大类 Consumer Dispute｜行业 通用｜渠道 通用｜交易类型 商品/退款｜数据来源类别 规则还原场景（原文仅给原因码+规则，无完整故事）
- **来源**：SRC-03｜定位：SRC-03 §28｜置信度 HIGH｜需人工复核 否
- **原文摘录（≤50 词）**：编号2 服务未提供或未收到商品→C08；编号8 未收到退款→C02（ODPM 映射表）。
- **参与者**：cardholder=持卡人；issuer=Amex；acquirer=收单方；merchant=商户；platform=无
- **资金关系**：who_paid_whom：持卡人付款；who_initiated：持卡人主张未收到/未退款；who_received_notice：商户；who_bears_risk：商户
- **交易事实**：金额 NOT_STATED｜时间 NOT_STATED｜商品 NOT_STATED｜渠道 NOT_STATED｜认证 NOT_STATED｜履约 NOT_STATED｜退款 NOT_STATED
- **拒付事实**：触发 未收到/退款未处理｜持卡人主张 NOT_STATED｜通知 C08/C02｜收到时间 NOT_STATED｜截止 NOT_STATED（原文缺失）｜商户立场 NOT_STATED｜建议 信息不足（依据：Amex 原文缺失，按同类场景逻辑暂列证据清单，需业务确认）
- **所需证据**：
  - 交付/退款证明（类比）（DELIVERY，必填）——为何需要：证明履约或退款；规则依据：SRC-03 §28（映射，非 Amex 原文）；本案可得性：视案件而定；缺失后果：建议接受
- **处理流程**：first_see：案件进入后按原因码匹配规则 → auto：规则引擎装载对应条件与证据清单 → ops：按清单收集证据 → agent：解释原因码与证据要求 → human：确认关键事实 → reviewer：审核后放行 → submit_condition：证据满足对应原因码要求 → upstream_result：NOT_STATED → final_status：PENDING
- **结局**：未说明（依据：无 Amex 原文）｜成功因素：NOT_STATED｜失败因素：NOT_STATED｜可否预防：NOT_STATED｜商户改进：NOT_STATED｜未决问题：Amex C 系列官方证据与时限（GAP-005）
- **OceanPilot 映射**：演示 —｜seed —｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则引擎（待 Amex 原文）
- **关联案例**：CB-CASE-032、CB-CASE-033

## CB-CASE-060｜SYNTHETIC_DEMO｜合成：证据充分的电商拒付抗辩案（13.1 类）

- **一句话场景**：虚构商户「云岚数码」(sandbox-mer-001) 被拒付 USD 299 耳机：物流轨迹完整、POD 签收人=持卡人、收货地址与账单地址一致。系统判定可抗辩并生成材料包。
- **业务分类**：卡组织 Visa｜原因码 13.1（Merchandise/Services Not Received）｜大类 Consumer Dispute｜行业 3C 电商｜渠道 线上｜交易类型 实物商品｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-01、SRC-03｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=Sandbox 用户 sandbox-user-001；issuer=发卡行（模拟）；acquirer=收单机构（模拟）；merchant=云岚数码 sandbox-mer-001；psp=OceanPilot；platform=物流 sandbox-courier-001
- **资金关系**：who_paid_whom：持卡人向商户支付 USD 299；who_initiated：持卡人主张未收到；who_received_notice：商户（OceanPilot 案件中心）；who_bears_risk：商户（可抗辩）
- **交易事实**：金额 USD 299｜时间 2026-08-01T10:30:00Z｜商品 无线降噪耳机｜渠道 电商 CNP｜认证 3DS 未强制（ECI 7）｜履约 已签收（POD 收件人=持卡人）｜退款 未退款
- **拒付事实**：触发 持卡人声称未收到商品｜持卡人主张 我没有收到耳机｜通知 13.1 拒付通知（模拟报文）｜收到时间 2026-08-25T02:00:00Z｜截止 2026-09-04T23:59:59Z（演示设定，Visa 天数需收单确认）｜商户立场 已妥投且签收人一致｜建议 抗辩（依据：证据链完整：Tracking→POD→收件人一致→地址匹配（依据 CB-CASE-026/041））
- **所需证据**：
  - 物流轨迹（TRACKING，必填）——为何需要：证明运输；规则依据：SRC-01 P40-41；本案可得性：是；缺失后果：证据链断裂
  - 签收证明（POD，必填）——为何需要：证明交付给本人；规则依据：SRC-03 §5；本案可得性：是；缺失后果：无法抗辩
- **处理流程**：first_see：首页待办置顶（截止 9/4，高准备度） → auto：物流数据对接、证据抽取、准备度评分、草稿生成 → ops：核对 POD 收件人 → agent：解释证据链与建议抗辩 → human：确认证据真实后一键确认 → reviewer：审核提交 → submit_condition：准备度达标+人工确认 → upstream_result：提交成功（模拟回执 ack-060） → final_status：SUBMITTED
- **结局**：待定（依据：合成设定：已提交，等待上游回执）｜成功因素：证据链完整｜失败因素：N/A（演示正面路径）｜可否预防：是｜商户改进：维持签收留档｜未决问题：演示案件无真实裁决
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：首页待办、案件列表、案件详情、证据上传与抽取、准备度评估、申诉草稿、材料包、人工审核、上游提交
  - 演示步骤：首页进入→查看证据链→准备度 95%→生成草稿→人工确认→提交→回执
- **合成标记**：依据规则 ['CB-CASE-026', 'CB-CASE-041']；来自资料的字段：证据链要求（SRC-03 §5、SRC-01 P40-41）：Tracking+Delivery Address+Recipient+POD；13.1 争议条件；演示补充字段：商户名、订单号、金额 USD 299、交易时间、物流单号、签收时间——全部为演示虚构；备注：金额/时间/编号均为虚构，仅证据链规则来自资料
- **核心案例**：是（证据充分抗辩的正面主路径演示）
- **关联案例**：CB-CASE-026、CB-CASE-041

## CB-CASE-061｜SYNTHETIC_DEMO｜合成：证据严重缺失、系统阻止提交（10.4 欺诈）

- **一句话场景**：虚构商户被 10.4 欺诈拒付：无 3DS、无设备指纹、无历史交易（guest checkout）。系统准备度 12%，阻止提交并建议接受。
- **业务分类**：卡组织 Visa｜原因码 10.4（Other Fraud – Card-Absent Environment）｜大类 Fraud｜行业 跨境电商｜渠道 线上｜交易类型 CNP 欺诈｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-01、SRC-03｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=Sandbox 用户 sandbox-user-002；issuer=发卡行（模拟）；acquirer=收单机构（模拟）；merchant=环球优选 sandbox-mer-002；psp=OceanPilot；platform=独立站
- **资金关系**：who_paid_whom：持卡人被扣 EUR 459；who_initiated：持卡人否认交易；who_received_notice：商户；who_bears_risk：商户（无证据）
- **交易事实**：金额 EUR 459｜时间 2026-08-10T18:00:00Z｜商品 智能手表｜渠道 独立站 CNP｜认证 无 3DS（guest checkout）｜履约 已发货（无签收）｜退款 未退款
- **拒付事实**：触发 持卡人否认交易｜持卡人主张 我没有买过｜通知 10.4｜收到时间 2026-08-28T01:00:00Z｜截止 2026-09-07T23:59:59Z（演示设定）｜商户立场 无法举证持卡人参与｜建议 接受（依据：CE3.0 要素全缺（无认证/无设备/无历史交易），抗辩成功率依据规则极低）
- **所需证据**：
  - 3DS 认证记录（AUTH，必填）——为何需要：认证保护；规则依据：SRC-01 P14/P26；本案可得性：否；缺失后果：转向 CE
  - 同设备历史未争议交易（HISTORY，必填）——为何需要：CE 核心；规则依据：SRC-01 P26；本案可得性：否；缺失后果：无法抗辩
- **处理流程**：first_see：首页红色低准备度待办 → auto：准备度 12%、阻断提交 → ops：选择接受或补证 → agent：解释证据缺失与 CE 条件 → human：确认接受 → reviewer：接受动作需审核权限 → submit_condition：无（阻止抗辩提交） → upstream_result：接受回执（模拟） → final_status：ACCEPTED_BY_MERCHANT
- **结局**：待定（依据：合成设定：等待商户选择接受）｜成功因素：N/A｜失败因素：证据全缺｜可否预防：是（可预防：强制 3DS）｜商户改进：强制 3DS 与注册登录｜未决问题：演示无真实裁决
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 ✓｜路演故事 ✓
  - 涉及模块：首页待办、案件详情、准备度评估、Agent、接受拒付流程、飞书提醒
  - 演示步骤：首页低准备度标记→Agent 解释为何无法抗辩→系统阻止提交→一键接受→通知
- **合成标记**：依据规则 ['CB-CASE-025', 'CB-CASE-040']；来自资料的字段：CE3.0/Compelling Evidence 要求（SRC-03 §3、SRC-01 P26/P54-58）；10.4 争议条件；演示补充字段：商户名、金额 EUR 459、guest checkout 场景；备注：演示虚构；阻断阈值属 OceanPilot 产品设定
- **核心案例**：是（证据不足阻止提交+建议接受的负面路径）
- **关联案例**：CB-CASE-025、CB-CASE-040

## CB-CASE-062｜SYNTHETIC_DEMO｜合成：更适合接受的拒付（4808 无授权）

- **一句话场景**：清算记录显示该笔交易从未获得授权批准（拒绝后无 Stand-in），结构化比对直接命中 4808。系统建议接受，不浪费时间收集证据。
- **业务分类**：卡组织 Mastercard｜原因码 4808（Authorization-related Chargeback）｜大类 Authorization｜行业 餐饮｜渠道 线下｜交易类型 授权问题｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-02｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=Sandbox 用户 sandbox-user-003；issuer=发卡行（模拟）；acquirer=收单机构（模拟）；merchant=南巷小馆 sandbox-mer-003；psp=OceanPilot；platform=无
- **资金关系**：who_paid_whom：交易入账 USD 68；who_initiated：发卡行授权类拒付；who_received_notice：商户；who_bears_risk：商户（无授权）
- **交易事实**：金额 USD 68｜时间 2026-08-15T12:10:00Z｜商品 堂食消费｜渠道 POS｜认证 无授权批准（拒绝后无 Stand-in）｜履约 已提供｜退款 未退款
- **拒付事实**：触发 授权缺失｜持卡人主张 N/A（发卡行主张）｜通知 4808｜收到时间 2026-08-30T03:00:00Z｜截止 2026-09-12T23:59:59Z（演示设定）｜商户立场 无授权记录｜建议 接受（依据：授权数据结构化比对直接命中 4808，无可抗辩空间）
- **所需证据**：
  - 授权记录（AUTH_LOG，必填）——为何需要：2008 抗辩前提；规则依据：SRC-02 P64-73；本案可得性：否；缺失后果：建议接受
- **处理流程**：first_see：首页标记规则直判案件 → auto：授权数据自动比对 → ops：确认接受 → agent：解释 4808 命中原因 → human：确认接受 → reviewer：审核接受动作 → submit_condition：N/A → upstream_result：接受回执（模拟） → final_status：ACCEPTED_BY_MERCHANT
- **结局**：待定（依据：合成设定）｜成功因素：N/A｜失败因素：无授权｜可否预防：是｜商户改进：POS 操作规范（拒绝不成交）｜未决问题：演示无真实裁决
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、规则引擎、接受拒付流程
  - 演示步骤：展示结构化比对结果→一键接受
- **合成标记**：依据规则 ['CB-CASE-049', 'CB-CASE-007']；来自资料的字段：4808 触发条件与抗辩路径（SRC-02 P54-73）；演示补充字段：商户名、金额 USD 68、交易细节；备注：演示虚构
- **核心案例**：是（规则直判+接受路径演示）
- **关联案例**：CB-CASE-049

## CB-CASE-063｜SYNTHETIC_DEMO｜合成：临近截止触发飞书提醒（13.1 未收到）

- **一句话场景**：证据已齐全但商户迟迟未处理，距离响应截止仅剩 3 天。系统向运营群发送飞书提醒卡片，运营当日完成提交。
- **业务分类**：卡组织 Visa｜原因码 13.1（Merchandise/Services Not Received）｜大类 Consumer Dispute｜行业 服装电商｜渠道 线上｜交易类型 实物商品｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-01、SRC-03｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=Sandbox 用户 sandbox-user-004；issuer=发卡行（模拟）；acquirer=收单机构（模拟）；merchant=织语服饰 sandbox-mer-004；psp=OceanPilot；platform=物流 sandbox-courier-002
- **资金关系**：who_paid_whom：持卡人支付 USD 89；who_initiated：持卡人主张未收到；who_received_notice：商户；who_bears_risk：超期则视为放弃抗辩
- **交易事实**：金额 USD 89｜时间 2026-08-05T09:00:00Z｜商品 针织衫｜渠道 电商｜认证 无｜履约 已签收｜退款 未退款
- **拒付事实**：触发 未收到｜持卡人主张 没收到｜通知 13.1｜收到时间 2026-08-26T02:00:00Z｜截止 2026-09-05T23:59:59Z（演示设定）｜商户立场 证据已齐未提交｜建议 抗辩（依据：证据齐全，但必须赶在截止前提交）
- **所需证据**：
  - 签收证明（POD，必填）——为何需要：履约证明；规则依据：SRC-03 §5；本案可得性：是；缺失后果：无法抗辩
- **处理流程**：first_see：首页置顶「临近截止」标签 → auto：飞书提醒调度（T-72h） → ops：点击卡片处理案件 → agent：说明截止风险 → human：确认提交 → reviewer：无需（已预审） → submit_condition：截止前提交 → upstream_result：提交成功（模拟） → final_status：SUBMITTED
- **结局**：待定（依据：合成设定：已按时提交）｜成功因素：提醒及时｜失败因素：超期｜可否预防：是｜商户改进：及时响应案件｜未决问题：演示无真实裁决
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 ✓｜路演故事 ✓
  - 涉及模块：首页待办、飞书提醒、案件详情、上游提交
  - 演示步骤：演示飞书卡片到达→点击跳转案件→提交→回执
- **合成标记**：依据规则 ['CB-CASE-026', 'CB-CASE-041']；来自资料的字段：13.1 证据链（SRC-03 §5）；演示补充字段：截止时间、飞书提醒阈值（产品设定）、商户与订单细节；备注：提醒阈值与截止天数均为产品设定
- **核心案例**：是（临近截止+飞书提醒演示）
- **关联案例**：CB-CASE-026

## CB-CASE-064｜SYNTHETIC_DEMO｜合成：已过期案件（无法再提交）

- **一句话场景**：商户错过响应截止 6 天。系统锁定提交入口，状态置为 EXPIRED，并展示规则依据与商户改进建议。
- **业务分类**：卡组织 Mastercard｜原因码 4853（Cardholder Dispute）｜大类 Consumer Dispute｜行业 旅游｜渠道 预订｜交易类型 取消退款｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-02｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=Sandbox 用户 sandbox-user-005；issuer=发卡行（模拟）；acquirer=收单机构（模拟）；merchant=远方假期 sandbox-mer-005；psp=OceanPilot；platform=无
- **资金关系**：who_paid_whom：持卡人支付订金；who_initiated：持卡人主张退款未处理；who_received_notice：商户；who_bears_risk：商户（已失抗辩机会）
- **交易事实**：金额 USD 420｜时间 2026-06-20T10:00:00Z｜商品 度假套餐订金｜渠道 卡支付｜认证 无｜履约 已取消｜退款 未退款
- **拒付事实**：触发 退款未处理｜持卡人主张 应退款｜通知 4853｜收到时间 2026-07-30T02:00:00Z｜截止 2026-08-28T23:59:59Z（演示设定，已过 6 天）｜商户立场 未及时响应｜建议 接受（依据：已过截止，系统锁定并默认接受）
- **所需证据**：
  - 退款记录（REFUND_RECORD，必填）——为何需要：本可抗辩；规则依据：SRC-02 P273-276；本案可得性：否；缺失后果：已过期，不再收集
- **处理流程**：first_see：首页「已过期」分组 → auto：状态机自动置 EXPIRED → ops：复盘原因 → agent：解释超期后果与改进建议 → human：无需 → reviewer：无需 → submit_condition：禁止提交 → upstream_result：N/A → final_status：EXPIRED
- **结局**：商户败（依据：合成设定：超期未响应，视为放弃（演示，非卡组织裁决））｜成功因素：N/A｜失败因素：错过截止｜可否预防：是｜商户改进：及时处理+开启飞书提醒｜未决问题：演示无真实裁决
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 ✓｜路演故事 ✓
  - 涉及模块：首页待办、案件详情、状态机、Agent
  - 演示步骤：打开过期案件→展示锁定状态与原因→Agent 复盘
- **合成标记**：依据规则 ['CB-CASE-045', 'CB-CASE-047']；来自资料的字段：4853 时限（SRC-02 P159 等）：120 天（大陆 90 天）；演示补充字段：截止时间、错过天数；备注：状态 EXPIRED 属 OceanPilot 状态机设计
- **核心案例**：是（已过期状态机演示）
- **关联案例**：CB-CASE-045

## CB-CASE-065｜SYNTHETIC_DEMO｜合成：文件抽取需人工修正（证据 OCR 错误）

- **一句话场景**：上传的 POD 被 OCR 识别为收件人「张珊」，人工比对原件实为「张杉」且与持卡人一致。系统标记低置信度字段，运营修正后重新校验通过。
- **业务分类**：卡组织 Visa｜原因码 13.1（Merchandise/Services Not Received）｜大类 Consumer Dispute｜行业 家居电商｜渠道 线上｜交易类型 实物商品｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-01、SRC-03｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=张杉 sandbox-user-006；issuer=发卡行（模拟）；acquirer=收单机构（模拟）；merchant=素居生活 sandbox-mer-006；psp=OceanPilot；platform=物流 sandbox-courier-003
- **资金关系**：who_paid_whom：持卡人支付 USD 156；who_initiated：持卡人主张未收到；who_received_notice：商户；who_bears_risk：商户（可抗辩）
- **交易事实**：金额 USD 156｜时间 2026-08-08T14:00:00Z｜商品 台灯｜渠道 电商｜认证 无｜履约 已签收｜退款 未退款
- **拒付事实**：触发 未收到｜持卡人主张 没收到｜通知 13.1｜收到时间 2026-08-29T02:00:00Z｜截止 2026-09-08T23:59:59Z（演示设定）｜商户立场 已签收｜建议 抗辩（依据：收件人修正后与持卡人一致，证据链成立）
- **所需证据**：
  - 签收证明（POD，必填）——为何需要：收件人比对；规则依据：SRC-03 §5；本案可得性：是（OCR 有误）；缺失后果：比对失败则无法抗辩
- **处理流程**：first_see：证据页字段高亮提示低置信 → auto：OCR 抽取+置信度评分 → ops：比对原件修正字段 → agent：提示需人工核对 → human：修正收件人姓名 → reviewer：复核修正 → submit_condition：低置信字段已确认 → upstream_result：提交成功（模拟） → final_status：SUBMITTED
- **结局**：待定（依据：合成设定：修正后已提交）｜成功因素：人工修正及时｜失败因素：未复核｜可否预防：是｜商户改进：关键字段人工复核｜未决问题：演示无真实裁决
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：证据上传与抽取、案件详情、人工审核
  - 演示步骤：展示低置信字段高亮→人工修正→重新校验→提交
- **合成标记**：依据规则 ['CB-CASE-026', 'CB-CASE-041']；来自资料的字段：13.1 收件人比对要求（SRC-03 §5）；演示补充字段：OCR 错误、修正动作、人名（虚构）；备注：OCR 场景为产品设定
- **核心案例**：是（文件抽取人工修正路径演示）
- **关联案例**：CB-CASE-026

## CB-CASE-066｜SYNTHETIC_DEMO｜合成：Agent 生成操作提案、用户确认后执行（4853 课程）

- **一句话场景**：数字课程拒付：Agent 检索到 17 次登录记录，生成「提交抗辩」操作提案，附材料包与规则引用；用户确认后提案被执行，全程留痕。
- **业务分类**：卡组织 Mastercard｜原因码 4853（Cardholder Dispute）｜大类 Consumer Dispute｜行业 在线教育｜渠道 线上｜交易类型 数字服务｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-02、SRC-03｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=Sandbox 用户 sandbox-user-007；issuer=发卡行（模拟）；acquirer=收单机构（模拟）；merchant=启明学堂 sandbox-mer-007；psp=OceanPilot；platform=课程平台
- **资金关系**：who_paid_whom：持卡人支付 USD 499；who_initiated：持卡人主张课程不可访问；who_received_notice：商户；who_bears_risk：商户（可抗辩）
- **交易事实**：金额 USD 499｜时间 2026-08-02T11:00:00Z｜商品 在线课程｜渠道 电商｜认证 账号｜履约 登录 17 次｜退款 未退款
- **拒付事实**：触发 服务不可用｜持卡人主张 课程打不开｜通知 4853｜收到时间 2026-08-27T02:00:00Z｜截止 2026-09-06T23:59:59Z（演示设定）｜商户立场 已被使用｜建议 抗辩（依据：消费日志构成证据链）
- **所需证据**：
  - 登录/访问记录（USAGE_LOG，必填）——为何需要：证明使用；规则依据：SRC-03 §12；本案可得性：是；缺失后果：无法抗辩
- **处理流程**：first_see：Agent 面板展示提案预览 → auto：检索证据+生成提案 → ops：审查提案 → agent：解释提案依据 → human：确认提案 → reviewer：无需（提案含证据） → submit_condition：用户确认提案 → upstream_result：提交成功（模拟） → final_status：SUBMITTED
- **结局**：待定（依据：合成设定：提案执行后已提交）｜成功因素：证据充分｜失败因素：N/A｜可否预防：是｜商户改进：记录消费行为｜未决问题：演示无真实裁决
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：Agent、操作提案、申诉草稿、材料包、审计
  - 演示步骤：Agent 生成提案→展示规则引用与材料包→用户确认→提案执行→审计留痕
- **合成标记**：依据规则 ['CB-CASE-031', 'CB-CASE-046']；来自资料的字段：4853 消费证据链（SRC-03 §12）；演示补充字段：登录次数、提案流程（产品设定）、虚构商户；备注：提案机制为产品设定
- **核心案例**：是（Agent 提案+用户确认的产品交互演示）
- **关联案例**：CB-CASE-031

## CB-CASE-067｜SYNTHETIC_DEMO｜合成：提案因 case revision 过期被拒绝

- **一句话场景**：Agent 生成提案后，另一运营同时更新了案件（版本号 +1）。用户点击确认时系统检测 revision 不匹配，拒绝执行并要求基于最新版本重新生成。
- **业务分类**：卡组织 Mastercard｜原因码 4853（Cardholder Dispute）｜大类 Consumer Dispute｜行业 3C 电商｜渠道 线上｜交易类型 实物商品｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-02｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=Sandbox 用户 sandbox-user-008；issuer=发卡行（模拟）；acquirer=收单机构（模拟）；merchant=极光数码 sandbox-mer-008；psp=OceanPilot；platform=无
- **资金关系**：who_paid_whom：持卡人支付 USD 88；who_initiated：持卡人主张货不对板；who_received_notice：商户；who_bears_risk：商户
- **交易事实**：金额 USD 88｜时间 2026-08-11T15:00:00Z｜商品 键盘｜渠道 电商｜认证 无｜履约 已收货｜退款 未退款
- **拒付事实**：触发 货不对板｜持卡人主张 描述不符｜通知 4853｜收到时间 2026-08-31T02:00:00Z｜截止 2026-09-10T23:59:59Z（演示设定）｜商户立场 已按约交付｜建议 抗辩（依据：基于最新版本证据重新提案）
- **所需证据**：
  - 按约交付说明（MERCHANT_NARRATIVE，必填）——为何需要：2700 抗辩；规则依据：SRC-02 P160-170；本案可得性：是；缺失后果：抗辩不成立
- **处理流程**：first_see：确认弹窗报「案件已更新」 → auto：revision 检测 → ops：重新处理 → agent：基于最新版本重新生成 → human：再次确认 → reviewer：审核 → submit_condition：提案版本=当前版本 → upstream_result：提交成功（模拟） → final_status：SUBMITTED
- **结局**：待定（依据：合成设定：重新生成提案后提交）｜成功因素：版本检测生效｜失败因素：N/A｜可否预防：是｜商户改进：协作时留意版本提示｜未决问题：演示无真实裁决
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：Agent、操作提案、案件详情、并发控制
  - 演示步骤：演示并发更新→确认被拒→基于新版本重新生成→提交
- **合成标记**：依据规则 ['CB-CASE-045']；来自资料的字段：4853 抗辩证据要求（SRC-02 P157-177）；演示补充字段：并发更新、revision 机制（产品设定）；备注：revision 机制为产品设定
- **核心案例**：是（乐观锁/case revision 并发演示）
- **关联案例**：CB-CASE-066

## CB-CASE-068｜SYNTHETIC_DEMO｜合成：上游提交超时后幂等重试成功

- **一句话场景**：提交抗辩时上游接口超时。系统以幂等键重试，未产生重复提交，最终收到成功回执；审计记录显示一次业务提交+两次网络重试。
- **业务分类**：卡组织 Visa｜原因码 13.1（Merchandise/Services Not Received）｜大类 Consumer Dispute｜行业 服装电商｜渠道 线上｜交易类型 实物商品｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-01、SRC-03｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=Sandbox 用户 sandbox-user-009；issuer=发卡行（模拟）；acquirer=上游收单（模拟）；merchant=栖木服饰 sandbox-mer-009；psp=OceanPilot；platform=无
- **资金关系**：who_paid_whom：持卡人支付 USD 132；who_initiated：持卡人主张未收到；who_received_notice：商户；who_bears_risk：商户（可抗辩）
- **交易事实**：金额 USD 132｜时间 2026-08-12T16:00:00Z｜商品 风衣｜渠道 电商｜认证 无｜履约 已签收｜退款 未退款
- **拒付事实**：触发 未收到｜持卡人主张 没收到｜通知 13.1｜收到时间 2026-08-30T02:00:00Z｜截止 2026-09-09T23:59:59Z（演示设定）｜商户立场 已签收｜建议 抗辩（依据：证据链成立，重试机制保证提交成功）
- **所需证据**：
  - 签收证明（POD，必填）——为何需要：履约证明；规则依据：SRC-03 §5；本案可得性：是；缺失后果：无法抗辩
- **处理流程**：first_see：提交按钮转圈后提示重试中 → auto：幂等重试（3 次退避） → ops：无需干预 → agent：汇报重试结果 → human：无需 → reviewer：无需 → submit_condition：幂等键一致 → upstream_result：回执 ack-068（模拟） → final_status：SUBMITTED
- **结局**：待定（依据：合成设定：重试后收到回执）｜成功因素：幂等键｜失败因素：N/A｜可否预防：是｜商户改进：N/A｜未决问题：演示无真实裁决
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 ✓
  - 涉及模块：上游提交、幂等与重试、审计
  - 演示步骤：点击提交→模拟超时→自动重试→成功回执→展示审计
- **合成标记**：依据规则 ['CB-CASE-026', 'CB-CASE-041']；来自资料的字段：13.1 证据链（SRC-03 §5）；演示补充字段：超时与重试（产品设定）；备注：超时与重试为产品设定
- **核心案例**：是（上游超时幂等重试的可靠性演示）
- **关联案例**：CB-CASE-060

## CB-CASE-069｜SYNTHETIC_DEMO｜合成：跨租户访问必须被阻断（安全测试）

- **一句话场景**：租户 A 的运营人员携带租户 B 的案件 ID 访问，系统鉴权层返回 403；越权尝试被写入安全审计，触发告警。
- **业务分类**：卡组织 N/A（产品安全）｜原因码 N/A（Cross-tenant access）｜大类 Security｜行业 通用（安全）｜渠道 通用｜交易类型 安全测试｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-01、SRC-02｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：merchant=租户 A=云岚数码 sandbox-mer-001；租户 B=环球优选 sandbox-mer-002；psp=OceanPilot
- **资金关系**：who_paid_whom：N/A；who_initiated：租户 A 成员试图访问租户 B 案件；who_received_notice：N/A；who_bears_risk：越权访问风险
- **交易事实**：金额 N/A｜时间 N/A｜商品 N/A｜渠道 N/A｜认证 租户鉴权｜履约 N/A｜退款 N/A
- **拒付事实**：触发 N/A｜持卡人主张 N/A｜通知 N/A｜收到时间 N/A｜截止 N/A｜商户立场 N/A｜建议 信息不足（依据：N/A（安全测试））
- **所需证据**：无（不适用）
- **处理流程**：first_see：403 页面 → auto：鉴权拦截+审计写入 → ops：无需 → agent：不泄露其他租户信息 → human：无需 → reviewer：安全审计复查 → submit_condition：N/A → upstream_result：N/A → final_status：BLOCKED
- **结局**：未说明（依据：安全测试用例，无业务结局）｜成功因素：鉴权生效｜失败因素：越权泄露｜可否预防：NOT_APPLICABLE｜商户改进：N/A｜未决问题：N/A
- **OceanPilot 映射**：演示 ✓｜seed —｜规则测试 —｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 ✓｜飞书演示 —｜路演故事 —
  - 涉及模块：权限与鉴权、审计、告警
  - 演示步骤：跨租户 URL 访问→403→审计告警
- **合成标记**：依据规则 ['CB-CASE-060']；来自资料的字段：无（纯产品安全设计，与卡组织规则无关）；演示补充字段：租户模型、403 行为、告警（产品设定）；备注：纯产品安全设计
- **核心案例**：是（跨租户安全测试用例）

## CB-CASE-070｜SYNTHETIC_DEMO｜合成：规则版本变化但历史快照不变

- **一句话场景**：案件处理期间 Mastercard 旧码 4855 被标记将淘汰、并入 4853。案件仍按受理时的规则版本 2026-05 展示证据要求；新案件使用 2026-06 版本。
- **业务分类**：卡组织 Mastercard｜原因码 4853/4855（Cardholder Dispute（版本切换））｜大类 Consumer Dispute｜行业 电商｜渠道 线上｜交易类型 商品未收到｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-02、SRC-03｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=Sandbox 用户 sandbox-user-010；issuer=发卡行（模拟）；acquirer=收单机构（模拟）；merchant=森屿杂货 sandbox-mer-010；psp=OceanPilot；platform=无
- **资金关系**：who_paid_whom：持卡人支付 USD 45；who_initiated：持卡人主张未收到；who_received_notice：商户；who_bears_risk：商户
- **交易事实**：金额 USD 45｜时间 2026-08-13T10:00:00Z｜商品 家居用品｜渠道 电商｜认证 无｜履约 已发货｜退款 未退款
- **拒付事实**：触发 未收到｜持卡人主张 没收到｜通知 4855（旧码，将并入 4853）｜收到时间 2026-08-29T02:00:00Z｜截止 2026-09-08T23:59:59Z（演示设定）｜商户立场 已发货｜建议 条件性（依据：按受理版本规则展示证据要求，不受后续版本影响）
- **所需证据**：
  - 交付证明（DELIVERY，必填）——为何需要：履约；规则依据：SRC-02 P182-184；本案可得性：是；缺失后果：抗辩无据
- **处理流程**：first_see：案件详情显示规则版本 2026-05 → auto：快照绑定受理版本 → ops：无需 → agent：解释版本差异 → human：无需 → reviewer：无需 → submit_condition：按快照规则校验 → upstream_result：提交成功（模拟） → final_status：SUBMITTED
- **结局**：待定（依据：合成设定）｜成功因素：快照稳定｜失败因素：版本混淆｜可否预防：是｜商户改进：N/A｜未决问题：真实版本切换机制
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：规则版本管理、案件快照、审计
  - 演示步骤：展示历史案件规则快照 vs 新案件新版本
- **合成标记**：依据规则 ['CB-CASE-046']；来自资料的字段：淘汰码并入规则（SRC-02 P182 等、SRC-03 §11）；演示补充字段：规则版本号、快照行为（产品设定）；备注：版本切换为产品设定
- **核心案例**：是（规则版本与历史快照演示）
- **关联案例**：CB-CASE-046

## CB-CASE-071｜SYNTHETIC_DEMO｜合成：路演开场故事——友好欺诈（账单描述不清）

- **一句话场景**：路演开场：一家独立设计店铺收到「持卡人不认识这笔交易」的拒付。Agent 调出订单照片与商品描述后，运营发现是友好欺诈，用历史交易+设备证据抗辩成功。
- **业务分类**：卡组织 Visa｜原因码 10.4（Other Fraud – Card-Absent Environment）｜大类 Fraud｜行业 原创设计零售｜渠道 线上｜交易类型 CNP 欺诈/友好欺诈｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-01、SRC-03｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=Sandbox 用户 sandbox-user-011；issuer=发卡行（模拟）；acquirer=收单机构（模拟）；merchant=拾光设计 sandbox-mer-011；psp=OceanPilot；platform=独立站
- **资金关系**：who_paid_whom：持卡人支付 USD 310；who_initiated：持卡人称不认识交易；who_received_notice：商户；who_bears_risk：商户（可抗辩）
- **交易事实**：金额 USD 310｜时间 2026-08-06T20:00:00Z｜商品 手工皮包｜渠道 独立站 CNP｜认证 3DS（ECI 5）｜履约 已签收｜退款 未退款
- **拒付事实**：触发 持卡人不认识交易｜持卡人主张 这笔交易不是我做的｜通知 10.4｜收到时间 2026-08-26T02:00:00Z｜截止 2026-09-05T23:59:59Z（演示设定）｜商户立场 3DS 认证+历史交易可证｜建议 抗辩（依据：ECI 5 认证+同设备历史交易+签收，构成抗辩链）
- **所需证据**：
  - 3DS 认证（ECI 5）（AUTH，必填）——为何需要：认证保护；规则依据：SRC-01 P14；本案可得性：是；缺失后果：保护缺失
  - 同设备历史交易（HISTORY，可选）——为何需要：佐证本人交易；规则依据：SRC-01 P26；本案可得性：是；缺失后果：佐证减弱
  - 签收证明（POD，可选）——为何需要：佐证收货；规则依据：SRC-01 P54；本案可得性：是；缺失后果：佐证减弱
- **处理流程**：first_see：路演首页进入该案件 → auto：证据聚合与评分 → ops：按脚本演示 → agent：讲解友好欺诈 → human：确认提交 → reviewer：无需 → submit_condition：证据齐全 → upstream_result：模拟胜诉回执（路演设定） → final_status：MERCHANT_WON
- **结局**：商户胜（依据：合成设定：演示抗辩成功（非真实裁决，仅路演叙事））｜成功因素：认证+历史+签收｜失败因素：N/A｜可否预防：是｜商户改进：账单描述清晰化+3DS｜未决问题：演示无真实裁决
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 ✓｜路演故事 ✓
  - 涉及模块：首页待办、案件详情、Agent、准备度评估、上游提交
  - 演示步骤：开场叙事→展示证据链→提交→成功回执（路演）
- **合成标记**：依据规则 ['CB-CASE-025', 'CB-CASE-034', 'CB-CASE-040']；来自资料的字段：CE3.0 证据要求（SRC-03 §3、SRC-01 P26）；账单描述预防（SRC-03 §20）；演示补充字段：全部商户/订单/金额为虚构；备注：胜诉为路演设定，非真实裁决
- **核心案例**：是（路演开场故事（通俗+真实规则支撑））
- **关联案例**：CB-CASE-034

## CB-CASE-072｜SYNTHETIC_DEMO｜合成：退款未到账（seed 数据）

- **一句话场景**：商户 8 月 20 日发起退款 USD 120，持卡人 8 月 30 日仍称未收到。系统检索到退款 ARN 与结算状态，生成 2011/13.6 抗辩。
- **业务分类**：卡组织 Visa｜原因码 13.6（Credit Not Processed）｜大类 Consumer Dispute｜行业 美妆电商｜渠道 线上｜交易类型 退款未到账｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-01、SRC-03｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=Sandbox 用户 sandbox-user-012；issuer=发卡行（模拟）；acquirer=收单机构（模拟）；merchant=澄心美妆 sandbox-mer-012；psp=OceanPilot；platform=无
- **资金关系**：who_paid_whom：持卡人支付后商户退款；who_initiated：持卡人主张退款未到；who_received_notice：商户；who_bears_risk：商户（可证已退）
- **交易事实**：金额 USD 120｜时间 2026-08-18T09:00:00Z｜商品 护肤品套装｜渠道 电商｜认证 无｜履约 已退货｜退款 已发起退款（ARN sandbox-arn-072）
- **拒付事实**：触发 退款未到账｜持卡人主张 退款没收到｜通知 13.6｜收到时间 2026-08-30T02:00:00Z｜截止 2026-09-09T23:59:59Z（演示设定）｜商户立场 退款已结算｜建议 抗辩（依据：ARN+退款交易记录是核心证据）
- **所需证据**：
  - 退款 ARN/日期/金额/结算状态（REFUND_TX，必填）——为何需要：证明退款；规则依据：SRC-03 §8；本案可得性：是；缺失后果：建议接受
- **处理流程**：first_see：案件详情展示退款关联 → auto：退款匹配 → ops：核对结算状态 → agent：解释 ARN 证据价值 → human：确认 → reviewer：审核 → submit_condition：退款记录完整 → upstream_result：提交成功（模拟） → final_status：SUBMITTED
- **结局**：待定（依据：合成设定）｜成功因素：ARN 可查｜失败因素：仅聊天记录｜可否预防：是｜商户改进：退款即时留 ARN｜未决问题：演示无真实裁决
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：退款匹配、案件详情、Agent
  - 演示步骤：展示原交易↔退款关联→提交
- **合成标记**：依据规则 ['CB-CASE-029', 'CB-CASE-047']；来自资料的字段：13.6 退款关联要求（SRC-03 §8）；演示补充字段：订单/退款明细为虚构；备注：seed 可脱敏复用
- **关联案例**：CB-CASE-029

## CB-CASE-073｜SYNTHETIC_DEMO｜合成：重复扣款（seed 数据）

- **一句话场景**：同一订单被扣两笔 USD 66。系统比对订单号/授权/清算发现两笔指向同一订单，判定重复；商户确认后走退款补救并接受拒付。
- **业务分类**：卡组织 Mastercard｜原因码 4834（Point-of-Interaction Error）｜大类 Processing Error｜行业 运动电商｜渠道 线上｜交易类型 重复扣款｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-02、SRC-03｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=Sandbox 用户 sandbox-user-013；issuer=发卡行（模拟）；acquirer=收单机构（模拟）；merchant=锐动体育 sandbox-mer-013；psp=OceanPilot；platform=无
- **资金关系**：who_paid_whom：持卡人被扣两笔 USD 66；who_initiated：持卡人主张重复；who_received_notice：商户；who_bears_risk：重复部分商户
- **交易事实**：金额 USD 66 × 2｜时间 2026-08-14T10:01:00Z / 10:02:00Z｜商品 跑鞋｜渠道 电商｜认证 无｜履约 已发货（一笔）｜退款 未退款
- **拒付事实**：触发 重复扣款｜持卡人主张 被扣两次｜通知 4834｜收到时间 2026-08-31T02:00:00Z｜截止 2026-09-10T23:59:59Z（演示设定）｜商户立场 确认为系统重复扣款｜建议 接受（依据：两笔指向同一订单，判定重复，应退款并接受）
- **所需证据**：
  - 订单/授权/清算比对（ORDER_MATCH，必填）——为何需要：重复判定；规则依据：SRC-03 §9；本案可得性：是；缺失后果：无法判定
- **处理流程**：first_see：首页标记疑似重复 → auto：多字段比对 → ops：确认重复并退款 → agent：解释判定依据 → human：确认接受 → reviewer：审核接受 → submit_condition：N/A（接受） → upstream_result：接受回执（模拟） → final_status：ACCEPTED_BY_MERCHANT
- **结局**：商户接受（依据：合成设定：接受并退款补救）｜成功因素：判定清晰｜失败因素：N/A｜可否预防：是｜商户改进：扣款幂等控制｜未决问题：演示无真实裁决
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 ✓｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：重复判定、退款补救、案件详情
  - 演示步骤：展示多字段比对→接受→退款补救
- **合成标记**：依据规则 ['CB-CASE-030', 'CB-CASE-043', 'CB-CASE-050']；来自资料的字段：重复判定多字段比对（SRC-03 §9）；演示补充字段：订单/金额为虚构；备注：seed 可脱敏复用
- **关联案例**：CB-CASE-030

## CB-CASE-074｜SYNTHETIC_DEMO｜合成：货不对板抗辩（seed 数据，4853）

- **一句话场景**：持卡人称收到的台灯为旧款。商户提供 SKU、发货序列号与商品页快照证明一致，生成 2700 抗辩。
- **业务分类**：卡组织 Mastercard｜原因码 4853（Cardholder Dispute）｜大类 Consumer Dispute｜行业 家居电商｜渠道 线上｜交易类型 货不对板｜数据来源类别 项目合成演示案例（虚构商户/虚构用户）
- **来源**：SRC-02、SRC-03｜定位：合成案例，无原文定位（见 derived_from_rule_ids）｜置信度 HIGH｜需人工复核 否
- **参与者**：cardholder=Sandbox 用户 sandbox-user-014；issuer=发卡行（模拟）；acquirer=收单机构（模拟）；merchant=简居家居 sandbox-mer-014；psp=OceanPilot；platform=无
- **资金关系**：who_paid_whom：持卡人支付 USD 98；who_initiated：持卡人主张货不对板；who_received_notice：商户；who_bears_risk：商户（可抗辩）
- **交易事实**：金额 USD 98｜时间 2026-08-16T13:00:00Z｜商品 台灯（新款）｜渠道 电商｜认证 无｜履约 已收货｜退款 未退款
- **拒付事实**：触发 货不对板｜持卡人主张 收到旧款｜通知 4853｜收到时间 2026-08-30T02:00:00Z｜截止 2026-09-09T23:59:59Z（演示设定）｜商户立场 SKU 与序列号一致｜建议 抗辩（依据：SKU+序列号+页面快照构成一致性证明）
- **所需证据**：
  - SKU/商品页快照（PRODUCT_DESC，必填）——为何需要：一致性证明；规则依据：SRC-03 §7；本案可得性：是；缺失后果：抗辩无据
  - 发货序列号记录（DELIVERY_RECORD，必填）——为何需要：证明所发商品；规则依据：SRC-03 §7；本案可得性：是；缺失后果：抗辩无据
- **处理流程**：first_see：案件详情对比视图 → auto：SKU 与序列号比对 → ops：上传快照 → agent：解释一致性证明 → human：确认 → reviewer：审核 → submit_condition：证据齐全 → upstream_result：提交成功（模拟） → final_status：SUBMITTED
- **结局**：待定（依据：合成设定）｜成功因素：序列号一致｜失败因素：记录缺失｜可否预防：是｜商户改进：发货留序列号｜未决问题：演示无真实裁决
- **OceanPilot 映射**：演示 ✓｜seed ✓｜规则测试 ✓｜Agent 测试 ✓｜UI 测试 —｜安全测试 —｜飞书演示 —｜路演故事 —
  - 涉及模块：案件详情、证据上传
  - 演示步骤：展示描述 vs 交付对比
- **合成标记**：依据规则 ['CB-CASE-028', 'CB-CASE-045']；来自资料的字段：13.3/4853 一致性证明（SRC-03 §7、SRC-02 P157-177）；演示补充字段：订单/商品细节为虚构；备注：seed 可脱敏复用
- **关联案例**：CB-CASE-028
