"""
Django admin configuration for employers.
"""

from django.contrib import admin
from .models import Employer


@admin.register(Employer)
class EmployerAdmin(admin.ModelAdmin):
    """Admin interface for Employer model."""

    list_display = [
        'name', 'registration_number', 'payroll_cycle_day',
        'hr_contact_name', 'hr_contact_email', 'is_active',
        'onboarded_by', 'onboarded_at'
    ]
    list_filter = ['is_active', 'payroll_cycle_day', 'onboarded_at']
    search_fields = ['name', 'registration_number', 'hr_contact_name', 'hr_contact_email']
    readonly_fields = ['onboarded_by', 'onboarded_at', 'updated_at']
    ordering = ['name']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'registration_number', 'address', 'is_active')
        }),
        ('Payroll Configuration', {
            'fields': ('payroll_cycle_day',)
        }),
        ('HR Contact', {
            'fields': ('hr_contact_name', 'hr_contact_email', 'hr_contact_phone')
        }),
        ('Audit', {
            'fields': ('onboarded_by', 'onboarded_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
