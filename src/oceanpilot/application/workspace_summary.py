"""Readable, script-free HTML from an already frozen workspace snapshot."""

from html import escape
from typing import Any

LABELS = {
    "APPROVED": "登记复核通过",
    "NEEDS_MORE_INFO": "退回补充资料",
    "REJECTED": "驳回本次处理",
    "UNREVIEWED": "本版未复核",
    "MERCHANT": "材料提交方",
    "BUSINESS": "企业运营方",
    "SYNTHETIC_TEMPLATE": "合成演示模板",
    "SYNTHETIC_USER_METADATA": "操作人员登记的合成元数据",
    "UNKNOWN": "来源不明",
    "OPEN": "待处理",
    "RESOLVED": "已处理",
    "FACT_CONFLICT": "结构化事实分歧",
    "SOURCE_ISSUE": "来源问题",
    "RULE_CONFLICT": "规则适用疑点",
    "KEEP_ORIGINAL": "保留原登记",
    "ACCEPT_PROPOSED": "采纳建议值",
    "ACKNOWLEDGE": "记录人工处理说明",
    "MODEL": "实时模型输出",
    "DETERMINISTIC": "确定性规则输出",
    "FALLBACK": "模型异常后的降级输出",
    "EXACT_MATCH": "已匹配演示规则摘要",
    "NO_EXACT_MAPPING": "无精确匹配，仅有内部清单",
    "UNVERIFIED_SUMMARY": "尚未经企业专家核验的规则摘要",
}


def _text(value: Any) -> str:
    return escape(str(value if value is not None and value != "" else "未记录"), quote=True)


def _label(value: Any) -> str:
    return LABELS.get(str(value), str(value or "未记录"))


def _pairs(items) -> str:
    return (
        '<dl class="facts">'
        + "".join(
            f"<div><dt>{_text(key)}</dt><dd>{_text(value)}</dd></div>" for key, value in items
        )
        + "</dl>"
    )


def _list(items) -> str:
    values = list(items)
    return "<ul>" + "".join(f"<li>{_text(item)}</li>" for item in values) + "</ul>"


def _review(record: dict[str, Any]) -> str:
    return (
        '<article class="record">'
        + _pairs(
            [
                ("复核决定", _label(record.get("status"))),
                ("复核案件版本", record.get("case_revision")),
                ("演示复核人", record.get("confirmed_by")),
                ("确认时间（UTC）", record.get("confirmed_at")),
                ("决定编号", record.get("decision_id")),
                ("审计编号", record.get("audit_event_id")),
                ("复核范围", "、".join(record.get("confirmed_materials", []))),
                ("引用规则标识", "、".join(record.get("citation_ids", []))),
            ]
        )
        + '<p class="opinion">'
        + _text(record.get("summary"))
        + "</p></article>"
    )


def _materials(items) -> str:
    if not items:
        return '<p class="muted">尚无材料登记记录。</p>'
    rows = []
    for item in items:
        status = "已登记" if item["active"] else "已撤回"
        withdrawn = "<br>撤回时间：" + _text(item.get("withdrawn_at")) if not item["active"] else ""
        rows.append(
            '<tr><th scope="row">'
            + _text(item["label"])
            + "</th><td>"
            + _text(item["file_name"])
            + '<br><span class="muted">'
            + _text(_label(item["source"]))
            + "</span></td><td>"
            + _text(item["registered_by"])
            + "<br>版本 "
            + _text(item["registered_revision"])
            + "<br>"
            + _text(item["registered_at"])
            + "</td><td>"
            + status
            + "<br>正文未读取<br>内容未核验"
            + withdrawn
            + "</td></tr>"
        )
    return (
        '<div class="table-scroll"><table><caption>全部材料登记记录（时间均为 UTC）</caption>'
        '<thead><tr><th scope="col">材料项目</th><th scope="col">文件名与来源</th>'
        '<th scope="col">登记人、版本与时间</th><th scope="col">当前状态</th></tr></thead>'
        "<tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def render_summary(snapshot: dict[str, Any]) -> str:
    """Render only supplied values; no model, database, or network calls."""
    case = snapshot["case"]
    rule = case["rule_reference"]
    review = case["review"]
    current = review.get("current_record")
    next_action = case["next_action"]
    parts = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'; style-src 'unsafe-inline'\">",
        "<title>" + _text(snapshot["title"]) + "</title><style>",
        "*{box-sizing:border-box}body{margin:0;background:#f3f6f5;color:#243532;"
        "font:15px/1.65 system-ui,-apple-system,'PingFang SC','Microsoft YaHei',sans-serif}"
        "main{max-width:1060px;margin:32px auto;background:white;padding:40px 48px;"
        "border:1px solid #dbe5e1}h1{font-size:29px;line-height:1.3;margin:12px 0}"
        "h2{font-size:20px;border-top:1px solid #dbe5e1;padding-top:26px;margin:30px 0 14px}"
        "h3{font-size:16px;margin:20px 0 10px}.eyebrow{color:#39746c;font-weight:700;"
        "letter-spacing:.12em}.muted,dt,caption{color:#526862}.notice,.status{padding:16px 20px;"
        "background:#e9f4f0;border-left:4px solid #39746c}.notice{background:#fff8e7;"
        "border-color:#9b762b}.facts{display:grid;grid-template-columns:1fr 1fr;gap:12px 24px}"
        ".facts>div{min-width:0;padding-bottom:8px;border-bottom:1px solid #edf1ef}"
        "dt{font-size:12px}dd{margin:3px 0 0;overflow-wrap:anywhere}.table-scroll{overflow:auto}"
        "table{width:100%;border-collapse:collapse;font-size:13px}caption{text-align:left;"
        "padding:0 0 8px}th,td{border:1px solid #dbe5e1;padding:12px;text-align:left;"
        "vertical-align:top;overflow-wrap:anywhere}thead{background:#edf5f2}"
        "th:first-child{min-width:100px}td{max-width:300px}.record{padding:12px 18px;"
        "border:1px solid #dbe5e1;margin:12px 0}.opinion{white-space:pre-wrap}"
        "li{margin:7px 0;overflow-wrap:anywhere}p{overflow-wrap:anywhere}footer{margin-top:30px;"
        "font-size:13px;color:#526862}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
        "@media(max-width:700px){main{margin:0;padding:22px 18px}.facts{grid-template-columns:1fr}"
        "h1{font-size:24px}}@media print{body{background:white}main{margin:0;border:0;padding:0}"
        "h2,h3{break-after:avoid}tr,.record{break-inside:avoid}thead{display:table-header-group}}",
        '</style></head><body><main><header><div class="eyebrow">OCEANPILOT / SYNTHETIC</div>',
        "<h1>" + _text(snapshot["title"]) + "</h1>",
        '<p class="notice">仅登记合成材料元数据；正文未读取，真实性、内容一致性及正式规则适用性'
        "仍待核验。本文件不是官方可提交证据包。</p>",
        _pairs(
            [
                ("案件编号", snapshot["case_id"]),
                ("冻结案件版本", snapshot["revision"]),
                ("摘要编号", snapshot["summary_id"]),
                ("生成时间（UTC）", snapshot["generated_at"]),
                ("演示生成人", snapshot["generated_by"]),
                ("当前处理阶段", case["phase_label"]),
            ]
        ),
        "</header><section><h2>案件说明与已知信息</h2>",
        "<h3>"
        + _text(case["title"])
        + "</h3><p>建案时登记的说明："
        + _text(case["description"])
        + "</p>",
        _pairs(
            [
                ("卡组织", case.get("card_network")),
                ("争议原因", case.get("reason_label")),
                (
                    "流程前提",
                    "假定已进入正式争议流程（合成）" if case["formal_dispute"] else "尚未确认",
                ),
                (
                    "材料登记就绪度",
                    f"{case['readiness']['present']} / {case['readiness']['total']} 项",
                ),
            ]
        ),
        '<p class="status">' + _text(case["gate"]["reason"]) + "</p>",
        '<p class="muted">就绪度只表示内部登记清单完成度，不代表胜诉率或真实业务准确率。</p>',
        "</section><section><h2>材料登记清单</h2>",
        _materials(case["materials"]),
        "<h3>尚缺材料与补充目的</h3>",
        _list(
            item["label"]
            + ("（关键项）" if item["critical"] else "（普通项）")
            + "："
            + item["why"]
            + " 补充后："
            + item["what_changes"]
            for item in case["missing"]
        )
        if case["missing"]
        else "<p>当前登记清单无缺口；材料正文与真实性仍未核验。</p>",
        "</section><section><h2>规则版本与核验状态</h2>",
        _pairs(
            [
                ("匹配情况", _label(rule["match_status"])),
                ("规则名称", rule["display_name"]),
                (
                    "卡组织及原因码",
                    f"{rule.get('scheme') or '未确定'} / "
                    f"{rule.get('scheme_reason_code') or '无精确原因码'}",
                ),
                ("规则版本标识", rule["rule_version_id"]),
                ("资料版本", rule["rule_version"]),
                ("核验状态", _label(rule["verification_status"])),
                ("来源文档", rule["source_document"]),
                ("引用章节", rule["source_section"]),
                ("来源地址", rule["source_url"]),
            ]
        ),
        '<p class="notice">' + _text(rule["limitation"]) + "</p>",
        "</section><section><h2>当前版本人工复核</h2>",
        _review(current)
        if current
        else '<p class="status">本版未复核。旧版决定不代表当前版本通过。</p>',
        "<h3>历史人工审核</h3>",
    ]
    history = [item for item in review["history"] if not current or item != current]
    parts += [_review(item) for item in history] or ['<p class="muted">暂无其他历史复核决定。</p>']
    parts.append("</section><section><h2>人工记录的疑点与处理</h2>")
    for item in case["concerns"]:
        parts.append(
            '<article class="record">'
            + _pairs(
                [
                    ("疑点编号", item["concern_id"]),
                    ("类型与状态", _label(item["kind"]) + " / " + _label(item["status"])),
                    ("涉及字段", item["field"]),
                    (
                        "原登记值及来源",
                        str(item["original_value"]) + " / " + item["original_source"],
                    ),
                    ("建议值及来源", str(item["proposed_value"]) + " / " + item["proposed_source"]),
                    ("记录人", item["reported_by"]),
                    ("处理决定", _label(item.get("resolution"))),
                    ("处理人", item.get("resolved_by")),
                    ("处理时间（UTC）", item.get("resolved_at")),
                ]
            )
            + "<p>疑点说明："
            + _text(item["summary"])
            + "</p><p>处理说明："
            + _text(item.get("resolution_summary"))
            + "</p></article>"
        )
    if not case["concerns"]:
        parts.append("<p>尚无人为登记的疑点；这不等于已核验材料内容一致。</p>")
    parts += [
        "</section><section><h2>下一步与责任角色</h2>",
        _pairs(
            [
                ("建议动作", next_action["label"]),
                ("原因", next_action["reason"]),
                ("负责方", _label(next_action["owner"])),
                (
                    "需要补充",
                    "、".join(item["label"] for item in case["missing"]) or "暂无登记缺项",
                ),
                ("预期变化", next_action["expected_state"]),
                ("人工确认", "案件变更仍需操作人员确认"),
            ]
        ),
        '<p class="notice">最终发送未开放；不能据此执行真实提交。演示终点为人工复核与摘要。</p>',
        "</section><section><h2>尚未核验的事项</h2>",
        _list(case["unverified_items"]),
        "</section><section><h2>同版本已保存分析</h2>",
    ]
    analysis = case.get("latest_analysis")
    if analysis:
        parts += [
            _pairs(
                [
                    ("结果来源", _label(analysis.get("output_source"))),
                    ("案件版本", analysis.get("case_revision")),
                ]
            ),
            "<p>" + _text(analysis.get("assistant_message")) + "</p>",
        ]
    else:
        parts.append("<p>当前版本没有可引用的已保存 AI 分析；本摘要使用确定性快照。</p>")
    parts += [
        "</section><footer>"
        + _text(snapshot["notice"])
        + " 所有内容来自同一冻结快照；生成摘要未重新调用模型。"
        + "伴随 JSON 保留结构化字段及审计标识。</footer></main></body></html>"
    ]
    return "".join(parts)
