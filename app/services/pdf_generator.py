"""
PDF document generation using ReportLab with a standardized Prontivus template.

Header:
- Left: Prontivus logo (configurable via PRONTIVUS_LOGO_PATH)
- Center: Clinic name + details
- Right: Document type + issuance date

Footer:
- Centered slogan: "Prontivus — Cuidado inteligente"

Dynamic signature:
- "Dr. [Nome] - CRM/[número]"

Document templates:
- Prescription: medications table (name, dosage, frequency, duration, notes)
- Medical certificate
- Referral form
- Receipt
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional
from io import BytesIO
from datetime import datetime
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib import colors


def _draw_header(
    c: canvas.Canvas,
    page_width: float,
    page_height: float,
    clinic: Dict[str, Any],
    document_type: str,
    issuance_dt: Optional[datetime] = None,
) -> None:
    logo_path = os.getenv("PRONTIVUS_LOGO_PATH", "public/Logo/Prontivus Horizontal Transparents.png")
    left_x = 1.5 * cm
    top_y = page_height - 1.8 * cm

    # Left: logo (60px height ~ 0.85cm at 72dpi; we directly set pixel height in points)
    try:
        if os.path.exists(logo_path):
            c.drawImage(logo_path, left_x, page_height - 2.5 * cm, height=60, preserveAspectRatio=True, mask='auto')
    except Exception:
        pass

    # Center: clinic name + details
    center_x = page_width / 2
    c.setFont("Helvetica-Bold", 12)
    clinic_name = (clinic.get("name") or "Prontivus Clinic").strip()
    c.drawCentredString(center_x, page_height - 1.6 * cm, clinic_name)
    c.setFont("Helvetica", 9)
    details = clinic.get("details") or clinic.get("address") or ""
    if details:
        c.drawCentredString(center_x, page_height - 2.0 * cm, str(details)[:90])

    # Right: document type + date
    right_x = page_width - 1.5 * cm
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(right_x, page_height - 1.4 * cm, document_type)
    c.setFont("Helvetica", 9)
    issued = issuance_dt or datetime.now()
    c.drawRightString(right_x, page_height - 1.9 * cm, issued.strftime("%d/%m/%Y %H:%M"))

    # Divider
    c.setStrokeColor(colors.lightgrey)
    c.line(1.5 * cm, page_height - 2.7 * cm, page_width - 1.5 * cm, page_height - 2.7 * cm)


def _draw_footer(c: canvas.Canvas, page_width: float) -> None:
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.grey)
    c.drawCentredString(page_width / 2, 1.2 * cm, "Prontivus — Cuidado inteligente")
    c.setFillColor(colors.black)


def _draw_signature(
    c: canvas.Canvas,
    page_width: float,
    y: float,
    doctor: Dict[str, Any],
) -> None:
    # Signature line
    line_width = 6.5 * cm
    x = (page_width - line_width) / 2
    c.line(x, y, x + line_width, y)
    c.setFont("Helvetica", 9)
    doc_name = (doctor.get("name") or "").strip()
    crm = (doctor.get("crm") or "").strip()
    c.drawCentredString(x + line_width / 2, y - 12, f"Dr. {doc_name} - CRM/{crm}")


def _begin_doc(document_type: str, clinic: Dict[str, Any]) -> canvas.Canvas:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    _draw_header(c, width, height, clinic, document_type)
    return c


def _finalize(c: canvas.Canvas) -> bytes:
    width, _ = A4
    _draw_footer(c, width)
    c.showPage()
    c.save()
    data = c.getpdfdata()
    return data


def generate_prescription_pdf(
    clinic: Dict[str, Any],
    patient: Dict[str, Any],
    doctor: Dict[str, Any],
    medications: List[Dict[str, Any]],  # name, dosage, frequency, duration, notes
) -> bytes:
    c = _begin_doc("Prescrição", clinic)
    width, height = A4
    y = height - 3.5 * cm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1.5 * cm, y, "Paciente:")
    c.setFont("Helvetica", 10)
    c.drawString(3.2 * cm, y, f"{patient.get('name','')}  |  {patient.get('id','')}")
    y -= 0.6 * cm
    c.drawString(1.5 * cm, y, f"Data: {datetime.now().strftime('%d/%m/%Y')}")
    y -= 0.8 * cm

    # Table header
    c.setFont("Helvetica-Bold", 10)
    cols = ["Medicamento", "Dosagem", "Frequência", "Duração", "Observações"]
    col_x = [1.5 * cm, 7.5 * cm, 11.0 * cm, 14.0 * cm, 16.5 * cm]
    for i, col in enumerate(cols):
        c.drawString(col_x[i], y, col)
    y -= 0.4 * cm
    c.setStrokeColor(colors.black)
    c.line(1.5 * cm, y, width - 1.5 * cm, y)
    y -= 0.3 * cm
    c.setFont("Helvetica", 10)
    for m in medications:
        if y < 3.5 * cm:
            _draw_footer(c, width)
            c.showPage()
            _draw_header(c, width, height, clinic, "Prescrição")
            y = height - 3.5 * cm
            c.setFont("Helvetica-Bold", 10)
            for i, col in enumerate(cols):
                c.drawString(col_x[i], y, col)
            y -= 0.7 * cm
            c.setFont("Helvetica", 10)
        c.drawString(col_x[0], y, str(m.get('name',''))[:28])
        c.drawString(col_x[1], y, str(m.get('dosage',''))[:18])
        c.drawString(col_x[2], y, str(m.get('frequency',''))[:18])
        c.drawString(col_x[3], y, str(m.get('duration',''))[:12])
        c.drawString(col_x[4], y, str(m.get('notes',''))[:32])
        y -= 0.6 * cm

    # Signature
    _draw_signature(c, width, 2.8 * cm, doctor)
    return _finalize(c)


def generate_medical_certificate_pdf(
    clinic: Dict[str, Any],
    patient: Dict[str, Any],
    doctor: Dict[str, Any],
    justification: str,
    validity_days: int,
) -> bytes:
    c = _begin_doc("Atestado Médico", clinic)
    width, height = A4
    y = height - 3.5 * cm
    c.setFont("Helvetica", 11)
    c.drawString(1.5 * cm, y, f"Paciente: {patient.get('name','')}")
    y -= 0.8 * cm
    c.drawString(1.5 * cm, y, f"Documento: {patient.get('document','')}")
    y -= 1.0 * cm
    text = f"Justificativa: {justification}"
    for line in _wrap_text(text, 90):
        c.drawString(1.5 * cm, y, line)
        y -= 0.6 * cm
    y -= 0.4 * cm
    c.drawString(1.5 * cm, y, f"Validade: {validity_days} dias")

    _draw_signature(c, width, 2.8 * cm, doctor)
    return _finalize(c)


def generate_referral_pdf(
    clinic: Dict[str, Any],
    patient: Dict[str, Any],
    doctor: Dict[str, Any],
    specialty: str,
    reason: str,
    urgency: str,
) -> bytes:
    c = _begin_doc("Encaminhamento", clinic)
    width, height = A4
    y = height - 3.5 * cm
    c.setFont("Helvetica", 11)
    c.drawString(1.5 * cm, y, f"Paciente: {patient.get('name','')}")
    y -= 0.7 * cm
    c.drawString(1.5 * cm, y, f"Especialidade: {specialty}")
    y -= 0.7 * cm
    c.drawString(1.5 * cm, y, f"Urgência: {urgency}")
    y -= 0.9 * cm
    for line in _wrap_text(f"Motivo: {reason}", 95):
        c.drawString(1.5 * cm, y, line)
        y -= 0.6 * cm

    _draw_signature(c, width, 2.8 * cm, doctor)
    return _finalize(c)


def generate_receipt_pdf(
    clinic: Dict[str, Any],
    patient: Dict[str, Any],
    doctor: Dict[str, Any],
    services: List[Dict[str, Any]],  # description, qty, unit_price
    payments: Optional[List[Dict[str, Any]]] = None,  # method, amount, date
) -> bytes:
    c = _begin_doc("Recibo", clinic)
    width, height = A4
    y = height - 3.5 * cm
    c.setFont("Helvetica", 11)
    c.drawString(1.5 * cm, y, f"Paciente: {patient.get('name','')}")
    y -= 0.8 * cm

    # Services table
    c.setFont("Helvetica-Bold", 10)
    headers = ["Serviço", "Qtde", "Vlr Unit.", "Total"]
    xcol = [1.5 * cm, 12.5 * cm, 14.8 * cm, 17.2 * cm]
    for i, h in enumerate(headers):
        c.drawString(xcol[i], y, h)
    y -= 0.4 * cm
    c.line(1.5 * cm, y, width - 1.5 * cm, y)
    y -= 0.3 * cm
    c.setFont("Helvetica", 10)
    total = 0.0
    for s in services:
        desc = str(s.get('description',''))[:60]
        qty = float(s.get('qty') or 1)
        unit = float(s.get('unit_price') or 0)
        line_total = qty * unit
        total += line_total
        if y < 4.0 * cm:
            _draw_footer(c, width)
            c.showPage()
            _draw_header(c, width, height, clinic, "Recibo")
            y = height - 3.5 * cm
            c.setFont("Helvetica-Bold", 10)
            for i, h in enumerate(headers):
                c.drawString(xcol[i], y, h)
            y -= 0.7 * cm
            c.setFont("Helvetica", 10)
        c.drawString(xcol[0], y, desc)
        c.drawRightString(xcol[1] + 0.8 * cm, y, f"{qty:.0f}")
        c.drawRightString(xcol[2] + 1.2 * cm, y, f"R$ {unit:,.2f}")
        c.drawRightString(xcol[3] + 0.8 * cm, y, f"R$ {line_total:,.2f}")
        y -= 0.6 * cm

    y -= 0.4 * cm
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(width - 1.5 * cm, y, f"Total: R$ {total:,.2f}")
    y -= 0.8 * cm

    if payments:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(1.5 * cm, y, "Pagamentos")
        y -= 0.5 * cm
        c.setFont("Helvetica", 10)
        for p in payments:
            c.drawString(1.5 * cm, y, f"{p.get('date','')}: {p.get('method','')} - R$ {float(p.get('amount') or 0):,.2f}")
            y -= 0.5 * cm

    _draw_signature(c, width, max(2.8 * cm, y - 1.2 * cm), doctor)
    return _finalize(c)


def _wrap_text(text: str, width_chars: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current: List[str] = []
    for w in words:
        if len(" ".join(current + [w])) <= width_chars:
            current.append(w)
        else:
            lines.append(" ".join(current))
            current = [w]
    if current:
        lines.append(" ".join(current))
    return lines


