# CliniCore Backend

FastAPI backend for the CliniCore Healthcare Management System.

## Features

- **FastAPI** - Modern, fast web framework for building APIs
- **SQLAlchemy** - Async ORM for database operations
- **PostgreSQL** - Database with async support (asyncpg)
- **Alembic** - Database migrations
- **Pydantic** - Data validation
- **JWT Authentication** - Secure token-based auth

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+

### Installation

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your database credentials and secret key
```

4. Create the database:
```bash
# Connect to PostgreSQL and create database
psql -U postgres
CREATE DATABASE clinicore;
\q
```

5. Run migrations:
```bash
alembic upgrade head
```

### Running the Server

Development mode with auto-reload:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Or using Python:
```bash
python main.py
```

The API will be available at http://localhost:8000

### API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Database Migrations

Create a new migration:
```bash
alembic revision --autogenerate -m "description of changes"
```

Apply migrations:
```bash
alembic upgrade head
```

Rollback migration:
```bash
alembic downgrade -1
```

## Project Structure

```
backend/
├── alembic/            # Database migrations
├── main.py             # FastAPI application entry point
├── database.py         # Database connection and session
├── models.py           # SQLAlchemy models
├── config.py           # Application configuration
├── requirements.txt    # Python dependencies
└── .env.example        # Environment variables template
```

## Development

### Code Style

This project follows PEP 8 guidelines. Consider using:
- `black` for code formatting
- `flake8` for linting
- `mypy` for type checking

### Testing

(To be implemented)
```bash
pytest
```

