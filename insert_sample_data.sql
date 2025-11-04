-- Insert sample service items
INSERT INTO service_items (name, description, code, price, category, is_active, clinic_id) VALUES
('Consulta Médica', 'Consulta de rotina com médico generalista', '10101012', 150.00, 'CONSULTATION', true, 1),
('Eletrocardiograma (ECG)', 'Exame para avaliar a atividade elétrica do coração', '20101010', 80.00, 'EXAM', true, 1),
('Hemograma Completo', 'Exame de sangue para avaliar componentes sanguíneos', '40301010', 45.00, 'EXAM', true, 1),
('Curativo Simples', 'Procedimento de troca de curativo', '30101010', 25.00, 'PROCEDURE', true, 1),
('Aplicação de Injeção', 'Administração de medicamento injetável', '30101020', 30.00, 'PROCEDURE', true, 1),
('Retorno de Consulta', 'Reavaliação após consulta inicial', NULL, 0.00, 'CONSULTATION', true, 1)
ON CONFLICT DO NOTHING;
