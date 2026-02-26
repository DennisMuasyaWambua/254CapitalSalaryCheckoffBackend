"""
Serializers for notifications and messaging.
"""

from rest_framework import serializers
from .models import Notification, MessageThread, Message


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for notifications."""

    notification_type_display = serializers.CharField(
        source='get_notification_type_display',
        read_only=True
    )

    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'message', 'link', 'is_read',
            'notification_type', 'notification_type_display',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class NotificationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating notifications (internal use)."""

    class Meta:
        model = Notification
        fields = ['user', 'title', 'message', 'link', 'notification_type']


class UnreadCountSerializer(serializers.Serializer):
    """Serializer for unread notification count."""

    count = serializers.IntegerField()


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for individual messages."""

    sender_name = serializers.SerializerMethodField()
    sender_role = serializers.CharField(source='sender.role', read_only=True)
    attachment_url = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'thread', 'sender', 'sender_name', 'sender_role',
            'body', 'attachment', 'attachment_url', 'is_read',
            'created_at'
        ]
        read_only_fields = ['id', 'sender', 'created_at']

    def get_sender_name(self, obj):
        """Get sender's name."""
        if obj.sender:
            return obj.sender.get_full_name() or obj.sender.username
        return 'Unknown'

    def get_attachment_url(self, obj):
        """Get attachment URL if present."""
        if obj.attachment:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.attachment.url)
            return obj.attachment.url
        return None


class MessageCreateSerializer(serializers.Serializer):
    """Serializer for creating a new message."""

    body = serializers.CharField(min_length=1, max_length=5000)
    attachment = serializers.FileField(required=False, allow_null=True)

    def validate_body(self, value):
        """Ensure message body is not empty."""
        if not value.strip():
            raise serializers.ValidationError('Message body cannot be empty.')
        return value.strip()

    def validate_attachment(self, value):
        """Validate attachment if provided."""
        if value:
            # Check file size (max 5 MB)
            max_size = 5 * 1024 * 1024
            if value.size > max_size:
                raise serializers.ValidationError(
                    f'Attachment size must not exceed 5 MB. '
                    f'Your file is {value.size / (1024 * 1024):.1f} MB.'
                )
        return value


class MessageThreadSerializer(serializers.ModelSerializer):
    """Serializer for message threads."""

    application_number = serializers.CharField(
        source='application.application_number',
        read_only=True
    )
    created_by_name = serializers.SerializerMethodField()
    latest_message = MessageSerializer(read_only=True)
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = MessageThread
        fields = [
            'id', 'application', 'application_number', 'subject',
            'created_by', 'created_by_name', 'latest_message',
            'message_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        """Get creator's name."""
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return 'Unknown'

    def get_message_count(self, obj):
        """Get total message count in thread."""
        return obj.messages.count()


class MessageThreadCreateSerializer(serializers.Serializer):
    """Serializer for creating a new message thread."""

    application_id = serializers.UUIDField()
    subject = serializers.CharField(min_length=5, max_length=255)
    initial_message = serializers.CharField(min_length=1, max_length=5000)

    def validate_subject(self, value):
        """Ensure subject is meaningful."""
        if not value.strip():
            raise serializers.ValidationError('Subject cannot be empty.')
        return value.strip()

    def validate_initial_message(self, value):
        """Ensure initial message is not empty."""
        if not value.strip():
            raise serializers.ValidationError('Initial message cannot be empty.')
        return value.strip()

    def validate_application_id(self, value):
        """Validate application exists."""
        from apps.loans.models import LoanApplication
        try:
            application = LoanApplication.objects.get(id=value)
            return value
        except LoanApplication.DoesNotExist:
            raise serializers.ValidationError('Invalid application ID.')
