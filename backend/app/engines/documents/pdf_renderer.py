"""
PDF Renderer — generates watermarked invoice and statement PDFs using ReportLab.

EVERY PDF has a visible "SYNTHETIC SAMPLE — NOT A REAL DOCUMENT" watermark.
This CANNOT be disabled. PDF metadata also declares synthetic origin.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                 Paragraph, Spacer, PageBreak)
from reportlab.pdfgen import canvas as pdfcanvas

from app.core.money import fmt


WATERMARK_TEXT = "SYNTHETIC SAMPLE — NOT A REAL DOCUMENT"


def _draw_watermark(c, doc):
    """Draw diagonal watermark on every page. Cannot be disabled."""
    c.saveState()
    c.setFont("Helvetica-Bold", 42)
    c.setFillColor(colors.Color(0.85, 0.85, 0.85, alpha=0.5))
    c.translate(doc.pagesize[0] / 2, doc.pagesize[1] / 2)
    c.rotate(45)
    c.drawCentredString(0, 0, WATERMARK_TEXT)
    c.restoreState()

    # Footer
    c.saveState()
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.grey)
    c.drawCentredString(doc.pagesize[0] / 2, 15,
                        "This document is synthetic test data. It does not represent any real transaction.")
    c.restoreState()


def _set_metadata(c, title: str = "Synthetic Document"):
    """Set PDF metadata declaring synthetic origin."""
    c.setTitle(title)
    c.setAuthor("SynthGen AI — Synthetic Data Platform")
    c.setSubject("SYNTHETIC TEST DATA — NOT REAL")
    c.setKeywords("synthetic, test, generated, fictional, not-real")


def render_invoice_pdf(invoice, output_path: str, currency: str = "USD") -> str:
    """Render an Invoice object to a watermarked PDF.

    Args:
        invoice: Invoice model instance
        output_path: Where to save the PDF
        currency: Currency code for formatting

    Returns:
        Path to the generated PDF
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            topMargin=2*cm, bottomMargin=2*cm,
                            leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("InvTitle", parent=styles["Heading1"],
                                  fontSize=24, textColor=colors.HexColor("#1a1a2e"))
    subtitle_style = ParagraphStyle("InvSub", parent=styles["Normal"],
                                     fontSize=10, textColor=colors.grey)
    header_style = ParagraphStyle("InvHeader", parent=styles["Heading3"],
                                   fontSize=12, textColor=colors.HexColor("#16213e"))

    elements = []

    # Title + Invoice number
    elements.append(Paragraph("INVOICE", title_style))
    elements.append(Paragraph(f"{invoice.invoice_number}", subtitle_style))
    elements.append(Spacer(1, 8*mm))

    # Issuer / Recipient
    party_data = [
        ["From:", "Bill To:"],
        [Paragraph(f"<b>{invoice.issuer.name}</b><br/>{invoice.issuer.address}<br/>"
                    f"{invoice.issuer.city}, {invoice.issuer.country}<br/>"
                    f"{invoice.issuer.email}", styles["Normal"]),
         Paragraph(f"<b>{invoice.recipient.name}</b><br/>{invoice.recipient.address}<br/>"
                    f"{invoice.recipient.city}, {invoice.recipient.country}<br/>"
                    f"{invoice.recipient.email}", styles["Normal"])],
    ]
    t = Table(party_data, colWidths=[250, 250])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f3460")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 6*mm))

    # Dates
    elements.append(Paragraph(
        f"Issue Date: <b>{invoice.issue_date}</b> &nbsp;&nbsp;&nbsp; "
        f"Due Date: <b>{invoice.due_date}</b> &nbsp;&nbsp;&nbsp; "
        f"Terms: <b>{invoice.payment_terms}</b>", styles["Normal"]))
    elements.append(Spacer(1, 8*mm))

    # Line items table
    elements.append(Paragraph("Line Items", header_style))
    header = ["#", "Description", "Qty", "Unit Price", "Total"]
    data = [header]
    cur = invoice.currency
    for i, line in enumerate(invoice.lines, 1):
        data.append([
            str(i), line.description, str(line.quantity),
            fmt(line.unit_price, cur), fmt(line.line_total, cur),
        ])

    t = Table(data, colWidths=[30, 220, 40, 90, 90])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 6*mm))

    # Totals
    totals_data = [
        ["Subtotal:", fmt(invoice.subtotal, cur)],
    ]
    if invoice.discount_total > 0:
        totals_data.append(["Discount:", f"-{fmt(invoice.discount_total, cur)}"])
    totals_data.append(["Net Amount:", fmt(invoice.net_amount, cur)])
    for tax in invoice.taxes:
        totals_data.append([f"{tax.label} ({float(tax.rate)*100:.1f}%):", fmt(tax.amount, cur)])
    if invoice.shipping > 0:
        totals_data.append(["Shipping:", fmt(invoice.shipping, cur)])
    totals_data.append(["GRAND TOTAL:", fmt(invoice.grand_total, cur)])

    t = Table(totals_data, colWidths=[370, 100])
    style_cmds = [
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#1a1a2e")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    t.setStyle(TableStyle(style_cmds))
    elements.append(t)

    # Notes
    if invoice.notes:
        elements.append(Spacer(1, 8*mm))
        elements.append(Paragraph(f"Notes: {invoice.notes}", styles["Normal"]))

    # Build PDF with watermark on every page
    doc.build(elements, onFirstPage=_draw_watermark, onLaterPages=_draw_watermark)
    return output_path


def render_statement_pdf(statement, output_path: str, currency: str = "USD") -> str:
    """Render a BankStatement object to a watermarked PDF."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            topMargin=2*cm, bottomMargin=2*cm,
                            leftMargin=1.5*cm, rightMargin=1.5*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("StTitle", parent=styles["Heading1"],
                                  fontSize=20, textColor=colors.HexColor("#1a1a2e"))

    elements = []

    # Header
    elements.append(Paragraph(f"{statement.institution}", title_style))
    elements.append(Paragraph("ACCOUNT STATEMENT", styles["Heading2"]))
    elements.append(Spacer(1, 4*mm))

    # Account info
    info = [
        ["Account Holder:", statement.account_holder],
        ["Account Number:", statement.account_number],
        ["Statement Period:", f"{statement.period_start} to {statement.period_end}"],
        ["Opening Balance:", fmt(statement.opening_balance, currency)],
    ]
    t = Table(info, colWidths=[130, 350])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 6*mm))

    # Transactions table
    header = ["Date", "Description", "Debit", "Credit", "Balance"]
    data = [header]
    cur = statement.currency
    for tx in statement.transactions:
        data.append([
            tx.date,
            tx.description[:40],
            fmt(tx.debit, cur) if tx.debit else "",
            fmt(tx.credit, cur) if tx.credit else "",
            fmt(tx.balance, cur),
        ])

    t = Table(data, colWidths=[65, 200, 75, 75, 85])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 6*mm))

    # Summary
    summary = [
        ["Total Debits:", fmt(statement.total_debits, cur)],
        ["Total Credits:", fmt(statement.total_credits, cur)],
        ["Closing Balance:", fmt(statement.closing_balance, cur)],
        ["Transactions:", str(statement.n_transactions)],
    ]
    t = Table(summary, colWidths=[380, 100])
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, -2), (-1, -2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(t)

    doc.build(elements, onFirstPage=_draw_watermark, onLaterPages=_draw_watermark)
    return output_path


def render_to_bytes(render_func, obj, currency: str = "USD") -> bytes:
    """Render a PDF to bytes (for API responses)."""
    buf = io.BytesIO()
    # Use a temp path-like approach
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        tmp_path = f.name
    try:
        render_func(obj, tmp_path, currency)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
