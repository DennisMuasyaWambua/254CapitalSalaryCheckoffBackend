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
from django.db.models import Q
from django.utils import timezone
from decimal import Decimal

from .models import LoanApplication, LoanStatusHistory, RepaymentSchedule
from .serializers import (
    LoanApplicationListSerializer, LoanApplicationDetailSerializer,
    LoanApplicationCreateSerializer, LoanApplicationUpdateSerializer,
    LoanCalculatorSerializer, HRReviewSerializer, BatchApprovalSerializer,
    AdminCreditAssessmentSerializer, AdminDisbursementSerializer
)
from .services import (
    calculate_flat_interest, calculate_amortized, generate_application_number,
    calculate_first_deduction_date, generate_repayment_schedule
)
from apps.accounts.permissions import IsEmployee, IsHRManager, IsAdmin, IsHROrAdmin
from common.pagination import StandardPagination
from common.utils import get_client_ip
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
            purpose=serializer.validated_data.get('purpose', ''),
            total_repayment=calc['total_repayment'],
            monthly_deduction=calc['monthly_deduction'],
            status=LoanApplication.Status.SUBMITTED,
            terms_accepted=serializer.validated_data['terms_accepted'],
            terms_accepted_at=timezone.now() if serializer.validated_data['terms_accepted'] else None
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
        ).select_related('employee', 'employer').order_by('-created_at')

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
        ).select_related('employee', 'employer').order_by('-created_at')

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


# ADMIN VIEWS

class AdminAssessmentQueueView(APIView):
    """
    GET /api/v1/loans/admin/queue/
    List applications awaiting credit assessment (status=under_review_admin).
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """List applications in assessment queue."""
        applications = LoanApplication.objects.filter(
            status=LoanApplication.Status.UNDER_REVIEW_ADMIN
        ).select_related('employee', 'employer').order_by('-created_at')

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

        # Check status
        if app.status != LoanApplication.Status.UNDER_REVIEW_ADMIN:
            return Response(
                {'detail': 'Only applications under admin review can be assessed.'},
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

        # Check status
        if app.status != LoanApplication.Status.APPROVED:
            return Response(
                {'detail': 'Only approved applications can be disbursed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate request
        serializer = AdminDisbursementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        disbursement_date = serializer.validated_data['disbursement_date']
        disbursement_method = serializer.validated_data['disbursement_method']
        disbursement_reference = serializer.validated_data['disbursement_reference']

        # Calculate first deduction date
        first_deduction = calculate_first_deduction_date(disbursement_date)

        # Update application
        app.status = LoanApplication.Status.DISBURSED
        app.disbursement_date = disbursement_date
        app.first_deduction_date = first_deduction
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

        return Response({
            'detail': 'Loan disbursed successfully',
            'application': LoanApplicationDetailSerializer(app).data
        }, status=status.HTTP_200_OK)


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
                'application_number': loan.application_number,
                'employee_name': loan.employee.get_full_name(),
                'employee_mobile': loan.employee.phone,
                'employer_name': loan.employer.name,
                'principal_amount': str(loan.principal_amount),
                'total_repayment': str(loan.total_repayment),
                'outstanding_balance': str(loan.outstanding_balance),
                'disbursement_date': loan.disbursement_date.isoformat() if loan.disbursement_date else None,
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
