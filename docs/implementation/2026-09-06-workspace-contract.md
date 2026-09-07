# 双端可信复核闭环：实现合同与验收账本

基线：`63dc456`（已合并重构 PR #56）。工作分支：`feat/dual-workspace-review-loop`。
依据：2026-09-06 用户提供的实施计划及 Agent Mail message/9 设计指南。
近期主线：同案补证 → 人工登记复核 → 同版复核摘要。全部使用合成数据。

## 页面与角色

`/demo` 为材料提交方，`/business` 为企业争议运营方，二者同源且读取同一案件。
`/admin` 保留原运维入口。请求声明 `X-Demo-Role: MERCHANT|BUSINESS` 和
`X-Demo-Actor`，后端据角色限制操作。页面必须说明这是演示身份，不是生产身份认证。
普通支付/3DS失败不能直接作为正式争议：建案需明确确认合成正式争议前提。

## 共用接口

前缀 `/api/v1/workspace`：

- `GET /cases` → `{cases:[CaseView]}`。
- `GET /cases/{id}` → `CaseView`。
- `POST /commands` → `{status,receipt,case}`。
- `GET /commands/{command_id}` → 已保存结果，或 `{status:"UNKNOWN"}`。
- `POST /cases/{id}/summaries`（业务端，`{expected_revision}`）→ 摘要元数据。
- `GET /summaries/{id}?format=html|json` → 不可变的已保存摘要。

命令：`{command_id,action,case_id?,expected_revision?,data:{...},confirmed:true}`。
创建以外操作必须指定案件版本。命令编号在两次尝试间不变；主动新建副本使用新编号。
同编号异内容返回冲突。同编号同内容回放同一业务回执。
变更、版本、审计和命令回执在同一 Chargeback 数据库事务中提交。
超时先查询命令结果，UNKNOWN 只表示无已提交命令记录，不能假定在途操作已终止。

| action | data | 允许角色 |
| --- | --- | --- |
| CREATE_CASE | title,description,card_network,formal_dispute:true | 双端 |
| COPY_SAMPLE | sample:A/B/C | 双端 |
| CONFIRM_REASON | reason_code（可省略） | 双端 |
| SET_NETWORK | card_network | 双端 |
| REGISTER_MATERIAL | evidence_code,file_name,source | 双端 |
| WITHDRAW_MATERIAL | evidence_code | 双端 |
| FINALIZE | 空对象 | 双端 |
| REVIEW | decision,summary,scope,expected_rule_fingerprint | 业务端 |
| ADD_CONCERN | kind,field,original_value,proposed_value,original_source,proposed_source,summary | 双端 |
| RESOLVE_CONCERN | concern_id,resolution,summary | 业务端 |

source 为 SYNTHETIC_TEMPLATE、SYNTHETIC_USER_METADATA 或 UNKNOWN。
decision 为 APPROVED、NEEDS_MORE_INFO 或 REJECTED；复核只确认登记清单及内部处理条件。
kind 为 FACT_CONFLICT、SOURCE_ISSUE 或 RULE_CONFLICT；记录来自人工或结构化字段，不是正文检测。
resolution 为 KEEP_ORIGINAL、ACCEPT_PROPOSED 或 ACKNOWLEDGE，必须记录解释。
来源 UNKNOWN 不能仅靠确认知悉解除：先撤回并明确来源重新登记，再复核疑点；旧来源与撤回历史保留，正文状态仍为 NOT_READ。任何有效 UNKNOWN 材料都独立阻断批准。
对 reason_code/card_network 的旧分歧，当前字段与 original_value 不再相同时，KEEP/ACCEPT 返回 CONCERN_STALE；ACKNOWLEDGE 可明确关闭旧疑点但不采纳旧建议，并记录 resolved_fact（处理前后值与处理前案件版本）。非法枚举建议值返回 422。
人工审核必须携带预览时的 expected_rule_fingerprint；规则变化返回 RULE_CHANGED，不能把旧预览批准套到新规则。

receipt：`command_id,case_id,revision,audit_event_id,applied_at,result`。
首次 status=APPLIED，同请求回放 status=REPLAYED，receipt 不变。

## CaseView 字段

- 基本：case_id,title,description,revision,phase,phase_label,missing_count,next_actor,
  created_at,updated_at,review_status,synthetic,scenario,formal_dispute,card_network,
  reason_code,reason_label,reason_confirmed。
- readiness：present,total,ratio,meaning（内部材料清单完成度）。
- materials：code,label,file_name,source,registered_at,registered_by,
  registered_revision,content_verification（NOT_READ）,active,withdrawn_at。
- missing：code,label,why,what_changes,critical。
- rule_reference：match_status,rule_version_id,scheme_reason_code,scheme,display_name,
  rule_version,source_document,source_section,source_url,verification_status,limitation。
- rule_fingerprint：当前规则快照的 opaque 指纹，只用于一致性校验，不作为对外业务字段显示。
- review：status,current_record,history,stale。记录含 decision_id,source_turn_id,status,
  summary,confirmed_materials,case_revision,confirmed_by,confirmed_at,audit_event_id,
  citation_ids,rule_fingerprint；history 保留旧版本或旧规则记录，不标当前通过。
  即使案件 revision 相同，缺少指纹的旧审核或规则失配审核也只作为历史。
- concerns：concern_id,kind,field,original_value,proposed_value,original_source,
  proposed_source,summary,reported_by,reported_at,case_revision,status,resolution,
  resolved_by,resolved_at,resolution_summary,resolved_fact（实际支持的事实字段处理快照，可为 null）。
- timeline：event_type,detail,case_revision,occurred_at,actor。
- gate：status,reason,can_review,can_package,requires_human。can_review 表示可批准登记复核；
  退回/驳回由 allowed_actions 中 REVIEW 控制，不要求材料齐全。
- next_action：label,reason,owner,required_materials,expected_state,approval_required。
- allowed_actions：后端允许的命令名称。
- runtime：mode,provider,model；latest_analysis 为同版本已保存 Agent 响应或 null。
  结果来源读取响应 output_source/failure_code，不能仅依据所配置供应商。
  保存分析含 rule_fingerprint；只有案件、卡组织及规则指纹均匹配才能回放或引用到摘要。缺失指纹的历史分析不冒充当前结果。
- summaries：summary_id,case_id,revision,generated_at,title,html_url,json_url。
- unverified_items：正文、真实性、一致性、规则正式适用性等未完成核验事项。

## 验收账本

R0–R6 已由独立重构 PR 完成基础工作；本阶段补齐 R1 中材料/角色/复核的公共合同。
以下状态区分代码/自动化证据与现场运行验收；自动化通过不代表浏览器或实时供应商验收通过。

| 需求 | 当前状态 | 所需证据 |
| --- | --- | --- |
| U1–U8 双端职责、列表、单案、材料、反馈、导航、审核、联调 | 接口与页面已实现；主线程已完成桌面双端 A 主链及 B/C；新增规则指纹后审核、中文HTML和规则往返最终复验已通过 | `tests/api/test_workspace_api.py`、`tests/web/test_page_runtime.py`；同案双端实际操作已记录，见验收记录步骤 3–5 |
| P01–P03 三场景规则、无匹配、事实口径 | 后端/脚本/文档及定向回归已覆盖；中文HTML新排版实际浏览器复验已通过 | `tests/agents/test_material_boundaries.py`、`test_case_copilot_stability.py`、`tests/api/test_chargeback_api.py` |
| P04–P06 分层闸门、冲突、当前审核与历史 | 定向后端回归已覆盖 | `tests/application/test_workspace_service.py`：关键/普通缺失、UNKNOWN不能ACK绕过、来源撤回重登记、同字段旧疑点CAS、旧规则审核历史化 |
| P07–P08 创建幂等、A/B/C样例 | 后端幂等/并发/恢复已有回归；主线程已演示真实后端 A/B/C 副本 | `tests/api/test_workspace_api.py`、`tests/application/test_workspace_service.py`、真实API transcript |
| P09–P10 同版HTML/JSON摘要 | 案件/规则/AI/审核指纹回归已覆盖；中文HTML新排版与预览指纹最终复验已通过 | 无模型调用、规则读取间隙变化、旧分析与旧审核排除、预览指纹、并发冲突、HTML转义/重启读取 |
| P11 后端默认禁发送 | 直接HTTP自动化已覆盖 | 503 MOCK_SEND_DISABLED；设开关仍501 MOCK_SEND_NOT_READY；模型/打包/连接器零调用 |
| P12–P13 模型来源与期限 | 离线与故障自动化已覆盖；主线程已完成一次真实 DeepSeek MODEL 与人工边界检查，以及注入延迟 provider 的页面超时降级验收（不代表 DeepSeek 真实故障） | `tests/model/test_deadline_provider.py`、供应商超时/429、Copilot JSON/非法动作/越界主张降级测试；实际计时与页面见验收记录步骤 9 |
| P14–P15 离线恢复、文档、完整彩排 | runbook与无网HTTP A/B/C已更新并运行；桌面 A/B/C 已演示，新增一致性修复后的最终审核、摘要、规则往返与重启恢复已验证 | `examples/chargeback_transcript.py`、`docs/demo.md`；依赖在场前准备，刷新与重启恢复已验证，见验收记录步骤 4、8、10 |

E1/E2 为 P0 完成后的增强择一；E3 为独立发送增强。L1–L8 需要相应业务、数据、
企业校准或生产化启动条件，保留在后续路线，不提前宣称已实施。
主线程已在本机完成一次真实 DeepSeek 合成调用，并记录 MODEL 来源及人审边界；这不表示真实业务准确率、真实数据或生产集成已经验证。此前“未发现凭据”的状态已由本次实际验证更新。

## 已记录证据与剩余验收

- 主线程桌面浏览器首次验收：A 样例缺口、材料登记、规则往返、业务复核、摘要下载；B 阻断与历史；C 跨场景；一次 DeepSeek 实时回答。截图在 [验收目录](../acceptance/2026-09-06/screenshots/)。
- `04-rule-return.png` 和 `07-summary-before-readability-fix.png` 分别是规则布局、HTML 可读性修复前的截图，不能用于证明新版排版已通过。
- 定向真实 SQLite/API 回归覆盖：规则在摘要视图读取间隙变化、审核预览后规则变化、审核期间变化回滚、同版但旧规则 AI/审核排除、UNKNOWN 不允许仅 ACK 绕过、来源重登记保留历史、同字段旧疑点不覆盖后来事实、合法 JSON 中越界正文/交易/胜率主张降级。
- 最终复验已完成：新版服务 A 案件、审核及摘要均为版本 10，规则绑定一致；中文 HTML 和规则往返截图已检查。全量 1429 passed、6 skipped，最终措辞后 41 项页面测试通过，详见[验收记录](../acceptance/2026-09-06/README.md)和工程报告。
- 未进行完整移动端或读屏验收，不将其标为已完成。
