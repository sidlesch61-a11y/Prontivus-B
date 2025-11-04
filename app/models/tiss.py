"""
TISS (Troca de Informação em Saúde Suplementar) XML Models
Based on ANS TISS 3.05.02 standard for health insurance billing
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, validator
from decimal import Decimal


class TISSDemoIdentificacaoPrestador(BaseModel):
    """Identificação do Prestador de Serviços"""
    cnpj: str = Field(..., max_length=14, description="CNPJ do prestador")
    nome: str = Field(..., max_length=100, description="Nome do prestador")
    codigo_prestador: Optional[str] = Field(None, max_length=20, description="Código do prestador na operadora")
    cnes: Optional[str] = Field(None, max_length=7, description="Código CNES do prestador")
    
    @validator('cnpj')
    def validate_cnpj(cls, v):
        # Remove formatting characters
        cnpj = v.replace('.', '').replace('/', '').replace('-', '')
        if not cnpj.isdigit() or len(cnpj) != 14:
            raise ValueError('CNPJ deve conter 14 dígitos')
        return cnpj


class TISSDemoIdentificacaoOperadora(BaseModel):
    """Identificação da Operadora"""
    cnpj: str = Field(..., max_length=14, description="CNPJ da operadora")
    nome: str = Field(..., max_length=100, description="Nome da operadora")
    registro_ans: str = Field(..., max_length=6, description="Registro ANS da operadora")
    
    @validator('cnpj')
    def validate_cnpj(cls, v):
        cnpj = v.replace('.', '').replace('/', '').replace('-', '')
        if not cnpj.isdigit() or len(cnpj) != 14:
            raise ValueError('CNPJ deve conter 14 dígitos')
        return cnpj
    
    @validator('registro_ans')
    def validate_registro_ans(cls, v):
        if not v.isdigit() or len(v) != 6:
            raise ValueError('Registro ANS deve conter 6 dígitos')
        return v


class TISSDemoIdentificacaoBeneficiario(BaseModel):
    """Identificação do Beneficiário"""
    numero_carteira: str = Field(..., max_length=20, description="Número da carteira do beneficiário")
    nome: str = Field(..., max_length=100, description="Nome do beneficiário")
    cpf: str = Field(..., max_length=11, description="CPF do beneficiário")
    data_nascimento: str = Field(..., description="Data de nascimento (YYYY-MM-DD)")
    sexo: str = Field(..., max_length=1, description="Sexo (M/F)")
    nome_plano: str = Field(..., max_length=100, description="Nome do plano")
    validade_carteira: Optional[str] = Field(None, description="Validade da carteira (YYYY-MM-DD)")
    
    @validator('cpf')
    def validate_cpf(cls, v):
        cpf = v.replace('.', '').replace('-', '')
        if not cpf.isdigit() or len(cpf) != 11:
            raise ValueError('CPF deve conter 11 dígitos')
        return cpf
    
    @validator('sexo')
    def validate_sexo(cls, v):
        if v.upper() not in ['M', 'F']:
            raise ValueError('Sexo deve ser M ou F')
        return v.upper()


class TISSDemoIdentificacaoContratado(BaseModel):
    """Identificação do Profissional Contratado"""
    cpf: str = Field(..., max_length=11, description="CPF do profissional")
    nome: str = Field(..., max_length=100, description="Nome do profissional")
    cbo: str = Field(..., max_length=4, description="Código CBO do profissional")
    crm: Optional[str] = Field(None, max_length=10, description="CRM do profissional (se médico)")
    conselho: Optional[str] = Field(None, max_length=10, description="Conselho profissional")
    uf_conselho: Optional[str] = Field(None, max_length=2, description="UF do conselho")
    
    @validator('cpf')
    def validate_cpf(cls, v):
        cpf = v.replace('.', '').replace('-', '')
        if not cpf.isdigit() or len(cpf) != 11:
            raise ValueError('CPF deve conter 11 dígitos')
        return cpf


class TISSDemoIdentificacao(BaseModel):
    """Bloco de Identificação (Demo)"""
    prestador: TISSDemoIdentificacaoPrestador
    operadora: TISSDemoIdentificacaoOperadora
    beneficiario: TISSDemoIdentificacaoBeneficiario
    contratado: TISSDemoIdentificacaoContratado
    data_emissao: str = Field(..., description="Data de emissão (YYYY-MM-DD)")
    numero_guia: str = Field(..., max_length=20, description="Número da guia")
    tipo_guia: str = Field(default="1", description="Tipo da guia (1=Consulta, 2=Internação, 3=SP/SADT)")
    data_autorizacao: Optional[str] = Field(None, description="Data de autorização (YYYY-MM-DD)")
    senha: Optional[str] = Field(None, max_length=20, description="Senha de autorização")
    numero_guia_origem: Optional[str] = Field(None, max_length=20, description="Número da guia de origem")


class TISSProcedimentoExecutado(BaseModel):
    """Procedimento Executado"""
    codigo_tabela: str = Field(..., max_length=2, description="Código da tabela (TUSS)")
    codigo_procedimento: str = Field(..., max_length=10, description="Código do procedimento")
    descricao_procedimento: str = Field(..., max_length=200, description="Descrição do procedimento")
    quantidade_executada: int = Field(..., ge=1, description="Quantidade executada")
    valor_unitario: Decimal = Field(..., ge=0, description="Valor unitário do procedimento")
    valor_total: Decimal = Field(..., ge=0, description="Valor total do procedimento")
    data_execucao: str = Field(..., description="Data de execução (YYYY-MM-DD)")
    hora_inicio: Optional[str] = Field(None, max_length=5, description="Hora de início (HH:MM)")
    hora_fim: Optional[str] = Field(None, max_length=5, description="Hora de fim (HH:MM)")
    tecnica_utilizada: Optional[str] = Field(None, max_length=200, description="Técnica utilizada")
    via_acesso: Optional[str] = Field(None, max_length=50, description="Via de acesso")
    tipo_atendimento: Optional[str] = Field(None, max_length=1, description="Tipo de atendimento")
    codigo_sequencial_item: Optional[str] = Field(None, max_length=3, description="Código sequencial do item")
    
    @validator('hora_inicio', 'hora_fim')
    def validate_time_format(cls, v):
        if v and not v.count(':') == 1:
            raise ValueError('Formato de hora deve ser HH:MM')
        return v


class TISSProcedimentos(BaseModel):
    """Bloco de Procedimentos"""
    procedimentos: List[TISSProcedimentoExecutado] = Field(..., min_items=1)


class TISSOdontoProcedimento(BaseModel):
    """Procedimento Odontológico"""
    codigo_tabela: str = Field(..., max_length=2, description="Código da tabela odontológica")
    codigo_procedimento: str = Field(..., max_length=10, description="Código do procedimento")
    descricao_procedimento: str = Field(..., max_length=200, description="Descrição do procedimento")
    quantidade_executada: int = Field(..., ge=1, description="Quantidade executada")
    valor_unitario: Decimal = Field(..., ge=0, description="Valor unitário")
    valor_total: Decimal = Field(..., ge=0, description="Valor total")
    data_execucao: str = Field(..., description="Data de execução (YYYY-MM-DD)")
    dente: Optional[str] = Field(None, max_length=2, description="Número do dente")
    face: Optional[str] = Field(None, max_length=1, description="Face do dente")
    arcada: Optional[str] = Field(None, max_length=1, description="Arcada dentária")


class TISSOdonto(BaseModel):
    """Bloco Odontológico"""
    procedimentos: List[TISSOdontoProcedimento] = Field(..., min_items=1)


class TISSSADTProcedimento(BaseModel):
    """Procedimento SADT (Serviços Auxiliares de Diagnóstico e Terapia)"""
    codigo_tabela: str = Field(..., max_length=2, description="Código da tabela SADT")
    codigo_procedimento: str = Field(..., max_length=10, description="Código do procedimento")
    descricao_procedimento: str = Field(..., max_length=200, description="Descrição do procedimento")
    quantidade_executada: int = Field(..., ge=1, description="Quantidade executada")
    valor_unitario: Decimal = Field(..., ge=0, description="Valor unitário")
    valor_total: Decimal = Field(..., ge=0, description="Valor total")
    data_execucao: str = Field(..., description="Data de execução (YYYY-MM-DD)")
    hora_inicio: Optional[str] = Field(None, max_length=5, description="Hora de início (HH:MM)")
    hora_fim: Optional[str] = Field(None, max_length=5, description="Hora de fim (HH:MM)")
    tipo_exame: Optional[str] = Field(None, max_length=50, description="Tipo de exame")
    local_execucao: Optional[str] = Field(None, max_length=100, description="Local de execução")


class TISSSADT(BaseModel):
    """Bloco SADT"""
    procedimentos: List[TISSSADTProcedimento] = Field(..., min_items=1)


class TISSGuia(BaseModel):
    """Estrutura de uma Guia TISS"""
    identificacao: TISSDemoIdentificacao
    procedimentos: Optional[TISSProcedimentos] = None
    odonto: Optional[TISSOdonto] = None
    sadt: Optional[TISSSADT] = None
    valor_total_guia: Decimal = Field(..., ge=0, description="Valor total da guia")
    observacao: Optional[str] = Field(None, max_length=500, description="Observações da guia")


class TISSLote(BaseModel):
    """Lote de Guias TISS"""
    numero_lote: str = Field(..., max_length=20, description="Número do lote")
    data_envio: str = Field(..., description="Data de envio (YYYY-MM-DD)")
    hora_envio: Optional[str] = Field(None, max_length=5, description="Hora de envio (HH:MM)")
    guias: List[TISSGuia] = Field(..., min_items=1)
    valor_total_lote: Optional[Decimal] = Field(None, ge=0, description="Valor total do lote")


class TISSDocumento(BaseModel):
    """Documento TISS completo"""
    versao_tiss: str = Field(default="3.05.02", description="Versão do padrão TISS")
    lote: TISSLote


# Mapping of our internal service categories to TUSS table codes
TUSS_TABLE_MAPPING = {
    "CONSULTATION": "01",  # Consultas
    "PROCEDURE": "02",     # Procedimentos
    "EXAM": "03",          # Exames
    "MEDICATION": "04",    # Medicamentos
    "ODONTO": "05",        # Odontologia
    "SADT": "06",          # SADT
    "OTHER": "99"          # Outros
}

# Common TUSS codes for our service items
TUSS_CODE_MAPPING = {
    # Consultas
    "10101012": "10101012",  # Consulta médica
    "10101013": "10101013",  # Consulta de retorno
    
    # Procedimentos
    "20101010": "20101010",  # Eletrocardiograma
    "20101011": "20101011",  # Ecocardiograma
    "30101010": "30101010",  # Curativo simples
    "30101020": "30101020",  # Aplicação de injeção
    
    # Exames
    "40301010": "40301010",  # Hemograma completo
    "40301011": "40301011",  # Glicemia de jejum
    "40301012": "40301012",  # Colesterol total
    
    # Odontologia
    "50101010": "50101010",  # Consulta odontológica
    "50101011": "50101011",  # Prophylaxis
    "50101012": "50101012",  # Restauração
    
    # SADT
    "60101010": "60101010",  # Ultrassonografia
    "60101011": "60101011",  # Radiografia
    "60101012": "60101012",  # Tomografia
}

# TISS validation rules
TISS_VALIDATION_RULES = {
    "max_procedures_per_guia": 50,
    "max_guias_per_lote": 1000,
    "max_value_per_guia": Decimal('999999.99'),
    "required_fields": [
        "prestador.cnpj",
        "prestador.nome",
        "operadora.cnpj",
        "operadora.nome",
        "operadora.registro_ans",
        "beneficiario.numero_carteira",
        "beneficiario.nome",
        "beneficiario.cpf",
        "beneficiario.data_nascimento",
        "beneficiario.sexo",
        "beneficiario.nome_plano",
        "contratado.cpf",
        "contratado.nome",
        "contratado.cbo"
    ]
}
