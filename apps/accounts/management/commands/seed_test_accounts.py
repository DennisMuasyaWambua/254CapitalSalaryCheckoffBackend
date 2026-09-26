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

Outside DEBUG (i.e. production) this refuses the placeholder phone numbers and
the shared default password, because:
  - every role logs in with an OTP sent by SMS, and the dev-only OTP log line in
    apps/accounts/otp.py is gated on DEBUG, so a placeholder number produces an
    account nobody can sign in to;
  - DEFAULT_DEV_PASSWORD is committed to this repo, so using it on a live system
    would leave a known-password account on real salary and bank data.
"""

import getpass
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import CustomUser, HRProfile, EmployeeProfile
from apps.employers.models import Employer

DEFAULT_DEV_PASSWORD = 'Test@1234'
EMPLOYER_NAME = '254 Test Company'
PLACEHOLDER_PHONES = {'+254700000101', '+254700000102', '+254700000103'}


class Command(BaseCommand):
    help = 'Create one test account per role (admin, hr_manager, employee), fully wired.'

    def add_arguments(self, parser):
        parser.add_argument('--admin-phone', default='+254700000101')
        parser.add_argument('--hr-phone', default='+254700000102')
        parser.add_argument('--employee-phone', default='+254700000103')
        parser.add_argument('--admin-email', default='admin@test.254capital.com')
        parser.add_argument('--hr-email', default='hr@test.254capital.com')
        parser.add_argument('--employee-email', default='employee@test.254capital.com')
        parser.add_argument(
            '--password',
            help='Password for the admin and HR accounts. Prompted for if omitted. '
                 'Required outside DEBUG.',
        )
        parser.add_argument(
            '--no-superuser',
            action='store_true',
            help='Create the admin without Django superuser/staff rights.',
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        password = self._resolve_password(opts)

        if not settings.DEBUG:
            placeholders = PLACEHOLDER_PHONES.intersection({
                opts['admin_phone'], opts['hr_phone'], opts['employee_phone'],
            })
            if placeholders:
                raise CommandError(
                    'Refusing to seed placeholder phone numbers outside DEBUG: '
                    f'{", ".join(sorted(placeholders))}.\n'
                    'Every role signs in with an SMS OTP and the dev-only OTP log is '
                    'disabled when DEBUG is False, so these accounts would be '
                    'unreachable. Pass real numbers via --admin-phone / --hr-phone / '
                    '--employee-phone.'
                )

        # Employer
        employer, _ = Employer.objects.get_or_create(
            name=EMPLOYER_NAME,
            defaults={
                'registration_number': 'TEST/0001',
                'address': 'Nairobi, Kenya',
                'hr_contact_name': 'Test HR',
                'hr_contact_email': opts['hr_email'],
                'hr_contact_phone': opts['hr_phone'],
            },
        )

        # ----- Admin -----
        admin = self._upsert_user(
            phone=opts['admin_phone'], email=opts['admin_email'],
            username='admintest', role=CustomUser.Role.ADMIN,
            first_name='Test', last_name='Admin',
            password=password,
            extra={
                'is_staff': not opts['no_superuser'],
                'is_superuser': not opts['no_superuser'],
            },
        )

        # ----- HR manager (linked via HRProfile) -----
        hr = self._upsert_user(
            phone=opts['hr_phone'], email=opts['hr_email'],
            username='hrtest', role=CustomUser.Role.HR_MANAGER,
            first_name='Test', last_name='HR',
            password=password,
        )
        HRProfile.objects.get_or_create(
            user=hr, defaults={'employer': employer, 'department': 'Human Resources'}
        )
        # Ensure the link points at our employer even if profile pre-existed
        HRProfile.objects.filter(user=hr).update(employer=employer)

        # ----- Employee (confirmed staff, same employer) -----
        employee = self._upsert_user(
            phone=opts['employee_phone'], email=opts['employee_email'],
            username=None, role=CustomUser.Role.EMPLOYEE,
            first_name='Test', last_name='Employee',
            password=password,
            extra={'national_id': '99887766'},
        )
        EmployeeProfile.objects.get_or_create(
            user=employee,
            defaults={
                'employer': employer,
                'employee_id': 'EMP-TEST-001',
                'department': 'Operations',
                'employment_type': EmployeeProfile.EmploymentType.CONFIRMED,
                'employment_start_date': '2024-01-15',
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
            employment_start_date='2024-01-15',
        )

        password_note = (
            'password for all: %s' % DEFAULT_DEV_PASSWORD
            if settings.DEBUG and not opts.get('password')
            else 'password: as supplied'
        )
        self.stdout.write(self.style.SUCCESS('\n✅ Test accounts ready (%s)\n' % password_note))
        self.stdout.write(f'  Employer : {employer.name}')
        self.stdout.write(f'  ADMIN    : login=admin/login  email={admin.email}  username=admintest  phone={admin.phone_number}  superuser={admin.is_superuser}')
        self.stdout.write(f'  HR       : login=hr/login     email={hr.email}     username=hrtest     phone={hr.phone_number}')
        self.stdout.write(f'  EMPLOYEE : login=phone OTP    phone={employee.phone_number}  email={employee.email}')
        self.stdout.write('\nAll three require an OTP sent to the phone above; set real phones via --*-phone to receive it.\n')

    def _resolve_password(self, opts):
        """
        Resolve the password for the admin/HR accounts.

        The committed default is only acceptable in DEBUG; production must supply
        one explicitly or be prompted for it.
        """
        if opts.get('password'):
            return opts['password']

        if settings.DEBUG:
            return DEFAULT_DEV_PASSWORD

        while True:
            first = getpass.getpass('Password for the admin and HR accounts: ')
            second = getpass.getpass('Password (again): ')
            if first != second:
                self.stdout.write(self.style.ERROR('Passwords do not match. Try again.'))
                continue
            if len(first) < 8:
                self.stdout.write(self.style.ERROR('Password must be at least 8 characters.'))
                continue
            if first == DEFAULT_DEV_PASSWORD:
                self.stdout.write(self.style.ERROR(
                    'That password is committed to the repository. Choose another.'
                ))
                continue
            return first

    def _upsert_user(self, phone, email, username, role, first_name, last_name, password, extra=None):
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
        user.set_password(password)
        user.save()
        return user
