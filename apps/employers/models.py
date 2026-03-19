"""
Employer organization models.
"""

import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from common.utils import normalize_kenyan_phone


class Employer(models.Model):
    """
    Model representing an employer organization.

    Employers are onboarded by 254 Capital admins and have a check-off agreement
    for salary deductions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text='Company/Organization name'
    )
    registration_number = models.CharField(
        max_length=100,
        unique=True,
        help_text='Company registration number'
    )
    address = models.TextField(help_text='Physical address')

    # Payroll configuration
    payroll_cycle_day = models.IntegerField(
        default=25,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text='Day of month when payroll is processed (default: 25th)'
    )

    # HR contact information
    hr_contact_name = models.CharField(max_length=255)
    hr_contact_email = models.EmailField()
    hr_contact_phone = models.CharField(max_length=20)

    # Status and audit fields
    is_active = models.BooleanField(
        default=True,
        help_text='Whether the employer is currently active in the system'
    )
    onboarded_by = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='onboarded_employers',
        help_text='254 Capital admin who onboarded this employer'
    )
    onboarded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'employers'
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['name']
        verbose_name = 'Employer'
        verbose_name_plural = 'Employers'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Normalize contact phone number."""
        if self.hr_contact_phone:
            self.hr_contact_phone = normalize_kenyan_phone(self.hr_contact_phone)
        super().save(*args, **kwargs)

