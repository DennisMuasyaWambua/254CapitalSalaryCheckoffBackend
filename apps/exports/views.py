"""
Export APIViews for Excel and PDF generation.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from datetime import date
from decimal import Decimal

from .generators import (
    generate_deduction_list_excel,
    generate_repayment_schedule_pdf,
    generate_loan_book_report_data
)
from apps.accounts.permissions import IsHROrAdmin, IsAdmin
from apps.loans.models import LoanApplication, RepaymentSchedule
from apps.loans.services import calculate_first_deduction_date
import logging

logger = logging.getLogger(__name__)


class DeductionListExportView(APIView):
    """
    GET /api/v1/exports/deductions/
    Export deduction list as Excel.

    Query params:
    - month: Month (1-12)
    - year: Year
    - employer_id: Employer ID (optional for HR, required for admin without filter)
    """

    permission_classes = [IsAuthenticated, IsHROrAdmin]

    def get(self, request):
        """Export deduction list."""
        # Get parameters
        try:
            month = int(request.query_params.get('month'))
            year = int(request.query_params.get('year'))
        except (TypeError, ValueError):
            return Response(
                {'detail': 'Month and year are required as integers.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate month and year
        if not (1 <= month <= 12):
            return Response(
                {'detail': 'Month must be between 1 and 12.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not (2020 <= year <= 2050):
            return Response(
                {'detail': 'Invalid year.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get employer
        if request.user.role == 'hr_manager':
            employer = request.user.hr_profile.employer
        else:  # admin
            employer_id = request.query_params.get('employer_id')
            if not employer_id:
                return Response(
                    {'detail': 'Employer ID is required for admin users.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            from apps.employers.models import Employer
            try:
                employer = Employer.objects.get(id=employer_id)
            except Employer.DoesNotExist:
                return Response(
                    {'detail': 'Employer not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Get deduction date for this period
        deduction_date = date(year, month, 25)

        # Get all active loans for this employer
        active_loans = LoanApplication.objects.filter(
            employer=employer,
            status=LoanApplication.Status.DISBURSED,
            first_deduction_date__lte=deduction_date
        ).select_related('employee', 'employee__employee_profile')

        # Build deduction list
        deductions = []
        for loan in active_loans:
            # Get schedule entry for this period
            schedule = RepaymentSchedule.objects.filter(
                loan=loan,
                due_date=deduction_date
            ).first()

            if schedule and not schedule.is_paid:
                # Determine deduction tag
                # "This Month" if disbursement was before 16th of this month
                # "Next Month" if disbursement was after 15th of this month
                tag = "This Month"
                if loan.disbursement_date.year == year and loan.disbursement_date.month == month:
                    if loan.disbursement_date.day > 15:
                        tag = "Next Month"

                deductions.append({
                    'employee_name': loan.employee.get_full_name(),
                    'employee_id': loan.employee.employee_profile.employee_id,
                    'loan_number': loan.application_number,
                    'amount': schedule.amount,
                    'tag': tag,
                    'notes': ''
                })

        # Generate Excel
        excel_file = generate_deduction_list_excel(
            month=month,
            year=year,
            employer_name=employer.name,
            deductions=deductions
        )

        # Return as file download
        period_name = date(year, month, 1).strftime('%B_%Y')
        filename = f'Deduction_List_{employer.name.replace(" ", "_")}_{period_name}.xlsx'

        response = HttpResponse(
            excel_file.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        logger.info(f'Deduction list exported for {employer.name} - {period_name}')

        return response


class RepaymentPDFExportView(APIView):
    """
    GET /api/v1/exports/repayment-pdf/<uuid:application_id>/
    Generate PDF repayment schedule.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, application_id):
        """Generate repayment schedule PDF."""
        try:
            application = LoanApplication.objects.select_related(
                'employee', 'employer', 'employee__employee_profile'
            ).prefetch_related('repayment_schedule').get(id=application_id)
        except LoanApplication.DoesNotExist:
            return Response(
                {'detail': 'Application not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check access
        if request.user.role == 'employee' and application.employee != request.user:
            return Response(
                {'detail': 'Access denied.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if request.user.role == 'hr_manager':
            hr_profile = request.user.hr_profile
            if application.employer != hr_profile.employer:
                return Response(
                    {'detail': 'Access denied.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Check if loan is disbursed
        if application.status != LoanApplication.Status.DISBURSED:
            return Response(
                {'detail': 'Repayment schedule is only available for disbursed loans.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generate PDF
        pdf_file = generate_repayment_schedule_pdf(application)

        # Return as file download
        filename = f'Repayment_Schedule_{application.application_number}.pdf'

        response = HttpResponse(pdf_file.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        logger.info(f'Repayment PDF generated for {application.application_number}')

        return response


class LoanBookReportView(APIView):
    """
    GET /api/v1/exports/reports/loan-book/
    Admin loan book report (JSON for charts).

    Query params:
    - employer_id: Optional employer filter
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get loan book report data."""
        employer_id = request.query_params.get('employer_id')

        # Generate report data
        report_data = generate_loan_book_report_data(employer_id=employer_id)

        logger.info(f'Loan book report generated (employer: {employer_id or "all"})')

        return Response(report_data, status=status.HTTP_200_OK)


class EmployerSummaryReportView(APIView):
    """
    GET /api/v1/exports/reports/employer-summary/
    Per-employer summary report (JSON).

    Query params:
    - employer_id: Optional employer filter
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get employer summary report."""
        from apps.employers.models import Employer
        from django.db.models import Sum, Count, Q

        employer_id = request.query_params.get('employer_id')

        employers = Employer.objects.all()
        if employer_id:
            employers = employers.filter(id=employer_id)

        summaries = []

        for employer in employers:
            # Get loan statistics
            loans = LoanApplication.objects.filter(employer=employer)

            active_loans = loans.filter(status=LoanApplication.Status.DISBURSED)
            active_count = active_loans.count()

            total_disbursed = active_loans.aggregate(
                total=Sum('principal_amount')
            )['total'] or Decimal('0.00')

            total_outstanding = active_loans.aggregate(
                total=Sum('total_repayment')
            )['total'] or Decimal('0.00')

            # Calculate total paid
            paid_schedules = RepaymentSchedule.objects.filter(
                loan__employer=employer,
                is_paid=True
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

            # Pending applications
            pending_count = loans.filter(status=LoanApplication.Status.SUBMITTED).count()

            summaries.append({
                'employer_id': str(employer.id),
                'employer_name': employer.name,
                'active_loans_count': active_count,
                'total_disbursed': float(total_disbursed),
                'total_outstanding': float(total_outstanding),
                'total_paid': float(paid_schedules),
                'pending_applications': pending_count,
                'total_employees': employer.total_employees,
            })

        logger.info(f'Employer summary report generated for {len(summaries)} employers')

        return Response({
            'summaries': summaries,
            'total_employers': len(summaries)
        }, status=status.HTTP_200_OK)
