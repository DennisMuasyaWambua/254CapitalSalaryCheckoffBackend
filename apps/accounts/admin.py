"""
Django admin configuration for accounts models.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import CustomUser, EmployeeProfile, HRProfile


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    """Admin interface for CustomUser model."""

    list_display = ['username', 'phone_number', 'email', 'role', 'is_phone_verified', 'is_active', 'date_joined']
    list_filter = ['role', 'is_phone_verified', 'is_active', 'is_staff']
    search_fields = ['username', 'phone_number', 'email', 'first_name', 'last_name', 'national_id']
    ordering = ['-date_joined']

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email', 'phone_number', 'national_id')}),
        ('Role & Status', {'fields': ('role', 'is_phone_verified', 'is_active', 'is_staff', 'is_superuser')}),
        ('Permissions', {'fields': ('groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'phone_number', 'role', 'password1', 'password2'),
        }),
    )


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    """Admin interface for EmployeeProfile model."""

    list_display = ['user', 'employer', 'employee_id', 'department', 'monthly_gross_salary', 'created_at']
    list_filter = ['employer', 'created_at']
    search_fields = ['user__first_name', 'user__last_name', 'user__phone_number', 'employee_id', 'employer__name']
    raw_id_fields = ['user', 'employer']
    ordering = ['-created_at']

    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Employment', {'fields': ('employer', 'employee_id', 'department', 'monthly_gross_salary')}),
        ('Banking', {'fields': ('bank_name', 'bank_account_number', 'mpesa_number')}),
    )


@admin.register(HRProfile)
class HRProfileAdmin(admin.ModelAdmin):
    """Admin interface for HRProfile model."""

    list_display = ['user', 'employer', 'department', 'created_at']
    list_filter = ['employer', 'created_at']
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'employer__name']
    raw_id_fields = ['user', 'employer']
    ordering = ['-created_at']

    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Employment', {'fields': ('employer', 'department')}),
    )
