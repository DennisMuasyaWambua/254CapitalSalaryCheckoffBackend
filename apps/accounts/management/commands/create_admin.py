"""
Django management command to create an admin user.

Usage:
    python manage.py create_admin

This command creates an admin user for the 254 Capital system with:
- Admin role
- Email/password authentication
- OTP login capability
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.accounts.models import CustomUser
from common.email_service import send_welcome_email, send_internal_alert
import getpass


class Command(BaseCommand):
    help = 'Create an admin user for 254 Capital system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            help='Admin email address',
        )
        parser.add_argument(
            '--phone',
            type=str,
            help='Admin phone number (format: +254712345678 or 0712345678)',
        )
        parser.add_argument(
            '--first-name',
            type=str,
            help='Admin first name',
        )
        parser.add_argument(
            '--last-name',
            type=str,
            help='Admin last name',
        )
        parser.add_argument(
            '--password',
            type=str,
            help='Admin password (not recommended for security - use interactive mode)',
        )
        parser.add_argument(
            '--noinput',
            action='store_true',
            help='Non-interactive mode (requires all arguments)',
        )

    def handle(self, *args, **options):
        """Create admin user."""

        # Interactive mode
        if not options['noinput']:
            self.stdout.write(self.style.WARNING('\n=== Create Admin User ===\n'))

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

            if not all([email, phone, first_name, last_name, password]):
                raise CommandError(
                    'In non-interactive mode, all arguments are required: '
                    '--email, --phone, --first-name, --last-name, --password'
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

        # Create admin user
        try:
            with transaction.atomic():
                admin = CustomUser.objects.create(
                    username=email,
                    email=email,
                    phone_number=phone,
                    first_name=first_name,
                    last_name=last_name,
                    role=CustomUser.Role.ADMIN,
                    is_staff=True,
                    is_superuser=True,
                    is_active=True,
                    is_phone_verified=True,  # Pre-verify phone for admin
                )
                admin.set_password(password)
                admin.save()

                self.stdout.write(self.style.SUCCESS(f'\n✓ Admin user created successfully!'))
                self.stdout.write(self.style.SUCCESS(f'  Email: {email}'))
                self.stdout.write(self.style.SUCCESS(f'  Phone: {phone}'))
                self.stdout.write(self.style.SUCCESS(f'  Name: {first_name} {last_name}'))
                self.stdout.write(self.style.SUCCESS(f'  Role: Admin'))
                self.stdout.write(self.style.SUCCESS(f'  Superuser: Yes'))
                self.stdout.write(self.style.SUCCESS(f'\nYou can now log in at: /api/v1/auth/admin/login/'))
                self.stdout.write(self.style.WARNING(f'Note: OTP will be sent to {phone} during login\n'))

                # Send welcome email
                try:
                    send_welcome_email(
                        to_address=email,
                        user_name=f'{first_name} {last_name}',
                        role='Admin'
                    )
                    self.stdout.write(self.style.SUCCESS(f'✓ Welcome email sent to {email}'))
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'⚠ Failed to send welcome email: {str(e)}'))

                # Send internal alert
                try:
                    alert_message = f"""
                    <p><strong>New Admin User Created</strong></p>
                    <ul>
                        <li><strong>Name:</strong> {first_name} {last_name}</li>
                        <li><strong>Email:</strong> {email}</li>
                        <li><strong>Phone:</strong> {phone}</li>
                        <li><strong>Superuser:</strong> Yes</li>
                    </ul>
                    """
                    send_internal_alert(
                        subject=f'New Admin User Created - {first_name} {last_name}',
                        message=alert_message,
                        alert_type='info'
                    )
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'⚠ Failed to send internal alert: {str(e)}'))

        except Exception as e:
            raise CommandError(f'Failed to create admin user: {str(e)}')
