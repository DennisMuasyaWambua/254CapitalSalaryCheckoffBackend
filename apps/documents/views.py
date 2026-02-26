"""
Document upload and management APIViews.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.conf import settings

from .models import Document
from .serializers import DocumentSerializer, DocumentUploadSerializer, DocumentListSerializer
from apps.loans.models import LoanApplication
from common.utils import get_client_ip
from apps.audit.models import AuditLog
import logging

logger = logging.getLogger(__name__)


class DocumentUploadView(APIView):
    """
    POST /api/v1/documents/upload/
    Upload document with validation (multipart/form-data).

    Validates:
    - File type (PDF, JPG, PNG)
    - File size (max 5MB)
    - MIME type

    Stores to S3 (or local in development).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Upload document."""
        serializer = DocumentUploadSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        # Create document
        document = serializer.save()

        # Log upload
        AuditLog.log(
            action=f'Document uploaded: {document.document_type}',
            actor=request.user,
            target_type='Document',
            target_id=document.id,
            metadata={
                'document_type': document.document_type,
                'filename': document.original_filename,
                'file_size': document.file_size,
                'application_id': str(document.application.id) if document.application else None,
                'employer_id': str(document.employer.id) if document.employer else None,
            },
            ip_address=get_client_ip(request)
        )

        logger.info(f'Document uploaded: {document.id} by {request.user.id}')

        return Response(
            DocumentSerializer(document, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


class DocumentDetailView(APIView):
    """
    GET     /api/v1/documents/<uuid:pk>/  — Get document metadata + download URL
    DELETE  /api/v1/documents/<uuid:pk>/  — Delete document
    """

    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        """Get document with permission check."""
        try:
            doc = Document.objects.select_related('application', 'employer', 'uploaded_by').get(pk=pk)

            # Check access based on role
            if user.role == 'employee':
                # Employee can access own application documents
                if doc.application and doc.application.employee != user:
                    return None
                # Or documents they uploaded
                if doc.uploaded_by != user:
                    return None

            elif user.role == 'hr_manager':
                # HR can access documents from their employer
                hr_profile = getattr(user, 'hr_profile', None)
                if not hr_profile:
                    return None

                # Check if document belongs to their employer
                if doc.application and doc.application.employer != hr_profile.employer:
                    return None
                if doc.employer and doc.employer != hr_profile.employer:
                    return None

            # Admin can access all
            return doc

        except Document.DoesNotExist:
            return None

    def get(self, request, pk):
        """Get document metadata and download URL."""
        doc = self.get_object(pk, request.user)

        if not doc:
            return Response(
                {'detail': 'Document not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = DocumentSerializer(doc, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        """Delete document."""
        doc = self.get_object(pk, request.user)

        if not doc:
            return Response(
                {'detail': 'Document not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Only allow deletion if:
        # 1. User is the uploader
        # 2. AND application is still in submitted status (or no application)
        if doc.uploaded_by != request.user:
            return Response(
                {'detail': 'You can only delete documents you uploaded.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if doc.application and doc.application.status != LoanApplication.Status.SUBMITTED:
            return Response(
                {'detail': 'Cannot delete documents for applications that are no longer in submitted status.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Log deletion before deleting
        AuditLog.log(
            action=f'Document deleted: {doc.document_type}',
            actor=request.user,
            target_type='Document',
            target_id=doc.id,
            metadata={
                'document_type': doc.document_type,
                'filename': doc.original_filename,
                'application_id': str(doc.application.id) if doc.application else None,
            },
            ip_address=get_client_ip(request)
        )

        # Delete document (will also delete file from storage)
        doc.delete()

        logger.info(f'Document deleted: {pk} by {request.user.id}')

        return Response(
            {'detail': 'Document deleted successfully.'},
            status=status.HTTP_204_NO_CONTENT
        )


class ApplicationDocumentsView(APIView):
    """
    GET /api/v1/documents/application/<uuid:application_id>/
    List all documents for a specific application.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, application_id):
        """List documents for application."""
        # Check application exists and user has access
        try:
            application = LoanApplication.objects.get(pk=application_id)
        except LoanApplication.DoesNotExist:
            return Response(
                {'detail': 'Application not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check access
        if request.user.role == 'employee' and application.employee != request.user:
            return Response(
                {'detail': 'You do not have access to this application.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if request.user.role == 'hr_manager':
            hr_profile = getattr(request.user, 'hr_profile', None)
            if not hr_profile or application.employer != hr_profile.employer:
                return Response(
                    {'detail': 'You do not have access to this application.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Get documents
        documents = Document.objects.filter(application=application).order_by('document_type', '-created_at')

        serializer = DocumentListSerializer(documents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
