# 🎯 Próximos Passos - Integração de IA

## ✅ Status Atual

A integração de IA foi **completamente implementada** e está pronta para uso!

## 📋 Checklist de Configuração

### 1. Verificar Instalação
```bash
cd backend
python check_ai_setup.py
```

Este script verifica:
- ✅ Versão do Python
- ✅ Dependências instaladas
- ✅ Chave de criptografia configurada
- ✅ Modelos do banco de dados
- ✅ Serviços importáveis
- ✅ Endpoints funcionando

### 2. Instalar Dependências (se necessário)
```bash
pip install -r requirements.txt
```

### 3. Configurar Chave de Criptografia (se necessário)
```bash
python generate_encryption_key.py
# Copie a chave e adicione ao .env:
# ENCRYPTION_KEY=sua_chave_aqui
```

## 🚀 Passos para Usar

### Passo 1: Configurar Licença

1. **Acesse**: `http://localhost:3000/super-admin/configuracoes/licenciamento`
2. **Crie ou edite** uma licença para a clínica
3. **Configure**:
   - ✅ Marque o módulo **"ai"** ou **"api"**
   - ✅ Configure `ai_enabled = true`
   - ✅ Configure `ai_token_limit`:
     - `10000` para Basic
     - `50000` para Standard
     - `200000` para Premium
     - `-1` para Enterprise (ilimitado)

### Passo 2: Configurar Provedor de IA

1. **Acesse**: `http://localhost:3000/super-admin/integracoes/ia`
2. **Selecione** a clínica no dropdown
3. **Preencha** os campos:
   - **Provedor**: `openai`, `google`, `anthropic` ou `azure`
   - **API Key**: Sua chave de API do provedor
   - **Modelo**: Modelo a ser usado
   - **Max Tokens**: `2000` (padrão)
   - **Temperature**: `0.7` (padrão)
4. **Marque** ✅ "Habilitar IA"
5. **Clique** em "Testar Conexão"
6. **Salve** a configuração

### Passo 3: Testar Endpoints

#### Análise Clínica
```bash
POST /api/v1/ai/analyze-clinical
Body: {
  "clinical_data": {
    "symptoms": ["febre", "dor de cabeça"],
    "vital_signs": {"temperature": 38.5}
  },
  "analysis_type": "diagnosis"
}
```

#### Sugestão de Diagnóstico
```bash
POST /api/v1/ai/suggest-diagnosis
Body: {
  "symptoms": ["febre", "dor de garganta"],
  "patient_history": {"age": 30, "gender": "F"}
}
```

#### Chat Genérico
```bash
POST /api/v1/ai/chat
Body: {
  "message": "Explique o que é hipertensão",
  "system_prompt": "Você é um assistente médico."
}
```

## 📊 Monitoramento

### Ver Estatísticas
- Acesse: `http://localhost:3000/super-admin/integracoes/ia`
- Aba "Estatísticas" mostra:
  - Tokens usados no mês
  - Total de requisições
  - Taxa de sucesso
  - Tempo médio de resposta

### Verificar Logs
- Tokens são atualizados automaticamente após cada uso
- Reset mensal acontece automaticamente no dia 1

## 🔧 Integração no Frontend

### Exemplo de Uso em React

```typescript
// Analisar dados clínicos
const analyzeClinical = async (clinicalData: any) => {
  const response = await fetch('/api/v1/ai/analyze-clinical', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      clinical_data: clinicalData,
      analysis_type: 'diagnosis'
    })
  });
  
  const result = await response.json();
  return result.analysis;
};

// Sugerir diagnóstico
const suggestDiagnosis = async (symptoms: string[]) => {
  const response = await fetch('/api/v1/ai/suggest-diagnosis', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      symptoms: symptoms
    })
  });
  
  const result = await response.json();
  return result.suggestions;
};
```

## 🎨 Ideias de Implementação

### 1. Componente de Análise de Prontuário
- Botão "Analisar com IA" no prontuário
- Exibe análise em tempo real
- Salva análise no histórico

### 2. Assistente de Diagnóstico
- Campo de sintomas
- Botão "Sugerir Diagnóstico"
- Lista de sugestões com confiança

### 3. Sugestões de Tratamento
- Após selecionar diagnóstico
- Botão "Sugerir Tratamentos"
- Lista de opções de tratamento

### 4. Chat Médico
- Interface de chat
- Histórico de conversas
- Integração com prontuário

## 📚 Documentação

- **`QUICK_START_AI.md`** - Guia rápido passo a passo
- **`AI_INTEGRATION_GUIDE.md`** - Documentação completa
- **`AI_INTEGRATION_SUMMARY.md`** - Resumo da implementação

## 🐛 Troubleshooting

### Problema: "AI module is not enabled"
**Solução**: Ative o módulo "ai" na licença

### Problema: "Token limit exceeded"
**Solução**: Aguarde reset mensal ou aumente o limite

### Problema: "Connection test failed"
**Solução**: Verifique API key e modelo

### Problema: Dependências não instaladas
**Solução**: `pip install -r requirements.txt`

## ✨ Pronto para Usar!

A integração está **100% funcional**. Siga os passos acima para começar a usar!

---

**Última atualização**: Implementação completa ✅

