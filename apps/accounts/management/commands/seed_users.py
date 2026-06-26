"""
Management command to seed only users and roles (admin, hr_manager, employee)
"""
from django.core.management.base import BaseCommand
from decimal import Decimal
from apps.accounts.models import CustomUser, EmployeeProfile
from apps.employers.models import Employer


class Command(BaseCommand):
    help = 'Seed the database with users and basic employer entries (admin, hr, employees)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting to seed users...'))

        # Create Employers (minimal)
        self.stdout.write('Creating employers...')
        employers = []
        employer_data = [
            {
                'name': 'Kenya Power & Lighting Co.',
                'registration_number': 'C.123/2020',
                'hr_contact_name': 'John Kamau',
                'hr_contact_email': 'hr@kplc.co.ke',
                'hr_contact_phone': '+254712345678',
                'address': 'P.O. Box 30099, Nairobi',
            },
            {
                'name': 'Safaricom PLC',
                'registration_number': 'C.456/2018',
                'hr_contact_name': 'Mary Wanjiru',
                'hr_contact_email': 'hr@safaricom.co.ke',
                'hr_contact_phone': '+254723456789',
                'address': 'P.O. Box 66827, Nairobi',
            },
            {
                'name': 'KCB Bank Kenya',
                'registration_number': 'C.789/2015',
                'hr_contact_name': 'Peter Omondi',
                'hr_contact_email': 'hr@kcb.co.ke',
                'hr_contact_phone': '+254734567890',
                'address': 'P.O. Box 48400, Nairobi',
            },
        ]

        for data in employer_data:
            employer, created = Employer.objects.get_or_create(
                name=data['name'],
                defaults=data
            )
            employers.append(employer)
            if created:
                self.stdout.write(f'  Created employer: {employer.name}')
            else:
                self.stdout.write(f'  Employer already exists: {employer.name}')

        # Create Admin User
        self.stdout.write('Creating admin user...')
        admin, created = CustomUser.objects.get_or_create(
            phone_number='+254700000001',
            defaults={
                'first_name': 'Admin',
                'last_name': 'User',
                'email': 'admin@254capital.com',
                'role': 'admin',
                'username': 'admin',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin.set_password('admin123')
            admin.save()
            self.stdout.write(self.style.SUCCESS(f'  Created admin: {admin.get_full_name()} (Phone: {admin.phone_number}, Password: admin123)'))
        else:
            self.stdout.write(f'  Admin already exists: {admin.get_full_name()}')

        # Create HR Managers
        self.stdout.write('Creating HR managers...')
        hr_managers = []
        for i, employer in enumerate(employers):
            hr, created = CustomUser.objects.get_or_create(
                phone_number=f'+25470000000{i+2}',
                defaults={
                    'first_name': employer.hr_contact_name.split()[0],
                    'last_name': employer.hr_contact_name.split()[-1],
                    'email': employer.hr_contact_email,
                    'role': 'hr_manager',
                    'username': f'hr{i+1}',
                }
            )
            if created:
                hr.set_password('hr123')
                hr.save()
                # Link HR to employer through EmployeeProfile if model exists
                try:
                    EmployeeProfile.objects.create(
                        user=hr,
                        employer=employer,
                        employee_id=f'HR{i+1:03d}',
                        department='Human Resources',
                        monthly_gross_salary=Decimal('150000.00'),
                        bank_name='KCB Bank',
                        bank_account_number=f'1234567890{i}',
                        mpesa_number=hr.phone_number,
                    )
                except Exception:
                    # If EmployeeProfile model is not present or linkage fails, skip
                    pass
                self.stdout.write(self.style.SUCCESS(f'  Created HR: {hr.get_full_name()} for {employer.name} (Phone: {hr.phone_number}, Password: hr123)'))
            else:
                self.stdout.write(f'  HR already exists: {hr.get_full_name()}')
            hr_managers.append(hr)

        # Create Employees
        self.stdout.write('Creating employees...')
        employees_data = [
            {'first_name': 'James', 'last_name': 'Mwangi', 'department': 'Engineering', 'salary': 80000},
            {'first_name': 'Grace', 'last_name': 'Achieng', 'department': 'Finance', 'salary': 95000},
            {'first_name': 'David', 'last_name': 'Kipchoge', 'department': 'Marketing', 'salary': 70000},
            {'first_name': 'Sarah', 'last_name': 'Njeri', 'department': 'IT', 'salary': 85000},
            {'first_name': 'Michael', 'last_name': 'Otieno', 'department': 'Operations', 'salary': 75000},
        ]

        for i, emp_data in enumerate(employees_data):
            for j, employer in enumerate(employers):
                phone_number = f'+2547{(i*10 + j):08d}'
                employee, created = CustomUser.objects.get_or_create(
                    phone_number=phone_number,
                    defaults={
                        'first_name': emp_data['first_name'],
                        'last_name': emp_data['last_name'],
                        'email': f'{emp_data["first_name"].lower()}.{emp_data["last_name"].lower()}{j}@example.com',
                        'role': 'employee',
                    }
                )

                if created:
                    employee.set_password('employee123')
                    employee.save()

                    # Create employee profile if model exists
                    try:
                        EmployeeProfile.objects.create(
                            user=employee,
                            employer=employer,
                            employee_id=f'EMP{i}{j:03d}',
                            department=emp_data['department'],
                            monthly_gross_salary=Decimal(str(emp_data['salary'])),
                            bank_name='KCB Bank',
                            bank_account_number=f'987654321{i}{j}',
                            mpesa_number=employee.phone_number,
                        )
                    except Exception:
                        pass

                    self.stdout.write(self.style.SUCCESS(f'  Created employee: {employee.get_full_name()} at {employer.name} (Phone: {employee.phone_number}, Password: employee123)'))
                else:
                    self.stdout.write(f'  Employee already exists: {employee.get_full_name()}')

        self.stdout.write(self.style.SUCCESS('\n✅ Users seeded successfully!'))
        self.stdout.write('\n📋 Sample Credentials:')
        self.stdout.write('  Admin: Phone: +254700000001, Password: admin123')
        self.stdout.write('  HR Managers: Phone: +254700000002-004, Password: hr123')
        self.stdout.write('  Employees: Phone: +2547XXXXXXXX, Password: employee123')
