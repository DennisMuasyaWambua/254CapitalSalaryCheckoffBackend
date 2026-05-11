"""
Company Management models for Role-Based Access Control (RBAC).

This module provides organization-scoped roles with granular permissions
for loan application processing.
"""

import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinLengthValidator
from django.utils import timezone


class Organization(models.Model):
    """
    Organization model representing a company/employer in the system.

    Organizations are isolated entities where roles and users belong to
    a specific organization. This ensures multi-tenant security.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text='Organization name (must be unique)'
    )
    address = models.TextField(
        blank=True,
        help_text='Physical address of the organization'
    )
    contact_email = models.EmailField(
        blank=True,
        help_text='Primary contact email for the organization'
    )
    contact_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text='Primary contact phone number'
    )
    tax_id = models.CharField(
        max_length=50,
        blank=True,
        help_text='Tax identification number'
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text='Whether the organization is currently active'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_organizations',
        help_text='HR admin who created this organization'
    )

    class Meta:
        db_table = 'organizations'
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'Organization'
        verbose_name_plural = 'Organizations'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def active_users_count(self):
        """Count of active users in this organization."""
        return self.organization_users.filter(is_active=True).count()

    @property
    def active_roles_count(self):
        """Count of active roles in this organization."""
        return self.roles.filter(is_active=True).count()


class Role(models.Model):
    """
    Role model with organization-scoped permissions for loan applications.

    Each role belongs to exactly one organization and defines three
    granular permissions: view, approve, and decline loan applications.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='roles',
        help_text='Organization this role belongs to'
    )
    name = models.CharField(
        max_length=100,
        help_text='Role name (e.g., Loan Officer, Reviewer)'
    )
    description = models.TextField(
        blank=True,
        help_text='Description of the role responsibilities'
    )

    # Loan application permissions
    can_view_loan_application = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Can view pending loan application details'
    )
    can_approve_loan_application = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Can approve pending loan applications'
    )
    can_decline_loan_application = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Can decline pending loan applications'
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text='Whether this role is currently active'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_roles',
        help_text='HR admin who created this role'
    )

    class Meta:
        db_table = 'roles'
        unique_together = [['organization', 'name']]
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['organization', 'name']),
            models.Index(fields=['can_view_loan_application']),
            models.Index(fields=['can_approve_loan_application']),
            models.Index(fields=['can_decline_loan_application']),
        ]
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'
        ordering = ['organization', 'name']

    def __str__(self):
        return f'{self.name} ({self.organization.name})'

    @property
    def has_any_permission(self):
        """Check if role has at least one permission."""
        return (
            self.can_view_loan_application or
            self.can_approve_loan_application or
            self.can_decline_loan_application
        )

    @property
    def assigned_users_count(self):
        """Count of users assigned to this role."""
        return self.organization_users.filter(is_active=True).count()

    def get_permissions_list(self):
        """Get list of permission names granted by this role."""
        permissions = []
        if self.can_view_loan_application:
            permissions.append('view_loan_application')
        if self.can_approve_loan_application:
            permissions.append('approve_loan_application')
        if self.can_decline_loan_application:
            permissions.append('decline_loan_application')
        return permissions


class OrganizationUser(models.Model):
    """
    Organization User model linking users to organizations with assigned roles.

    This is the core RBAC model that associates a user with an organization
    and grants them permissions through a role. Users created through this
    system will have restricted access based on their role permissions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='organization_users',
        help_text='Organization this user belongs to'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organization_memberships',
        help_text='User account'
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name='organization_users',
        help_text='Role assigned to this user'
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text='Whether this user membership is active'
    )
    force_password_change = models.BooleanField(
        default=True,
        help_text='Whether user must change password on first login'
    )
    password_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of last password change'
    )
    last_login_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of last successful login'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_organization_users',
        help_text='HR admin who created this user'
    )

    class Meta:
        db_table = 'organization_users'
        unique_together = [['organization', 'user']]
        indexes = [
            models.Index(fields=['organization', 'user']),
            models.Index(fields=['organization', 'role']),
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['force_password_change']),
        ]
        verbose_name = 'Organization User'
        verbose_name_plural = 'Organization Users'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.get_full_name()} - {self.role.name} @ {self.organization.name}'

    def save(self, *args, **kwargs):
        """
        Validate that role belongs to the same organization as the user.
        """
        if self.role.organization_id != self.organization_id:
            raise ValueError(
                f'Role {self.role.name} does not belong to organization {self.organization.name}'
            )
        super().save(*args, **kwargs)

    def get_permissions(self):
        """Get list of permissions granted to this user through their role."""
        if not self.is_active or not self.role.is_active:
            return []
        return self.role.get_permissions_list()

    def has_permission(self, permission_name):
        """
        Check if user has a specific permission.

        Args:
            permission_name: One of 'view_loan_application',
                           'approve_loan_application', 'decline_loan_application'

        Returns:
            bool: True if user has the permission
        """
        if not self.is_active or not self.role.is_active:
            return False

        permission_map = {
            'view_loan_application': self.role.can_view_loan_application,
            'approve_loan_application': self.role.can_approve_loan_application,
            'decline_loan_application': self.role.can_decline_loan_application,
        }
        return permission_map.get(permission_name, False)


class AuditLog(models.Model):
    """
    Audit log for tracking all permission-based actions and user lifecycle events.

    This provides a comprehensive audit trail for compliance and security forensics.
    All records are append-only (no updates or deletes allowed).
    """

    class EventType(models.TextChoices):
        # Organization events
        ORGANIZATION_CREATED = 'organization_created', 'Organization Created'
        ORGANIZATION_UPDATED = 'organization_updated', 'Organization Updated'
        ORGANIZATION_DEACTIVATED = 'organization_deactivated', 'Organization Deactivated'

        # Role events
        ROLE_CREATED = 'role_created', 'Role Created'
        ROLE_UPDATED = 'role_updated', 'Role Updated'
        ROLE_DELETED = 'role_deleted', 'Role Deleted'

        # User events
        USER_CREATED = 'user_created', 'User Created'
        USER_UPDATED = 'user_updated', 'User Updated'
        USER_DEACTIVATED = 'user_deactivated', 'User Deactivated'

        # Authentication events
        LOGIN_SUCCESS = 'login_success', 'Login Successful'
        LOGIN_FAILED = 'login_failed', 'Login Failed'
        PASSWORD_CHANGED = 'password_changed', 'Password Changed'
        PASSWORD_RESET_REQUESTED = 'password_reset_requested', 'Password Reset Requested'

        # Loan application events
        LOAN_APPLICATION_VIEWED = 'loan_application_viewed', 'Loan Application Viewed'
        LOAN_APPLICATION_APPROVED = 'loan_application_approved', 'Loan Application Approved'
        LOAN_APPLICATION_DECLINED = 'loan_application_declined', 'Loan Application Declined'

        # Authorization events
        AUTHORIZATION_FAILED = 'authorization_failed', 'Authorization Failed'

    class Result(models.TextChoices):
        SUCCESS = 'success', 'Success'
        FAILURE = 'failure', 'Failure'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
        db_index=True,
        help_text='Type of event that occurred'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text='User who performed the action (actor)'
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='targeted_audit_logs',
        help_text='User who was the target of the action'
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text='Organization context of the action'
    )
    target_resource_type = models.CharField(
        max_length=50,
        blank=True,
        help_text='Type of resource affected (e.g., loan_application, role)'
    )
    target_resource_id = models.UUIDField(
        null=True,
        blank=True,
        help_text='ID of the affected resource'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text='IP address of the request'
    )
    user_agent = models.TextField(
        blank=True,
        help_text='User agent string of the request'
    )
    result = models.CharField(
        max_length=20,
        choices=Result.choices,
        default=Result.SUCCESS,
        db_index=True,
        help_text='Whether the action succeeded or failed'
    )
    error_message = models.TextField(
        blank=True,
        help_text='Error message if action failed'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional metadata about the event'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'audit_logs'
        indexes = [
            models.Index(fields=['event_type', 'created_at']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['organization', 'created_at']),
            models.Index(fields=['result', 'created_at']),
            models.Index(fields=['-created_at']),
        ]
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-created_at']
        # Prevent updates and deletes in admin
        permissions = [
            ('view_audit_log', 'Can view audit logs'),
        ]

    def __str__(self):
        actor = self.user.get_full_name() if self.user else 'System'
        return f'{self.event_type} by {actor} at {self.created_at}'

    @classmethod
    def log_event(cls, event_type, user=None, target_user=None, organization=None,
                  target_resource_type=None, target_resource_id=None,
                  ip_address=None, user_agent=None, result='success',
                  error_message='', metadata=None):
        """
        Helper method to create audit log entries.

        Usage:
            AuditLog.log_event(
                event_type=AuditLog.EventType.USER_CREATED,
                user=request.user,
                organization=org,
                target_user=new_user,
                ip_address=get_client_ip(request),
                result=AuditLog.Result.SUCCESS,
                metadata={'role': role.name}
            )
        """
        return cls.objects.create(
            event_type=event_type,
            user=user,
            target_user=target_user,
            organization=organization,
            target_resource_type=target_resource_type,
            target_resource_id=target_resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            result=result,
            error_message=error_message,
            metadata=metadata or {}
        )
