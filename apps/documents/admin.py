"""
Django admin configuration for documents.
"""

from django.contrib import admin
from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Admin interface for Document model."""

    list_display = [
        'document_type', 'original_filename', 'application', 'employer',
        'uploaded_by', 'file_size_mb', 'created_at'
    ]
    list_filter = ['document_type', 'mime_type', 'created_at']
    search_fields = [
        'original_filename', 'application__application_number',
        'uploaded_by__first_name', 'uploaded_by__last_name',
        'employer__name'
    ]
    readonly_fields = [
        'uploaded_by', 'original_filename', 'file_size',
        'mime_type', 'created_at', 'updated_at'
    ]
    raw_id_fields = ['application', 'employer', 'uploaded_by']
    ordering = ['-created_at']

    fieldsets = (
        ('Document Info', {
            'fields': ('document_type', 'file', 'original_filename', 'file_size', 'mime_type')
        }),
        ('Relationships', {
            'fields': ('application', 'employer', 'uploaded_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def file_size_mb(self, obj):
        """Display file size in MB."""
        return f'{obj.file_size_mb:.2f} MB'
    file_size_mb.short_description = 'File Size'
