"""
Management command to seed specific demo accounts with provided phone numbers.

Roles mapped:
  admin         → +254720523299   (is_staff + is_superuser)
  employer rep  → +254724857202   (hr_manager, linked to demo employer)
  employee      → +254713448947   (employee, linked to demo employer)
  hr_manager    → +254742064270   (hr_manager, linked to demo employer)
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.accounts.models import CustomUser, EmployeeProfile, HRProfile
from apps.employers.models import Employer


DEMO_EMPLOYER = {
    'name': '254 Capital Demo Company',
    'registration_number': 'C.DEMO/2024',
    'hr_contact_name': 'Demo HR Contact',
    'hr_contact_email': 'hr@254capital.com',
    'hr_contact_phone': '+254720523299',
    'address': 'P.O. Box 1, Nairobi',
}

ACCOUNTS = [
    {
        'phone': '+254720523299',
        'role': 'admin',
        'username': 'admin_demo',
        'first_name': 'Admin',
        'last_name': '254Capital',
        'email': 'admin@254capital.com',
        'password': 'Admin@254Capital',
        'is_staff': True,
        'is_superuser': True,
    },
    {
        'phone': '+254724857202',
        'role': 'hr_manager',
        'username': 'employer_rep',
        'first_name': 'Employer',
        'last_name': 'Representative',
        'email': 'employer@254capital.com',
        'password': 'Employer@254',
        'is_staff': False,
        'is_superuser': False,
        'link_employer': True,
        'department': 'Management',
    },
    {
        'phone': '+254713448947',
        'role': 'employee',
        'first_name': 'Demo',
        'last_name': 'Employee',
        'email': 'employee@254capital.com',
        'password': 'Employee@254',
        'link_employer': True,
        'employee_id': 'EMP001',
        'department': 'General',
        'salary': Decimal('80000.00'),
    },
    {
        'phone': '+254742064270',
        'role': 'hr_manager',
        'username': 'hr_manager',
        'first_name': 'HR',
        'last_name': 'Manager',
        'email': 'hr.manager@254capital.com',
        'password': 'HRManager@254',
        'is_staff': False,
        'is_superuser': False,
        'link_employer': True,
        'department': 'Human Resources',
    },
]


class Command(BaseCommand):
    help = 'Seed specific demo accounts with predefined phone numbers'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Seeding demo accounts...'))

        # Ensure the demo employer exists
        employer, created = Employer.objects.get_or_create(
            registration_number=DEMO_EMPLOYER['registration_number'],
            defaults=DEMO_EMPLOYER,
        )
        if created:
            self.stdout.write(f'  Created employer: {employer.name}')
        else:
            self.stdout.write(f'  Employer already exists: {employer.name}')

        for account in ACCOUNTS:
            phone = account['phone']
            role = account['role']

            user, created = CustomUser.objects.get_or_create(
                phone_number=phone,
                defaults={
                    'role': role,
                    'first_name': account['first_name'],
                    'last_name': account['last_name'],
                    'email': account['email'],
                    'is_staff': account.get('is_staff', False),
                    'is_superuser': account.get('is_superuser', False),
                    **(
                        {'username': account['username']}
                        if account.get('username')
                        else {}
                    ),
                },
            )

            if created:
                user.set_password(account['password'])
                user.save()

                # Link HR managers to employer via HRProfile
                if role == 'hr_manager' and account.get('link_employer'):
                    HRProfile.objects.get_or_create(
                        user=user,
                        defaults={
                            'employer': employer,
                            'department': account.get('department', ''),
                        },
                    )

                # Link employees via EmployeeProfile
                if role == 'employee' and account.get('link_employer'):
                    EmployeeProfile.objects.get_or_create(
                        user=user,
                        defaults={
                            'employer': employer,
                            'employee_id': account.get('employee_id', 'EMP001'),
                            'department': account.get('department', 'General'),
                            'monthly_gross_salary': account.get('salary', Decimal('50000.00')),
                            'bank_name': 'KCB Bank',
                            'bank_account_number': '1000000001',
                            'mpesa_number': phone,
                        },
                    )

                label = {
                    'admin': 'Admin',
                    'hr_manager': 'HR Manager',
                    'employee': 'Employee',
                }.get(role, role)

                self.stdout.write(
                    self.style.SUCCESS(
                        f'  [{label}] Created: {user.get_full_name()} | Phone: {phone} | Password: {account["password"]}'
                    )
                )
            else:
                self.stdout.write(f'  Already exists: {user.get_full_name()} ({phone})')

        self.stdout.write(self.style.SUCCESS('\nDemo accounts ready!'))
        self.stdout.write('\nCredentials:')
        self.stdout.write('  Admin:        +254720523299  /  Admin@254Capital')
        self.stdout.write('  Employer Rep: +254724857202  /  Employer@254')
        self.stdout.write('  Employee:     +254713448947  /  Employee@254')
        self.stdout.write('  HR Manager:   +254742064270  /  HRManager@254')
