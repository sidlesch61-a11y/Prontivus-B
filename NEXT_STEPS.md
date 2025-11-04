# Próximos Passos - Templates TISS

## ✅ Implementação Completa

A implementação dos templates TISS está completa no código. Todos os arquivos foram criados e configurados.

## 📋 Próximos Passos

### 1. Executar Migration (CRÍTICO)

**Problema:** A migration não pode ser executada automaticamente devido a problemas de conexão com o banco de dados.

**Solução:** Execute a migration quando o banco estiver disponível:

```bash
cd backend
python -m alembic upgrade head
```

**Alternativa:** Se a migration falhar, crie a tabela manualmente usando SQL:

```sql
CREATE TABLE tiss_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    category VARCHAR(50) NOT NULL CHECK (category IN ('consultation', 'procedure', 'exam', 'emergency', 'custom')),
    xml_template TEXT NOT NULL,
    variables JSONB,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    clinic_id INTEGER NOT NULL REFERENCES clinics(id),
    created_by_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX ix_tiss_templates_id ON tiss_templates(id);
CREATE INDEX ix_tiss_templates_name ON tiss_templates(name);
CREATE INDEX ix_tiss_templates_clinic_id ON tiss_templates(clinic_id);
```

### 2. Verificar Backend

- [ ] Verificar se o servidor está rodando: `netstat -ano | findstr :8000`
- [ ] Acessar API docs: http://localhost:8000/docs
- [ ] Verificar se o endpoint `/api/financial/templates` aparece na documentação
- [ ] Testar autenticação via API docs

### 3. Testar Endpoints

Via API docs (http://localhost:8000/docs):

1. **Login:**
   - Endpoint: `POST /api/auth/login`
   - Body: `{"username": "seu_usuario", "password": "sua_senha"}`
   - Copie o `access_token` retornado

2. **Criar Template:**
   - Endpoint: `POST /api/financial/templates`
   - Clique em "Authorize" e cole o token
   - Body de exemplo:
   ```json
   {
     "name": "Template de Teste",
     "description": "Template para testes",
     "category": "consultation",
     "xml_template": "<?xml version=\"1.0\"?><test>{{VARIABLE}}</test>",
     "is_default": false,
     "is_active": true
   }
   ```

3. **Listar Templates:**
   - Endpoint: `GET /api/financial/templates`
   - Deve retornar a lista de templates criados

### 4. Testar Frontend

1. Acesse: http://localhost:3000/financeiro/tiss-templates
2. Faça login no sistema
3. Teste as funcionalidades:
   - Criar novo template
   - Editar template existente
   - Excluir template
   - Duplicar template
   - Importar/Exportar templates
   - Buscar templates

### 5. Criar Templates Padrão (Opcional)

Crie um script de seed para popular templates padrão:

```python
# backend/seed_tiss_templates.py
from app.models import TissTemplate, TissTemplateCategory
from database import get_async_session
import asyncio

async def seed_default_templates():
    async for db in get_async_session():
        # Template de consulta padrão
        template = TissTemplate(
            clinic_id=1,  # Ajuste para o ID da sua clínica
            name="Consulta Médica Padrão",
            description="Template padrão para consultas médicas",
            category=TissTemplateCategory.CONSULTATION,
            xml_template="""<?xml version="1.0" encoding="UTF-8"?>
<ans:mensagemTISS xmlns:ans="http://www.ans.gov.br/padroes/tiss/schemas">
  <!-- Template padrão -->
</ans:mensagemTISS>""",
            is_default=True,
            is_active=True
        )
        db.add(template)
        await db.commit()

if __name__ == "__main__":
    asyncio.run(seed_default_templates())
```

## 🔍 Verificações de Problemas

### Erro 401 Unauthorized
- Verifique se está logado no frontend
- Verifique se o token está sendo salvo no localStorage
- Verifique se o token não expirou

### Erro 404 Not Found
- Verifique se o backend está rodando
- Verifique se o router foi registrado em `main.py`
- Verifique se o endpoint está correto: `/api/financial/templates`

### Erro de Banco de Dados
- Verifique se a tabela `tiss_templates` foi criada
- Verifique as credenciais do banco em `backend/config.py`
- Verifique se o PostgreSQL está rodando

## 📝 Arquivos Criados/Modificados

### Backend
- ✅ `backend/app/models/tiss_template.py` - Modelo
- ✅ `backend/app/schemas/tiss_template.py` - Schemas Pydantic
- ✅ `backend/app/api/endpoints/tiss_templates.py` - Endpoints
- ✅ `backend/alembic/versions/2025_01_30_add_tiss_templates_table.py` - Migration
- ✅ `backend/app/models/__init__.py` - Export do modelo
- ✅ `backend/app/api/endpoints/__init__.py` - Export dos endpoints
- ✅ `backend/main.py` - Router registrado

### Frontend
- ✅ `frontend/src/app/(dashboard)/financeiro/tiss-templates/page.tsx` - Página completa
- ✅ `frontend/src/lib/api.ts` - Melhorias no tratamento de erros

## 🎯 Status

- ✅ Código implementado
- ✅ Endpoints criados
- ✅ Frontend conectado
- ⏳ Migration pendente (aguardando banco de dados)
- ⏳ Testes pendentes

## 📞 Suporte

Se encontrar problemas:
1. Verifique os logs do backend
2. Verifique o console do navegador (F12)
3. Teste os endpoints via API docs primeiro
4. Verifique se a tabela foi criada no banco

