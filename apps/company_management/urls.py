"""
URL routing for Company Management API.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OrganizationViewSet, RoleViewSet, OrganizationUserViewSet,
    ChangePasswordView, AuditLogViewSet
)

app_name = 'company_management'

# Create router and register viewsets
router = DefaultRouter()
router.register(r'organizations', OrganizationViewSet, basename='organization')
router.register(r'roles', RoleViewSet, basename='role')
router.register(r'organization-users', OrganizationUserViewSet, basename='organization-user')
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
    path('change-password/', ChangePasswordView.as_view({'post': 'change_password'}), name='change-password'),
]
