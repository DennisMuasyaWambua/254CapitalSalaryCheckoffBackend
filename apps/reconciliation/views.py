"""
Reconciliation and remittance APIViews.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from decimal import Decimal

from .models import Remittance, ReconciliationRecord
from .serializers import (
    RemittanceListSerializer, RemittanceDetailSerializer,
    RemittanceCreateSerializer, RemittanceConfirmSerializer,
    ReconciliationRecordSerializer, ReconciliationRunSerializer,
    ReconciliationRecordUpdateSerializer
)
from apps.accounts.permissions import IsHRManager, IsAdmin, IsHROrAdmin
from apps.loans.models import LoanApplication, RepaymentSchedule
from common.pagination import StandardPagination
from common.utils import get_client_ip
from apps.audit.models import AuditLog
import logging

logger = logging.getLogger(__name__)


class RemittanceListView(APIView):
    """
    GET /api/v1/reconciliation/remittances/
    List remittances.

    HR sees own employer, Admin sees all.
    """

    permission_classes = [IsAuthenticated, IsHROrAdmin]

    def get(self, request):
        """List remittances."""
        if request.user.role == 'hr_manager':
            # HR sees only their employer's remittances
            hr_profile = request.user.hr_profile
            remittances = Remittance.objects.filter(
                employer=hr_profile.employer
            ).select_related('employer', 'submitted_by', 'confirmed_by')
        else:
            # Admin sees all
            remittances = Remittance.objects.all().select_related(
                'employer', 'submitted_by', 'confirmed_by'
            )

        # Apply status filter
        status_filter = request.query_params.get('status')
        if status_filter:
            remittances = remittances.filter(status=status_filter)

        # Apply employer filter (admin only)
        if request.user.role == 'admin':
            employer_id = request.query_params.get('employer')
            if employer_id:
                remittances = remittances.filter(employer_id=employer_id)

        remittances = remittances.order_by('-period_year', '-period_month', '-created_at')

        # Paginate
        paginator = StandardPagination()
        page = paginator.paginate_queryset(remittances, request)

        serializer = RemittanceListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class RemittanceCreateView(APIView):
    """
    POST /api/v1/reconciliation/remittances/
    HR submits remittance confirmation.
    """

    permission_classes = [IsAuthenticated, IsHRManager]

    def post(self, request):
        """Create remittance submission."""
        serializer = RemittanceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        hr_profile = request.user.hr_profile
        employer = serializer.validated_data['_employer']

        # Check HR can only submit for their employer
        if employer != hr_profile.employer:
            return Response(
                {'detail': 'You can only submit remittances for your own employer.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Create remittance
        remittance = Remittance.objects.create(
            employer=employer,
            submitted_by=request.user,
            period_month=serializer.validated_data['period_month'],
            period_year=serializer.validated_data['period_year'],
            total_amount=serializer.validated_data['total_amount'],
            proof_document=serializer.validated_data['proof_document'],
            notes=serializer.validated_data.get('notes', ''),
            status=Remittance.Status.PENDING
        )

        # Log submission
        AuditLog.log(
            action=f'Remittance submitted: {remittance.period_display}',
            actor=request.user,
            target_type='Remittance',
            target_id=remittance.id,
            metadata={
                'employer': employer.name,
                'period': f'{remittance.period_month}/{remittance.period_year}',
                'amount': str(remittance.total_amount)
            },
            ip_address=get_client_ip(request)
        )

        logger.info(f'Remittance submitted: {remittance.id} by {request.user.id}')

        # Notify admins
        from apps.notifications.tasks import notify_remittance_submitted
        notify_remittance_submitted.delay(str(remittance.id))

        return Response(
            RemittanceDetailSerializer(remittance, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


class RemittanceDetailView(APIView):
    """
    GET /api/v1/reconciliation/remittances/<uuid:pk>/
    Get remittance details with reconciliation records.
    """

    permission_classes = [IsAuthenticated, IsHROrAdmin]

    def get_object(self, pk, user):
        """Get remittance with permission check."""
        try:
            remittance = Remittance.objects.select_related(
                'employer', 'submitted_by', 'confirmed_by'
            ).prefetch_related('reconciliation_records__loan_application').get(pk=pk)

            # HR can only view their employer's remittances
            if user.role == 'hr_manager':
                hr_profile = user.hr_profile
                if remittance.employer != hr_profile.employer:
                    return None

            return remittance

        except Remittance.DoesNotExist:
            return None

    def get(self, request, pk):
        """Get remittance detail."""
        remittance = self.get_object(pk, request.user)

        if not remittance:
            return Response(
                {'detail': 'Remittance not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = RemittanceDetailSerializer(remittance, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class RunReconciliationView(APIView):
    """
    POST /api/v1/reconciliation/reconcile/
    Run reconciliation algorithm for a remittance.

    Matches expected deductions against remitted amount.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        """Run reconciliation."""
        serializer = ReconciliationRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        remittance_id = serializer.validated_data['remittance_id']

        try:
            remittance = Remittance.objects.get(pk=remittance_id)
        except Remittance.DoesNotExist:
            return Response(
                {'detail': 'Remittance not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get all active loans for this employer for this period
        from datetime import date
        period_date = date(remittance.period_year, remittance.period_month, 25)

        # Get loans that should have deductions in this period
        active_loans = LoanApplication.objects.filter(
            employer=remittance.employer,
            status=LoanApplication.Status.DISBURSED,
            first_deduction_date__lte=period_date
        ).select_related('employee')

        # Clear existing reconciliation records
        remittance.reconciliation_records.all().delete()

        total_expected = Decimal('0.00')
        records_created = 0

        for loan in active_loans:
            # Get the schedule entry for this period
            schedule = RepaymentSchedule.objects.filter(
                loan=loan,
                due_date=period_date,
                is_paid=False
            ).first()

            if schedule:
                expected_amount = schedule.amount

                # Create reconciliation record
                ReconciliationRecord.objects.create(
                    remittance=remittance,
                    loan_application=loan,
                    expected_amount=expected_amount,
                    received_amount=Decimal('0.00'),  # Will be updated manually or automatically
                    is_matched=False,
                    notes=''
                )

                total_expected += expected_amount
                records_created += 1

        # Compare totals
        variance = remittance.total_amount - total_expected

        # Log reconciliation
        AuditLog.log(
            action=f'Reconciliation run: {remittance.period_display}',
            actor=request.user,
            target_type='Remittance',
            target_id=remittance.id,
            metadata={
                'records_created': records_created,
                'total_expected': str(total_expected),
                'total_received': str(remittance.total_amount),
                'variance': str(variance)
            },
            ip_address=get_client_ip(request)
        )

        logger.info(f'Reconciliation run: {remittance.id} - {records_created} records created')

        return Response({
            'detail': 'Reconciliation completed',
            'records_created': records_created,
            'total_expected': str(total_expected),
            'total_received': str(remittance.total_amount),
            'variance': str(variance),
            'is_matched': abs(variance) < Decimal('0.01')  # Allow 1 cent tolerance
        }, status=status.HTTP_200_OK)


class ReconciliationRecordListView(APIView):
    """
    GET /api/v1/reconciliation/records/
    List reconciliation records with filtering.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """List reconciliation records."""
        records = ReconciliationRecord.objects.select_related(
            'remittance', 'loan_application__employee', 'loan_application__employer'
        ).order_by('-remittance__period_year', '-remittance__period_month')

        # Apply filters
        employer_id = request.query_params.get('employer')
        if employer_id:
            records = records.filter(remittance__employer_id=employer_id)

        is_matched = request.query_params.get('is_matched')
        if is_matched is not None:
            is_matched_bool = is_matched.lower() == 'true'
            records = records.filter(is_matched=is_matched_bool)

        remittance_id = request.query_params.get('remittance')
        if remittance_id:
            records = records.filter(remittance_id=remittance_id)

        # Paginate
        paginator = StandardPagination()
        page = paginator.paginate_queryset(records, request)

        serializer = ReconciliationRecordSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class ReconciliationRecordUpdateView(APIView):
    """
    PATCH /api/v1/reconciliation/records/<uuid:pk>/
    Update reconciliation record (Admin only).
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def patch(self, request, pk):
        """Update reconciliation record."""
        try:
            record = ReconciliationRecord.objects.get(pk=pk)
        except ReconciliationRecord.DoesNotExist:
            return Response(
                {'detail': 'Record not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ReconciliationRecordUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Update record
        record.received_amount = serializer.validated_data['received_amount']
        record.is_matched = serializer.validated_data['is_matched']
        record.notes = serializer.validated_data.get('notes', record.notes)
        record.save()

        # If matched, mark schedule as paid
        if record.is_matched:
            from datetime import date
            period_date = date(
                record.remittance.period_year,
                record.remittance.period_month,
                25
            )

            RepaymentSchedule.objects.filter(
                loan=record.loan_application,
                due_date=period_date
            ).update(is_paid=True, paid_date=timezone.now().date())

        # Log update
        AuditLog.log(
            action=f'Reconciliation record updated',
            actor=request.user,
            target_type='ReconciliationRecord',
            target_id=record.id,
            metadata={
                'loan': record.loan_application.application_number,
                'is_matched': record.is_matched,
                'received_amount': str(record.received_amount)
            },
            ip_address=get_client_ip(request)
        )

        return Response(
            ReconciliationRecordSerializer(record).data,
            status=status.HTTP_200_OK
        )


class RemittanceConfirmView(APIView):
    """
    POST /api/v1/reconciliation/remittances/<uuid:pk>/confirm/
    Admin confirms or disputes a remittance.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        """Confirm or dispute remittance."""
        try:
            remittance = Remittance.objects.get(pk=pk)
        except Remittance.DoesNotExist:
            return Response(
                {'detail': 'Remittance not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = RemittanceConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        remittance.status = serializer.validated_data['status']
        remittance.notes = serializer.validated_data.get('notes', remittance.notes)
        remittance.confirmed_by = request.user
        remittance.confirmed_at = timezone.now()
        remittance.save()

        # Log confirmation
        AuditLog.log(
            action=f'Remittance {remittance.status}: {remittance.period_display}',
            actor=request.user,
            target_type='Remittance',
            target_id=remittance.id,
            metadata={
                'status': remittance.status,
                'notes': remittance.notes
            },
            ip_address=get_client_ip(request)
        )

        # Notify HR
        from apps.notifications.tasks import notify_remittance_confirmed
        notify_remittance_confirmed.delay(str(remittance.id))

        return Response(
            RemittanceDetailSerializer(remittance, context={'request': request}).data,
            status=status.HTTP_200_OK
        )
