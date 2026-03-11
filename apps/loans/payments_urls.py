"""
URL routing for payment management endpoints.
"""

from django.urls import path
from apps.loans import views

app_name = 'payments'

urlpatterns = [
    path('record/', views.RecordPaymentView.as_view(), name='record-payment'),
    path('calculate-discount/', views.CalculateDiscountView.as_view(), name='calculate-discount'),
]
