"""
PDF document generation using ReportLab with a standardized Prontivus template.

Header:
- Center: Prontivus logo (centered, configurable via PRONTIVUS_LOGO_PATH)
- Center: Clinic name + details (below logo)
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
import logging

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors

try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PILImage = None
    PIL_AVAILABLE = False


def _resolve_logo_path() -> Optional[str]:
    """
    Resolve an absolute path to the **brand logo** image.

    Important: Consultation reports already use a logo resolution
    strategy that works in your environment. To ensure the same
    behaviour for prescriptions and certificates, we mirror that
    logic here.

    Priority:
      1) PRONTIVUS_LOGO_PATH env var (absolute or relative)
      2) Backend static copy:
         app/static/Prontivus Horizontal Transparents.png
      3) \"public/Logo/Prontivus Horizontal Transparents.png\" (when
         running from project root/backend)
      4) \"../frontend/public/Logo/Prontivus Horizontal Transparents.png\"
         (when backend is executed from the monorepo root)
    """
    # 1) Explicit override via env var (optional)
    env_path = os.getenv("PRONTIVUS_LOGO_PATH")
    if env_path:
        # Absolute path
        if os.path.isabs(env_path) and os.path.exists(env_path):
            return env_path
        # Relative path from current working directory
        if os.path.exists(env_path):
            return os.path.abspath(env_path)

    # 2) Backend static copy (recommended deployment location)
    services_dir = os.path.dirname(__file__)
    backend_static = os.path.abspath(
        os.path.join(services_dir, "..", "static", "Prontivus Horizontal Transparents.png")
    )
    if os.path.exists(backend_static):
        return backend_static

    # 3) Same defaults used by consultation PDF header
    #    a) public/Logo/... (when running from project root/backend)
    default_relative = os.path.join("public", "Logo", "Prontivus Horizontal Transparents.png")
    if os.path.exists(default_relative):
        return os.path.abspath(default_relative)

    #    b) ../frontend/public/Logo/... (when running from backend directory)
    fallback_frontend = os.path.join("..", "frontend", "public", "Logo", "Prontivus Horizontal Transparents.png")
    if os.path.exists(fallback_frontend):
        return os.path.abspath(fallback_frontend)

    return None


def _draw_header(
    c: canvas.Canvas,
    page_width: float,
    page_height: float,
    clinic: Dict[str, Any],
    document_type: str,
    issuance_dt: Optional[datetime] = None,
) -> float:
    """
    Draw the document header with logo and clinic information.
    
    Returns:
        The Y position (in points) where document content should start (below the header divider).
    """
    logo_path = _resolve_logo_path()
    
    # Debug logging (can be removed in production)
    logger = logging.getLogger(__name__)
    if logo_path:
        logger.info(f"PDF Logo path resolved: {logo_path}, exists: {os.path.exists(logo_path) if logo_path else False}")
    else:
        logger.warning("PDF Logo path could not be resolved")
    
    top_y = page_height - 1.8 * cm
    center_x = page_width / 2

    # Center: Logo (centered in header)
    # Use a more reasonable logo size (2.5 inches height for horizontal logos)
    logo_height = 2.5 * inch  # ~180 points, approximately 6.35 cm
    logo_drawn = False
    logo_bottom_y = None
    
    try:
        if logo_path and os.path.exists(logo_path):
            logo_width = None
            
            if PIL_AVAILABLE:
                # Get actual image dimensions to calculate proper aspect ratio
                try:
                    with PILImage.open(logo_path) as img:
                        img_width, img_height = img.size
                        aspect_ratio = img_width / img_height
                        # Calculate width based on fixed height to maintain aspect ratio
                        logo_width = logo_height * aspect_ratio
                        logger.info(f"Logo dimensions: {img_width}x{img_height}, calculated width: {logo_width}")
                except Exception as e:
                    # If PIL fails, fall through to fallback
                    logger.warning(f"PIL failed to open logo: {e}")
                    pass
            
            if logo_width is None:
                # Fallback: use reasonable default for horizontal logos (typical 3:2 ratio for this logo)
                # Based on actual logo size 1536x1024 = 1.5:1 ratio
                logo_width = logo_height * 1.5
                logger.info(f"Using fallback logo width: {logo_width}")
            
            # Position logo at top of page with small margin
            # logo_y is the BOTTOM of the logo in ReportLab coordinates (y=0 is bottom of page)
            logo_y = page_height - 0.8 * cm - logo_height
            logo_bottom_y = logo_y  # Store for positioning text below
            
            # Center the logo horizontally
            logo_x = center_x - (logo_width / 2)
            logger.info(f"Drawing logo at position: x={logo_x:.2f}, y={logo_y:.2f}, width={logo_width:.2f}, height={logo_height:.2f}")
            
            # Draw the logo - try without mask first, then with mask if needed
            try:
                c.drawImage(
                    logo_path,
                    logo_x,
                    logo_y,
                    width=logo_width,
                    height=logo_height,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception as mask_error:
                # If mask="auto" fails, try without mask
                logger.warning(f"drawImage with mask failed, trying without: {mask_error}")
                c.drawImage(
                    logo_path,
                    logo_x,
                    logo_y,
                    width=logo_width,
                    height=logo_height,
                    preserveAspectRatio=True,
                )
            
            logo_drawn = True
            logger.info("Logo successfully drawn on PDF")
    except Exception as e:
        # If logo loading fails, log the error and continue with text-based fallback logo
        logger.error(f"Failed to draw logo on PDF: {e}", exc_info=True)
        logo_drawn = False

    # If no image logo was drawn, render a simple text-based brand mark
    if not logo_drawn:
        text_logo_y = page_height - 1.2 * cm
        c.setFont("Helvetica-Bold", 18)
        c.setFillColorRGB(0.0, 0.45, 0.8)  # Prontivus brand blue
        c.drawCentredString(center_x, text_logo_y, "PRONTIVUS")
        c.setFillColor(colors.black)
        logo_bottom_y = text_logo_y - 0.3 * cm

    # Below logo: clinic/company identification (centered)
    # Position below the logo with appropriate spacing
    if logo_bottom_y is None:
        logo_bottom_y = page_height - 0.8 * cm - logo_height
    clinic_name_y = logo_bottom_y - 0.6 * cm
    c.setFont("Helvetica-Bold", 12)
    clinic_name = (clinic.get("name") or "Prontivus Clinic").strip()
    c.drawCentredString(center_x, clinic_name_y, clinic_name)

    # Build clinic/company detail lines
    c.setFont("Helvetica", 9)
    # First line: address or custom details string
    address_or_details = clinic.get("details") or clinic.get("address") or ""

    # Second line: CNPJ, phone, email (when available)
    tax_id = (clinic.get("tax_id") or clinic.get("cnpj") or "").strip()
    phone = (clinic.get("phone") or "").strip()
    email = (clinic.get("email") or "").strip()

    info_parts = []
    if tax_id:
        info_parts.append(f"CNPJ: {tax_id}")
    if phone:
        info_parts.append(f"Tel: {phone}")
    if email:
        info_parts.append(email)

    info_line = "  •  ".join(info_parts)

    # Draw address/details line (if any)
    text_y = clinic_name_y - 0.4 * cm
    if address_or_details:
        c.drawCentredString(center_x, text_y, str(address_or_details)[:110])
        text_y -= 0.35 * cm

    # Draw info line (if any)
    if info_line:
        c.drawCentredString(center_x, text_y, info_line[:110])

    # Right: document type + date
    right_x = page_width - 1.5 * cm
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(right_x, page_height - 1.4 * cm, document_type)
    c.setFont("Helvetica", 9)
    issued = issuance_dt or datetime.now()
    c.drawRightString(right_x, page_height - 1.9 * cm, issued.strftime("%d/%m/%Y %H:%M"))

    # Divider (below logo and clinic info)
    divider_y = text_y - 0.4 * cm
    c.setStrokeColor(colors.lightgrey)
    c.line(1.5 * cm, divider_y, page_width - 1.5 * cm, divider_y)
    
    # Return the Y position where content should start (below divider with spacing)
    content_start_y = divider_y - 0.6 * cm
    return content_start_y


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


def _begin_doc(document_type: str, clinic: Dict[str, Any]) -> tuple[canvas.Canvas, float]:
    """
    Initialize a new PDF document with header.
    
    Returns:
        Tuple of (canvas, content_start_y) where content_start_y is the Y position
        where document content should start (below the header).
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    content_start_y = _draw_header(c, width, height, clinic, document_type)
    return c, content_start_y


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
    c, content_start_y = _begin_doc("Prescrição", clinic)
    width, height = A4

    # Draw a soft card background to give a modern look
    card_margin_x = 1.4 * cm
    card_margin_y = 2.0 * cm  # Start card below header
    card_width = width - 2 * card_margin_x
    card_height = content_start_y - card_margin_y - 4.0 * cm  # Leave space for footer
    c.setFillColor(colors.whitesmoke)
    c.roundRect(card_margin_x, card_margin_y, card_width, card_height, 10, stroke=0, fill=1)
    c.setFillColor(colors.black)

    # Top section: patient info - start below header
    y = content_start_y
    x_left = card_margin_x + 0.6 * cm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_left, y, "Paciente")
    c.setFont("Helvetica", 10)
    c.drawString(x_left + 2.4 * cm, y, f"{patient.get('name','')}  |  {patient.get('id','')}")
    y -= 0.6 * cm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x_left, y, "Data")
    c.setFont("Helvetica", 10)
    c.drawString(x_left + 2.4 * cm, y, datetime.now().strftime("%d/%m/%Y"))
    y -= 0.9 * cm

    # Table header with colored band
    c.setFont("Helvetica-Bold", 10)
    cols = ["Medicamento", "Dosagem", "Frequência", "Duração", "Observações"]
    col_x = [
        x_left,
        x_left + 6.0 * cm,
        x_left + 9.3 * cm,
        x_left + 12.3 * cm,
        x_left + 14.8 * cm,
    ]

    header_height = 0.7 * cm
    c.setFillColorRGB(0.90, 0.95, 1.0)  # light blue band
    c.roundRect(
        card_margin_x + 0.3 * cm,
        y - 0.25 * cm,
        card_width - 0.6 * cm,
        header_height,
        4,
        stroke=0,
        fill=1,
    )
    c.setFillColor(colors.black)

    for i, col in enumerate(cols):
        c.drawString(col_x[i], y, col)
    y -= 0.4 * cm
    c.setStrokeColor(colors.lightgrey)
    c.line(card_margin_x + 0.3 * cm, y, width - card_margin_x - 0.3 * cm, y)
    y -= 0.25 * cm
    c.setFont("Helvetica", 10)

    for m in medications:
        if y < 3.5 * cm:
            _draw_footer(c, width)
            c.showPage()
            new_content_start_y = _draw_header(c, width, height, clinic, "Prescrição")
            # Redraw card and header row on new page
            c.setFillColor(colors.whitesmoke)
            c.roundRect(card_margin_x, card_margin_y, card_width, card_height, 10, stroke=0, fill=1)
            c.setFillColor(colors.black)
            y = new_content_start_y
            c.setFont("Helvetica-Bold", 10)
            c.setFillColorRGB(0.90, 0.95, 1.0)
            c.roundRect(
                card_margin_x + 0.3 * cm,
                y - 0.25 * cm,
                card_width - 0.6 * cm,
                header_height,
                4,
                stroke=0,
                fill=1,
            )
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 10)
            for i, col in enumerate(cols):
                c.drawString(col_x[i], y, col)
            y -= 0.4 * cm
            c.setStrokeColor(colors.lightgrey)
            c.line(card_margin_x + 0.3 * cm, y, width - card_margin_x - 0.3 * cm, y)
            y -= 0.25 * cm
            c.setFont("Helvetica", 10)

        # Zebra rows for readability
        if int((card_height - (y - card_margin_y)) / (0.7 * cm)) % 2 == 0:
            c.setFillColorRGB(0.98, 0.98, 0.98)
            c.rect(card_margin_x + 0.3 * cm, y - 0.15 * cm, card_width - 0.6 * cm, 0.55 * cm, stroke=0, fill=1)
            c.setFillColor(colors.black)

        c.drawString(col_x[0], y, str(m.get("name", ""))[:32])
        c.drawString(col_x[1], y, str(m.get("dosage", ""))[:20])
        c.drawString(col_x[2], y, str(m.get("frequency", ""))[:20])
        c.drawString(col_x[3], y, str(m.get("duration", ""))[:14])
        c.drawString(col_x[4], y, str(m.get("notes", ""))[:40])
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
    c, content_start_y = _begin_doc("Atestado Médico", clinic)
    width, height = A4

    # Card background for modern layout - positioned below header
    card_margin_x = 1.8 * cm
    card_margin_y = 2.0 * cm  # Start below header
    card_width = width - 2 * card_margin_x
    card_height = content_start_y - card_margin_y - 4.0 * cm  # Leave space for footer
    c.setFillColorRGB(0.98, 0.98, 0.98)
    c.roundRect(card_margin_x, card_margin_y, card_width, card_height, 12, stroke=0, fill=1)
    c.setFillColor(colors.black)

    # Header inside card - start below document header
    y = content_start_y
    x_left = card_margin_x + 0.8 * cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_left, y, "Atestado Médico")
    y -= 1.0 * cm

    # Patient info
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_left, y, "Paciente:")
    c.setFont("Helvetica", 11)
    c.drawString(x_left + 2.4 * cm, y, patient.get("name", ""))
    y -= 0.7 * cm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_left, y, "Documento:")
    c.setFont("Helvetica", 11)
    c.drawString(x_left + 2.4 * cm, y, patient.get("document", ""))
    y -= 1.0 * cm

    # Justification paragraph
    c.setFont("Helvetica", 11)
    justificacao = justification or ""
    if justificacao:
        pref = "Justificativa: "
        text = pref + justificacao
        # Indent following lines to align with text after label
        lines = _wrap_text(text, 90)
        for idx, line in enumerate(lines):
            if idx == 0:
                c.drawString(x_left, y, line)
            else:
                c.drawString(x_left + c.stringWidth("Justificativa: ", "Helvetica", 11), y, line)
            y -= 0.6 * cm
        y -= 0.4 * cm

    # Validity
    if validity_days:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x_left, y, "Validade:")
        c.setFont("Helvetica", 11)
        c.drawString(x_left + 2.4 * cm, y, f"{validity_days} dias")

    # Signature area
    _draw_signature(c, width, card_margin_y + 1.2 * cm, doctor)
    return _finalize(c)


def generate_referral_pdf(
    clinic: Dict[str, Any],
    patient: Dict[str, Any],
    doctor: Dict[str, Any],
    specialty: str,
    reason: str,
    urgency: str,
) -> bytes:
    c, content_start_y = _begin_doc("Encaminhamento", clinic)
    width, height = A4
    y = content_start_y
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
    c, content_start_y = _begin_doc("Recibo", clinic)
    width, height = A4
    y = content_start_y
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
            new_content_start_y = _draw_header(c, width, height, clinic, "Recibo")
            y = new_content_start_y
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


# ==================== Enhanced PDF Generator Class ====================

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from io import BytesIO
import tempfile


class PDFGenerator:
    """
    Enhanced PDF Generator using ReportLab's Platypus framework
    Provides structured document generation with better formatting
    """
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Setup custom paragraph styles for medical documents"""
        # Medical Title Style
        self.styles.add(ParagraphStyle(
            name='MedicalTitle',
            parent=self.styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#0F4C75'),
            spaceAfter=30,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold',
        ))
        
        # Medical Heading Style
        self.styles.add(ParagraphStyle(
            name='MedicalHeading',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#1B9AAA'),
            spaceAfter=12,
            spaceBefore=12,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold',
        ))
        
        # Medical Body Style
        self.styles.add(ParagraphStyle(
            name='MedicalBody',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            alignment=TA_LEFT,
            fontName='Helvetica',
        ))
        
        # Medical Footer Style
        self.styles.add(ParagraphStyle(
            name='MedicalFooter',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.grey,
            alignment=TA_CENTER,
            fontName='Helvetica-Oblique',
        ))
    
    def generate_consultation_report(self, consultation_data: dict) -> bytes:
        """
        Generate a complete consultation report PDF
        
        Args:
            consultation_data: Dictionary containing:
                - clinic: Clinic information
                - patient: Patient information
                - doctor: Doctor information
                - appointment: Appointment details
                - clinical_record: Clinical record with SOAP notes
                - prescriptions: List of prescriptions
                - diagnoses: List of diagnoses
                - exam_requests: List of exam requests
        
        Returns:
            PDF file as bytes
        """
        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=1.5*cm,
                leftMargin=1.5*cm,
                topMargin=2*cm,
                bottomMargin=2*cm
            )
            story = []
            
            # Clinic Header
            story.extend(self._create_clinic_header(consultation_data.get('clinic', {})))
            story.append(Spacer(1, 20))
            
            # Patient Information
            story.append(Paragraph("INFORMAÇÕES DO PACIENTE", self.styles['MedicalTitle']))
            story.append(self._create_patient_table(consultation_data.get('patient', {})))
            story.append(Spacer(1, 15))
            
            # Appointment Details
            story.append(Paragraph("DADOS DA CONSULTA", self.styles['MedicalTitle']))
            story.extend(self._create_appointment_details(consultation_data.get('appointment', {})))
            story.append(Spacer(1, 15))
            
            # Clinical Record (SOAP Notes)
            clinical_record = consultation_data.get('clinical_record')
            if clinical_record:
                story.append(Paragraph("RELATÓRIO CLÍNICO", self.styles['MedicalTitle']))
                story.extend(self._create_consultation_content(clinical_record))
                story.append(Spacer(1, 15))
            
            # Diagnoses
            diagnoses = consultation_data.get('diagnoses', [])
            if diagnoses:
                story.append(Paragraph("DIAGNÓSTICOS", self.styles['MedicalTitle']))
                story.extend(self._create_diagnoses_section(diagnoses))
                story.append(Spacer(1, 15))
            
            # Prescriptions
            prescriptions = consultation_data.get('prescriptions', [])
            if prescriptions:
                story.append(Paragraph("PRESCRIÇÕES", self.styles['MedicalTitle']))
                story.extend(self._create_prescriptions_section(prescriptions))
                story.append(Spacer(1, 15))
            
            # Exam Requests
            exam_requests = consultation_data.get('exam_requests', [])
            if exam_requests:
                story.append(Paragraph("SOLICITAÇÕES DE EXAMES", self.styles['MedicalTitle']))
                story.extend(self._create_exam_requests_section(exam_requests))
                story.append(Spacer(1, 15))
            
            # Doctor Signature
            story.append(Spacer(1, 30))
            story.extend(self._create_doctor_signature_platypus(consultation_data.get('doctor', {})))
            
            # Footer
            story.append(Spacer(1, 20))
            story.append(Paragraph("Prontivus — Cuidado Inteligente", self.styles['MedicalFooter']))
            
            # Build PDF
            doc.build(story)
            buffer.seek(0)
            return buffer.getvalue()
            
        except Exception as e:
            raise Exception(f"PDF generation failed: {str(e)}")
    
    def _create_clinic_header(self, clinic_data: dict) -> list:
        """Create clinic header with centered logo and information"""
        elements = []
        
        # Try to load logo - check multiple paths
        logo_path = os.getenv("PRONTIVUS_LOGO_PATH", "public/Logo/Prontivus Horizontal Transparents.png")
        if not os.path.exists(logo_path):
            # Try frontend public path
            frontend_logo_path = os.path.join("..", "frontend", "public", "Logo", "Prontivus Horizontal Transparents.png")
            if os.path.exists(frontend_logo_path):
                logo_path = frontend_logo_path
        
        logo_exists = os.path.exists(logo_path)
        
        # Logo row - centered
        if logo_exists:
            try:
                logo_width = None
                logo_height = 2.4 * inch  # 3x larger (was 0.8 * inch)
                
                # Calculate proper dimensions based on actual logo aspect ratio
                if PIL_AVAILABLE:
                    try:
                        with PILImage.open(logo_path) as img:
                            img_width, img_height = img.size
                            aspect_ratio = img_width / img_height
                            # Calculate width based on fixed height to maintain aspect ratio
                            logo_width = logo_height * aspect_ratio
                    except Exception:
                        # If PIL fails, fall through to fallback
                        pass
                
                if logo_width is None:
                    # Fallback: use reasonable default for horizontal logos (3x larger)
                    logo_width = 9 * inch
                
                # Create Image with calculated dimensions to preserve aspect ratio
                logo_img = Image(logo_path, width=logo_width, height=logo_height)
                
                # Center the logo by placing it in a single-cell table
                logo_table = Table([[logo_img]], colWidths=[7*inch])
                logo_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                elements.append(logo_table)
                elements.append(Spacer(1, 8))
            except Exception as e:
                # If logo loading fails, continue without it
                pass
        
        # Clinic information row - centered below logo
        clinic_name = clinic_data.get('name', 'Prontivus Clinic')
        clinic_address = clinic_data.get('address', '')
        clinic_phone = clinic_data.get('phone', '')
        
        center_content = f"<b>{clinic_name}</b>"
        if clinic_address:
            center_content += f"<br/>{clinic_address}"
        if clinic_phone:
            center_content += f"<br/>Tel: {clinic_phone}"
        
        # Create a centered table for clinic info
        clinic_info_table = Table([[Paragraph(center_content, self.styles['Normal'])]], colWidths=[7*inch])
        clinic_info_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(clinic_info_table)
        elements.append(Spacer(1, 8))
        
        # Document type and date row - right aligned
        right_content = f"<b>Relatório de Consulta</b><br/>"
        right_content += f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        
        doc_info_table = Table([[Paragraph(right_content, self.styles['Normal'])]], colWidths=[7*inch])
        doc_info_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(doc_info_table)
        elements.append(Spacer(1, 10))
        
        # Divider line
        elements.append(Paragraph("<hr/>", self.styles['Normal']))
        
        return elements
    
    def _create_patient_table(self, patient_data: dict) -> Table:
        """Create patient information table"""
        patient_info = [
            ['Nome:', patient_data.get('first_name', '') + ' ' + patient_data.get('last_name', '')],
            ['CPF:', patient_data.get('cpf', 'N/A')],
            ['Data de Nascimento:', patient_data.get('date_of_birth', 'N/A')],
            ['Gênero:', patient_data.get('gender', 'N/A')],
            ['Telefone:', patient_data.get('phone', 'N/A')],
            ['E-mail:', patient_data.get('email', 'N/A')],
            ['Endereço:', patient_data.get('address', 'N/A')],
        ]
        
        table = Table(patient_info, colWidths=[2*inch, 5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F0F0F0')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#0F4C75')),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (0, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (1, 0), (1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]))
        
        return table
    
    def _create_appointment_details(self, appointment_data: dict) -> list:
        """Create appointment details section"""
        elements = []
        
        appointment_date = appointment_data.get('scheduled_datetime', '')
        if appointment_date:
            if isinstance(appointment_date, str):
                try:
                    appointment_date = datetime.fromisoformat(appointment_date.replace('Z', '+00:00'))
                except:
                    pass
            if isinstance(appointment_date, datetime):
                appointment_date = appointment_date.strftime('%d/%m/%Y %H:%M')
        
        details = [
            ['Data/Hora:', appointment_date or 'N/A'],
            ['Tipo:', appointment_data.get('appointment_type', 'N/A')],
            ['Status:', appointment_data.get('status', 'N/A')],
        ]
        
        if appointment_data.get('reason'):
            details.append(['Motivo:', appointment_data.get('reason', '')])
        
        table = Table(details, colWidths=[2*inch, 5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F0F0F0')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#0F4C75')),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (0, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (1, 0), (1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]))
        
        elements.append(table)
        return elements
    
    def _create_consultation_content(self, clinical_record: dict) -> list:
        """Create SOAP notes content"""
        elements = []
        
        # Subjective
        if clinical_record.get('subjective'):
            elements.append(Paragraph("<b>S - Subjetivo:</b>", self.styles['MedicalHeading']))
            elements.append(Paragraph(clinical_record.get('subjective', ''), self.styles['MedicalBody']))
            elements.append(Spacer(1, 10))
        
        # Objective
        if clinical_record.get('objective'):
            elements.append(Paragraph("<b>O - Objetivo:</b>", self.styles['MedicalHeading']))
            elements.append(Paragraph(clinical_record.get('objective', ''), self.styles['MedicalBody']))
            elements.append(Spacer(1, 10))
        
        # Assessment
        if clinical_record.get('assessment'):
            elements.append(Paragraph("<b>A - Avaliação:</b>", self.styles['MedicalHeading']))
            elements.append(Paragraph(clinical_record.get('assessment', ''), self.styles['MedicalBody']))
            elements.append(Spacer(1, 10))
        
        # Plan
        plan_text = clinical_record.get('plan_soap') or clinical_record.get('plan', '')
        if plan_text:
            elements.append(Paragraph("<b>P - Plano:</b>", self.styles['MedicalHeading']))
            elements.append(Paragraph(plan_text, self.styles['MedicalBody']))
            elements.append(Spacer(1, 10))
        
        return elements
    
    def _create_diagnoses_section(self, diagnoses: list) -> list:
        """Create diagnoses section"""
        elements = []
        
        if not diagnoses:
            return elements
        
        diagnoses_data = [['Código ICD-10', 'Descrição']]
        for diagnosis in diagnoses:
            icd10_code = diagnosis.get('icd10_code', 'N/A')
            description = diagnosis.get('description', diagnosis.get('diagnosis', 'N/A'))
            diagnoses_data.append([icd10_code, description])
        
        table = Table(diagnoses_data, colWidths=[2*inch, 5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1B9AAA')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ]))
        
        elements.append(table)
        return elements
    
    def _create_prescriptions_section(self, prescriptions: list) -> list:
        """Create prescriptions section"""
        elements = []
        
        if not prescriptions:
            return elements
        
        # Use existing prescription PDF function format
        prescriptions_data = [['Medicamento', 'Dosagem', 'Frequência', 'Duração', 'Instruções']]
        for rx in prescriptions:
            prescriptions_data.append([
                rx.get('medication_name', 'N/A'),
                rx.get('dosage', 'N/A'),
                rx.get('frequency', 'N/A'),
                rx.get('duration', 'N/A'),
                rx.get('instructions', '')[:50]  # Truncate long instructions
            ])
        
        table = Table(prescriptions_data, colWidths=[2*inch, 1.2*inch, 1.2*inch, 1*inch, 2.3*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1B9AAA')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
        ]))
        
        elements.append(table)
        return elements
    
    def _create_exam_requests_section(self, exam_requests: list) -> list:
        """Create exam requests section"""
        elements = []
        
        if not exam_requests:
            return elements
        
        exams_data = [['Tipo de Exame', 'Descrição', 'Urgência']]
        for exam in exam_requests:
            exams_data.append([
                exam.get('exam_type', 'N/A'),
                exam.get('description', exam.get('reason', 'N/A'))[:40],
                exam.get('urgency', 'N/A').upper() if exam.get('urgency') else 'N/A'
            ])
        
        table = Table(exams_data, colWidths=[2.5*inch, 3.5*inch, 1.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1B9AAA')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]))
        
        elements.append(table)
        return elements
    
    def _create_doctor_signature_platypus(self, doctor_data: dict) -> list:
        """Create doctor signature section using Platypus"""
        elements = []
        
        doctor_name = f"{doctor_data.get('first_name', '')} {doctor_data.get('last_name', '')}".strip()
        crm = doctor_data.get('crm', '')
        
        if doctor_name or crm:
            signature_text = f"Dr. {doctor_name}" if doctor_name else "Dr."
            if crm:
                signature_text += f" - CRM/{crm}"
            
            elements.append(Spacer(1, 20))
            elements.append(Paragraph("_" * 50, self.styles['Normal']))
            elements.append(Paragraph(signature_text, self.styles['Normal']))
        
        return elements
    
    def generate_prescription(self, prescription_data: dict) -> bytes:
        """
        Generate prescription PDF using existing function
        
        Args:
            prescription_data: Dictionary containing clinic, patient, doctor, medications
        
        Returns:
            PDF file as bytes
        """
        # Use existing function
        pdf_bytes = generate_prescription_pdf(
            clinic=prescription_data.get('clinic', {}),
            patient=prescription_data.get('patient', {}),
            doctor=prescription_data.get('doctor', {}),
            medications=prescription_data.get('medications', [])
        )
        return pdf_bytes
    
    def generate_medical_certificate(self, certificate_data: dict) -> bytes:
        """
        Generate medical certificate PDF using existing function
        
        Args:
            certificate_data: Dictionary containing clinic, patient, doctor, justification, validity_days
        
        Returns:
            PDF file as bytes
        """
        # Use existing function
        pdf_bytes = generate_medical_certificate_pdf(
            clinic=certificate_data.get('clinic', {}),
            patient=certificate_data.get('patient', {}),
            doctor=certificate_data.get('doctor', {}),
            justification=certificate_data.get('justification', ''),
            validity_days=certificate_data.get('validity_days', 0)
        )
        return pdf_bytes

