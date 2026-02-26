"""
Custom permission classes for role-based access control.
"""

from rest_framework import permissions


class IsEmployee(permissions.BasePermission):
    """
    Permission class that only allows employee users.
    """

    message = 'You must be an employee to perform this action.'

    def has_permission(self, request, view):
        """
        Check if user is authenticated and has employee role.
        """
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'employee'
        )


class IsHRManager(permissions.BasePermission):
    """
    Permission class that only allows HR manager users.
    """

    message = 'You must be an HR manager to perform this action.'

    def has_permission(self, request, view):
        """
        Check if user is authenticated and has hr_manager role.
        """
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'hr_manager'
        )


class IsAdmin(permissions.BasePermission):
    """
    Permission class that only allows admin users (254 Capital staff).
    """

    message = 'You must be an admin to perform this action.'

    def has_permission(self, request, view):
        """
        Check if user is authenticated and has admin role.
        """
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'admin'
        )


class IsHROrAdmin(permissions.BasePermission):
    """
    Permission class that allows HR managers or admins.

    Useful for endpoints that both HR and admins can access.
    """

    message = 'You must be an HR manager or admin to perform this action.'

    def has_permission(self, request, view):
        """
        Check if user is authenticated and has hr_manager or admin role.
        """
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ['hr_manager', 'admin']
        )


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Object-level permission that allows owners or admins.

    For employee-owned resources (like loan applications).
    """

    message = 'You must be the owner of this resource or an admin.'

    def has_object_permission(self, request, view, obj):
        """
        Check if user is the owner of the object or an admin.
        """
        if request.user.role == 'admin':
            return True

        # Check if object has an 'employee' attribute (like LoanApplication)
        if hasattr(obj, 'employee'):
            return obj.employee == request.user

        # Check if object has a 'user' attribute (like EmployeeProfile)
        if hasattr(obj, 'user'):
            return obj.user == request.user

        # Check if object is the user themselves
        if obj == request.user:
            return True

        return False


class IsSameEmployer(permissions.BasePermission):
    """
    Object-level permission for HR managers to access only their employer's data.

    Admins can access all employers' data.
    """

    message = 'You can only access data from your own employer.'

    def has_object_permission(self, request, view, obj):
        """
        Check if HR user's employer matches object's employer.
        """
        # Admins can access everything
        if request.user.role == 'admin':
            return True

        # For HR managers, check employer match
        if request.user.role == 'hr_manager':
            hr_profile = getattr(request.user, 'hr_profile', None)
            if not hr_profile:
                return False

            # Check if object has an 'employer' attribute
            if hasattr(obj, 'employer'):
                return obj.employer == hr_profile.employer

            # Check if object is an Employer instance
            if obj.__class__.__name__ == 'Employer':
                return obj == hr_profile.employer

        return False


class CanModifyApplication(permissions.BasePermission):
    """
    Object-level permission for modifying loan applications.

    Rules:
    - Employee can only modify their own applications in 'submitted' status
    - HR can review applications from their employer
    - Admin can review any application
    """

    message = 'You cannot modify this loan application.'

    def has_object_permission(self, request, view, obj):
        """
        Check if user can modify the loan application.
        """
        # Admin can do anything
        if request.user.role == 'admin':
            return True

        # HR can review applications from their employer
        if request.user.role == 'hr_manager':
            hr_profile = getattr(request.user, 'hr_profile', None)
            if hr_profile and obj.employer == hr_profile.employer:
                return True
            return False

        # Employee can only modify their own applications in 'submitted' status
        if request.user.role == 'employee':
            if obj.employee == request.user and obj.status == 'submitted':
                return True
            return False

        return False


class ReadOnly(permissions.BasePermission):
    """
    Permission that only allows safe methods (GET, HEAD, OPTIONS).
    """

    def has_permission(self, request, view):
        """
        Allow only safe methods.
        """
        return request.method in permissions.SAFE_METHODS
