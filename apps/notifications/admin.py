"""
Django admin configuration for notifications.
"""

from django.contrib import admin
from .models import Notification, MessageThread, Message


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin interface for Notification model."""

    list_display = ['user', 'title', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['user__first_name', 'user__last_name', 'user__phone_number', 'title', 'message']
    readonly_fields = ['created_at']
    ordering = ['-created_at']

    fieldsets = (
        ('Notification', {
            'fields': ('user', 'title', 'message', 'link', 'notification_type')
        }),
        ('Status', {
            'fields': ('is_read', 'created_at')
        }),
    )


class MessageInline(admin.TabularInline):
    """Inline display of messages."""
    model = Message
    extra = 0
    readonly_fields = ['sender', 'body', 'is_read', 'created_at']
    can_delete = False


@admin.register(MessageThread)
class MessageThreadAdmin(admin.ModelAdmin):
    """Admin interface for MessageThread model."""

    list_display = ['subject', 'application', 'created_by', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['subject', 'application__application_number', 'created_by__first_name', 'created_by__last_name']
    readonly_fields = ['created_by', 'created_at', 'updated_at']
    raw_id_fields = ['application', 'created_by']
    ordering = ['-updated_at']
    inlines = [MessageInline]

    fieldsets = (
        ('Thread Info', {
            'fields': ('application', 'subject', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Admin interface for Message model."""

    list_display = ['thread', 'sender', 'body_preview', 'is_read', 'created_at']
    list_filter = ['is_read', 'created_at']
    search_fields = ['thread__subject', 'sender__first_name', 'sender__last_name', 'body']
    readonly_fields = ['thread', 'sender', 'created_at']
    raw_id_fields = ['thread', 'sender']
    ordering = ['-created_at']

    fieldsets = (
        ('Message Info', {
            'fields': ('thread', 'sender', 'body', 'attachment')
        }),
        ('Status', {
            'fields': ('is_read', 'created_at')
        }),
    )

    def body_preview(self, obj):
        """Display truncated body."""
        max_length = 100
        if len(obj.body) > max_length:
            return f'{obj.body[:max_length]}...'
        return obj.body
    body_preview.short_description = 'Message'
