"""
Audit middleware for automatic action logging.
"""

from .models import AuditLog
from common.utils import get_client_ip


class AuditMiddleware:
    """
    Middleware to automatically log certain HTTP requests for audit trail.

    Logs:
    - All POST, PUT, PATCH, DELETE requests from authenticated users
    - Captures IP address and basic request info
    """

    # Paths to exclude from audit logging
    EXCLUDED_PATHS = [
        '/admin/jsi18n/',
        '/api/schema/',
        '/api/docs/',
        '/api/redoc/',
        '/static/',
        '/media/',
    ]

    # Methods to log
    LOGGED_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        Process the request and log if applicable.
        """
        response = self.get_response(request)

        # Only log if user is authenticated and method is in LOGGED_METHODS
        if (
            request.user.is_authenticated
            and request.method in self.LOGGED_METHODS
            and not any(request.path.startswith(path) for path in self.EXCLUDED_PATHS)
        ):
            self.log_request(request, response)

        return response

    def log_request(self, request, response):
        """
        Create an audit log entry for the request.
        """
        try:
            # Build action description from request
            action = f'{request.method} {request.path}'

            # Get IP address
            ip_address = get_client_ip(request)

            # Build metadata
            metadata = {
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
            }

            # Add query params if present
            if request.GET:
                metadata['query_params'] = dict(request.GET)

            # Log the action
            # Note: We don't have target_type/target_id at middleware level,
            # so we use generic values. Specific actions should create their own audit logs.
            AuditLog.log(
                action=action,
                actor=request.user,
                target_type='Request',
                target_id=request.user.id,  # Use user ID as target
                metadata=metadata,
                ip_address=ip_address
            )

        except Exception as e:
            # Don't fail the request if audit logging fails
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Failed to create audit log: {e}')
