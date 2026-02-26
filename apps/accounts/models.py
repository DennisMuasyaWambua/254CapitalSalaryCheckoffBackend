"""
User and profile models for the 254 Capital system.
"""

import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from common.utils import validate_kenyan_phone, normalize_kenyan_phone, validate_national_id


class CustomUser(AbstractUser):
    """
    Custom user model extending Django's AbstractUser.

    Supports three user roles:
    - employee: Can apply for loans, track applications
    - hr_manager: Can review applications for their employer
    - admin: Full system access (254 Capital staff)
    """

    class Role(models.TextChoices):
        EMPLOYEE = 'employee', 'Employee'
        HR_MANAGER = 'hr_manager', 'HR Manager'
        ADMIN = 'admin', 'Admin'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.EMPLOYEE,
        db_index=True
    )
    phone_number = models.CharField(
        max_length=20,
        unique=True,
        help_text='Phone number in format +254712345678'
    )
    national_id = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text='Kenyan National ID number'
    )
    is_phone_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Override username to make it optional for employees (who use phone)
    username = models.CharField(
        max_length=150,
        unique=True,
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['phone_number']),
            models.Index(fields=['national_id']),
            models.Index(fields=['role']),
            models.Index(fields=['is_phone_verified']),
        ]
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        if self.get_full_name():
            return f'{self.get_full_name()} ({self.role})'
        return f'{self.phone_number} ({self.role})'

    def save(self, *args, **kwargs):
        """
        Override save to normalize phone number and set username for employees.
        """
        # Normalize phone number
        if self.phone_number:
            self.phone_number = normalize_kenyan_phone(self.phone_number)

        # For employees, use phone number as username if not set
        if self.role == self.Role.EMPLOYEE and not self.username:
            self.username = self.phone_number

        # For HR/Admin, ensure username is set
        if self.role in [self.Role.HR_MANAGER, self.Role.ADMIN] and not self.username:
            raise ValueError('Username is required for HR managers and admins')

        super().save(*args, **kwargs)

    @property
    def is_employee(self):
        """Check if user is an employee."""
        return self.role == self.Role.EMPLOYEE

    @property
    def is_hr_manager(self):
        """Check if user is an HR manager."""
        return self.role == self.Role.HR_MANAGER

    @property
    def is_admin_user(self):
        """Check if user is an admin."""
        return self.role == self.Role.ADMIN

    def get_profile(self):
        """Get the user's role-specific profile."""
        if self.is_employee:
            return getattr(self, 'employee_profile', None)
        elif self.is_hr_manager:
            return getattr(self, 'hr_profile', None)
        return None


class EmployeeProfile(models.Model):
    """
    Profile for employee users.

    Stores employment details, salary information, and bank account details
    for loan applications and disbursements.
    """

    class EmploymentType(models.TextChoices):
        CONFIRMED = 'confirmed', 'Confirmed Staff'
        CONTRACT = 'contract', 'Contract Staff'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='employee_profile'
    )
    employer = models.ForeignKey(
        'employers.Employer',
        on_delete=models.PROTECT,
        related_name='employees'
    )
    employee_id = models.CharField(
        max_length=50,
        help_text='Employee ID assigned by the employer'
    )
    department = models.CharField(max_length=100, blank=True)

    # Employment details
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.CONFIRMED,
        db_index=True,
        help_text='Type of employment: confirmed or contract staff'
    )
    contract_end_date = models.DateField(
        null=True,
        blank=True,
        help_text='Contract end date for contract employees'
    )

    # Contact information
    work_email = models.EmailField(
        blank=True,
        help_text='Work email address'
    )
    personal_email = models.EmailField(
        blank=True,
        help_text='Personal email address'
    )
    residential_location = models.CharField(
        max_length=255,
        blank=True,
        help_text='Residential location/address'
    )

    monthly_gross_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Monthly gross salary in KES'
    )

    # Bank account details for disbursement
    bank_name = models.CharField(max_length=100)
    bank_account_number = models.CharField(max_length=50)

    # M-Pesa number for alternative disbursement
    mpesa_number = models.CharField(
        max_length=20,
        blank=True,
        help_text='M-Pesa number (usually same as phone number)'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'employee_profiles'
        unique_together = [['employer', 'employee_id']]
        indexes = [
            models.Index(fields=['employer', 'employee_id']),
            models.Index(fields=['employment_type']),
            models.Index(fields=['contract_end_date']),
        ]
        verbose_name = 'Employee Profile'
        verbose_name_plural = 'Employee Profiles'

    def __str__(self):
        return f'{self.user.get_full_name()} - {self.employer.name} ({self.employee_id})'

    def save(self, *args, **kwargs):
        """Validate contract end date and normalize M-Pesa number."""
        # Validate that contract employees have a contract end date
        if self.employment_type == self.EmploymentType.CONTRACT and not self.contract_end_date:
            from django.core.exceptions import ValidationError
            raise ValidationError('Contract end date is required for contract employees')

        # Normalize M-Pesa number if provided
        if self.mpesa_number:
            self.mpesa_number = normalize_kenyan_phone(self.mpesa_number)
        super().save(*args, **kwargs)

    @property
    def is_confirmed_staff(self):
        """Check if employee is confirmed staff."""
        return self.employment_type == self.EmploymentType.CONFIRMED

    @property
    def is_contract_staff(self):
        """Check if employee is contract staff."""
        return self.employment_type == self.EmploymentType.CONTRACT

    @property
    def is_loan_eligible(self):
        """Check if employee is eligible for loans (confirmed staff only)."""
        return self.employment_type == self.EmploymentType.CONFIRMED

    @property
    def contract_expiring_soon(self):
        """Check if contract is expiring within 30 days."""
        if not self.is_contract_staff or not self.contract_end_date:
            return False
        from django.utils import timezone
        from datetime import timedelta
        days_until_expiry = (self.contract_end_date - timezone.now().date()).days
        return 0 <= days_until_expiry <= 30

    @property
    def days_until_contract_expiry(self):
        """Get number of days until contract expiry."""
        if not self.is_contract_staff or not self.contract_end_date:
            return None
        from django.utils import timezone
        return (self.contract_end_date - timezone.now().date()).days


class HRProfile(models.Model):
    """
    Profile for HR manager users.

    Links HR users to their employer organization.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='hr_profile'
    )
    employer = models.ForeignKey(
        'employers.Employer',
        on_delete=models.PROTECT,
        related_name='hr_managers'
    )
    department = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_profiles'
        verbose_name = 'HR Profile'
        verbose_name_plural = 'HR Profiles'

    def __str__(self):
        return f'{self.user.get_full_name()} - {self.employer.name} (HR)'
