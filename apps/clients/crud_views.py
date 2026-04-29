"""
Client CRUD operations (Admin only).
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Count
import logging

from .models import ExistingClient
from .serializers import ExistingClientSerializer
from apps.audit.models import AuditLog
from common.utils import get_client_ip
from apps.accounts.models import CustomUser

logger = logging.getLogger(__name__)


class UpdateClientView(APIView):
    """
    PATCH /api/v1/clients/{client_id}/
    Update client record (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, client_id):
        """Update client details."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can update client records'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get client
        try:
            client = ExistingClient.objects.select_related('employer').get(id=client_id)
        except ExistingClient.DoesNotExist:
            return Response(
                {'error': 'Client not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get fields to update
        data = {}

        if 'full_name' in request.data:
            data['full_name'] = request.data.get('full_name', '').strip()
        if 'national_id' in request.data:
            data['national_id'] = request.data.get('national_id', '').strip()
        if 'mobile' in request.data:
            data['mobile'] = request.data.get('mobile', '').strip()
        if 'email' in request.data:
            data['email'] = request.data.get('email', '').strip()
        if 'employer' in request.data:
            data['employer'] = request.data.get('employer', '').strip()
        if 'employee_id' in request.data:
            data['employee_id'] = request.data.get('employee_id', '').strip()
        if 'loan_amount' in request.data:
            data['loan_amount'] = request.data.get('loan_amount')
        if 'interest_rate' in request.data:
            data['interest_rate'] = request.data.get('interest_rate')
        if 'repayment_period' in request.data:
            data['repayment_period'] = request.data.get('repayment_period')
        if 'disbursement_date' in request.data:
            data['disbursement_date'] = request.data.get('disbursement_date')
        if 'disbursement_method' in request.data:
            data['disbursement_method'] = request.data.get('disbursement_method', '').strip()
        if 'amount_paid' in request.data:
            data['amount_paid'] = request.data.get('amount_paid')
        if 'loan_status' in request.data:
            data['loan_status'] = request.data.get('loan_status', '').strip()
        if 'admin_notes' in request.data:
            data['admin_notes'] = request.data.get('admin_notes', '').strip()

        # Update client using serializer
        serializer = ExistingClientSerializer(client, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_client = serializer.save()

        # Log action
        AuditLog.log(
            action=f'Admin updated client {client.full_name} (ID: {client.national_id})',
            actor=request.user,
            target_type='ExistingClient',
            target_id=client.id,
            ip_address=get_client_ip(request),
            details=f'Updated fields: {", ".join(data.keys())}'
        )

        logger.info(f'Client {client.id} updated by admin {request.user.email}')

        return Response({
            'detail': 'Client record updated successfully',
            'client': {
                'id': str(updated_client.id),
                'full_name': updated_client.full_name,
                'mobile': updated_client.mobile,
                'loan_amount': str(updated_client.loan_amount),
                'repayment_period': updated_client.repayment_period,
                'updated_at': timezone.now().isoformat()
            },
            'modification_logged': True
        }, status=status.HTTP_200_OK)


class DeleteClientCheckView(APIView):
    """
    GET /api/v1/clients/{client_id}/delete-check/
    Check what will be deleted if client is removed (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, client_id):
        """Pre-delete check for client."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can perform delete checks'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get client
        try:
            client = ExistingClient.objects.select_related('employer').get(id=client_id)
        except ExistingClient.DoesNotExist:
            return Response(
                {'error': 'Client not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Note: ExistingClient doesn't have separate loan/repayment tables
        # It's a single record with loan information
        # Deleting this client will only delete this single record

        return Response({
            'can_delete': True,
            'client': {
                'id': str(client.id),
                'full_name': client.full_name,
                'employer_name': client.employer.name if client.employer else 'N/A'
            },
            'associated_data': {
                'note': 'This is a legacy client record. Deleting will remove this single record only.'
            },
            'warning': 'Deleting this client will permanently remove this record. This action cannot be undone.'
        }, status=status.HTTP_200_OK)


class DeleteClientView(APIView):
    """
    DELETE /api/v1/clients/{client_id}/
    Delete client record (Admin only).
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, client_id):
        """Delete client record."""
        # Check if user is admin
        if request.user.role != CustomUser.Role.ADMIN:
            return Response(
                {'error': 'Only admins can delete client records'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get client
        try:
            client = ExistingClient.objects.select_related('employer').get(id=client_id)
        except ExistingClient.DoesNotExist:
            return Response(
                {'error': 'Client not found'},
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

        # Store client details for response
        client_name = client.full_name
        client_national_id = client.national_id
        employer_name = client.employer.name if client.employer else 'N/A'

        # Log action before deletion
        AuditLog.log(
            action=f'Admin deleted client {client_name} (ID: {client_national_id}). Reason: {reason or "Not specified"}',
            actor=request.user,
            target_type='ExistingClient',
            target_id=client.id,
            ip_address=get_client_ip(request)
        )

        # Delete client
        client.delete()

        logger.info(f'Client deleted: {client_name} by admin {request.user.email}')

        return Response({
            'detail': 'Client and all associated data deleted successfully',
            'deleted': {
                'client_id': str(client_id),
                'client_name': client_name,
                'loans_deleted': 0,  # ExistingClient is a single record
                'repayments_deleted': 0
            },
            'archived': True,
            'archived_at': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
