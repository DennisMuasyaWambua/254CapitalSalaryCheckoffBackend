"""
Tests for the admin loan application export (PDF / Excel with T&C).
"""

import io
import datetime
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.accounts.models import CustomUser, EmployeeProfile, HRProfile
from apps.audit.models import AuditLog
from apps.employers.models import Employer
from apps.loans.models import LoanApplication, LoanStatusHistory
from apps.loans.services import generate_repayment_schedule
from apps.loans.terms import TERMS_VERSIONS

TERMS = TERMS_VERSIONS['2026-01']


class LoanApplicationExportTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.employer = Employer.objects.create(
            name='Acme Ltd', registration_number='REG-1', address='Nairobi',
            hr_contact_name='HR', hr_contact_email='hr@acme.test', hr_contact_phone='0712000000',
        )
        cls.employee = CustomUser.objects.create_user(
            username='+254712345678', phone_number='0712345678', password='x', role='employee',
            first_name='Jane', last_name='Doe', national_id='12345678',
        )
        EmployeeProfile.objects.create(
            user=cls.employee, employer=cls.employer, employee_id='E1', department='Finance',
            monthly_gross_salary=Decimal('150000'), bank_name='KCB', bank_account_number='999',
        )
        cls.admin = CustomUser.objects.create_user(
            username='admin1', phone_number='0711111111', password='x', role='admin',
            first_name='Ada', last_name='Admin',
        )
        cls.hr = CustomUser.objects.create_user(
            username='hr1', phone_number='0722222222', password='x', role='hr_manager',
        )
        HRProfile.objects.create(user=cls.hr, employer=cls.employer)

        cls.accepted_at = timezone.make_aware(datetime.datetime(2026, 10, 1, 9, 30))
        cls.loan = LoanApplication.objects.create(
            application_number='254L00000001', employee=cls.employee, employer=cls.employer,
            principal_amount=Decimal('50000'), repayment_months=6, interest_rate=Decimal('0.05'),
            interest_method='reducing_balance', total_repayment=Decimal('59110.52'),
            monthly_deduction=Decimal('9851.75'), disbursement_method='bank',
            bank_name='Equity', bank_branch='CBD', account_number='0011223344',
            terms_accepted=True, terms_accepted_at=cls.accepted_at, terms_version='2026-01',
        )
        LoanStatusHistory.objects.create(
            application=cls.loan, status='submitted', actor=cls.employee, comment='Application submitted',
        )
        AuditLog.log(
            action=f'Loan application submitted: {cls.loan.application_number}', actor=cls.employee,
            target_type='LoanApplication', target_id=cls.loan.id, ip_address='41.90.1.2',
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def url(self, fmt, loan=None):
        return f'/api/v1/exports/loan-application/{(loan or self.loan).id}/{fmt}/'

    def test_pdf_download(self):
        response = self.client.get(self.url('pdf'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(
            response['Content-Disposition'], 'attachment; filename="Loan_Application_254L00000001.pdf"'
        )
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertTrue(AuditLog.objects.filter(
            action='Loan application exported (pdf): 254L00000001', actor=self.admin,
        ).exists())

    def test_pdf_contains_details_and_full_terms(self):
        with mock.patch('weasyprint.HTML') as html:
            html.return_value.write_pdf.return_value = b'%PDF-stub'
            self.client.get(self.url('pdf'))
        rendered = html.call_args.kwargs['string']

        for expected in ('Jane Doe', '12345678', 'Acme Ltd', 'KES 50,000.00', '5.00% per month',
                         'Equity', '0011223344', '41.90.1.2', '01 Oct 2026, 09:30:00 EAT',
                         'Application submitted'):
            self.assertIn(expected, rendered)
        for section in TERMS['sections']:
            self.assertIn(section['heading'].replace('&', '&amp;'), rendered)
        self.assertIn(TERMS['acceptance_statement'], rendered)

    def test_excel_download_has_terms_sheet(self):
        response = self.client.get(self.url('excel'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Disposition'], 'attachment; filename="Loan_Application_254L00000001.xlsx"'
        )
        wb = load_workbook(io.BytesIO(response.content))
        self.assertEqual(wb.sheetnames, ['Application', 'Terms & Conditions', 'Status History', 'Documents'])

        application = {row[0]: row[1] for row in wb['Application'].iter_rows(values_only=True) if row[0]}
        self.assertEqual(application['Principal Amount'], 'KES 50,000.00')
        self.assertEqual(application['Account Number'], '0011223344')
        self.assertEqual(application['Terms Version'], '2026-01')

        terms_text = '\n'.join(r[0] for r in wb['Terms & Conditions'].iter_rows(values_only=True) if r[0])
        self.assertIn('Accepted At: 01 Oct 2026, 09:30:00 EAT', terms_text)
        self.assertIn('Submitted From IP: 41.90.1.2', terms_text)
        for section in TERMS['sections']:
            self.assertIn(section['heading'], terms_text)
            for paragraph in section['paragraphs']:
                self.assertIn(paragraph, terms_text)

    def test_legacy_loan_version_is_inferred_from_acceptance_date(self):
        LoanApplication.objects.filter(pk=self.loan.pk).update(terms_version='')

        wb = load_workbook(io.BytesIO(self.client.get(self.url('excel')).content))

        application = {row[0]: row[1] for row in wb['Application'].iter_rows(values_only=True) if row[0]}
        self.assertTrue(application['Terms Version'].startswith('2026-01 (inferred'))

    def test_terms_not_accepted(self):
        LoanApplication.objects.filter(pk=self.loan.pk).update(terms_accepted=False, terms_accepted_at=None)

        wb = load_workbook(io.BytesIO(self.client.get(self.url('excel')).content))

        self.assertEqual(
            wb['Terms & Conditions']['A1'].value, 'The applicant did not accept the Terms & Conditions.'
        )

    def test_disbursed_loan_includes_repayment_schedule(self):
        LoanApplication.objects.filter(pk=self.loan.pk).update(
            status='disbursed', disbursement_date=datetime.date(2026, 10, 10),
            first_deduction_date=datetime.date(2026, 10, 25),
        )
        self.loan.refresh_from_db()
        generate_repayment_schedule(self.loan)

        wb = load_workbook(io.BytesIO(self.client.get(self.url('excel')).content))

        rows = list(wb['Repayment Schedule'].iter_rows(min_row=2, values_only=True))
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0][1].date(), datetime.date(2026, 10, 25))

    def test_only_admins_can_export(self):
        for user in (self.employee, self.hr):
            self.client.force_authenticate(user)
            for fmt in ('pdf', 'excel'):
                self.assertEqual(self.client.get(self.url(fmt)).status_code, 403)

    def test_unknown_application(self):
        response = self.client.get('/api/v1/exports/loan-application/00000000-0000-0000-0000-000000000000/pdf/')
        self.assertEqual(response.status_code, 404)

    def test_repayment_schedule_pdf_renders(self):
        """Regression: the template used |intcomma without loading humanize."""
        LoanApplication.objects.filter(pk=self.loan.pk).update(
            status='disbursed', disbursement_date=datetime.date(2026, 10, 10),
            first_deduction_date=datetime.date(2026, 10, 25),
        )
        self.loan.refresh_from_db()
        generate_repayment_schedule(self.loan)

        response = self.client.get(f'/api/v1/exports/repayment-pdf/{self.loan.id}/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'%PDF'))
