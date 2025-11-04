-- =====================================================
-- Script SQL para criar a tabela tiss_templates
-- Execute este script no seu banco de dados PostgreSQL
-- =====================================================

-- Passo 1: Criar o tipo ENUM para categorias
-- (Ignora erro se já existir)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tisstemplatecategory') THEN
        CREATE TYPE tisstemplatecategory AS ENUM (
            'consultation',
            'procedure',
            'exam',
            'emergency',
            'custom'
        );
    END IF;
END $$;

-- Passo 2: Criar a tabela tiss_templates
CREATE TABLE IF NOT EXISTS tiss_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    category tisstemplatecategory NOT NULL DEFAULT 'custom',
    xml_template TEXT NOT NULL,
    variables JSONB,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    clinic_id INTEGER NOT NULL,
    created_by_id INTEGER,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    
    -- Foreign Keys
    CONSTRAINT fk_tiss_templates_clinic 
        FOREIGN KEY (clinic_id) 
        REFERENCES clinics(id) 
        ON DELETE CASCADE,
    
    CONSTRAINT fk_tiss_templates_created_by 
        FOREIGN KEY (created_by_id) 
        REFERENCES users(id) 
        ON DELETE SET NULL
);

-- Passo 3: Criar índices para melhor performance
CREATE INDEX IF NOT EXISTS ix_tiss_templates_id 
    ON tiss_templates(id);

CREATE INDEX IF NOT EXISTS ix_tiss_templates_name 
    ON tiss_templates(name);

CREATE INDEX IF NOT EXISTS ix_tiss_templates_clinic_id 
    ON tiss_templates(clinic_id);

CREATE INDEX IF NOT EXISTS ix_tiss_templates_category 
    ON tiss_templates(category);

CREATE INDEX IF NOT EXISTS ix_tiss_templates_is_active 
    ON tiss_templates(is_active);

-- Passo 4: Comentários para documentação
COMMENT ON TABLE tiss_templates IS 'Templates XML para geração de documentos TISS';
COMMENT ON COLUMN tiss_templates.name IS 'Nome do template';
COMMENT ON COLUMN tiss_templates.description IS 'Descrição do template';
COMMENT ON COLUMN tiss_templates.category IS 'Categoria do template (consultation, procedure, exam, emergency, custom)';
COMMENT ON COLUMN tiss_templates.xml_template IS 'Template XML com variáveis no formato {{VARIABLE_NAME}}';
COMMENT ON COLUMN tiss_templates.variables IS 'Lista JSON de variáveis encontradas no template';
COMMENT ON COLUMN tiss_templates.is_default IS 'Indica se é um template padrão do sistema';
COMMENT ON COLUMN tiss_templates.is_active IS 'Indica se o template está ativo';
COMMENT ON COLUMN tiss_templates.clinic_id IS 'ID da clínica proprietária do template';
COMMENT ON COLUMN tiss_templates.created_by_id IS 'ID do usuário que criou o template';

-- =====================================================
-- Verificação: Verificar se a tabela foi criada
-- =====================================================
SELECT 
    'Tabela criada com sucesso!' AS status,
    COUNT(*) AS total_templates
FROM tiss_templates;

-- =====================================================
-- Opcional: Inserir template de exemplo
-- =====================================================
-- Descomente as linhas abaixo para inserir um template de exemplo
/*
INSERT INTO tiss_templates (
    name,
    description,
    category,
    xml_template,
    variables,
    clinic_id,
    is_default,
    is_active
) VALUES (
    'Consulta Médica Padrão',
    'Template padrão para consultas médicas',
    'consultation',
    '<?xml version="1.0" encoding="UTF-8"?>
<ans:mensagemTISS xmlns:ans="http://www.ans.gov.br/padroes/tiss/schemas">
  <ans:cabecalho>
    <ans:identificacaoTransacao>
      <ans:tipoTransacao>ENVIO_LOTE_GUIAS</ans:tipoTransacao>
      <ans:sequencialTransacao>{{SEQUENTIAL}}</ans:sequencialTransacao>
      <ans:dataRegistroTransacao>{{DATE}}</ans:dataRegistroTransacao>
      <ans:horaRegistroTransacao>{{TIME}}</ans:horaRegistroTransacao>
    </ans:identificacaoTransacao>
  </ans:cabecalho>
</ans:mensagemTISS>',
    '["SEQUENTIAL", "DATE", "TIME"]'::jsonb,
    1, -- Ajuste para o ID da sua clínica
    true,
    true
) ON CONFLICT DO NOTHING;
*/

-- =====================================================
-- Fim do script
-- =====================================================

