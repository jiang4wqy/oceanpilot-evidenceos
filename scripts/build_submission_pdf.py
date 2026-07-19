"""Build the deterministic two-page OceanPilot opening-report attachment."""

from __future__ import annotations

import html
import pathlib

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT_PDF = ROOT / "artifacts" / "OceanPilot-开题报告补充材料.pdf"
FIGURE_1 = ROOT / "docs" / "assets" / "submission" / "fig-01-evidence-loop.png"
FIGURE_2 = ROOT / "docs" / "assets" / "submission" / "fig-02-layered-architecture.png"

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


def draw_contained_image(
    canvas,
    path: pathlib.Path,
    x: float,
    y: float,
    max_width: float,
    max_height: float,
) -> tuple[float, float]:
    """Draw an uncropped, aspect-ratio-preserving image centered in a box."""
    if not path.is_file():
        raise FileNotFoundError(f"Required image not found: {path}")
    image = ImageReader(str(path))
    pixel_width, pixel_height = image.getSize()
    scale = min(max_width / pixel_width, max_height / pixel_height)
    draw_width = pixel_width * scale
    draw_height = pixel_height * scale
    draw_x = x + (max_width - draw_width) / 2
    draw_y = y + (max_height - draw_height) / 2
    canvas.drawImage(
        image,
        draw_x,
        draw_y,
        width=draw_width,
        height=draw_height,
        preserveAspectRatio=True,
        mask="auto",
    )
    return draw_width, draw_height


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
    figure_1_y = 118.5
    figure_1_box_height = 359.5
    drawn_width, _ = draw_contained_image(
        pdf,
        FIGURE_1,
        margin,
        figure_1_y,
        figure_1_width,
        figure_1_box_height,
    )
    if drawn_width < 220 * mm:
        raise ValueError("Page 1 main diagram rendered below 220 mm")

    card_x = margin + figure_1_width + 14
    card_width = page_width - margin - card_x
    draw_card(
        pdf,
        card_x,
        365,
        card_width,
        113,
        ">72% 自由文本",
        "Swift 2025：跨境支付异常调查消息仍存在显著结构化缺口。",
        accent=OCEAN_BLUE,
    )
    draw_card(
        pdf,
        card_x,
        242,
        card_width,
        113,
        "单点能力已成熟",
        "Stripe 动态推荐支付方式；Primer 用事件时间线还原请求与响应。",
        accent=TEAL,
    )
    draw_card(
        pdf,
        card_x,
        119,
        card_width,
        113,
        "协作仍需人工还原",
        "G2 单一验证用户反馈：历史交易与到账关系仍需人工梳理。定性个案，不代表行业比例。",
        accent=AMBER,
    )

    draw_paragraph(
        pdf,
        html.escape("绿色实线为当前基础原型，蓝色虚线为离线规则资产，灰色与琥珀色为完整方案路径。"),
        margin,
        111,
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

    # Page 2: verified implementation boundary and staged delivery plan.
    _draw_page_frame(pdf, page_width, page_height, margin)
    draw_paragraph(
        pdf,
        html.escape("02｜证据内核已验证，完整飞书闭环按阶段接入"),
        margin,
        page_height - margin,
        content_width,
        34,
        title_style,
    )

    figure_2_width = 220 * mm
    figure_2_y = 169.5
    figure_2_box_height = 351.5
    drawn_width, _ = draw_contained_image(
        pdf,
        FIGURE_2,
        margin,
        figure_2_y,
        figure_2_width,
        figure_2_box_height,
    )
    if drawn_width < 220 * mm - 0.1:
        raise ValueError("Page 2 main diagram rendered below 220 mm")

    status_x = margin + figure_2_width + 13
    status_width = page_width - margin - status_x
    draw_card(
        pdf,
        status_x,
        412,
        status_width,
        109,
        "当前已实现",
        "建案、证据、完整度、revision、SQLite 原子事务与审计｜717 项本地测试｜5 条 API 路径",
        accent=TEAL,
    )
    draw_card(
        pdf,
        status_x,
        291,
        status_width,
        109,
        "离线领域资产",
        "4 条确定性异常规则及测试｜尚未接入运行时诊断主链",
        accent=OCEAN_BLUE,
    )
    draw_card(
        pdf,
        status_x,
        170,
        status_width,
        109,
        "入围后规划",
        "飞书 Agent｜真实只读适配｜诊断编排｜Workflow｜工单/SLA｜知识复用",
        accent=NEUTRAL_GRAY,
    )

    mandatory_note = (
        "事实边界：诊断请求进入 API 后固定返回 HTTP 501 FEATURE_DEFERRED；离线规则当前未接入主链。"
        "图中左侧深蓝折线仅标示停止边界，不表示 501 反向调用 FastAPI。"
    )
    draw_paragraph(
        pdf,
        html.escape(mandatory_note),
        margin,
        160,
        content_width,
        30,
        note_style,
    )
    _draw_roadmap_bar(
        pdf,
        "基础原型（当前） → 飞书交互 → 真实只读适配 → 试点评估",
        margin,
        101,
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
        91,
        content_width,
        16,
        trial_style,
    )
    pdf.setStrokeColor(PALE_BORDER)
    pdf.setLineWidth(0.6)
    pdf.line(margin, 64, page_width - margin, 64)
    draw_paragraph(
        pdf,
        html.escape(
            "仅使用合成数据｜诊断仍为 HTTP 501｜不执行支付、退款、风控放行或资金动作｜"
            "不声称真实业务成效或生产就绪"
        ),
        margin,
        57,
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
