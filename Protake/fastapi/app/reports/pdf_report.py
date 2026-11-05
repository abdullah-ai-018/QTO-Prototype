import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.reports.data import ReportData

_NAVY = colors.HexColor("#0B0D10")
_ACCENT = colors.HexColor("#2563EB")
_MUTED = colors.HexColor("#475569")
_BORDER = colors.HexColor("#CBD5E1")


def generate_pdf(data: ReportData) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], textColor=_NAVY, fontSize=20, spaceAfter=2)
    subtitle_style = ParagraphStyle("ReportSubtitle", parent=styles["Normal"], textColor=_MUTED, fontSize=10)
    section_style = ParagraphStyle("Section", parent=styles["Heading2"], textColor=_ACCENT, fontSize=13, spaceBefore=16, spaceAfter=6)

    story = []
    story.append(Paragraph("Protake — Enterprise Estimate Report", title_style))
    story.append(Paragraph(f"{data.project_name} &nbsp;·&nbsp; Revision {data.version} &nbsp;·&nbsp; {data.generated_at}", subtitle_style))
    story.append(Spacer(1, 4))

    meta_rows = [
        ["Client", data.client_name or "—"],
        ["Location", data.location or "—"],
    ]
    meta_table = Table(meta_rows, colWidths=[1.3 * inch, 4.5 * inch])
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), _MUTED),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(meta_table)

    for section in data.trades:
        story.append(Paragraph(section.trade, section_style))
        table_data = [["Line Item", "Quantity", "Unit", "Unit Cost", "Total"]]
        for item in section.items:
            table_data.append(
                [item.label, f"{item.quantity:,.2f}", item.unit, f"${item.unit_cost:,.2f}", f"${item.total_cost:,.2f}"]
            )
        table_data.append(["", "", "", "Direct Cost", f"${section.direct_cost:,.2f}"])

        table = Table(table_data, colWidths=[2.3 * inch, 1.1 * inch, 0.9 * inch, 1.1 * inch, 1.2 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("GRID", (0, 0), (-1, -1), 0.5, _BORDER),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EFF6FF")),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)

    story.append(Paragraph("Cost Summary", section_style))
    summary_data = [
        ["Material Cost", f"${data.material_cost:,.2f}"],
        ["Labor Cost", f"${data.labor_cost:,.2f}"],
        ["Direct Cost", f"${data.direct_cost:,.2f}"],
        [f"Overhead ({data.overhead_pct:g}%)", f"${data.overhead_amount:,.2f}"],
        [f"Contingency ({data.contingency_pct:g}%)", f"${data.contingency_amount:,.2f}"],
        [f"Profit ({data.profit_pct:g}%)", f"${data.profit_amount:,.2f}"],
        ["Final Bid Price", f"${data.final_bid_price:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[3.3 * inch, 2.3 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, _BORDER),
                ("BACKGROUND", (0, -1), (-1, -1), _ACCENT),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, -1), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(summary_table)

    doc.build(story)
    return buffer.getvalue()
