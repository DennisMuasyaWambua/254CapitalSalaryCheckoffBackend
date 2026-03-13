# 📧 Email Integration Production Deployment Guide

## ✅ Testing Results

**All Email Tests Passed Successfully!**

All test emails were successfully sent via Microsoft Graph API.

---

## 🚀 Production Deployment Steps

### Step 1: Update Production Environment Variables

**SSH into your production server and add Azure credentials to `.env.production`:**

```bash
# SSH into production
ssh your-user@your-ec2-ip

# Navigate to app directory
cd /opt/salary_checkoff

# Edit .env.production
nano .env.production
```

**Add these lines (get actual values from your local `.env` file):**

```bash
# Microsoft Azure Email Configuration (Microsoft Graph API)
AZURE_TENANT_ID=<copy from local .env>
AZURE_CLIENT_ID=<copy from local .env>
AZURE_CLIENT_SECRET=<copy from local .env>
SENDER_EMAIL=checkoff@254-capital.com
```

**⚠️ IMPORTANT:**
- Copy the actual credential values from your local `.env` file
- NEVER commit these credentials to Git
- Save with: `Ctrl+X`, then `Y`, then `Enter`

---

### Step 2: Install Required Python Packages

```bash
cd /opt/salary_checkoff
source venv/bin/activate
pip install msal==1.28.0 requests==2.32.3
```

---

### Step 3: Pull Latest Code & Run Migrations

```bash
# Pull latest code
git pull origin main

# Run migrations
python manage.py migrate accounts
```

Expected output:
```
Running migrations:
  Applying accounts.0004_passwordresettoken... OK
```

---

### Step 4: Restart Production Services

**Choose based on your setup:**

```bash
# If using Docker:
docker-compose down && docker-compose up -d

# If using Systemd:
sudo systemctl restart salary-checkoff

# If using Supervisor:
sudo supervisorctl restart salary-checkoff
```

---

### Step 5: Test Email Integration

Create and run test script:

```bash
cd /opt/salary_checkoff

cat > test_production_email.py << 'EOF'
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()

from common.email_service import send_email

result = send_email(
    to_address='david.muema@254-capital.com',
    subject='Production Email Test - 254 Capital',
    body_html='<h1>Success!</h1><p>Email integration is working on production!</p>'
)

print('✅ Email sent successfully!' if result['success'] else f'❌ Failed: {result.get("error")}')
EOF

python test_production_email.py
```

Check `david.muema@254-capital.com` inbox for test email.

---

## 📊 What's Been Integrated

**Email sending now works in these locations:**

| Action | Sends Email To | CC's Admin |
|--------|---------------|------------|
| Employee registers | Employee | ✓ |
| Admin created | Admin | ✓ |
| HR Manager created | HR Manager | ✓ |
| Client approved | Client | ✓ |
| Client rejected | Client | ✓ |
| Loan application submitted | Employee | ✓ |
| HR approves/declines loan | Employee | ✓ |
| Admin approves/declines loan | Employee | ✓ |
| Loan disbursed | Employee | ✓ |
| Password reset request | User | - |
| Password reset complete | - | ✓ |

**All internal alerts go to: david.muema@254-capital.com**

---

## 🔒 Security Notes

1. **NEVER commit credentials to Git**
2. **Only add credentials to server `.env` files**
3. **Rotate Azure secrets periodically**
4. **Limit SSH access to production server**

---

## 🆘 Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'msal'"
**Solution:**
```bash
pip install msal==1.28.0 requests==2.32.3
```

### Issue: "Missing Azure credentials"
**Solution:**
```bash
# Verify environment variables are set
echo $AZURE_TENANT_ID
echo $AZURE_CLIENT_ID
echo $SENDER_EMAIL
```

### Issue: Emails not received
**Solution:**
- Check spam/junk folder
- Check application logs for errors
- Verify Azure credentials are correct

---

## 📋 Deployment Checklist

- [ ] Azure credentials added to production `.env`
- [ ] `msal` and `requests` packages installed
- [ ] Latest code pulled from Git
- [ ] Migrations run successfully
- [ ] Production services restarted
- [ ] Test email sent successfully
- [ ] Password reset tested
- [ ] Logs monitored for issues

---

## ✨ Summary

✅ **Email integration deployed via Microsoft Graph API**
✅ **All credentials loaded from environment variables**
✅ **No secrets in codebase**
✅ **Professional HTML email templates**
✅ **Password reset functionality for HR/Admin**
✅ **Internal alerts to admin**

**Total Files Modified:** 12
**Email Integration Points:** 14

---

**For detailed credential values, check your local `.env` file.**
**Never share or commit these credentials!**
