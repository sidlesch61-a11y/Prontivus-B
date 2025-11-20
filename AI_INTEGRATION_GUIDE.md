# Guia de Integração de IA

Este documento descreve como usar a integração de IA no sistema Prontivus.

## Provedores Suportados

1. **OpenAI** - GPT-4, GPT-3.5 Turbo
2. **Azure OpenAI** - Compatível com OpenAI API
3. **Anthropic** - Claude 3 Opus, Sonnet, Haiku
4. **Google** - Gemini Pro, Gemini Pro Vision

## Configuração Inicial

### 1. Instalar Dependências

```bash
cd backend
pip install -r requirements.txt
```

Isso instalará:
- `openai` - Para OpenAI e Azure OpenAI
- `anthropic` - Para Anthropic Claude
- `google-generativeai` - Para Google Gemini

### 2. Configurar Chave de Criptografia

Certifique-se de que a variável de ambiente `ENCRYPTION_KEY` está configurada:

```bash
# Gerar uma chave (se ainda não tiver)
python generate_encryption_key.py

# Adicionar ao .env
ENCRYPTION_KEY=sua_chave_aqui
```

### 3. Habilitar IA para uma Clínica

1. Acesse `/super-admin/configuracoes/licenciamento`
2. Crie ou edite uma licença
3. Marque o módulo "ai" como ativo
4. Configure `ai_enabled = true` e `ai_token_limit` (ou -1 para ilimitado)

### 4. Configurar Provedor de IA

1. Acesse `/super-admin/integracoes/ia`
2. Selecione a clínica
3. Configure:
   - **Provedor**: OpenAI, Google, Anthropic ou Azure
   - **API Key**: Chave de API do provedor
   - **Modelo**: Modelo a ser usado (ex: gpt-4, claude-3-opus-20240229)
   - **Base URL**: (Apenas para Azure OpenAI ou endpoints customizados)
   - **Max Tokens**: Máximo de tokens por requisição
   - **Temperature**: Criatividade (0.0-1.0)
4. Habilite a IA
5. Teste a conexão

## Endpoints de Configuração

### Obter Configuração
```
GET /api/v1/ai-config?clinic_id={id}
```

### Atualizar Configuração
```
PUT /api/v1/ai-config?clinic_id={id}
Body: {
  "enabled": true,
  "provider": "openai",
  "api_key": "sk-...",
  "model": "gpt-4",
  "max_tokens": 2000,
  "temperature": 0.7
}
```

### Testar Conexão
```
POST /api/v1/ai-config/test-connection?clinic_id={id}
Body (opcional): {
  "provider": "openai",
  "api_key": "sk-...",
  "model": "gpt-4"
}
```

### Obter Estatísticas
```
GET /api/v1/ai-config/stats?clinic_id={id}
```

## Endpoints de Uso

### Análise Clínica
```
POST /api/v1/ai/analyze-clinical?clinic_id={id}
Body: {
  "clinical_data": {
    "symptoms": ["febre", "dor de cabeça"],
    "vital_signs": {
      "temperature": 38.5,
      "blood_pressure": "120/80"
    },
    "lab_results": {...}
  },
  "analysis_type": "general" // ou "diagnosis", "treatment", "risk"
}
```

### Sugestões de Diagnóstico
```
POST /api/v1/ai/suggest-diagnosis?clinic_id={id}
Body: {
  "symptoms": ["febre", "dor de cabeça", "náusea"],
  "patient_history": {
    "age": 35,
    "gender": "M",
    "previous_conditions": ["hipertensão"]
  }
}
```

### Sugestões de Tratamento
```
POST /api/v1/ai/suggest-treatment?clinic_id={id}
Body: {
  "diagnosis": "Gripe",
  "patient_data": {
    "allergies": ["penicilina"],
    "current_medications": ["aspirina"]
  }
}
```

### Chat Genérico
```
POST /api/v1/ai/chat?clinic_id={id}
Body: {
  "message": "Explique o que é hipertensão",
  "system_prompt": "Você é um assistente médico especializado.",
  "context": [
    {"role": "user", "content": "Olá"},
    {"role": "assistant", "content": "Olá! Como posso ajudar?"}
  ]
}
```

## Controle de Tokens

### Limites por Plano

- **Basic**: 10.000 tokens/mês
- **Standard**: 50.000 tokens/mês
- **Premium**: 200.000 tokens/mês
- **Enterprise**: Ilimitado (-1)

### Estatísticas Rastreadas

- `total_tokens` - Total acumulado
- `tokens_this_month` - Tokens usados no mês atual
- `requests_count` - Total de requisições
- `successful_requests` - Requisições bem-sucedidas
- `failed_requests` - Requisições falhadas
- `average_response_time_ms` - Tempo médio de resposta
- `documents_processed` - Documentos processados
- `suggestions_generated` - Sugestões geradas

### Reset Mensal

O contador `tokens_this_month` é resetado automaticamente no início de cada mês.

## Modelos Recomendados por Provedor

### OpenAI
- `gpt-4` - Melhor qualidade
- `gpt-4-turbo-preview` - Mais rápido
- `gpt-3.5-turbo` - Mais econômico

### Anthropic
- `claude-3-opus-20240229` - Melhor qualidade
- `claude-3-sonnet-20240229` - Balanceado
- `claude-3-haiku-20240307` - Mais rápido

### Google
- `gemini-pro` - Texto
- `gemini-pro-vision` - Texto + Imagens

### Azure OpenAI
- Use os mesmos modelos do OpenAI
- Configure `base_url` como: `https://{resource}.openai.azure.com/openai/deployments/{deployment}/chat/completions?api-version=2024-02-15-preview`

## Tratamento de Erros

### Erro: "AI is not enabled for this clinic"
- Habilite a IA na configuração da clínica

### Erro: "AI module is not enabled for this clinic's license"
- Ative o módulo "ai" na licença da clínica

### Erro: "Token limit exceeded"
- O limite mensal foi atingido
- Aguarde o reset mensal ou atualize o plano

### Erro: "API key is not configured"
- Configure a API key na configuração de IA

### Erro: "Connection test failed"
- Verifique se a API key está correta
- Verifique se o modelo está disponível para o provedor
- Para Azure OpenAI, verifique se o `base_url` está correto

## Exemplos de Uso

### Exemplo 1: Análise de Prontuário

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/ai/analyze-clinical",
    headers={"Authorization": "Bearer {token}"},
    json={
        "clinical_data": {
            "patient_age": 45,
            "symptoms": ["dor no peito", "falta de ar"],
            "vital_signs": {
                "blood_pressure": "140/90",
                "heart_rate": 95
            }
        },
        "analysis_type": "diagnosis"
    }
)

analysis = response.json()
print(analysis["analysis"])
```

### Exemplo 2: Sugestão de Diagnóstico

```python
response = requests.post(
    "http://localhost:8000/api/v1/ai/suggest-diagnosis",
    headers={"Authorization": "Bearer {token}"},
    json={
        "symptoms": ["febre", "dor de garganta", "tosse"],
        "patient_history": {
            "age": 30,
            "gender": "F"
        }
    }
)

suggestions = response.json()["suggestions"]
for suggestion in suggestions:
    print(f"{suggestion['diagnosis']} - {suggestion['confidence']}")
```

## Segurança

- **API Keys são criptografadas** usando Fernet (symmetric encryption)
- **Validação de limites** antes de cada requisição
- **Rastreamento de uso** para auditoria
- **Isolamento por clínica** - cada clínica tem sua própria configuração

## Troubleshooting

### Biblioteca não encontrada
```bash
pip install openai anthropic google-generativeai
```

### Erro de criptografia
- Verifique se `ENCRYPTION_KEY` está configurada
- Gere uma nova chave se necessário: `python generate_encryption_key.py`

### Google Gemini não funciona
- Certifique-se de que está usando `google-generativeai>=0.3.0`
- Verifique se a API key está correta
- Alguns modelos podem não estar disponíveis em todas as regiões

### Azure OpenAI não conecta
- Verifique o formato do `base_url`
- Certifique-se de que o deployment name está correto
- Verifique a versão da API no `base_url`

## Próximos Passos

1. Configure uma licença com módulo AI ativo
2. Configure o provedor de IA na página de integrações
3. Teste a conexão
4. Comece a usar os endpoints de análise e sugestões

