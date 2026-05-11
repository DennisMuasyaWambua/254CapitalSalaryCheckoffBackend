"""
Custom permission classes for Company Management RBAC.
"""

from rest_framework import permissions
from .models import OrganizationUser, AuditLog


def get_client_ip(request):
    """Extract client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


class IsHRAdmin(permissions.BasePermission):
    """
    Permission class that allows only HR admins and system admins.
    """

    message = 'Only HR administrators and system admins can access this resource.'

    def has_permission(self, request, view):
        """Check if user is authenticated and is HR or admin."""
        if not request.user or not request.user.is_authenticated:
            return False

        # Allow system admins (254 Capital staff)
        if request.user.role == 'admin':
            return True

        # Allow HR managers
        if request.user.role == 'hr_manager':
            return True

        return False


class HasLoanApplicationPermission(permissions.BasePermission):
    """
    Permission class for checking loan application permissions.

    This checks if the user has the required permission through their
    organization role assignment.
    """

    def has_permission(self, request, view):
        """Check if user has base permission to access loan applications."""
        if not request.user or not request.user.is_authenticated:
            return False

        # System admins always have access
        if request.user.role == 'admin':
            return True

        # Check if user has an active organization membership
        try:
            org_user = OrganizationUser.objects.select_related(
                'organization', 'role'
            ).get(user=request.user, is_active=True)

            # Check if organization is active
            if not org_user.organization.is_active:
                return False

            # User must have at least view permission to access the list
            return org_user.role.can_view_loan_application

        except OrganizationUser.DoesNotExist:
            return False

    def has_object_permission(self, request, view, obj):
        """
        Check if user has permission for specific loan application action.

        obj: LoanApplication instance
        """
        if not request.user or not request.user.is_authenticated:
            return False

        # System admins always have access
        if request.user.role == 'admin':
            return True

        try:
            org_user = OrganizationUser.objects.select_related(
                'organization', 'role'
            ).get(user=request.user, is_active=True)

            # Verify loan application belongs to user's organization
            if obj.organization_id != org_user.organization_id:
                # Log authorization failure
                AuditLog.log_event(
                    event_type=AuditLog.EventType.AUTHORIZATION_FAILED,
                    user=request.user,
                    organization=org_user.organization,
                    target_resource_type='loan_application',
                    target_resource_id=obj.id,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    result=AuditLog.Result.FAILURE,
                    error_message='Cross-organization access attempt',
                    metadata={'attempted_org_id': str(obj.organization_id)}
                )
                return False

            # Check specific action permissions
            action = view.action
            if action == 'retrieve' or action == 'list':
                return org_user.role.can_view_loan_application
            elif action == 'approve':
                return org_user.role.can_approve_loan_application
            elif action == 'decline':
                return org_user.role.can_decline_loan_application

            # Default to view permission for other actions
            return org_user.role.can_view_loan_application

        except OrganizationUser.DoesNotExist:
            return False


class CanViewLoanApplication(permissions.BasePermission):
    """Permission to view loan application details."""

    message = 'You do not have permission to view loan applications.'

    def has_permission(self, request, view):
        """Check if user can view loan applications."""
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.role == 'admin':
            return True

        try:
            org_user = OrganizationUser.objects.select_related('role').get(
                user=request.user, is_active=True
            )
            return org_user.role.can_view_loan_application
        except OrganizationUser.DoesNotExist:
            return False


class CanApproveLoanApplication(permissions.BasePermission):
    """Permission to approve loan applications."""

    message = 'You do not have permission to approve loan applications.'

    def has_permission(self, request, view):
        """Check if user can approve loan applications."""
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.role == 'admin':
            return True

        try:
            org_user = OrganizationUser.objects.select_related('role').get(
                user=request.user, is_active=True
            )
            return org_user.role.can_approve_loan_application
        except OrganizationUser.DoesNotExist:
            return False


class CanDeclineLoanApplication(permissions.BasePermission):
    """Permission to decline loan applications."""

    message = 'You do not have permission to decline loan applications.'

    def has_permission(self, request, view):
        """Check if user can decline loan applications."""
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.role == 'admin':
            return True

        try:
            org_user = OrganizationUser.objects.select_related('role').get(
                user=request.user, is_active=True
            )
            return org_user.role.can_decline_loan_application
        except OrganizationUser.DoesNotExist:
            return False


class BelongsToSameOrganization(permissions.BasePermission):
    """
    Permission to ensure resource belongs to user's organization.
    """

    message = 'You can only access resources from your organization.'

    def has_object_permission(self, request, view, obj):
        """Check if object belongs to user's organization."""
        if not request.user or not request.user.is_authenticated:
            return False

        # System admins can access all organizations
        if request.user.role == 'admin':
            return True

        try:
            org_user = OrganizationUser.objects.get(
                user=request.user, is_active=True
            )

            # Check if object has organization_id attribute
            if hasattr(obj, 'organization_id'):
                return obj.organization_id == org_user.organization_id
            elif hasattr(obj, 'organization'):
                return obj.organization.id == org_user.organization_id

            return False

        except OrganizationUser.DoesNotExist:
            return False
