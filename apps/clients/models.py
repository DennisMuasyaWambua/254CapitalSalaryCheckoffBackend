"""
Client management models for existing client records.
"""

import uuid
from django.db import models
from decimal import Decimal


class ExistingClient(models.Model):
    """
    Model representing an existing client record.

    Used for manual data entry of clients with existing loans
    that need to be migrated into the system.
    """

    LOAN_STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Fully Paid', 'Fully Paid'),
        ('Defaulted', 'Defaulted'),
        ('Restructured', 'Restructured'),
    ]

    APPROVAL_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    DISBURSEMENT_METHOD_CHOICES = [
        ('mpesa', 'M-Pesa'),
        ('bank', 'Bank Transfer'),
        ('cash', 'Cash'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=255, help_text='Full name of the client')
    national_id = models.CharField(max_length=20, help_text='National ID number')
    mobile = models.CharField(max_length=15, help_text='Mobile phone number')
    email = models.EmailField(blank=True, null=True, help_text='Email address (optional)')
    employer = models.ForeignKey(
        'employers.Employer',
        on_delete=models.CASCADE,
        related_name='existing_clients',
        help_text='Employer organization'
    )
    employee_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Employee ID at employer organization'
    )

    # Loan Details
    loan_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Original loan amount (principal)'
    )
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text='Interest rate as percentage (e.g., 5 for 5%)'
    )
    start_date = models.DateField(help_text='Loan start date')
    repayment_period = models.IntegerField(help_text='Repayment period in months')
    disbursement_date = models.DateField(help_text='Date when loan was disbursed')
    disbursement_method = models.CharField(
        max_length=10,
        choices=DISBURSEMENT_METHOD_CHOICES,
        help_text='Method of disbursement'
    )

    # Calculated Fields
    total_due = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Total amount due (principal + interest)'
    )
    monthly_deduction = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Monthly deduction amount'
    )
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='Amount paid so far'
    )
    outstanding_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Outstanding balance'
    )

    # Status
    loan_status = models.CharField(
        max_length=20,
        choices=LOAN_STATUS_CHOICES,
        default='Active',
        help_text='Current loan status'
    )
    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default='pending',
        help_text='Approval status for this record'
    )

    # Metadata
    entered_by = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Name of admin who entered this record'
    )
    rejection_reason = models.TextField(
        blank=True,
        null=True,
        help_text='Reason for rejection if rejected'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'existing_clients'
        ordering = ['-created_at']
        verbose_name = 'Existing Client'
        verbose_name_plural = 'Existing Clients'
        indexes = [
            models.Index(fields=['approval_status']),
            models.Index(fields=['loan_status']),
            models.Index(fields=['employer']),
            models.Index(fields=['national_id']),
            models.Index(fields=['mobile']),
        ]

    def __str__(self):
        return f"{self.full_name} - {self.employer.name}"

    def save(self, *args, **kwargs):
        """Calculate totals before saving."""
        # Calculate interest
        interest = self.loan_amount * (self.interest_rate / Decimal('100'))

        # Calculate total due
        self.total_due = self.loan_amount + interest

        # Calculate monthly deduction
        self.monthly_deduction = self.total_due / Decimal(str(self.repayment_period))

        # Calculate outstanding balance
        self.outstanding_balance = self.total_due - self.amount_paid

        super().save(*args, **kwargs)

    @property
    def is_fully_paid(self):
        """Check if loan is fully paid."""
        return self.outstanding_balance <= Decimal('0.00')

    @property
    def payment_progress_percentage(self):
        """Calculate payment progress as percentage."""
        if self.total_due <= Decimal('0.00'):
            return Decimal('0.00')
        return (self.amount_paid / self.total_due) * Decimal('100')
