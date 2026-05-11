"""
Django Admin configuration for Company Management models.
"""

from django.contrib import admin
from .models import Organization, Role, OrganizationUser, AuditLog


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Admin interface for Organization model."""

    list_display = ['name', 'is_active', 'contact_email', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'contact_email', 'tax_id']
    readonly_fields = ['id', 'created_at', 'updated_at', 'created_by']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'address', 'contact_email', 'contact_phone', 'tax_id')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """Admin interface for Role model."""

    list_display = ['name', 'organization', 'is_active', 'can_view_loan_application',
                    'can_approve_loan_application', 'can_decline_loan_application']
    list_filter = ['organization', 'is_active', 'can_view_loan_application',
                   'can_approve_loan_application', 'can_decline_loan_application']
    search_fields = ['name', 'description', 'organization__name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'created_by', 'assigned_users_count']
    fieldsets = (
        ('Basic Information', {
            'fields': ('organization', 'name', 'description')
        }),
        ('Permissions', {
            'fields': ('can_view_loan_application', 'can_approve_loan_application',
                      'can_decline_loan_application')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at', 'created_by', 'assigned_users_count'),
            'classes': ('collapse',)
        }),
    )


@admin.register(OrganizationUser)
class OrganizationUserAdmin(admin.ModelAdmin):
    """Admin interface for OrganizationUser model."""

    list_display = ['user', 'organization', 'role', 'is_active', 'force_password_change',
                    'last_login_at']
    list_filter = ['organization', 'role', 'is_active', 'force_password_change']
    search_fields = ['user__email', 'user__first_name', 'user__last_name',
                    'organization__name', 'role__name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'created_by',
                      'password_changed_at', 'last_login_at']
    fieldsets = (
        ('Assignment', {
            'fields': ('organization', 'user', 'role')
        }),
        ('Status', {
            'fields': ('is_active', 'force_password_change')
        }),
        ('Timestamps', {
            'fields': ('password_changed_at', 'last_login_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Admin interface for AuditLog model.

    Read-only to prevent tampering with audit trail.
    """

    list_display = ['event_type', 'user', 'organization', 'result', 'created_at']
    list_filter = ['event_type', 'result', 'organization', 'created_at']
    search_fields = ['event_type', 'user__email', 'target_user__email',
                    'organization__name', 'error_message']
    readonly_fields = ['id', 'event_type', 'user', 'target_user', 'organization',
                      'target_resource_type', 'target_resource_id', 'ip_address',
                      'user_agent', 'result', 'error_message', 'metadata', 'created_at']
    fieldsets = (
        ('Event Information', {
            'fields': ('event_type', 'result', 'error_message')
        }),
        ('Actors', {
            'fields': ('user', 'target_user', 'organization')
        }),
        ('Target Resource', {
            'fields': ('target_resource_type', 'target_resource_id')
        }),
        ('Request Context', {
            'fields': ('ip_address', 'user_agent')
        }),
        ('Additional Data', {
            'fields': ('metadata',)
        }),
        ('Timestamp', {
            'fields': ('created_at',)
        }),
    )

    def has_add_permission(self, request):
        """Prevent manual creation of audit logs."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of audit logs."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent modification of audit logs."""
        return False
