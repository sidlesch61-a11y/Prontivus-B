# 🚀 Guia Rápido: Como Usar a Integração de IA

## Passo 1: Instalar Dependências

```bash
cd backend
pip install -r requirements.txt
```

Isso instalará:
- `openai` - Para OpenAI e Azure OpenAI
- `anthropic` - Para Anthropic Claude  
- `google-generativeai` - Para Google Gemini

## Passo 2: Verificar Chave de Criptografia

Certifique-se de que `ENCRYPTION_KEY` está no seu `.env`:

```bash
# Se não tiver, gere uma:
python generate_encryption_key.py

# Adicione ao .env:
ENCRYPTION_KEY=sua_chave_gerada_aqui
```

## Passo 3: Criar/Editar Licença com Módulo AI

1. Acesse: `http://localhost:3000/super-admin/configuracoes/licenciamento`
2. Clique em "Criar Nova" ou edite uma licença existente
3. Configure:
   - **Clínica**: Selecione a clínica
   - **Plano**: Escolha um plano (Basic, Standard, Premium, Enterprise)
   - **Módulos**: Marque ✅ **"ai"** ou **"api"**
   - **AI Enabled**: Marque ✅
   - **AI Token Limit**: 
     - `10000` para Basic
     - `50000` para Standard
     - `200000` para Premium
     - `-1` para Enterprise (ilimitado)
4. Clique em "Salvar"

## Passo 4: Configurar Provedor de IA

1. Acesse: `http://localhost:3000/super-admin/integracoes/ia`
2. Selecione a **Clínica** no dropdown
3. Preencha os campos:

   **Para OpenAI:**
   - **Provedor**: `openai`
   - **API Key**: `sk-...` (sua chave OpenAI)
   - **Modelo**: `gpt-4` ou `gpt-3.5-turbo`
   - **Base URL**: (deixe vazio)
   - **Max Tokens**: `2000`
   - **Temperature**: `0.7`

   **Para Azure OpenAI:**
   - **Provedor**: `azure`
   - **API Key**: Sua chave Azure
   - **Modelo**: Nome do deployment (ex: `gpt-4`)
   - **Base URL**: `https://{resource}.openai.azure.com/openai/deployments/{deployment}/chat/completions?api-version=2024-02-15-preview`
   - **Max Tokens**: `2000`
   - **Temperature**: `0.7`

   **Para Anthropic Claude:**
   - **Provedor**: `anthropic`
   - **API Key**: `sk-ant-...` (sua chave Anthropic)
   - **Modelo**: `claude-3-opus-20240229` ou `claude-3-sonnet-20240229`
   - **Base URL**: (deixe vazio)
   - **Max Tokens**: `2000`
   - **Temperature**: `0.7`

   **Para Google Gemini:**
   - **Provedor**: `google`
   - **API Key**: Sua chave Google AI
   - **Modelo**: `gemini-pro`
   - **Base URL**: (deixe vazio)
   - **Max Tokens**: `2000`
   - **Temperature**: `0.7`

4. Marque ✅ **"Habilitar IA"**
5. Clique em **"Testar Conexão"** para verificar se está funcionando
6. Clique em **"Salvar Configuração"**

## Passo 5: Testar os Endpoints

### Exemplo 1: Análise Clínica

```bash
curl -X POST "http://localhost:8000/api/v1/ai/analyze-clinical" \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "clinical_data": {
      "symptoms": ["febre", "dor de cabeça"],
      "vital_signs": {
        "temperature": 38.5,
        "blood_pressure": "120/80"
      }
    },
    "analysis_type": "diagnosis"
  }'
```

### Exemplo 2: Sugestão de Diagnóstico

```bash
curl -X POST "http://localhost:8000/api/v1/ai/suggest-diagnosis" \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symptoms": ["febre", "dor de garganta", "tosse"],
    "patient_history": {
      "age": 30,
      "gender": "F"
    }
  }'
```

### Exemplo 3: Chat Genérico

```bash
curl -X POST "http://localhost:8000/api/v1/ai/chat" \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explique o que é hipertensão",
    "system_prompt": "Você é um assistente médico especializado."
  }'
```

## Passo 6: Verificar Estatísticas

Acesse: `http://localhost:3000/super-admin/integracoes/ia`

Na aba "Estatísticas", você verá:
- Tokens usados no mês
- Total de requisições
- Taxa de sucesso
- Tempo médio de resposta
- Documentos processados

## 🔍 Verificações Importantes

### ✅ Checklist

- [ ] Dependências instaladas (`pip install -r requirements.txt`)
- [ ] `ENCRYPTION_KEY` configurada no `.env`
- [ ] Licença criada com módulo "ai" ativo
- [ ] `ai_enabled = true` na licença
- [ ] `ai_token_limit` configurado na licença
- [ ] Provedor de IA configurado na página de integrações
- [ ] API key do provedor configurada
- [ ] Teste de conexão bem-sucedido
- [ ] IA habilitada na configuração

## 🐛 Problemas Comuns

### Erro: "AI module is not enabled"
**Solução**: Ative o módulo "ai" na licença da clínica

### Erro: "Token limit exceeded"
**Solução**: 
- Aguarde o reset mensal (automático no dia 1)
- Ou aumente o `ai_token_limit` na licença

### Erro: "Connection test failed"
**Solução**:
- Verifique se a API key está correta
- Verifique se o modelo está disponível para o provedor
- Para Azure, verifique o formato do `base_url`

### Erro: "API key is not configured"
**Solução**: Configure a API key na página de integrações de IA

## 📊 Modelos Recomendados

### OpenAI
- `gpt-4` - Melhor qualidade (mais caro)
- `gpt-4-turbo-preview` - Balanceado
- `gpt-3.5-turbo` - Mais econômico

### Anthropic
- `claude-3-opus-20240229` - Melhor qualidade
- `claude-3-sonnet-20240229` - Balanceado
- `claude-3-haiku-20240307` - Mais rápido

### Google
- `gemini-pro` - Texto
- `gemini-pro-vision` - Texto + Imagens

## 🎯 Próximos Passos

1. **Integrar no Frontend**: Crie componentes React para usar os endpoints
2. **Adicionar ao Prontuário**: Integre análise de IA nos prontuários médicos
3. **Dashboard de Uso**: Crie visualizações de uso de tokens
4. **Alertas**: Configure alertas quando o limite estiver próximo

## 📚 Documentação Completa

Para mais detalhes, consulte:
- `AI_INTEGRATION_GUIDE.md` - Guia completo
- `AI_INTEGRATION_SUMMARY.md` - Resumo da implementação

## ✨ Pronto!

Agora você pode usar a integração de IA no sistema! 🎉

