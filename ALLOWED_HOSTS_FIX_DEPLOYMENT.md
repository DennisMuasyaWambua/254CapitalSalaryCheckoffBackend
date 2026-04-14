# ALLOWED_HOSTS Fix - Deployment Guide

**Date:** April 14, 2026
**Issue:** Django ALLOWED_HOSTS misconfiguration causing 400 Bad Request
**Status:** FIXED - Ready for deployment

---

## Problem Identified

The `.env` file had incorrect ALLOWED_HOSTS configuration with URL protocols:

**Before (Incorrect):**
```env
ALLOWED_HOSTS=localhost,127.0.0.1,http://54.77.248.243,254-capital.com,www.254-capital.com,254-capital.vercel.app,https://api.254-capital.com
```

**After (Fixed):**
```env
ALLOWED_HOSTS=localhost,127.0.0.1,54.77.248.243,254-capital.com,www.254-capital.com,api.254-capital.com,254-capital.vercel.app
```

### What Changed
- Removed `http://` from `54.77.248.243`
- Removed `https://` from `api.254-capital.com`
- Django ALLOWED_HOSTS only accepts domain names/IPs without protocols

---

## Deployment Steps

### Option 1: Docker Deployment (Recommended)

If you're using Docker Compose on the production server:

```bash
# 1. SSH into production server
ssh user@54.77.248.243

# 2. Navigate to project directory
cd /opt/salary_checkoff

# 3. Pull latest code
git pull origin main

# 4. Update the .env file if needed
nano .env

# Ensure line 8 reads:
# ALLOWED_HOSTS=localhost,127.0.0.1,54.77.248.243,254-capital.com,www.254-capital.com,api.254-capital.com,254-capital.vercel.app

# 5. Restart the services
docker-compose down
docker-compose up -d

# 6. Check logs to verify
docker-compose logs -f web
```

### Option 2: Manual Deployment (If not using Docker)

```bash
# 1. SSH into production server
ssh user@54.77.248.243

# 2. Navigate to project directory
cd /opt/salary_checkoff

# 3. Pull latest code
git pull origin main

# 4. Update .env file
nano .env

# Ensure ALLOWED_HOSTS line is:
# ALLOWED_HOSTS=localhost,127.0.0.1,54.77.248.243,254-capital.com,www.254-capital.com,api.254-capital.com,254-capital.vercel.app

# 5. Restart Gunicorn
sudo systemctl restart gunicorn

# 6. Check status
sudo systemctl status gunicorn

# 7. Check logs
tail -f /var/log/gunicorn/error.log
```

### Option 3: Quick Fix Without Git Pull

If you just want to fix the .env file directly on the server:

```bash
# 1. SSH into server
ssh user@54.77.248.243

# 2. Navigate to project directory
cd /opt/salary_checkoff

# 3. Backup current .env
cp .env .env.backup

# 4. Edit .env file
nano .env

# 5. Find line 8 (ALLOWED_HOSTS) and change it to:
ALLOWED_HOSTS=localhost,127.0.0.1,54.77.248.243,254-capital.com,www.254-capital.com,api.254-capital.com,254-capital.vercel.app

# 6. Save and exit (Ctrl+X, then Y, then Enter)

# 7. Restart services
# For Docker:
docker-compose restart web

# For systemd:
sudo systemctl restart gunicorn
```

---

## Verification Steps

After deploying the fix, verify that the API is working:

### Test 1: Admin Login Endpoint

```bash
curl -X POST https://api.254-capital.com/api/v1/auth/admin/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"muasyathegreat4@gmail.com","password":"Muasya@2024"}'
```

**Expected Response (Success):**
```json
{
  "detail": "OTP sent to your registered phone number",
  "requires_otp": true,
  "temp_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "masked_phone": "0712****567",
  "expires_in": 300
}
```

**Should NOT get:** HTML with "Bad Request (400)"

### Test 2: Check from Frontend

1. Go to https://www.254-capital.com/salary-checkoff
2. Click "HR / Admin Login"
3. Enter:
   - Email: muasyathegreat4@gmail.com
   - Password: Muasya@2024
4. Should see OTP input screen (not a 400 error)

---

## Checking Logs

### Docker Logs
```bash
# Check web container logs
docker-compose logs -f web

# Check last 100 lines
docker-compose logs --tail=100 web
```

### Systemd Logs
```bash
# Gunicorn logs
sudo journalctl -u gunicorn -f

# Or file logs
tail -f /var/log/gunicorn/error.log
tail -f /opt/salary_checkoff/logs/django.log
```

### What to Look For
After restart, you should see:
```
[INFO] Starting gunicorn 20.1.0
[INFO] Listening at: http://0.0.0.0:8000
[INFO] Worker processes: 4
```

You should NOT see:
```
DisallowedHost at /api/v1/auth/admin/login/
Invalid HTTP_HOST header: 'api.254-capital.com'
```

---

## Rollback (If Something Goes Wrong)

If the deployment causes issues:

```bash
# Restore backup
cp .env.backup .env

# Restart services
docker-compose restart web
# OR
sudo systemctl restart gunicorn
```

---

## Files Changed

- `/home/dennis/Desktop/docs/business/254capital/salary_checkoff/backend/.env` (Line 8)

---

## Summary

| Issue | Status |
|-------|--------|
| ALLOWED_HOSTS had URL protocols | ✅ FIXED |
| Local .env file updated | ✅ DONE |
| Production deployment | ⏳ PENDING |

---

## Next Steps

1. **Deploy to Production** - Use one of the deployment options above
2. **Test the API** - Verify admin login works
3. **Monitor Logs** - Check for any errors
4. **Test from Frontend** - Ensure login flow works end-to-end

---

## Support

If the issue persists after deployment:

1. Check that the production server's `.env` file matches the fixed version
2. Verify Django is using the correct settings module: `config.settings.production`
3. Check nginx is properly forwarding the Host header
4. Review Django logs for detailed error messages

**Server Details:**
- IP: 54.77.248.243
- API URL: https://api.254-capital.com
- Expected deployment path: `/opt/salary_checkoff`
