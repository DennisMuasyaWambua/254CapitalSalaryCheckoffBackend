"""
URL routing for loan management endpoints.
"""

from django.urls import path
from . import views

app_name = 'loans'

urlpatterns = [
    # Employee endpoints
    path('applications/', views.LoanApplicationListCreateView.as_view(), name='application-list-create'),
    path('applications/<uuid:pk>/', views.LoanApplicationDetailView.as_view(), name='application-detail'),
    path('calculator/', views.LoanCalculatorView.as_view(), name='calculator'),

    # HR endpoints
    path('hr/pending/', views.HRPendingApplicationsView.as_view(), name='hr-pending'),
    path('hr/all/', views.HRAllApplicationsView.as_view(), name='hr-all'),
    path('hr/<uuid:pk>/review/', views.HRReviewApplicationView.as_view(), name='hr-review'),
    path('hr/batch-approval/', views.HRBatchApprovalView.as_view(), name='hr-batch-approval'),

    # Admin endpoints
    path('admin/queue/', views.AdminAssessmentQueueView.as_view(), name='admin-queue'),
    path('admin/<uuid:pk>/assess/', views.AdminCreditAssessmentView.as_view(), name='admin-assess'),
    path('admin/<uuid:pk>/disburse/', views.AdminDisbursementView.as_view(), name='admin-disburse'),

    # Payment management endpoints
    path('search/', views.LoanSearchView.as_view(), name='loan-search'),
]
