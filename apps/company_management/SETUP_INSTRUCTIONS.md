# Company Management Feature - Setup Instructions

## Backend Setup (Django)

### 1. Create and Run Migrations

Navigate to the backend directory and activate your virtual environment, then run:

```bash
cd ~/Desktop/docs/business/254capital/salary_checkoff/backend

# Activate virtual environment (if using venv)
source venv/bin/activate

# Create migrations for the new app
python manage.py makemigrations company_management

# Run migrations to create database tables
python manage.py migrate company_management

# Run all pending migrations
python manage.py migrate
```

### 2. Update Existing Loan Applications (Optional Migration)

If you have existing loan applications, you need to add an `organization_id` field to them. Create a data migration or run SQL:

```sql
-- Add organization_id column to loan_applications table (if not exists)
ALTER TABLE loan_applications
ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id);

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_loan_applications_org_status
ON loan_applications(organization_id, status);
```

### 3. Test the Backend API

Start the development server:

```bash
python manage.py runserver
```

The Company Management API will be available at:
- Organizations: `http://localhost:8000/api/v1/company-management/organizations/`
- Roles: `http://localhost:8000/api/v1/company-management/roles/`
- Users: `http://localhost:8000/api/v1/company-management/organization-users/`
- Audit Logs: `http://localhost:8000/api/v1/company-management/audit-logs/`
- Change Password: `http://localhost:8000/api/v1/company-management/change-password/`

### 4. Create Test Data (Optional)

You can use the Django admin or API to create test organizations, roles, and users:

```bash
# Access Django admin at http://localhost:8000/admin/
# Login with your superuser account
```

## API Endpoints Summary

### Organization Management
- `GET /api/v1/company-management/organizations/` - List organizations
- `POST /api/v1/company-management/organizations/` - Create organization
- `GET /api/v1/company-management/organizations/{id}/` - Get organization details
- `PUT /api/v1/company-management/organizations/{id}/` - Update organization
- `PATCH /api/v1/company-management/organizations/{id}/deactivate/` - Deactivate organization

### Role Management
- `GET /api/v1/company-management/roles/` - List roles
- `GET /api/v1/company-management/roles/?organization_id={org_id}` - Filter roles by organization
- `POST /api/v1/company-management/roles/` - Create role
- `PUT /api/v1/company-management/roles/{id}/` - Update role
- `DELETE /api/v1/company-management/roles/{id}/` - Soft delete role

### User Management
- `GET /api/v1/company-management/organization-users/` - List users
- `GET /api/v1/company-management/organization-users/?organization_id={org_id}` - Filter by organization
- `POST /api/v1/company-management/organization-users/create-with-email/` - Create user with email
- `PATCH /api/v1/company-management/organization-users/{id}/deactivate/` - Deactivate user

### Authentication
- `POST /api/v1/company-management/change-password/` - Change password

### Audit Logs
- `GET /api/v1/company-management/audit-logs/` - List audit logs
- `GET /api/v1/company-management/audit-logs/?organization={org_id}` - Filter by organization
- `GET /api/v1/company-management/audit-logs/?event_type={type}` - Filter by event type

## Email Configuration

Ensure your `.env` file has the following configured:

```env
# Email settings (already configured in your .env)
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
SENDER_EMAIL=checkoff@254-capital.com

# Frontend URL for email links
FRONTEND_URL=https://www.254-capital.com/

# Django email backend (add if not present)
DEFAULT_FROM_EMAIL=checkoff@254-capital.com
```

## Security Notes

1. **Permission Classes**: All endpoints are protected by `IsHRAdmin` permission
2. **Organization Isolation**: Users can only access resources from their organization
3. **Audit Logging**: All actions are automatically logged to `audit_logs` table
4. **Password Security**: Passwords are hashed with bcrypt, generated passwords are 14 characters with mixed case/digit/special

## Troubleshooting

### Migration Errors

If you encounter migration conflicts:

```bash
# List migrations
python manage.py showmigrations company_management

# If needed, fake the initial migration (only if tables already exist)
python manage.py migrate company_management --fake-initial

# Or rollback and reapply
python manage.py migrate company_management zero
python manage.py migrate company_management
```

### Email Sending Errors

Check email configuration:

```python
# Test email in Django shell
python manage.py shell

from django.core.mail import send_mail
send_mail(
    'Test Subject',
    'Test Message',
    'checkoff@254-capital.com',
    ['test@example.com'],
    fail_silently=False
)
```

## Next Steps

After backend setup is complete:
1. Proceed to frontend implementation
2. Create HR admin UI for managing organizations, roles, and users
3. Implement restricted user interface (pending applications + change password only)
4. Test end-to-end user creation and onboarding flow
