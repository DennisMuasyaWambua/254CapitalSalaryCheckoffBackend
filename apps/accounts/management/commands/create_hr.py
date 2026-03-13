"""
Django management command to create an HR manager user.

Usage:
    python manage.py create_hr
    python manage.py create_hr --email hr@company.com --phone +254712345678 --password Pass123!

This command creates an HR manager user for the 254 Capital system with:
- HR Manager role
- Email/password authentication
- OTP login capability
- Linked to an employer
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.accounts.models import CustomUser, HRProfile
from apps.employers.models import Employer
from common.email_service import send_welcome_email, send_internal_alert
import getpass


class Command(BaseCommand):
    help = 'Create an HR manager user for 254 Capital system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            help='HR manager email address',
        )
        parser.add_argument(
            '--phone',
            type=str,
            help='HR manager phone number (format: +254712345678 or 0712345678)',
        )
        parser.add_argument(
            '--first-name',
            type=str,
            help='HR manager first name',
        )
        parser.add_argument(
            '--last-name',
            type=str,
            help='HR manager last name',
        )
        parser.add_argument(
            '--password',
            type=str,
            help='HR manager password (not recommended for security - use interactive mode)',
        )
        parser.add_argument(
            '--employer-id',
            type=str,
            help='UUID of the employer to link this HR manager to',
        )
        parser.add_argument(
            '--noinput',
            action='store_true',
            help='Non-interactive mode (requires all arguments)',
        )

    def handle(self, *args, **options):
        """Create HR manager user."""

        # Interactive mode
        if not options['noinput']:
            self.stdout.write(self.style.WARNING('\n=== Create HR Manager User ===\n'))

            # Get email
            email = options.get('email') or input('Email: ')
            if not email:
                raise CommandError('Email is required')

            # Check if email already exists
            if CustomUser.objects.filter(email=email).exists():
                raise CommandError(f'User with email {email} already exists')

            # Get phone number
            phone = options.get('phone') or input('Phone (+254712345678): ')
            if not phone:
                raise CommandError('Phone number is required')

            # Normalize phone number
            from common.utils import normalize_kenyan_phone, validate_kenyan_phone
            if not validate_kenyan_phone(phone):
                raise CommandError('Invalid Kenyan phone number format')
            phone = normalize_kenyan_phone(phone)

            # Check if phone already exists
            if CustomUser.objects.filter(phone_number=phone).exists():
                raise CommandError(f'User with phone {phone} already exists')

            # Get name
            first_name = options.get('first_name') or input('First Name: ')
            last_name = options.get('last_name') or input('Last Name: ')

            # Show available employers
            employers = Employer.objects.filter(is_active=True)
            if not employers.exists():
                raise CommandError('No active employers found. Please create an employer first.')

            self.stdout.write(self.style.SUCCESS('\nAvailable Employers:'))
            for i, emp in enumerate(employers, 1):
                self.stdout.write(f'  {i}. {emp.name} (ID: {emp.id})')

            # Get employer
            employer_id = options.get('employer_id')
            if not employer_id:
                employer_choice = input('\nSelect employer number (or enter UUID): ')
                try:
                    # Try as number first
                    choice_num = int(employer_choice)
                    if 1 <= choice_num <= employers.count():
                        employer = list(employers)[choice_num - 1]
                        employer_id = employer.id
                    else:
                        raise CommandError('Invalid employer number')
                except ValueError:
                    # Try as UUID
                    employer_id = employer_choice

            # Validate employer exists
            try:
                employer = Employer.objects.get(id=employer_id, is_active=True)
            except Employer.DoesNotExist:
                raise CommandError(f'Employer with ID {employer_id} not found or inactive')

            # Get password
            password = None
            while not password:
                password1 = getpass.getpass('Password: ')
                password2 = getpass.getpass('Password (again): ')

                if password1 != password2:
                    self.stdout.write(self.style.ERROR('Passwords do not match. Try again.'))
                    continue

                if len(password1) < 8:
                    self.stdout.write(self.style.ERROR('Password must be at least 8 characters. Try again.'))
                    continue

                password = password1

        # Non-interactive mode
        else:
            email = options.get('email')
            phone = options.get('phone')
            first_name = options.get('first_name')
            last_name = options.get('last_name')
            password = options.get('password')
            employer_id = options.get('employer_id')

            if not all([email, phone, first_name, last_name, password, employer_id]):
                raise CommandError(
                    'In non-interactive mode, all arguments are required: '
                    '--email, --phone, --first-name, --last-name, --password, --employer-id'
                )

            # Normalize phone number
            from common.utils import normalize_kenyan_phone, validate_kenyan_phone
            if not validate_kenyan_phone(phone):
                raise CommandError('Invalid Kenyan phone number format')
            phone = normalize_kenyan_phone(phone)

            # Check if user exists
            if CustomUser.objects.filter(email=email).exists():
                raise CommandError(f'User with email {email} already exists')
            if CustomUser.objects.filter(phone_number=phone).exists():
                raise CommandError(f'User with phone {phone} already exists')

            # Validate employer exists
            try:
                employer = Employer.objects.get(id=employer_id, is_active=True)
            except Employer.DoesNotExist:
                raise CommandError(f'Employer with ID {employer_id} not found or inactive')

        # Create HR manager user
        try:
            with transaction.atomic():
                hr_user = CustomUser.objects.create(
                    username=email,
                    email=email,
                    phone_number=phone,
                    first_name=first_name,
                    last_name=last_name,
                    role=CustomUser.Role.HR_MANAGER,
                    is_staff=False,
                    is_superuser=False,
                    is_active=True,
                    is_phone_verified=True,  # Pre-verify phone for HR
                )
                hr_user.set_password(password)
                hr_user.save()

                # Create HR profile linked to employer
                hr_profile = HRProfile.objects.create(
                    user=hr_user,
                    employer=employer,
                    department='Human Resources',
                )

                self.stdout.write(self.style.SUCCESS(f'\n✓ HR Manager user created successfully!'))
                self.stdout.write(self.style.SUCCESS(f'  Email: {email}'))
                self.stdout.write(self.style.SUCCESS(f'  Phone: {phone}'))
                self.stdout.write(self.style.SUCCESS(f'  Name: {first_name} {last_name}'))
                self.stdout.write(self.style.SUCCESS(f'  Role: HR Manager'))
                self.stdout.write(self.style.SUCCESS(f'  Employer: {employer.name}'))
                self.stdout.write(self.style.SUCCESS(f'\nYou can now log in at: /api/v1/auth/hr/login/'))
                self.stdout.write(self.style.WARNING(f'Note: OTP will be sent to {phone} during login\n'))

                # Send welcome email
                try:
                    send_welcome_email(
                        to_address=email,
                        user_name=f'{first_name} {last_name}',
                        role='HR Manager'
                    )
                    self.stdout.write(self.style.SUCCESS(f'✓ Welcome email sent to {email}'))
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'⚠ Failed to send welcome email: {str(e)}'))

                # Send internal alert
                try:
                    alert_message = f"""
                    <p><strong>New HR Manager Created</strong></p>
                    <ul>
                        <li><strong>Name:</strong> {first_name} {last_name}</li>
                        <li><strong>Email:</strong> {email}</li>
                        <li><strong>Phone:</strong> {phone}</li>
                        <li><strong>Employer:</strong> {employer.name}</li>
                        <li><strong>Department:</strong> {hr_profile.department}</li>
                    </ul>
                    """
                    send_internal_alert(
                        subject=f'New HR Manager Created - {employer.name}',
                        message=alert_message,
                        alert_type='info'
                    )
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'⚠ Failed to send internal alert: {str(e)}'))

        except Exception as e:
            raise CommandError(f'Failed to create HR manager user: {str(e)}')
