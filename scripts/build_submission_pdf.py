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

    # Page 1: comprehensive-agent thesis and controlled evidence loop.
    _draw_page_frame(pdf, page_width, page_height, margin)
    title_bottom = draw_paragraph(
        pdf,
        html.escape("01｜从单点工具到综合商户成功智能体"),
        margin,
        page_height - margin,
        content_width,
        34,
        title_style,
    )
    draw_paragraph(
        pdf,
        html.escape(
            "OceanPilot 用一份可追溯的商户成功案件统一问题、证据、判断、责任与审计："
            "缺证先补问，过门再判断，高风险动作由人工确认。"
        ),
        margin,
        title_bottom - 6,
        content_width,
        42,
        statement_style,
    )

    card_gap = 12
    card_width = (content_width - 2 * card_gap) / 3
    draw_card(
        pdf,
        margin,
        348,
        card_width,
        112,
        ">72% 自由文本",
        "Swift 2025：跨境支付异常调查消息仍存在显著结构化缺口。",
        accent=OCEAN_BLUE,
    )
    draw_card(
        pdf,
        margin + card_width + card_gap,
        348,
        card_width,
        112,
        "单点能力已成熟",
        "Stripe 动态推荐支付方式；Primer 用事件时间线还原请求与响应。",
        accent=TEAL,
    )
    draw_card(
        pdf,
        margin + 2 * (card_width + card_gap),
        348,
        card_width,
        112,
        "协作仍需人工还原",
        "G2 单一验证用户反馈：历史交易与到账关系仍需人工梳理。定性个案，不代表行业比例。",
        accent=AMBER,
    )

    loop_title_style = ParagraphStyle(
        "loop-title",
        fontName=bold_font,
        fontSize=17,
        leading=21,
        textColor=NAVY,
        alignment=TA_CENTER,
        wordWrap="CJK",
    )
    draw_paragraph(
        pdf,
        html.escape("一份案件，一套证据口径，扩展到多种商户成功场景"),
        margin,
        318,
        content_width,
        24,
        loop_title_style,
    )
    loop_labels = (
        ("问题建案", TEAL),
        ("证据补问", OCEAN_BLUE),
        ("证据门槛", OCEAN_BLUE),
        ("确定性诊断", TEAL),
        ("责任路由", OCEAN_BLUE),
        ("人工确认", AMBER),
    )
    loop_gap = 13
    loop_width = (content_width - 5 * loop_gap) / 6
    loop_y = 253
    for index, (label, accent) in enumerate(loop_labels):
        x = margin + index * (loop_width + loop_gap)
        _draw_chip(pdf, label, x, loop_y, loop_width, 35, accent=accent)
        if index < len(loop_labels) - 1:
            pdf.setStrokeColor(NAVY)
            pdf.setFillColor(NAVY)
            pdf.setLineWidth(1.4)
            start_x = x + loop_width + 2
            end_x = x + loop_width + loop_gap - 2
            center_y = loop_y + 17.5
            pdf.line(start_x, center_y, end_x, center_y)
            pdf.line(end_x - 4, center_y + 3, end_x, center_y)
            pdf.line(end_x - 4, center_y - 3, end_x, center_y)

    vision_width = (content_width - 2 * card_gap) / 3
    draw_card(
        pdf,
        margin,
        118,
        vision_width,
        108,
        "AI 处理模糊性",
        "理解描述、抽取字段、向正确角色追问，但不绕过证据门槛。",
        accent=OCEAN_BLUE,
    )
    draw_card(
        pdf,
        margin + vision_width + card_gap,
        118,
        vision_width,
        108,
        "规则守住确定性",
        "版本化证据、状态机、确定性规则、来源引用与责任路由可审计。",
        accent=TEAL,
    )
    draw_card(
        pdf,
        margin + 2 * (vision_width + card_gap),
        118,
        vision_width,
        108,
        "人工守住高风险",
        "确认只写审批审计，不等于执行支付、退款、放行或资金动作。",
        accent=AMBER,
    )

    chip_width = 118
    chip_gap = 10
    chip_y = 76
    _draw_chip(pdf, "商户成功案件", margin, chip_y, chip_width, 25, accent=TEAL)
    _draw_chip(
        pdf,
        "案件证据契约",
        margin + chip_width + chip_gap,
        chip_y,
        chip_width,
        25,
        accent=OCEAN_BLUE,
    )
    _draw_chip(
        pdf,
        "受控协作闭环",
        margin + 2 * (chip_width + chip_gap),
        chip_y,
        chip_width,
        25,
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

    # Page 2: two verified synthetic vertical slices and the external boundary.
    _draw_page_frame(pdf, page_width, page_height, margin)
    draw_paragraph(
        pdf,
        html.escape("02｜两个 synthetic 纵向切片，共用同一证据内核"),
        margin,
        page_height - margin,
        content_width,
        34,
        title_style,
    )

    slice_gap = 16
    slice_width = (content_width - slice_gap) / 2
    draw_card(
        pdf,
        margin,
        357,
        slice_width,
        141,
        "支付异常｜8 月 16 日主展示",
        "四个 synthetic 场景；公开案件/证据/诊断 API；就绪门、规则、置信度、"
        "责任域、证据与审计引用；signed local Feishu fixture 与幂等确认。",
        accent=TEAL,
    )
    draw_card(
        pdf,
        margin + slice_width + slice_gap,
        357,
        slice_width,
        141,
        "拒付申诉｜并列纵向切片",
        "synthetic 建案、原因分类、证据清单、评估、材料包、申诉草稿、"
        "人审门、安全扫描、审计与指标。",
        accent=OCEAN_BLUE,
    )
    draw_card(
        pdf,
        margin,
        260,
        content_width,
        76,
        "共用证据内核｜19 OpenAPI 路径",
        "Case + Evidence Contract + Readiness Gate + Diagnosis + Routing + Audit；"
        "三个 SQLite 职责隔离，本地 signed fixture 经过真实验签与回调路由。",
        accent=TEAL,
    )

    mandatory_note = (
        "真实性边界：signed fixture 使用进程内 synthetic transport，不连接飞书网络。"
        "人工确认仅写审计，no business action；真实飞书群未验证，公网 HTTPS 回调、"
        "Oceanpayment 数据与生产部署也未验证。"
    )
    draw_paragraph(
        pdf,
        html.escape(mandatory_note),
        margin,
        244,
        content_width,
        36,
        note_style,
    )
    _draw_roadmap_bar(
        pdf,
        "两个 synthetic 切片（当前） → 真实飞书群 smoke → 企业授权只读适配 → 试点评估",
        margin,
        176,
        content_width,
        28,
    )
    draw_paragraph(
        pdf,
        html.escape(
            "未来试点目标（非当前收益）：证据引用/高风险人审 100%｜资料到齐时间 -30%｜"
            "首次责任域命中 80%｜改派次数 -30%"
        ),
        margin,
        157,
        content_width,
        32,
        trial_style,
    )
    pdf.setStrokeColor(PALE_BORDER)
    pdf.setLineWidth(0.6)
    pdf.line(margin, 102, page_width - margin, 102)
    draw_paragraph(
        pdf,
        html.escape(
            "仅使用 synthetic 数据｜不执行支付、退款、风控放行、资金移动、"
            "生产配置变更或真实拒付提交｜"
            "不声称真实飞书联调、真实业务成效或生产就绪"
        ),
        margin,
        93,
        content_width,
        28,
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
