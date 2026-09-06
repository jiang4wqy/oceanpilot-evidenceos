"""Formal-dispute premise for legacy case-creation HTTP entry points."""

import re

from oceanpilot.application.workspace_ports import WorkspaceError
from oceanpilot.domain.security import assert_no_sensitive_data

_NEGATED_DISPUTE = re.compile(
    r"(?:尚未|还未|未|没有)(?:进入|启动|发起|发生|产生)(?:正式)?(?:拒付|争议)"
    r"|(?:尚无|暂无|没有|并非|不是|不属于)(?:正式)?(?:拒付|争议)"
    r"|未收到(?:任何)?(?:拒付通知|争议通知)"
    r"|\b(?:no|not|without)\s+(?:a\s+|any\s+|formal\s+)*(?:chargeback|dispute)\b",
    re.IGNORECASE,
)
_DISPUTE_CONTEXT = re.compile(r"拒付|正式争议|\b(?:chargeback|dispute)\b", re.IGNORECASE)


def require_formal_dispute(description: str, declared: bool | None) -> bool:
    """Accept an explicit premise or an unambiguous legacy dispute description.

    Product non-delivery, a payment error or failed 3DS challenge alone does not
    establish a formal dispute. New clients should send the explicit assertion.
    """
    assert_no_sensitive_data({"description": description})
    if declared is False or _NEGATED_DISPUTE.search(description):
        raise WorkspaceError(
            "FORMAL_DISPUTE_REQUIRED",
            "当前说明未确认正式争议前提；普通支付失败或3DS失败不能直接作为拒付建案。",
            422,
        )
    if declared is True or _DISPUTE_CONTEXT.search(description):
        return True
    raise WorkspaceError(
        "FORMAL_DISPUTE_REQUIRED",
        "请明确确认这是已进入正式争议流程的合成案件，并提供 formal_dispute=true。",
        422,
    )
