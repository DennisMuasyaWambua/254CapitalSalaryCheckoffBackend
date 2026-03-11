"""
URL configuration for 254 Capital Salary Check-Off Loan Management System.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # Django Admin
    path('admin/', admin.site.urls),

    # API v1 endpoints
    path('api/v1/auth/', include('apps.accounts.urls')),
    path('api/v1/employers/', include('apps.employers.urls')),
    path('api/v1/loans/', include('apps.loans.urls')),
    path('api/v1/documents/', include('apps.documents.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
    path('api/v1/reconciliation/', include('apps.reconciliation.urls')),
    path('api/v1/exports/', include('apps.exports.urls')),
    path('api/v1/clients/', include('apps.clients.urls')),
    path('api/v1/payments/', include('apps.loans.payments_urls')),

    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Admin site customization
admin.site.site_header = '254 Capital Administration'
admin.site.site_title = '254 Capital Admin Portal'
admin.site.index_title = 'Welcome to 254 Capital Administration'
