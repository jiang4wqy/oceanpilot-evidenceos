"""Build the deterministic two-page OceanPilot opening-report attachment."""

from __future__ import annotations

import html
import pathlib

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT_PDF = ROOT / "artifacts" / "OceanPilot-开题报告补充材料.pdf"
FONT_REGULAR = "OceanPilot-MSYH"
FONT_BOLD = "OceanPilot-MSYH-Bold"
FONT_REGULAR_PATH = pathlib.Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD_PATH = pathlib.Path(r"C:\Windows\Fonts\msyhbd.ttc")

NAVY = HexColor("#0B1F3A")
OCEAN_BLUE = HexColor("#1677FF")
TEAL = HexColor("#00A68A")
LIGHT_CYAN = HexColor("#EAF7FF")
AMBER = HexColor("#F5A000")
NEUTRAL_GRAY = HexColor("#667085")
PALE_BORDER = HexColor("#D9E2EC")
PAGE_BACKGROUND = HexColor("#FBFDFF")


def register_fonts() -> tuple[str, str]:
    """Register the verified Microsoft YaHei fonts and return their names."""
    missing = [path for path in (FONT_REGULAR_PATH, FONT_BOLD_PATH) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Required font not found: {missing[0]}")

    registered = set(pdfmetrics.getRegisteredFontNames())
    if FONT_REGULAR not in registered:
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(FONT_REGULAR_PATH), subfontIndex=0))
    if FONT_BOLD not in registered:
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_BOLD_PATH), subfontIndex=0))
    return FONT_REGULAR, FONT_BOLD


def draw_paragraph(
    canvas,
    text: str,
    x: float,
    y_top: float,
    width: float,
    height: float,
    style,
) -> float:
    """Draw a paragraph from its top edge and return the resulting bottom y."""
    paragraph = Paragraph(text, style)
    required_width, required_height = paragraph.wrap(width, height)
    if required_width > width + 0.01 or required_height > height + 0.01:
        raise ValueError(
            f"Paragraph does not fit: required {required_width:.2f} x "
            f"{required_height:.2f}, available {width:.2f} x {height:.2f}"
        )
    y_bottom = y_top - required_height
    paragraph.drawOn(canvas, x, y_bottom)
    return y_bottom


def draw_card(
    canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    body: str,
    *,
    accent,
) -> None:
    """Draw a compact evidence or status card."""
    canvas.saveState()
    canvas.setFillColor(white)
    canvas.setStrokeColor(PALE_BORDER)
    canvas.setLineWidth(0.8)
    canvas.roundRect(x, y, width, height, 7, fill=1, stroke=1)
    canvas.setStrokeColor(accent)
    canvas.setLineWidth(3.2)
    canvas.line(x + 8, y + height - 2.5, x + width - 8, y + height - 2.5)
    canvas.restoreState()

    title_style = ParagraphStyle(
        "card-title",
        fontName=FONT_BOLD,
        fontSize=11.5,
        leading=14.5,
        textColor=NAVY,
        alignment=TA_LEFT,
        wordWrap="CJK",
        spaceAfter=0,
    )
    body_style = ParagraphStyle(
        "card-body",
        fontName=FONT_REGULAR,
        fontSize=10.5,
        leading=13.2,
        textColor=NEUTRAL_GRAY,
        alignment=TA_LEFT,
        wordWrap="CJK",
        spaceAfter=0,
    )
    inner_x = x + 9
    inner_width = width - 18
    title_bottom = draw_paragraph(
        canvas,
        html.escape(title),
        inner_x,
        y + height - 10,
        inner_width,
        30,
        title_style,
    )
    body_top = title_bottom - 4
    draw_paragraph(
        canvas,
        html.escape(body),
        inner_x,
        body_top,
        inner_width,
        body_top - y - 8,
        body_style,
    )


def _draw_page_frame(canvas, page_width: float, page_height: float, margin: float) -> None:
    canvas.setFillColor(PAGE_BACKGROUND)
    canvas.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    canvas.setStrokeColor(OCEAN_BLUE)
    canvas.setLineWidth(2.4)
    canvas.line(margin, page_height - margin + 5, page_width - margin, page_height - margin + 5)


def _draw_chip(
    canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    accent,
) -> None:
    canvas.saveState()
    canvas.setFillColor(LIGHT_CYAN if accent != AMBER else HexColor("#FFF7E6"))
    canvas.setStrokeColor(accent)
    canvas.setLineWidth(0.9)
    canvas.roundRect(x, y, width, height, height / 2, fill=1, stroke=1)
    canvas.restoreState()
    chip_style = ParagraphStyle(
        "chip",
        fontName=FONT_BOLD,
        fontSize=10.5,
        leading=12.5,
        textColor=NAVY,
        alignment=TA_CENTER,
        wordWrap="CJK",
    )
    draw_paragraph(
        canvas,
        html.escape(text),
        x + 6,
        y + (height + chip_style.leading) / 2,
        width - 12,
        chip_style.leading,
        chip_style,
    )


def _draw_roadmap_bar(
    canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
) -> None:
    canvas.saveState()
    canvas.setFillColor(LIGHT_CYAN)
    canvas.setStrokeColor(HexColor("#B7DFFF"))
    canvas.setLineWidth(0.8)
    canvas.roundRect(x, y, width, height, 6, fill=1, stroke=1)
    canvas.setFillColor(TEAL)
    canvas.roundRect(x, y, 6, height, 3, fill=1, stroke=0)
    canvas.restoreState()
    roadmap_style = ParagraphStyle(
        "roadmap",
        fontName=FONT_BOLD,
        fontSize=11.5,
        leading=14,
        textColor=NAVY,
        alignment=TA_CENTER,
        wordWrap="CJK",
    )
    draw_paragraph(
        canvas,
        html.escape(text),
        x + 12,
        y + (height + roadmap_style.leading) / 2,
        width - 24,
        roadmap_style.leading,
        roadmap_style,
    )


def _draw_arrow(
    canvas,
    x_start: float,
    y_start: float,
    x_end: float,
    y_end: float,
    *,
    color=OCEAN_BLUE,
) -> None:
    canvas.saveState()
    canvas.setStrokeColor(color)
    canvas.setFillColor(color)
    canvas.setLineWidth(1.8)
    canvas.line(x_start, y_start, x_end, y_end)
    if abs(x_end - x_start) >= abs(y_end - y_start):
        direction = 1 if x_end >= x_start else -1
        points = (
            (x_end, y_end),
            (x_end - direction * 7, y_end + 4),
            (x_end - direction * 7, y_end - 4),
        )
    else:
        direction = 1 if y_end >= y_start else -1
        points = (
            (x_end, y_end),
            (x_end + 4, y_end - direction * 7),
            (x_end - 4, y_end - direction * 7),
        )
    path = canvas.beginPath()
    path.moveTo(*points[0])
    path.lineTo(*points[1])
    path.lineTo(*points[2])
    path.close()
    canvas.drawPath(path, fill=1, stroke=0)
    canvas.restoreState()


def _draw_layer(
    canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    body: str,
    *,
    accent,
) -> None:
    canvas.saveState()
    canvas.setFillColor(white)
    canvas.setStrokeColor(accent)
    canvas.setLineWidth(1.2)
    canvas.roundRect(x, y, width, height, 7, fill=1, stroke=1)
    canvas.setFillColor(accent)
    canvas.roundRect(x, y, 7, height, 3, fill=1, stroke=0)
    canvas.restoreState()
    layer_style = ParagraphStyle(
        "layer",
        fontName=FONT_REGULAR,
        fontSize=11,
        leading=14,
        textColor=NAVY,
        alignment=TA_CENTER,
        wordWrap="CJK",
    )
    draw_paragraph(
        canvas,
        f"<b>{html.escape(title)}</b>　{html.escape(body)}",
        x + 14,
        y + (height + layer_style.leading) / 2,
        width - 28,
        layer_style.leading,
        layer_style,
    )


def build_pdf(output_path: pathlib.Path = OUTPUT_PDF) -> pathlib.Path:
    """Build and return the deterministic two-page PDF."""
    regular_font, bold_font = register_fonts()
    output_path = pathlib.Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    page_width, page_height = landscape(A4)
    margin = 11 * mm
    content_width = page_width - 2 * margin

    title_style = ParagraphStyle(
        "page-title",
        fontName=bold_font,
        fontSize=26,
        leading=31,
        textColor=NAVY,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    statement_style = ParagraphStyle(
        "statement",
        fontName=regular_font,
        fontSize=14,
        leading=20,
        textColor=NAVY,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    caption_style = ParagraphStyle(
        "caption",
        fontName=regular_font,
        fontSize=9.5,
        leading=12,
        textColor=NEUTRAL_GRAY,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    source_style = ParagraphStyle(
        "source",
        fontName=regular_font,
        fontSize=7.5,
        leading=9.2,
        textColor=NEUTRAL_GRAY,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    note_style = ParagraphStyle(
        "boundary-note",
        fontName=regular_font,
        fontSize=10.5,
        leading=14.2,
        textColor=NAVY,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    trial_style = ParagraphStyle(
        "trial-target",
        fontName=bold_font,
        fontSize=11,
        leading=14.5,
        textColor=NAVY,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    boundary_style = ParagraphStyle(
        "boundary-footer",
        fontName=regular_font,
        fontSize=9.5,
        leading=12,
        textColor=NEUTRAL_GRAY,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )

    pdf = pdfcanvas.Canvas(
        str(output_path),
        pagesize=(page_width, page_height),
        pageCompression=1,
        invariant=1,
    )
    pdf.setTitle("OceanPilot 开题报告补充材料")
    pdf.setAuthor("OceanPilot")
    pdf.setSubject("飞书未来人才计划开题报告补充材料")
    pdf.setCreator("OceanPilot deterministic ReportLab builder")

    # Page 1: market evidence and the evidence-loop thesis.
    _draw_page_frame(pdf, page_width, page_height, margin)
    title_bottom = draw_paragraph(
        pdf,
        html.escape("01｜为什么不是“再做一个 Agent”"),
        margin,
        page_height - margin,
        content_width,
        34,
        title_style,
    )
    draw_paragraph(
        pdf,
        html.escape(
            "OceanPilot 不抢着回答，而是先把一次跨境支付问题组织成可追溯案件："
            "缺证先补问，过门再判断，高风险动作由人工确认。"
        ),
        margin,
        title_bottom - 6,
        content_width,
        42,
        statement_style,
    )

    figure_1_width = 225 * mm
    flow_x = margin + 12
    flow_width = figure_1_width - 24
    node_width = 125
    node_height = 70
    node_gap = (flow_width - 3 * node_width) / 2
    row_1_y = 360
    row_2_y = 260
    row_3_y = 160
    flow_nodes = (
        ("1 问题建案", "群聊描述变成版本化案件", flow_x, row_1_y, TEAL),
        ("2 证据缺口", "readiness 决定下一补问", flow_x + node_width + node_gap, row_1_y, TEAL),
        (
            "3 角色化补问",
            "七步收集服务端选定证据",
            flow_x + 2 * (node_width + node_gap),
            row_1_y,
            TEAL,
        ),
        ("4 确定性诊断", "四规则 + 证据引用 + 置信度", flow_x, row_2_y, OCEAN_BLUE),
        (
            "5 责任建议",
            "团队、优先级与下一动作",
            flow_x + node_width + node_gap,
            row_2_y,
            OCEAN_BLUE,
        ),
        (
            "6 人工确认",
            "只写 approval audit，不执行业务",
            flow_x + 2 * (node_width + node_gap),
            row_2_y,
            AMBER,
        ),
        (
            "7 只读 Cockpit",
            "同一 persisted case 可回看",
            flow_x + node_width + node_gap,
            row_3_y,
            TEAL,
        ),
    )
    for title, body, x, y, accent in flow_nodes:
        draw_card(pdf, x, y, node_width, node_height, title, body, accent=accent)
    _draw_arrow(
        pdf,
        flow_x + node_width,
        row_1_y + node_height / 2,
        flow_x + node_width + node_gap - 7,
        row_1_y + node_height / 2,
    )
    _draw_arrow(
        pdf,
        flow_x + 2 * node_width + node_gap,
        row_1_y + node_height / 2,
        flow_x + 2 * (node_width + node_gap) - 7,
        row_1_y + node_height / 2,
    )
    _draw_arrow(
        pdf,
        flow_x + 2 * (node_width + node_gap) + node_width / 2,
        row_1_y - 7,
        flow_x + node_width / 2,
        row_2_y + node_height + 7,
    )
    _draw_arrow(
        pdf,
        flow_x + node_width,
        row_2_y + node_height / 2,
        flow_x + node_width + node_gap - 7,
        row_2_y + node_height / 2,
    )
    _draw_arrow(
        pdf,
        flow_x + 2 * node_width + node_gap,
        row_2_y + node_height / 2,
        flow_x + 2 * (node_width + node_gap) - 7,
        row_2_y + node_height / 2,
    )
    _draw_arrow(
        pdf,
        flow_x + 2 * (node_width + node_gap) + node_width / 2,
        row_2_y - 7,
        flow_x + node_width + node_gap + node_width / 2,
        row_3_y + node_height + 7,
    )

    card_x = margin + figure_1_width + 14
    card_width = page_width - margin - card_x
    draw_card(
        pdf,
        card_x,
        360,
        card_width,
        118,
        ">72% 自由文本",
        "Swift 2025：跨境支付异常调查消息仍存在显著结构化缺口。",
        accent=OCEAN_BLUE,
    )
    draw_card(
        pdf,
        card_x,
        232,
        card_width,
        118,
        "单点能力已成熟",
        "Stripe 动态推荐支付方式；Primer 用事件时间线还原请求与响应。",
        accent=TEAL,
    )
    draw_card(
        pdf,
        card_x,
        104,
        card_width,
        118,
        "协作仍需人工还原",
        "G2 单一验证用户反馈：历史交易与到账关系仍需人工梳理。定性个案，不代表行业比例。",
        accent=AMBER,
    )

    draw_paragraph(
        pdf,
        html.escape("全链仅使用 synthetic 数据；人工确认不执行支付、退款、风控放行或资金动作。"),
        margin,
        144,
        figure_1_width,
        13,
        caption_style,
    )
    chip_width = 109
    chip_gap = 9
    chip_y = 68
    _draw_chip(pdf, "商户成功案件", margin, chip_y, chip_width, 23, accent=TEAL)
    _draw_chip(
        pdf,
        "案件证据契约",
        margin + chip_width + chip_gap,
        chip_y,
        chip_width,
        23,
        accent=OCEAN_BLUE,
    )
    _draw_chip(
        pdf,
        "受控协作闭环",
        margin + 2 * (chip_width + chip_gap),
        chip_y,
        chip_width,
        23,
        accent=AMBER,
    )
    pdf.setStrokeColor(PALE_BORDER)
    pdf.setLineWidth(0.6)
    pdf.line(margin, 62, page_width - margin, 62)
    page_1_sources = (
        html.escape(
            "[1] swift.com/.../exceptions-and-investigations-april2025.pdf  "
            "[2] docs.stripe.com/.../dynamic-payment-methods"
        )
        + "<br/>"
        + html.escape(
            "[3] primer.io/docs/concepts/payment-timeline  "
            "[4] g2.com/products/stripe-stripe-payments/reviews（定性个案）"
        )
    )
    draw_paragraph(pdf, page_1_sources, margin, 57, content_width, 20, source_style)
    pdf.showPage()

    # Page 2: current runtime, local evidence, and external release boundary.
    _draw_page_frame(pdf, page_width, page_height, margin)
    draw_paragraph(
        pdf,
        html.escape("02｜支付异常闭环已打通，综合智能体按阶段扩展"),
        margin,
        page_height - margin,
        content_width,
        34,
        title_style,
    )

    figure_2_width = 220 * mm
    layer_x = margin + 10
    layer_width = figure_2_width - 20
    layer_height = 48
    layer_y_values = (438, 371, 304, 237, 170)
    runtime_layers = (
        ("飞书交互", "签名 callback｜群聊建案｜角色化卡片", OCEAN_BLUE),
        ("案件编排", "readiness｜七步补证｜去重与租约", TEAL),
        ("诊断内核", "四条确定性规则｜置信度｜证据引用", TEAL),
        ("受控协作", "责任建议｜人工确认｜approval audit", AMBER),
        ("持久化展示", "Core + Feishu SQLite｜只读 Cockpit", OCEAN_BLUE),
    )
    for index, ((title, body, accent), layer_y) in enumerate(
        zip(runtime_layers, layer_y_values, strict=True)
    ):
        _draw_layer(
            pdf,
            layer_x,
            layer_y,
            layer_width,
            layer_height,
            title,
            body,
            accent=accent,
        )
        if index < len(runtime_layers) - 1:
            _draw_arrow(
                pdf,
                layer_x + layer_width / 2,
                layer_y - 4,
                layer_x + layer_width / 2,
                layer_y_values[index + 1] + layer_height + 4,
            )

    status_x = margin + figure_2_width + 13
    status_width = page_width - margin - status_x
    draw_card(
        pdf,
        status_x,
        400,
        status_width,
        121,
        "当前已实现｜LIVE / SYNTHETIC",
        "飞书建案、七步补证、持久化诊断、责任建议、人工确认审计、只读驾驶舱｜8 条 OpenAPI",
        accent=TEAL,
    )
    draw_card(
        pdf,
        status_x,
        267,
        status_width,
        121,
        "本地发布证据",
        "1034 tests｜signed fixture｜四规则 API demo｜clean copy｜wheel 静态资源",
        accent=OCEAN_BLUE,
    )
    draw_card(
        pdf,
        status_x,
        134,
        status_width,
        121,
        "仍需外部验证 / 后续扩展",
        "真实飞书测试群｜GitHub CI / 匿名 commit｜Oceanpayment 只读适配｜Workflow｜工单/SLA",
        accent=NEUTRAL_GRAY,
    )

    mandatory_note = (
        "事实边界：当前本地能力均使用 synthetic 数据。真实飞书测试群、远端 CI 和"
        "当前提交的匿名可见性"
        "尚未验证；诊断与路由只提供建议，人工确认只写审计，不触发任何业务动作。"
    )
    draw_paragraph(
        pdf,
        html.escape(mandatory_note),
        margin,
        126,
        content_width,
        32,
        note_style,
    )
    _draw_roadmap_bar(
        pdf,
        "比赛演示（当前） → 真实飞书 smoke → 企业授权只读适配 → 试点评估",
        margin,
        64,
        content_width,
        24,
    )
    draw_paragraph(
        pdf,
        html.escape(
            "试点目标：证据引用/高风险人审 100%｜资料到齐时间 -30%｜"
            "首次责任域命中 80%｜改派次数 -30%"
        ),
        margin,
        54,
        content_width,
        16,
        trial_style,
    )
    pdf.setStrokeColor(PALE_BORDER)
    pdf.setLineWidth(0.6)
    pdf.line(margin, 36, page_width - margin, 36)
    draw_paragraph(
        pdf,
        html.escape(
            "仅使用 synthetic 数据｜不执行支付、退款、风控放行、资金移动或生产配置修改｜"
            "不声称真实业务成效、真实飞书联调、远端 CI 绿色或生产就绪"
        ),
        margin,
        30,
        content_width,
        14,
        boundary_style,
    )
    pdf.showPage()
    pdf.save()
    return output_path


def main() -> int:
    output_path = build_pdf()
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
