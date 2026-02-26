"""
URL routing for document endpoints.
"""

from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    path('upload/', views.DocumentUploadView.as_view(), name='document-upload'),
    path('<uuid:pk>/', views.DocumentDetailView.as_view(), name='document-detail'),
    path('application/<uuid:application_id>/', views.ApplicationDocumentsView.as_view(), name='application-documents'),
]
