import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const repo = process.cwd();
const outDir = path.join(repo, "outputs", "oceanpilot-chargeback-case-library-v1");
const accessed = "2026-08-14";

const E = {
  receipt: "transaction.receipt", avs: "auth.avs_result", cvv: "auth.cvv_result",
  threeds: "auth.threeds", device: "auth.device_ip_match", tracking: "fulfillment.tracking",
  pod: "fulfillment.proof_of_delivery", address: "fulfillment.address_match",
  description: "product.description", refund: "billing.refund_record",
  policy: "policy.terms_refund", comms: "comms.customer",
  cancellation: "subscription.cancellation_record", history: "history.prior_transactions",
  duplicate: "billing.duplicate_check",
};
const evidenceMeta = {
  [E.receipt]: ["交易收据", "证明交易金额、时间和商户主体"],
  [E.avs]: ["AVS结果", "核对账单地址验证结果"], [E.cvv]: ["CVV结果", "核对卡背码验证结果"],
  [E.threeds]: ["3DS认证", "核对强认证与责任转移"], [E.device]: ["设备/IP匹配", "核对本次与历史行为一致性"],
  [E.tracking]: ["物流轨迹", "证明发货与运输节点"], [E.pod]: ["签收证明", "证明送达时间、地点或签收人"],
  [E.address]: ["地址匹配", "核对订单与履约地址"], [E.description]: ["商品描述", "固定交易时展示的规格与承诺"],
  [E.refund]: ["退款记录", "证明退款发起、金额、时间与状态"], [E.policy]: ["条款与退款政策", "证明交易时披露并同意的规则"],
  [E.comms]: ["客户沟通", "还原投诉、补救与时间线"], [E.cancellation]: ["取消记录", "界定取消与扣款先后"],
  [E.history]: ["历史交易", "显示既往正常交易关系"], [E.duplicate]: ["重复核查", "比对授权、捕获与订单是否重复"],
};
const reasonPolicy = {
  FRAUD_CARD_NOT_PRESENT: {team:"RISK", required:[E.receipt,E.threeds,E.avs,E.cvv,E.device,E.history]},
  PRODUCT_NOT_RECEIVED: {team:"CUSTOMER_SUPPORT", required:[E.receipt,E.tracking,E.pod,E.address,E.comms]},
  PRODUCT_NOT_AS_DESCRIBED: {team:"BUSINESS", required:[E.receipt,E.description,E.comms,E.policy,E.pod]},
  DUPLICATE_PROCESSING: {team:"TECHNICAL_SUPPORT", required:[E.receipt,E.duplicate,E.history]},
  CREDIT_NOT_PROCESSED: {team:"FINANCE", required:[E.receipt,E.refund,E.policy,E.comms]},
  SUBSCRIPTION_CANCELED: {team:"CUSTOMER_SUPPORT", required:[E.receipt,E.cancellation,E.policy,E.comms]},
  AUTHORIZATION_ERROR: {team:"PSP_SUPPORT", required:[E.receipt,E.avs,E.cvv,E.threeds]},
};

const sources = [
  ["SRC-FOS","Financial Ombudsman Service final decisions database","Financial Ombudsman Service","https://www.financial-ombudsman.org.uk/businesses/resolving-complaint/ombudsman-decisions/search","PUBLIC_FINAL_DECISION","公开匿名最终决定；裁决对象通常是金融机构的处理，不等同卡组织仲裁"],
  ["SRC-VISA-LIB","Visa Merchant Resource Library","Visa","https://usa.visa.com/support/merchant/library.html","OFFICIAL_RULE_EXAMPLE","卡组织商户争议资料入口"],
  ["SRC-VISA-CE3","Visa Compelling Evidence 3.0 Merchant Readiness","Visa","https://usa.visa.com/content/dam/VCOM/regional/na/us/support-legal/documents/compelling-evidence-3.0-merchant-readiness-mar2023.pdf","OFFICIAL_RULE_EXAMPLE","历史交易、设备等证据示例；不是个案结果"],
  ["SRC-MC","Mastercard Chargeback Guide","Mastercard","https://www.mastercard.us/content/dam/public/mastercardcom/na/global-site/documents/chargeback-guide.pdf","OFFICIAL_RULE_EXAMPLE","流程、理由与证据规则；版本适用性需业务确认"],
  ["SRC-STRIPE-VIS","Visual evidence packets","Stripe","https://docs.stripe.com/disputes/visual-evidence","OFFICIAL_RULE_EXAMPLE","证据包视觉与结构示例"],
  ["SRC-STRIPE-BEST","Dispute evidence best practices","Stripe","https://docs.stripe.com/disputes/best-practices","OFFICIAL_RULE_EXAMPLE","证据相关性、可读性与提交建议"],
  ["SRC-STRIPE-LIFE","How disputes work","Stripe","https://docs.stripe.com/disputes/how-disputes-work","OFFICIAL_RULE_EXAMPLE","争议生命周期与状态；时限因网络和地区而异"],
  ["SRC-AIRWALLEX","Dispute flow","Airwallex","https://www.airwallex.com/docs/payments/payment-operations/disputes/dispute-flow","OFFICIAL_RULE_EXAMPLE","争议、预仲裁及状态流程"],
  ["SRC-ADYEN","Dispute reason codes","Adyen","https://docs.adyen.com/risk-management/understanding-disputes/dispute-reason-codes","OFFICIAL_RULE_EXAMPLE","理由码与抗辩材料概览"],
  ["SRC-JPM","Dispute Management User Guide","J.P. Morgan","https://www.jpmorgan.com/content/dam/jpmorgan/documents/payments/client-resource-center/asset-files/pdfs/dispute-managment-user-guide-new-updates-1.pdf","OFFICIAL_RULE_EXAMPLE","案件字段与结果状态参考"],
];

const realSpecs = [
  ["PUB-001","未授权理由被商户身份链反驳","FRAUD_CARD_NOT_PRESENT","专业服务","数字服务","英国",429,"GBP","NOT_DISCLOSED","NOT_DISCLOSED","消费者先称不认识交易，后承认本人付款但质疑服务","商户证明真实卡资料、长期账户、邮箱手机验证、稳定网络和服务履行","商户综合身份与服务证据反驳未授权主张","MERCHANT_PREVAILED","COMPLAINT_NOT_UPHELD","FOS_FINAL_DECISION","真实结果：拒付失败，临时退款收回；银行误称可二次拒付，仅另赔£50","先确认主张究竟是未授权还是服务争议；不能在一次失败后随意换理由重提",[E.receipt,E.device,E.history,E.comms,E.policy],"DRN-4956156"],
  ["PUB-002","自动续订但无取消证明","SUBSCRIPTION_CANCELED","订阅服务","数字订阅","英国",115.13,"GBP","NOT_DISCLOSED","NOT_DISCLOSED","消费者称续订前已取消，但没有确认邮件或表单回执","平台指出消费者承认订阅且条款写明自动续订","取消时间与续订扣款的先后无法由证据证明","NOT_RAISED","COMPLAINT_NOT_UPHELD","FOS_FINAL_DECISION","真实结果：因缺取消证明未继续拒付；申诉专员认为成功前景很低","产品应在取消提交时生成不可抵赖回执，并保留条款版本",[E.receipt,E.policy,E.comms],"DRN-5553620"],
  ["PUB-003","定制商品多次承诺送达仍未交付","PRODUCT_NOT_RECEIVED","家居零售","实体商品","英国",2391.34,"GBP","VISA","NOT_DISCLOSED","消费者称商品从未送达且多次承诺日期落空","商户以定制不可取消、已可安排配送为抗辩","商户抗辩没有正面证明在约定日期送达","DISCONTINUED","COMPLAINT_UPHELD","FOS_FINAL_DECISION","真实结果：银行停止争议；申诉专员认为应继续并判银行赔付及利息","分类必须围绕未交付事实，定制/不可退不是未收到的直接反驳",[E.receipt,E.comms],"DRN-4634402"],
  ["PUB-004","错误理由码导致唯一机会浪费","PRODUCT_NOT_RECEIVED","电商零售","实体商品","英国",85.97,"GBP","NOT_DISCLOSED","REFUND_NOT_RECEIVED_USED_IN_ERROR","消费者未收到任何商品；商户邮件对是否收款/退款互相矛盾","商户以未收到退货为由抗辩退款未到账","实际事实是未收到商品，却选择退款未到账理由","MERCHANT_PREVAILED","COMPLAINT_UPHELD","FOS_FINAL_DECISION","真实结果：错误理由码下拒付失败；申诉专员判银行退还款项并赔偿","必须先问清商品是否收到、退款是否承诺，再锁定理由码",[E.receipt,E.comms],"DRN-3125371"],
  ["PUB-005","商品不符但已丢弃无法退回","PRODUCT_NOT_AS_DESCRIBED","珠宝零售","实体商品","英国",25,"GBP","MASTERCARD","NOT_DISCLOSED","消费者称收到的图案与下单不符，但因不适已处置商品","商户先以已送达反驳未收到；后续商品已无法退回","不符主张可能成立，但商品不再可供退回","NOT_PURSUED","COMPLAINT_NOT_UPHELD","FOS_FINAL_DECISION","真实结果：未收到理由失败；不符理由因无法退货未继续","补问是否仍持有商品、是否已提出退货以及商户是否拒绝接收",[E.receipt,E.pod,E.description,E.comms],"DRN-5947106"],
  ["PUB-006","咨询服务有合同与履行记录","PRODUCT_NOT_RECEIVED","咨询服务","专业服务","英国",1199,"GBP","NOT_DISCLOSED","NOT_DISCLOSED","消费者称未按约提供服务并认为被骗","商户提交长篇咨询服务履行证据，案件进入预仲裁","签署合同、沟通及交付记录共同证明服务已提供","MERCHANT_PREVAILED","COMPLAINT_NOT_UPHELD","FOS_FINAL_DECISION","真实结果：预仲裁后拒付仍失败，临时退款收回","服务类不能只交合同，还要建立交付物与客户使用/沟通时间线",[E.receipt,E.policy,E.comms],"DRN-5250346"],
  ["PUB-007","假酒店网站把款转给真实汇款服务","PRODUCT_NOT_RECEIVED","旅游诈骗","资金转移服务","英国",596,"GBP","NOT_DISCLOSED","NOT_DISCLOSED","消费者以为预订酒店，实际向汇款服务支付且酒店无预订","收款商户证明其受托的资金转移服务已完成","底层骗局存在，但被争议商户已完成其合同服务","MERCHANT_PREVAILED","COMPLAINT_NOT_UPHELD","FOS_FINAL_DECISION","真实结果：汇款服务成功抗辩；申诉专员不要求银行赔付","区分消费者想买的东西、账单商户和实际被争议服务",[E.receipt,E.comms],"DRN-4400167"],
  ["PUB-008","假机票骗局中的汇款服务已履约","PRODUCT_NOT_RECEIVED","旅游诈骗","资金转移服务","英国",99,"GBP","NOT_DISCLOSED","NOT_DISCLOSED","消费者以为向旅行社付机票定金，实际通过汇款服务转账","汇款服务证明已按指令完成转移","机票未获得不代表汇款服务未提供","MERCHANT_PREVAILED","COMPLAINT_NOT_UPHELD","FOS_FINAL_DECISION","真实结果：卡交易拒付失败；另有银行转账追索也未追回","建案时识别资金流中哪个主体是商户，避免把诈骗损失误映射为未履约",[E.receipt,E.comms],"DRN-3728445"],
  ["PUB-009","现金与刷卡定金退款归属不清","CREDIT_NOT_PROCESSED","汽车销售","定金","英国",500,"GBP","NOT_DISCLOSED","NOT_DISCLOSED","消费者称现金部分已退、刷卡部分未退","商户证明仅有一笔£500卡定金，且已向银行账户退款£500","双方对退款对应哪种支付方式存在矛盾，消费者无反证","MERCHANT_PREVAILED","COMPLAINT_NOT_UPHELD","FOS_FINAL_DECISION","真实结果：商户抗辩后临时贷记被收回","混合支付必须逐笔关联支付介质、退款去向和金额，防止重复赔付",[E.receipt,E.refund,E.comms],"DRN6563116"],
  ["PUB-010","客人取消不可退酒店而酒店仍营业","PRODUCT_NOT_RECEIVED","酒店旅游","住宿服务","英国",318.60,"GBP","NOT_DISCLOSED","NOT_DISCLOSED","消费者因疫情与航班取消主动取消酒店","商户证明预订不可退且入住期间酒店可提供服务","是客人不能使用，而非商户取消或无法提供","MERCHANT_PREVAILED","COMPLAINT_NOT_UPHELD","FOS_FINAL_DECISION","真实结果：商户抗辩成功，临时贷记收回","把商户取消、政府关闭、消费者取消分成不同事实路径",[E.receipt,E.policy,E.comms],"DRN-3004919"],
  ["PUB-011","车辆质量争议因补证逾期与格式失败","PRODUCT_NOT_AS_DESCRIBED","汽车销售","二手车","英国",2190,"GBP","NOT_DISCLOSED","NOT_DISCLOSED","消费者称车辆存在试驾时未知问题并尝试退车","商户成功抗辩；消费者未在10天内补齐材料，通话录音格式未被接受","时限和文件格式使可能相关的证据无法进入审理","MERCHANT_PREVAILED","COMPLAINT_NOT_UPHELD","FOS_FINAL_DECISION","真实结果：拒付失败，申诉专员认为银行处理合理","系统应在收件时检查格式、页数、可读性与截止时间，而非提交时才发现",[E.receipt,E.description,E.comms],"DRN-3058378"],
  ["PUB-012","旅行商倒闭、承接方与保险责任混乱","PRODUCT_NOT_RECEIVED","邮轮旅游","旅行服务","英国",350,"GBP","NOT_DISCLOSED","NOT_DISCLOSED","消费者为邮轮付定金，原商户倒闭后被要求向新公司再次支付全价","抗辩材料涉及承接方、电子货币账户、保险与ATOL，且责任主体混乱","正确商户、服务是否承接、应由保险还是拒付承担需要逐层核验","MERCHANT_PREVAILED","COMPLAINT_UPHELD","FOS_FINAL_DECISION","真实结果：拒付未成功；申诉专员支持消费者并要求银行赔付及补偿","建立主体关系图和付款受益人校验，复杂案件强制人工复核",[E.receipt,E.policy,E.comms],"DRN-4403335"],
];

const synthSpecs = [
  ["SYN-001","数字道具已消费后称未授权","FRAUD_CARD_NOT_PRESENT","游戏","数字商品","玩家购买后24小时内消耗道具，随后否认交易",[E.receipt,E.threeds,E.device,E.history],"EXPECTED_WON","won","DIGITAL_GOODS_CONSUMED","3DS、账号登录和消耗日志形成同一时间线；人工核验账号是否被盗"],
  ["SYN-002","家庭共享设备上的未成年人购买","FRAUD_CARD_NOT_PRESENT","游戏","数字商品","持卡人称孩子未经允许在家庭平板充值",[E.receipt,E.device,E.history],"EXPECTED_LOST","lost","SHARED_FAMILY_DEVICE","设备匹配不等于持卡人授权；缺3DS时不应把家庭关系当作同意"],
  ["SYN-003","3DS通过但账户接管迹象明显","FRAUD_CARD_NOT_PRESENT","电商","高价值电子品","3DS成功，但新设备、新地址且登录凭据疑似泄露",[E.receipt,E.threeds,E.avs,E.cvv],"EXPECTED_PENDING","pending","CONTRADICTORY_FRAUD_SIGNALS","责任转移与账户接管信号冲突，必须人工审查并保留风险决定"],
  ["SYN-004","熟客突然否认周期性大额交易","FRAUD_CARD_NOT_PRESENT","SaaS","企业软件","同卡连续正常支付一年后否认最新一笔，设备与历史一致",[E.receipt,E.device,E.history,E.comms],"EXPECTED_WON","won","PRIOR_RELATIONSHIP","历史关系有帮助但不能替代认证；补齐登录与服务使用证明"],
  ["SYN-005","包裹签收后在门口被盗","PRODUCT_NOT_RECEIVED","电商","实体商品","承运商拍照妥投，消费者称回家时包裹已被盗",[E.receipt,E.tracking,E.pod,E.address],"EXPECTED_WON","won","PORCH_THEFT_AFTER_DELIVERY","先证明按约妥投；是否需签名取决于承诺、商品风险与适用规则"],
  ["SYN-006","一个订单只发了三件中的两件","PRODUCT_NOT_RECEIVED","电商","部分发货","订单三件商品，物流只证明两件送达，消费者争议全额",[E.receipt,E.tracking,E.pod,E.comms],"EXPECTED_PENDING","pending","PARTIAL_FULFILLMENT","按未交付部分计算争议金额，避免用部分送达反驳全部缺失"],
  ["SYN-007","虚拟课程已观看但称未收到","PRODUCT_NOT_RECEIVED","在线教育","数字服务","课程账号已观看80%，但消费者称没有收到服务",[E.receipt,E.device,E.comms,E.policy],"EXPECTED_WON","won","SERVICE_USAGE","数字服务以访问、观看和互动日志替代物流证据"],
  ["SYN-008","商户取消酒店却只给代金券","PRODUCT_NOT_RECEIVED","酒店旅游","住宿服务","酒店主动取消且无法提供住宿，只提供一年期代金券",[E.receipt,E.comms,E.policy],"EXPECTED_LOST","lost","MERCHANT_CANCELED","商户无法履约与客人主动取消不同；若无现金退款依据，接受或退款更合理"],
  ["SYN-009","页面写真皮但收到人造革","PRODUCT_NOT_AS_DESCRIBED","电商","实体商品","消费者提供开箱与材质检测，页面快照写真皮",[E.receipt,E.description,E.comms,E.pod],"EXPECTED_LOST","lost","OBJECTIVE_MISDESCRIPTION","客观规格矛盾且消费者愿意退货，商户应接受退款或提供反证"],
  ["SYN-010","颜色轻微偏差但页面有显示器免责声明","PRODUCT_NOT_AS_DESCRIBED","电商","实体商品","消费者称色差，商户页面注明不同屏幕可能有差异",[E.receipt,E.description,E.policy,E.comms,E.pod],"EXPECTED_WON","won","SUBJECTIVE_DIFFERENCE","判断是否为实质不符，并证明交易时已披露合理差异"],
  ["SYN-011","定制礼服尺寸不符但量体数据被改写","PRODUCT_NOT_AS_DESCRIBED","服装定制","定制商品","成衣与确认尺寸不符，后台记录显示商户后改数据",[E.receipt,E.description,E.comms,E.pod],"EXPECTED_LOST","lost","VERSIONED_DESCRIPTION","必须保留下单时版本；事后修改页面或规格会削弱证据可信度"],
  ["SYN-012","软件承诺功能未上线但客户持续使用","PRODUCT_NOT_AS_DESCRIBED","SaaS","数字服务","销售材料承诺关键功能，实际未上线；客户仍使用其他模块",[E.receipt,E.description,E.comms,E.policy],"EXPECTED_PENDING","pending","PARTIAL_SERVICE_VALUE","区分整体可用与关键承诺缺失，评估部分退款并人工复核"],
  ["SYN-013","两次授权但只捕获一次","DUPLICATE_PROCESSING","电商","卡支付","银行账单先显示两笔待入账，最终只有一笔完成",[E.receipt,E.duplicate,E.history],"EXPECTED_WON","won","DUPLICATE_AUTH_SINGLE_CAPTURE","授权冻结不是最终扣款；用授权/捕获状态解释并等待入账"],
  ["SYN-014","重试支付生成两笔捕获同一订单","DUPLICATE_PROCESSING","票务","卡支付","网络超时后客户端重试，服务端缺幂等键导致两笔成功捕获",[E.receipt,E.duplicate],"EXPECTED_LOST","lost","TRUE_DUPLICATE_CAPTURE","确认真实重复后主动退一笔并停止申诉"],
  ["SYN-015","同金额两笔但对应两张不同订单","DUPLICATE_PROCESSING","外卖","实体服务","同日同金额两笔，商品和收货时间不同",[E.receipt,E.duplicate,E.history,E.comms],"EXPECTED_WON","won","SAME_AMOUNT_DIFFERENT_ORDERS","用订单内容、时间和履约分别证明，不只比较金额"],
  ["SYN-016","部分退款后消费者发起全额拒付","CREDIT_NOT_PROCESSED","电商","实体商品","商户已退30%，消费者仍对100%发起争议",[E.receipt,E.refund,E.comms,E.policy],"EXPECTED_PENDING","pending","PARTIAL_REFUND_FULL_CHARGEBACK","核对剩余争议金额，防止重复退款并提交部分退款凭证"],
  ["SYN-017","退款与拒付同时在途造成双重赔付","CREDIT_NOT_PROCESSED","旅游","旅行服务","商户先发退款，隔日收到拒付；两条资金链同时处理中",[E.receipt,E.refund,E.comms],"EXPECTED_WON","won","REFUND_CHARGEBACK_COLLISION","冻结重复退款操作，关联原交易与退款ARN/状态，提示双重赔付风险"],
  ["SYN-018","退款已发起但跨币种到账较慢","CREDIT_NOT_PROCESSED","跨境电商","实体商品","退款完成后消费者因汇率与到账延迟称未收到",[E.receipt,E.refund,E.comms,E.policy],"EXPECTED_WON","won","FX_AND_POSTING_DELAY","解释退款路径与币种差异，提交可追踪退款记录而非只给内部截图"],
  ["SYN-019","取消发生在续订扣款后一秒","SUBSCRIPTION_CANCELED","SaaS","数字订阅","系统扣款时间为10:00:00，取消提交为10:00:01",[E.receipt,E.cancellation,E.policy,E.comms],"EXPECTED_WON","won","CANCELLATION_BOUNDARY","使用统一时区与服务器时间；同时检查条款是否清楚说明生效规则"],
  ["SYN-020","用户点取消但后台任务失败","SUBSCRIPTION_CANCELED","视频会员","数字订阅","前端显示取消成功，后台消息失败仍续费",[E.receipt,E.cancellation,E.comms],"EXPECTED_LOST","lost","CANCELLATION_STATE_DIVERGENCE","以用户看到的确认和审计日志为准，主动退款并修复状态一致性"],
  ["SYN-021","免费试用转付费提醒进入垃圾邮箱","SUBSCRIPTION_CANCELED","健身应用","数字订阅","用户未取消试用，条款明确转付费，提醒邮件未读",[E.receipt,E.policy,E.comms],"EXPECTED_WON","won","TRIAL_CONVERSION","证明显著披露与同意；未读提醒本身不等于已取消"],
  ["SYN-022","离线交易在授权过期后捕获","AUTHORIZATION_ERROR","酒店","预授权","入住预授权已过期，酒店数日后以旧授权捕获",[E.receipt,E.avs,E.cvv],"EXPECTED_LOST","lost","EXPIRED_AUTH_CAPTURE","核对授权有效期与捕获链；无法证明有效授权时不要硬申诉"],
  ["SYN-023","金额调整超过原授权容差","AUTHORIZATION_ERROR","租车","增量授权","最终扣款包含损坏费，未取得合规增量授权",[E.receipt,E.avs,E.cvv,E.comms],"EXPECTED_LOST","lost","AMOUNT_ABOVE_AUTHORIZATION","费用真实性与授权有效性是两件事；需补增量授权或接受争议"],
  ["SYN-024","客户撤诉但卡组织案件仍开放并晚反转","AUTHORIZATION_ERROR","电商","卡支付","消费者称已联系银行撤诉，商户后台先显示胜诉后又反转",[E.receipt,E.threeds,E.comms],"EXPECTED_PENDING","pending","WITHDRAWAL_LATE_WIN_REVERSAL","客户口头撤诉不等于案件关闭；以正式状态和资金入账为准并持续监控"],
];

const fosSources = realSpecs.map((r) => ["SRC-"+r[19],`Decision ${r[19]}`,"Financial Ombudsman Service",`https://www.financial-ombudsman.org.uk/decision/${r[19]}.pdf`,"PUBLIC_FINAL_DECISION","公开匿名最终决定；仅摘要与结果层级"]);
sources.push(...fosSources);

const cases = realSpecs.map((r) => ({
  case_id:r[0], title:r[1], authenticity:"PUBLIC_FINAL_DECISION", evidence_level:"A-PUBLIC-FINAL", synthetic:false,
  industry:r[3], item_type:r[4], jurisdiction:r[5], amount:r[6], currency:r[7], card_network:r[8], original_reason_code:r[9],
  reason_code:r[2], cardholder_claim:r[10], merchant_claim:r[11], core_conflict:r[12], dispute_stage:"FINAL_PUBLIC_DECISION",
  chargeback_outcome:r[13], adjudication_outcome:r[14], outcome_scope:r[15], result_summary:r[16], redo_action:r[17],
  present_evidence:r[18], special_tags:r[1].includes("错误理由码")?"WRONG_REASON_CODE":"PUBLIC_DECISION",
  responsible_team:reasonPolicy[r[2]].team, manual_review_reason:"PUBLIC_CASE_NOT_IMPORTABLE", oceanpilot_can_handle:"PARTIAL",
  product_gap:r[17], recommendation:r[17], source_id:"SRC-"+r[19], rule_basis:"公开最终决定事实摘要；不推断未披露字段",
  import_outcome:"", notes:"真实公开案例不进入CaseSampleRecord导入文件。",
}));

for (const s of synthSpecs) {
  const reason = s[2]; const present = s[6];
  cases.push({
    case_id:s[0], title:s[1], authenticity:"RULE_DERIVED_SYNTHETIC", evidence_level:"C-RULE-DERIVED", synthetic:true,
    industry:s[3], item_type:s[4], jurisdiction:"GLOBAL-SYNTHETIC", amount:null, currency:"NOT_DISCLOSED", card_network:"NOT_DISCLOSED", original_reason_code:"SYNTHETIC",
    reason_code:reason, cardholder_claim:s[5], merchant_claim:`商户按${reason}准备已有证据并等待人工决定`, core_conflict:s[5], dispute_stage:"SIMULATED_REVIEW",
    chargeback_outcome:s[7], adjudication_outcome:"NOT_APPLICABLE", outcome_scope:"SIMULATED_EXPECTATION",
    result_summary:`模拟预期：${s[7]}。${s[10]}`, redo_action:s[10], present_evidence:present, special_tags:s[9],
    responsible_team:reasonPolicy[reason].team, manual_review_reason:["EXPECTED_PENDING","EXPECTED_LOST"].includes(s[7])?"CONFLICT_OR_WEAK_EVIDENCE":"POLICY_REVIEW",
    oceanpilot_can_handle:"PARTIAL", product_gap:s[10], recommendation:s[10],
    source_id: reason==="FRAUD_CARD_NOT_PRESENT"?"SRC-VISA-CE3":(["PRODUCT_NOT_RECEIVED","PRODUCT_NOT_AS_DESCRIBED"].includes(reason)?"SRC-MC":(["CREDIT_NOT_PROCESSED","SUBSCRIPTION_CANCELED"].includes(reason)?"SRC-STRIPE-BEST":"SRC-AIRWALLEX")),
    rule_basis:`依据官方流程/证据原则构造；不是Oceanpayment真实规则或真实案件`, import_outcome:s[8], notes:"纯合成案例；金额、人物、订单与结果均不对应真实交易。",
  });
}

const steps = [];
for (const c of cases) {
  const base = [
    [1,"INTAKE","PSP_SUPPORT","接收争议通知，记录金额、理由、截止时间与资金状态","案件主键与截止时间已建立"],
    [2,"CLASSIFY",c.responsible_team,"核对持卡人主张、交易事实与理由族，识别是否选错理由","理由族已确认或转人工"],
    [3,"COLLECT",c.responsible_team,"按清单向商户/内部团队补证，并标记来源、时间和矛盾","证据存在性与缺失项已登记"],
    [4,"REVIEW","RISK","检查证据相关性、真实性、格式、页数、金额和时限","形成接受/申诉/升级建议"],
    [5,"DECIDE",c.responsible_team,c.chargeback_outcome.includes("LOST")?"建议接受或先补关键证据，避免无效抗辩":"人工确认后决定是否提交申诉","保留人工决定与理由"],
    [6,"PACKAGE","PSP_SUPPORT","按事实时间线打包，去除敏感信息，不把无关材料堆入证据包","证据包可读、可追溯、格式合规"],
    [7,"OUTCOME","FINANCE",`记录拒付结果=${c.chargeback_outcome}；裁决结果=${c.adjudication_outcome}，并核对临时贷记/退款/再扣款`,`结果层级与资金状态分开落库`],
  ];
  for (const row of base) steps.push({case_id:c.case_id, step_no:row[0], phase:row[1], owner:row[2], action:row[3], output:row[4], deadline_rule:row[0]===1?"以实际通知为准；示例不声明统一时限":"继承案件截止时间", escalation:row[0]===4?c.manual_review_reason:""});
}

const evidenceRows = [];
for (const c of cases) {
  const req = reasonPolicy[c.reason_code].required;
  for (const code of req) {
    const present = c.present_evidence.includes(code);
    evidenceRows.push({case_id:c.case_id,evidence_code:code,evidence_name:evidenceMeta[code][0],required:"YES",available:present?"YES":"NO_OR_NOT_DISCLOSED",source:present?(c.synthetic?"SYNTHETIC_MERCHANT_SYSTEM":"PUBLIC_DECISION_SUMMARY"):"NOT_DISCLOSED",quality:present?(c.synthetic?"SIMULATED":"PUBLIC_SUMMARY"):"UNKNOWN",critical:[E.threeds,E.pod,E.description,E.refund,E.cancellation,E.duplicate,E.receipt].includes(code)?"YES":"CONTEXTUAL",why:evidenceMeta[code][1],missing_impact:present?"":"可能降低可抗辩性或触发人工复核",contradiction:c.special_tags.includes("CONTRADICT")?"与其他风险信号冲突":"",privacy:"仅记录类型与是否存在，不存原值"});
  }
}

const caseHeaders = ["case_id","title","authenticity","evidence_level","synthetic","industry","item_type","jurisdiction","amount","currency","card_network","original_reason_code","reason_code","cardholder_claim","merchant_claim","core_conflict","dispute_stage","chargeback_outcome","adjudication_outcome","outcome_scope","result_summary","redo_action","special_tags","responsible_team","manual_review_reason","oceanpilot_can_handle","product_gap","recommendation","source_id","rule_basis","import_outcome","notes"];
const stepHeaders = ["case_id","step_no","phase","owner","action","output","deadline_rule","escalation"];
const evidenceHeaders = ["case_id","evidence_code","evidence_name","required","available","source","quality","critical","why","missing_impact","contradiction","privacy"];
const sourceHeaders = ["source_id","title","institution","url","publication_date","accessed_date","authenticity","scope_notes"];

function csvEscape(v){ if(v===null||v===undefined)return ""; const s=String(v); return /[\",\n]/.test(s)?`"${s.replaceAll('"','""')}"`:s; }
function toCsv(headers, rows){ return "\uFEFF"+[headers.join(","),...rows.map(r=>headers.map(h=>csvEscape(r[h])).join(","))].join("\n")+"\n"; }
function col(n){let s=""; while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;}
function matrix(headers, rows){ return [headers,...rows.map(r=>headers.map(h=>r[h]??""))]; }
function styleDataSheet(sheet, headers, rowCount, widths, tableName){
  const end=col(headers.length); sheet.showGridLines=false; sheet.freezePanes.freezeRows(1); sheet.freezePanes.freezeColumns(2);
  const used=sheet.getRange(`A1:${end}${rowCount+1}`); used.format.font={name:"Aptos",size:10,color:"#172033"}; used.format.verticalAlignment="top";
  const head=sheet.getRange(`A1:${end}1`); head.format={fill:"#153E75",font:{bold:true,color:"#FFFFFF",size:10},wrapText:true,verticalAlignment:"center"}; head.format.rowHeight=34;
  sheet.getRange(`A2:${end}${rowCount+1}`).format.wrapText=true; sheet.getRange(`A2:${end}${rowCount+1}`).format.rowHeight=66;
  sheet.tables.add(`A1:${end}${rowCount+1}`,true,tableName).style="TableStyleMedium2";
  widths.forEach((w,i)=>sheet.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=w);
}

await fs.mkdir(outDir,{recursive:true});
await fs.writeFile(path.join(outDir,"cases.csv"),toCsv(caseHeaders,cases));
await fs.writeFile(path.join(outDir,"case_steps.csv"),toCsv(stepHeaders,steps));
await fs.writeFile(path.join(outDir,"evidence_items.csv"),toCsv(evidenceHeaders,evidenceRows));
const sourceRows=sources.map(s=>({source_id:s[0],title:s[1],institution:s[2],url:s[3],publication_date:"NOT_DISCLOSED",accessed_date:accessed,authenticity:s[4],scope_notes:s[5]}));
await fs.writeFile(path.join(outDir,"sources.csv"),toCsv(sourceHeaders,sourceRows));
const imports=cases.filter(c=>c.synthetic).map(c=>({case_ref:c.case_id,reason_code:c.reason_code,present_evidence:c.present_evidence,outcome:c.import_outcome,synthetic:true,notes:`${c.title}；${c.special_tags}；模拟预期，不代表真实胜诉率。`}));
await fs.writeFile(path.join(outDir,"synthetic_case_samples.import.json"),JSON.stringify(imports,null,2)+"\n");

const wb=Workbook.create();
const guide=wb.worksheets.add("使用说明"); const master=wb.worksheets.add("案例总表"); const flow=wb.worksheets.add("处理流程"); const ev=wb.worksheets.add("证据明细"); const src=wb.worksheets.add("来源登记"); const enums=wb.worksheets.add("枚举映射"); const dash=wb.worksheets.add("覆盖看板");
guide.showGridLines=false; guide.getRange("A1:H1").merge(); guide.getRange("A1").values=[["OceanPilot 公开拒付案例库 v1"]]; guide.getRange("A1:H1").format={fill:"#0B3B60",font:{bold:true,color:"#FFFFFF",size:20},verticalAlignment:"center"}; guide.getRange("A1:H1").format.rowHeight=44;
const guideRows=[
 ["定位","用于产品完善、离线测试、导师讨论和演示，不是Oceanpayment生产规则库。"],
 ["真实性","PUBLIC_FINAL_DECISION=公开匿名最终决定；OFFICIAL_RULE_EXAMPLE=官方规则/示例；RULE_DERIVED_SYNTHETIC=规则推演合成。"],
 ["结果口径","chargeback_outcome记录拒付链路结果；adjudication_outcome记录申诉专员等外部裁决。两者不得混写。"],
 ["未知字段","公开来源未披露的卡组织、理由码、金额或日期保持UNKNOWN/NOT_DISCLOSED，禁止猜测。"],
 ["合成案例","所有SYN案例synthetic=true，结果均为模拟预期；不得用于计算或宣传真实胜诉率。"],
 ["隐私红线","不存姓名、卡号、地址、真实订单号、IP/设备指纹原值、密钥或内部链接；只存证据类别与是否存在。"],
 ["使用顺序","先在案例总表筛选理由/行业/特殊标签，再查看处理流程与证据明细，最后把产品缺口转为规则或测试。"],
 ["反馈建议","同事可对reason_code、责任团队、关键证据、流程步骤和结果解释逐项标注：正确/需修改/不适用。"],
];
guide.getRange("A3:B10").values=guideRows; guide.getRange("A3:A10").format={fill:"#DCEAF7",font:{bold:true,color:"#153E75"}}; guide.getRange("A3:B10").format.wrapText=true; guide.getRange("A3:B10").format.rowHeight=48; guide.getRange("A:A").format.columnWidth=18; guide.getRange("B:B").format.columnWidth=88; guide.getRange("A12:H12").merge(); guide.getRange("A12").values=[["来源均以链接和摘要保留；使用前需由Oceanpayment业务专家确认适用版本、收单链路和内部SOP。"]]; guide.getRange("A12:H12").format={fill:"#FFF4CE",font:{bold:true,color:"#7A4E00"},wrapText:true}; guide.getRange("A12:H12").format.rowHeight=38;

master.getRange(`A1:${col(caseHeaders.length)}${cases.length+1}`).values=matrix(caseHeaders,cases); styleDataSheet(master,caseHeaders,cases.length,[13,24,22,16,10,14,16,16,12,10,14,20,23,34,34,36,20,22,22,22,40,36,26,22,26,18,34,34,18,34,16,30],"CasesTable"); master.getRange(`I2:I${cases.length+1}`).format.numberFormat="#,#0.00";
flow.getRange(`A1:${col(stepHeaders.length)}${steps.length+1}`).values=matrix(stepHeaders,steps); styleDataSheet(flow,stepHeaders,steps.length,[13,9,16,22,50,38,28,28],"StepsTable"); flow.getRange(`B2:B${steps.length+1}`).format.numberFormat="0";
ev.getRange(`A1:${col(evidenceHeaders.length)}${evidenceRows.length+1}`).values=matrix(evidenceHeaders,evidenceRows); styleDataSheet(ev,evidenceHeaders,evidenceRows.length,[13,28,18,12,20,25,18,14,34,32,28,30],"EvidenceTable");
src.getRange(`A1:${col(sourceHeaders.length)}${sourceRows.length+1}`).values=matrix(sourceHeaders,sourceRows); styleDataSheet(src,sourceHeaders,sourceRows.length,[20,36,28,100,18,16,24,44],"SourcesTable"); src.getRange(`D2:D${sourceRows.length+1}`).format.font={name:"Aptos",size:9,color:"#172033"};

const enumRows=[["category","enum_value","中文说明"],
 ...Object.keys(reasonPolicy).map(x=>["reason_code",x,{FRAUD_CARD_NOT_PRESENT:"无卡欺诈",PRODUCT_NOT_RECEIVED:"未收到",PRODUCT_NOT_AS_DESCRIBED:"与描述不符",DUPLICATE_PROCESSING:"重复扣款",CREDIT_NOT_PROCESSED:"退款未入账",SUBSCRIPTION_CANCELED:"取消后扣款",AUTHORIZATION_ERROR:"授权错误"}[x]]),
 ...Object.entries(evidenceMeta).map(([k,v])=>["evidence_code",k,v[0]]),
 ...["BUSINESS","TECHNICAL_SUPPORT","RISK","FINANCE","CUSTOMER_SUPPORT","PSP_SUPPORT"].map(x=>["responsible_team",x,x]),
 ...["INTAKE","CLASSIFY","COLLECT","REVIEW","DECIDE","PACKAGE","OUTCOME"].map(x=>["phase",x,x]),
 ...["PUBLIC_FINAL_DECISION","OFFICIAL_RULE_EXAMPLE","RULE_DERIVED_SYNTHETIC"].map(x=>["authenticity",x,x]),
 ...["MERCHANT_PREVAILED","DISCONTINUED","NOT_RAISED","NOT_PURSUED","EXPECTED_WON","EXPECTED_LOST","EXPECTED_PENDING"].map(x=>["chargeback_outcome",x,x])];
enums.getRange(`A1:C${enumRows.length}`).values=enumRows; styleDataSheet(enums,["category","enum_value","中文说明"],enumRows.length-1,[24,34,34],"EnumsTable"); enums.getRange(`A2:C${enumRows.length}`).format.rowHeight=26;

dash.showGridLines=false; dash.getRange("A1:L1").merge(); dash.getRange("A1").values=[["覆盖看板｜36个案例的结构与测试覆盖"]]; dash.getRange("A1:L1").format={fill:"#0B3B60",font:{bold:true,color:"#FFFFFF",size:18}}; dash.getRange("A1:L1").format.rowHeight=42;
dash.getRange("A3:B6").values=[["指标","数量"],["案例总数",null],["公开最终决定",null],["规则推演合成",null]]; dash.getRange("B4").formulas=[["=COUNTA('案例总表'!$A$2:$A$37)"]]; dash.getRange("B5").formulas=[["=COUNTIF('案例总表'!$C$2:$C$37,\"PUBLIC_FINAL_DECISION\")"]]; dash.getRange("B6").formulas=[["=COUNTIF('案例总表'!$C$2:$C$37,\"RULE_DERIVED_SYNTHETIC\")"]];
dash.getRange("D3:E10").values=[["理由族","案例数"],...Object.keys(reasonPolicy).map(r=>[r,null])]; for(let i=4;i<=10;i++) dash.getRange(`E${i}`).formulas=[[`=COUNTIF('案例总表'!$M$2:$M$37,D${i})`]];
dash.getRange("G3:H9").values=[["责任团队","案例数"],...["BUSINESS","TECHNICAL_SUPPORT","RISK","FINANCE","CUSTOMER_SUPPORT","PSP_SUPPORT"].map(t=>[t,null])]; for(let i=4;i<=9;i++) dash.getRange(`H${i}`).formulas=[[`=COUNTIF('案例总表'!$X$2:$X$37,G${i})`]];
for(const rg of ["A3:B6","D3:E10","G3:H9"]){dash.getRange(rg).format={borders:{preset:"all",style:"thin",color:"#C9D6E2"}}; dash.getRange(rg.split(":")[0].replace(/\d+$/,"3")+":"+rg.split(":")[1].replace(/\d+$/,"3")).format={fill:"#153E75",font:{bold:true,color:"#FFFFFF"}};}
dash.getRange("A3:H10").format.rowHeight=26; dash.getRange("A:A").format.columnWidth=24; dash.getRange("B:B").format.columnWidth=12; dash.getRange("D:D").format.columnWidth=30; dash.getRange("E:E").format.columnWidth=12; dash.getRange("G:G").format.columnWidth=24; dash.getRange("H:H").format.columnWidth=12;
const chart=dash.charts.add("bar",dash.getRange("D3:E10")); chart.title="7类理由族案例覆盖"; chart.hasLegend=false; chart.setPosition("A13","H30"); chart.xAxis={axisType:"textAxis",textStyle:{fontSize:9}}; chart.yAxis={numberFormatCode:"0"};
dash.getRange("J3:L8").values=[["验收项","目标","当前"],["总案例",36,null],["公开案例",12,null],["合成案例",24,null],["每类至少",3,null],["证据码覆盖",15,null]]; dash.getRange("L4").formulas=[["=B4"]];dash.getRange("L5").formulas=[["=B5"]];dash.getRange("L6").formulas=[["=B6"]];dash.getRange("L7").formulas=[["=MIN(E4:E10)"]];dash.getRange("L8").formulas=[["=COUNTA('枚举映射'!$B$9:$B$23)"]]; dash.getRange("J3:L8").format={borders:{preset:"all",style:"thin",color:"#C9D6E2"}}; dash.getRange("J3:L3").format={fill:"#153E75",font:{bold:true,color:"#FFFFFF"}}; dash.getRange("J:J").format.columnWidth=18; dash.getRange("K:L").format.columnWidth=12;

wb.comments.setSelf({displayName:"zhuzelin"}); wb.comments.addThread({cell:guide.getRange("B4")},"结果层级拆分是本案例库最重要的数据质量控制：FOS支持消费者，不必然等于卡组织拒付胜诉。");
const previews=path.join("/tmp","oceanpilot-chargeback-case-library-v1-qa"); await fs.mkdir(previews,{recursive:true});
for(const [name,range,file] of [["使用说明","A1:H13","使用说明"],["案例总表","A1:H8","案例总表"],["案例总表","M1:AF7","案例总表-详情"],["处理流程","A1:H10","处理流程"],["证据明细","A1:L9","证据明细"],["来源登记","A1:H9","来源登记"],["枚举映射","A1:C20","枚举映射"],["覆盖看板","A1:L30","覆盖看板"]]){const p=await wb.render({sheetName:name,range,scale:1.1,format:"png"});await fs.writeFile(path.join(previews,`${file}.png`),new Uint8Array(await p.arrayBuffer()));}
const check=await wb.inspect({kind:"table",range:"覆盖看板!A1:L10",include:"values,formulas",tableMaxRows:12,tableMaxCols:12}); await fs.writeFile(path.join(previews,"dashboard-inspect.ndjson"),check.ndjson);
const errors=await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",options:{useRegex:true,maxResults:300},summary:"final formula error scan"}); await fs.writeFile(path.join(previews,"formula-errors.ndjson"),errors.ndjson);
const xlsx=await SpreadsheetFile.exportXlsx(wb); await xlsx.save(path.join(outDir,"OceanPilot_拒付案例库_v1.xlsx"));

const readme=`# OceanPilot 公开拒付案例库 v1\n\n本目录包含 12 个公开最终决定案例和 24 个规则推演合成案例。主文件为 \`OceanPilot_拒付案例库_v1.xlsx\`。\n\n## 怎么用\n\n1. 在“案例总表”按理由族、行业或特殊标签筛选。\n2. 到“处理流程”查看每一步责任人、产出和升级条件。\n3. 到“证据明细”查看已有/缺失证据和缺失影响。\n4. 把 recommendation/product_gap 转为产品规则、回归测试或导师确认问题。\n\n## 文件\n\n- \`cases.csv\`：一案一行。\n- \`case_steps.csv\`：一案多步骤。\n- \`evidence_items.csv\`：一案多证据。\n- \`sources.csv\`：来源和适用范围。\n- \`synthetic_case_samples.import.json\`：仅 24 个合成案例，可用项目校验器导入。\n\n## 重要边界\n\n公开案例是对公开文书的事实摘要；FOS裁决通常评价金融机构是否公平处理，不等同卡组织仲裁结果。合成案例结果均为“模拟预期”，不代表Oceanpayment真实规则或胜诉率。本库不含PII、真实订单号、IP/设备指纹原值或任何凭据。\n\n## 校验\n\n\`oceanpilot-validate-data --case-samples outputs/oceanpilot-chargeback-case-library-v1/synthetic_case_samples.import.json\`\n`;
await fs.writeFile(path.join(outDir,"README.md"),readme);
console.log(JSON.stringify({outDir,cases:cases.length,public:cases.filter(c=>!c.synthetic).length,synthetic:imports.length,steps:steps.length,evidence:evidenceRows.length,sources:sourceRows.length}));
