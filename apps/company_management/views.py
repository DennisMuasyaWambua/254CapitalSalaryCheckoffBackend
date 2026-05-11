"""
API views for Company Management.
"""

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import Organization, Role, OrganizationUser, AuditLog
from .serializers import (
    OrganizationSerializer, RoleSerializer, OrganizationUserSerializer,
    CreateOrganizationUserSerializer, ChangePasswordSerializer, AuditLogSerializer
)
from .permissions import IsHRAdmin, get_client_ip


class OrganizationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing organizations.

    Only accessible by HR admins and system admins.
    """

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, IsHRAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['name', 'contact_email']
    ordering_fields = ['name', 'created_at']
    ordering = ['-created_at']
    filterset_fields = ['is_active']

    def perform_create(self, serializer):
        """Create organization and log the event."""
        org = serializer.save(created_by=self.request.user)

        # Log organization creation
        AuditLog.log_event(
            event_type=AuditLog.EventType.ORGANIZATION_CREATED,
            user=self.request.user,
            organization=org,
            target_resource_type='organization',
            target_resource_id=org.id,
            ip_address=get_client_ip(self.request),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            result=AuditLog.Result.SUCCESS,
            metadata={'organization_name': org.name}
        )

    def perform_update(self, serializer):
        """Update organization and log the event."""
        org = serializer.save()

        # Log organization update
        AuditLog.log_event(
            event_type=AuditLog.EventType.ORGANIZATION_UPDATED,
            user=self.request.user,
            organization=org,
            target_resource_type='organization',
            target_resource_id=org.id,
            ip_address=get_client_ip(self.request),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            result=AuditLog.Result.SUCCESS
        )

    @action(detail=True, methods=['patch'])
    def deactivate(self, request, pk=None):
        """Deactivate an organization."""
        org = self.get_object()
        org.is_active = False
        org.save()

        # Log deactivation
        AuditLog.log_event(
            event_type=AuditLog.EventType.ORGANIZATION_DEACTIVATED,
            user=request.user,
            organization=org,
            target_resource_type='organization',
            target_resource_id=org.id,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            result=AuditLog.Result.SUCCESS
        )

        serializer = self.get_serializer(org)
        return Response(serializer.data)


class RoleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing roles within organizations.

    Roles are scoped to specific organizations. Only HR admins can
    create and modify roles.
    """

    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, IsHRAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['organization__name', 'name']
    filterset_fields = ['organization', 'is_active']

    def get_queryset(self):
        """Get roles filtered by organization if specified."""
        queryset = Role.objects.select_related('organization').all()

        # Filter by organization if specified in query params
        org_id = self.request.query_params.get('organization_id')
        if org_id:
            queryset = queryset.filter(organization_id=org_id)

        return queryset

    def perform_create(self, serializer):
        """Create role and log the event."""
        role = serializer.save(created_by=self.request.user)

        # Log role creation
        AuditLog.log_event(
            event_type=AuditLog.EventType.ROLE_CREATED,
            user=self.request.user,
            organization=role.organization,
            target_resource_type='role',
            target_resource_id=role.id,
            ip_address=get_client_ip(self.request),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            result=AuditLog.Result.SUCCESS,
            metadata={
                'role_name': role.name,
                'permissions': role.get_permissions_list()
            }
        )

    def perform_update(self, serializer):
        """Update role and log the event."""
        role = serializer.save()

        # Log role update
        AuditLog.log_event(
            event_type=AuditLog.EventType.ROLE_UPDATED,
            user=self.request.user,
            organization=role.organization,
            target_resource_type='role',
            target_resource_id=role.id,
            ip_address=get_client_ip(self.request),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            result=AuditLog.Result.SUCCESS,
            metadata={'permissions': role.get_permissions_list()}
        )

    def perform_destroy(self, instance):
        """Soft delete role (set is_active=False) and log the event."""
        # Check if role has active users
        if instance.assigned_users_count > 0:
            return Response(
                {'error': 'Cannot delete role with active users assigned.'},
                status=status.HTTP_409_CONFLICT
            )

        instance.is_active = False
        instance.save()

        # Log role deletion
        AuditLog.log_event(
            event_type=AuditLog.EventType.ROLE_DELETED,
            user=self.request.user,
            organization=instance.organization,
            target_resource_type='role',
            target_resource_id=instance.id,
            ip_address=get_client_ip(self.request),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            result=AuditLog.Result.SUCCESS
        )


class OrganizationUserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing organization users (user-role assignments).

    Handles user creation with automatic password generation and email delivery.
    """

    serializer_class = OrganizationUserSerializer
    permission_classes = [IsAuthenticated, IsHRAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    ordering_fields = ['created_at', 'user__email']
    ordering = ['-created_at']
    filterset_fields = ['organization', 'role', 'is_active']

    def get_queryset(self):
        """Get organization users with related data."""
        queryset = OrganizationUser.objects.select_related(
            'organization', 'user', 'role'
        ).all()

        # Filter by organization if specified
        org_id = self.request.query_params.get('organization_id')
        if org_id:
            queryset = queryset.filter(organization_id=org_id)

        return queryset

    @action(detail=False, methods=['post'], url_path='create-with-email')
    def create_user_with_email(self, request):
        """
        Create a new organization user with generated password and email delivery.

        Expected payload:
        {
            "organization_id": "uuid",
            "email": "user@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone_number": "+254712345678",  // optional
            "role_id": "uuid"
        }
        """
        org_id = request.data.get('organization_id')

        if not org_id:
            return Response(
                {'error': 'organization_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify organization exists and is active
        try:
            organization = Organization.objects.get(id=org_id, is_active=True)
        except Organization.DoesNotExist:
            return Response(
                {'error': 'Organization not found or inactive'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Create user using the serializer
        serializer = CreateOrganizationUserSerializer(
            data=request.data,
            context={
                'request': request,
                'organization_id': org_id
            }
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Create user and get generated password
            org_user, plain_password = serializer.save()

            # Send onboarding email
            self._send_onboarding_email(
                org_user=org_user,
                plain_password=plain_password,
                organization=organization
            )

            # Log user creation
            AuditLog.log_event(
                event_type=AuditLog.EventType.USER_CREATED,
                user=request.user,
                target_user=org_user.user,
                organization=organization,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                result=AuditLog.Result.SUCCESS,
                metadata={
                    'email': org_user.user.email,
                    'role': org_user.role.name
                }
            )

            # Return created user data
            response_serializer = OrganizationUserSerializer(org_user)
            return Response({
                'user': response_serializer.data,
                'onboarding_email_sent': True,
                'message': 'User created successfully. Onboarding email sent.'
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            # Log failure
            AuditLog.log_event(
                event_type=AuditLog.EventType.USER_CREATED,
                user=request.user,
                organization=organization,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                result=AuditLog.Result.FAILURE,
                error_message=str(e)
            )

            return Response(
                {'error': f'Failed to create user: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _send_onboarding_email(self, org_user, plain_password, organization):
        """Send onboarding email with credentials to new user."""
        subject = f'Welcome to {organization.name} - Your Account Details'

        # Prepare email context
        context = {
            'first_name': org_user.user.first_name,
            'last_name': org_user.user.last_name,
            'organization_name': organization.name,
            'role_name': org_user.role.name,
            'email': org_user.user.email,
            'password': plain_password,
            'login_url': settings.FRONTEND_URL + '/salary-checkoff/auth/login',
            'support_email': settings.DEFAULT_FROM_EMAIL,
            'can_view': org_user.role.can_view_loan_application,
            'can_approve': org_user.role.can_approve_loan_application,
            'can_decline': org_user.role.can_decline_loan_application,
        }

        # Render HTML email (you can create a template later)
        html_message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #0066cc;">Welcome to {organization.name}</h2>

                <p>Hi {org_user.user.first_name} {org_user.user.last_name},</p>

                <p>Your account has been created for the <strong>{organization.name}</strong> Loan Management System.
                You have been assigned the role of <strong>{org_user.role.name}</strong>.</p>

                <div style="background-color: #f0f0f0; padding: 15px; border-left: 4px solid #0066cc; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>Login Email:</strong> {org_user.user.email}</p>
                    <p style="margin: 5px 0;"><strong>Temporary Password:</strong> <code style="background-color: #fff; padding: 2px 5px;">{plain_password}</code></p>
                </div>

                <div style="background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 20px 0;">
                    <p><strong>⚠️ Security Notice:</strong> You will be required to change this temporary password on your first login.
                    Please keep these credentials confidential.</p>
                </div>

                <p style="text-align: center; margin: 30px 0;">
                    <a href="{context['login_url']}" style="display: inline-block; padding: 12px 30px; background-color: #0066cc; color: white; text-decoration: none; border-radius: 5px;">
                        Log In to Portal
                    </a>
                </p>

                <p><strong>Your Role Permissions:</strong></p>
                <ul>
                    {'<li>View pending loan application details</li>' if context['can_view'] else ''}
                    {'<li>Approve loan applications</li>' if context['can_approve'] else ''}
                    {'<li>Decline loan applications</li>' if context['can_decline'] else ''}
                </ul>

                <p>If you have any questions, please contact your HR administrator or our support team at
                <a href="mailto:{context['support_email']}">{context['support_email']}</a>.</p>

                <p>Best regards,<br>{organization.name} Team</p>

                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="font-size: 12px; color: #777; text-align: center;">
                    This email contains sensitive information. Please do not forward it to others.
                </p>
            </div>
        </body>
        </html>
        """

        plain_message = strip_tags(html_message)

        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[org_user.user.email],
            html_message=html_message,
            fail_silently=False
        )

    @action(detail=True, methods=['patch'])
    def deactivate(self, request, pk=None):
        """Deactivate an organization user."""
        org_user = self.get_object()
        org_user.is_active = False
        org_user.save()

        # Log deactivation
        AuditLog.log_event(
            event_type=AuditLog.EventType.USER_DEACTIVATED,
            user=request.user,
            target_user=org_user.user,
            organization=org_user.organization,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            result=AuditLog.Result.SUCCESS
        )

        serializer = self.get_serializer(org_user)
        return Response(serializer.data)


class ChangePasswordView(viewsets.GenericViewSet):
    """
    ViewSet for changing user password.

    Available to all authenticated users.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """Change the current user's password."""
        serializer = self.get_serializer(
            data=request.data,
            context={'request': request}
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Change password
        serializer.save()

        # Log password change
        try:
            org_user = OrganizationUser.objects.get(user=request.user, is_active=True)
            organization = org_user.organization
        except OrganizationUser.DoesNotExist:
            organization = None

        AuditLog.log_event(
            event_type=AuditLog.EventType.PASSWORD_CHANGED,
            user=request.user,
            organization=organization,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            result=AuditLog.Result.SUCCESS
        )

        return Response({
            'message': 'Password changed successfully. Please log in again with your new password.'
        }, status=status.HTTP_200_OK)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for audit logs.

    Only accessible by system admins and HR admins can see their org's logs.
    """

    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsHRAdmin]
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend]
    ordering_fields = ['created_at', 'event_type']
    ordering = ['-created_at']
    filterset_fields = ['event_type', 'result', 'organization']

    def get_queryset(self):
        """Get audit logs filtered by organization for HR admins."""
        queryset = AuditLog.objects.select_related(
            'user', 'target_user', 'organization'
        ).all()

        # System admins see all logs
        if self.request.user.role == 'admin':
            return queryset

        # HR managers only see logs from their organization
        try:
            org_user = OrganizationUser.objects.get(
                user=self.request.user, is_active=True
            )
            return queryset.filter(organization=org_user.organization)
        except OrganizationUser.DoesNotExist:
            return queryset.none()
