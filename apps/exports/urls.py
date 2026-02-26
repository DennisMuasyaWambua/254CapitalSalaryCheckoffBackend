"""
URL routing for export endpoints.
"""

from django.urls import path
from . import views

app_name = 'exports'

urlpatterns = [
    path('deductions/', views.DeductionListExportView.as_view(), name='deductions-export'),
    path('repayment-pdf/<uuid:application_id>/', views.RepaymentPDFExportView.as_view(), name='repayment-pdf'),
    path('reports/loan-book/', views.LoanBookReportView.as_view(), name='loan-book-report'),
    path('reports/employer-summary/', views.EmployerSummaryReportView.as_view(), name='employer-summary'),
    path('reports/collection-sheet/', views.CollectionSheetReportView.as_view(), name='collection-sheet'),
]
