"""
Django admin configuration for reconciliation.
"""

from django.contrib import admin
from .models import Remittance, ReconciliationRecord


class ReconciliationRecordInline(admin.TabularInline):
    """Inline display of reconciliation records."""
    model = ReconciliationRecord
    extra = 0
    readonly_fields = ['loan_application', 'expected_amount', 'received_amount', 'is_matched', 'variance']
    fields = ['loan_application', 'expected_amount', 'received_amount', 'is_matched', 'notes']


@admin.register(Remittance)
class RemittanceAdmin(admin.ModelAdmin):
    """Admin interface for Remittance model."""

    list_display = [
        'employer', 'period_display', 'total_amount', 'status',
        'submitted_by', 'confirmed_by', 'created_at', 'confirmed_at'
    ]
    list_filter = ['status', 'period_year', 'period_month', 'employer', 'created_at']
    search_fields = ['employer__name', 'submitted_by__first_name', 'submitted_by__last_name']
    readonly_fields = ['submitted_by', 'confirmed_by', 'confirmed_at', 'created_at', 'updated_at', 'reconciliation_status']
    raw_id_fields = ['employer', 'submitted_by', 'confirmed_by']
    ordering = ['-period_year', '-period_month', '-created_at']
    inlines = [ReconciliationRecordInline]

    fieldsets = (
        ('Period', {
            'fields': ('employer', 'period_month', 'period_year')
        }),
        ('Payment', {
            'fields': ('total_amount', 'proof_document')
        }),
        ('Status', {
            'fields': ('status', 'notes', 'reconciliation_status')
        }),
        ('Audit', {
            'fields': ('submitted_by', 'created_at', 'confirmed_by', 'confirmed_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ReconciliationRecord)
class ReconciliationRecordAdmin(admin.ModelAdmin):
    """Admin interface for ReconciliationRecord model."""

    list_display = [
        'remittance', 'loan_application', 'expected_amount',
        'received_amount', 'is_matched', 'variance', 'created_at'
    ]
    list_filter = ['is_matched', 'remittance__employer', 'created_at']
    search_fields = [
        'loan_application__application_number',
        'loan_application__employee__first_name',
        'loan_application__employee__last_name',
        'remittance__employer__name'
    ]
    readonly_fields = ['variance', 'variance_percentage', 'created_at', 'updated_at']
    raw_id_fields = ['remittance', 'loan_application']
    ordering = ['-created_at']

    fieldsets = (
        ('Reconciliation', {
            'fields': ('remittance', 'loan_application', 'expected_amount', 'received_amount', 'is_matched')
        }),
        ('Variance', {
            'fields': ('variance', 'variance_percentage', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
