"""
URL routing for notification and messaging endpoints.
"""

from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    # Notifications
    path('', views.NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', views.UnreadCountView.as_view(), name='unread-count'),
    path('<uuid:pk>/read/', views.MarkNotificationReadView.as_view(), name='mark-read'),
    path('mark-all-read/', views.MarkAllReadView.as_view(), name='mark-all-read'),

    # Message threads
    path('threads/', views.MessageThreadListCreateView.as_view(), name='thread-list-create'),
    path('threads/<uuid:thread_id>/messages/', views.MessageListCreateView.as_view(), name='message-list-create'),
]
