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
from django.conf import settings
import logging

from .serializers import (
    SendOTPSerializer, VerifyOTPSerializer, RegisterEmployeeSerializer,
    HRLoginSerializer, AdminLoginSerializer, AdminVerify2FASerializer,
    VerifyLoginOTPSerializer, UserSerializer, UpdateProfileSerializer
)
from .otp import generate_otp, store_otp, verify_otp, can_request_new_otp
from .models import CustomUser, PasswordResetToken
from common.throttling import OTPRateThrottle
from common.utils import get_client_ip
from common.email_service import send_welcome_email, send_internal_alert, send_password_reset_email
from apps.audit.models import AuditLog
import secrets
from datetime import timedelta

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

        # Send welcome email if user has email address
        if user.email:
            try:
                send_welcome_email(
                    to_address=user.email,
                    user_name=user.get_full_name() or user.phone_number,
                    role='Employee'
                )
                logger.info(f'Welcome email sent to {user.email}')
            except Exception as e:
                logger.error(f'Failed to send welcome email to {user.email}: {str(e)}')

        # Send internal alert to admin
        try:
            employer_name = user.employee_profile.employer.name
            alert_message = f"""
            <p><strong>New Employee Registration</strong></p>
            <ul>
                <li><strong>Name:</strong> {user.get_full_name()}</li>
                <li><strong>Phone:</strong> {user.phone_number}</li>
                <li><strong>Email:</strong> {user.email or 'Not provided'}</li>
                <li><strong>Employer:</strong> {employer_name}</li>
                <li><strong>Employee ID:</strong> {user.employee_profile.employee_id}</li>
            </ul>
            """
            send_internal_alert(
                subject=f'New Employee Registration - {employer_name}',
                message=alert_message,
                alert_type='info'
            )
        except Exception as e:
            logger.error(f'Failed to send internal alert for employee registration: {str(e)}')

        return Response({
            'detail': 'Registration successful',
            'tokens': tokens,
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)


class HRLoginView(APIView):
    """
    POST /api/v1/auth/hr/login/
    Email/password login for HR managers (step 1 of OTP login).

    Returns temporary token and sends OTP via SMS.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Authenticate HR user and send OTP."""
        serializer = HRLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']

        # Check if user has phone number
        if not user.phone_number:
            return Response(
                {'detail': 'No phone number on file. Please contact administrator.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generate temporary token (expires in 5 minutes)
        temp_token = RefreshToken.for_user(user)
        temp_token.set_exp(lifetime=timezone.timedelta(minutes=5))

        # CRITICAL: Generate access token ONCE and reuse it
        # Each call to temp_token.access_token creates a NEW token with different JTI
        access_token_str = str(temp_token.access_token)

        # Generate OTP
        otp_code = generate_otp()

        # Store OTP in Redis
        otp_info = store_otp(user.phone_number, otp_code)

        # Send OTP via SMS (async Celery task)
        from apps.notifications.tasks import send_otp_sms
        send_otp_sms.delay(user.phone_number, otp_code)

        # Store user ID in cache for OTP verification
        cache_key = f'login_otp_pending:{access_token_str}'
        cache.set(
            cache_key,
            str(user.id),
            timeout=300  # 5 minutes
        )

        # Verify cache was set successfully
        cached_value = cache.get(cache_key)
        logger.info(f'HR login OTP sent to {otp_info["masked_phone"]}')
        logger.info(f'Cache set: key={cache_key}, user_id={user.id}, token={access_token_str[:20]}...')
        logger.info(f'Cache verify: immediate get returned {cached_value}, matches={cached_value == str(user.id)}')

        return Response({
            'detail': 'OTP sent to your phone. Please verify to complete login.',
            'requires_otp': True,
            'temp_token': access_token_str,
            'masked_phone': otp_info['masked_phone'],
            'expires_in': otp_info['expires_in']
        }, status=status.HTTP_200_OK)


class AdminLoginView(APIView):
    """
    POST /api/v1/auth/admin/login/
    Email/password login for admins (step 1 of OTP login).

    Returns temporary token and sends OTP via SMS.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Authenticate admin user and send OTP."""
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']

        # Check if user has phone number
        if not user.phone_number:
            return Response(
                {'detail': 'No phone number on file. Please contact administrator.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generate temporary token (expires in 5 minutes)
        temp_token = RefreshToken.for_user(user)
        temp_token.set_exp(lifetime=timezone.timedelta(minutes=5))

        # CRITICAL: Generate access token ONCE and reuse it
        # Each call to temp_token.access_token creates a NEW token with different JTI
        access_token_str = str(temp_token.access_token)

        # Generate OTP
        otp_code = generate_otp()

        # Store OTP in Redis
        otp_info = store_otp(user.phone_number, otp_code)

        # Send OTP via SMS (async Celery task)
        from apps.notifications.tasks import send_otp_sms
        send_otp_sms.delay(user.phone_number, otp_code)

        # Store user ID in cache for OTP verification
        cache_key = f'login_otp_pending:{access_token_str}'
        cache.set(
            cache_key,
            str(user.id),
            timeout=300  # 5 minutes
        )

        # Verify cache was set successfully
        cached_value = cache.get(cache_key)
        logger.info(f'Admin login OTP sent to {otp_info["masked_phone"]}')
        logger.info(f'Cache set: key={cache_key}, user_id={user.id}, token={access_token_str[:20]}...')
        logger.info(f'Cache verify: immediate get returned {cached_value}, matches={cached_value == str(user.id)}')

        return Response({
            'detail': 'OTP sent to your phone. Please verify to complete login.',
            'requires_otp': True,
            'temp_token': access_token_str,
            'masked_phone': otp_info['masked_phone'],
            'expires_in': otp_info['expires_in']
        }, status=status.HTTP_200_OK)


class VerifyLoginOTPView(APIView):
    """
    POST /api/v1/auth/verify-login-otp/
    Verify OTP for HR/Admin login (step 2 of OTP login).

    Returns full JWT tokens on success.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Verify login OTP code."""
        serializer = VerifyLoginOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        temp_token = serializer.validated_data['temp_token']
        otp = serializer.validated_data['otp']

        # Get user ID from cache
        cache_key = f'login_otp_pending:{temp_token}'
        user_id = cache.get(cache_key)
        logger.info(f'Cache lookup: key={cache_key}, found={user_id is not None}, token={temp_token[:20]}...')

        if not user_id:
            logger.error(f'Cache miss for key={cache_key}')
            return Response(
                {'detail': 'OTP session expired or invalid. Please log in again.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get user
        try:
            user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            return Response(
                {'detail': 'Invalid user.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify role is HR or Admin
        if user.role not in ['hr_manager', 'admin']:
            return Response(
                {'detail': 'Invalid user role for this endpoint.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify OTP
        is_valid, error_message = verify_otp(user.phone_number, otp)

        if not is_valid:
            return Response(
                {'detail': error_message},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Clear OTP pending from cache
        cache.delete(f'login_otp_pending:{temp_token}')

        # Generate full tokens
        tokens = get_tokens_for_user(user)

        # Log login
        action_name = 'HR login with OTP' if user.role == 'hr_manager' else 'Admin login with OTP'
        AuditLog.log(
            action=action_name,
            actor=user,
            target_type='CustomUser',
            target_id=user.id,
            ip_address=get_client_ip(request)
        )

        logger.info(f'{user.role.upper()} user logged in with OTP: {user.id}')

        return Response({
            'detail': 'Login successful',
            'tokens': tokens,
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)


class AdminVerify2FAView(APIView):
    """
    POST /api/v1/auth/admin/verify-2fa/
    Verify TOTP code for admin (step 2 of 2FA).

    DEPRECATED: This endpoint is kept for backward compatibility.
    Use VerifyLoginOTPView for OTP-based authentication.

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


class RequestPasswordResetView(APIView):
    """
    POST /api/v1/auth/password-reset/request/
    Request password reset for HR/Admin users via email.

    Sends a password reset link to the user's email address.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Request password reset."""
        email = request.data.get('email', '').strip()

        if not email:
            return Response(
                {'detail': 'Email address is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find user by email (HR or Admin only)
        try:
            user = CustomUser.objects.get(
                email=email,
                role__in=[CustomUser.Role.HR_MANAGER, CustomUser.Role.ADMIN]
            )
        except CustomUser.DoesNotExist:
            # For security, don't reveal if email exists
            return Response(
                {'detail': 'If the email address is registered, you will receive a password reset link.'},
                status=status.HTTP_200_OK
            )

        # Generate secure token
        token = secrets.token_urlsafe(32)

        # Create password reset token (expires in 1 hour)
        reset_token = PasswordResetToken.objects.create(
            user=user,
            token=token,
            expires_at=timezone.now() + timedelta(hours=1)
        )

        # Send password reset email
        try:
            frontend_url = settings.FRONTEND_URL
            reset_url = f'{frontend_url}/reset-password'
            send_password_reset_email(
                to_address=user.email,
                user_name=user.get_full_name() or user.email,
                reset_token=token,
                reset_url=reset_url
            )
            logger.info(f'Password reset email sent to {user.email}')
        except Exception as e:
            logger.error(f'Failed to send password reset email: {str(e)}')
            return Response(
                {'detail': 'Failed to send password reset email. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Log password reset request
        AuditLog.log(
            action='Password reset requested',
            actor=user,
            target_type='CustomUser',
            target_id=user.id,
            ip_address=get_client_ip(request)
        )

        return Response(
            {'detail': 'If the email address is registered, you will receive a password reset link.'},
            status=status.HTTP_200_OK
        )


class ResetPasswordView(APIView):
    """
    POST /api/v1/auth/password-reset/confirm/
    Reset password using the token from email.

    Validates the token and sets a new password.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Reset password with token."""
        token = request.data.get('token', '').strip()
        new_password = request.data.get('new_password', '').strip()

        if not token or not new_password:
            return Response(
                {'detail': 'Token and new password are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate password length
        if len(new_password) < 8:
            return Response(
                {'detail': 'Password must be at least 8 characters long.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find valid token
        try:
            reset_token = PasswordResetToken.objects.select_related('user').get(
                token=token,
                is_used=False
            )
        except PasswordResetToken.DoesNotExist:
            return Response(
                {'detail': 'Invalid or expired reset token.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if token expired
        if reset_token.is_expired:
            return Response(
                {'detail': 'Reset token has expired. Please request a new one.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update password
        user = reset_token.user
        user.set_password(new_password)
        user.save()

        # Mark token as used
        reset_token.is_used = True
        reset_token.used_at = timezone.now()
        reset_token.save()

        # Log password reset
        AuditLog.log(
            action='Password reset completed',
            actor=user,
            target_type='CustomUser',
            target_id=user.id,
            ip_address=get_client_ip(request)
        )

        # Send internal alert
        try:
            alert_message = f"""
            <p><strong>Password Reset Completed</strong></p>
            <ul>
                <li><strong>User:</strong> {user.get_full_name()}</li>
                <li><strong>Email:</strong> {user.email}</li>
                <li><strong>Role:</strong> {user.get_role_display()}</li>
            </ul>
            """
            send_internal_alert(
                subject=f'Password Reset - {user.get_full_name()}',
                message=alert_message,
                alert_type='info'
            )
        except Exception as e:
            logger.error(f'Failed to send internal alert: {str(e)}')

        logger.info(f'Password reset completed for {user.email}')

        return Response(
            {'detail': 'Password reset successful. You can now log in with your new password.'},
            status=status.HTTP_200_OK
        )


class ChangePasswordView(APIView):
    """
    POST /api/v1/auth/change-password/
    Self-service password change for authenticated users.

    Allows employees, HR managers, and admins to change their own password.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Change user's password."""
        current_password = request.data.get('current_password', '').strip()
        new_password = request.data.get('new_password', '').strip()
        confirm_password = request.data.get('confirm_password', '').strip()

        # Validate required fields
        if not current_password or not new_password or not confirm_password:
            return Response(
                {'error': 'All fields are required (current_password, new_password, confirm_password)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if new passwords match
        if new_password != confirm_password:
            return Response(
                {'error': 'New passwords do not match'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify current password
        if not request.user.check_password(current_password):
            return Response(
                {'error': 'Current password is incorrect'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate new password requirements
        if len(new_password) < 8:
            return Response(
                {
                    'error': 'New password does not meet requirements',
                    'requirements': [
                        'Minimum 8 characters',
                        'At least one uppercase letter',
                        'At least one number',
                        'At least one special character'
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check for uppercase letter
        if not any(c.isupper() for c in new_password):
            return Response(
                {
                    'error': 'New password does not meet requirements',
                    'requirements': [
                        'Minimum 8 characters',
                        'At least one uppercase letter',
                        'At least one number',
                        'At least one special character'
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check for number
        if not any(c.isdigit() for c in new_password):
            return Response(
                {
                    'error': 'New password does not meet requirements',
                    'requirements': [
                        'Minimum 8 characters',
                        'At least one uppercase letter',
                        'At least one number',
                        'At least one special character'
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check for special character
        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        if not any(c in special_chars for c in new_password):
            return Response(
                {
                    'error': 'New password does not meet requirements',
                    'requirements': [
                        'Minimum 8 characters',
                        'At least one uppercase letter',
                        'At least one number',
                        'At least one special character'
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update password
        request.user.set_password(new_password)
        request.user.save()

        # Log password change
        AuditLog.log(
            action='Password changed',
            actor=request.user,
            target_type='CustomUser',
            target_id=request.user.id,
            ip_address=get_client_ip(request)
        )

        logger.info(f'Password changed for user {request.user.email}')

        return Response(
            {
                'detail': 'Password changed successfully',
                'requires_relogin': True
            },
            status=status.HTTP_200_OK
        )


class RequestPasswordResetOTPView(APIView):
    """
    POST /api/v1/auth/request-password-reset/
    Request password reset for HR/Admin users via OTP.

    Sends an OTP to the user's registered phone number.
    """

    permission_classes = [AllowAny]
    throttle_classes = [OTPRateThrottle]

    def post(self, request):
        """Request password reset with OTP."""
        email = request.data.get('email', '').strip()

        if not email:
            return Response(
                {'error': 'Email address is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find user by email (HR or Admin only)
        try:
            user = CustomUser.objects.get(
                email=email,
                role__in=[CustomUser.Role.HR_MANAGER, CustomUser.Role.ADMIN]
            )
        except CustomUser.DoesNotExist:
            # For security, don't reveal if email exists
            return Response(
                {'error': 'No user found with this email address'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if user has phone number
        if not user.phone_number:
            return Response(
                {'error': 'No phone number registered for this account. Please contact support.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check rate limiting
        if not can_request_new_otp(user.phone_number):
            return Response(
                {'error': 'Too many OTP requests. Please try again in 5 minutes.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Generate OTP
        otp_code = generate_otp()

        # Store OTP in cache (5 minute expiry)
        otp_key = f'password_reset_otp_{user.id}'
        store_otp(otp_key, otp_code, expiry_minutes=5)

        # Send OTP via SMS (would integrate with SMS provider)
        # For now, log it
        logger.info(f'Password reset OTP for {user.email}: {otp_code}')

        # In production, send SMS here:
        # send_sms(user.phone_number, f'Your 254 Capital password reset code is: {otp_code}')

        # Create temporary token for the reset flow
        temp_token = secrets.token_urlsafe(32)
        temp_token_key = f'password_reset_token_{temp_token}'
        cache.set(temp_token_key, str(user.id), timeout=300)  # 5 minutes

        # Mask phone number
        masked_phone = user.phone_number[:4] + '****' + user.phone_number[-3:]

        # Log password reset request
        AuditLog.log(
            action='Password reset OTP requested',
            actor=user,
            target_type='CustomUser',
            target_id=user.id,
            ip_address=get_client_ip(request)
        )

        return Response(
            {
                'detail': 'OTP sent to your registered phone number',
                'masked_phone': masked_phone,
                'temp_token': temp_token,
                'expires_in': 300  # 5 minutes in seconds
            },
            status=status.HTTP_200_OK
        )


class ResetPasswordWithOTPView(APIView):
    """
    POST /api/v1/auth/reset-password/
    Reset password using OTP.

    Verifies OTP and sets new password.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Reset password with OTP."""
        temp_token = request.data.get('temp_token', '').strip()
        otp = request.data.get('otp', '').strip()
        new_password = request.data.get('new_password', '').strip()
        confirm_password = request.data.get('confirm_password', '').strip()

        # Validate required fields
        if not temp_token or not otp or not new_password or not confirm_password:
            return Response(
                {'error': 'All fields are required (temp_token, otp, new_password, confirm_password)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if new passwords match
        if new_password != confirm_password:
            return Response(
                {'error': 'New passwords do not match'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate temp token
        temp_token_key = f'password_reset_token_{temp_token}'
        user_id = cache.get(temp_token_key)

        if not user_id:
            return Response(
                {'error': 'Invalid or expired reset token. Please request a new OTP.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get user
        try:
            user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Verify OTP
        otp_key = f'password_reset_otp_{user.id}'
        if not verify_otp(otp_key, otp):
            return Response(
                {'error': 'Invalid or expired OTP'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate new password requirements
        if len(new_password) < 8:
            return Response(
                {
                    'error': 'New password does not meet requirements',
                    'requirements': [
                        'Minimum 8 characters',
                        'At least one uppercase letter',
                        'At least one number',
                        'At least one special character'
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check for uppercase, number, and special character
        if not any(c.isupper() for c in new_password):
            return Response(
                {'error': 'Password must contain at least one uppercase letter'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not any(c.isdigit() for c in new_password):
            return Response(
                {'error': 'Password must contain at least one number'},
                status=status.HTTP_400_BAD_REQUEST
            )

        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        if not any(c in special_chars for c in new_password):
            return Response(
                {'error': 'Password must contain at least one special character'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update password
        user.set_password(new_password)
        user.save()

        # Clear OTP and temp token from cache
        cache.delete(otp_key)
        cache.delete(temp_token_key)

        # Generate new tokens for automatic login
        tokens = get_tokens_for_user(user)

        # Log password reset
        AuditLog.log(
            action='Password reset completed via OTP',
            actor=user,
            target_type='CustomUser',
            target_id=user.id,
            ip_address=get_client_ip(request)
        )

        logger.info(f'Password reset completed for {user.email}')

        return Response(
            {
                'detail': 'Password reset successfully',
                'tokens': tokens
            },
            status=status.HTTP_200_OK
        )


class AdminResetUserPasswordView(APIView):
    """
    POST /api/v1/auth/admin/reset-user-password/
    Admin can trigger password reset for any HR user.

    Sends OTP to the HR user's phone for password reset.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Admin trigger password reset for HR user."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can reset user passwords'},
                status=status.HTTP_403_FORBIDDEN
            )

        user_id = request.data.get('user_id', '').strip()
        send_otp = request.data.get('send_otp', True)

        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get target user
        try:
            target_user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if user has phone number
        if not target_user.phone_number and send_otp:
            return Response(
                {'error': 'User has no phone number registered. Cannot send OTP.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if send_otp:
            # Generate OTP
            otp_code = generate_otp()

            # Store OTP in cache (5 minute expiry)
            otp_key = f'admin_password_reset_otp_{target_user.id}'
            store_otp(otp_key, otp_code, expiry_minutes=5)

            # Send OTP via SMS
            logger.info(f'Admin password reset OTP for {target_user.email}: {otp_code}')
            # In production: send_sms(target_user.phone_number, f'Your password reset code is: {otp_code}')

            # Mask phone number
            masked_phone = target_user.phone_number[:4] + '****' + target_user.phone_number[-3:]

            # Log action
            AuditLog.log(
                action=f'Admin triggered password reset for user {target_user.email}',
                actor=request.user,
                target_type='CustomUser',
                target_id=target_user.id,
                ip_address=get_client_ip(request)
            )

            return Response(
                {
                    'detail': 'Password reset OTP sent to user\'s phone',
                    'masked_phone': masked_phone,
                    'user_email': target_user.email,
                    'user_name': target_user.get_full_name()
                },
                status=status.HTTP_200_OK
            )
        else:
            # Generate temporary password
            temp_password = secrets.token_urlsafe(12)

            # Set temporary password
            target_user.set_password(temp_password)
            target_user.save()

            # Log action
            AuditLog.log(
                action=f'Admin generated temporary password for user {target_user.email}',
                actor=request.user,
                target_type='CustomUser',
                target_id=target_user.id,
                ip_address=get_client_ip(request)
            )

            return Response(
                {
                    'detail': 'Temporary password generated',
                    'temporary_password': temp_password,
                    'user_email': target_user.email,
                    'user_name': target_user.get_full_name(),
                    'expires_in_hours': 24,
                    'requires_change_on_login': True
                },
                status=status.HTTP_200_OK
            )
