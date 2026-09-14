# 合成拒付接收契约（#69 / #70）

基线：222e754；分支 member-b/synthetic-intake-69-70。由 B 统一负责业务与网页，飞书 #71 文件未改。

POST /api/v2/intake/simulations/preview：正常会话与 CSRF，运营/主管/管理员且有目标商户权限。输入 case_template_id、merchant_id、scheme、reason_code、amount_minor、currency、received_at（带时区）。返回 input、reference、rule、materials（中文 label）、confirmation_token、production_eligible=false。仅 Visa 10.4、Visa 13.1、Mastercard 4853 具有现成合成规则；全库 62 条参考均可建独立演练案。只有范围匹配的可执行模板使用现成规则；其余返回 requires_rule_confirmation=true、空材料清单与待确认期限，不自动套用相同原因码的通用规则。

POST /api/v2/intake/simulations：输入 {input: 预览输入, confirmed: true, request_id: 唯一请求标识, confirmation_token: 预览返回值}。明确确认针对合成交易与合成规则，不是商户决定或材料审批。系统生成唯一交易/事件 ID，登记合成交易，通过现有 receive 建案，有匹配演练规则时再依次执行 CONFIRM_RULE 和 PUBLISH_TASK；否则保留待确认规则状态，由运营确认本案规则后发布任务。真实生产入口不变。

请求和确认快照存入独立 v21_simulations 表。相同 actor/request_id 只对应同一输入；业务命令 ID、版本及规则负载稳定。中途中断后重放原 POST 恢复，不能换 ID 自动再建案。业务冲突会保留并报错，不能跳过校验。

成功：simulation_status=READY，case_id，case（当前有权限的案件投影），原始 intake 事件/回执，notification_intent={kind:MERCHANT_TASK_AVAILABLE,case_id,revision,merchant_id,delivery_status:NOT_VERIFIED}。READY 只表示商户任务已在网页可见，不表示飞书已投递/商户已读。规则待确认返回 NEEDS_RULE_CONFIRMATION、case_id 和 notification_intent=null；尚未发布商户待办。接收未完成返回 NEEDS_ATTENTION 和事件原因。HTTP 409 是输入、预览或当前版本冲突；5xx/网络超时结果未知，重放原请求。

飞书 #71：请复用已存在 PUBLISH_TASK 的正常 on_change/通知通路，避免再发布业务任务。任务完成后的 case_id/revision 是卡片绑定依据；接受/抗辩仍调用原 MERCHANT_DECISION 命令并获得商户明确确认；投递持久化、幂等与状态由飞书适配负责人处理。notification_intent 只是交接描述，不替代可靠投递队列。新接口不调用飞书，也不承诺通知已发送。

模板 reference 仅作为来源，证据、决定、审批、评分和结果不导入。新案件证据为空、merchant_decision=NONE、business_outcome=UNKNOWN。时间来自确认的独立合成规则（72/96/120 小时），不声称为银行正式期限。

通知意图补充：id 为稳定的任务命令标识；revision 为该任务发布版本；active 根据当前案件是否仍待商户首次决定计算。重放不能重复投递；active=false 或当前业务状态已变化时，应刷新卡片/停止旧提醒，不再次催初始决定。
