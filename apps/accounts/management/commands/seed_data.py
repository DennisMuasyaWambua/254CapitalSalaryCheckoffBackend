"""
Management command to seed the database with sample data for testing
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from apps.accounts.models import CustomUser, EmployeeProfile
from apps.employers.models import Employer
from apps.loans.models import LoanApplication, LoanStatusHistory


class Command(BaseCommand):
    help = 'Seed the database with sample data for testing'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting to seed database...'))

        # Create Employers
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
                # Link HR to employer through EmployeeProfile
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
                self.stdout.write(self.style.SUCCESS(f'  Created HR: {hr.get_full_name()} for {employer.name} (Phone: {hr.phone_number}, Password: hr123)'))
            else:
                self.stdout.write(f'  HR already exists: {hr.get_full_name()}')
            hr_managers.append(hr)

        # Create Employees with loan applications
        self.stdout.write('Creating employees...')
        employees_data = [
            {'first_name': 'James', 'last_name': 'Mwangi', 'department': 'Engineering', 'salary': 80000},
            {'first_name': 'Grace', 'last_name': 'Achieng', 'department': 'Finance', 'salary': 95000},
            {'first_name': 'David', 'last_name': 'Kipchoge', 'department': 'Marketing', 'salary': 70000},
            {'first_name': 'Sarah', 'last_name': 'Njeri', 'department': 'IT', 'salary': 85000},
            {'first_name': 'Michael', 'last_name': 'Otieno', 'department': 'Operations', 'salary': 75000},
        ]

        loan_statuses = ['submitted', 'under_review_hr', 'under_review_admin', 'approved', 'disbursed']

        for i, emp_data in enumerate(employees_data):
            for j, employer in enumerate(employers):
                # Create valid Kenyan phone number +254712345678 format
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

                    # Create employee profile
                    profile = EmployeeProfile.objects.create(
                        user=employee,
                        employer=employer,
                        employee_id=f'EMP{i}{j:03d}',
                        department=emp_data['department'],
                        monthly_gross_salary=Decimal(str(emp_data['salary'])),
                        bank_name='KCB Bank',
                        bank_account_number=f'987654321{i}{j}',
                        mpesa_number=employee.phone_number,
                    )

                    self.stdout.write(self.style.SUCCESS(f'  Created employee: {employee.get_full_name()} at {employer.name} (Phone: {employee.phone_number}, Password: employee123)'))

                    # Create 1-2 loan applications per employee
                    num_loans = 1 if i % 2 == 0 else 2
                    for k in range(num_loans):
                        # Generate unique application number
                        app_num = f'254L{(i*100 + j*10 + k):08d}'

                        principal = Decimal(str(50000 + (i * 10000) + (k * 20000)))
                        months = 6 + (k * 6)
                        interest_rate = Decimal('0.15')  # 15%
                        total_repayment = principal * (1 + interest_rate)
                        monthly_deduction = total_repayment / months

                        # Cycle through statuses
                        status_idx = (i + j + k) % len(loan_statuses)
                        status = loan_statuses[status_idx]

                        loan = LoanApplication.objects.create(
                            application_number=app_num,
                            employee=employee,
                            employer=employer,
                            principal_amount=principal,
                            interest_rate=interest_rate,
                            repayment_months=months,
                            total_repayment=total_repayment,
                            monthly_deduction=monthly_deduction,
                            purpose='Personal development' if k == 0 else 'Emergency expenses',
                            status=status,
                            created_at=timezone.now() - timedelta(days=30 - (k * 10)),
                        )

                        # Create status history
                        LoanStatusHistory.objects.create(
                            application=loan,
                            status='submitted',
                            actor=employee,
                            comment='Application submitted by employee',
                        )

                        # Add more status history based on current status
                        if status in ['under_review_hr', 'under_review_admin', 'approved', 'disbursed']:
                            LoanStatusHistory.objects.create(
                                application=loan,
                                status='under_review_hr',
                                actor=hr_managers[j],
                                comment='Application forwarded for credit assessment',
                                created_at=timezone.now() - timedelta(days=25 - (k * 10)),
                            )

                        if status in ['under_review_admin', 'approved', 'disbursed']:
                            LoanStatusHistory.objects.create(
                                application=loan,
                                status='under_review_admin',
                                actor=admin,
                                comment='Under credit assessment review',
                                created_at=timezone.now() - timedelta(days=20 - (k * 10)),
                            )

                        if status in ['approved', 'disbursed']:
                            LoanStatusHistory.objects.create(
                                application=loan,
                                status='approved',
                                actor=admin,
                                comment='Application approved - ready for disbursement',
                                created_at=timezone.now() - timedelta(days=15 - (k * 10)),
                            )
                            loan.approved_at = timezone.now() - timedelta(days=15 - (k * 10))
                            loan.save()

                        if status == 'disbursed':
                            loan.disbursement_date = timezone.now() - timedelta(days=10 - (k * 5))
                            loan.disbursement_method = 'mpesa'
                            loan.disbursement_reference = f'MPE{loan.id}'
                            loan.save()

                            LoanStatusHistory.objects.create(
                                application=loan,
                                status='disbursed',
                                actor=admin,
                                comment=f'Loan disbursed via M-Pesa to {employee.phone_number}',
                                created_at=timezone.now() - timedelta(days=10 - (k * 5)),
                            )

                        self.stdout.write(f'    Created loan application: {loan.application_number} ({status})')
                else:
                    self.stdout.write(f'  Employee already exists: {employee.get_full_name()}')

        self.stdout.write(self.style.SUCCESS('\n✅ Database seeded successfully!'))
        self.stdout.write('\n📋 Sample Credentials:')
        self.stdout.write('  Admin: Phone: +254700000001, Password: admin123')
        self.stdout.write('  HR Managers: Phone: +254700000002-004, Password: hr123')
        self.stdout.write('  Employees: Phone: +2547XXXXXXXX, Password: employee123')
        self.stdout.write('\n🌐 Access the application at: http://localhost:3000')
