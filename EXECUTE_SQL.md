# Como Executar o SQL Manualmente

## Opções de Execução

### Opção 1: Usando psql (Linha de Comando)

```bash
# Conectar ao banco
psql -U postgres -d prontivus

# Executar o script
\i create_tiss_templates.sql
```

Ou em um único comando:
```bash
psql -U postgres -d prontivus -f create_tiss_templates.sql
```

### Opção 2: Usando pgAdmin

1. Abra o pgAdmin
2. Conecte-se ao seu servidor PostgreSQL
3. Selecione o banco de dados `prontivus` (ou seu banco)
4. Clique com botão direito no banco → **Query Tool**
5. Abra o arquivo `create_tiss_templates.sql`
6. Execute o script (F5 ou botão "Execute")

### Opção 3: Usando DBeaver ou outra ferramenta SQL

1. Conecte-se ao banco de dados
2. Abra o arquivo `create_tiss_templates.sql`
3. Execute o script completo

### Opção 4: Copiar e Colar no Terminal psql

1. Abra o terminal
2. Conecte-se: `psql -U postgres -d prontivus`
3. Copie todo o conteúdo do arquivo SQL
4. Cole no terminal e pressione Enter

## Verificação

Após executar, verifique se a tabela foi criada:

```sql
-- Verificar se a tabela existe
SELECT table_name 
FROM information_schema.tables 
WHERE table_name = 'tiss_templates';

-- Verificar estrutura da tabela
\d tiss_templates

-- Verificar se há templates
SELECT COUNT(*) FROM tiss_templates;
```

## Troubleshooting

### Erro: "type already exists"
- Normal, o script verifica se o tipo já existe antes de criar

### Erro: "relation already exists"
- A tabela já existe. Você pode:
  - Ignorar (a tabela já está criada)
  - Ou usar `DROP TABLE tiss_templates CASCADE;` antes de executar (cuidado: apaga dados!)

### Erro: "foreign key constraint"
- Verifique se as tabelas `clinics` e `users` existem
- Execute as migrations anteriores primeiro

## Próximos Passos

Após executar o SQL com sucesso:

1. ✅ A tabela `tiss_templates` estará criada
2. ✅ Os endpoints da API funcionarão
3. ✅ A página frontend poderá criar/editar templates
4. ✅ Teste a funcionalidade em `http://localhost:3000/financeiro/tiss-templates`

