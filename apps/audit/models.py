"""
Audit trail models for tracking system actions.
"""

import uuid
from django.db import models


class AuditLog(models.Model):
    """
    Immutable audit log for tracking all significant actions in the system.

    This model is append-only - records are never updated or deleted.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(
        max_length=255,
        help_text='Description of the action performed'
    )
    actor = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs',
        help_text='User who performed the action'
    )
    target_type = models.CharField(
        max_length=100,
        help_text='Type of object affected (e.g., LoanApplication, User)'
    )
    target_id = models.UUIDField(
        help_text='ID of the affected object'
    )
    metadata = models.JSONField(
        default=dict,
        help_text='Additional context about the action (changes, reason, etc.)'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text='IP address of the actor'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        indexes = [
            models.Index(fields=['actor', 'created_at']),
            models.Index(fields=['target_type', 'target_id']),
            models.Index(fields=['created_at']),
        ]
        # Prevent updates and deletes
        # permissions = [
        #     ('view_auditlog', 'Can view audit logs'),
        # ]
        default_permissions = ('add', 'change', 'delete', 'view')

    def __str__(self):
        actor_name = self.actor.get_full_name() if self.actor else 'System'
        return f'{actor_name} - {self.action} - {self.created_at}'

    def save(self, *args, **kwargs):
        """
        Override save to only allow creation, not updates.
        """
        if self.pk is not None:
            raise ValueError('AuditLog records cannot be modified after creation')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Override delete to prevent deletion of audit logs.
        """
        raise ValueError('AuditLog records cannot be deleted')

    @classmethod
    def log(cls, action, actor, target_type, target_id, metadata=None, ip_address=None):
        """
        Helper method to create an audit log entry.

        Args:
            action: Description of the action
            actor: User who performed the action
            target_type: Type of object affected
            target_id: ID of the affected object
            metadata: Additional context (dict)
            ip_address: IP address of the actor

        Returns:
            Created AuditLog instance
        """
        return cls.objects.create(
            action=action,
            actor=actor,
            target_type=target_type,
            target_id=target_id,
            metadata=metadata or {},
            ip_address=ip_address
        )
