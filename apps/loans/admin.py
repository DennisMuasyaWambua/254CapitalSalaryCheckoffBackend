"""
Django admin configuration for loan models.
"""

from django.contrib import admin
from .models import LoanApplication, LoanStatusHistory, RepaymentSchedule


class LoanStatusHistoryInline(admin.TabularInline):
    """Inline display of status history."""
    model = LoanStatusHistory
    extra = 0
    readonly_fields = ['status', 'actor', 'comment', 'created_at']
    can_delete = False


class RepaymentScheduleInline(admin.TabularInline):
    """Inline display of repayment schedule."""
    model = RepaymentSchedule
    extra = 0
    readonly_fields = ['installment_number', 'due_date', 'amount', 'running_balance', 'is_first_deduction', 'is_paid', 'paid_date']
    can_delete = False


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    """Admin interface for LoanApplication model."""

    list_display = [
        'application_number', 'employee', 'employer', 'principal_amount',
        'total_repayment', 'monthly_deduction', 'repayment_months',
        'status', 'disbursement_date', 'created_at'
    ]
    list_filter = ['status', 'repayment_months', 'employer', 'disbursement_method', 'created_at']
    search_fields = ['application_number', 'employee__first_name', 'employee__last_name', 'employee__phone_number', 'employer__name']
    readonly_fields = [
        'application_number', 'employee', 'employer', 'total_repayment',
        'monthly_deduction', 'created_at', 'updated_at'
    ]
    ordering = ['-created_at']
    inlines = [LoanStatusHistoryInline, RepaymentScheduleInline]

    fieldsets = (
        ('Application Info', {
            'fields': ('application_number', 'employee', 'employer', 'status', 'purpose')
        }),
        ('Loan Details', {
            'fields': ('principal_amount', 'interest_rate', 'repayment_months', 'total_repayment', 'monthly_deduction')
        }),
        ('Disbursement', {
            'fields': ('disbursement_date', 'first_deduction_date', 'disbursement_method', 'disbursement_reference'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(LoanStatusHistory)
class LoanStatusHistoryAdmin(admin.ModelAdmin):
    """Admin interface for LoanStatusHistory model."""

    list_display = ['application', 'status', 'actor', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['application__application_number', 'actor__first_name', 'actor__last_name']
    readonly_fields = ['application', 'status', 'actor', 'comment', 'created_at']
    ordering = ['-created_at']


@admin.register(RepaymentSchedule)
class RepaymentScheduleAdmin(admin.ModelAdmin):
    """Admin interface for RepaymentSchedule model."""

    list_display = [
        'loan', 'installment_number', 'due_date', 'amount',
        'running_balance', 'is_first_deduction', 'is_paid', 'paid_date'
    ]
    list_filter = ['is_paid', 'is_first_deduction', 'due_date']
    search_fields = ['loan__application_number', 'loan__employee__first_name', 'loan__employee__last_name']
    readonly_fields = ['loan', 'installment_number', 'due_date', 'amount', 'running_balance', 'is_first_deduction']
    ordering = ['loan', 'installment_number']
