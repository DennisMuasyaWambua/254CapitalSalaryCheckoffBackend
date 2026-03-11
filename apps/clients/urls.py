"""
URL routing for client management endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'clients'

# Create router for viewsets
router = DefaultRouter()
router.register(r'', views.ExistingClientViewSet, basename='existing-clients')

urlpatterns = [
    path('', include(router.urls)),
]
