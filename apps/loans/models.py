"""
Loan application and repayment models.
"""

import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from django.conf import settings


class LoanApplication(models.Model):
    """
    Model representing a loan application.

    Tracks the complete lifecycle of a loan from application to disbursement
    and repayment.
    """

    class Status(models.TextChoices):
        SUBMITTED = 'submitted', 'Submitted'
        UNDER_REVIEW_HR = 'under_review_hr', 'Under HR Review'
        UNDER_REVIEW_ADMIN = 'under_review_admin', 'Under 254 Capital Review'
        APPROVED = 'approved', 'Approved'
        DECLINED = 'declined', 'Declined'
        DISBURSED = 'disbursed', 'Disbursed'

    class DisbursementMethod(models.TextChoices):
        BANK = 'bank', 'Bank Transfer'
        MPESA = 'mpesa', 'M-Pesa'

    REPAYMENT_MONTHS_CHOICES = [(3, '3 months'), (6, '6 months'), (9, '9 months'), (12, '12 months')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text='Unique application number (format: 254L + 8 digits)'
    )

    # Relationships
    employee = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.PROTECT,
        related_name='loan_applications',
        limit_choices_to={'role': 'employee'}
    )
    employer = models.ForeignKey(
        'employers.Employer',
        on_delete=models.PROTECT,
        related_name='loan_applications'
    )

    # Loan details
    principal_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal('5000.00')),
            MaxValueValidator(Decimal('5000000.00'))
        ],
        help_text='Loan principal amount in KES (5,000 - 5,000,000)'
    )
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal('0.0500'),
        help_text='Interest rate (default 5% = 0.0500)'
    )
    repayment_months = models.IntegerField(
        choices=REPAYMENT_MONTHS_CHOICES,
        help_text='Number of months for repayment'
    )
    total_repayment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Total amount to be repaid (principal + interest)'
    )
    monthly_deduction = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Monthly salary deduction amount'
    )
    purpose = models.TextField(
        blank=True,
        help_text='Purpose of the loan (optional)'
    )

    # Status tracking
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.SUBMITTED,
        db_index=True
    )

    # Disbursement details
    disbursement_date = models.DateField(
        null=True,
        blank=True,
        help_text='Date when loan was disbursed'
    )
    first_deduction_date = models.DateField(
        null=True,
        blank=True,
        help_text='Date of first salary deduction'
    )
    disbursement_method = models.CharField(
        max_length=10,
        choices=DisbursementMethod.choices,
        null=True,
        blank=True
    )
    disbursement_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text='Transaction reference for disbursement'
    )

    # Terms and conditions acceptance
    terms_accepted = models.BooleanField(
        default=False,
        help_text='Whether the employee has accepted the terms and conditions'
    )
    terms_accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the employee accepted the terms and conditions'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'loan_applications'
        indexes = [
            models.Index(fields=['application_number']),
            models.Index(fields=['status']),
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['employer', 'status']),
            models.Index(fields=['disbursement_date']),
            models.Index(fields=['created_at']),
            models.Index(fields=['terms_accepted']),
        ]
        ordering = ['-created_at']
        verbose_name = 'Loan Application'
        verbose_name_plural = 'Loan Applications'

    def __str__(self):
        return f'{self.application_number} - {self.employee.get_full_name()} (KES {self.principal_amount:,.2f})'

    @property
    def is_active(self):
        """Check if loan is active (disbursed but not fully paid)."""
        return self.status == self.Status.DISBURSED

    @property
    def can_be_edited(self):
        """Check if application can still be edited by employee."""
        return self.status == self.Status.SUBMITTED

    @property
    def can_be_reviewed_by_hr(self):
        """Check if application is ready for HR review."""
        return self.status == self.Status.SUBMITTED

    @property
    def can_be_reviewed_by_admin(self):
        """Check if application is ready for admin credit assessment."""
        return self.status == self.Status.UNDER_REVIEW_ADMIN

    @property
    def can_be_disbursed(self):
        """Check if application is ready for disbursement."""
        return self.status == self.Status.APPROVED

    @property
    def total_paid(self):
        """Calculate total amount paid so far."""
        return sum(
            schedule.amount
            for schedule in self.repayment_schedule.filter(is_paid=True)
        )

    @property
    def outstanding_balance(self):
        """Calculate outstanding balance."""
        if not self.total_repayment:
            return Decimal('0.00')
        return self.total_repayment - self.total_paid


class LoanStatusHistory(models.Model):
    """
    Model tracking status changes for loan applications.

    Maintains an audit trail of all status changes with actor and comments.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name='status_history'
    )
    status = models.CharField(
        max_length=30,
        choices=LoanApplication.Status.choices
    )
    actor = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='loan_status_changes',
        help_text='User who made this status change'
    )
    comment = models.TextField(
        help_text='Comment or reason for status change'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'loan_status_history'
        ordering = ['created_at']
        verbose_name = 'Loan Status History'
        verbose_name_plural = 'Loan Status Histories'
        indexes = [
            models.Index(fields=['application', 'created_at']),
        ]

    def __str__(self):
        return f'{self.application.application_number} - {self.status} - {self.created_at}'


class RepaymentSchedule(models.Model):
    """
    Model representing individual installments in a loan repayment schedule.

    Each loan has multiple repayment schedule entries, one for each month.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    loan = models.ForeignKey(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name='repayment_schedule'
    )
    installment_number = models.IntegerField(
        help_text='Installment number (1, 2, 3, etc.)'
    )
    due_date = models.DateField(
        help_text='Date when this installment is due (usually 25th of month)'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Amount to be deducted for this installment'
    )
    running_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Remaining balance after this installment'
    )
    is_first_deduction = models.BooleanField(
        default=False,
        help_text='Whether this is the first deduction'
    )
    is_paid = models.BooleanField(
        default=False,
        help_text='Whether this installment has been paid'
    )
    paid_date = models.DateField(
        null=True,
        blank=True,
        help_text='Date when this installment was actually paid'
    )

    class Meta:
        db_table = 'repayment_schedules'
        unique_together = [['loan', 'installment_number']]
        ordering = ['installment_number']
        verbose_name = 'Repayment Schedule'
        verbose_name_plural = 'Repayment Schedules'
        indexes = [
            models.Index(fields=['loan', 'installment_number']),
            models.Index(fields=['due_date']),
            models.Index(fields=['is_paid']),
        ]

    def __str__(self):
        return f'{self.loan.application_number} - Installment {self.installment_number} (KES {self.amount:,.2f})'

    @property
    def is_overdue(self):
        """Check if installment is overdue."""
        from django.utils import timezone
        if self.is_paid:
            return False
        return self.due_date < timezone.now().date()


class ManualPayment(models.Model):
    """
    Model for recording manual payments outside the regular payroll cycle.

    Used for tracking ad-hoc payments made by clients such as early payments,
    partial payments, or settlements.
    """

    PAYMENT_METHOD_CHOICES = [
        ('mpesa', 'M-Pesa'),
        ('bank', 'Bank Transfer'),
        ('cash', 'Cash'),
        ('cheque', 'Cheque'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    loan = models.ForeignKey(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name='manual_payments',
        help_text='Loan application this payment is for'
    )
    payment_date = models.DateField(help_text='Date when payment was received')
    amount_received = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Amount received in this payment'
    )
    payment_method = models.CharField(
        max_length=10,
        choices=PAYMENT_METHOD_CHOICES,
        help_text='Method of payment'
    )
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Transaction reference number (e.g., M-Pesa code)'
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text='Additional notes about this payment'
    )
    early_payment_discount_applied = models.BooleanField(
        default=False,
        help_text='Whether early payment discount was applied'
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Discount amount if early payment'
    )
    recorded_by = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='recorded_manual_payments',
        help_text='Admin who recorded this payment'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'manual_payments'
        ordering = ['-payment_date']
        verbose_name = 'Manual Payment'
        verbose_name_plural = 'Manual Payments'
        indexes = [
            models.Index(fields=['loan', 'payment_date']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['payment_method']),
        ]

    def __str__(self):
        return f"Payment KES {self.amount_received:,.2f} for {self.loan.application_number}"
