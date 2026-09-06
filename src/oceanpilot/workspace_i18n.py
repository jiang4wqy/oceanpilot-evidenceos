# ruff: noqa: E501

"""Reviewed display translations for the synthetic workspace (never translate input data)."""

TRANSLATIONS = dict(
    line.split(" | ", 1)
    for line in """
查看详情 | View details
来源与适用范围 | Source and applicability
文档 | Document
章节 | Section
生效日期 | Effective date
来源链接 | Source link
打开来源文档 | Open source document
限制与免责声明 | Limitations and disclaimer
未标定 | Unspecified
版本未标定 | Version unspecified
未核验 | Unverified
无 | None
未记录 | Not recorded
未提供 | Not provided
待核验 | Pending verification
关键材料 | Critical material
暂无待办 | No pending action
待确认处理方 | Owner to be confirmed
已驳回 | Rejected
待补充资料 | More materials required
旧版复核已失效 | Earlier review invalidated
历史记录 | History
只读查看 | Read only
内部处理门槛 | Internal processing criteria
材料登记清单 | Material register
原登记值 / 来源 | Original value / source
建议值 / 来源 | Proposed value / source
仍未完成的核验 | Outstanding verification
保留原登记 | Keep original value
采纳建议值 | Accept proposed value
确认已知悉并说明处理边界 | Acknowledge and explain handling limits
处理决定 | Resolution
确认记录处理决定 | Confirm resolution
已记录处理决定 | Resolution recorded
处理说明： | Resolution notes:
说明处理理由及仍需核验的事项 | Explain the resolution and outstanding verification
疑点来自人工登记或结构化元数据检查，不代表已读取文件正文。 | Concerns come from human entries or structured metadata checks, not document reading.
目前未登记冲突或来源疑点；这不等于已经验证材料内容一致。 | No conflicts or source issues are registered. Content consistency has not been verified.
未记录文件名 | File name not recorded
登记人未记录 | Registering actor not recorded
尚未登记材料 | No materials registered
卡组织待确认 | Card network unconfirmed
材料边界 | Material boundary
流程前提 | Process premise
已进入正式争议流程（合成） | Formal dispute already initiated (synthetic)
正式争议前提待确认 | Formal dispute premise unconfirmed
仅登记元数据 · 正文未读取 | Metadata only · Body not read
查看并处理下一步 | View and handle next step
查看当前材料登记状态 | View the current material register
先确认争议原因 | Confirm dispute reason first
确认争议原因后生成材料清单 | Confirm the dispute reason to generate the checklist
由后端校验处理条件 | Processing criteria validated by the server
等待人工确认 | Awaiting human confirmation
需要人工确认 | Human confirmation required
材料登记就绪度仅表示内部清单完成情况。 | Registration readiness measures internal checklist completion only.
没有精确匹配 | No exact match
版本待核验 | Version awaiting verification
章节待核验 | Section awaiting verification
仅为公开规则整理摘要，正式适用性需人工确认。 | Public-source summary only; formal applicability requires human confirmation.
规则库暂不可用 | Rule library unavailable
无法读取规则目录 | Unable to read the rule catalog
无法读取规则详情 | Unable to read rule details
请稍后重试；页面不会回退到伪造数据。 | Please retry later. No fabricated data is used.
没有使用缓存或伪造详情。 | No cached or fabricated details are used.
没有匹配规则 | No matching rules
请调整卡组织或搜索条件。 | Adjust the network or search terms.
选择当前列表中的规则 | Select a rule from the current list
筛选已更新；旧详情已清除，避免列表与来源错配。 | Filters updated. Previous details cleared to keep the list and source aligned.
规则数据库暂不可用。 | Rule database unavailable.
该规则版本不存在。 | This rule version does not exist.
旧详情已清除。 | Previous details cleared.
内部 Demo 窗口 | Internal demo window
卡组织打包证据摘要 | Network evidence summary
所需断言 | Required assertions
来源追溯 | Provenance
当前案件 | Current case
新建合成争议 | Create synthetic dispute
可重复演示的合成案件 | Repeatable synthetic cases
规则整理原型 | Curated rules prototype
合成演示 | Synthetic demo
登记已记录 | Registration recorded
完成并返回案件 | Done; return to case
材料登记已保存 | Material registration saved
下载 HTML | Download HTML
下载 JSON | Download JSON
正在从当前版本生成确定性复核摘要… | Generating a deterministic summary of this revision…
正在读取已冻结摘要… | Loading the frozen summary…
案件版本已变化，请刷新案件后重新生成。 | Case revision changed. Refresh the case and generate again.
摘要生成结果尚未确认，请刷新本案查看已保存摘要，再决定是否重试。 | Summary outcome unconfirmed. Refresh the saved summaries before retrying.
摘要版本与本次请求不一致，请刷新案件后重新生成。 | Summary revision does not match the request. Refresh and generate again.
摘要读取失败，请重试下载。 | Summary could not be read. Retry the download.
本次尚无对话 | No conversation yet
查看并登记所需材料 | View and register required material
当前没有精确匹配的规则引用。 | No exact rule citation for this case.
规则引用与核验边界 | Rule citations and verification limits
查看引用规则 | View cited rule
查看执行记录（不展示思维链） | View execution log (no chain of thought)
涉及状态变更的意见，请到对应分区查看范围并明确确认。 | Review the scope and explicitly confirm changes in the corresponding section.
未返回说明 | No explanation returned
已保存结果回放 | Saved result replay
已有一条输入等待分析，请稍后再发送。 | One message is already queued. Please wait before sending another.
输入已排队，将在当前分析结束后处理。 | Message queued for processing after the current analysis.
正在读取当前案件版本并生成说明… | Reading the current case revision and generating an explanation…
本轮说明未完成，可重试分析；本操作不批准或提交案件。 | Explanation incomplete. Retry analysis; this action does not approve or submit the case.
重试分析 | Retry analysis
服务端案件版本已变化，请刷新本案后重新分析。 | The server revision changed. Refresh this case and analyze again.
请至少输入 3 个字符。 | Enter at least 3 characters.
为什么这个案件仍然被阻断？ | Why is this case still blocked?
目前缺什么，补充后会改变什么？ | What is missing and what changes after registration?
案件列表暂不可用。 | Case list unavailable.
重试读取 | Retry loading
暂无匹配案件 | No matching cases
可调整筛选，或从演示样例创建一个新副本。 | Adjust the filters or create a new demo sample copy.
打开演示样例 | Open demo samples
案件工作台 | Case workspace
合成争议案件 | Synthetic dispute case
案件暂时无法读取，请返回列表重试。 | This case is unavailable. Return to the list and retry.
本案刷新失败，仍显示上次读取的版本；请重试。 | Refresh failed. The last loaded revision remains visible; please retry.
请明确确认：这是已进入正式争议流程的合成案件。 | Confirm that this synthetic case has entered the formal dispute process.
请填写案件名称及至少 10 个字符的合成案件说明。 | Enter a case name and a synthetic description of at least 10 characters.
请填写涉及字段及疑点说明。 | Enter the field and concern notes.
请填写原来源及建议来源。 | Enter both the original and proposed sources.
请填写疑点处理说明，再确认记录处理决定。 | Enter resolution notes before confirming the resolution.
请填写至少 3 个字符的复核意见。 | Enter review notes of at least 3 characters.
尚未读取当前规则依据，请刷新本案后再预览复核。 | Current rule basis unavailable. Refresh the case before previewing the review.
当前版本仍有阻断项，不能批准登记复核。可退回补充或驳回。 | This revision is blocked and cannot be approved. Request more materials or reject it.
案件版本或规则依据已变化，请重新预览本版本复核范围。 | Case revision or rule basis changed. Preview the current review scope again.
请先选择合成文件名或使用 Synthetic 演示文件。 | Select a synthetic file name or use the synthetic demo file.
尚未取得已保存回执。可关闭弹窗，在页面顶部查询本次处理结果。 | No saved receipt yet. Close this dialog and check the outcome at the top of the page.
尚未取得已保存回执，请关闭弹窗后查询本次处理结果。 | No saved receipt yet. Close this dialog and check the operation outcome.
暂时无法查询原回执。请保持同一命令编号，恢复连接后再次查询。 | Receipt lookup unavailable. Keep the same command ID and check again after reconnecting.
后端已拒绝本次请求且未查到已提交回执。输入已保留，请检查当前版本及填写内容后重新确认。 | The server rejected this request and no committed receipt was found. Input retained; check the revision and input before confirming again.
请求超时，处理结果尚未确认。 | Request timed out; outcome unconfirmed.
请求未完成，处理结果尚未确认。 | Request incomplete; outcome unconfirmed.
请填写演示操作者，再确认本次操作。 | Enter the demo actor before confirming.
请按当前案件材料要求补充登记。 | Register the material required by this case.
后端重新计算本案材料登记缺口。 | The server recalculates this case's registration gaps.
系统记录 | System record
尚无处理记录 | No processing history
原因已确认 | Reason confirmed
原因识别 | Reason classified
材料已登记 | Material registered
材料登记已撤回 | Material registration withdrawn
材料收集结束 | Material collection finalized
卡组织已更新 | Card network updated
登记复核已记录 | Register review recorded
登记复核已确认 | Register review confirmed
疑点已登记 | Concern recorded
疑点已处理 | Concern resolved
原文记录（保留录入语言） | Original record (language as entered)
原语言回复；切换语言后可重新分析当前版本。 | Original-language response; analyze the current revision for a response in your selected language.
运行维护中心未启动 | Operations center is not running
当前服务运行维护 | Current service operations
补齐此关键登记项；其他缺口与疑点仍需处理，正文仍待核验。 | Complete this critical registration; other gaps and concerns remain, and document bodies still need verification.
提高材料清单就绪度；内容仍待核验。 | Improve registration readiness; content remains unverified.
需要人工确认案件原因。 | A human must confirm the dispute reason.
存在未解决的人工登记疑点或来源不明材料，暂停自动推进。 | Unresolved registered concerns or unknown sources block progress.
关键材料缺失，不能进入正式评估。 | Critical materials are missing; formal assessment is blocked.
普通材料仍有缺口，仅允许有限分析。 | Noncritical materials are missing; only limited analysis is allowed.
当前版本材料登记复核已通过；正文与正式规则适用性仍未核验。 | This revision's register review is approved; document bodies and formal rule applicability remain unverified.
内部登记清单齐全，等待业务人员复核当前版本。 | The internal register is complete; business review of this revision is pending.
内部材料登记清单完成度；不代表胜诉率、真实性或正文核验。 | Internal registration checklist completion; not an outcome estimate or verification of authenticity or document bodies.
无精确匹配，仅使用内部材料清单 | No exact match; internal checklist only
未匹配到当前卡组织及原因的具体规则；内部演示清单不能作为正式依据。 | No exact rule for this network and reason; the internal demo checklist is not formal grounds.
补充材料 | Register missing materials
复核疑点 | Review concerns
生成复核摘要 | Generate review summary
复核当前登记清单 | Review the current register
更新登记状态并使旧审核失效 | Update registrations and invalidate earlier approval
留下当前版本人工复核记录或摘要 | Save a human review or summary for this revision
真实文件正文未读取；仅登记合成材料元数据。 | Real document bodies have not been read; only synthetic metadata is registered.
材料真实性及跨材料内容一致性尚未核验。 | Authenticity and consistency across materials remain unverified.
卡组织规则的地区、时效及正式适用性尚待企业专家复核。 | Rule region, effective period, and formal applicability await expert review.
材料就绪度仅表示内部清单完成度，不代表胜诉率或业务准确率。 | Readiness measures internal checklist completion only, not outcome probability or business accuracy.
需要操作人员明确确认。 | Explicit operator confirmation is required.
此操作需要业务复核演示角色。 | This action requires the business review demo role.
该材料已登记，请查看当前案件。 | This material is already registered; check the current case.
请选择实际争议原因。 | Select the actual dispute reason.
疑点已变化，请刷新案件。 | The concern changed; refresh the case.
不支持此操作。 | Unsupported action.
请选择卡组织后再确认。 | Select a card network before confirming.
输入超过允许长度，请缩短后重试。 | Input exceeds the allowed length. Shorten it and retry.
""".strip().splitlines()
)

TRANSLATIONS.update(
    dict(
        line.split(" | ", 1)
        for line in """
3DS 认证技术背景 | 3DS authentication context
American Express 规则演示摘要；地区、版本、适用条件及正式期限尚未核验。 | American Express demo summary; region, version, applicability, and official deadlines are unverified.
与描述不符 / 商品或服务有缺陷 | Not as described / defective goods or services
争议交易发生时仍存在有效循环扣款授权 | Recurring payment authorization was valid at the time of the disputed transaction
争议交易收据 | Disputed transaction receipt
交付或签收记录 | Delivery or receipt record
交付至约定地点并与争议交易关联 | Delivery to the agreed location linked to the disputed transaction
仅用于解释 3DS 接入与材料留存语境；不参与卡组织争议资格、责任转移或期限判定。 | Technical context for 3DS integration and retention only; it does not determine dispute eligibility, liability shift, or deadlines.
供人工核对交易标识、金额、时间与商户信息；登记不表示真实性已核验。 | For human review of transaction ID, amount, time, and merchant. Registration does not verify authenticity.
供人工核对取消和扣费的时间顺序；登记不代表已判断扣费是否合理。 | For human review of cancellation and charging chronology. Registration does not determine whether a charge was justified.
供人工核对妥投时间、地点与签收信息；登记不代表已核实送达。 | For human review of delivery time, location, and receipt. Registration does not confirm delivery.
供人工核对当时展示的版本与接受记录；登记不代表条款已生效或被接受。 | For human review of the terms version and acceptance record. Registration does not establish acceptance or validity.
供人工核对既往交易关联；登记不代表历史记录真实或争议主张已被排除。 | For human review of prior transaction links. Registration does not verify records or disprove the dispute.
供人工核对校验结果；仅保留结果码，不能据此认定本人交易。 | For human review of verification result codes only; these do not establish cardholder participation.
供人工核对设备与网络关联；登记不代表匹配结果或本人交易已获确认。 | For human review of device and network links. Registration does not confirm a match or cardholder participation.
供人工核对返回码及其含义；登记不代表地址确已匹配。 | For human review of response codes and their meaning. Registration does not confirm an address match.
供人工核对退款标识、金额与状态；登记不代表退款已完成或已入账。 | For human review of refund ID, amount, and status. Registration does not confirm completion or crediting.
供人工梳理双方陈述与处理经过；登记不代表陈述已获得核实。 | For human review of statements and handling history. Registration does not verify those statements.
供人工比对下单页面与争议描述；登记不代表实际商品已核验。 | For human comparison of the order page and dispute. Registration does not verify the actual goods.
供人工比对授权与流水标识；登记不代表已排除重复扣款。 | For human comparison of authorization and transaction IDs. Registration does not rule out duplicate charging.
供人工比对订单、物流与账单地址；登记不代表地址匹配或送达已获确认。 | For human comparison of order, shipping, and billing addresses. Registration does not confirm a match or delivery.
保留 Synthetic 3DS 认证结果作为案件技术上下文 | Retain synthetic 3DS results as technical case context
历史无争议交易满足适用的关联条件 | Prior undisputed transactions meet the applicable linking conditions
历史无争议交易记录 | Prior undisputed transaction records
原始交易收据 | Original transaction receipt
取消发生在政策截止时间之后或不符合条款 | Cancellation was after the policy deadline or outside the terms
取消政策与披露记录 | Cancellation policy and disclosure record
取消时间与状态记录 | Cancellation time and status
取消确认或客户沟通 | Cancellation confirmation or customer correspondence
取消请求时间与状态 | Cancellation request time and status
合成演示配置；适用地区、消息系统、阶段及正式期限仍需生产规则确认，15 天仅为原型内部准备窗口。 | Synthetic demo configuration. Region, messaging system, stage, and official deadlines require rule verification; 15 days is only the prototype's internal preparation window.
商品 / 服务已取消 | Goods / services cancelled
商品 / 服务已退回或拒收 | Goods / services returned or refused
商品 / 服务未收到 | Goods / services not received
商品交付或服务使用记录 | Goods delivery or service usage record
商品或服务已经交付 | Goods or services were delivered
商品或服务描述 | Goods or services description
商品或服务符合交易时的描述或合同 | Goods or services match the description or contract at purchase
商品未实际退回或退回不符合披露政策 | Goods were not returned or the return did not comply with the disclosed policy
商户指南演示摘要；15 天为本原型内部准备窗口，不是 Visa 官方申诉期限。 | Merchant guide demo summary; 15 days is the prototype's internal preparation window, not Visa's official response deadline.
商户指南演示摘要；不自动判定 CE3.0、3DS 责任转移或正式申诉资格，15 天仅为原型内部准备窗口。 | Merchant guide demo summary; no automatic determination of CE3.0, 3DS liability shift, or formal eligibility. 15 days is only an internal preparation window.
商户指南演示摘要；适用地区、流程、责任转移与正式期限须以有效规则复核。 | Merchant guide demo summary; verify region, process, liability shift, and official deadlines against applicable rules.
商户材料逐项回应持卡人的具体主张 | Merchant materials address each specific cardholder claim
在约定日期前交付或可供取用 | Delivered or made available before the agreed date
实际交付内容符合购买时的描述或合同 | Delivery matches the description or contract at purchase
属于本合成内部清单的关键项，供人工核对认证记录；不据此认定责任转移或举证资格。 | Critical in this synthetic internal checklist, for human review of authentication. It does not establish liability shift or evidence eligibility.
属于本合成内部清单的关键项，供人工追查运输过程；登记不代表实际发货或送达。 | Critical in this synthetic internal checklist, for human review of shipping. Registration does not establish dispatch or delivery.
履约、维修、替换或交付记录能够对应争议交易 | Fulfilment, repair, replacement, or delivery records link to the disputed transaction
已取消的循环交易 | Cancelled recurring transaction
循环扣款与取消条款 | Recurring payment and cancellation terms
持卡人争议 — 商品 / 服务与描述不符 | Cardholder dispute — goods / services not as described
持卡人参与交易或从交易中受益 | The cardholder participated in or benefited from the transaction
条款、退换货或退款政策 | Terms, returns, exchanges, or refund policy
物流跟踪号与轨迹 | Tracking number and shipping history
相似交易对应独立订单或独立服务 | Similar transactions relate to separate orders or services
签收或妥投证明 | Signed receipt or proof of delivery
订单、发票或服务关联记录 | Order, invoice, or linked service records
订阅取消记录 | Subscription cancellation record
认证、设备或网络信息能够关联争议交易 | Authentication, device, or network information links to the disputed transaction
设备或 IP 关联 | Device or IP link
购买时的商品或服务描述 | Goods or services description at purchase
退款已按约定发起或完成 | Refund initiated or completed as agreed
退款未处理 | Refund not processed
退款沟通记录 | Refund correspondence
退款流水、ARN 或退款回执 | Refund transaction, ARN, or receipt
退款记录（如适用） | Refund record (if applicable)
退货与退款政策 | Returns and refund policy
重复处理 / 其他方式付款 | Duplicate processing / paid by other means
非本人交易（无卡环境） | Unauthorized transaction (card absent)
操作已记录 | Operation recorded
命令 | Command
审计 | Audit
来源 | Source
登记版本 | Registration revision
冻结版本 | Frozen revision
登记清单 | Registration checklist
预期变化： | Expected change:
需要 | Required owner:
待确认： | To confirm:
摘要已保存 | Summary saved
撤回于 | Withdrawn at
内部映射 | Internal mapping
降级原因 | Fallback reason
演示占位，仅元数据 | Demo placeholder, metadata only
项 | items
未收到货 | Goods not received
""".strip().splitlines()
    )
)

TRANSLATIONS.update(
    dict(
        line.split(" | ", 1)
        for line in """
无卡欺诈（未授权交易） | Card-not-present fraud
已取消订阅仍被扣费 | Subscription canceled
授权错误 | Authorization error
输入格式不符合要求，请检查必填项及长度。 | Invalid input. Check required fields and length limits.
内部材料登记清单已齐备；所有合成案件仍需人工复核，AI 不会自动判定通过。 | The internal material register is complete. All synthetic cases still require human review; AI does not automatically approve them.
当前版本的内部材料登记审核已由操作人员确认通过；正文内容与真实性仍待另行核验。 | An operator approved this revision's register review. Document content and authenticity still require separate verification.
内部材料审核已由操作人员确认驳回，案件保留审核决定与审计记录。 | An operator rejected the register review. The decision and audit record are retained.
材料登记门槛已经满足，下一步仍需按案件流程执行人工确认。 | Registration criteria are met; the next step still requires human confirmation under the case workflow.
接收案件上下文问题 | Receive the case-context question
已绑定现有案件，未创建重复案件 | Bound to the existing case; no duplicate case created
读取当前案件确定性快照 | Read the current deterministic case snapshot
理解问题并生成案件说明 | Interpret the question and generate a case explanation
实时模型说明受固定 JSON 合同和案件快照约束 | Live explanation constrained by the JSON contract and case snapshot
当前说明来自确定性案件规则 | Explanation from deterministic case rules
模型请求未能提供可用说明，已降级为确定性案件规则 | No usable model explanation; deterministic case rules used as fallback
等待操作人员确认推荐动作 | Await operator confirmation of the recommended action
Agent 不会直接改变案件或执行资金动作 | The Agent does not directly change the case or execute financial actions
3DS 文档仅解释认证结果留存的技术语境，不参与责任转移、资格或期限判断。 | 3DS documentation provides technical retention context only; it does not determine liability shift, eligibility, or deadlines.
该规则仅为未核验摘要，不代表正式适用依据或材料内容已获验证。 | This is an unverified rule summary, not formal grounds or verification of material contents.
已匹配当前案件的合成规则摘要；规则版本、适用范围和材料内容仍待人工核验。 | A synthetic rule summary matches this case; version, applicability, and material content still require human verification.
未登记操作 | Operation not recorded
创建案件 | Create case
新建样例副本 | Create sample copy
更新卡组织 | Update card network
收集结束 | Finalize collection
登记复核 | Register review
登记疑点 | Record concern
处理疑点 | Resolve concern
仅供展示 | Display only
演示已映射 | Demo mapped
未核验摘要 | Unverified summary
全球（需核验适用地区） | Global (region requires verification)
必需 | Required
推荐 | Recommended
已完成 | Completed
已阻断 | Blocked
信息 | Information
输入渠道 | Input channel
案件内核 | Case engine
模型辅助 | Model assistance
人工确认门槛 | Human confirmation gate
网络不可用，请重试查询。 | Network unavailable. Retry the lookup.
摘要编号 | Summary ID
案件编号 | Case ID
冻结案件版本 | Frozen case revision
生成时间（UTC） | Generated at (UTC)
演示生成人 | Demo author
当前处理阶段 | Current stage
案件说明与已知信息 | Case description and known facts
建案时登记的说明： | Description recorded at creation:
假定已进入正式争议流程（合成） | Assumed formal dispute (synthetic)
尚未确认 | Unconfirmed
材料登记就绪度 | Registration readiness
就绪度只表示内部登记清单完成度，不代表胜诉率或真实业务准确率。 | Readiness measures internal registration checklist completion only; it does not measure outcomes or business accuracy.
尚缺材料与补充目的 | Missing materials and registration purpose
（关键项） | (critical)
（普通项） | (noncritical)
当前登记清单无缺口；材料正文与真实性仍未核验。 | No registration gaps; document bodies and authenticity remain unverified.
规则版本与核验状态 | Rule version and verification status
匹配情况 | Match status
规则名称 | Rule name
卡组织及原因码 | Network and reason code
规则版本标识 | Rule version ID
资料版本 | Document version
核验状态 | Verification status
来源文档 | Source document
引用章节 | Cited section
来源地址 | Source URL
未确定 | Undetermined
无精确原因码 | No exact reason code
当前版本人工复核 | Current revision human review
本版未复核。旧版决定不代表当前版本通过。 | This revision has not been reviewed. Earlier decisions do not approve the current revision.
历史人工审核 | Human review history
暂无其他历史复核决定。 | No other historical review decisions.
人工记录的疑点与处理 | Human-recorded concerns and resolutions
疑点编号 | Concern ID
类型与状态 | Type and status
原登记值及来源 | Original value and source
建议值及来源 | Proposed value and source
记录人 | Reported by
处理人 | Resolved by
处理时间（UTC） | Resolved at (UTC)
疑点说明： | Concern notes:
尚无人为登记的疑点；这不等于已核验材料内容一致。 | No human-recorded concerns; this does not establish content consistency.
下一步与责任角色 | Next step and responsible role
建议动作 | Recommended action
原因 | Reason
负责方 | Owner
需要补充 | Missing registrations
暂无登记缺项 | No registration gaps
预期变化 | Expected change
人工确认 | Human confirmation
案件变更仍需操作人员确认 | Case changes still require operator confirmation
最终发送未开放；不能据此执行真实提交。演示终点为人工复核与摘要。 | Final submission is disabled. This cannot execute a real submission; the demo ends with human review and summary export.
尚未核验的事项 | Outstanding verification
同版本已保存分析 | Saved analysis of the same revision
结果来源 | Output source
当前版本没有可引用的已保存 AI 分析；本摘要使用确定性快照。 | No saved AI analysis for this revision; this summary uses a deterministic snapshot.
所有内容来自同一冻结快照；生成摘要未重新调用模型。 | All content comes from one frozen snapshot; export did not call the model again.
伴随 JSON 保留结构化字段及审计标识。 | Accompanying JSON retains structured fields and audit IDs.
材料登记与人工复核摘要；不是官方可提交证据包。假定已进入正式争议流程。 | Registration and human review summary, not an official submission package. A formal dispute is assumed.
仅登记合成材料元数据；正文未读取，真实性、内容一致性及正式规则适用性仍待核验。本文件不是官方可提交证据包。 | Only synthetic metadata is registered. Document bodies remain unread; authenticity, consistency, and formal rule applicability are unverified. This is not an official submission package.
尚无材料登记记录。 | No material registration records.
全部材料登记记录（时间均为 UTC） | All material registration records (times in UTC)
材料项目 | Material item
文件名与来源 | File name and source
登记人、版本与时间 | Actor, revision, and time
当前状态 | Current status
已撤回 | Withdrawn
撤回时间： | Withdrawn at:
内容未核验 | Content unverified
复核决定 | Review decision
复核案件版本 | Reviewed case revision
演示复核人 | Demo reviewer
确认时间（UTC） | Confirmed at (UTC)
决定编号 | Decision ID
审计编号 | Audit ID
复核范围 | Review scope
引用规则标识 | Cited rule IDs
来源不明 | Unknown source
已处理 | Resolved
结构化事实分歧 | Structured fact conflict
规则适用疑点 | Rule applicability concern
记录人工处理说明 | Record human resolution notes
已匹配演示规则摘要 | Demo rule summary matched
无精确匹配，仅有内部清单 | No exact match; internal checklist only
尚未经企业专家核验的规则摘要 | Rule summary not verified by enterprise experts
""".strip().splitlines()
    )
)

TRANSLATIONS.update({"已登记": "Registered"})

TRANSLATIONS.update(
    dict(
        line.split(" | ", 1)
        for line in """
A · Visa 10.4 主案例 | A · Visa 10.4 main scenario
B · 撤回关键材料后阻断 | B · Blocked after critical material withdrawal
C · Visa 13.1 跨场景 | C · Visa 13.1 cross-scenario check
合成正式争议：持卡人提出 Visa 10.4 无卡未授权交易争议。假定已进入正式争议流程，金额 USD 120。初始预置时保留 3DS 登记缺口。 | Synthetic formal dispute: a cardholder alleges a Visa 10.4 unauthorized card-absent transaction. Formal dispute proceedings are assumed, for USD 120. The initial template leaves 3DS registration missing.
合成正式争议：初始样例曾完成材料登记复核，之后撤回关键 3DS 材料。初始状态的旧审核仅作为历史，后续状态以当前登记和复核记录为准。 | Synthetic formal dispute: the initial register review was completed before critical 3DS material was withdrawn. That approval is historical; subsequent status follows the current register and review records.
合成正式争议：持卡人提出 Visa 13.1 商品未收到争议。假定已进入正式争议流程，初始预置缺签收证明。 | Synthetic formal dispute: a cardholder alleges goods not received under Visa 13.1. Formal proceedings are assumed; the initial template lacks proof-of-delivery registration.
当前案件版本 | Current case revision
新选择与当前记录不同，须业务人员明确复核。 | The new selection differs from the current record and requires explicit business review.
提交方未说明材料来源，暂停推进。 | The registering party did not specify a source; progress is paused.
待人工说明来源 | Awaiting human source clarification
合成样例：已复核登记清单；正文未读取。 | Synthetic sample: register reviewed; document bodies unread.
提交卡组织选择 | Submit network selection
更换已登记卡组织会形成待复核分歧；企业确认处理决定前仍使用原选择。 | Changing an existing network records a concern; the original selection remains until the business operator confirms a resolution.
系统记录与原文意见 | System entries and original notes
""".strip().splitlines()
    )
)

TRANSLATIONS.update({"补充后：": "After registration: "})

TRANSLATIONS.update(
    dict(
        line.split(" | ", 1)
        for line in """
规则读取期间变化，请刷新案件。 | Rules changed while loading; refresh the case.
请先确认这是已进入正式争议流程的合成案件。 | First confirm that this synthetic case is in formal dispute proceedings.
已明确确认并执行合成案件操作。 | Synthetic case operation explicitly confirmed and performed.
该材料来源仍不明。请先撤回并说明来源后重新登记，再由业务人员复核此疑点。 | This material's source is still unknown. Withdraw it, register it with a clarified source, then request business review of the concern.
该字段已在其他处理后变化；旧对照不能用于保留或采纳。可明确知悉并关闭旧疑点，或按当前事实重新登记分歧。 | This field changed after another action. The old comparison cannot retain or replace its value. Acknowledge and close the old concern, or register a new comparison of the current facts.
当前事实已变化，仅关闭旧疑点，不采纳旧建议。 | Current facts changed; close the old concern without adopting its old proposal.
建议值不属于允许的原因或卡组织，请重新登记。 | The proposed value is not an allowed reason or network. Register a corrected concern.
请先读取当前规则并预览本版本复核范围。 | Load the current rule and preview this revision's review scope first.
规则在预览后变化，请刷新并重新确认复核范围。 | Rules changed after preview. Refresh and confirm the review scope again.
规则在预览后变化，请重新确认本次复核范围。 | Rules changed after preview. Confirm the review scope again.
规则在复核期间变化，请刷新后重新确认。 | Rules changed during review. Refresh and confirm again.
请由业务人员生成复核摘要。 | A business operator must generate the review summary.
规则在生成期间变化，请重新生成摘要。 | Rules changed during generation. Generate the summary again.
演示操作人名称不合法。 | Invalid demo actor name.
此写操作要求业务复核演示角色。 | This write requires the business review demo role.
操作字段不符合当前命令合同，请检查输入。 | Operation fields do not meet the current command contract. Check the input.
该材料已登记，请先查看当前记录。 | This material is already registered. Check the current record first.
此字段只能记录人工复核结论，不能自动改写。 | This field supports a human resolution record only; it cannot be automatically overwritten.
该疑点不存在或已经复核，请刷新案件。 | The concern is missing or already reviewed. Refresh the case.
命令回执属于另一个演示身份。 | This receipt belongs to another demo identity.
命令编号已用于其他内容或身份，请核对原回执。 | This command ID was used for different content or an identity. Check the original receipt.
""".strip().splitlines()
    )
)

TRANSLATIONS.update(
    {
        "合成模板随界面语言显示；人工录入内容保留原文。": "Synthetic templates follow the interface language; human entries retain their original wording."
    }
)
