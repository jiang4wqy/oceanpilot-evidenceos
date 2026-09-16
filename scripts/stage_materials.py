"""One-page, text-based synthetic delivery records. No real customer data."""

from io import BytesIO

PROOF = "fulfillment.proof_of_delivery"


def delivery_pdf(transaction, *, delivered_at=None):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4, invariant=1)
    pdf.setTitle("OceanPilot - Synthetic proof of delivery")
    width, height = A4
    ink, teal = HexColor("#173D40"), HexColor("#00786C")
    pdf.setFillColor(teal)
    pdf.rect(0, height - 125, width, 125, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(42, height - 36, "OCEANPILOT / SYNTHETIC DEMO ONLY")
    pdf.setFont("Helvetica-Bold", 28)
    pdf.drawString(42, height - 77, "Proof of delivery")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(42, height - 103, "MOCK upstream - not a real carrier or customer record")
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica", 13)
    pdf.drawString(
        42, height - 166, "Delivery record / " + ("Revision 2" if delivered_at else "Revision 1")
    )
    rows = [
        ("transaction_id", transaction["transaction_id"]),
        ("currency", transaction["currency"]),
        ("amount_minor", str(transaction["amount_minor"])),
        ("recipient_confirmation", "Received by Alex Demo (synthetic)"),
    ]
    if delivered_at:
        rows.append(("delivered_at", delivered_at))
    y = height - 216
    for key, value in rows:
        pdf.setStrokeColor(HexColor("#DCE8E3"))
        pdf.line(42, y - 18, width - 42, y - 18)
        pdf.setFont("Helvetica", 13)
        pdf.drawString(42, y, f"{key}: {value}")
        y -= 62
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(42, 182, "Independent verification required")
    pdf.setFont("Helvetica", 11)
    for line, baseline in zip(
        [
            "This file is a synthetic training fixture for an OceanPilot demo.",
            "Text extraction is a suggestion, not proof of authenticity or admissibility.",
            "No bank submission, dispute outcome or movement of funds is represented.",
        ],
        (155, 136, 117),
        strict=True,
    ):
        pdf.drawString(42, baseline, line)
    pdf.setFillColor(teal)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(42, 52, "SYNTHETIC / MOCK / NOT FINAL")
    pdf.drawRightString(width - 42, 52, "1 / 1")
    pdf.showPage()
    pdf.save()
    return stream.getvalue()
