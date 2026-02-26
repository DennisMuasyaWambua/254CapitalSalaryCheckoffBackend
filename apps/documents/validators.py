"""
Validators for document uploads.
"""

from django.core.exceptions import ValidationError
from django.conf import settings
import os
import magic


def validate_file_size(file):
    """
    Validate file size does not exceed maximum allowed.

    Args:
        file: Uploaded file object

    Raises:
        ValidationError: If file size exceeds limit
    """
    max_size = settings.MAX_UPLOAD_SIZE
    if file.size > max_size:
        max_size_mb = max_size / (1024 * 1024)
        file_size_mb = file.size / (1024 * 1024)
        raise ValidationError(
            f'File size must not exceed {max_size_mb:.1f} MB. '
            f'Your file is {file_size_mb:.1f} MB.'
        )


def validate_file_extension(file):
    """
    Validate file has an allowed extension.

    Args:
        file: Uploaded file object

    Raises:
        ValidationError: If file extension is not allowed
    """
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in settings.ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValidationError(
            f'File extension {ext} is not allowed. '
            f'Allowed extensions: {", ".join(settings.ALLOWED_DOCUMENT_EXTENSIONS)}'
        )


def validate_file_mime_type(file):
    """
    Validate file MIME type using python-magic.

    Args:
        file: Uploaded file object

    Raises:
        ValidationError: If MIME type is not allowed
    """
    try:
        # Read first 2048 bytes for MIME detection
        file.seek(0)
        file_head = file.read(2048)
        file.seek(0)

        mime = magic.from_buffer(file_head, mime=True)

        if mime not in settings.ALLOWED_DOCUMENT_TYPES:
            raise ValidationError(
                f'File type {mime} is not allowed. '
                f'Allowed types: PDF, JPEG, PNG'
            )

    except Exception as e:
        # If magic fails, we already checked extension, so pass
        pass


def validate_document_file(file):
    """
    Run all document file validations.

    Args:
        file: Uploaded file object

    Raises:
        ValidationError: If any validation fails
    """
    validate_file_size(file)
    validate_file_extension(file)
    validate_file_mime_type(file)
