"""
URL routing for export endpoints.
"""

from django.urls import path
from . import views

app_name = 'exports'

urlpatterns = [
    path('deductions/', views.DeductionListExportView.as_view(), name='deductions-export'),
    path('repayment-pdf/<uuid:application_id>/', views.RepaymentPDFExportView.as_view(), name='repayment-pdf'),
    path('loan-application/<uuid:application_id>/pdf/',
         views.LoanApplicationExportView.as_view(export_format='pdf'), name='loan-application-pdf'),
    path('loan-application/<uuid:application_id>/excel/',
         views.LoanApplicationExportView.as_view(export_format='excel'), name='loan-application-excel'),
    # Bulk export of loan applications (admin: all employers or one; HR: own employer)
    path('loan-applications/summary/', views.LoanApplicationsExportSummaryView.as_view(),
         name='loan-applications-summary'),
    path('loan-applications/excel/',
         views.LoanApplicationsExportView.as_view(export_format='excel'), name='loan-applications-excel'),
    path('loan-applications/csv/',
         views.LoanApplicationsExportView.as_view(export_format='csv'), name='loan-applications-csv'),
    path('loan-applications/pdf/',
         views.LoanApplicationsExportView.as_view(export_format='pdf'), name='loan-applications-pdf'),
    path('reports/loan-book/', views.LoanBookReportView.as_view(), name='loan-book-report'),
    path('reports/employer-summary/', views.EmployerSummaryReportView.as_view(), name='employer-summary'),
    path('reports/collection-sheet/', views.CollectionSheetReportView.as_view(), name='collection-sheet'),
    path('reports/disbursement/', views.DisbursementReportView.as_view(), name='disbursement-report'),
    path('reports/disbursement/excel/', views.DisbursementReportExcelView.as_view(), name='disbursement-report-excel'),
]
