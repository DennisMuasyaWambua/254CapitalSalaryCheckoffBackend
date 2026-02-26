"""
Document upload and storage models.
"""

import uuid
import os
from django.db import models
from django.core.validators import FileExtensionValidator


def document_upload_path(instance, filename):
    """
    Generate upload path for documents.

    Format: documents/<year>/<month>/<uuid>_<original_filename>
    """
    ext = filename.split('.')[-1]
    new_filename = f'{uuid.uuid4()}.{ext}'

    from django.utils import timezone
    now = timezone.now()

    return os.path.join(
        'documents',
        str(now.year),
        str(now.month).zfill(2),
        new_filename
    )


class Document(models.Model):
    """
    Model for storing uploaded documents.

    Documents can be linked to loan applications or employers (for agreements).
    """

    class DocumentType(models.TextChoices):
        NATIONAL_ID_FRONT = 'national_id_front', 'National ID (Front)'
        NATIONAL_ID_BACK = 'national_id_back', 'National ID (Back)'
        PAYSLIP_1 = 'payslip_1', 'Payslip 1 (Most Recent)'
        PAYSLIP_2 = 'payslip_2', 'Payslip 2'
        PAYSLIP_3 = 'payslip_3', 'Payslip 3'
        CHECK_OFF_AGREEMENT = 'check_off_agreement', 'Check-Off Agreement'
        DISBURSEMENT_RECEIPT = 'disbursement_receipt', 'Disbursement Receipt'
        REMITTANCE_PROOF = 'remittance_proof', 'Remittance Proof'
        OTHER = 'other', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relationships (nullable to allow different document contexts)
    application = models.ForeignKey(
        'loans.LoanApplication',
        on_delete=models.CASCADE,
        related_name='documents',
        null=True,
        blank=True,
        help_text='Loan application this document is attached to'
    )
    employer = models.ForeignKey(
        'employers.Employer',
        on_delete=models.CASCADE,
        related_name='documents',
        null=True,
        blank=True,
        help_text='Employer this document is attached to (e.g., agreements)'
    )

    # Document details
    uploaded_by = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_documents'
    )
    document_type = models.CharField(
        max_length=30,
        choices=DocumentType.choices
    )
    file = models.FileField(
        upload_to=document_upload_path,
        validators=[
            FileExtensionValidator(
                allowed_extensions=['pdf', 'jpg', 'jpeg', 'png']
            )
        ],
        help_text='Allowed formats: PDF, JPG, PNG. Max size: 5MB'
    )
    original_filename = models.CharField(
        max_length=255,
        help_text='Original filename when uploaded'
    )
    file_size = models.IntegerField(
        help_text='File size in bytes'
    )
    mime_type = models.CharField(
        max_length=100,
        help_text='MIME type of the file'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'documents'
        ordering = ['-created_at']
        verbose_name = 'Document'
        verbose_name_plural = 'Documents'
        indexes = [
            models.Index(fields=['application']),
            models.Index(fields=['employer']),
            models.Index(fields=['document_type']),
            models.Index(fields=['uploaded_by']),
        ]

    def __str__(self):
        return f'{self.get_document_type_display()} - {self.original_filename}'

    @property
    def file_size_mb(self):
        """Get file size in MB."""
        return self.file_size / (1024 * 1024)

    @property
    def is_image(self):
        """Check if document is an image."""
        return self.mime_type.startswith('image/')

    @property
    def is_pdf(self):
        """Check if document is a PDF."""
        return self.mime_type == 'application/pdf'

    def delete(self, *args, **kwargs):
        """Override delete to also delete the file from storage."""
        if self.file:
            # Delete file from storage
            self.file.delete(save=False)
        super().delete(*args, **kwargs)
