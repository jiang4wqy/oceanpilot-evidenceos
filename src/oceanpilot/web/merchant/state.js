const BASE="/api/v1/chargeback";
const caseContext=createCaseContext();
const S={loc:window.oceanI18n.getLanguage(),currentView:"hub",packaged:false,appealed:false,caseCreating:false,evidenceSubmitting:false,evidenceSubmittingCases:new Set(),evidenceDraft:null,agentSubmitting:false,pendingAgentTurn:null,agentBoundCaseId:null,agentMessages:[],pendingReview:null,lastAgentInput:"",cardNetwork:"",expectedReason:null,
  scenarioIndex:0,autoEvidence:["transaction.receipt","fulfillment.tracking"],cases:[],
  rules:[],currentRuleId:null,ruleReturnContext:null,rulesRequestId:0,ruleDetailRequestId:0,
  auditByCase:new Map(),withdrawDraft:null,dialogTrigger:null};
// Compatibility names are read-only views, not independent mutable case copies.
Object.defineProperties(S, {
  caseId: {get: () => caseContext.caseId},
  caseRevision: {get: () => caseContext.snapshot ? caseContext.snapshot.revision : null},
  caseSnapshot: {get: () => caseContext.snapshot},
  selectedCase: {get: () => caseContext.snapshot},
  last: {get: () => caseContext.snapshot},
  agentCase: {get: () => S.agentBoundCaseId === S.caseId ? caseContext.snapshot : null},
});
function selectCase(caseId) {
  if (caseContext.select(caseId)) S.agentBoundCaseId=null;
}
function acceptCaseSnapshot(snapshot) {
  const previous=caseContext.snapshot;
  if (!caseContext.accept(snapshot)) return false;
  S.cardNetwork=snapshot.card_network||'';
  if(previous&&snapshot.revision!==previous.revision){
    invalidateDerivedViews();
    S.pendingReview=null;
    const proposal=$('agentReviewProposal');
    if(proposal)proposal.remove();
  }
  return true;
}
const SCENARIOS=[
  {label:"Visa 13.1 · 未收到货",meta:"已有 2 项 · 仍缺 3 项",network:"VISA",reason:"PRODUCT_NOT_RECEIVED",
    available:["transaction.receipt","fulfillment.tracking"],
    desc:"客户声称未收到商品；商户目前只有交易收据和物流轨迹，尚未取得签收证明、地址匹配及客服沟通。"},
  {label:"Visa 10.4 · 非本人交易",meta:"已有 1 项 · 仍缺 5 项",network:"VISA",reason:"FRAUD_CARD_NOT_PRESENT",available:["transaction.receipt"],
    desc:"持卡人声称这笔交易不是本人、属于盗刷；商户目前只有交易收据，缺少 3DS、AVS/CVV、设备/IP 和历史交易关联。"},
  {label:"Mastercard 4853 · 商品不符",meta:"已有 2 项 · 仍缺 3 项",network:"MASTERCARD",reason:"PRODUCT_NOT_AS_DESCRIBED",
    available:["transaction.receipt","product.description"],
    desc:"客户声称收到的商品与下单页面描述不符；商户目前只有交易收据和商品页面，缺少签收、沟通和政策材料。"},
];
const PHASE={NEEDS_INTAKE:["未建案","p-mut","创建案件"],REASON_PROPOSED:["待确认原因","p-warn","确认原因"],
  NEED_EVIDENCE:["补充材料","p-acc","补充材料"],ASSESSED:["评估完成","p-good","评估结果"]};
const REASON_LABEL={FRAUD_CARD_NOT_PRESENT:"非本人交易",PRODUCT_NOT_RECEIVED:"未收到商品",
  PRODUCT_NOT_AS_DESCRIBED:"商品或服务与描述不符",DUPLICATE_PROCESSING:"重复扣款",
  CREDIT_NOT_PROCESSED:"退款未入账",SUBSCRIPTION_CANCELED:"订阅取消后仍扣款",AUTHORIZATION_ERROR:"授权异常"};
const TEAM_LABEL={RISK:"风控团队",CUSTOMER_SUPPORT:"客服团队",BUSINESS:"业务团队",
  TECHNICAL_SUPPORT:"技术支持",FINANCE:"财务团队",PSP_SUPPORT:"支付支持"};
const AGENT_LABEL={IntakeAgent:"案件识别",EvidenceAgent:"材料校验",AssessAgent:"规则评估",HumanGate:"人工确认"};
const SOURCE_LABEL={MODEL:"辅助说明",FALLBACK:"规则说明",HEURISTIC:"规则识别"};
const EVENT_LABEL={CASE_OPENED:"案件创建",REASON_CLASSIFIED:"争议原因识别",REASON_CONFIRMED:"争议原因确认",
  EVIDENCE_ADDED:"材料已补充",EVIDENCE_WITHDRAWN:"材料已撤回",COLLECTION_FINALIZED:"材料收集结束"};
const RISK_LABEL={LOW:"低风险",MEDIUM:"中风险",HIGH:"高风险"};
const FACTOR_LABEL={NO_3DS:"未完成 3DS",AVS_MISMATCH:"AVS 地址不匹配",CVV_MISMATCH:"CVV 不匹配",
  DEVICE_IP_MISMATCH:"设备与 IP 异常",HIGH_TICKET:"高额交易",HIGH_RISK_MCC:"高风险行业",
  CROSS_BORDER:"跨境交易",SHIPPING_BILLING_MISMATCH:"收货与账单地址不符",REPEAT_DISPUTER:"历史争议较多",DIGITAL_GOODS:"数字商品"};
const EVIDENCE_LABEL={"transaction.receipt":"交易收据","auth.avs_result":"AVS 验证结果","auth.cvv_result":"CVV 验证结果",
  "auth.threeds":"3DS 认证记录","auth.device_ip_match":"设备与 IP 关联","fulfillment.tracking":"物流跟踪号/轨迹",
  "fulfillment.proof_of_delivery":"签收证明","fulfillment.address_match":"收货地址匹配","product.description":"商品页面",
  "billing.refund_record":"退款记录","policy.terms_refund":"条款与退款政策","comms.customer":"客户沟通记录",
  "subscription.cancellation_record":"取消订阅记录","history.prior_transactions":"历史交易记录","billing.duplicate_check":"重复扣款核验"};
const $=(id)=>document.getElementById(id);
const esc=(s)=>String(s==null?"":s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tr=(s)=>window.oceanI18n.translate(s);
const cleanCopy=(s)=>String(s||"").replace(/（合成模型输出，仅用于离线演示）/g,"").trim();
const actionLabel=(s)=>cleanCopy(s).replace(/胜诉评估 ([0-9.]+)（数字由内核判定）/,"材料就绪度 $1（规则评估）");
const detailLabel=(s)=>REASON_LABEL[s]||EVIDENCE_LABEL[s]||s;
