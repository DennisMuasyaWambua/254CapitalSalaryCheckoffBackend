"""
URL routing for client management endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import crud_views

app_name = 'clients'

# Create router for viewsets
router = DefaultRouter()
router.register(r'', views.ExistingClientViewSet, basename='existing-clients')

urlpatterns = [
    # Standalone endpoints (MUST be before router.urls to avoid 405 errors)
    path('template-download/', views.download_client_template, name='template-download'),
    path('validate/', views.validate_bulk_upload, name='validate-bulk'),
    path('bulk-upload/', views.bulk_upload_clients, name='bulk-upload'),
    path('collection-report/', views.generate_collection_report, name='collection-report'),
    path('collection-report-data/', views.get_collection_report_data, name='collection-report-data'),

    # Client CRUD endpoints (Admin only)
    path('<uuid:client_id>/', crud_views.UpdateClientView.as_view(), name='update-client'),
    path('<uuid:client_id>/delete-check/', crud_views.DeleteClientCheckView.as_view(), name='delete-check'),
    path('<uuid:client_id>/delete/', crud_views.DeleteClientView.as_view(), name='delete-client'),

    # Viewset routes
    path('', include(router.urls)),
]
