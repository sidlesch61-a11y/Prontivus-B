"""
TISS Validation Service
Validates TISS XML documents for compliance with ANS standards
"""

from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, date
import re

from app.models.tiss import (
    TISSDocumento, TISSGuia, TISSProcedimentoExecutado,
    TISSOdontoProcedimento, TISSSADTProcedimento,
    TISS_VALIDATION_RULES
)


class TISSValidationError(Exception):
    """Custom exception for TISS validation errors"""
    def __init__(self, message: str, field: str = None, code: str = None):
        self.message = message
        self.field = field
        self.code = code
        super().__init__(self.message)


class TISSValidator:
    """Validates TISS documents for compliance"""
    
    def __init__(self):
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
    
    def validate_document(self, tiss_doc: TISSDocumento) -> Dict[str, Any]:
        """
        Validate a complete TISS document
        
        Args:
            tiss_doc: TISS document to validate
            
        Returns:
            Validation result with errors and warnings
        """
        self.errors = []
        self.warnings = []
        
        # Validate document structure
        self._validate_document_structure(tiss_doc)
        
        # Validate lote
        self._validate_lote(tiss_doc.lote)
        
        # Validate each guia
        for i, guia in enumerate(tiss_doc.lote.guias):
            self._validate_guia(guia, i)
        
        return {
            "is_valid": len(self.errors) == 0,
            "errors": self.errors,
            "warnings": self.warnings,
            "total_errors": len(self.errors),
            "total_warnings": len(self.warnings)
        }
    
    def _validate_document_structure(self, tiss_doc: TISSDocumento):
        """Validate document structure"""
        if not tiss_doc.versao_tiss:
            self._add_error("Versão TISS é obrigatória", "versao_tiss")
        elif tiss_doc.versao_tiss not in ["3.05.02", "3.03.00"]:
            self._add_warning(f"Versão TISS {tiss_doc.versao_tiss} pode não ser suportada", "versao_tiss")
        
        if not tiss_doc.lote:
            self._add_error("Lote é obrigatório", "lote")
    
    def _validate_lote(self, lote):
        """Validate lote structure"""
        if not lote.numero_lote:
            self._add_error("Número do lote é obrigatório", "lote.numero_lote")
        elif len(lote.numero_lote) > 20:
            self._add_error("Número do lote deve ter no máximo 20 caracteres", "lote.numero_lote")
        
        if not lote.data_envio:
            self._add_error("Data de envio é obrigatória", "lote.data_envio")
        elif not self._validate_date_format(lote.data_envio):
            self._add_error("Data de envio deve estar no formato YYYY-MM-DD", "lote.data_envio")
        
        if lote.hora_envio and not self._validate_time_format(lote.hora_envio):
            self._add_error("Hora de envio deve estar no formato HH:MM", "lote.hora_envio")
        
        if not lote.guias:
            self._add_error("Lote deve conter pelo menos uma guia", "lote.guias")
        elif len(lote.guias) > TISS_VALIDATION_RULES["max_guias_per_lote"]:
            self._add_error(
                f"Lote deve conter no máximo {TISS_VALIDATION_RULES['max_guias_per_lote']} guias",
                "lote.guias"
            )
        
        # Validate total value
        if lote.valor_total_lote:
            total_calculated = sum(guia.valor_total_guia for guia in lote.guias)
            if abs(lote.valor_total_lote - total_calculated) > Decimal('0.01'):
                self._add_warning(
                    f"Valor total do lote ({lote.valor_total_lote}) não confere com soma das guias ({total_calculated})",
                    "lote.valor_total_lote"
                )
    
    def _validate_guia(self, guia: TISSGuia, guia_index: int):
        """Validate individual guia"""
        # Validate identificacao
        self._validate_identificacao(guia.identificacao, guia_index)
        
        # Validate procedures
        if guia.procedimentos:
            self._validate_procedimentos(guia.procedimentos, guia_index)
        
        if guia.odonto:
            self._validate_odonto(guia.odonto, guia_index)
        
        if guia.sadt:
            self._validate_sadt(guia.sadt, guia_index)
        
        # Validate guia total
        if guia.valor_total_guia > TISS_VALIDATION_RULES["max_value_per_guia"]:
            self._add_error(
                f"Valor total da guia excede o limite máximo de {TISS_VALIDATION_RULES['max_value_per_guia']}",
                f"guia_{guia_index}.valor_total_guia"
            )
    
    def _validate_identificacao(self, identificacao, guia_index: int):
        """Validate identificacao block"""
        # Validate prestador
        if not identificacao.prestador.cnpj:
            self._add_error("CNPJ do prestador é obrigatório", f"guia_{guia_index}.prestador.cnpj")
        elif not self._validate_cnpj(identificacao.prestador.cnpj):
            self._add_error("CNPJ do prestador inválido", f"guia_{guia_index}.prestador.cnpj")
        
        if not identificacao.prestador.nome:
            self._add_error("Nome do prestador é obrigatório", f"guia_{guia_index}.prestador.nome")
        
        # Validate operadora
        if not identificacao.operadora.cnpj:
            self._add_error("CNPJ da operadora é obrigatório", f"guia_{guia_index}.operadora.cnpj")
        elif not self._validate_cnpj(identificacao.operadora.cnpj):
            self._add_error("CNPJ da operadora inválido", f"guia_{guia_index}.operadora.cnpj")
        
        if not identificacao.operadora.nome:
            self._add_error("Nome da operadora é obrigatório", f"guia_{guia_index}.operadora.nome")
        
        if not identificacao.operadora.registro_ans:
            self._add_error("Registro ANS é obrigatório", f"guia_{guia_index}.operadora.registro_ans")
        elif not self._validate_ans_registration(identificacao.operadora.registro_ans):
            self._add_error("Registro ANS inválido", f"guia_{guia_index}.operadora.registro_ans")
        
        # Validate beneficiario
        if not identificacao.beneficiario.numero_carteira:
            self._add_error("Número da carteira é obrigatório", f"guia_{guia_index}.beneficiario.numero_carteira")
        
        if not identificacao.beneficiario.nome:
            self._add_error("Nome do beneficiário é obrigatório", f"guia_{guia_index}.beneficiario.nome")
        
        if not identificacao.beneficiario.cpf:
            self._add_error("CPF do beneficiário é obrigatório", f"guia_{guia_index}.beneficiario.cpf")
        elif not self._validate_cpf(identificacao.beneficiario.cpf):
            self._add_error("CPF do beneficiário inválido", f"guia_{guia_index}.beneficiario.cpf")
        
        if not identificacao.beneficiario.data_nascimento:
            self._add_error("Data de nascimento é obrigatória", f"guia_{guia_index}.beneficiario.data_nascimento")
        elif not self._validate_date_format(identificacao.beneficiario.data_nascimento):
            self._add_error("Data de nascimento deve estar no formato YYYY-MM-DD", f"guia_{guia_index}.beneficiario.data_nascimento")
        
        if not identificacao.beneficiario.sexo:
            self._add_error("Sexo é obrigatório", f"guia_{guia_index}.beneficiario.sexo")
        elif identificacao.beneficiario.sexo not in ['M', 'F']:
            self._add_error("Sexo deve ser M ou F", f"guia_{guia_index}.beneficiario.sexo")
        
        if not identificacao.beneficiario.nome_plano:
            self._add_error("Nome do plano é obrigatório", f"guia_{guia_index}.beneficiario.nome_plano")
        
        # Validate contratado
        if not identificacao.contratado.cpf:
            self._add_error("CPF do contratado é obrigatório", f"guia_{guia_index}.contratado.cpf")
        elif not self._validate_cpf(identificacao.contratado.cpf):
            self._add_error("CPF do contratado inválido", f"guia_{guia_index}.contratado.cpf")
        
        if not identificacao.contratado.nome:
            self._add_error("Nome do contratado é obrigatório", f"guia_{guia_index}.contratado.nome")
        
        if not identificacao.contratado.cbo:
            self._add_error("CBO é obrigatório", f"guia_{guia_index}.contratado.cbo")
        elif not self._validate_cbo(identificacao.contratado.cbo):
            self._add_error("CBO inválido", f"guia_{guia_index}.contratado.cbo")
        
        # Validate guia info
        if not identificacao.data_emissao:
            self._add_error("Data de emissão é obrigatória", f"guia_{guia_index}.data_emissao")
        elif not self._validate_date_format(identificacao.data_emissao):
            self._add_error("Data de emissão deve estar no formato YYYY-MM-DD", f"guia_{guia_index}.data_emissao")
        
        if not identificacao.numero_guia:
            self._add_error("Número da guia é obrigatório", f"guia_{guia_index}.numero_guia")
    
    def _validate_procedimentos(self, procedimentos, guia_index: int):
        """Validate procedimentos block"""
        if not procedimentos.procedimentos:
            self._add_error("Guia deve conter pelo menos um procedimento", f"guia_{guia_index}.procedimentos")
            return
        
        if len(procedimentos.procedimentos) > TISS_VALIDATION_RULES["max_procedures_per_guia"]:
            self._add_error(
                f"Guia deve conter no máximo {TISS_VALIDATION_RULES['max_procedures_per_guia']} procedimentos",
                f"guia_{guia_index}.procedimentos"
            )
        
        for i, procedimento in enumerate(procedimentos.procedimentos):
            self._validate_procedimento(procedimento, guia_index, i)
    
    def _validate_procedimento(self, procedimento: TISSProcedimentoExecutado, guia_index: int, proc_index: int):
        """Validate individual procedimento"""
        field_prefix = f"guia_{guia_index}.procedimentos[{proc_index}]"
        
        if not procedimento.codigo_tabela:
            self._add_error("Código da tabela é obrigatório", f"{field_prefix}.codigo_tabela")
        elif not self._validate_table_code(procedimento.codigo_tabela):
            self._add_error("Código da tabela inválido", f"{field_prefix}.codigo_tabela")
        
        if not procedimento.codigo_procedimento:
            self._add_error("Código do procedimento é obrigatório", f"{field_prefix}.codigo_procedimento")
        
        if not procedimento.descricao_procedimento:
            self._add_error("Descrição do procedimento é obrigatória", f"{field_prefix}.descricao_procedimento")
        
        if procedimento.quantidade_executada <= 0:
            self._add_error("Quantidade executada deve ser maior que zero", f"{field_prefix}.quantidade_executada")
        
        if procedimento.valor_unitario < 0:
            self._add_error("Valor unitário não pode ser negativo", f"{field_prefix}.valor_unitario")
        
        if procedimento.valor_total < 0:
            self._add_error("Valor total não pode ser negativo", f"{field_prefix}.valor_total")
        
        # Validate calculated total
        calculated_total = procedimento.quantidade_executada * procedimento.valor_unitario
        if abs(procedimento.valor_total - calculated_total) > Decimal('0.01'):
            self._add_warning(
                f"Valor total ({procedimento.valor_total}) não confere com quantidade × valor unitário ({calculated_total})",
                f"{field_prefix}.valor_total"
            )
        
        if not self._validate_date_format(procedimento.data_execucao):
            self._add_error("Data de execução deve estar no formato YYYY-MM-DD", f"{field_prefix}.data_execucao")
        
        if procedimento.hora_inicio and not self._validate_time_format(procedimento.hora_inicio):
            self._add_error("Hora de início deve estar no formato HH:MM", f"{field_prefix}.hora_inicio")
        
        if procedimento.hora_fim and not self._validate_time_format(procedimento.hora_fim):
            self._add_error("Hora de fim deve estar no formato HH:MM", f"{field_prefix}.hora_fim")
    
    def _validate_odonto(self, odonto, guia_index: int):
        """Validate odonto block"""
        if not odonto.procedimentos:
            self._add_error("Bloco odonto deve conter pelo menos um procedimento", f"guia_{guia_index}.odonto")
            return
        
        for i, procedimento in enumerate(odonto.procedimentos):
            self._validate_odonto_procedimento(procedimento, guia_index, i)
    
    def _validate_odonto_procedimento(self, procedimento: TISSOdontoProcedimento, guia_index: int, proc_index: int):
        """Validate individual odonto procedimento"""
        field_prefix = f"guia_{guia_index}.odonto.procedimentos[{proc_index}]"
        
        # Similar validation as regular procedimento
        if not procedimento.codigo_tabela:
            self._add_error("Código da tabela odontológica é obrigatório", f"{field_prefix}.codigo_tabela")
        elif procedimento.codigo_tabela != "05":
            self._add_warning("Código da tabela odontológica deve ser 05", f"{field_prefix}.codigo_tabela")
        
        # Validate dental-specific fields
        if procedimento.dente and not self._validate_tooth_number(procedimento.dente):
            self._add_error("Número do dente inválido", f"{field_prefix}.dente")
        
        if procedimento.face and not self._validate_tooth_face(procedimento.face):
            self._add_error("Face do dente inválida", f"{field_prefix}.face")
        
        if procedimento.arcada and not self._validate_arcada(procedimento.arcada):
            self._add_error("Arcada dentária inválida", f"{field_prefix}.arcada")
    
    def _validate_sadt(self, sadt, guia_index: int):
        """Validate SADT block"""
        if not sadt.procedimentos:
            self._add_error("Bloco SADT deve conter pelo menos um procedimento", f"guia_{guia_index}.sadt")
            return
        
        for i, procedimento in enumerate(sadt.procedimentos):
            self._validate_sadt_procedimento(procedimento, guia_index, i)
    
    def _validate_sadt_procedimento(self, procedimento: TISSSADTProcedimento, guia_index: int, proc_index: int):
        """Validate individual SADT procedimento"""
        field_prefix = f"guia_{guia_index}.sadt.procedimentos[{proc_index}]"
        
        # Similar validation as regular procedimento
        if not procedimento.codigo_tabela:
            self._add_error("Código da tabela SADT é obrigatório", f"{field_prefix}.codigo_tabela")
        elif procedimento.codigo_tabela != "06":
            self._add_warning("Código da tabela SADT deve ser 06", f"{field_prefix}.codigo_tabela")
    
    def _validate_cnpj(self, cnpj: str) -> bool:
        """Validate CNPJ format and check digits"""
        cnpj = re.sub(r'[^0-9]', '', cnpj)
        if len(cnpj) != 14:
            return False
        
        # Check if all digits are the same
        if cnpj == cnpj[0] * 14:
            return False
        
        # Validate check digits
        def calculate_check_digit(cnpj, weights):
            sum_val = sum(int(cnpj[i]) * weights[i] for i in range(len(weights)))
            remainder = sum_val % 11
            return 0 if remainder < 2 else 11 - remainder
        
        weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        
        check1 = calculate_check_digit(cnpj[:12], weights1)
        check2 = calculate_check_digit(cnpj[:13], weights2)
        
        return int(cnpj[12]) == check1 and int(cnpj[13]) == check2
    
    def _validate_cpf(self, cpf: str) -> bool:
        """Validate CPF format and check digits"""
        cpf = re.sub(r'[^0-9]', '', cpf)
        if len(cpf) != 11:
            return False
        
        # Check if all digits are the same
        if cpf == cpf[0] * 11:
            return False
        
        # Validate check digits
        def calculate_check_digit(cpf, weights):
            sum_val = sum(int(cpf[i]) * weights[i] for i in range(len(weights)))
            remainder = sum_val % 11
            return 0 if remainder < 2 else 11 - remainder
        
        weights1 = [10, 9, 8, 7, 6, 5, 4, 3, 2]
        weights2 = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]
        
        check1 = calculate_check_digit(cpf[:9], weights1)
        check2 = calculate_check_digit(cpf[:10], weights2)
        
        return int(cpf[9]) == check1 and int(cpf[10]) == check2
    
    def _validate_ans_registration(self, ans_reg: str) -> bool:
        """Validate ANS registration number"""
        return ans_reg.isdigit() and len(ans_reg) == 6
    
    def _validate_cbo(self, cbo: str) -> bool:
        """Validate CBO code"""
        return cbo.isdigit() and len(cbo) == 4
    
    def _validate_table_code(self, table_code: str) -> bool:
        """Validate TUSS table code"""
        valid_codes = ["01", "02", "03", "04", "05", "06", "99"]
        return table_code in valid_codes
    
    def _validate_date_format(self, date_str: str) -> bool:
        """Validate date format YYYY-MM-DD"""
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False
    
    def _validate_time_format(self, time_str: str) -> bool:
        """Validate time format HH:MM"""
        try:
            datetime.strptime(time_str, '%H:%M')
            return True
        except ValueError:
            return False
    
    def _validate_tooth_number(self, tooth: str) -> bool:
        """Validate tooth number (1-32)"""
        try:
            tooth_num = int(tooth)
            return 1 <= tooth_num <= 32
        except ValueError:
            return False
    
    def _validate_tooth_face(self, face: str) -> bool:
        """Validate tooth face (V, L, M, D, O)"""
        valid_faces = ['V', 'L', 'M', 'D', 'O']
        return face.upper() in valid_faces
    
    def _validate_arcada(self, arcada: str) -> bool:
        """Validate dental arch (S, I)"""
        valid_arcadas = ['S', 'I']
        return arcada.upper() in valid_arcadas
    
    def _add_error(self, message: str, field: str = None):
        """Add validation error"""
        self.errors.append({
            "message": message,
            "field": field,
            "type": "error"
        })
    
    def _add_warning(self, message: str, field: str = None):
        """Add validation warning"""
        self.warnings.append({
            "message": message,
            "field": field,
            "type": "warning"
        })


def validate_tiss_document(tiss_doc: TISSDocumento) -> Dict[str, Any]:
    """
    Convenience function to validate a TISS document
    
    Args:
        tiss_doc: TISS document to validate
        
    Returns:
        Validation result
    """
    validator = TISSValidator()
    return validator.validate_document(tiss_doc)
