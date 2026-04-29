"""
Loan and Repayment CRUD operations (Admin only).
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
import logging

from .models import LoanApplication, RepaymentSchedule, ManualPayment
from apps.audit.models import AuditLog
from common.utils import get_client_ip
from apps.accounts.models import CustomUser

logger = logging.getLogger(__name__)


class UpdateLoanView(APIView):
    """
    PATCH /api/v1/loans/{loan_id}/
    Update loan details (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, loan_id):
        """Update loan details."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can update loan records'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get loan
        try:
            loan = LoanApplication.objects.select_related('employee', 'employer').get(id=loan_id)
        except LoanApplication.DoesNotExist:
            return Response(
                {'error': 'Loan not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Track changed fields
        changed_fields = []

        # Update fields
        if 'principal_amount' in request.data:
            loan.principal_amount = Decimal(str(request.data['principal_amount']))
            changed_fields.append('principal_amount')

        if 'interest_rate' in request.data:
            loan.interest_rate = Decimal(str(request.data['interest_rate']))
            changed_fields.append('interest_rate')

        if 'repayment_months' in request.data:
            loan.repayment_months = int(request.data['repayment_months'])
            changed_fields.append('repayment_months')

        if 'disbursement_date' in request.data:
            loan.disbursement_date = request.data['disbursement_date']
            changed_fields.append('disbursement_date')

        if 'disbursement_method' in request.data:
            loan.disbursement_method = request.data['disbursement_method']
            changed_fields.append('disbursement_method')

        # Recalculate loan amounts if principal, rate, or months changed
        if any(field in ['principal_amount', 'interest_rate', 'repayment_months'] for field in changed_fields):
            from .services import calculate_flat_interest

            calculation = calculate_flat_interest(
                principal=loan.principal_amount,
                rate=loan.interest_rate,
                months=loan.repayment_months
            )

            loan.interest_amount = calculation['interest_amount']
            loan.total_repayment = calculation['total_repayment']
            loan.monthly_deduction = calculation['monthly_deduction']

        loan.save()

        # Log action
        AuditLog.log(
            action=f'Admin updated loan {loan.application_number}',
            actor=request.user,
            target_type='LoanApplication',
            target_id=loan.id,
            ip_address=get_client_ip(request),
            details=f'Updated fields: {", ".join(changed_fields)}'
        )

        logger.info(f'Loan {loan.id} updated by admin {request.user.email}')

        return Response({
            'detail': 'Loan updated successfully',
            'loan': {
                'id': str(loan.id),
                'principal_amount': str(loan.principal_amount),
                'interest_rate': str(loan.interest_rate),
                'repayment_months': loan.repayment_months,
                'monthly_deduction': str(loan.monthly_deduction),
                'updated_at': timezone.now().isoformat()
            },
            'repayment_schedule_updated': True,
            'modification_logged': True
        }, status=status.HTTP_200_OK)


class DeleteLoanCheckView(APIView):
    """
    GET /api/v1/loans/{loan_id}/delete-check/
    Check what will be deleted if loan is removed (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, loan_id):
        """Pre-delete check for loan."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can perform delete checks'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get loan
        try:
            loan = LoanApplication.objects.select_related('employee').get(id=loan_id)
        except LoanApplication.DoesNotExist:
            return Response(
                {'error': 'Loan not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Count repayments
        total_repayments = RepaymentSchedule.objects.filter(loan=loan).count()
        paid_repayments = RepaymentSchedule.objects.filter(loan=loan, is_paid=True).count()
        pending_repayments = total_repayments - paid_repayments

        return Response({
            'can_delete': True,
            'loan': {
                'id': str(loan.id),
                'application_number': loan.application_number,
                'employee_name': loan.employee.get_full_name() if loan.employee else 'N/A',
                'principal_amount': str(loan.principal_amount),
                'status': loan.status,
                'outstanding_balance': str(loan.outstanding_balance)
            },
            'associated_data': {
                'total_repayments': total_repayments,
                'paid_repayments': paid_repayments,
                'pending_repayments': pending_repayments
            },
            'warning': f'Deleting this loan will permanently remove {total_repayments} repayment record(s). This action cannot be undone.'
        }, status=status.HTTP_200_OK)


class DeleteLoanView(APIView):
    """
    DELETE /api/v1/loans/{loan_id}/
    Delete loan and all associated repayments (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, loan_id):
        """Delete loan record."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can delete loan records'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get loan
        try:
            loan = LoanApplication.objects.select_related('employee').get(id=loan_id)
        except LoanApplication.DoesNotExist:
            return Response(
                {'error': 'Loan not found'},
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

        # Count repayments before deletion
        repayments_count = RepaymentSchedule.objects.filter(loan=loan).count()

        # Store loan details for response
        application_number = loan.application_number

        # Log action before deletion
        AuditLog.log(
            action=f'Admin deleted loan {application_number}. Reason: {reason or "Not specified"}',
            actor=request.user,
            target_type='LoanApplication',
            target_id=loan.id,
            ip_address=get_client_ip(request)
        )

        # Delete loan (will cascade to repayments)
        loan.delete()

        logger.info(f'Loan deleted: {application_number} by admin {request.user.email}')

        return Response({
            'detail': 'Loan and all associated repayments deleted successfully',
            'deleted': {
                'loan_id': str(loan_id),
                'application_number': application_number,
                'repayments_deleted': repayments_count
            },
            'archived': True,
            'archived_at': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)


class GetLoanRepaymentsView(APIView):
    """
    GET /api/v1/loans/{loan_id}/repayments/
    Get all repayments for a loan (Admin/HR).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, loan_id):
        """Get loan repayments."""
        # Check if user is admin or HR
        if request.user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.HR_MANAGER]:
            return Response(
                {'error': 'Only admins and HR managers can view repayments'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get loan
        try:
            loan = LoanApplication.objects.select_related('employee').get(id=loan_id)
        except LoanApplication.DoesNotExist:
            return Response(
                {'error': 'Loan not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get repayments
        repayments = RepaymentSchedule.objects.filter(loan=loan).order_by('due_date')

        # Serialize repayments
        repayment_list = []
        for idx, repayment in enumerate(repayments, start=1):
            repayment_list.append({
                'id': str(repayment.id),
                'installment_number': idx,
                'due_date': repayment.due_date.isoformat() if repayment.due_date else None,
                'amount': str(repayment.amount),
                'paid': repayment.is_paid,
                'payment_date': repayment.paid_date.isoformat() if repayment.paid_date else None,
                'payment_method': repayment.payment_method if repayment.is_paid else None,
                'reference': repayment.payment_reference if repayment.is_paid else None
            })

        # Calculate summary
        total_paid = repayments.filter(is_paid=True).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

        return Response({
            'loan_id': str(loan.id),
            'loan_details': {
                'application_number': loan.application_number,
                'employee_name': loan.employee.get_full_name() if loan.employee else 'N/A',
                'total_repayment': str(loan.total_repayment),
                'monthly_deduction': str(loan.monthly_deduction)
            },
            'repayments': repayment_list,
            'summary': {
                'total_installments': repayments.count(),
                'paid_installments': repayments.filter(is_paid=True).count(),
                'pending_installments': repayments.filter(is_paid=False).count(),
                'total_paid': str(total_paid),
                'outstanding_balance': str(loan.outstanding_balance)
            }
        }, status=status.HTTP_200_OK)


class ManualRepaymentView(APIView):
    """
    POST /api/v1/loans/{loan_id}/repayments/manual/
    Manually post a repayment (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, loan_id):
        """Manually post repayment."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can post manual repayments'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get loan
        try:
            loan = LoanApplication.objects.get(id=loan_id)
        except LoanApplication.DoesNotExist:
            return Response(
                {'error': 'Loan not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get payment details
        amount = request.data.get('amount')
        payment_date = request.data.get('payment_date')
        payment_method = request.data.get('payment_method', 'manual').strip()
        reference = request.data.get('reference', '').strip()
        notes = request.data.get('notes', '').strip()

        # Validate required fields
        if not amount or not payment_date:
            return Response(
                {'error': 'Amount and payment_date are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Convert amount to Decimal
        try:
            amount_decimal = Decimal(str(amount))
        except (ValueError, TypeError):
            return Response(
                {'error': 'Invalid amount format'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get next unpaid repayment schedule
        next_unpaid = RepaymentSchedule.objects.filter(
            loan=loan,
            is_paid=False
        ).order_by('due_date').first()

        if next_unpaid:
            # Mark this repayment as paid
            next_unpaid.is_paid = True
            next_unpaid.paid_date = payment_date
            next_unpaid.payment_method = payment_method
            next_unpaid.payment_reference = reference
            next_unpaid.save()

            repayment_id = next_unpaid.id
            installment_number = RepaymentSchedule.objects.filter(loan=loan, due_date__lte=next_unpaid.due_date).count()
        else:
            # No scheduled repayment, create manual payment record
            manual_payment = ManualPayment.objects.create(
                loan=loan,
                amount=amount_decimal,
                payment_date=payment_date,
                payment_method=payment_method,
                reference_number=reference,
                notes=notes,
                recorded_by=request.user
            )
            repayment_id = manual_payment.id
            installment_number = RepaymentSchedule.objects.filter(loan=loan).count() + 1

        # Recalculate outstanding balance
        total_paid = RepaymentSchedule.objects.filter(loan=loan, is_paid=True).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        manual_paid = ManualPayment.objects.filter(loan=loan).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

        loan.outstanding_balance = loan.total_repayment - (total_paid + manual_paid)
        loan.save()

        # Log action
        AuditLog.log(
            action=f'Admin posted manual repayment for loan {loan.application_number}',
            actor=request.user,
            target_type='LoanApplication',
            target_id=loan.id,
            ip_address=get_client_ip(request),
            details=f'Amount: {amount_decimal}, Method: {payment_method}'
        )

        logger.info(f'Manual repayment posted for loan {loan.id} by admin {request.user.email}')

        return Response({
            'detail': 'Repayment posted successfully',
            'repayment': {
                'id': str(repayment_id),
                'loan_id': str(loan.id),
                'installment_number': installment_number,
                'amount': str(amount_decimal),
                'due_date': payment_date,
                'paid': True,
                'payment_date': payment_date,
                'payment_method': payment_method,
                'reference': reference,
                'created_at': timezone.now().isoformat()
            },
            'loan_updated': {
                'amount_paid': str(total_paid + manual_paid),
                'outstanding_balance': str(loan.outstanding_balance)
            }
        }, status=status.HTTP_201_CREATED)


class UpdateRepaymentView(APIView):
    """
    PATCH /api/v1/repayments/{repayment_id}/
    Update repayment record (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, repayment_id):
        """Update repayment record."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can update repayment records'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get repayment
        try:
            repayment = RepaymentSchedule.objects.select_related('loan').get(id=repayment_id)
        except RepaymentSchedule.DoesNotExist:
            return Response(
                {'error': 'Repayment not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Track changed fields
        changed_fields = []

        # Update fields
        if 'amount' in request.data:
            repayment.amount = Decimal(str(request.data['amount']))
            changed_fields.append('amount')

        if 'due_date' in request.data:
            repayment.due_date = request.data['due_date']
            changed_fields.append('due_date')

        if 'paid' in request.data:
            repayment.is_paid = bool(request.data['paid'])
            changed_fields.append('paid')

        if 'payment_date' in request.data:
            repayment.paid_date = request.data['payment_date']
            changed_fields.append('payment_date')

        if 'payment_method' in request.data:
            repayment.payment_method = request.data['payment_method']
            changed_fields.append('payment_method')

        if 'reference' in request.data:
            repayment.payment_reference = request.data['reference']
            changed_fields.append('reference')

        repayment.save()

        # Recalculate loan balance
        loan = repayment.loan
        total_paid = RepaymentSchedule.objects.filter(loan=loan, is_paid=True).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        loan.outstanding_balance = loan.total_repayment - total_paid
        loan.save()

        # Log action
        AuditLog.log(
            action=f'Admin updated repayment for loan {loan.application_number}',
            actor=request.user,
            target_type='RepaymentSchedule',
            target_id=repayment.id,
            ip_address=get_client_ip(request),
            details=f'Updated fields: {", ".join(changed_fields)}'
        )

        # Get installment number
        installment_number = RepaymentSchedule.objects.filter(
            loan=loan,
            due_date__lte=repayment.due_date
        ).count()

        return Response({
            'detail': 'Repayment record updated successfully',
            'repayment': {
                'id': str(repayment.id),
                'installment_number': installment_number,
                'amount': str(repayment.amount),
                'due_date': repayment.due_date.isoformat() if repayment.due_date else None,
                'paid': repayment.is_paid,
                'payment_date': repayment.paid_date.isoformat() if repayment.paid_date else None,
                'updated_at': timezone.now().isoformat()
            },
            'loan_balance_updated': True,
            'modification_logged': True
        }, status=status.HTTP_200_OK)


class DeleteRepaymentView(APIView):
    """
    DELETE /api/v1/repayments/{repayment_id}/
    Delete repayment record (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, repayment_id):
        """Delete repayment record."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can delete repayment records'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get repayment
        try:
            repayment = RepaymentSchedule.objects.select_related('loan').get(id=repayment_id)
        except RepaymentSchedule.DoesNotExist:
            return Response(
                {'error': 'Repayment not found'},
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

        # Store details
        loan = repayment.loan
        installment_number = RepaymentSchedule.objects.filter(
            loan=loan,
            due_date__lte=repayment.due_date
        ).count()
        amount = repayment.amount

        # Log action before deletion
        AuditLog.log(
            action=f'Admin deleted repayment for loan {loan.application_number}. Reason: {reason or "Not specified"}',
            actor=request.user,
            target_type='RepaymentSchedule',
            target_id=repayment.id,
            ip_address=get_client_ip(request)
        )

        # Delete repayment
        repayment.delete()

        # Recalculate loan balance
        total_paid = RepaymentSchedule.objects.filter(loan=loan, is_paid=True).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        loan.outstanding_balance = loan.total_repayment - total_paid
        loan.save()

        logger.info(f'Repayment deleted for loan {loan.id} by admin {request.user.email}')

        return Response({
            'detail': 'Repayment record deleted successfully',
            'deleted': {
                'repayment_id': str(repayment_id),
                'installment_number': installment_number,
                'amount': str(amount),
                'loan_id': str(loan.id)
            },
            'loan_balance_updated': True,
            'archived': True,
            'archived_at': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
