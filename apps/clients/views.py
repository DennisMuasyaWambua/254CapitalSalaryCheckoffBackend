"""
Views for client management endpoints.
"""

from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.shortcuts import get_object_or_404
import pandas as pd
from io import BytesIO
from openpyxl import Workbook

from .models import ExistingClient
from .serializers import (
    ExistingClientSerializer,
    ExistingClientBulkUploadSerializer,
    ExistingClientApprovalSerializer,
    BulkApprovalSerializer,
)


class ExistingClientViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing existing client records.

    Provides endpoints for:
    - Creating manual client entries
    - Bulk upload from Excel/CSV
    - Listing and filtering clients
    - Approving/rejecting clients
    """

    queryset = ExistingClient.objects.select_related('employer').all()
    serializer_class = ExistingClientSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['approval_status', 'loan_status', 'employer']
    search_fields = ['full_name', 'national_id', 'mobile', 'employee_id']
    ordering_fields = ['created_at', 'full_name', 'outstanding_balance']

    def get_queryset(self):
        """Filter queryset based on user role."""
        queryset = super().get_queryset()

        # Admins see all clients
        if self.request.user.role == 'admin':
            return queryset

        # HR users see only their employer's clients
        if self.request.user.role == 'hr':
            return queryset.filter(employer=self.request.user.employer)

        # Employees should not access this endpoint
        return queryset.none()

    @action(detail=False, methods=['post'])
    def manual(self, request):
        """
        Create a manual existing client entry.

        POST /api/v1/clients/manual/
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Set entered_by to current user's name
        client = serializer.save(entered_by=request.user.get_full_name())

        return Response({
            'detail': 'Client record created successfully',
            'client': ExistingClientSerializer(client).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def bulk_upload(self, request):
        """
        Bulk upload client records from Excel/CSV file.

        POST /api/v1/clients/bulk-upload/
        """
        upload_serializer = ExistingClientBulkUploadSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)

        file = request.FILES['file']

        try:
            # Read file into pandas DataFrame
            if file.name.endswith('.xlsx') or file.name.endswith('.xls'):
                df = pd.read_excel(file)
            elif file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                return Response({
                    'error': 'Invalid file format'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Process and validate rows
            valid_clients = []
            errors = []

            for index, row in df.iterrows():
                try:
                    # Map DataFrame columns to model fields
                    client_data = {
                        'full_name': row.get('Full Name') or row.get('full_name'),
                        'national_id': str(row.get('National ID') or row.get('national_id')),
                        'mobile': str(row.get('Mobile') or row.get('mobile')),
                        'email': row.get('Email') or row.get('email', ''),
                        'employer_id': row.get('Employer ID') or row.get('employer_id'),
                        'employee_id': row.get('Employee ID') or row.get('employee_id', ''),
                        'loan_amount': float(row.get('Loan Amount') or row.get('loan_amount')),
                        'interest_rate': float(row.get('Interest Rate') or row.get('interest_rate')),
                        'start_date': pd.to_datetime(row.get('Start Date') or row.get('start_date')).date(),
                        'repayment_period': int(row.get('Repayment Period') or row.get('repayment_period')),
                        'disbursement_date': pd.to_datetime(row.get('Disbursement Date') or row.get('disbursement_date')).date(),
                        'disbursement_method': (row.get('Disbursement Method') or row.get('disbursement_method', 'mpesa')).lower(),
                        'amount_paid': float(row.get('Amount Paid') or row.get('amount_paid', 0)),
                        'loan_status': row.get('Loan Status') or row.get('loan_status', 'Active'),
                    }

                    # Validate and create client
                    serializer = ExistingClientSerializer(data=client_data)
                    serializer.is_valid(raise_exception=True)
                    client = serializer.save(entered_by=request.user.get_full_name())
                    valid_clients.append(str(client.id))

                except Exception as e:
                    errors.append({
                        'row': index + 2,  # +2 because index starts at 0 and we have header row
                        'error': str(e)
                    })

            return Response({
                'message': 'Bulk upload processed',
                'total_rows': len(df),
                'successful': len(valid_clients),
                'failed': len(errors),
                'valid_client_ids': valid_clients,
                'errors': errors[:50]  # Limit errors to first 50
            }, status=status.HTTP_201_CREATED if valid_clients else status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({
                'error': f'Failed to process file: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def validate_upload(self, request):
        """
        Validate bulk upload file without importing.

        POST /api/v1/clients/validate/
        """
        upload_serializer = ExistingClientBulkUploadSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)

        file = request.FILES['file']

        try:
            # Read file
            if file.name.endswith('.xlsx') or file.name.endswith('.xls'):
                df = pd.read_excel(file)
            elif file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                return Response({
                    'error': 'Invalid file format'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Validate rows
            validation_results = []

            for index, row in df.iterrows():
                result = {
                    'row': index + 2,
                    'status': 'valid',
                    'errors': []
                }

                try:
                    client_data = {
                        'full_name': row.get('Full Name') or row.get('full_name'),
                        'national_id': str(row.get('National ID') or row.get('national_id')),
                        'mobile': str(row.get('Mobile') or row.get('mobile')),
                        'email': row.get('Email') or row.get('email', ''),
                        'employer_id': row.get('Employer ID') or row.get('employer_id'),
                        'employee_id': row.get('Employee ID') or row.get('employee_id', ''),
                        'loan_amount': float(row.get('Loan Amount') or row.get('loan_amount')),
                        'interest_rate': float(row.get('Interest Rate') or row.get('interest_rate')),
                        'start_date': pd.to_datetime(row.get('Start Date') or row.get('start_date')).date(),
                        'repayment_period': int(row.get('Repayment Period') or row.get('repayment_period')),
                        'disbursement_date': pd.to_datetime(row.get('Disbursement Date') or row.get('disbursement_date')).date(),
                        'disbursement_method': (row.get('Disbursement Method') or row.get('disbursement_method', 'mpesa')).lower(),
                    }

                    serializer = ExistingClientSerializer(data=client_data)
                    if not serializer.is_valid():
                        result['status'] = 'invalid'
                        result['errors'] = serializer.errors

                except Exception as e:
                    result['status'] = 'invalid'
                    result['errors'] = [str(e)]

                validation_results.append(result)

            valid_count = sum(1 for r in validation_results if r['status'] == 'valid')
            invalid_count = len(validation_results) - valid_count

            return Response({
                'total_rows': len(df),
                'valid_rows': valid_count,
                'invalid_rows': invalid_count,
                'validation_results': validation_results[:100]  # Limit to first 100
            })

        except Exception as e:
            return Response({
                'error': f'Failed to validate file: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def upload_template(self, request):
        """
        Generate and return Excel template file.

        GET /api/v1/clients/upload-template/
        """
        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Client Upload Template"

        # Define headers
        headers = [
            'Full Name',
            'National ID',
            'Mobile',
            'Email',
            'Employer ID',
            'Employee ID',
            'Loan Amount',
            'Interest Rate',
            'Start Date',
            'Repayment Period',
            'Disbursement Date',
            'Disbursement Method',
            'Amount Paid',
            'Loan Status'
        ]

        # Write headers
        for col, header in enumerate(headers, start=1):
            ws.cell(row=1, column=col, value=header)

        # Add sample data
        sample_data = [
            'John Kamau',
            '12345678',
            '0712345678',
            'john@example.com',
            '[Employer UUID]',
            'EMP-1234',
            100000,
            5,
            '2025-01-01',
            6,
            '2025-01-05',
            'mpesa',
            0,
            'Active'
        ]

        for col, value in enumerate(sample_data, start=1):
            ws.cell(row=2, column=col, value=value)

        # Save to BytesIO
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        from django.http import HttpResponse
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=client_upload_template.xlsx'

        return response

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """
        List all pending client approvals.

        GET /api/v1/clients/pending/
        """
        pending_clients = self.get_queryset().filter(approval_status='pending')
        page = self.paginate_queryset(pending_clients)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(pending_clients, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """
        Approve a client record.

        POST /api/v1/clients/{id}/approve/
        """
        client = self.get_object()

        if client.approval_status != 'pending':
            return Response({
                'error': 'Client is not in pending status'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Update approval status
        client.approval_status = 'approved'
        client.save()

        # TODO: Create employee account if needed
        # TODO: Send SMS notification

        return Response({
            'detail': 'Client approved successfully',
            'client': ExistingClientSerializer(client).data
        })

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """
        Reject a client record.

        POST /api/v1/clients/{id}/reject/
        """
        client = self.get_object()

        if client.approval_status != 'pending':
            return Response({
                'error': 'Client is not in pending status'
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = ExistingClientApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Update approval status and rejection reason
        client.approval_status = 'rejected'
        client.rejection_reason = serializer.validated_data.get('rejection_reason', '')
        client.save()

        return Response({
            'detail': 'Client rejected successfully',
            'client': ExistingClientSerializer(client).data
        })

    @action(detail=False, methods=['post'])
    def bulk_approve(self, request):
        """
        Approve multiple client records.

        POST /api/v1/clients/bulk-approve/
        """
        serializer = BulkApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_ids = serializer.validated_data['client_ids']

        # Get all pending clients
        clients = ExistingClient.objects.filter(
            id__in=client_ids,
            approval_status='pending'
        )

        # Update all to approved
        updated_count = clients.update(approval_status='approved')

        # TODO: Create employee accounts for approved clients
        # TODO: Send SMS notifications

        return Response({
            'detail': f'{updated_count} client(s) approved successfully',
            'approved_count': updated_count
        })
