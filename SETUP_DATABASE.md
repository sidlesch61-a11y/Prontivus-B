# Database Setup Guide for CliniCore

## Step 1: Create PostgreSQL Database

### Option A: Using psql Command Line

```powershell
# Connect to PostgreSQL
psql -U postgres

# In the PostgreSQL prompt:
CREATE DATABASE clinicore;
CREATE USER clinicore_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE clinicore TO clinicore_user;
\q
```

### Option B: Using pgAdmin

1. Open pgAdmin
2. Right-click on "Databases" → "Create" → "Database"
3. Name: `clinicore`
4. Click "Save"

## Step 2: Update Environment Configuration

Edit `backend/.env` with your database credentials:

```env
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/clinicore
```

Replace `YOUR_PASSWORD` with your PostgreSQL password.

## Step 3: Run Migrations

```powershell
cd backend
.\venv\Scripts\Activate.ps1
alembic upgrade head
```

## Database Schema

After running migrations, the following tables will be created:

### Tables:
- **clinics** - Healthcare facilities
- **users** - System users (admin, secretary, doctor, patient roles)
- **patients** - Patient records with medical history
- **appointments** - Medical appointments with status tracking

### Relationships:
- Clinic → Users (one-to-many)
- Clinic → Patients (one-to-many)
- Clinic → Appointments (one-to-many)
- Patient → Appointments (one-to-many)
- User (Doctor) → Appointments (one-to-many)

## Troubleshooting

### Error: "database does not exist"
- Make sure you've created the database using Step 1

### Error: "connection refused"
- Ensure PostgreSQL service is running
- Check if PostgreSQL is listening on port 5432

### Error: "authentication failed"
- Verify your PostgreSQL password in `.env`
- Check pg_hba.conf for authentication settings

