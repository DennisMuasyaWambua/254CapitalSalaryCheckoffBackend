"""
Authentication and profile APIViews.

All views inherit from APIView for explicit control.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTTokenRefreshView
from django_otp.plugins.otp_totp.models import TOTPDevice
from django.core.cache import cache
from django.utils import timezone
import logging

from .serializers import (
    SendOTPSerializer, VerifyOTPSerializer, RegisterEmployeeSerializer,
    HRLoginSerializer, AdminLoginSerializer, AdminVerify2FASerializer,
    UserSerializer, UpdateProfileSerializer
)
from .otp import generate_otp, store_otp, verify_otp, can_request_new_otp
from .models import CustomUser
from common.throttling import OTPRateThrottle
from common.utils import get_client_ip
from apps.audit.models import AuditLog

logger = logging.getLogger(__name__)


def get_tokens_for_user(user):
    """
    Generate JWT tokens for a user.

    Args:
        user: CustomUser instance

    Returns:
        Dict with access and refresh tokens
    """
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


class SendOTPView(APIView):
    """
    POST /api/v1/auth/otp/send/
    Send OTP to phone number for verification.

    Throttled to 5 requests per minute per phone/IP.
    """

    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]

    def post(self, request):
        """Send OTP via SMS."""
        serializer = SendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']

        # Check if can request new OTP
        can_request, error_message = can_request_new_otp(phone_number)
        if not can_request:
            return Response(
                {'detail': error_message},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Generate OTP
        otp_code = generate_otp()

        # Store hashed OTP in Redis
        otp_info = store_otp(phone_number, otp_code)

        # Send OTP via SMS (async Celery task)
        from apps.notifications.tasks import send_otp_sms
        send_otp_sms.delay(phone_number, otp_code)

        logger.info(f'OTP sent to {otp_info["masked_phone"]}')

        # In development, log OTP for testing
        if settings.DEBUG:
            logger.info(f'[DEV] OTP for {phone_number}: {otp_code}')

        return Response({
            'detail': 'OTP sent successfully',
            'masked_phone': otp_info['masked_phone'],
            'expires_in': otp_info['expires_in'],
        }, status=status.HTTP_200_OK)


class VerifyOTPView(APIView):
    """
    POST /api/v1/auth/otp/verify/
    Verify OTP for phone number.

    Returns:
    - If user exists: JWT tokens
    - If new user: { is_new_user: true, phone_verified: true }
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Verify OTP code."""
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']
        otp = serializer.validated_data['otp']

        # Verify OTP
        is_valid, error_message = verify_otp(phone_number, otp)

        if not is_valid:
            return Response(
                {'detail': error_message},
                status=status.HTTP_400_BAD_REQUEST
            )

        # OTP is valid - check if user exists
        try:
            user = CustomUser.objects.get(phone_number=phone_number)

            # Update phone verification status
            if not user.is_phone_verified:
                user.is_phone_verified = True
                user.save()

            # Generate tokens
            tokens = get_tokens_for_user(user)

            # Log successful login
            AuditLog.log(
                action='OTP login successful',
                actor=user,
                target_type='CustomUser',
                target_id=user.id,
                ip_address=get_client_ip(request)
            )

            return Response({
                'detail': 'Login successful',
                'is_new_user': False,
                'tokens': tokens,
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)

        except CustomUser.DoesNotExist:
            # New user - return flag to proceed with registration
            # Store verified phone in cache for 10 minutes
            cache.set(
                f'verified_phone:{phone_number}',
                True,
                timeout=600  # 10 minutes
            )

            logger.info(f'New user phone verified: {phone_number}')

            return Response({
                'detail': 'Phone verified successfully',
                'is_new_user': True,
                'phone_verified': True,
                'phone_number': phone_number
            }, status=status.HTTP_200_OK)


class RegisterEmployeeView(APIView):
    """
    POST /api/v1/auth/register/
    Register new employee user.

    Requires phone number to be already verified via OTP.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Register employee."""
        serializer = RegisterEmployeeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']

        # Verify phone was verified via OTP
        is_verified = cache.get(f'verified_phone:{phone_number}')
        if not is_verified:
            return Response(
                {'detail': 'Phone number must be verified first. Please verify via OTP.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create user and profile
        user = serializer.save()

        # Clear verified phone from cache
        cache.delete(f'verified_phone:{phone_number}')

        # Generate tokens
        tokens = get_tokens_for_user(user)

        # Log registration
        AuditLog.log(
            action='Employee registration',
            actor=user,
            target_type='CustomUser',
            target_id=user.id,
            metadata={'employer_id': str(user.employee_profile.employer.id)},
            ip_address=get_client_ip(request)
        )

        logger.info(f'New employee registered: {user.id}')

        return Response({
            'detail': 'Registration successful',
            'tokens': tokens,
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)


class HRLoginView(APIView):
    """
    POST /api/v1/auth/hr/login/
    Email/password login for HR managers.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Authenticate HR user."""
        serializer = HRLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']

        # Generate tokens
        tokens = get_tokens_for_user(user)

        # Log login
        AuditLog.log(
            action='HR login',
            actor=user,
            target_type='CustomUser',
            target_id=user.id,
            ip_address=get_client_ip(request)
        )

        logger.info(f'HR user logged in: {user.id}')

        return Response({
            'detail': 'Login successful',
            'tokens': tokens,
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)


class AdminLoginView(APIView):
    """
    POST /api/v1/auth/admin/login/
    Email/password login for admins (step 1 of 2FA).

    Returns temporary token for 2FA verification.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Authenticate admin user (step 1)."""
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']

        # Generate temporary token (expires in 5 minutes)
        temp_token = RefreshToken.for_user(user)
        temp_token.set_exp(lifetime=timezone.timedelta(minutes=5))

        # Store user ID in cache for 2FA verification
        cache.set(
            f'2fa_pending:{str(temp_token)}',
            str(user.id),
            timeout=300  # 5 minutes
        )

        logger.info(f'Admin 2FA pending: {user.id}')

        return Response({
            'detail': '2FA verification required',
            'requires_2fa': True,
            'temp_token': str(temp_token.access_token)
        }, status=status.HTTP_200_OK)


class AdminVerify2FAView(APIView):
    """
    POST /api/v1/auth/admin/verify-2fa/
    Verify TOTP code for admin (step 2 of 2FA).

    Returns full JWT tokens on success.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Verify admin 2FA TOTP code."""
        serializer = AdminVerify2FASerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        temp_token = serializer.validated_data['temp_token']
        totp_code = serializer.validated_data['totp_code']

        # Get user ID from cache
        user_id = cache.get(f'2fa_pending:{temp_token}')
        if not user_id:
            return Response(
                {'detail': '2FA session expired or invalid. Please log in again.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get user
        try:
            user = CustomUser.objects.get(id=user_id, role='admin')
        except CustomUser.DoesNotExist:
            return Response(
                {'detail': 'Invalid user.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get or create TOTP device for user
        devices = TOTPDevice.objects.filter(user=user, confirmed=True)
        if not devices.exists():
            # For development: auto-create and confirm device
            # In production, this should be done through admin setup
            if settings.DEBUG:
                device = TOTPDevice.objects.create(
                    user=user,
                    name='default',
                    confirmed=True
                )
            else:
                return Response(
                    {'detail': '2FA not configured for this account. Please contact administrator.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            device = devices.first()

        # Verify TOTP code
        is_valid = device.verify_token(totp_code)
        if not is_valid:
            return Response(
                {'detail': 'Invalid TOTP code.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Clear 2FA pending from cache
        cache.delete(f'2fa_pending:{temp_token}')

        # Generate full tokens
        tokens = get_tokens_for_user(user)

        # Log login
        AuditLog.log(
            action='Admin login with 2FA',
            actor=user,
            target_type='CustomUser',
            target_id=user.id,
            ip_address=get_client_ip(request)
        )

        logger.info(f'Admin logged in with 2FA: {user.id}')

        return Response({
            'detail': 'Login successful',
            'tokens': tokens,
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)


class TokenRefreshView(SimpleJWTTokenRefreshView):
    """
    POST /api/v1/auth/token/refresh/
    Refresh JWT access token using refresh token.

    Uses djangorestframework-simplejwt's built-in view.
    """
    pass


class ProfileView(APIView):
    """
    GET  /api/v1/auth/profile/  — Get current user profile
    PUT  /api/v1/auth/profile/  — Update current user profile
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current user profile."""
        user = request.user
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        """Update current user profile."""
        user = request.user
        serializer = UpdateProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Update user
        updated_user = serializer.update(user, serializer.validated_data)

        # Log update
        AuditLog.log(
            action='Profile updated',
            actor=user,
            target_type='CustomUser',
            target_id=user.id,
            metadata={'fields_updated': list(serializer.validated_data.keys())},
            ip_address=get_client_ip(request)
        )

        return Response(
            UserSerializer(updated_user).data,
            status=status.HTTP_200_OK
        )
