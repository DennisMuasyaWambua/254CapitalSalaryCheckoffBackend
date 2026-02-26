"""
Reconciliation and remittance models.
"""

import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal


class Remittance(models.Model):
    """
    Model for employer remittance submissions.

    HR managers submit remittances confirming salary deductions made
    for a specific period.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending Confirmation'
        CONFIRMED = 'confirmed', 'Confirmed'
        DISPUTED = 'disputed', 'Disputed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer = models.ForeignKey(
        'employers.Employer',
        on_delete=models.PROTECT,
        related_name='remittances'
    )
    submitted_by = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='submitted_remittances',
        limit_choices_to={'role': 'hr_manager'},
        help_text='HR manager who submitted this remittance'
    )

    # Period details
    period_month = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text='Month of remittance (1-12)'
    )
    period_year = models.IntegerField(
        help_text='Year of remittance'
    )

    # Payment details
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Total amount remitted in KES'
    )
    proof_document = models.FileField(
        upload_to='remittance_proofs/',
        help_text='Proof of payment (bank slip, transfer receipt, etc.)'
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True
    )
    confirmed_by = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_remittances',
        limit_choices_to={'role': 'admin'},
        help_text='Admin who confirmed this remittance'
    )
    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When this remittance was confirmed'
    )
    notes = models.TextField(
        blank=True,
        help_text='Notes or comments about this remittance'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'remittances'
        unique_together = [['employer', 'period_month', 'period_year']]
        ordering = ['-period_year', '-period_month', '-created_at']
        verbose_name = 'Remittance'
        verbose_name_plural = 'Remittances'
        indexes = [
            models.Index(fields=['employer', 'period_year', 'period_month']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.employer.name} - {self.period_month}/{self.period_year} (KES {self.total_amount:,.2f})'

    @property
    def period_display(self):
        """Get human-readable period display."""
        from datetime import date
        month_name = date(self.period_year, self.period_month, 1).strftime('%B')
        return f'{month_name} {self.period_year}'

    @property
    def reconciliation_status(self):
        """Get reconciliation status summary."""
        records = self.reconciliation_records.all()
        if not records.exists():
            return 'Not reconciled'

        total_records = records.count()
        matched_records = records.filter(is_matched=True).count()

        if matched_records == total_records:
            return 'Fully reconciled'
        elif matched_records > 0:
            return f'Partially reconciled ({matched_records}/{total_records})'
        else:
            return 'Unreconciled'


class ReconciliationRecord(models.Model):
    """
    Model for individual loan reconciliation records within a remittance.

    Tracks whether each expected deduction was included in the remittance.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    remittance = models.ForeignKey(
        Remittance,
        on_delete=models.CASCADE,
        related_name='reconciliation_records'
    )
    loan_application = models.ForeignKey(
        'loans.LoanApplication',
        on_delete=models.PROTECT,
        related_name='reconciliation_records'
    )

    # Reconciliation details
    expected_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Expected deduction amount for this loan'
    )
    received_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Actual amount received (if matched)'
    )
    is_matched = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Whether expected and received amounts match'
    )
    notes = models.TextField(
        blank=True,
        help_text='Notes about this reconciliation record'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reconciliation_records'
        unique_together = [['remittance', 'loan_application']]
        ordering = ['loan_application__application_number']
        verbose_name = 'Reconciliation Record'
        verbose_name_plural = 'Reconciliation Records'
        indexes = [
            models.Index(fields=['remittance', 'is_matched']),
        ]

    def __str__(self):
        status = 'Matched' if self.is_matched else 'Unmatched'
        return f'{self.loan_application.application_number} - {status}'

    @property
    def variance(self):
        """Calculate variance between expected and received amounts."""
        return self.received_amount - self.expected_amount

    @property
    def variance_percentage(self):
        """Calculate variance as a percentage of expected amount."""
        if self.expected_amount == 0:
            return Decimal('0.00')
        return (self.variance / self.expected_amount) * 100
