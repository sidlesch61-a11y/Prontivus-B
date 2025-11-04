"""
TISS XML Generation Service
Generates TISS standard XML files for health insurance billing
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload

from app.models.tiss import (
    TISSDocumento, TISSLote, TISSGuia, TISSDemoIdentificacao,
    TISSDemoIdentificacaoPrestador, TISSDemoIdentificacaoOperadora,
    TISSDemoIdentificacaoBeneficiario, TISSDemoIdentificacaoContratado,
    TISSProcedimentos, TISSProcedimentoExecutado, TISSOdonto, TISSOdontoProcedimento,
    TISSSADT, TISSSADTProcedimento,
    TUSS_TABLE_MAPPING, TUSS_CODE_MAPPING
)
from app.services.tiss_validator import validate_tiss_document
from app.models import Invoice, InvoiceLine, ServiceItem, Patient, User, Clinic, Appointment
from app.core.auth import get_current_user


async def generate_tiss_xml(invoice_id: int, db: AsyncSession, skip_validation: bool = False) -> str:
    """
    Generate TISS XML for a given invoice
    
    Args:
        invoice_id: ID of the invoice to generate TISS XML for
        db: Database session
        skip_validation: If True, skip validation and generate XML anyway
        
    Returns:
        XML string in TISS format
    """
    # Fetch invoice with all related data
    invoice_query = select(Invoice).options(
        joinedload(Invoice.patient),
        joinedload(Invoice.appointment).joinedload(Appointment.doctor),
        joinedload(Invoice.clinic),
        joinedload(Invoice.invoice_lines).joinedload(InvoiceLine.service_item)
    ).filter(Invoice.id == invoice_id)
    
    invoice_result = await db.execute(invoice_query)
    invoice = invoice_result.unique().scalar_one_or_none()
    
    if not invoice:
        raise ValueError(f"Invoice {invoice_id} not found")
    
    # Build TISS document structure
    tiss_doc = await _build_tiss_document(invoice)
    
    # Validate TISS document (unless skipped)
    if not skip_validation:
        validation_result = validate_tiss_document(tiss_doc)
        if not validation_result["is_valid"]:
            error_messages = [error["message"] for error in validation_result["errors"]]
            raise ValueError(f"TISS validation failed: {'; '.join(error_messages)}")
    
    # Convert to XML
    xml_content = _tiss_to_xml(tiss_doc)
    
    return xml_content


async def _build_tiss_document(invoice: Invoice) -> TISSDocumento:
    """Build TISS document structure from invoice data"""
    
    # Get clinic data (prestador)
    clinic = invoice.clinic
    # Clean CNPJ (remove formatting characters)
    cnpj_clean = (clinic.tax_id or "00000000000000").replace(".", "").replace("/", "").replace("-", "")
    prestador = TISSDemoIdentificacaoPrestador(
        cnpj=cnpj_clean,
        nome=clinic.name,
        codigo_prestador="001"  # Default code
    )
    
    # Default operadora data (should be configurable)
    operadora = TISSDemoIdentificacaoOperadora(
        cnpj="00000000000000",  # Should be configured per clinic
        nome="Operadora Padrão",
        registro_ans="000000"  # Should be configured per clinic
    )
    
    # Get patient data (beneficiario)
    patient = invoice.patient
    # Clean CPF (remove formatting characters)
    cpf_clean = (patient.cpf or "00000000000").replace(".", "").replace("-", "")
    # Map gender to TISS format
    sexo_tiss = "M"  # Default
    if patient.gender:
        if patient.gender.value.lower() in ["male", "masculino", "m"]:
            sexo_tiss = "M"
        elif patient.gender.value.lower() in ["female", "feminino", "f"]:
            sexo_tiss = "F"
    
    beneficiario = TISSDemoIdentificacaoBeneficiario(
        numero_carteira=cpf_clean,  # Use CPF as carteira number
        nome=f"{patient.first_name} {patient.last_name}",
        cpf=cpf_clean,
        data_nascimento=patient.date_of_birth.strftime("%Y-%m-%d") if patient.date_of_birth else "1900-01-01",
        sexo=sexo_tiss,
        nome_plano="Plano Padrão"  # Should be configured per patient
    )
    
    # Get doctor data (contratado)
    doctor = None
    if invoice.appointment and invoice.appointment.doctor:
        doctor = invoice.appointment.doctor
    
    # Clean doctor CPF if available (User model doesn't have CPF, use default)
    doctor_cpf_clean = "00000000000"
    # Note: User model doesn't have CPF field, using default value
    # In a real implementation, you might want to add CPF to User model or use a different approach
    
    contratado = TISSDemoIdentificacaoContratado(
        cpf=doctor_cpf_clean,
        nome=doctor.full_name if doctor else "Profissional Padrão",
        cbo="2251",  # Default CBO for doctors
        crm=doctor.crm if doctor and hasattr(doctor, 'crm') else None
    )
    
    # Build identificacao
    identificacao = TISSDemoIdentificacao(
        prestador=prestador,
        operadora=operadora,
        beneficiario=beneficiario,
        contratado=contratado,
        data_emissao=invoice.issue_date.strftime("%Y-%m-%d"),
        numero_guia=f"GUIA{invoice.id:06d}"
    )
    
    # Build procedimentos from invoice lines
    procedimentos = []
    for line in invoice.invoice_lines:
        service_item = line.service_item
        
        # Map service category to TUSS table code
        tabela_codigo = TUSS_TABLE_MAPPING.get(service_item.category.value, "99")
        
        # Get TUSS procedure code
        codigo_procedimento = TUSS_CODE_MAPPING.get(service_item.code, service_item.code or "0000000000")
        
        procedimento = TISSProcedimentoExecutado(
            codigo_tabela=tabela_codigo,
            codigo_procedimento=codigo_procedimento,
            descricao_procedimento=service_item.name,
            quantidade_executada=int(line.quantity),
            valor_unitario=line.unit_price,
            valor_total=line.line_total,
            data_execucao=invoice.issue_date.strftime("%Y-%m-%d"),
            hora_inicio="08:00",  # Default time
            hora_fim="09:00"      # Default time
        )
        procedimentos.append(procedimento)
    
    # Build procedimentos block
    procedimentos_block = TISSProcedimentos(procedimentos=procedimentos)
    
    # Build guia
    guia = TISSGuia(
        identificacao=identificacao,
        procedimentos=procedimentos_block,
        valor_total_guia=invoice.total_amount
    )
    
    # Build lote
    lote = TISSLote(
        numero_lote=f"LOTE{invoice.id:06d}",
        data_envio=datetime.now().strftime("%Y-%m-%d"),
        guias=[guia]
    )
    
    # Build final document
    tiss_doc = TISSDocumento(
        versao_tiss="3.05.02",
        lote=lote
    )
    
    return tiss_doc


def _tiss_to_xml(tiss_doc: TISSDocumento) -> str:
    """Convert TISS document to XML string"""
    import xml.etree.ElementTree as ET
    from xml.dom import minidom
    
    # Create root element
    root = ET.Element("tiss")
    root.set("xmlns", "http://www.ans.gov.br/padroes/tiss/schemas")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xsi:schemaLocation", "http://www.ans.gov.br/padroes/tiss/schemas http://www.ans.gov.br/padroes/tiss/schemas/tissV3_03_00.xsd")
    
    # Add version
    versao = ET.SubElement(root, "versao")
    versao.text = tiss_doc.versao_tiss
    
    # Add lote
    lote_elem = ET.SubElement(root, "lote")
    
    # Lote info
    numero_lote = ET.SubElement(lote_elem, "numeroLote")
    numero_lote.text = tiss_doc.lote.numero_lote
    
    data_envio = ET.SubElement(lote_elem, "dataEnvio")
    data_envio.text = tiss_doc.lote.data_envio
    
    # Guias
    guias_elem = ET.SubElement(lote_elem, "guias")
    
    for guia in tiss_doc.lote.guias:
        guia_elem = ET.SubElement(guias_elem, "guia")
        
        # Identificação
        identificacao_elem = ET.SubElement(guia_elem, "identificacao")
        
        # Prestador
        prestador_elem = ET.SubElement(identificacao_elem, "prestador")
        cnpj_prestador = ET.SubElement(prestador_elem, "cnpj")
        cnpj_prestador.text = guia.identificacao.prestador.cnpj
        nome_prestador = ET.SubElement(prestador_elem, "nome")
        nome_prestador.text = guia.identificacao.prestador.nome
        if guia.identificacao.prestador.codigo_prestador:
            codigo_prestador = ET.SubElement(prestador_elem, "codigoPrestador")
            codigo_prestador.text = guia.identificacao.prestador.codigo_prestador
        
        # Operadora
        operadora_elem = ET.SubElement(identificacao_elem, "operadora")
        cnpj_operadora = ET.SubElement(operadora_elem, "cnpj")
        cnpj_operadora.text = guia.identificacao.operadora.cnpj
        nome_operadora = ET.SubElement(operadora_elem, "nome")
        nome_operadora.text = guia.identificacao.operadora.nome
        registro_ans = ET.SubElement(operadora_elem, "registroANS")
        registro_ans.text = guia.identificacao.operadora.registro_ans
        
        # Beneficiário
        beneficiario_elem = ET.SubElement(identificacao_elem, "beneficiario")
        numero_carteira = ET.SubElement(beneficiario_elem, "numeroCarteira")
        numero_carteira.text = guia.identificacao.beneficiario.numero_carteira
        nome_beneficiario = ET.SubElement(beneficiario_elem, "nome")
        nome_beneficiario.text = guia.identificacao.beneficiario.nome
        cpf_beneficiario = ET.SubElement(beneficiario_elem, "cpf")
        cpf_beneficiario.text = guia.identificacao.beneficiario.cpf
        data_nascimento = ET.SubElement(beneficiario_elem, "dataNascimento")
        data_nascimento.text = guia.identificacao.beneficiario.data_nascimento
        sexo = ET.SubElement(beneficiario_elem, "sexo")
        sexo.text = guia.identificacao.beneficiario.sexo
        nome_plano = ET.SubElement(beneficiario_elem, "nomePlano")
        nome_plano.text = guia.identificacao.beneficiario.nome_plano
        
        # Contratado
        contratado_elem = ET.SubElement(identificacao_elem, "contratado")
        cpf_contratado = ET.SubElement(contratado_elem, "cpf")
        cpf_contratado.text = guia.identificacao.contratado.cpf
        nome_contratado = ET.SubElement(contratado_elem, "nome")
        nome_contratado.text = guia.identificacao.contratado.nome
        cbo = ET.SubElement(contratado_elem, "cbo")
        cbo.text = guia.identificacao.contratado.cbo
        if guia.identificacao.contratado.crm:
            crm = ET.SubElement(contratado_elem, "crm")
            crm.text = guia.identificacao.contratado.crm
        
        # Data emissão e número da guia
        data_emissao = ET.SubElement(identificacao_elem, "dataEmissao")
        data_emissao.text = guia.identificacao.data_emissao
        numero_guia = ET.SubElement(identificacao_elem, "numeroGuia")
        numero_guia.text = guia.identificacao.numero_guia
        
        # Procedimentos
        procedimentos_elem = ET.SubElement(guia_elem, "procedimentos")
        
        for procedimento in guia.procedimentos.procedimentos:
            procedimento_elem = ET.SubElement(procedimentos_elem, "procedimento")
            
            codigo_tabela = ET.SubElement(procedimento_elem, "codigoTabela")
            codigo_tabela.text = procedimento.codigo_tabela
            codigo_procedimento = ET.SubElement(procedimento_elem, "codigoProcedimento")
            codigo_procedimento.text = procedimento.codigo_procedimento
            descricao_procedimento = ET.SubElement(procedimento_elem, "descricaoProcedimento")
            descricao_procedimento.text = procedimento.descricao_procedimento
            quantidade_executada = ET.SubElement(procedimento_elem, "quantidadeExecutada")
            quantidade_executada.text = str(procedimento.quantidade_executada)
            valor_unitario = ET.SubElement(procedimento_elem, "valorUnitario")
            valor_unitario.text = str(procedimento.valor_unitario)
            valor_total = ET.SubElement(procedimento_elem, "valorTotal")
            valor_total.text = str(procedimento.valor_total)
            data_execucao = ET.SubElement(procedimento_elem, "dataExecucao")
            data_execucao.text = procedimento.data_execucao
            if procedimento.hora_inicio:
                hora_inicio = ET.SubElement(procedimento_elem, "horaInicio")
                hora_inicio.text = procedimento.hora_inicio
            if procedimento.hora_fim:
                hora_fim = ET.SubElement(procedimento_elem, "horaFim")
                hora_fim.text = procedimento.hora_fim
        
        # Valor total da guia
        valor_total_guia = ET.SubElement(guia_elem, "valorTotalGuia")
        valor_total_guia.text = str(guia.valor_total_guia)
    
    # Convert to pretty XML
    rough_string = ET.tostring(root, encoding='utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8')
    
    return pretty_xml.decode('utf-8')


async def generate_batch_tiss_xml(invoice_ids: List[int], db: AsyncSession) -> bytes:
    """
    Generate TISS XML for multiple invoices and return as ZIP file
    
    Args:
        invoice_ids: List of invoice IDs to generate TISS XML for
        db: Database session
        
    Returns:
        ZIP file content as bytes
    """
    import zipfile
    import io
    
    # Create ZIP file in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for invoice_id in invoice_ids:
            try:
                # Generate TISS XML for each invoice
                xml_content = await generate_tiss_xml(invoice_id, db)
                
                # Add to ZIP file
                filename = f"tiss_invoice_{invoice_id:06d}.xml"
                zip_file.writestr(filename, xml_content)
                
            except Exception as e:
                # Add error file to ZIP
                error_content = f"Error generating TISS XML for invoice {invoice_id}: {str(e)}"
                error_filename = f"error_invoice_{invoice_id:06d}.txt"
                zip_file.writestr(error_filename, error_content)
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()
