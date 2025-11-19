# Como Habilitar IA em uma Licença

## Opção 1: Via Interface Web (SuperAdmin)

1. Acesse: `http://localhost:3000/super-admin/configuracoes/licenciamento`
2. Clique em "Editar" na licença desejada
3. Na aba "Módulos", marque "AI" ou "API"
4. Os campos `ai_token_limit` e `ai_enabled` serão atualizados automaticamente baseado no plano

## Opção 2: Via API (SuperAdmin)

### Atualizar Licença Existente

```bash
PUT /api/v1/licenses/{license_id}
Authorization: Bearer {token}

{
  "modules": ["patients", "appointments", "ai"],
  "ai_enabled": true,
  "ai_token_limit": 100000  // ou null para usar limite do plano
}
```

### Criar Nova Licença com IA

```bash
POST /api/v1/licenses
Authorization: Bearer {token}

{
  "tenant_id": 1,
  "plan": "professional",
  "modules": ["patients", "appointments", "clinical", "ai"],
  "users_limit": 50,
  "start_at": "2025-01-01T00:00:00Z",
  "end_at": "2026-01-01T00:00:00Z",
  "ai_enabled": true,
  "ai_token_limit": 100000  // opcional: null = usa limite do plano
}
```

## Limites por Plano

- **BASIC**: 10.000 tokens/mês
- **PROFESSIONAL**: 100.000 tokens/mês
- **ENTERPRISE**: 1.000.000 tokens/mês
- **CUSTOM**: Ilimitado (-1) ou valor customizado

## Configurar IA para Clínica

Após habilitar o módulo na licença:

1. Acesse: `http://localhost:3000/super-admin/integracoes/ia`
2. Selecione a clínica
3. Configure:
   - Provedor (OpenAI, Google, Anthropic, Azure)
   - API Key (será criptografada)
   - Modelo
   - Recursos habilitados

## Verificar Status

```bash
GET /api/v1/ai-config?clinic_id=1
Authorization: Bearer {token}

Resposta inclui:
- token_limit: Limite mensal
- tokens_remaining: Tokens restantes
- usage_stats: Estatísticas de uso
```

