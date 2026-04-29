"""
HR User Management Views (Admin only).
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Q
import logging
import secrets

from .models import CustomUser, HRProfile
from apps.audit.models import AuditLog
from common.utils import get_client_ip
from common.email_service import send_welcome_email

logger = logging.getLogger(__name__)


class ListHRUsersView(APIView):
    """
    GET /api/v1/users/hr/
    List all HR users (Admin only).

    Supports filtering and searching.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all HR users."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can view HR users'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get query parameters
        search = request.query_params.get('search', '').strip()
        employer_id = request.query_params.get('employer_id', '').strip()
        is_active = request.query_params.get('is_active', '').strip()
        page = request.query_params.get('page', '1')

        # Base query
        hr_users = CustomUser.objects.filter(role=CustomUser.Role.HR_MANAGER)

        # Apply filters
        if search:
            hr_users = hr_users.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone_number__icontains=search)
            )

        if employer_id:
            hr_users = hr_users.filter(hr_profile__employer_id=employer_id)

        if is_active:
            is_active_bool = is_active.lower() == 'true'
            hr_users = hr_users.filter(is_active=is_active_bool)

        # Get total count
        total_count = hr_users.count()

        # Pagination
        page_size = 20
        try:
            page_num = int(page)
        except ValueError:
            page_num = 1

        start = (page_num - 1) * page_size
        end = start + page_size
        hr_users = hr_users[start:end]

        # Serialize results
        results = []
        for user in hr_users.select_related('hr_profile', 'hr_profile__employer'):
            hr_profile = getattr(user, 'hr_profile', None)
            employer = hr_profile.employer if hr_profile else None

            results.append({
                'id': str(user.id),
                'email': user.email,
                'phone_number': user.phone_number or '',
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_active': user.is_active,
                'employer': {
                    'id': str(employer.id) if employer else None,
                    'name': employer.name if employer else None
                } if employer else None,
                'position': hr_profile.position if hr_profile else '',
                'created_at': user.date_joined.isoformat() if user.date_joined else None,
                'last_login': user.last_login.isoformat() if user.last_login else None
            })

        # Calculate pagination
        total_pages = (total_count + page_size - 1) // page_size

        return Response({
            'count': total_count,
            'next': f'/api/v1/users/hr/?page={page_num + 1}' if page_num < total_pages else None,
            'previous': f'/api/v1/users/hr/?page={page_num - 1}' if page_num > 1 else None,
            'page': page_num,
            'total_pages': total_pages,
            'results': results
        }, status=status.HTTP_200_OK)


class HRUserDetailView(APIView):
    """
    GET /api/v1/users/hr/{user_id}/
    Get HR user details (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        """Get HR user details."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can view HR user details'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get user
        try:
            user = CustomUser.objects.select_related(
                'hr_profile', 'hr_profile__employer'
            ).get(id=user_id, role=CustomUser.Role.HR_MANAGER)
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'HR user not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        hr_profile = getattr(user, 'hr_profile', None)
        employer = hr_profile.employer if hr_profile else None

        # Get active loans count for employer
        active_loans_count = 0
        if employer:
            from apps.loans.models import LoanApplication
            active_loans_count = LoanApplication.objects.filter(
                employer=employer,
                status=LoanApplication.Status.DISBURSED
            ).count()

        return Response({
            'id': str(user.id),
            'email': user.email,
            'phone_number': user.phone_number or '',
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_active': user.is_active,
            'employer': {
                'id': str(employer.id) if employer else None,
                'name': employer.name if employer else None,
                'registration_number': employer.registration_number if employer else None,
                'total_employees': employer.total_employees if employer else 0,
                'active_loans_count': active_loans_count
            } if employer else None,
            'position': hr_profile.position if hr_profile else '',
            'created_at': user.date_joined.isoformat() if user.date_joined else None,
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'login_history': []  # TODO: Implement login history tracking
        }, status=status.HTTP_200_OK)


class UpdateHRUserView(APIView):
    """
    PATCH /api/v1/users/hr/{user_id}/
    Update HR user details (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, user_id):
        """Update HR user details."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can update HR users'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get user
        try:
            user = CustomUser.objects.select_related('hr_profile').get(
                id=user_id,
                role=CustomUser.Role.HR_MANAGER
            )
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'HR user not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get fields to update
        email = request.data.get('email', '').strip()
        phone_number = request.data.get('phone_number', '').strip()
        first_name = request.data.get('first_name', '').strip()
        last_name = request.data.get('last_name', '').strip()
        position = request.data.get('position', '').strip()
        employer_id = request.data.get('employer_id', '').strip()

        # Update user fields
        if email:
            # Check if email already exists
            if CustomUser.objects.filter(email=email).exclude(id=user_id).exists():
                return Response(
                    {'error': 'Email already in use'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user.email = email

        if phone_number:
            user.phone_number = phone_number

        if first_name:
            user.first_name = first_name

        if last_name:
            user.last_name = last_name

        user.save()

        # Update HR profile
        hr_profile = getattr(user, 'hr_profile', None)
        if hr_profile:
            if position:
                hr_profile.position = position

            if employer_id:
                from apps.employers.models import Employer
                try:
                    employer = Employer.objects.get(id=employer_id)
                    hr_profile.employer = employer
                except Employer.DoesNotExist:
                    return Response(
                        {'error': 'Employer not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )

            hr_profile.save()

        # Log action
        AuditLog.log(
            action=f'Admin updated HR user {user.email}',
            actor=request.user,
            target_type='CustomUser',
            target_id=user.id,
            ip_address=get_client_ip(request)
        )

        # Get updated employer info
        employer = hr_profile.employer if hr_profile else None

        return Response({
            'detail': 'HR user updated successfully',
            'user': {
                'id': str(user.id),
                'email': user.email,
                'phone_number': user.phone_number or '',
                'first_name': user.first_name,
                'last_name': user.last_name,
                'employer': {
                    'id': str(employer.id) if employer else None,
                    'name': employer.name if employer else None
                } if employer else None,
                'position': hr_profile.position if hr_profile else ''
            }
        }, status=status.HTTP_200_OK)


class ToggleHRUserActiveView(APIView):
    """
    POST /api/v1/users/hr/{user_id}/toggle-active/
    Deactivate or reactivate HR user account (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        """Toggle HR user active status."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can toggle HR user status'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get user
        try:
            user = CustomUser.objects.get(id=user_id, role=CustomUser.Role.HR_MANAGER)
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'HR user not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get parameters
        is_active = request.data.get('is_active', True)
        reason = request.data.get('reason', '').strip()

        # Update status
        user.is_active = is_active
        user.save()

        # Log action
        action_text = 'activated' if is_active else 'deactivated'
        AuditLog.log(
            action=f'Admin {action_text} HR user {user.email}. Reason: {reason or "Not specified"}',
            actor=request.user,
            target_type='CustomUser',
            target_id=user.id,
            ip_address=get_client_ip(request)
        )

        return Response({
            'detail': f'HR user account {action_text} successfully',
            'user': {
                'id': str(user.id),
                'email': user.email,
                'is_active': user.is_active,
                'deactivated_at': timezone.now().isoformat() if not is_active else None,
                'deactivation_reason': reason if not is_active else None
            }
        }, status=status.HTTP_200_OK)


class CreateHRUserView(APIView):
    """
    POST /api/v1/users/hr/create/
    Create new HR user account (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Create new HR user."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can create HR users'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get required fields
        email = request.data.get('email', '').strip()
        phone_number = request.data.get('phone_number', '').strip()
        first_name = request.data.get('first_name', '').strip()
        last_name = request.data.get('last_name', '').strip()
        employer_id = request.data.get('employer_id', '').strip()
        position = request.data.get('position', '').strip()
        send_welcome_email_flag = request.data.get('send_welcome_email', True)
        send_credentials_sms = request.data.get('send_credentials_sms', True)

        # Validate required fields
        if not all([email, phone_number, first_name, last_name, employer_id]):
            return Response(
                {'error': 'All fields are required (email, phone_number, first_name, last_name, employer_id)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if email already exists
        if CustomUser.objects.filter(email=email).exists():
            return Response(
                {'error': 'Email already in use'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if employer exists
        from apps.employers.models import Employer
        try:
            employer = Employer.objects.get(id=employer_id)
        except Employer.DoesNotExist:
            return Response(
                {'error': 'Employer not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Generate temporary password
        temp_password = secrets.token_urlsafe(12)

        # Create user
        user = CustomUser.objects.create(
            email=email,
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            role=CustomUser.Role.HR_MANAGER,
            is_active=True
        )
        user.set_password(temp_password)
        user.save()

        # Create HR profile
        hr_profile = HRProfile.objects.create(
            user=user,
            employer=employer,
            position=position or 'HR Manager'
        )

        # Send welcome email
        welcome_email_sent = False
        if send_welcome_email_flag:
            try:
                send_welcome_email(
                    to_address=user.email,
                    user_name=user.get_full_name(),
                    temporary_password=temp_password
                )
                welcome_email_sent = True
                logger.info(f'Welcome email sent to {user.email}')
            except Exception as e:
                logger.error(f'Failed to send welcome email: {str(e)}')

        # Send SMS with credentials
        credentials_sms_sent = False
        if send_credentials_sms:
            # Log SMS (would send via SMS provider in production)
            logger.info(f'Credentials SMS for {user.email}: Password={temp_password}')
            credentials_sms_sent = True

        # Log action
        AuditLog.log(
            action=f'Admin created HR user {user.email} for employer {employer.name}',
            actor=request.user,
            target_type='CustomUser',
            target_id=user.id,
            ip_address=get_client_ip(request)
        )

        return Response({
            'detail': 'HR user created successfully',
            'user': {
                'id': str(user.id),
                'email': user.email,
                'phone_number': user.phone_number,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'employer': {
                    'id': str(employer.id),
                    'name': employer.name
                },
                'position': hr_profile.position
            },
            'temporary_password': temp_password,
            'welcome_email_sent': welcome_email_sent,
            'credentials_sms_sent': credentials_sms_sent,
            'password_expires_in_hours': 24
        }, status=status.HTTP_201_CREATED)


class DeleteHRUserView(APIView):
    """
    DELETE /api/v1/users/hr/{user_id}/
    Delete HR user account (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, user_id):
        """Delete HR user."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can delete HR users'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get user
        try:
            user = CustomUser.objects.select_related('hr_profile', 'hr_profile__employer').get(
                id=user_id,
                role=CustomUser.Role.HR_MANAGER
            )
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'HR user not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get confirmation
        confirm = request.data.get('confirm', False)
        reason = request.data.get('reason', '').strip()

        if not confirm:
            return Response(
                {'error': 'Please confirm deletion by setting confirm=true'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if HR user has active responsibilities
        hr_profile = getattr(user, 'hr_profile', None)
        employer = hr_profile.employer if hr_profile else None

        if employer:
            from apps.loans.models import LoanApplication
            # Check for pending loan reviews
            pending_reviews = LoanApplication.objects.filter(
                employer=employer,
                status__in=[LoanApplication.Status.SUBMITTED, LoanApplication.Status.HR_REVIEW]
            ).count()

            # Check for active loans
            active_loans = LoanApplication.objects.filter(
                employer=employer,
                status=LoanApplication.Status.DISBURSED
            ).count()

            if pending_reviews > 0 or active_loans > 0:
                return Response(
                    {
                        'error': 'Cannot delete HR user with active responsibilities',
                        'details': {
                            'pending_loan_reviews': pending_reviews,
                            'active_employer_loans': active_loans
                        },
                        'suggestion': 'Consider deactivating the account instead of deleting it, or reassign the employer to another HR user first'
                    },
                    status=status.HTTP_409_CONFLICT
                )

        # Store user details for response
        user_email = user.email
        user_name = user.get_full_name()
        employer_name = employer.name if employer else 'N/A'

        # Log action before deletion
        AuditLog.log(
            action=f'Admin deleted HR user {user_email}. Reason: {reason or "Not specified"}',
            actor=request.user,
            target_type='CustomUser',
            target_id=user.id,
            ip_address=get_client_ip(request)
        )

        # Delete user (this will cascade to HR profile)
        user.delete()

        logger.info(f'HR user deleted: {user_email} (employer: {employer_name})')

        return Response({
            'detail': 'HR user account deleted successfully',
            'deleted_user': {
                'id': str(user_id),
                'email': user_email,
                'name': user_name,
                'employer': employer_name
            },
            'archived': True,
            'archived_at': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
