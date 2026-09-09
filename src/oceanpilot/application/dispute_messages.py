"""Chinese business gate explanations shared by the API and command executor."""

_REASONS = {
    "This action requires a different business role": ("此操作需要由相应岗位的负责人处理。"),
    "Rules cannot be replaced after submission or a terminal outcome": (
        "已提交上游或收到终局结果，不能直接替换规则。"
    ),
    "Closed business records require authorized reopening": (
        "案件已关闭；须由主管凭授权依据重开后处理。"
    ),
    "Current Contest authority must be confirmed before evidence, review or submission": (
        "请先确认本阶段仍有抗辩权利，并由商户确认抗辩决定。"
    ),
    "Unknown or conflicting rule requires Risk confirmation": (
        "规则未知或来源冲突，请风控人员先核对确认。"
    ),
    "An explicit source and confirmed deadline are required": (
        "请先提供来源依据并确认本阶段期限。"
    ),
    "Create the confirmed next stage before continuing": (
        "已收到下一阶段事项，请先登记确认的新阶段。"
    ),
    "This action is unavailable in the current business state": (
        "本案当前步骤尚不支持此操作，请先完成页面提示的前置事项。"
    ),
    "Financial reconciliation requires a verified terminal upstream outcome": (
        "请先核验上游终局结果，再完成资金核对。"
    ),
    "No open business task requires resolution": ("当前没有需要处置的未完成业务任务。"),
    "Risk must verify remaining response rights": ("剩余响应权利待确认，请风控人员先核验。"),
    "Active file content is insufficient or requires human verification": (
        "当前材料内容不足或存在待核验问题，请补充、替换或核对材料。"
    ),
    "Required evidence is missing or its file content needs review": (
        "必需材料尚未齐备，或材料内容仍需核对。"
    ),
    "Current evidence requires Risk review": ("当前版本材料尚未通过风控审核。"),
    "Evidence review and final approval require two different people": (
        "材料审核和最终审批须由不同人员完成。"
    ),
    "Supervisor must approve and freeze the package": (
        "请主管完成终审、隐私检查并确认冻结当前材料包。"
    ),
    "Confirmed external deadline has passed; verify remaining rights": (
        "已超过确认的上游期限，请先核验剩余权利。"
    ),
    "A confirmed next-stage event is required": ("尚无已确认的下一阶段事件，请先核对上游通知。"),
    "No response or rights review is pending": ("当前没有待处理的未响应或权利恢复事项。"),
    "Evidence reuse must be reviewed before this stage is submitted": (
        "旧材料的本阶段适用性须在提交前完成审核。"
    ),
    "Terminal outcomes require authorized reopening before correction": (
        "已有终局结果；更正前须由主管凭依据授权重开。"
    ),
}


def localize_gate(gate):
    reason = gate.get("blocked_reason")
    if reason in _REASONS:
        return gate | {"blocked_reason": _REASONS[reason]}
    if gate.get("code") == "CLOSE_BLOCKED":
        return gate | {"blocked_reason": "结案条件尚未齐备，请查看结果、资金、通知和未完成任务。"}
    return gate
