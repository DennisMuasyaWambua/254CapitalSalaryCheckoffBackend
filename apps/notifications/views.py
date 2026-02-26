"""
Notification and messaging APIViews.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from .models import Notification, MessageThread, Message
from .serializers import (
    NotificationSerializer, UnreadCountSerializer, MessageSerializer,
    MessageThreadSerializer, MessageThreadCreateSerializer, MessageCreateSerializer
)
from apps.loans.models import LoanApplication
from common.pagination import StandardPagination
from common.utils import get_client_ip
from apps.audit.models import AuditLog
import logging

logger = logging.getLogger(__name__)


class NotificationListView(APIView):
    """
    GET /api/v1/notifications/
    List user's notifications with filtering.

    Supports:
    - ?is_read=true|false — filter by read status
    - Pagination
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List notifications."""
        notifications = Notification.objects.filter(
            user=request.user
        ).order_by('-created_at')

        # Apply read filter
        is_read = request.query_params.get('is_read')
        if is_read is not None:
            is_read_bool = is_read.lower() == 'true'
            notifications = notifications.filter(is_read=is_read_bool)

        # Paginate
        paginator = StandardPagination()
        page = paginator.paginate_queryset(notifications, request)

        serializer = NotificationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class UnreadCountView(APIView):
    """
    GET /api/v1/notifications/unread-count/
    Get count of unread notifications.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get unread count."""
        count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()

        serializer = UnreadCountSerializer({'count': count})
        return Response(serializer.data, status=status.HTTP_200_OK)


class MarkNotificationReadView(APIView):
    """
    PATCH /api/v1/notifications/<uuid:pk>/read/
    Mark single notification as read.
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        """Mark notification as read."""
        try:
            notification = Notification.objects.get(
                pk=pk,
                user=request.user
            )
        except Notification.DoesNotExist:
            return Response(
                {'detail': 'Notification not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        notification.is_read = True
        notification.save()

        return Response(
            NotificationSerializer(notification).data,
            status=status.HTTP_200_OK
        )


class MarkAllReadView(APIView):
    """
    POST /api/v1/notifications/mark-all-read/
    Mark all user's notifications as read.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Mark all notifications as read."""
        updated_count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True)

        logger.info(f'Marked {updated_count} notifications as read for user {request.user.id}')

        return Response({
            'detail': f'{updated_count} notifications marked as read.',
            'count': updated_count
        }, status=status.HTTP_200_OK)


class MessageThreadListCreateView(APIView):
    """
    GET  /api/v1/notifications/threads/  — List message threads
    POST /api/v1/notifications/threads/  — Create new thread
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List message threads for user's applications."""
        # Get threads based on user role
        if request.user.role == 'employee':
            # Employee sees threads for their applications
            threads = MessageThread.objects.filter(
                application__employee=request.user
            ).select_related('application', 'created_by').prefetch_related('messages')

        elif request.user.role == 'hr_manager':
            # HR sees threads for their employer's applications
            hr_profile = request.user.hr_profile
            threads = MessageThread.objects.filter(
                application__employer=hr_profile.employer
            ).select_related('application', 'created_by').prefetch_related('messages')

        else:  # admin
            # Admin sees all threads
            threads = MessageThread.objects.all().select_related(
                'application', 'created_by'
            ).prefetch_related('messages')

        threads = threads.order_by('-updated_at')

        # Paginate
        paginator = StandardPagination()
        page = paginator.paginate_queryset(threads, request)

        serializer = MessageThreadSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """Create new message thread."""
        serializer = MessageThreadCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        application_id = serializer.validated_data['application_id']
        subject = serializer.validated_data['subject']
        initial_message = serializer.validated_data['initial_message']

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
                {'detail': 'You can only create threads for your own applications.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if request.user.role == 'hr_manager':
            hr_profile = request.user.hr_profile
            if application.employer != hr_profile.employer:
                return Response(
                    {'detail': 'You can only create threads for applications from your employer.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Create thread
        thread = MessageThread.objects.create(
            application=application,
            subject=subject,
            created_by=request.user
        )

        # Create initial message
        Message.objects.create(
            thread=thread,
            sender=request.user,
            body=initial_message
        )

        # Log action
        AuditLog.log(
            action=f'Message thread created: {subject}',
            actor=request.user,
            target_type='MessageThread',
            target_id=thread.id,
            metadata={'application_id': str(application_id)},
            ip_address=get_client_ip(request)
        )

        logger.info(f'Message thread created: {thread.id} by {request.user.id}')

        return Response(
            MessageThreadSerializer(thread).data,
            status=status.HTTP_201_CREATED
        )


class MessageListCreateView(APIView):
    """
    GET  /api/v1/notifications/threads/<uuid:thread_id>/messages/  — List messages
    POST /api/v1/notifications/threads/<uuid:thread_id>/messages/  — Send message
    """

    permission_classes = [IsAuthenticated]

    def get_thread(self, thread_id, user):
        """Get thread with permission check."""
        try:
            thread = MessageThread.objects.select_related('application').get(pk=thread_id)

            # Check access
            if user.role == 'employee' and thread.application.employee != user:
                return None

            if user.role == 'hr_manager':
                hr_profile = user.hr_profile
                if thread.application.employer != hr_profile.employer:
                    return None

            # Admin can access all
            return thread

        except MessageThread.DoesNotExist:
            return None

    def get(self, request, thread_id):
        """List messages in thread."""
        thread = self.get_thread(thread_id, request.user)

        if not thread:
            return Response(
                {'detail': 'Thread not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        messages = thread.messages.select_related('sender').order_by('created_at')

        # Mark messages as read (messages not sent by current user)
        messages.exclude(sender=request.user).update(is_read=True)

        serializer = MessageSerializer(messages, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, thread_id):
        """Send message in thread."""
        thread = self.get_thread(thread_id, request.user)

        if not thread:
            return Response(
                {'detail': 'Thread not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create message
        message = Message.objects.create(
            thread=thread,
            sender=request.user,
            body=serializer.validated_data['body'],
            attachment=serializer.validated_data.get('attachment')
        )

        # Create notification for other participants
        # Determine recipients based on user role
        if request.user.role == 'employee':
            # Notify HR and admin
            from apps.accounts.models import CustomUser
            hr_users = CustomUser.objects.filter(
                role='hr_manager',
                hr_profile__employer=thread.application.employer
            )
            admin_users = CustomUser.objects.filter(role='admin')
            recipients = list(hr_users) + list(admin_users)
        else:
            # Notify employee
            recipients = [thread.application.employee]

        # Create notifications
        for recipient in recipients:
            if recipient != request.user:  # Don't notify sender
                Notification.objects.create(
                    user=recipient,
                    title=f'New message in {thread.subject}',
                    message=f'{request.user.get_full_name() or request.user.username} sent a message',
                    link=f'/applications/{thread.application.id}/messages/{thread.id}',
                    notification_type=Notification.NotificationType.GENERAL
                )

        logger.info(f'Message sent in thread {thread_id} by {request.user.id}')

        return Response(
            MessageSerializer(message, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )
