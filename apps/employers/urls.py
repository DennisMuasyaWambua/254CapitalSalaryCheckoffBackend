"""
URL routing for employer endpoints.
"""

from django.urls import path
from . import views

app_name = 'employers'

urlpatterns = [
    path('', views.EmployerListView.as_view(), name='employer-list'),
    path('create/', views.EmployerCreateView.as_view(), name='employer-create'),
    path('<uuid:pk>/', views.EmployerDetailView.as_view(), name='employer-detail'),
]
