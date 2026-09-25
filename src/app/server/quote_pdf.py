from __future__ import annotations

from datetime import UTC, datetime, timedelta
from html import escape
from io import BytesIO
from typing import Any, Iterable, Mapping

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import QuotePdfSettings


INK = colors.HexColor("#1B2028")
MUTED = colors.HexColor("#667085")
LINE = colors.HexColor("#E4E7EC")
SURFACE = colors.HexColor("#F7F8FA")
SUCCESS = colors.HexColor("#13795B")


def _money(value: Any) -> str:
    return f"${float(value or 0):,.2f}"


def _text(value: Any, fallback: str = "") -> str:
    return escape(str(value or fallback).strip())


def build_quote_pdf(
    *,
    quote_id: str,
    order_id: str,
    revision_number: int,
    account: Mapping[str, Any] | None,
    seller_email: str,
    line_items: Iterable[Mapping[str, Any]],
    generated_at: datetime | None = None,
    pdf_settings: QuotePdfSettings | Mapping[str, Any] | None = None,
) -> bytes:
    """Render a customer-ready quote with repeating headers for long line lists."""

    if not isinstance(pdf_settings, QuotePdfSettings):
        pdf_settings = QuotePdfSettings.model_validate(pdf_settings or {})
    generated = generated_at or datetime.now(UTC)
    account = account or {}
    lines = [dict(line) for line in line_items]
    compact = pdf_settings.layout == "compact"
    accent = colors.HexColor(pdf_settings.accent_color)
    list_total = sum(
        float(line.get("list_price") or line.get("unit_price") or 0)
        * int(line.get("quantity") or 1)
        for line in lines
    )
    net_total = sum(
        float(line.get("total_price") or (
            float(line.get("unit_price") or 0) * int(line.get("quantity") or 1)
        ))
        for line in lines
    )
    savings = max(0.0, list_total - net_total)

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=LETTER,
        leftMargin=(0.46 if compact else 0.58) * inch,
        rightMargin=(0.46 if compact else 0.58) * inch,
        topMargin=(0.5 if compact else 0.62) * inch,
        bottomMargin=(0.5 if compact else 0.58) * inch,
        title=f"Quote {quote_id}",
        author="Agentic CPQ",
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "QuoteBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.8 if compact else 8.5,
        leading=9.5 if compact else 11,
        textColor=INK,
    )
    small = ParagraphStyle(
        "QuoteSmall",
        parent=body,
        fontSize=6.5 if compact else 7,
        leading=8 if compact else 9,
        textColor=MUTED,
    )
    label = ParagraphStyle(
        "QuoteLabel",
        parent=small,
        fontName="Helvetica-Bold",
        fontSize=6.5,
        leading=8,
        spaceAfter=2,
    )
    title = ParagraphStyle(
        "QuoteTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=19 if compact else 23,
        leading=22 if compact else 27,
        textColor=INK,
        spaceAfter=4,
    )
    product = ParagraphStyle(
        "QuoteProduct",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=7.7,
        leading=9.5,
    )
    product_meta = ParagraphStyle(
        "QuoteProductMeta",
        parent=small,
        fontSize=6.5,
        leading=8,
    )
    amount = ParagraphStyle(
        "QuoteAmount",
        parent=body,
        fontSize=7.7,
        leading=9.5,
        alignment=TA_RIGHT,
    )

    story: list[Any] = []
    heading = Table(
        [[
            [
                Paragraph(f"<b>{_text(pdf_settings.brand_name)}</b>", label),
                Paragraph(_text(pdf_settings.document_title), title),
            ],
            [Paragraph("QUOTE", label), Paragraph(f"<b>{_text(quote_id)}</b>", body),
             Paragraph(f"Revision {revision_number} · {generated:%b %d, %Y}", small)],
        ]],
        colWidths=[document.width * 0.72, document.width * 0.28],
    )
    heading.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.extend([heading, Spacer(1, (0.14 if compact else 0.22) * inch)])

    customer = Table(
        [[
            [Paragraph("PREPARED FOR", label), Paragraph(f"<b>{_text(account.get('name'), 'Customer')}</b>", body),
             Paragraph(f"{_text(account.get('segment'), 'Standard').title()} · {_text(account.get('region'), 'Region')}", small)],
            [Paragraph("PREPARED BY", label), Paragraph(_text(seller_email, "Sales team"), body),
             Paragraph(
                 f"Valid through {(generated + timedelta(days=pdf_settings.validity_days)):%b %d, %Y}",
                 small,
             )],
        ]],
        colWidths=[document.width * 0.51, document.width * 0.49],
    )
    customer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6 if compact else 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6 if compact else 8),
    ]))
    story.extend([customer, Spacer(1, (0.15 if compact else 0.23) * inch)])

    header_row: list[Any] = [
        Paragraph("PRODUCT", label),
        Paragraph("QTY", label),
    ]
    if pdf_settings.show_list_prices:
        header_row.append(Paragraph("LIST", label))
    header_row.extend([
        Paragraph("NET UNIT", label),
        Paragraph("LINE TOTAL", label),
    ])
    rows: list[list[Any]] = [header_row]
    for line in lines:
        is_care = bool(line.get("is_addon"))
        name = _text(line.get("title"), "Product")
        prefix = "Care plan · " if is_care else ""
        metadata = f"{_text(line.get('sku'))} · {_text(line.get('category'), 'Product').title()}"
        if is_care and line.get("covers_sku"):
            metadata += f" · Covers {_text(line.get('covers_sku'))}"
        quantity = int(line.get("quantity") or 1)
        unit = float(line.get("unit_price") or 0)
        list_price = float(line.get("list_price") or unit)
        total = float(line.get("total_price") or unit * quantity)
        row: list[Any] = [
            [Paragraph(f"{prefix}{name}", product), Paragraph(metadata, product_meta)],
            Paragraph(str(quantity), amount),
        ]
        if pdf_settings.show_list_prices:
            row.append(Paragraph(_money(list_price), amount))
        row.extend([
            Paragraph(_money(unit), amount),
            Paragraph(f"<b>{_money(total)}</b>", amount),
        ])
        rows.append(row)

    line_widths = (
        [
            document.width * 0.47,
            document.width * 0.06,
            document.width * 0.13,
            document.width * 0.15,
            document.width * 0.19,
        ]
        if pdf_settings.show_list_prices
        else [
            document.width * 0.59,
            document.width * 0.06,
            document.width * 0.16,
            document.width * 0.19,
        ]
    )

    line_table = Table(
        rows,
        repeatRows=1,
        colWidths=line_widths,
        hAlign="LEFT",
    )
    line_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.45, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 4 if compact else 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4 if compact else 6),
    ]
    for index, line in enumerate(lines, start=1):
        if line.get("is_addon"):
            line_styles.append(("BACKGROUND", (0, index), (-1, index), colors.HexColor("#F1F8F5")))
        elif index % 2 == 0:
            line_styles.append(("BACKGROUND", (0, index), (-1, index), SURFACE))
    line_table.setStyle(TableStyle(line_styles))
    story.extend([line_table, Spacer(1, (0.14 if compact else 0.22) * inch)])

    summary_rows: list[list[Any]] = []
    if pdf_settings.show_list_prices:
        summary_rows.append(
            [Paragraph("List value", body), Paragraph(_money(list_total), amount)]
        )
    if pdf_settings.show_savings:
        summary_rows.append(
            [Paragraph("Customer savings", body), Paragraph(_money(savings), amount)]
        )
    summary_rows.append([
        Paragraph(
            "Quote total",
            ParagraphStyle("TotalLabel", parent=body, fontName="Helvetica-Bold", fontSize=10),
        ),
        Paragraph(
            f"<b>{_money(net_total)}</b>",
            ParagraphStyle("TotalAmount", parent=amount, fontSize=12, textColor=SUCCESS),
        ),
    ])
    total_row = len(summary_rows) - 1
    summary = Table(summary_rows, colWidths=[1.7 * inch, 1.35 * inch], hAlign="RIGHT")
    summary.setStyle(TableStyle([
        ("LINEABOVE", (0, total_row), (-1, total_row), 1, INK),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(KeepTogether([summary, Spacer(1, 0.25 * inch)]))
    story.extend([
        Paragraph("TERMS", label),
        Paragraph(_text(pdf_settings.terms_text), small),
        Spacer(1, 0.12 * inch),
        Paragraph(f"Reference: {_text(order_id)}", small),
    ])

    def decorate_page(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        width, height = LETTER
        canvas.setFillColor(accent)
        canvas.rect(0, height - 7, width, 7, stroke=0, fill=1)
        canvas.setStrokeColor(LINE)
        canvas.line(document.leftMargin, 30, width - document.rightMargin, 30)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.5)
        canvas.drawString(document.leftMargin, 19, pdf_settings.footer_text)
        canvas.drawRightString(width - document.rightMargin, 19, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
    return output.getvalue()
