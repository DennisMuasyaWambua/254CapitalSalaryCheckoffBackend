"""
Notification and messaging models.
"""

import uuid
from django.db import models


class Notification(models.Model):
    """
    Model for in-app notifications.

    Notifications are sent to users for various events like status changes,
    disbursements, reminders, etc.
    """

    class NotificationType(models.TextChoices):
        OTP = 'otp', 'OTP'
        STATUS_UPDATE = 'status_update', 'Status Update'
        DISBURSEMENT = 'disbursement', 'Disbursement'
        REMITTANCE = 'remittance', 'Remittance'
        REMINDER = 'reminder', 'Reminder'
        GENERAL = 'general', 'General'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.CharField(
        max_length=500,
        blank=True,
        help_text='Optional link to related resource (e.g., /applications/123)'
    )
    is_read = models.BooleanField(default=False, db_index=True)
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.GENERAL
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.phone_number} - {self.title}'

    @classmethod
    def create_notification(cls, user, title, message, notification_type=NotificationType.GENERAL, link=''):
        """
        Helper method to create a notification.

        Args:
            user: User to send notification to
            title: Notification title
            message: Notification message
            notification_type: Type of notification
            link: Optional link to related resource

        Returns:
            Created notification instance
        """
        return cls.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
            link=link
        )


class MessageThread(models.Model):
    """
    Model for message threads linked to loan applications.

    Allows employee-HR-Admin communication about specific loan applications.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        'loans.LoanApplication',
        on_delete=models.CASCADE,
        related_name='message_threads'
    )
    subject = models.CharField(
        max_length=255,
        help_text='Thread subject'
    )
    created_by = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_threads'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'message_threads'
        ordering = ['-updated_at']
        verbose_name = 'Message Thread'
        verbose_name_plural = 'Message Threads'
        indexes = [
            models.Index(fields=['application']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.application.application_number} - {self.subject}'

    @property
    def latest_message(self):
        """Get the most recent message in this thread."""
        return self.messages.first()

    @property
    def unread_count_for_user(self, user):
        """Get count of unread messages for a specific user."""
        return self.messages.exclude(sender=user).filter(is_read=False).count()


class Message(models.Model):
    """
    Model for individual messages within a thread.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(
        MessageThread,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_messages'
    )
    body = models.TextField()
    attachment = models.FileField(
        upload_to='message_attachments/',
        null=True,
        blank=True,
        help_text='Optional file attachment'
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'messages'
        ordering = ['created_at']
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        indexes = [
            models.Index(fields=['thread', 'created_at']),
        ]

    def __str__(self):
        return f'{self.sender.get_full_name() if self.sender else "Unknown"} - {self.created_at}'

    def save(self, *args, **kwargs):
        """Override save to update thread's updated_at timestamp."""
        super().save(*args, **kwargs)
        # Update thread's updated_at
        self.thread.save(update_fields=['updated_at'])
