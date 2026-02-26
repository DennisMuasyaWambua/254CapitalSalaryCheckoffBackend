"""
Custom throttling classes for rate limiting.
"""

from rest_framework.throttling import SimpleRateThrottle


class OTPRateThrottle(SimpleRateThrottle):
    """
    Throttle class for OTP endpoints.
    Limits OTP requests to 5 per minute per phone number or IP address.
    """
    rate = '5/min'
    scope = 'otp'

    def get_cache_key(self, request, view):
        """
        Generate cache key based on phone number (if provided) or IP address.
        """
        # Try to get phone number from request data
        phone_number = None
        if request.data:
            phone_number = request.data.get('phone_number')

        if phone_number:
            # Throttle by phone number
            return f'throttle_otp_phone_{phone_number}'

        # Fallback to IP-based throttling
        ident = self.get_ident(request)
        return f'throttle_otp_ip_{ident}'


class DocumentUploadThrottle(SimpleRateThrottle):
    """
    Throttle class for document upload endpoints.
    Limits uploads to 20 per hour per user.
    """
    rate = '20/hour'
    scope = 'upload'

    def get_cache_key(self, request, view):
        """
        Generate cache key based on authenticated user.
        """
        if request.user and request.user.is_authenticated:
            return f'throttle_upload_user_{request.user.id}'

        # Fallback to IP-based throttling for anonymous users
        ident = self.get_ident(request)
        return f'throttle_upload_ip_{ident}'


class SMSThrottle(SimpleRateThrottle):
    """
    Throttle class for SMS sending.
    Limits SMS sends to 10 per hour per phone number.
    """
    rate = '10/hour'
    scope = 'sms'

    def get_cache_key(self, request, view):
        """
        Generate cache key based on phone number.
        """
        phone_number = request.data.get('phone_number')
        if phone_number:
            return f'throttle_sms_{phone_number}'

        # Fallback to IP
        ident = self.get_ident(request)
        return f'throttle_sms_ip_{ident}'
