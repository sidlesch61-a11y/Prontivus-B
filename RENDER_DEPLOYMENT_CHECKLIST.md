# Render.com Deployment Checklist

## Pre-Deployment Steps

### 1. Generate Secret Key
```bash
cd backend
python generate_secret_key.py
```
Copy the generated key - you'll need it for the SECRET_KEY environment variable.

### 2. Verify Requirements
- [ ] All dependencies are in `requirements.txt`
- [ ] Python version is specified (3.12 recommended)
- [ ] No hardcoded credentials in code

### 3. Database Setup
- [ ] Create PostgreSQL database on Render
- [ ] Save the **Internal Database URL** (not external)
- [ ] Format: `postgresql+asyncpg://user:password@host:port/database`

### 4. Environment Variables Checklist
Prepare these values before deploying:

- [ ] `DATABASE_URL` - Internal PostgreSQL connection string
- [ ] `SECRET_KEY` - Strong secret key (32+ characters)
- [ ] `ALGORITHM` - `HS256`
- [ ] `ACCESS_TOKEN_EXPIRE_MINUTES` - `30`
- [ ] `REFRESH_TOKEN_EXPIRE_DAYS` - `7`
- [ ] `ENVIRONMENT` - `production`
- [ ] `DEBUG` - `false`
- [ ] `BACKEND_CORS_ORIGINS` - Your frontend URL(s), comma-separated
  - Example: `https://prontivus.vercel.app,https://www.prontivus.com`

## Deployment Steps

### Option 1: Using Render Dashboard (Recommended)

1. **Create PostgreSQL Database**
   - Go to Render Dashboard
   - Click "New +" → "PostgreSQL"
   - Configure and create
   - Copy **Internal Database URL**

2. **Create Web Service**
   - Click "New +" → "Web Service"
   - Connect your Git repository
   - Select repository and branch
   - Configure:
     - **Name**: `prontivus-backend`
     - **Root Directory**: `backend`
     - **Environment**: `Python 3`
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

3. **Set Environment Variables**
   - In the service settings, go to "Environment"
   - Add all variables from the checklist above
   - **Important**: Use Internal Database URL for `DATABASE_URL`

4. **Deploy**
   - Click "Create Web Service"
   - Monitor build logs

5. **Run Migrations**
   - After deployment, go to "Shell" tab
   - Run: `alembic upgrade head`

### Option 2: Using render.yaml (Blueprint)

1. Push `render.yaml` to your repository
2. Go to Render Dashboard
3. Click "New +" → "Blueprint"
4. Connect repository
5. Render will auto-detect and use `render.yaml`
6. Update environment variables as needed
7. Deploy

## Post-Deployment Verification

### 1. Test Health Endpoint
```bash
curl https://your-service-name.onrender.com/api/health
```
Expected response:
```json
{
  "status": "healthy",
  "service": "Prontivus API",
  "version": "1.0.0"
}
```

### 2. Test Database Connection
- Check service logs for database connection errors
- Verify migrations ran successfully

### 3. Test CORS
- Try accessing API from your frontend
- Check browser console for CORS errors
- Verify `BACKEND_CORS_ORIGINS` includes your frontend URL

### 4. Update Frontend
- Update `NEXT_PUBLIC_API_URL` to your Render service URL
- Redeploy frontend

## Common Issues & Solutions

### Issue: Service won't start
**Solution**: 
- Check logs for errors
- Verify all environment variables are set
- Check Python version compatibility

### Issue: Database connection errors
**Solution**:
- Verify using **Internal Database URL** (not external)
- Check database is running
- Verify credentials are correct

### Issue: CORS errors
**Solution**:
- Check `BACKEND_CORS_ORIGINS` includes your frontend URL
- No trailing slashes in URLs
- Use HTTPS for production origins

### Issue: 502 Bad Gateway
**Solution**:
- Check service logs
- Verify start command is correct
- Check service is listening on `0.0.0.0:$PORT`

### Issue: Migrations not running
**Solution**:
- Manually run: `alembic upgrade head` in Shell
- Or add to build script (see `render-build.sh`)

## Security Checklist

- [ ] Strong `SECRET_KEY` set (32+ characters)
- [ ] `DEBUG=false` in production
- [ ] `ENVIRONMENT=production` set
- [ ] CORS origins limited to your domains
- [ ] Database credentials secure
- [ ] No secrets in code or logs
- [ ] HTTPS enabled (automatic on Render)

## Monitoring

- **Logs**: Available in Render dashboard
- **Metrics**: CPU, memory, request metrics
- **Alerts**: Set up in Render dashboard

## Quick Reference

### Service URL Format
```
https://prontivus-backend.onrender.com
```

### Health Check
```
GET https://your-service-name.onrender.com/api/health
```

### Database Connection String Format
```
postgresql+asyncpg://user:password@host:port/database
```

### Generate Secret Key
```bash
python backend/generate_secret_key.py
```

## Next Steps After Deployment

1. ✅ Update frontend API URL
2. ✅ Test all API endpoints
3. ✅ Verify authentication works
4. ✅ Check database migrations
5. ✅ Set up monitoring/alerts
6. ✅ Configure custom domain (optional)

## Support

- Render Docs: https://render.com/docs
- Render Status: https://status.render.com
- Check service logs in Render dashboard

