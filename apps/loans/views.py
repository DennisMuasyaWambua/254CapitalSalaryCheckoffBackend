"""
Loan application management APIViews.

Handles the complete loan lifecycle:
- Employee: apply, view applications, calculator
- HR: review queue, approve/decline, batch operations
- Admin: credit assessment, disbursement
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Q, Count, Sum
from django.utils import timezone
from decimal import Decimal
from datetime import date

from .models import LoanApplication, LoanStatusHistory, RepaymentSchedule, IdempotencyLog
from .serializers import (
    LoanApplicationListSerializer, LoanApplicationDetailSerializer,
    LoanApplicationCreateSerializer, LoanApplicationUpdateSerializer,
    LoanCalculatorSerializer, HRReviewSerializer, BatchApprovalSerializer,
    AdminCreditAssessmentSerializer, AdminDisbursementSerializer,
    AdminBulkDisbursementSerializer
)
import hashlib
import json
from .services import (
    calculate_flat_interest, calculate_amortized, generate_application_number,
    calculate_first_deduction_date, generate_repayment_schedule
)
from apps.accounts.permissions import IsEmployee, IsHRManager, IsAdmin, IsHROrAdmin
from common.pagination import StandardPagination
from common.utils import get_client_ip
from common.email_service import send_email, send_internal_alert
from apps.audit.models import AuditLog
import logging

logger = logging.getLogger(__name__)


class LoanApplicationListCreateView(APIView):
    """
    GET   /api/v1/loans/applications/  — List employee's own loan applications
    POST  /api/v1/loans/applications/  — Submit new loan application
    """

    permission_classes = [IsAuthenticated, IsEmployee]

    def get(self, request):
        """List employee's applications with filtering."""
        # Get employee's applications
        applications = LoanApplication.objects.filter(
            employee=request.user
        ).select_related('employer').order_by('-created_at')

        # Apply status filter
        status_filter = request.query_params.get('status')
        if status_filter:
            applications = applications.filter(status=status_filter)

        # Apply date range filter
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        if from_date:
            applications = applications.filter(created_at__gte=from_date)
        if to_date:
            applications = applications.filter(created_at__lte=to_date)

        # Paginate
        paginator = StandardPagination()
        page = paginator.paginate_queryset(applications, request)

        serializer = LoanApplicationListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """Submit new loan application."""
        serializer = LoanApplicationCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        # Get employee profile
        employee_profile = request.user.employee_profile

        # Calculate repayment
        calc = calculate_flat_interest(
            serializer.validated_data['principal_amount'],
            Decimal('0.05'),  # 5% flat interest
            serializer.validated_data['repayment_months']
        )

        # Generate application number
        app_number = generate_application_number()

        # Create application
        loan = LoanApplication.objects.create(
            application_number=app_number,
            employee=request.user,
            employer=employee_profile.employer,
            principal_amount=serializer.validated_data['principal_amount'],
            repayment_months=serializer.validated_data['repayment_months'],
            disbursement_method=serializer.validated_data['disbursement_method'],
            purpose=serializer.validated_data.get('purpose', ''),
            total_repayment=calc['total_repayment'],
            monthly_deduction=calc['monthly_deduction'],
            status=LoanApplication.Status.SUBMITTED,
            terms_accepted=serializer.validated_data['terms_accepted'],
            terms_accepted_at=timezone.now() if serializer.validated_data['terms_accepted'] else None,
            # Bank details for disbursement
            bank_name=serializer.validated_data.get('bank_name', ''),
            bank_branch=serializer.validated_data.get('bank_branch', ''),
            account_number=serializer.validated_data.get('account_number', ''),
        )

        # Create initial status history
        LoanStatusHistory.objects.create(
            application=loan,
            status=LoanApplication.Status.SUBMITTED,
            actor=request.user,
            comment='Application submitted'
        )

        # Trigger notification to HR (async)
        from apps.notifications.tasks import notify_hr_new_application
        notify_hr_new_application.delay(str(loan.id))

        # Log action
        AuditLog.log(
            action=f'Loan application submitted: {loan.application_number}',
            actor=request.user,
            target_type='LoanApplication',
            target_id=loan.id,
            metadata={
                'principal': str(loan.principal_amount),
                'months': loan.repayment_months
            },
            ip_address=get_client_ip(request)
        )

        logger.info(f'Loan application submitted: {loan.application_number}')

        # Send email notification to employee if they have email
        if request.user.email:
            try:
                subject = 'Loan Application Submitted - 254 Capital'
                body_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                        .header {{ background-color: #3498db; color: white; padding: 20px; text-align: center; }}
                        .content {{ padding: 20px; background-color: #f9f9f9; }}
                        .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
                        .info-box {{ background-color: #e8f4fd; border-left: 4px solid #3498db; padding: 15px; margin: 15px 0; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Application Submitted</h1>
                        </div>
                        <div class="content">
                            <h2>Hello {request.user.get_full_name()},</h2>
                            <p>Your loan application has been successfully submitted and is now under review.</p>

                            <div class="info-box">
                                <p><strong>Application Details:</strong></p>
                                <ul>
                                    <li><strong>Application Number:</strong> {loan.application_number}</li>
                                    <li><strong>Loan Amount:</strong> KES {loan.principal_amount:,.2f}</li>
                                    <li><strong>Repayment Period:</strong> {loan.repayment_months} months</li>
                                    <li><strong>Monthly Deduction:</strong> KES {loan.monthly_deduction:,.2f}</li>
                                    <li><strong>Total Repayment:</strong> KES {loan.total_repayment:,.2f}</li>
                                </ul>
                            </div>

                            <p>You will receive updates on your application status.</p>

                            <p>Best regards,<br>
                            <strong>254 Capital Team</strong></p>
                        </div>
                        <div class="footer">
                            <p>&copy; 2026 254 Capital. All rights reserved.</p>
                        </div>
                    </div>
                </body>
                </html>
                """
                send_email(request.user.email, subject, body_html)
                logger.info(f'Application submission email sent to {request.user.email}')
            except Exception as e:
                logger.error(f'Failed to send application submission email: {str(e)}')

        # Send internal alert to admin
        try:
            alert_message = f"""
            <p><strong>New Loan Application Submitted</strong></p>
            <ul>
                <li><strong>Application Number:</strong> {loan.application_number}</li>
                <li><strong>Employee:</strong> {request.user.get_full_name()}</li>
                <li><strong>Employer:</strong> {employee_profile.employer.name}</li>
                <li><strong>Loan Amount:</strong> KES {loan.principal_amount:,.2f}</li>
                <li><strong>Repayment Period:</strong> {loan.repayment_months} months</li>
            </ul>
            """
            send_internal_alert(
                subject=f'New Loan Application - {loan.application_number}',
                message=alert_message,
                alert_type='info'
            )
        except Exception as e:
            logger.error(f'Failed to send internal alert: {str(e)}')

        return Response(
            LoanApplicationDetailSerializer(loan).data,
            status=status.HTTP_201_CREATED
        )


class LoanApplicationDetailView(APIView):
    """
    GET    /api/v1/loans/applications/<uuid:pk>/  — Get application detail
    PATCH  /api/v1/loans/applications/<uuid:pk>/  — Update application (employee, submitted status only)
    """

    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        """Get application with permission check."""
        try:
            app = LoanApplication.objects.select_related(
                'employee', 'employer'
            ).prefetch_related(
                'status_history', 'repayment_schedule'
            ).get(pk=pk)

            # Check access based on role
            if user.role == 'employee' and app.employee != user:
                return None

            if user.role == 'hr_manager':
                hr_profile = getattr(user, 'hr_profile', None)
                if not hr_profile or app.employer != hr_profile.employer:
                    return None

            # Admin can see all
            return app

        except LoanApplication.DoesNotExist:
            return None

    def get(self, request, pk):
        """Get application detail."""
        app = self.get_object(pk, request.user)

        if not app:
            return Response(
                {'detail': 'Application not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = LoanApplicationDetailSerializer(app)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        """Update application (employee only, submitted status only)."""
        if request.user.role != 'employee':
            return Response(
                {'detail': 'Only employees can update their applications.'},
                status=status.HTTP_403_FORBIDDEN
            )

        app = self.get_object(pk, request.user)

        if not app:
            return Response(
                {'detail': 'Application not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if app.status != LoanApplication.Status.SUBMITTED:
            return Response(
                {'detail': 'Only submitted applications can be updated.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = LoanApplicationUpdateSerializer(app, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_app = serializer.save()

        # Log update
        AuditLog.log(
            action=f'Loan application updated: {app.application_number}',
            actor=request.user,
            target_type='LoanApplication',
            target_id=app.id,
            metadata={'fields_updated': list(serializer.validated_data.keys())},
            ip_address=get_client_ip(request)
        )

        return Response(
            LoanApplicationDetailSerializer(updated_app).data,
            status=status.HTTP_200_OK
        )


class LoanCalculatorView(APIView):
    """
    POST /api/v1/loans/calculator/
    Calculate loan repayment (server-side verification).

    Public endpoint - no auth required.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Calculate loan repayment."""
        serializer = LoanCalculatorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        principal = serializer.validated_data['principal']
        months = int(serializer.validated_data['months'])
        calc_type = serializer.validated_data['calculation_type']
        annual_rate = serializer.validated_data.get('annual_rate', Decimal('0.05'))

        if calc_type == 'flat':
            result = calculate_flat_interest(principal, annual_rate, months)

            # Calculate first deduction date (using today as disbursement)
            first_deduction = calculate_first_deduction_date(timezone.now().date())

            # Generate schedule preview
            schedule = []
            balance = result['total_repayment']
            current_date = first_deduction

            for i in range(1, months + 1):
                amount = result['monthly_deduction']
                if i == months:
                    # Last installment
                    amount = balance

                balance -= amount

                schedule.append({
                    'installment_number': i,
                    'due_date': current_date.isoformat(),
                    'amount': str(amount),
                    'running_balance': str(balance),
                    'is_first_deduction': (i == 1)
                })

                # Next month
                from dateutil.relativedelta import relativedelta
                current_date = current_date + relativedelta(months=1)

            return Response({
                'calculation_type': 'flat',
                'principal_amount': str(principal),
                'interest_rate': str(annual_rate),
                'repayment_months': months,
                'total_repayment': str(result['total_repayment']),
                'monthly_deduction': str(result['monthly_deduction']),
                'interest_amount': str(result['interest_amount']),
                'first_deduction_date': first_deduction.isoformat(),
                'schedule': schedule
            }, status=status.HTTP_200_OK)

        else:  # amortized
            result = calculate_amortized(principal, annual_rate, months)
            first_deduction = calculate_first_deduction_date(timezone.now().date())

            return Response({
                'calculation_type': 'amortized',
                'principal_amount': str(principal),
                'annual_interest_rate': str(annual_rate),
                'repayment_months': months,
                'monthly_payment': str(result['monthly_payment']),
                'total_repayment': str(result['total_repayment']),
                'interest_amount': str(result['interest_amount']),
                'first_deduction_date': first_deduction.isoformat(),
                'schedule': result['schedule']
            }, status=status.HTTP_200_OK)


# HR VIEWS

class HRPendingApplicationsView(APIView):
    """
    GET /api/v1/loans/hr/pending/
    List pending applications for HR's employer (status=submitted).
    """

    permission_classes = [IsAuthenticated, IsHRManager]

    def get(self, request):
        """List pending applications."""
        hr_profile = request.user.hr_profile

        # Get submitted applications for employer
        applications = LoanApplication.objects.filter(
            employer=hr_profile.employer,
            status=LoanApplication.Status.SUBMITTED
        ).select_related('employee', 'employee__employee_profile', 'employer').order_by('-created_at')

        # Apply search filter
        search = request.query_params.get('search', '').strip()
        if search:
            applications = applications.filter(
                Q(application_number__icontains=search) |
                Q(employee__first_name__icontains=search) |
                Q(employee__last_name__icontains=search) |
                Q(employee__phone_number__icontains=search)
            )

        # Paginate
        paginator = StandardPagination()
        page = paginator.paginate_queryset(applications, request)

        serializer = LoanApplicationListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class HRAllApplicationsView(APIView):
    """
    GET /api/v1/loans/hr/all/
    List all applications for HR's employer (with filtering).
    """

    permission_classes = [IsAuthenticated, IsHRManager]

    def get(self, request):
        """List all applications for employer."""
        hr_profile = request.user.hr_profile

        # Get all applications for employer
        applications = LoanApplication.objects.filter(
            employer=hr_profile.employer
        ).select_related('employee', 'employee__employee_profile', 'employer').order_by('-created_at')

        # Apply status filter
        status_filter = request.query_params.get('status')
        if status_filter:
            applications = applications.filter(status=status_filter)

        # Apply date range filter
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        if from_date:
            applications = applications.filter(created_at__gte=from_date)
        if to_date:
            applications = applications.filter(created_at__lte=to_date)

        # Apply search
        search = request.query_params.get('search', '').strip()
        if search:
            applications = applications.filter(
                Q(application_number__icontains=search) |
                Q(employee__first_name__icontains=search) |
                Q(employee__last_name__icontains=search)
            )

        # Paginate
        paginator = StandardPagination()
        page = paginator.paginate_queryset(applications, request)

        serializer = LoanApplicationListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class HRReviewApplicationView(APIView):
    """
    POST /api/v1/loans/hr/<uuid:pk>/review/
    HR approve or decline application.
    """

    permission_classes = [IsAuthenticated, IsHRManager]

    def post(self, request, pk):
        """Review (approve/decline) application."""
        hr_profile = request.user.hr_profile

        # Get application
        try:
            app = LoanApplication.objects.get(pk=pk)
        except LoanApplication.DoesNotExist:
            return Response(
                {'detail': 'Application not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check employer match
        if app.employer != hr_profile.employer:
            return Response(
                {'detail': 'You can only review applications from your employer.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check status
        if app.status != LoanApplication.Status.SUBMITTED:
            return Response(
                {'detail': 'Only submitted applications can be reviewed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate request
        serializer = HRReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data['action']
        comment = serializer.validated_data['comment']

        if action == 'approve':
            # Move to admin review
            app.status = LoanApplication.Status.UNDER_REVIEW_ADMIN
            status_msg = 'HR approved - forwarded to 254 Capital for credit assessment'
        else:  # decline
            app.status = LoanApplication.Status.DECLINED
            status_msg = 'HR declined'

        app.save()

        # Create status history
        LoanStatusHistory.objects.create(
            application=app,
            status=app.status,
            actor=request.user,
            comment=comment
        )

        # Send notification to employee
        from apps.notifications.tasks import notify_status_change
        notify_status_change.delay(str(app.id), app.status)

        # Log action
        AuditLog.log(
            action=f'HR {action}: {app.application_number}',
            actor=request.user,
            target_type='LoanApplication',
            target_id=app.id,
            metadata={'action': action, 'comment': comment},
            ip_address=get_client_ip(request)
        )

        logger.info(f'HR {action}: {app.application_number} by {request.user.id}')

        # Send email notification to employee if they have email
        if app.employee.email:
            try:
                if action == 'approve':
                    subject = 'Loan Application Update - HR Approved'
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
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="header">
                                <h1>Application Approved by HR</h1>
                            </div>
                            <div class="content">
                                <h2>Hello {app.employee.get_full_name()},</h2>
                                <p>Your loan application <strong>{app.application_number}</strong> has been approved by your HR department and forwarded to 254 Capital for credit assessment.</p>
                                <p>You will be notified once the final decision is made.</p>
                                <p>Best regards,<br>
                                <strong>254 Capital Team</strong></p>
                            </div>
                            <div class="footer">
                                <p>&copy; 2026 254 Capital. All rights reserved.</p>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                else:  # decline
                    subject = 'Loan Application Update - Decision'
                    body_html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="UTF-8">
                        <style>
                            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                            .header {{ background-color: #e74c3c; color: white; padding: 20px; text-align: center; }}
                            .content {{ padding: 20px; background-color: #f9f9f9; }}
                            .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="header">
                                <h1>Application Update</h1>
                            </div>
                            <div class="content">
                                <h2>Hello {app.employee.get_full_name()},</h2>
                                <p>We regret to inform you that your loan application <strong>{app.application_number}</strong> was not approved at this time.</p>
                                <p><strong>HR Comment:</strong> {comment}</p>
                                <p>Please contact your HR department for more information.</p>
                                <p>Best regards,<br>
                                <strong>254 Capital Team</strong></p>
                            </div>
                            <div class="footer">
                                <p>&copy; 2026 254 Capital. All rights reserved.</p>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                send_email(app.employee.email, subject, body_html)
                logger.info(f'HR review email sent to {app.employee.email}')
            except Exception as e:
                logger.error(f'Failed to send HR review email: {str(e)}')

        # Send internal alert to admin
        try:
            alert_message = f"""
            <p><strong>HR {action.title()} - Loan Application</strong></p>
            <ul>
                <li><strong>Application:</strong> {app.application_number}</li>
                <li><strong>Employee:</strong> {app.employee.get_full_name()}</li>
                <li><strong>Employer:</strong> {app.employer.name}</li>
                <li><strong>Amount:</strong> KES {app.principal_amount:,.2f}</li>
                <li><strong>Action:</strong> {action.title()}</li>
                <li><strong>HR Manager:</strong> {request.user.get_full_name()}</li>
                <li><strong>Comment:</strong> {comment}</li>
            </ul>
            """
            send_internal_alert(
                subject=f'HR {action.title()} - {app.application_number}',
                message=alert_message,
                alert_type='success' if action == 'approve' else 'warning'
            )
        except Exception as e:
            logger.error(f'Failed to send internal alert: {str(e)}')

        return Response({
            'detail': status_msg,
            'application': LoanApplicationDetailSerializer(app).data
        }, status=status.HTTP_200_OK)


class HRBatchApprovalView(APIView):
    """
    POST /api/v1/loans/hr/batch-approval/
    Batch approve or decline multiple applications.
    """

    permission_classes = [IsAuthenticated, IsHRManager]

    def post(self, request):
        """Batch approve/decline applications."""
        hr_profile = request.user.hr_profile

        serializer = BatchApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        application_ids = serializer.validated_data['application_ids']
        action = serializer.validated_data['action']
        comment = serializer.validated_data['comment']

        # Get applications
        applications = LoanApplication.objects.filter(
            id__in=application_ids,
            employer=hr_profile.employer,
            status=LoanApplication.Status.SUBMITTED
        )

        processed = []
        failed = []

        for app in applications:
            try:
                if action == 'approve':
                    app.status = LoanApplication.Status.UNDER_REVIEW_ADMIN
                else:
                    app.status = LoanApplication.Status.DECLINED

                app.save()

                # Create status history
                LoanStatusHistory.objects.create(
                    application=app,
                    status=app.status,
                    actor=request.user,
                    comment=comment
                )

                # Notify employee
                from apps.notifications.tasks import notify_status_change
                notify_status_change.delay(str(app.id), app.status)

                processed.append(str(app.id))

            except Exception as e:
                logger.error(f'Batch {action} failed for {app.id}: {e}')
                failed.append({'id': str(app.id), 'error': str(e)})

        # Log batch action
        AuditLog.log(
            action=f'Batch HR {action}: {len(processed)} applications',
            actor=request.user,
            target_type='LoanApplication',
            target_id=request.user.id,  # Use user ID as no single target
            metadata={
                'action': action,
                'processed': processed,
                'failed': failed,
                'comment': comment
            },
            ip_address=get_client_ip(request)
        )

        return Response({
            'detail': f'Batch {action} completed',
            'processed_count': len(processed),
            'failed_count': len(failed),
            'processed': processed,
            'failed': failed
        }, status=status.HTTP_200_OK)


class HRDashboardStatsView(APIView):
    """
    GET /api/v1/loans/hr/dashboard-stats/
    Get aggregated dashboard statistics for HR's employer.

    Returns:
    - Pending applications count
    - Applications approved this month
    - Active loans count
    - Monthly remittance total
    - Deduction breakdown (this month vs next month)
    - Recent remittance submissions
    """

    permission_classes = [IsAuthenticated, IsHRManager]

    def get(self, request):
        """Get HR dashboard statistics."""
        try:
            hr_profile = request.user.hr_profile
        except AttributeError:
            return Response(
                {'detail': 'HR profile not found.'},
                status=status.HTTP_403_FORBIDDEN
            )

        employer = hr_profile.employer

        # Get current date and month boundaries
        now = timezone.now()
        first_day_of_month = date(now.year, now.month, 1)

        # Calculate all loan statistics in a single aggregated query
        loan_stats = LoanApplication.objects.filter(
            employer=employer
        ).aggregate(
            pending_count=Count('id', filter=Q(status=LoanApplication.Status.SUBMITTED)),
            approved_this_month=Count(
                'id',
                filter=Q(
                    status=LoanApplication.Status.UNDER_REVIEW_ADMIN,
                    updated_at__gte=first_day_of_month
                )
            ),
            active_loans_count=Count(
                'id',
                filter=Q(status__in=[
                    LoanApplication.Status.DISBURSED,
                    LoanApplication.Status.APPROVED
                ])
            ),
            monthly_remittance=Sum(
                'monthly_deduction',
                filter=Q(status=LoanApplication.Status.DISBURSED)
            ),
            deduct_this_month_count=Count(
                'id',
                filter=Q(
                    status=LoanApplication.Status.DISBURSED,
                    disbursement_date__isnull=False,
                    disbursement_date__day__lte=15,
                    disbursement_date__month=now.month,
                    disbursement_date__year=now.year
                )
            ),
            deduct_this_month_amount=Sum(
                'monthly_deduction',
                filter=Q(
                    status=LoanApplication.Status.DISBURSED,
                    disbursement_date__isnull=False,
                    disbursement_date__day__lte=15,
                    disbursement_date__month=now.month,
                    disbursement_date__year=now.year
                )
            ),
            deduct_next_month_count=Count(
                'id',
                filter=Q(
                    status=LoanApplication.Status.DISBURSED,
                    disbursement_date__isnull=False,
                    disbursement_date__day__gt=15,
                    disbursement_date__month=now.month,
                    disbursement_date__year=now.year
                )
            ),
            deduct_next_month_amount=Sum(
                'monthly_deduction',
                filter=Q(
                    status=LoanApplication.Status.DISBURSED,
                    disbursement_date__isnull=False,
                    disbursement_date__day__gt=15,
                    disbursement_date__month=now.month,
                    disbursement_date__year=now.year
                )
            )
        )

        # Get recent remittances (from reconciliation app)
        from apps.reconciliation.models import Remittance
        recent_remittances = Remittance.objects.filter(
            employer=employer
        ).select_related('submitted_by', 'confirmed_by').order_by(
            '-period_year', '-period_month'
        )[:3]

        # Get remittance status counts
        remittance_stats = Remittance.objects.filter(
            employer=employer,
            period_year=now.year
        ).aggregate(
            pending_count=Count('id', filter=Q(status='pending')),
            confirmed_count=Count('id', filter=Q(status='confirmed'))
        )

        # Format remittance data
        remittance_submissions = []
        for remittance in recent_remittances:
            month_names = [
                'January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'
            ]
            period_display = f"{month_names[remittance.period_month - 1]} {remittance.period_year}"

            remittance_submissions.append({
                'id': str(remittance.id),
                'period_month': remittance.period_month,
                'period_year': remittance.period_year,
                'period_display': period_display,
                'total_amount': float(remittance.total_amount),
                'status': remittance.status,
                'submitted_at': remittance.submitted_at.isoformat()
            })

        # Build response
        response_data = {
            'statistics': {
                'pending_applications': loan_stats['pending_count'] or 0,
                'approved_this_month': loan_stats['approved_this_month'] or 0,
                'active_loans': loan_stats['active_loans_count'] or 0,
                'monthly_remittance': float(loan_stats['monthly_remittance'] or Decimal('0.00'))
            },
            'deduction_breakdown': {
                'this_month': {
                    'count': loan_stats['deduct_this_month_count'] or 0,
                    'total_amount': float(loan_stats['deduct_this_month_amount'] or Decimal('0.00'))
                },
                'next_month': {
                    'count': loan_stats['deduct_next_month_count'] or 0,
                    'total_amount': float(loan_stats['deduct_next_month_amount'] or Decimal('0.00'))
                }
            },
            'remittance_summary': {
                'recent_submissions': remittance_submissions,
                'pending_count': remittance_stats['pending_count'] or 0,
                'confirmed_count': remittance_stats['confirmed_count'] or 0
            }
        }

        logger.info(f'HR dashboard stats retrieved for employer {employer.name} by user {request.user.id}')

        return Response(response_data, status=status.HTTP_200_OK)


# ADMIN VIEWS

class AdminAssessmentQueueView(APIView):
    """
    GET /api/v1/loans/admin/queue/
    List all loan applications for admin with complete disbursement details.
    Includes bank details and M-Pesa information from employee profiles.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """List all applications with disbursement details."""
        # Fetch all applications with related employee profile data for disbursement info
        applications = LoanApplication.objects.select_related(
            'employee',
            'employee__employee_profile',
            'employer'
        ).order_by('-created_at')

        # Apply status filter if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            applications = applications.filter(status=status_filter)

        # Apply employer filter
        employer_id = request.query_params.get('employer')
        if employer_id:
            applications = applications.filter(employer_id=employer_id)

        # Apply search
        search = request.query_params.get('search', '').strip()
        if search:
            applications = applications.filter(
                Q(application_number__icontains=search) |
                Q(employee__first_name__icontains=search) |
                Q(employee__last_name__icontains=search) |
                Q(employer__name__icontains=search)
            )

        # Paginate
        paginator = StandardPagination()
        page = paginator.paginate_queryset(applications, request)

        serializer = LoanApplicationListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminCreditAssessmentView(APIView):
    """
    POST /api/v1/loans/admin/<uuid:pk>/assess/
    Admin credit assessment - approve or decline after review.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        """Perform credit assessment."""
        try:
            app = LoanApplication.objects.get(pk=pk)
        except LoanApplication.DoesNotExist:
            return Response(
                {'detail': 'Application not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check status - accepting all pre-approval statuses
        # This includes legacy statuses (under_review_hr, under_review_admin) and new workflow (submitted)
        valid_statuses = ['submitted', 'under_review_hr', 'under_review_admin']
        if app.status not in valid_statuses:
            return Response(
                {'detail': f'Applications with status "{app.status}" cannot be assessed. Must be in submitted, under_review_hr, or under_review_admin status.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate request
        serializer = AdminCreditAssessmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data['action']
        comment = serializer.validated_data['comment']
        credit_notes = serializer.validated_data.get('credit_score_notes', '')

        if action == 'approve':
            app.status = LoanApplication.Status.APPROVED
            status_msg = 'Credit assessment passed - approved for disbursement'
        else:
            app.status = LoanApplication.Status.DECLINED
            status_msg = 'Credit assessment failed - declined'

        app.save()

        # Create status history
        history_comment = f'{comment}\n\nCredit Notes: {credit_notes}' if credit_notes else comment
        LoanStatusHistory.objects.create(
            application=app,
            status=app.status,
            actor=request.user,
            comment=history_comment
        )

        # Notify employee
        from apps.notifications.tasks import notify_status_change
        notify_status_change.delay(str(app.id), app.status)

        # Log assessment
        AuditLog.log(
            action=f'Admin credit assessment {action}: {app.application_number}',
            actor=request.user,
            target_type='LoanApplication',
            target_id=app.id,
            metadata={'action': action, 'comment': comment, 'credit_notes': credit_notes},
            ip_address=get_client_ip(request)
        )

        logger.info(f'Admin assessment {action}: {app.application_number}')

        # Send email notification to employee if they have email
        if app.employee.email:
            try:
                if action == 'approve':
                    subject = 'Loan Application Approved - 254 Capital'
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
                                <h1>Loan Approved!</h1>
                            </div>
                            <div class="content">
                                <h2>Congratulations {app.employee.get_full_name()}!</h2>
                                <p>Your loan application <strong>{app.application_number}</strong> has been approved by 254 Capital.</p>

                                <div class="info-box">
                                    <p><strong>Loan Details:</strong></p>
                                    <ul>
                                        <li><strong>Loan Amount:</strong> KES {app.principal_amount:,.2f}</li>
                                        <li><strong>Repayment Period:</strong> {app.repayment_months} months</li>
                                        <li><strong>Monthly Deduction:</strong> KES {app.monthly_deduction:,.2f}</li>
                                        <li><strong>Total Repayment:</strong> KES {app.total_repayment:,.2f}</li>
                                    </ul>
                                </div>

                                <p>Your loan will be disbursed shortly. You will receive notification once disbursement is completed.</p>

                                <p>Best regards,<br>
                                <strong>254 Capital Team</strong></p>
                            </div>
                            <div class="footer">
                                <p>&copy; 2026 254 Capital. All rights reserved.</p>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                else:  # decline
                    subject = 'Loan Application Update - 254 Capital'
                    body_html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="UTF-8">
                        <style>
                            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                            .header {{ background-color: #e74c3c; color: white; padding: 20px; text-align: center; }}
                            .content {{ padding: 20px; background-color: #f9f9f9; }}
                            .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="header">
                                <h1>Application Decision</h1>
                            </div>
                            <div class="content">
                                <h2>Hello {app.employee.get_full_name()},</h2>
                                <p>We regret to inform you that your loan application <strong>{app.application_number}</strong> was not approved at this time.</p>
                                <p>Please contact us if you have any questions.</p>
                                <p>Best regards,<br>
                                <strong>254 Capital Team</strong></p>
                            </div>
                            <div class="footer">
                                <p>&copy; 2026 254 Capital. All rights reserved.</p>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                send_email(app.employee.email, subject, body_html, cc_address='david.muema@254-capital.com')
                logger.info(f'Admin assessment email sent to {app.employee.email}')
            except Exception as e:
                logger.error(f'Failed to send admin assessment email: {str(e)}')

        # Send internal alert
        try:
            alert_message = f"""
            <p><strong>Loan Application {action.title()} - Credit Assessment</strong></p>
            <ul>
                <li><strong>Application:</strong> {app.application_number}</li>
                <li><strong>Employee:</strong> {app.employee.get_full_name()}</li>
                <li><strong>Employer:</strong> {app.employer.name}</li>
                <li><strong>Amount:</strong> KES {app.principal_amount:,.2f}</li>
                <li><strong>Action:</strong> {action.title()}</li>
                <li><strong>Admin:</strong> {request.user.get_full_name()}</li>
                <li><strong>Comment:</strong> {comment}</li>
            </ul>
            """
            send_internal_alert(
                subject=f'Loan {action.title()} - {app.application_number}',
                message=alert_message,
                alert_type='success' if action == 'approve' else 'warning'
            )
        except Exception as e:
            logger.error(f'Failed to send internal alert: {str(e)}')

        return Response({
            'detail': status_msg,
            'application': LoanApplicationDetailSerializer(app).data
        }, status=status.HTTP_200_OK)


class AdminDisbursementView(APIView):
    """
    POST /api/v1/loans/admin/<uuid:pk>/disburse/
    Record loan disbursement.

    Auto-calculates first deduction date and generates repayment schedule.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        """Record disbursement."""
        try:
            app = LoanApplication.objects.get(pk=pk)
        except LoanApplication.DoesNotExist:
            return Response(
                {'detail': 'Application not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Refresh from database to ensure we have the latest status
        # This prevents race conditions when approval and disbursement happen sequentially
        app.refresh_from_db()

        # Check status - only approved applications can be disbursed
        if app.status != LoanApplication.Status.APPROVED:
            return Response(
                {'detail': f'Only approved applications can be disbursed. Current status: {app.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate request
        serializer = AdminDisbursementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        disbursement_date = serializer.validated_data['disbursement_date']
        # Use employee's preferred disbursement method if not provided by admin
        disbursement_method = serializer.validated_data.get('disbursement_method') or app.disbursement_method or 'mpesa'
        disbursement_reference = serializer.validated_data['disbursement_reference']

        # Calculate first deduction date
        first_deduction = calculate_first_deduction_date(disbursement_date)

        # Update application
        app.status = LoanApplication.Status.DISBURSED
        app.disbursement_date = disbursement_date
        app.first_deduction_date = first_deduction
        # Only update disbursement_method if it wasn't already set by employee
        if not app.disbursement_method:
            app.disbursement_method = disbursement_method
        app.disbursement_reference = disbursement_reference
        app.save()

        # Generate repayment schedule
        generate_repayment_schedule(app)

        # Create status history
        LoanStatusHistory.objects.create(
            application=app,
            status=app.status,
            actor=request.user,
            comment=f'Loan disbursed via {disbursement_method}. Reference: {disbursement_reference}'
        )

        # Notify employee of disbursement
        from apps.notifications.tasks import notify_disbursement
        notify_disbursement.delay(str(app.id))

        # Log disbursement
        AuditLog.log(
            action=f'Loan disbursed: {app.application_number}',
            actor=request.user,
            target_type='LoanApplication',
            target_id=app.id,
            metadata={
                'amount': str(app.principal_amount),
                'method': disbursement_method,
                'reference': disbursement_reference,
                'first_deduction': first_deduction.isoformat()
            },
            ip_address=get_client_ip(request)
        )

        logger.info(f'Loan disbursed: {app.application_number}')

        # Send email notification to employee if they have email
        if app.employee.email:
            try:
                subject = 'Loan Disbursed - 254 Capital'
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
                            <h1>Loan Disbursed!</h1>
                        </div>
                        <div class="content">
                            <h2>Hello {app.employee.get_full_name()},</h2>
                            <p>Your loan has been successfully disbursed!</p>

                            <div class="info-box">
                                <p><strong>Disbursement Details:</strong></p>
                                <ul>
                                    <li><strong>Application Number:</strong> {app.application_number}</li>
                                    <li><strong>Loan Amount:</strong> KES {app.principal_amount:,.2f}</li>
                                    <li><strong>Disbursement Date:</strong> {app.disbursement_date.strftime('%d %B %Y')}</li>
                                    <li><strong>Disbursement Method:</strong> {app.get_disbursement_method_display()}</li>
                                    <li><strong>Reference:</strong> {disbursement_reference}</li>
                                </ul>
                                <p><strong>Repayment Details:</strong></p>
                                <ul>
                                    <li><strong>Monthly Deduction:</strong> KES {app.monthly_deduction:,.2f}</li>
                                    <li><strong>First Deduction Date:</strong> {app.first_deduction_date.strftime('%d %B %Y')}</li>
                                    <li><strong>Repayment Period:</strong> {app.repayment_months} months</li>
                                    <li><strong>Total Repayment:</strong> KES {app.total_repayment:,.2f}</li>
                                </ul>
                            </div>

                            <p>Your monthly deductions will begin on {app.first_deduction_date.strftime('%d %B %Y')} through your employer's payroll.</p>

                            <p>Thank you for choosing 254 Capital!</p>

                            <p>Best regards,<br>
                            <strong>254 Capital Team</strong></p>
                        </div>
                        <div class="footer">
                            <p>&copy; 2026 254 Capital. All rights reserved.</p>
                        </div>
                    </div>
                </body>
                </html>
                """
                send_email(app.employee.email, subject, body_html, cc_address='david.muema@254-capital.com')
                logger.info(f'Disbursement email sent to {app.employee.email}')
            except Exception as e:
                logger.error(f'Failed to send disbursement email: {str(e)}')

        # Send internal alert
        try:
            alert_message = f"""
            <p><strong>Loan Disbursed Successfully</strong></p>
            <ul>
                <li><strong>Application:</strong> {app.application_number}</li>
                <li><strong>Employee:</strong> {app.employee.get_full_name()}</li>
                <li><strong>Employer:</strong> {app.employer.name}</li>
                <li><strong>Amount Disbursed:</strong> KES {app.principal_amount:,.2f}</li>
                <li><strong>Disbursement Method:</strong> {app.get_disbursement_method_display()}</li>
                <li><strong>Reference:</strong> {disbursement_reference}</li>
                <li><strong>First Deduction Date:</strong> {app.first_deduction_date.strftime('%d %B %Y')}</li>
                <li><strong>Processed by:</strong> {request.user.get_full_name()}</li>
            </ul>
            """
            send_internal_alert(
                subject=f'Loan Disbursed - {app.application_number}',
                message=alert_message,
                alert_type='success'
            )
        except Exception as e:
            logger.error(f'Failed to send internal alert: {str(e)}')

        return Response({
            'detail': 'Loan disbursed successfully',
            'application': LoanApplicationDetailSerializer(app).data
        }, status=status.HTTP_200_OK)


class AdminBulkDisbursementView(APIView):
    """
    POST /api/v1/loans/admin/bulk-disburse/
    Bulk approve and disburse multiple loans.

    Features:
    - Auto-approval of pending loans before disbursement
    - Idempotency support to prevent duplicate processing
    - Per-loan status tracking and error reporting
    - Atomic transactions for each loan
    - Comprehensive audit logging
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        """Process bulk disbursement request."""
        # 1. Validate request
        serializer = AdminBulkDisbursementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        loan_ids = [str(lid) for lid in data['loan_ids']]
        disbursement_date = data['disbursement_date']
        reference_prefix = data['reference_prefix']
        idempotency_key = data.get('idempotency_key', '').strip()
        auto_approve = data.get('auto_approve', True)

        # Generate idempotency key if not provided
        if not idempotency_key:
            import time
            import random
            import string
            random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=9))
            idempotency_key = f'bulk-{int(time.time())}-{random_suffix}'

        # 2. Check idempotency
        existing_log = IdempotencyLog.objects.filter(
            idempotency_key=idempotency_key,
            expires_at__gt=timezone.now()
        ).first()

        if existing_log:
            return Response(
                {
                    'detail': 'Request with this idempotency key was already processed',
                    'previous_response': existing_log.response_body
                },
                status=status.HTTP_409_CONFLICT
            )

        # 3. Fetch all loan applications
        loans = LoanApplication.objects.filter(
            id__in=loan_ids
        ).select_related('employee', 'employer')
        loan_map = {str(loan.id): loan for loan in loans}

        # 4. Process each loan
        results = []
        successful_count = 0
        failed_count = 0
        skipped_count = 0
        total_amount_disbursed = Decimal('0.00')

        for loan_id in loan_ids:
            loan = loan_map.get(loan_id)

            if not loan:
                results.append({
                    'loan_id': loan_id,
                    'application_number': None,
                    'status': 'failed',
                    'error_code': 'LOAN_NOT_FOUND',
                    'error_message': 'Loan application not found'
                })
                failed_count += 1
                continue

            try:
                result = self._process_single_loan(
                    loan=loan,
                    disbursement_date=disbursement_date,
                    reference_prefix=reference_prefix,
                    auto_approve=auto_approve,
                    admin=request.user,
                    request=request
                )
                results.append(result)

                if result['status'] == 'success':
                    successful_count += 1
                    total_amount_disbursed += loan.principal_amount
                elif result['status'] == 'skipped':
                    skipped_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                logger.error(f'Error processing loan {loan_id}: {str(e)}', exc_info=True)
                results.append({
                    'loan_id': loan_id,
                    'application_number': loan.application_number,
                    'status': 'failed',
                    'error_code': 'PROCESSING_ERROR',
                    'error_message': str(e)
                })
                failed_count += 1

        # 5. Build response
        response_data = {
            'processed_count': len(loan_ids),
            'successful_count': successful_count,
            'failed_count': failed_count,
            'skipped_count': skipped_count,
            'total_amount_disbursed': float(total_amount_disbursed),
            'results': results,
            'idempotency_key': idempotency_key
        }

        # 6. Store idempotency log
        request_hash = hashlib.sha256(
            json.dumps(request.data, sort_keys=True, default=str).encode()
        ).hexdigest()

        IdempotencyLog.objects.create(
            idempotency_key=idempotency_key,
            endpoint='/api/v1/loans/admin/bulk-disburse/',
            request_hash=request_hash,
            response_status=200,
            response_body=response_data,
            admin=request.user,
            expires_at=timezone.now() + timezone.timedelta(hours=24)
        )

        # 7. Log bulk operation
        AuditLog.log(
            action=f'Bulk disbursement: {successful_count} successful, {failed_count} failed, {skipped_count} skipped',
            actor=request.user,
            target_type='BulkDisbursement',
            target_id=None,
            metadata={
                'loan_ids': loan_ids,
                'successful_count': successful_count,
                'failed_count': failed_count,
                'skipped_count': skipped_count,
                'total_amount': str(total_amount_disbursed),
                'idempotency_key': idempotency_key
            },
            ip_address=get_client_ip(request)
        )

        logger.info(
            f'Bulk disbursement completed by {request.user.get_full_name()}: '
            f'{successful_count} success, {failed_count} failed, {skipped_count} skipped'
        )

        return Response(response_data, status=status.HTTP_200_OK)

    def _process_single_loan(self, loan, disbursement_date, reference_prefix,
                              auto_approve, admin, request):
        """
        Process a single loan for approval and disbursement.

        Returns a result dict with status and details.
        """
        from django.db import transaction

        # Check if already disbursed
        if loan.status == LoanApplication.Status.DISBURSED:
            return {
                'loan_id': str(loan.id),
                'application_number': loan.application_number,
                'status': 'skipped',
                'loan_status_after': loan.status,
                'error_code': 'ALREADY_DISBURSED',
                'error_message': 'Loan already disbursed'
            }

        with transaction.atomic():
            # Refresh from database with lock
            loan = LoanApplication.objects.select_for_update().get(pk=loan.pk)

            # Approve if needed
            eligible_for_approval = [
                LoanApplication.Status.SUBMITTED,
            ]

            if loan.status in eligible_for_approval and auto_approve:
                loan.status = LoanApplication.Status.APPROVED
                loan.save(update_fields=['status', 'updated_at'])

                # Create status history for approval
                LoanStatusHistory.objects.create(
                    application=loan,
                    status=loan.status,
                    actor=admin,
                    comment='Auto-approved during bulk disbursement'
                )

                logger.info(f'Auto-approved loan {loan.application_number} during bulk disbursement')

            elif loan.status != LoanApplication.Status.APPROVED:
                return {
                    'loan_id': str(loan.id),
                    'application_number': loan.application_number,
                    'status': 'failed',
                    'loan_status_after': loan.status,
                    'error_code': 'INVALID_STATUS',
                    'error_message': f'Cannot disburse loan in status: {loan.status}'
                }

            # Validate disbursement details
            validation_error = self._validate_disbursement_details(loan)
            if validation_error:
                return {
                    'loan_id': str(loan.id),
                    'application_number': loan.application_number,
                    'status': 'failed',
                    'loan_status_after': loan.status,
                    'error_code': 'MISSING_DETAILS',
                    'error_message': validation_error
                }

            # Generate disbursement reference
            disbursement_reference = f'{reference_prefix}-{loan.application_number}'

            # Get disbursement method
            disbursement_method = loan.disbursement_method or 'mpesa'

            # Calculate first deduction date
            first_deduction = calculate_first_deduction_date(disbursement_date)

            # Update loan
            loan.status = LoanApplication.Status.DISBURSED
            loan.disbursement_date = disbursement_date
            loan.first_deduction_date = first_deduction
            loan.disbursement_reference = disbursement_reference
            if not loan.disbursement_method:
                loan.disbursement_method = disbursement_method
            loan.save()

            # Generate repayment schedule
            generate_repayment_schedule(loan)

            # Create status history for disbursement
            LoanStatusHistory.objects.create(
                application=loan,
                status=loan.status,
                actor=admin,
                comment=f'Bulk disbursement via {disbursement_method}. Reference: {disbursement_reference}'
            )

            # Notify employee (async)
            try:
                from apps.notifications.tasks import notify_disbursement
                notify_disbursement.delay(str(loan.id))
            except Exception as e:
                logger.warning(f'Failed to queue disbursement notification for {loan.id}: {e}')

            # Log individual disbursement
            AuditLog.log(
                action=f'Loan disbursed (bulk): {loan.application_number}',
                actor=admin,
                target_type='LoanApplication',
                target_id=loan.id,
                metadata={
                    'amount': str(loan.principal_amount),
                    'method': disbursement_method,
                    'reference': disbursement_reference,
                    'first_deduction': first_deduction.isoformat(),
                    'bulk_operation': True
                },
                ip_address=get_client_ip(request)
            )

            # Send email notification
            if loan.employee.email:
                try:
                    subject = 'Loan Disbursed - 254 Capital'
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
                            .info-box {{ background-color: #e8f5e9; border-left: 4px solid #27ae60; padding: 15px; margin: 15px 0; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="header">
                                <h1>Loan Disbursed!</h1>
                            </div>
                            <div class="content">
                                <h2>Hello {loan.employee.get_full_name()},</h2>
                                <p>Your loan has been successfully disbursed!</p>
                                <div class="info-box">
                                    <p><strong>Disbursement Details:</strong></p>
                                    <ul>
                                        <li><strong>Application Number:</strong> {loan.application_number}</li>
                                        <li><strong>Loan Amount:</strong> KES {loan.principal_amount:,.2f}</li>
                                        <li><strong>Disbursement Date:</strong> {loan.disbursement_date.strftime('%d %B %Y')}</li>
                                        <li><strong>Reference:</strong> {disbursement_reference}</li>
                                    </ul>
                                    <p><strong>Repayment Details:</strong></p>
                                    <ul>
                                        <li><strong>Monthly Deduction:</strong> KES {loan.monthly_deduction:,.2f}</li>
                                        <li><strong>First Deduction Date:</strong> {loan.first_deduction_date.strftime('%d %B %Y')}</li>
                                        <li><strong>Repayment Period:</strong> {loan.repayment_months} months</li>
                                    </ul>
                                </div>
                                <p>Thank you for choosing 254 Capital!</p>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                    send_email(loan.employee.email, subject, body_html, cc_address='david.muema@254-capital.com')
                except Exception as e:
                    logger.error(f'Failed to send disbursement email for {loan.id}: {e}')

            return {
                'loan_id': str(loan.id),
                'application_number': loan.application_number,
                'status': 'success',
                'loan_status_after': 'disbursed',
                'disbursement_status': 'initiated',
                'disbursement_reference': disbursement_reference
            }

    def _validate_disbursement_details(self, loan):
        """
        Validate disbursement details for the loan.

        Returns error message if validation fails, None if valid.
        """
        method = loan.disbursement_method or 'mpesa'

        if method == 'bank':
            # Check bank details from employee profile
            if hasattr(loan.employee, 'employee_profile'):
                profile = loan.employee.employee_profile
                if not profile.bank_name:
                    return 'Bank name is required for bank transfer'
                if not profile.bank_account_number:
                    return 'Bank account number is required for bank transfer'
            else:
                return 'Employee profile with bank details is required'

        elif method == 'mpesa':
            # Check M-Pesa number
            phone = None
            if hasattr(loan.employee, 'employee_profile'):
                phone = loan.employee.employee_profile.mpesa_number
            if not phone:
                phone = loan.employee.phone_number
            if not phone:
                return 'M-Pesa phone number is required'

        return None


class LoanSearchView(APIView):
    """
    GET /api/v1/loans/search/?q=<search_term>
    Search loans by employee name, ID, mobile, or application number.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Search for loans."""
        query = request.query_params.get('q', '').strip()

        if not query:
            return Response({
                'error': 'Search query parameter "q" is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Search loans
        loans = LoanApplication.objects.filter(
            Q(application_number__icontains=query) |
            Q(employee__first_name__icontains=query) |
            Q(employee__last_name__icontains=query) |
            Q(employee__phone__icontains=query) |
            Q(employee__national_id__icontains=query)
        ).select_related('employee', 'employer').filter(
            status=LoanApplication.Status.DISBURSED
        )[:20]  # Limit to 20 results

        results = []
        for loan in loans:
            results.append({
                'id': str(loan.id),
                'loan_number': loan.application_number,
                'employee_name': loan.employee.get_full_name(),
                'employee_id': loan.employee.national_id,
                'employer_name': loan.employer.name,
                'employer_id': str(loan.employer.id),
                'original_amount': float(loan.principal_amount),
                'total_due': float(loan.total_repayment),
                'amount_paid': float(loan.amount_paid) if hasattr(loan, 'amount_paid') else 0.0,
                'outstanding_balance': float(loan.outstanding_balance),
                'start_date': loan.created_at.date().isoformat(),
                'disbursement_date': loan.disbursement_date.isoformat() if loan.disbursement_date else None,
                'repayment_period': loan.repayment_months,
                'monthly_deduction': float(loan.monthly_deduction),
                'interest_rate': float(loan.interest_rate),
                'status': loan.status,
            })

        return Response({
            'count': len(results),
            'results': results
        })


class RecordPaymentView(APIView):
    """
    POST /api/v1/payments/record/
    Record a manual payment for a loan.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        """Record manual payment."""
        from .serializers import RecordPaymentSerializer
        from .models import ManualPayment

        serializer = RecordPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        loan_id = serializer.validated_data['loan_id']
        payment_date = serializer.validated_data['payment_date']
        amount_received = serializer.validated_data['amount_received']
        payment_method = serializer.validated_data['payment_method']
        reference_number = serializer.validated_data.get('reference_number', '')
        notes = serializer.validated_data.get('notes', '')
        apply_discount = serializer.validated_data.get('apply_early_payment_discount', False)

        # Get loan
        try:
            loan = LoanApplication.objects.get(id=loan_id)
        except LoanApplication.DoesNotExist:
            return Response({
                'error': 'Loan not found'
            }, status=status.HTTP_404_NOT_FOUND)

        if loan.status != LoanApplication.Status.DISBURSED:
            return Response({
                'error': 'Can only record payments for disbursed loans'
            }, status=status.HTTP_400_BAD_REQUEST)

        discount_amount = Decimal('0.00')

        # Calculate early payment discount if requested
        if apply_discount:
            from datetime import datetime
            from math import ceil

            # Calculate actual months since start
            start_date = loan.disbursement_date
            days_difference = (payment_date - start_date).days
            actual_months = max(1, ceil(days_difference / 30))

            # Calculate adjusted interest
            principal = loan.principal_amount
            interest_rate = loan.interest_rate
            original_months = loan.repayment_months

            adjusted_interest = principal * interest_rate * Decimal(str(actual_months))
            original_interest = principal * interest_rate * Decimal(str(original_months))

            discount_amount = original_interest - adjusted_interest

            if discount_amount < 0:
                discount_amount = Decimal('0.00')

        # Create payment record
        payment = ManualPayment.objects.create(
            loan=loan,
            payment_date=payment_date,
            amount_received=amount_received,
            payment_method=payment_method,
            reference_number=reference_number,
            notes=notes,
            early_payment_discount_applied=apply_discount,
            discount_amount=discount_amount,
            recorded_by=request.user
        )

        # Update loan's repayment schedule
        # Mark installments as paid based on amount received
        remaining_amount = amount_received
        unpaid_schedules = RepaymentSchedule.objects.filter(
            loan=loan,
            is_paid=False
        ).order_by('installment_number')

        for schedule in unpaid_schedules:
            if remaining_amount >= schedule.amount:
                schedule.is_paid = True
                schedule.paid_date = payment_date
                schedule.save()
                remaining_amount -= schedule.amount
            else:
                break

        # Log payment
        AuditLog.log(
            action=f'Manual payment recorded: {loan.application_number}',
            actor=request.user,
            target_type='LoanApplication',
            target_id=loan.id,
            metadata={
                'amount': str(amount_received),
                'method': payment_method,
                'reference': reference_number,
                'discount': str(discount_amount) if apply_discount else '0.00'
            },
            ip_address=get_client_ip(request)
        )

        # TODO: Send SMS notification to employee

        return Response({
            'detail': 'Payment recorded successfully',
            'payment': {
                'id': str(payment.id),
                'amount_received': str(payment.amount_received),
                'discount_amount': str(payment.discount_amount),
                'payment_date': payment.payment_date.isoformat(),
                'outstanding_balance': str(loan.outstanding_balance)
            }
        }, status=status.HTTP_201_CREATED)


class CalculateDiscountView(APIView):
    """
    POST /api/v1/payments/calculate-discount/
    Calculate early payment discount for a loan.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        """Calculate early payment discount."""
        from .serializers import EarlyPaymentDiscountSerializer
        from datetime import datetime
        from math import ceil

        serializer = EarlyPaymentDiscountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        loan_id = serializer.validated_data['loan_id']
        payment_date = serializer.validated_data['payment_date']

        # Get loan
        try:
            loan = LoanApplication.objects.get(id=loan_id)
        except LoanApplication.DoesNotExist:
            return Response({
                'error': 'Loan not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Calculate actual months
        start_date = loan.disbursement_date
        days_difference = (payment_date - start_date).days
        actual_months = max(1, ceil(days_difference / 30))

        # Calculate discount
        principal = loan.principal_amount
        interest_rate = loan.interest_rate
        original_months = loan.repayment_months

        original_interest = principal * interest_rate * Decimal(str(original_months))
        adjusted_interest = principal * interest_rate * Decimal(str(actual_months))

        discount = max(Decimal('0.00'), original_interest - adjusted_interest)

        new_total_due = principal + adjusted_interest
        new_outstanding = new_total_due - loan.total_paid

        return Response({
            'loan_id': str(loan.id),
            'application_number': loan.application_number,
            'original_interest': str(original_interest),
            'adjusted_interest': str(adjusted_interest),
            'discount_amount': str(discount),
            'original_total_due': str(loan.total_repayment),
            'new_total_due': str(new_total_due),
            'amount_paid': str(loan.total_paid),
            'new_outstanding_balance': str(new_outstanding),
            'actual_months': actual_months,
            'original_months': original_months
        })
# Muasya2024