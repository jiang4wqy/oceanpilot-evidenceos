"""Synthetic sample import bundles (illustrative; replace with company data).

These are valid, redacted, synthetic-only records demonstrating the T12 import
schema and exercising the loaders end to end until real data arrives. They must
never contain real PII.
"""

SYNTHETIC_REASON_CODE_MAPPINGS: tuple[dict[str, object], ...] = (
    {
        "card_network": "VISA",
        "network_reason_code": "13.1",
        "reason_code": "PRODUCT_NOT_RECEIVED",
        "notes": "合成映射：仅用于演示导入格式。",
    },
    {
        "card_network": "MASTERCARD",
        "network_reason_code": "4837",
        "reason_code": "FRAUD_CARD_NOT_PRESENT",
        "notes": "合成映射：请由公司专家确认实际口径。",
    },
)

SYNTHETIC_REASON_POLICIES: tuple[dict[str, object], ...] = (
    {
        "reason_code": "PRODUCT_NOT_RECEIVED",
        "responsible_team": "BUSINESS",
        "default_deadline_days": 15,
        "high_risk": False,
        "required": [
            {"evidence_code": "transaction.receipt", "weight": 2, "critical": True},
            {"evidence_code": "fulfillment.tracking", "weight": 3, "critical": True},
            {"evidence_code": "fulfillment.proof_of_delivery", "weight": 3},
        ],
    },
    {
        "reason_code": "FRAUD_CARD_NOT_PRESENT",
        "responsible_team": "RISK",
        "default_deadline_days": 10,
        "high_risk": True,
        "required": [
            {"evidence_code": "transaction.receipt", "weight": 2, "critical": True},
            {"evidence_code": "auth.threeds", "weight": 3, "critical": True},
            {"evidence_code": "auth.avs_result", "weight": 2},
        ],
    },
)

SYNTHETIC_BANK_RULES: tuple[dict[str, object], ...] = (
    {
        "reason_code": "PRODUCT_NOT_RECEIVED",
        "card_network": "VISA",
        "source": "bank",
        "bank_id": "ACME_BANK",
        "required_evidence": [
            "fulfillment.proof_of_delivery",
            "fulfillment.tracking",
            "transaction.receipt",
        ],
        "template_order": [
            "fulfillment.proof_of_delivery",
            "fulfillment.tracking",
            "transaction.receipt",
        ],
        "submission_window_days": 12,
        "notes": "ACME 要求签收证明列在最前（合成样例）。",
    },
    {
        "reason_code": "CREDIT_NOT_PROCESSED",
        "card_network": "VISA",
        "source": "network",
        "required_evidence": ["billing.refund_record", "transaction.receipt"],
        "template_order": ["billing.refund_record", "transaction.receipt"],
        "submission_window_days": 14,
        "notes": "VISA 通用：退款凭证优先（合成样例）。",
    },
)

SYNTHETIC_CASE_SAMPLES: tuple[dict[str, object], ...] = (
    {
        "case_ref": "SYN-CASE-0001",
        "reason_code": "PRODUCT_NOT_RECEIVED",
        "present_evidence": ["transaction.receipt", "fulfillment.tracking"],
        "outcome": "won",
        "synthetic": True,
        "notes": "合成案例：证据齐备，胜诉。",
    },
    {
        "case_ref": "SYN-CASE-0002",
        "reason_code": "FRAUD_CARD_NOT_PRESENT",
        "present_evidence": ["transaction.receipt"],
        "outcome": "lost",
        "synthetic": True,
        "notes": "合成案例：缺 3DS 关键证据，败诉。",
    },
)
