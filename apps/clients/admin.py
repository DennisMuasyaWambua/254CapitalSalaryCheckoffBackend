"""
Django admin configuration for client management.
"""

from django.contrib import admin
from .models import ExistingClient


@admin.register(ExistingClient)
class ExistingClientAdmin(admin.ModelAdmin):
    """Admin interface for ExistingClient model."""

    list_display = [
        'full_name',
        'national_id',
        'mobile',
        'employer',
        'loan_amount',
        'outstanding_balance',
        'loan_status',
        'approval_status',
        'created_at',
    ]

    list_filter = [
        'approval_status',
        'loan_status',
        'employer',
        'created_at',
    ]

    search_fields = [
        'full_name',
        'national_id',
        'mobile',
        'email',
        'employee_id',
    ]

    readonly_fields = [
        'id',
        'total_due',
        'monthly_deduction',
        'outstanding_balance',
        'created_at',
        'updated_at',
    ]

    fieldsets = (
        ('Personal Information', {
            'fields': (
                'full_name',
                'national_id',
                'mobile',
                'email',
            )
        }),
        ('Employment Details', {
            'fields': (
                'employer',
                'employee_id',
            )
        }),
        ('Loan Details', {
            'fields': (
                'loan_amount',
                'interest_rate',
                'start_date',
                'repayment_period',
                'disbursement_date',
                'disbursement_method',
            )
        }),
        ('Calculated Fields', {
            'fields': (
                'total_due',
                'monthly_deduction',
                'amount_paid',
                'outstanding_balance',
            )
        }),
        ('Status', {
            'fields': (
                'loan_status',
                'approval_status',
                'rejection_reason',
            )
        }),
        ('Metadata', {
            'fields': (
                'id',
                'entered_by',
                'created_at',
                'updated_at',
            )
        }),
    )

    def has_delete_permission(self, request, obj=None):
        """Only admins can delete client records."""
        return request.user.is_superuser
