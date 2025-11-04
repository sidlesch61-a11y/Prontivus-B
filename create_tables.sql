-- Create service_items table
CREATE TABLE IF NOT EXISTS service_items (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    code VARCHAR(50),
    price NUMERIC(10, 2) NOT NULL,
    category VARCHAR(20) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    clinic_id INTEGER NOT NULL REFERENCES clinics(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create invoices table
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    appointment_id INTEGER REFERENCES appointments(id),
    clinic_id INTEGER NOT NULL REFERENCES clinics(id),
    issue_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    due_date TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    total_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create invoice_lines table
CREATE TABLE IF NOT EXISTS invoice_lines (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    service_item_id INTEGER NOT NULL REFERENCES service_items(id),
    quantity NUMERIC(8, 2) NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    line_total NUMERIC(10, 2) NOT NULL,
    description VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS ix_service_items_id ON service_items(id);
CREATE INDEX IF NOT EXISTS ix_service_items_name ON service_items(name);
CREATE INDEX IF NOT EXISTS ix_service_items_code ON service_items(code);
CREATE INDEX IF NOT EXISTS ix_invoices_id ON invoices(id);
CREATE INDEX IF NOT EXISTS ix_invoices_patient_id ON invoices(patient_id);
CREATE INDEX IF NOT EXISTS ix_invoices_appointment_id ON invoices(appointment_id);
CREATE INDEX IF NOT EXISTS ix_invoices_clinic_id ON invoices(clinic_id);
CREATE INDEX IF NOT EXISTS ix_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS ix_invoice_lines_id ON invoice_lines(id);
CREATE INDEX IF NOT EXISTS ix_invoice_lines_invoice_id ON invoice_lines(invoice_id);
CREATE INDEX IF NOT EXISTS ix_invoice_lines_service_item_id ON invoice_lines(service_item_id);
