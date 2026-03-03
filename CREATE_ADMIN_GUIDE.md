# Creating Admin Users on Production

There are **3 methods** to create admin users on your production server. Choose the one that works best for your setup.

---

## Method 1: Using Custom Management Command (RECOMMENDED) ✅

This is the easiest and safest method.

### **Interactive Mode** (Recommended for Security)

```bash
# SSH to your production server
ssh your-server

# Navigate to project directory
cd /path/to/backend

# Activate virtual environment
source venv/bin/activate

# Run the create_admin command
python manage.py create_admin
```

You'll be prompted to enter:
```
Email: admin@254capital.com
Phone (+254712345678): +254712345678
First Name: Super
Last Name: Admin
Password: ********
Password (again): ********
```

**Output:**
```
✓ Admin user created successfully!
  Email: admin@254capital.com
  Phone: +254712345678
  Name: Super Admin
  Role: Admin
  Superuser: Yes

You can now log in at: /api/v1/auth/admin/login/
Note: OTP will be sent to +254712345678 during login
```

### **Non-Interactive Mode** (For Scripts/Automation)

```bash
python manage.py create_admin \
  --email admin@254capital.com \
  --phone +254712345678 \
  --first-name Super \
  --last-name Admin \
  --password "YourSecurePassword123!" \
  --noinput
```

---

## Method 2: Using Django Shell

If you prefer more control or need to customize:

```bash
# SSH to your server
ssh your-server
cd /path/to/backend
source venv/bin/activate

# Open Django shell
python manage.py shell
```

Then run this Python code:

```python
from apps.accounts.models import CustomUser

# Create admin user
admin = CustomUser.objects.create(
    username='admin@254capital.com',
    email='admin@254capital.com',
    phone_number='+254712345678',
    first_name='Super',
    last_name='Admin',
    role='admin',
    is_staff=True,
    is_superuser=True,
    is_active=True,
    is_phone_verified=True,  # Pre-verify phone
)

# Set password
admin.set_password('YourSecurePassword123!')
admin.save()

print(f"✓ Admin created: {admin.email}")
exit()
```

---

## Method 3: Using Django's Built-in createsuperuser (NOT RECOMMENDED)

Django's default `createsuperuser` may not work properly with your custom user model that requires phone numbers and roles. **Use Method 1 or 2 instead.**

---

## After Creating Admin

### Step 1: Test Login

```bash
# Test admin login endpoint
curl -X POST https://your-domain.com/api/v1/auth/admin/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@254capital.com",
    "password": "YourSecurePassword123!"
  }'
```

**Expected Response:**
```json
{
  "detail": "OTP sent to your phone. Please verify to complete login.",
  "requires_otp": true,
  "temp_token": "eyJ0eXAiOiJKV1Q...",
  "masked_phone": "071***678",
  "expires_in": 300
}
```

### Step 2: Verify OTP (Check SMS)

```bash
# Use the OTP from SMS
curl -X POST https://your-domain.com/api/v1/auth/verify-login-otp/ \
  -H "Content-Type: application/json" \
  -d '{
    "temp_token": "TEMP_TOKEN_FROM_ABOVE",
    "otp": "123456"
  }'
```

**Expected Response:**
```json
{
  "detail": "Login successful",
  "tokens": {
    "refresh": "eyJ0eXAiOiJKV1Q...",
    "access": "eyJ0eXAiOiJKV1Q..."
  },
  "user": {
    "id": "...",
    "email": "admin@254capital.com",
    "role": "admin",
    ...
  }
}
```

---

## Creating Multiple Admins

You can create as many admins as needed. Each admin needs:

- ✅ Unique email address
- ✅ Unique phone number (for OTP)
- ✅ Secure password

**Example: Create second admin**

```bash
python manage.py create_admin \
  --email admin2@254capital.com \
  --phone +254723456789 \
  --first-name John \
  --last-name Doe \
  --password "SecurePass456!" \
  --noinput
```

---

## Security Best Practices

1. **Strong Passwords**
   - Minimum 8 characters
   - Mix of uppercase, lowercase, numbers, symbols
   - Never use common passwords

2. **Phone Number Verification**
   - Admin phone should be a real number for OTP
   - Phone must be in Kenyan format (+254...)
   - Keep phone number confidential

3. **Email Security**
   - Use official company email
   - Enable 2FA on email account
   - Monitor for suspicious login attempts

4. **OTP Security**
   - OTPs expire in 5 minutes
   - Maximum 5 verification attempts
   - New OTP invalidates old ones

---

## Troubleshooting

### Error: "User with email already exists"

**Solution**: Email must be unique. Use a different email or delete the existing user first.

```bash
# Check if user exists
python manage.py shell
>>> from apps.accounts.models import CustomUser
>>> CustomUser.objects.filter(email='admin@254capital.com').exists()
>>> exit()
```

### Error: "Invalid Kenyan phone number format"

**Solution**: Use correct format:
- ✅ `+254712345678`
- ✅ `254712345678`
- ✅ `0712345678`
- ❌ `712345678` (missing prefix)

### Error: "command not found: create_admin"

**Solution**: Make sure you deployed the new `create_admin.py` file:

```bash
# Check if file exists
ls apps/accounts/management/commands/create_admin.py

# If not, copy it to server or pull from git
git pull origin main
```

### OTP Not Received

**Solution**:
1. Check Celery worker is running: `systemctl status celery-worker`
2. Check Redis is running: `redis-cli ping`
3. Verify Wasiliana credentials in `.env`
4. Check Celery logs: `tail -f /var/log/celery/worker.log`

---

## Quick Reference

| Method | Best For | Security | Complexity |
|--------|----------|----------|------------|
| **create_admin (interactive)** | Production setup | ⭐⭐⭐⭐⭐ | Low |
| **create_admin (non-interactive)** | Scripts/automation | ⭐⭐⭐ | Low |
| **Django shell** | Custom requirements | ⭐⭐⭐⭐ | Medium |
| ~~**createsuperuser**~~ | ❌ Not compatible | ❌ | N/A |

---

## Example: Complete Production Setup

```bash
# 1. SSH to server
ssh production-server

# 2. Navigate to project
cd /var/www/salary_checkoff/backend

# 3. Activate environment
source venv/bin/activate

# 4. Create first admin
python manage.py create_admin
# Follow prompts...

# 5. Test login
curl -X POST https://254-capital.vercel.app/api/v1/auth/admin/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@254capital.com", "password": "YourPassword"}'

# 6. Check OTP SMS and verify
curl -X POST https://254-capital.vercel.app/api/v1/auth/verify-login-otp/ \
  -H "Content-Type: application/json" \
  -d '{"temp_token": "TOKEN", "otp": "123456"}'

# 7. Success! Admin can now create companies
```

---

## Admin Capabilities

Once admin is created and logged in, they can:

- ✅ Create/update companies (employers)
- ✅ View all loan applications
- ✅ Approve/reject applications
- ✅ Manage users (employees, HR managers)
- ✅ View system statistics
- ✅ Access Django admin panel
- ✅ Generate reports
- ✅ Configure system settings

---

## Next Steps After Creating Admin

1. **Log in as admin** and verify OTP works
2. **Create test company** to verify employer creation
3. **Create HR manager** for the test company
4. **Test employee registration** flow
5. **Document credentials** securely (use password manager)

---

## Summary

**Recommended approach for production:**

```bash
# On production server
python manage.py create_admin
```

Simple, secure, and interactive. Takes 30 seconds! ✅
