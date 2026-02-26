"""
URL routing for reconciliation endpoints.
"""

from django.urls import path
from . import views

app_name = 'reconciliation'

urlpatterns = [
    # Remittances
    path('remittances/', views.RemittanceListView.as_view(), name='remittance-list'),
    path('remittances/create/', views.RemittanceCreateView.as_view(), name='remittance-create'),
    path('remittances/<uuid:pk>/', views.RemittanceDetailView.as_view(), name='remittance-detail'),
    path('remittances/<uuid:pk>/confirm/', views.RemittanceConfirmView.as_view(), name='remittance-confirm'),

    # Reconciliation
    path('reconcile/', views.RunReconciliationView.as_view(), name='reconcile-run'),
    path('records/', views.ReconciliationRecordListView.as_view(), name='record-list'),
    path('records/<uuid:pk>/', views.ReconciliationRecordUpdateView.as_view(), name='record-update'),
]
