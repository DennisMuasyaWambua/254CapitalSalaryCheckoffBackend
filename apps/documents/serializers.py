"""
Serializers for document uploads and management.
"""

from rest_framework import serializers
from django.conf import settings
from .models import Document
import magic
import os


class DocumentSerializer(serializers.ModelSerializer):
    """Serializer for document metadata."""

    document_type_display = serializers.CharField(
        source='get_document_type_display',
        read_only=True
    )
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    file_size_mb = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = Document
        fields = [
            'id', 'application', 'employer', 'uploaded_by',
            'uploaded_by_name', 'document_type', 'document_type_display',
            'file', 'file_url', 'original_filename', 'file_size',
            'file_size_mb', 'mime_type', 'created_at'
        ]
        read_only_fields = [
            'id', 'uploaded_by', 'original_filename',
            'file_size', 'mime_type', 'created_at'
        ]

    def get_uploaded_by_name(self, obj):
        """Get uploader's name."""
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.username
        return None

    def get_file_url(self, obj):
        """Get file URL (presigned if S3, direct if local)."""
        if obj.file:
            request = self.context.get('request')
            if request:
                # For local storage
                if not settings.USE_S3:
                    return request.build_absolute_uri(obj.file.url)
                else:
                    # For S3, generate presigned URL
                    try:
                        from django.core.files.storage import default_storage
                        url = default_storage.url(obj.file.name)
                        return url
                    except Exception:
                        return obj.file.url
            return obj.file.url
        return None


class DocumentUploadSerializer(serializers.Serializer):
    """Serializer for uploading documents."""

    file = serializers.FileField()
    document_type = serializers.ChoiceField(
        choices=Document.DocumentType.choices
    )
    application_id = serializers.UUIDField(required=False, allow_null=True)
    employer_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_file(self, value):
        """
        Validate file type and size.

        Allowed types: PDF, JPG, PNG
        Max size: 5 MB
        """
        # Check file size
        if value.size > settings.MAX_UPLOAD_SIZE:
            max_size_mb = settings.MAX_UPLOAD_SIZE / (1024 * 1024)
            raise serializers.ValidationError(
                f'File size must not exceed {max_size_mb:.1f} MB. '
                f'Your file is {value.size / (1024 * 1024):.1f} MB.'
            )

        # Check file extension
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in settings.ALLOWED_DOCUMENT_EXTENSIONS:
            raise serializers.ValidationError(
                f'File type not allowed. Allowed types: {", ".join(settings.ALLOWED_DOCUMENT_EXTENSIONS)}'
            )

        # Check MIME type using python-magic
        try:
            # Read first 2048 bytes for MIME detection
            value.seek(0)
            file_head = value.read(2048)
            value.seek(0)

            mime = magic.from_buffer(file_head, mime=True)

            if mime not in settings.ALLOWED_DOCUMENT_TYPES:
                raise serializers.ValidationError(
                    f'File content type not allowed. Detected type: {mime}. '
                    f'Allowed types: PDF, JPEG, PNG'
                )

        except Exception as e:
            # If python-magic fails, fall back to checking extension only
            pass

        return value

    def validate(self, attrs):
        """Ensure either application_id or employer_id is provided."""
        application_id = attrs.get('application_id')
        employer_id = attrs.get('employer_id')

        if not application_id and not employer_id:
            raise serializers.ValidationError(
                'Either application_id or employer_id must be provided.'
            )

        if application_id and employer_id:
            raise serializers.ValidationError(
                'Provide either application_id or employer_id, not both.'
            )

        # Validate application exists if provided
        if application_id:
            from apps.loans.models import LoanApplication
            try:
                application = LoanApplication.objects.get(id=application_id)
                attrs['_application'] = application
            except LoanApplication.DoesNotExist:
                raise serializers.ValidationError({'application_id': 'Invalid application ID.'})

        # Validate employer exists if provided
        if employer_id:
            from apps.employers.models import Employer
            try:
                employer = Employer.objects.get(id=employer_id)
                attrs['_employer'] = employer
            except Employer.DoesNotExist:
                raise serializers.ValidationError({'employer_id': 'Invalid employer ID.'})

        return attrs

    def create(self, validated_data):
        """Create document record."""
        file = validated_data['file']
        document_type = validated_data['document_type']
        application = validated_data.get('_application')
        employer = validated_data.get('_employer')
        uploaded_by = self.context['request'].user

        # Get MIME type
        file.seek(0)
        file_head = file.read(2048)
        file.seek(0)
        try:
            mime_type = magic.from_buffer(file_head, mime=True)
        except Exception:
            # Fallback to extension-based MIME type
            ext = os.path.splitext(file.name)[1].lower()
            mime_map = {
                '.pdf': 'application/pdf',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
            }
            mime_type = mime_map.get(ext, 'application/octet-stream')

        # Create document
        document = Document.objects.create(
            application=application,
            employer=employer,
            uploaded_by=uploaded_by,
            document_type=document_type,
            file=file,
            original_filename=file.name,
            file_size=file.size,
            mime_type=mime_type
        )

        return document


class DocumentListSerializer(serializers.ModelSerializer):
    """Minimal serializer for listing documents."""

    document_type_display = serializers.CharField(
        source='get_document_type_display',
        read_only=True
    )

    class Meta:
        model = Document
        fields = [
            'id', 'document_type', 'document_type_display',
            'original_filename', 'file_size', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
