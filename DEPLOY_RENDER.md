# Deploying Prontivus Backend to Render.com

This guide will help you deploy the Prontivus backend API to Render.com.

## Prerequisites

1. A Render.com account (sign up at https://render.com)
2. A PostgreSQL database (Render provides managed PostgreSQL databases)
3. Your frontend URL (for CORS configuration)

## Step 1: Create a PostgreSQL Database on Render

1. Go to your Render dashboard
2. Click "New +" → "PostgreSQL"
3. Configure:
   - **Name**: `prontivus-db` (or your preferred name)
   - **Database**: `prontivus_clinic` (or your preferred name)
   - **User**: Auto-generated (or custom)
   - **Region**: Choose closest to your users
   - **Plan**: Free tier available for testing
4. Click "Create Database"
5. **Save the connection string** - you'll need it later

## Step 2: Create a Web Service on Render

1. In Render dashboard, click "New +" → "Web Service"
2. Connect your Git repository (GitHub, GitLab, or Bitbucket)
3. Select the repository containing your backend code
4. Configure the service:

### Basic Settings

- **Name**: `prontivus-backend` (or your preferred name)
- **Region**: Same as your database
- **Branch**: `main` (or your default branch)
- **Root Directory**: `backend`
- **Environment**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Environment Variables

Add these environment variables in the Render dashboard:

#### Required Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@host:port/database
# Use the Internal Database URL from your Render PostgreSQL service

# Security (IMPORTANT: Generate a strong secret key!)
SECRET_KEY=your-super-secret-key-min-32-characters-long
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Environment
ENVIRONMENT=production
DEBUG=false

# CORS - Add your frontend URL(s), comma-separated
BACKEND_CORS_ORIGINS=https://your-frontend-domain.com,https://www.your-frontend-domain.com

# Server
PORT=10000
# Render automatically sets $PORT, but you can specify a default
```

#### Optional Variables

```bash
HOST=0.0.0.0
APP_NAME=Prontivus API
APP_VERSION=1.0.0
```

### Important Notes

1. **DATABASE_URL**: Use the **Internal Database URL** from your Render PostgreSQL service (not the external one)
   - Format: `postgresql+asyncpg://user:password@host:port/database`
   - The internal URL is faster and more secure

2. **SECRET_KEY**: Generate a strong secret key:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Or use: https://djecrety.ir/

3. **CORS Origins**: Add your production frontend URL(s)
   - Example: `https://prontivus.vercel.app,https://www.prontivus.com`
   - Separate multiple origins with commas

## Step 3: Deploy

1. Click "Create Web Service"
2. Render will:
   - Clone your repository
   - Install dependencies from `requirements.txt`
   - Start the service
3. Monitor the build logs for any errors

## Step 4: Run Database Migrations

After the service is deployed, you need to run Alembic migrations:

1. Go to your web service in Render
2. Click on "Shell" tab (or use the "Manual Deploy" → "Run Command")
3. Run:
   ```bash
   alembic upgrade head
   ```

Alternatively, you can add a build script to run migrations automatically (see below).

## Step 5: Verify Deployment

1. Check the service URL (Render provides: `https://your-service-name.onrender.com`)
2. Test the health endpoint:
   ```
   https://your-service-name.onrender.com/api/health
   ```
3. You should see a JSON response with status information

## Step 6: Update Frontend Configuration

Update your frontend's API URL:

1. In your frontend `.env` or `.env.production`:
   ```bash
   NEXT_PUBLIC_API_URL=https://your-service-name.onrender.com
   ```

2. Redeploy your frontend

## Optional: Automated Migration on Deploy

To automatically run migrations on each deploy, create a `render-build.sh` script:

```bash
#!/bin/bash
# render-build.sh
set -e

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Running database migrations..."
alembic upgrade head

echo "Build complete!"
```

Then update your Render build command:
```bash
chmod +x render-build.sh && ./render-build.sh
```

## Troubleshooting

### Service Won't Start

1. Check the logs in Render dashboard
2. Verify all environment variables are set
3. Check that `DATABASE_URL` is correct
4. Ensure `requirements.txt` is up to date

### Database Connection Errors

1. Verify you're using the **Internal Database URL**
2. Check that the database is running
3. Verify database credentials

### CORS Errors

1. Check `BACKEND_CORS_ORIGINS` includes your frontend URL
2. Ensure no trailing slashes in URLs
3. Check that HTTPS is used for production origins

### 502 Bad Gateway

1. Check service logs for errors
2. Verify the start command is correct
3. Check that the service is listening on `0.0.0.0:$PORT`

## Render Configuration File (Alternative)

If you prefer using `render.yaml`, you can use the provided `render.yaml` file in the backend directory.

To use it:
1. Go to Render dashboard
2. Click "New +" → "Blueprint"
3. Connect your repository
4. Render will automatically detect and use `render.yaml`

## Monitoring

Render provides:
- **Logs**: Real-time logs in the dashboard
- **Metrics**: CPU, memory, and request metrics
- **Alerts**: Set up alerts for downtime

## Security Checklist

- [ ] Strong `SECRET_KEY` generated and set
- [ ] `DEBUG=false` in production
- [ ] `ENVIRONMENT=production` set
- [ ] CORS origins limited to your frontend domains
- [ ] Database credentials secure (not in code)
- [ ] HTTPS enabled (automatic on Render)
- [ ] Database uses internal connection string

## Support

For Render-specific issues, check:
- Render Documentation: https://render.com/docs
- Render Status: https://status.render.com

For application issues, check your service logs in the Render dashboard.

