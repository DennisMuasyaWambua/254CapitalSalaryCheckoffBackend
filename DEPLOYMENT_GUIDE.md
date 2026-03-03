# Deployment Guide - OTP Login Implementation

## Overview
This guide explains how to deploy the updated 254 Capital Salary Check-Off system with OTP authentication using Wasiliana SMS gateway.

## Changes Made

### 1. Wasiliana SMS Integration
- **New Module**: `apps/notifications/wasiliana_sms.py`
- **Updated Module**: `apps/notifications/sms.py` (now uses Wasiliana instead of Africa's Talking)
- **Package Added**: `pytek-wasiliana==1.2` in `requirements.txt`

### 2. OTP Login Flow for HR/Admin
- **New Serializer**: `VerifyLoginOTPSerializer` in `apps/accounts/serializers.py`
- **Updated Views**:
  - `HRLoginView` - Now sends OTP after credentials verification
  - `AdminLoginView` - Now sends OTP after credentials verification
  - `VerifyLoginOTPView` - New endpoint to verify OTP and complete login
- **New Route**: `/api/v1/auth/verify-login-otp/`

### 3. Configuration
- **New Settings**: `WASILIANA_API_KEY` and `WASILIANA_SENDER_ID` in `config/settings/base.py`
- **Environment Variables**: Added to `.env.example`

---

## Deployment Steps

### Option 1: Deploy to Existing Production Server

#### Step 1: Update Code on Server
```bash
# SSH into your server
ssh your-server

# Navigate to project directory
cd /path/to/salary_checkoff/backend

# Pull latest changes
git pull origin main

# Or if using manual upload, upload the updated files
```

#### Step 2: Install New Dependencies
```bash
# Activate virtual environment
source venv/bin/activate  # or source /path/to/venv/bin/activate

# Install new package
pip install pytek-wasiliana==1.2

# Or reinstall all requirements
pip install -r requirements.txt
```

#### Step 3: Update Environment Variables
```bash
# Edit your production .env file
nano .env  # or vim .env

# Add these lines:
WASILIANA_API_KEY=cLASQNLUPha4ryxweSJI2jKqNhyZrUs2HPnLDhDahs5eYufyTpOucPCjAtHckRfk
WASILIANA_SENDER_ID=254-CAPITAL
```

#### Step 4: Run Database Migrations (if any)
```bash
python manage.py migrate
```

#### Step 5: Collect Static Files
```bash
python manage.py collectstatic --noinput
```

#### Step 6: Restart Services
```bash
# If using systemd
sudo systemctl restart gunicorn
sudo systemctl restart celery-worker
sudo systemctl restart celery-beat

# If using supervisor
sudo supervisorctl restart all

# If using Docker
docker-compose restart web celery_worker celery_beat
```

#### Step 7: Verify Deployment
```bash
# Check if services are running
sudo systemctl status gunicorn
sudo systemctl status celery-worker

# Test the API
curl -X POST https://your-domain.com/api/v1/auth/hr/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "testpass"}'
```

---

### Option 2: Deploy Using Docker

#### Step 1: Build New Docker Image
```bash
# In your local machine, build and push new image
docker build -t your-dockerhub-username/salary-checkoff-backend:latest .
docker push your-dockerhub-username/salary-checkoff-backend:latest
```

#### Step 2: Update Server
```bash
# SSH into server
ssh your-server

cd /path/to/project

# Pull new image
docker-compose pull

# Restart containers
docker-compose down
docker-compose up -d

# Check logs
docker-compose logs -f web
```

---

### Option 3: Use Existing Deployed Server for Testing

If your server is already running at `https://254-capital.vercel.app` or another domain:

1. **Commit and Push Changes**:
```bash
git add .
git commit -m "Implement OTP login flow with Wasiliana SMS"
git push origin main
```

2. **Trigger Deployment** (depends on your CI/CD setup):
   - If using GitHub Actions, it should auto-deploy
   - If using manual deployment, follow Option 1 steps above
   - If using Vercel/Railway/Render, trigger a redeploy from their dashboard

3. **Configure Environment Variables** in your hosting platform:
   - Go to your hosting dashboard (Vercel/Railway/Render/DigitalOcean)
   - Add environment variables:
     - `WASILIANA_API_KEY=cLASQNLUPha4ryxweSJI2jKqNhyZrUs2HPnLDhDahs5eYufyTpOucPCjAtHckRfk`
     - `WASILIANA_SENDER_ID=254-CAPITAL`

---

## Testing the OTP Login Flow

Once deployed, you can test using these curl commands or Postman:

### 1. Test Employee OTP Login

**Step 1: Send OTP**
```bash
curl -X POST https://your-domain.com/api/v1/auth/otp/send/ \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+254712345678"}'

# Expected Response:
# {
#   "detail": "OTP sent successfully",
#   "masked_phone": "071***678",
#   "expires_in": 300
# }
```

**Step 2: Verify OTP** (Use the OTP received via SMS)
```bash
curl -X POST https://your-domain.com/api/v1/auth/otp/verify/ \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+254712345678",
    "otp": "123456"
  }'

# Expected Response:
# {
#   "detail": "Login successful",
#   "is_new_user": false,
#   "tokens": {
#     "refresh": "...",
#     "access": "..."
#   },
#   "user": {...}
# }
```

### 2. Test HR Manager OTP Login

**Step 1: Login with Email/Password**
```bash
curl -X POST https://your-domain.com/api/v1/auth/hr/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "hr@company.com",
    "password": "HRPassword123"
  }'

# Expected Response:
# {
#   "detail": "OTP sent to your phone. Please verify to complete login.",
#   "requires_otp": true,
#   "temp_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
#   "masked_phone": "072***789",
#   "expires_in": 300
# }
```

**Step 2: Verify OTP** (Use the OTP received via SMS)
```bash
curl -X POST https://your-domain.com/api/v1/auth/verify-login-otp/ \
  -H "Content-Type: application/json" \
  -d '{
    "temp_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "otp": "654321"
  }'

# Expected Response:
# {
#   "detail": "Login successful",
#   "tokens": {
#     "refresh": "...",
#     "access": "..."
#   },
#   "user": {...}
# }
```

### 3. Test Admin OTP Login

Same as HR Manager login but use `/api/v1/auth/admin/login/` endpoint.

---

## API Endpoints Summary

### New/Updated Endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/otp/send/` | Send OTP to phone (Employee) |
| POST | `/api/v1/auth/otp/verify/` | Verify OTP for Employee login |
| POST | `/api/v1/auth/hr/login/` | HR login with email/password (sends OTP) |
| POST | `/api/v1/auth/admin/login/` | Admin login with email/password (sends OTP) |
| POST | `/api/v1/auth/verify-login-otp/` | Verify OTP for HR/Admin login (NEW) |

---

## Troubleshooting

### Issue: SMS not being sent

**Check:**
1. Wasiliana API credentials are correct in `.env`
2. Celery worker is running: `sudo systemctl status celery-worker`
3. Redis is running: `redis-cli ping`
4. Check Celery logs: `tail -f /var/log/celery/worker.log`

**Test SMS directly:**
```bash
source venv/bin/activate
python test_wasiliana_sms.py 254712345678
```

### Issue: OTP verification fails

**Check:**
1. Redis is running and accessible
2. OTP hasn't expired (5 minutes default)
3. Check Redis for OTP: `redis-cli KEYS "*otp*"`
4. OTP attempts not exceeded (5 attempts max)

### Issue: CORS errors from frontend

**Fix:**
Ensure `.env` has correct CORS origins:
```bash
CORS_ALLOWED_ORIGINS=https://254-capital.vercel.app,http://localhost:3000
```

Note: No trailing slashes!

### Issue: Database connection errors

**Check:**
1. Database service is running
2. `DATABASE_URL` in `.env` is correct
3. Database migrations are applied: `python manage.py migrate`

---

## Monitoring

### Check Logs

```bash
# Application logs
tail -f /var/log/gunicorn/error.log

# Celery logs
tail -f /var/log/celery/worker.log

# Nginx logs
tail -f /var/log/nginx/error.log
```

### Monitor SMS Sending

```bash
# Check recent SMS tasks in Celery
celery -A config inspect active

# Monitor Redis
redis-cli MONITOR
```

---

## Rollback Plan

If deployment fails:

```bash
# Revert git changes
git revert HEAD
git push origin main

# Or checkout previous commit
git checkout <previous-commit-hash>

# Restart services
sudo systemctl restart gunicorn celery-worker celery-beat
```

---

## Security Notes

1. **API Keys**: Wasiliana API key is stored in environment variables, never commit to git
2. **OTP Expiry**: OTPs expire in 5 minutes (configurable via `OTP_EXPIRY_SECONDS`)
3. **Rate Limiting**: OTP sending is rate-limited to 5 requests per minute
4. **Max Attempts**: Users get 5 attempts to verify OTP before it's invalidated

---

## Support

For issues or questions:
- Check application logs first
- Review Wasiliana API documentation: https://docs.wasiliana.com/
- Test SMS functionality using `test_wasiliana_sms.py` script

---

## Summary of Files Changed

```
backend/
├── apps/
│   ├── accounts/
│   │   ├── serializers.py          # Added VerifyLoginOTPSerializer
│   │   ├── views.py                # Updated HR/Admin login, added VerifyLoginOTPView
│   │   └── urls.py                 # Added verify-login-otp route
│   └── notifications/
│       ├── wasiliana_sms.py        # NEW - Wasiliana SMS integration
│       └── sms.py                  # Updated to use Wasiliana
├── config/
│   └── settings/
│       └── base.py                 # Added WASILIANA_* settings
├── requirements.txt                # Added pytek-wasiliana==1.2
├── .env.example                    # Added WASILIANA_* variables
├── test_wasiliana_sms.py          # NEW - SMS testing script
├── test_login_flows.py            # NEW - Login flow testing script
└── DEPLOYMENT_GUIDE.md            # This file
```
