#!/bin/bash

# 254 Capital Email Integration - Production Deployment Helper
# This script provides step-by-step guidance without exposing secrets

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     254 CAPITAL - EMAIL INTEGRATION PRODUCTION DEPLOYMENT     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

cat << 'EOF'
STEP 1: SSH into Production Server
===================================
ssh your-user@your-server-ip

Example: ssh ubuntu@54.77.248.243


STEP 2: Navigate to Application Directory
=========================================
cd /opt/salary_checkoff


STEP 3: Add Azure Credentials to .env.production
================================================
nano .env.production

Add these lines (copy actual values from local .env file):

# Microsoft Azure Email Configuration
AZURE_TENANT_ID=<from local .env>
AZURE_CLIENT_ID=<from local .env>
AZURE_CLIENT_SECRET=<from local .env>
SENDER_EMAIL=checkoff@254-capital.com

Save: Ctrl+X, Y, Enter


STEP 4: Pull Latest Code
========================
git pull origin main


STEP 5: Install Dependencies
============================
source venv/bin/activate
pip install msal==1.28.0 requests==2.32.3


STEP 6: Run Migrations
=====================
python manage.py migrate accounts


STEP 7: Restart Services
========================
# Docker:
docker-compose down && docker-compose up -d

# Systemd:
sudo systemctl restart salary-checkoff


STEP 8: Test Email
==================
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()
from common.email_service import send_email
result = send_email('david.muema@254-capital.com', 'Test', '<h1>Working!</h1>')
print('✅ Success!' if result['success'] else '❌ Failed')
"


VERIFICATION
============
- Check david.muema@254-capital.com for test email
- Monitor logs for any errors
- Test password reset functionality
- Register a new user and verify welcome email

For detailed instructions, see: DEPLOYMENT_EMAIL_GUIDE.md
For credential values, check your local .env file
EOF

echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""
