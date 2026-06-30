"""
Create one fully-wired test account per role (admin, HR manager, employee)
for end-to-end testing.

Unlike seed_users, this:
  - links the HR user via HRProfile (the app resolves an HR's employer through
    user.hr_profile.employer), so the HR portal actually shows data;
  - makes the employee CONFIRMED staff (loan-eligible) on the SAME employer as
    the HR user, so an application the employee submits is visible to that HR;
  - is idempotent and lets you set real phone numbers (needed to receive the
    login OTP over SMS).

Usage:
  python manage.py seed_test_accounts \
      --admin-phone +2547... --hr-phone +2547... --employee-phone +2547...
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import CustomUser, HRProfile, EmployeeProfile
from apps.employers.models import Employer

PASSWORD = 'Test@1234'
EMPLOYER_NAME = '254 Test Company'


class Command(BaseCommand):
    help = 'Create one test account per role (admin, hr_manager, employee), fully wired.'

    def add_arguments(self, parser):
        parser.add_argument('--admin-phone', default='+254700000101')
        parser.add_argument('--hr-phone', default='+254700000102')
        parser.add_argument('--employee-phone', default='+254700000103')

    @transaction.atomic
    def handle(self, *args, **opts):
        # Employer
        employer, _ = Employer.objects.get_or_create(
            name=EMPLOYER_NAME,
            defaults={
                'registration_number': 'TEST/0001',
                'address': 'Nairobi, Kenya',
                'hr_contact_name': 'Test HR',
                'hr_contact_email': 'hr@test.254capital.com',
                'hr_contact_phone': '+254700000102',
            },
        )

        # ----- Admin -----
        admin = self._upsert_user(
            phone=opts['admin_phone'], email='admin@test.254capital.com',
            username='admintest', role=CustomUser.Role.ADMIN,
            first_name='Test', last_name='Admin',
            extra={'is_staff': True, 'is_superuser': True},
        )

        # ----- HR manager (linked via HRProfile) -----
        hr = self._upsert_user(
            phone=opts['hr_phone'], email='hr@test.254capital.com',
            username='hrtest', role=CustomUser.Role.HR_MANAGER,
            first_name='Test', last_name='HR',
        )
        HRProfile.objects.get_or_create(
            user=hr, defaults={'employer': employer, 'department': 'Human Resources'}
        )
        # Ensure the link points at our employer even if profile pre-existed
        HRProfile.objects.filter(user=hr).update(employer=employer)

        # ----- Employee (confirmed staff, same employer) -----
        employee = self._upsert_user(
            phone=opts['employee_phone'], email='employee@test.254capital.com',
            username=None, role=CustomUser.Role.EMPLOYEE,
            first_name='Test', last_name='Employee',
            extra={'national_id': '99887766'},
        )
        EmployeeProfile.objects.get_or_create(
            user=employee,
            defaults={
                'employer': employer,
                'employee_id': 'EMP-TEST-001',
                'department': 'Operations',
                'employment_type': EmployeeProfile.EmploymentType.CONFIRMED,
                'monthly_gross_salary': Decimal('120000.00'),
                'bank_name': 'KCB Bank',
                'bank_branch': 'Nairobi',
                'bank_account_number': '1122334455',
                'mpesa_number': employee.phone_number,
            },
        )
        EmployeeProfile.objects.filter(user=employee).update(
            employer=employer,
            employment_type=EmployeeProfile.EmploymentType.CONFIRMED,
        )

        self.stdout.write(self.style.SUCCESS('\n✅ Test accounts ready (password for all: %s)\n' % PASSWORD))
        self.stdout.write(f'  Employer : {employer.name}')
        self.stdout.write(f'  ADMIN    : login=admin/login  email=admin@test.254capital.com  username=admintest  phone={admin.phone_number}')
        self.stdout.write(f'  HR       : login=hr/login     email=hr@test.254capital.com     username=hrtest     phone={hr.phone_number}')
        self.stdout.write(f'  EMPLOYEE : login=phone OTP    phone={employee.phone_number}')
        self.stdout.write('\nAll three require an OTP sent to the phone above; set real phones via --*-phone to receive it.\n')

    def _upsert_user(self, phone, email, username, role, first_name, last_name, extra=None):
        extra = extra or {}
        user = CustomUser.objects.filter(phone_number=phone).first() \
            or (CustomUser.objects.filter(email=email).first() if email else None)
        if user is None:
            user = CustomUser(phone_number=phone)
        user.email = email
        user.username = username
        user.role = role
        user.first_name = first_name
        user.last_name = last_name
        user.phone_number = phone
        user.is_phone_verified = True
        for k, v in extra.items():
            setattr(user, k, v)
        user.set_password(PASSWORD)
        user.save()
        return user
