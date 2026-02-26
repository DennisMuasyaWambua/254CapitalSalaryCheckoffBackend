"""
Custom exception handler for consistent API error responses.
"""

from rest_framework.views import exception_handler
from rest_framework.exceptions import ValidationError, ErrorDetail
from rest_framework.response import Response
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.http import Http404
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that returns a consistent error format:

    {
        "detail": "Human-readable error message",
        "code": "error_code",
        "errors": {  # Only for validation errors
            "field_name": ["Error message 1", "Error message 2"]
        }
    }
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    if response is not None:
        # Customize the response data
        custom_response_data = {}

        # Handle validation errors (400)
        if isinstance(exc, ValidationError):
            custom_response_data['detail'] = 'Validation error'
            custom_response_data['code'] = 'validation_error'

            # Format validation errors
            errors = {}
            if isinstance(response.data, dict):
                for field, messages in response.data.items():
                    if isinstance(messages, list):
                        errors[field] = [
                            str(msg) if not isinstance(msg, ErrorDetail) else msg
                            for msg in messages
                        ]
                    else:
                        errors[field] = [str(messages)]
            elif isinstance(response.data, list):
                errors['non_field_errors'] = [str(msg) for msg in response.data]

            custom_response_data['errors'] = errors

        # Handle other DRF exceptions
        elif hasattr(exc, 'detail'):
            if isinstance(exc.detail, dict):
                custom_response_data['detail'] = exc.detail.get('detail', str(exc.detail))
                custom_response_data['code'] = exc.detail.get('code', exc.get_codes())
            else:
                custom_response_data['detail'] = str(exc.detail)
                custom_response_data['code'] = exc.get_codes() if hasattr(exc, 'get_codes') else 'error'

        # Update response data
        response.data = custom_response_data

    else:
        # Handle Django core exceptions
        if isinstance(exc, Http404) or isinstance(exc, ObjectDoesNotExist):
            custom_response_data = {
                'detail': 'Resource not found',
                'code': 'not_found'
            }
            response = Response(custom_response_data, status=404)

        elif isinstance(exc, PermissionDenied):
            custom_response_data = {
                'detail': 'You do not have permission to perform this action',
                'code': 'permission_denied'
            }
            response = Response(custom_response_data, status=403)

        else:
            # Log unexpected errors
            logger.error(f'Unexpected error: {exc}', exc_info=True)

            # Return generic error for unexpected exceptions
            custom_response_data = {
                'detail': 'An unexpected error occurred. Please try again later.',
                'code': 'server_error'
            }
            response = Response(custom_response_data, status=500)

    return response


class OTPVerificationError(Exception):
    """Custom exception for OTP verification failures."""
    def __init__(self, message, code='otp_verification_failed'):
        self.message = message
        self.code = code
        super().__init__(self.message)


class LoanCalculationError(Exception):
    """Custom exception for loan calculation errors."""
    def __init__(self, message, code='calculation_error'):
        self.message = message
        self.code = code
        super().__init__(self.message)


class DocumentUploadError(Exception):
    """Custom exception for document upload errors."""
    def __init__(self, message, code='upload_error'):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ReconciliationError(Exception):
    """Custom exception for reconciliation errors."""
    def __init__(self, message, code='reconciliation_error'):
        self.message = message
        self.code = code
        super().__init__(self.message)
