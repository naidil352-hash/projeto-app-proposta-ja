"""Geração do PDF público de uma proposta aceita."""

from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _text(value: Any, fallback: str = "-") -> str:
    if value is None or value == "":
        return fallback
    return escape(str(value))


def _money(value: Any, currency: Any) -> str:
    try:
        amount = float(value or 0)
        formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        formatted = _text(value, "0,00")
    return f"{formatted} {_text(currency, 'BRL')}"


def _date(value: Any) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        return _text(value)


def build_proposal_pdf(proposal: dict[str, Any], company: dict[str, Any] | None = None) -> bytes:
    """Retorna um PDF A4 autocontido, pronto para download e arquivamento."""
    company = company or {}
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Proposta {proposal.get('number') or proposal.get('public_code') or ''}",
        author=company.get("name") or company.get("company_name") or "Proposta Já",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("ProposalTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=colors.HexColor("#0f766e"))
    heading = ParagraphStyle("Heading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#134e4a"), spaceBefore=10, spaceAfter=5)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=13)
    small = ParagraphStyle("Small", parent=body, fontSize=8, leading=11, textColor=colors.HexColor("#475569"))
    total = ParagraphStyle("Total", parent=body, fontName="Helvetica-Bold", fontSize=12, leading=15, alignment=TA_RIGHT, textColor=colors.HexColor("#0f766e"))

    story: list[Any] = []
    story.append(Paragraph(_text(company.get("name") or company.get("company_name"), "Proposta Já"), title))
    story.append(Paragraph("PROPOSTA COMERCIAL", heading))
    story.append(Paragraph(f"Proposta nº <b>{_text(proposal.get('number') or proposal.get('public_code'))}</b> &nbsp; • &nbsp; Emitida em {_date(proposal.get('created_at'))}", body))
    story.append(Spacer(1, 5 * mm))

    client = proposal.get("client") or {
        "name": proposal.get("client_name") or proposal.get("client_company"),
        "document": proposal.get("client_document"),
        "email": proposal.get("client_email"),
    }
    story.append(Paragraph("Cliente", heading))
    client_data = [
        [Paragraph("<b>Nome</b>", small), Paragraph(_text(client.get("name")), body)],
        [Paragraph("<b>Documento</b>", small), Paragraph(_text(client.get("document")), body)],
        [Paragraph("<b>E-mail</b>", small), Paragraph(_text(client.get("email")), body)],
    ]
    client_table = Table(client_data, colWidths=[32 * mm, 140 * mm])
    client_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0fdfa")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(client_table)

    story.append(Paragraph("Itens", heading))
    rows: list[list[Any]] = [[
        Paragraph("<b>Descrição</b>", small), Paragraph("<b>Qtd.</b>", small),
        Paragraph("<b>Valor unit.</b>", small), Paragraph("<b>Total</b>", small),
    ]]
    items = proposal.get("items") or proposal.get("products") or []
    currency = proposal.get("currency") or "BRL"
    for item in items:
        quantity = item.get("quantity") or 0
        unit_price = item.get("unit_price", item.get("price", 0))
        line_total = item.get("total", item.get("total_price"))
        if line_total is None:
            try:
                line_total = float(quantity) * float(unit_price)
            except (TypeError, ValueError):
                line_total = 0
        description = item.get("description") or item.get("name") or item.get("product_name") or "Item"
        sku = item.get("sku") or item.get("code")
        if sku:
            description = f"{description} (SKU: {sku})"
        rows.append([
            Paragraph(_text(description), body), Paragraph(_text(quantity, "0"), body),
            Paragraph(_money(unit_price, currency), body), Paragraph(_money(line_total, currency), body),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("Nenhum item informado", body), "", "", ""])
    items_table = Table(rows, colWidths=[82 * mm, 18 * mm, 35 * mm, 37 * mm], repeatRows=1)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(items_table)

    financial = proposal.get("financial") or {}
    total_value = financial.get("total", proposal.get("grand_total", proposal.get("total")))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"Total da proposta: {_money(total_value, financial.get('currency') or currency)}", total))
    terms = proposal.get("terms") or proposal.get("commercial_conditions") or proposal.get("notes")
    if terms:
        story.append(Paragraph("Observações", heading))
        story.append(Paragraph(_text(terms).replace("\n", "<br/>"), body))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Documento gerado automaticamente pelo Proposta Já.", small))
    document.build(story)
    return buffer.getvalue()
