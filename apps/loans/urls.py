"""
URL routing for loan management endpoints.
"""

from django.urls import path
from . import views
from . import crud_views

app_name = 'loans'

urlpatterns = [
    # Employee endpoints
    path('applications/', views.LoanApplicationListCreateView.as_view(), name='application-list-create'),
    path('applications/<uuid:pk>/', views.LoanApplicationDetailView.as_view(), name='application-detail'),
    path('calculator/', views.LoanCalculatorView.as_view(), name='calculator'),

    # HR endpoints
    path('hr/pending/', views.HRPendingApplicationsView.as_view(), name='hr-pending'),
    path('hr/all/', views.HRAllApplicationsView.as_view(), name='hr-all'),
    path('hr/dashboard-stats/', views.HRDashboardStatsView.as_view(), name='hr-dashboard-stats'),
    path('hr/<uuid:pk>/review/', views.HRReviewApplicationView.as_view(), name='hr-review'),
    path('hr/batch-approval/', views.HRBatchApprovalView.as_view(), name='hr-batch-approval'),

    # Admin endpoints
    path('admin/queue/', views.AdminAssessmentQueueView.as_view(), name='admin-queue'),
    path('admin/<uuid:pk>/assess/', views.AdminCreditAssessmentView.as_view(), name='admin-assess'),
    path('admin/<uuid:pk>/disburse/', views.AdminDisbursementView.as_view(), name='admin-disburse'),
    path('admin/bulk-disburse/', views.AdminBulkDisbursementView.as_view(), name='admin-bulk-disburse'),

    # Payment management endpoints
    path('search/', views.LoanSearchView.as_view(), name='loan-search'),

    # Loan CRUD endpoints (Admin only)
    path('<uuid:loan_id>/', crud_views.UpdateLoanView.as_view(), name='update-loan'),
    path('<uuid:loan_id>/delete-check/', crud_views.DeleteLoanCheckView.as_view(), name='delete-check'),
    path('<uuid:loan_id>/delete/', crud_views.DeleteLoanView.as_view(), name='delete-loan'),
    path('<uuid:loan_id>/repayments/', crud_views.GetLoanRepaymentsView.as_view(), name='loan-repayments'),
    path('<uuid:loan_id>/repayments/manual/', crud_views.ManualRepaymentView.as_view(), name='manual-repayment'),

    # Repayment CRUD endpoints (Admin only)
    path('repayments/<uuid:repayment_id>/', crud_views.UpdateRepaymentView.as_view(), name='update-repayment'),
    path('repayments/<uuid:repayment_id>/delete/', crud_views.DeleteRepaymentView.as_view(), name='delete-repayment'),
]
