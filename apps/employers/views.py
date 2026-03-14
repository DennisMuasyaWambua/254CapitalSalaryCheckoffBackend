"""
Employer management APIViews.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from .models import Employer
from .serializers import (
    EmployerListSerializer, EmployerDetailSerializer,
    EmployerCreateSerializer, EmployerUpdateSerializer
)
from apps.accounts.permissions import IsAdmin, IsHROrAdmin
from common.pagination import StandardPagination
from common.utils import get_client_ip
from apps.audit.models import AuditLog
from common.email_service import send_email, send_internal_alert
import logging

logger = logging.getLogger(__name__)


class EmployerListView(APIView):
    """
    GET /api/v1/employers/
    List all active employers.

    Supports:
    - ?search= — search by name
    - Pagination

    Used for registration dropdown (employees) and browsing (HR/Admin).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List employers."""
        # Get all active employers
        employers = Employer.objects.filter(is_active=True)

        # Apply search filter
        search = request.query_params.get('search', '').strip()
        if search:
            employers = employers.filter(
                Q(name__icontains=search) |
                Q(registration_number__icontains=search)
            )

        # Order by name
        employers = employers.order_by('name')

        # Paginate
        paginator = StandardPagination()
        page = paginator.paginate_queryset(employers, request)

        serializer = EmployerListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class EmployerCreateView(APIView):
    """
    POST /api/v1/employers/
    Onboard a new employer (Admin only).
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        """Create new employer."""
        serializer = EmployerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create employer
        employer = serializer.save(onboarded_by=request.user)

        # Log onboarding
        AuditLog.log(
            action=f'Employer onboarded: {employer.name}',
            actor=request.user,
            target_type='Employer',
            target_id=employer.id,
            metadata={'employer_name': employer.name},
            ip_address=get_client_ip(request)
        )

        logger.info(f'Employer onboarded: {employer.name} by {request.user.id}')

        # Send welcome email to HR contact
        if employer.hr_contact_email:
            try:
                subject = 'Welcome to 254 Capital - Employer Onboarding Successful'
                body_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                        .header {{ background-color: #27ae60; color: white; padding: 20px; text-align: center; }}
                        .content {{ padding: 20px; background-color: #f9f9f9; }}
                        .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
                        .info-box {{ background-color: #e8f5e9; border-left: 4px solid #27ae60; padding: 15px; margin: 15px 0; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Welcome to 254 Capital</h1>
                        </div>
                        <div class="content">
                            <h2>Hello {employer.hr_contact_name},</h2>
                            <p>We are pleased to inform you that <strong>{employer.name}</strong> has been successfully onboarded to the 254 Capital Salary Check-Off Loan Management System.</p>

                            <div class="info-box">
                                <p><strong>Employer Details:</strong></p>
                                <ul>
                                    <li><strong>Company Name:</strong> {employer.name}</li>
                                    <li><strong>Registration Number:</strong> {employer.registration_number}</li>
                                    <li><strong>Payroll Cycle Day:</strong> Day {employer.payroll_cycle_day} of each month</li>
                                    <li><strong>HR Contact:</strong> {employer.hr_contact_name}</li>
                                    <li><strong>Contact Phone:</strong> {employer.hr_contact_phone}</li>
                                </ul>
                            </div>

                            <p>As an onboarded employer, your employees can now:</p>
                            <ul>
                                <li>Register on the platform using your organization's details</li>
                                <li>Apply for salary check-off loans</li>
                                <li>Track their loan applications and repayment schedules</li>
                            </ul>

                            <p>Your HR team will be able to:</p>
                            <ul>
                                <li>Review and approve employee loan applications</li>
                                <li>Submit monthly salary deduction remittances</li>
                                <li>Manage employee records and loan statuses</li>
                            </ul>

                            <p>For HR manager access, please contact our admin team at david.muema@254-capital.com</p>

                            <p>If you have any questions or need assistance, please don't hesitate to reach out.</p>

                            <p>Best regards,<br>
                            <strong>254 Capital Team</strong></p>
                        </div>
                        <div class="footer">
                            <p>&copy; 2026 254 Capital. All rights reserved.</p>
                            <p>This is an automated message. Please do not reply to this email.</p>
                        </div>
                    </div>
                </body>
                </html>
                """
                send_email(employer.hr_contact_email, subject, body_html, cc_address='david.muema@254-capital.com')
                logger.info(f'Employer onboarding email sent to {employer.hr_contact_email}')
            except Exception as e:
                logger.error(f'Failed to send employer onboarding email: {str(e)}')

        # Send internal alert to admin
        try:
            alert_message = f"""
            <p><strong>New Employer Onboarded</strong></p>
            <ul>
                <li><strong>Company Name:</strong> {employer.name}</li>
                <li><strong>Registration Number:</strong> {employer.registration_number}</li>
                <li><strong>Address:</strong> {employer.address}</li>
                <li><strong>Payroll Cycle Day:</strong> Day {employer.payroll_cycle_day}</li>
                <li><strong>HR Contact Name:</strong> {employer.hr_contact_name}</li>
                <li><strong>HR Contact Email:</strong> {employer.hr_contact_email}</li>
                <li><strong>HR Contact Phone:</strong> {employer.hr_contact_phone}</li>
                <li><strong>Onboarded By:</strong> {request.user.get_full_name() or request.user.email}</li>
            </ul>
            """
            send_internal_alert(
                subject=f'New Employer Onboarded - {employer.name}',
                message=alert_message,
                alert_type='success'
            )
        except Exception as e:
            logger.error(f'Failed to send internal alert for employer onboarding: {str(e)}')

        return Response(
            EmployerDetailSerializer(employer).data,
            status=status.HTTP_201_CREATED
        )


class EmployerDetailView(APIView):
    """
    GET  /api/v1/employers/<uuid:pk>/  — Get employer details
    PUT  /api/v1/employers/<uuid:pk>/  — Update employer (Admin only)
    """

    permission_classes = [IsAuthenticated, IsHROrAdmin]

    def get_object(self, pk, user):
        """Get employer with permission check."""
        try:
            employer = Employer.objects.get(pk=pk)

            # HR can only view their own employer
            if user.role == 'hr_manager':
                hr_profile = getattr(user, 'hr_profile', None)
                if not hr_profile or hr_profile.employer != employer:
                    return None

            return employer

        except Employer.DoesNotExist:
            return None

    def get(self, request, pk):
        """Get employer details."""
        employer = self.get_object(pk, request.user)

        if not employer:
            return Response(
                {'detail': 'Employer not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = EmployerDetailSerializer(employer)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        """Update employer (Admin only)."""
        # Check admin permission
        if request.user.role != 'admin':
            return Response(
                {'detail': 'Only admins can update employer information.'},
                status=status.HTTP_403_FORBIDDEN
            )

        employer = self.get_object(pk, request.user)

        if not employer:
            return Response(
                {'detail': 'Employer not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = EmployerUpdateSerializer(employer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_employer = serializer.save()

        # Log update
        AuditLog.log(
            action=f'Employer updated: {employer.name}',
            actor=request.user,
            target_type='Employer',
            target_id=employer.id,
            metadata={'fields_updated': list(serializer.validated_data.keys())},
            ip_address=get_client_ip(request)
        )

        logger.info(f'Employer updated: {employer.name} by {request.user.id}')

        return Response(
            EmployerDetailSerializer(updated_employer).data,
            status=status.HTTP_200_OK
        )
