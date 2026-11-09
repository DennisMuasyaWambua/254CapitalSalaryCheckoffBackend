"""
Bulk loan application export: permissions, filters, one row per application,
and the Excel/CSV/PDF files themselves. Uses made-up data only.
"""

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import TestCase
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.accounts.models import CustomUser, EmployeeProfile, HRProfile
from apps.audit.models import AuditLog
from apps.employers.models import Employer
from apps.exports import application_list_export as bulk_export
from apps.loans.models import LoanApplication, LoanStatusHistory, RepaymentSchedule

NAIROBI = ZoneInfo('Africa/Nairobi')
BASE = '/api/v1/exports/loan-applications/'
FORMATS = ('excel', 'csv', 'pdf')


def at(year, month, day, hour=10, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=NAIROBI)


class ExportFixture(TestCase):
    """Two employers, their HR, an admin, and loans in several states."""

    @classmethod
    def setUpTestData(cls):
        cls.acme = cls.make_employer('Acme Ltd', 'REG-A')
        cls.beta = cls.make_employer('Beta Holdings', 'REG-B')

        cls.admin = CustomUser.objects.create_user(
            username='admin', phone_number='0700000001', password='x', role='admin',
            first_name='Ada', last_name='Admin',
        )
        cls.acme_hr = cls.make_hr('0700000002', cls.acme)
        cls.beta_hr = cls.make_hr('0700000003', cls.beta)

        cls.alice = cls.make_employee('0711000001', cls.acme, 'Alice', 'Wanjiru', '11111111', 'E-001')
        cls.bob = cls.make_employee('0711000002', cls.acme, 'Bob', 'Otieno', '22222222', 'E-002')
        cls.carol = cls.make_employee('0711000003', cls.beta, 'Carol', 'Achieng', '33333333', 'B-001')

        # Acme: one disbursed with partial repayment, one submitted
        cls.alice_loan = cls.make_loan(
            '254L00000001', cls.alice, cls.acme, 'disbursed', at(2026, 1, 10),
            principal='100000', total='118210.50', monthly='19701.75',
            disbursement_method='bank', bank_name='KCB', account_number='0011223344',
            disbursement_date=date(2026, 1, 12), disbursement_reference='TX-1',
            first_deduction_date=date(2026, 1, 25),
        )
        cls.bob_loan = cls.make_loan(
            '254L00000002', cls.bob, cls.acme, 'submitted', at(2026, 1, 31, 23, 30),
            principal='50000', total='59000.00', monthly='9833.33',
        )
        # Beta: approved, submitted on 1 Feb shortly after midnight Nairobi time
        cls.carol_loan = cls.make_loan(
            '254L00000003', cls.carol, cls.beta, 'approved', at(2026, 2, 1, 0, 30),
            principal='20000', total='21000.00', monthly='21000.00',
        )

        # Many related rows that a careless join would multiply
        for n, paid in ((1, True), (2, True), (3, False)):
            RepaymentSchedule.objects.create(
                loan=cls.alice_loan, installment_number=n, due_date=date(2026, n, 25),
                amount=Decimal('19701.75'), running_balance=Decimal('0'), is_paid=paid,
            )
        for status, when in (('submitted', at(2026, 1, 10)), ('approved', at(2026, 1, 11)),
                             ('approved', at(2026, 1, 11, 15)), ('disbursed', at(2026, 1, 12))):
            entry = LoanStatusHistory.objects.create(
                application=cls.alice_loan, status=status, actor=cls.admin, comment='x'
            )
            LoanStatusHistory.objects.filter(pk=entry.pk).update(created_at=when)

    @staticmethod
    def make_employer(name, reg):
        return Employer.objects.create(
            name=name, registration_number=reg, address='Nairobi', hr_contact_name='HR',
            hr_contact_email=f'hr@{reg.lower()}.test', hr_contact_phone='0712000000',
        )

    @staticmethod
    def make_hr(phone, employer):
        user = CustomUser.objects.create_user(
            username=f'hr-{phone}', phone_number=phone, password='x', role='hr_manager',
            first_name='Hana', last_name='HR',
        )
        HRProfile.objects.create(user=user, employer=employer)
        return user

    @staticmethod
    def make_employee(phone, employer, first, last, national_id, staff_no):
        user = CustomUser.objects.create_user(
            username=f'+254{phone[1:]}', phone_number=phone, password='x', role='employee',
            first_name=first, last_name=last, national_id=national_id,
        )
        EmployeeProfile.objects.create(
            user=user, employer=employer, employee_id=staff_no, department='Finance',
            monthly_gross_salary=Decimal('150000'), bank_name='Equity', bank_account_number='999',
            mpesa_number=phone,
        )
        return user

    @staticmethod
    def make_loan(number, employee, employer, status, created_at, principal, total, monthly, **extra):
        loan = LoanApplication.objects.create(
            application_number=number, employee=employee, employer=employer, status=status,
            principal_amount=Decimal(principal), total_repayment=Decimal(total),
            monthly_deduction=Decimal(monthly), repayment_months=6,
            interest_rate=Decimal('0.0500'), interest_method='reducing_balance',
            terms_accepted=True, purpose='School fees', **extra,
        )
        LoanApplication.objects.filter(pk=loan.pk).update(created_at=created_at)
        return loan

    def setUp(self):
        self.client = APIClient()

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def csv_rows(self, response):
        text = b''.join(response.streaming_content).decode('utf-8-sig')
        return list(csv.DictReader(io.StringIO(text)))

    def csv_numbers(self, response):
        return [r['Application Number'] for r in self.csv_rows(response)]


class PermissionTests(ExportFixture):

    def test_unauthenticated_requests_are_rejected(self):
        for path in ['summary/'] + [f'{f}/' for f in FORMATS]:
            self.assertEqual(self.client.get(BASE + path).status_code, 401, path)

    def test_employees_cannot_export(self):
        self.as_user(self.alice)
        for path in ['summary/'] + [f'{f}/' for f in FORMATS]:
            self.assertEqual(self.client.get(BASE + path).status_code, 403, path)

    def test_hr_sees_only_their_employer_and_cannot_override_it(self):
        client = self.as_user(self.acme_hr)
        response = client.get(BASE + 'csv/', {'employer_id': str(self.beta.id)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.csv_numbers(response), ['254L00000002', '254L00000001'])

        summary = client.get(BASE + 'summary/', {'employer_id': str(self.beta.id)}).json()
        self.assertTrue(summary['employer_locked'])
        self.assertEqual([e['name'] for e in summary['employers']], ['Acme Ltd'])
        self.assertEqual(summary['count'], 2)

    def test_hr_without_employer_is_forbidden(self):
        HRProfile.objects.filter(user=self.beta_hr).delete()
        user = CustomUser.objects.get(pk=self.beta_hr.pk)
        self.assertEqual(self.as_user(user).get(BASE + 'excel/').status_code, 403)


class FilterTests(ExportFixture):

    def test_admin_exports_all_employers_in_stable_order(self):
        response = self.as_user(self.admin).get(BASE + 'csv/')
        # employer name, then newest submission first
        self.assertEqual(self.csv_numbers(response), ['254L00000002', '254L00000001', '254L00000003'])

    def test_admin_filters_by_employer(self):
        response = self.as_user(self.admin).get(BASE + 'csv/', {'employer_id': str(self.beta.id)})
        self.assertEqual(self.csv_numbers(response), ['254L00000003'])

    def test_admin_filters_by_status(self):
        response = self.as_user(self.admin).get(BASE + 'csv/', {'status': 'disbursed'})
        self.assertEqual(self.csv_numbers(response), ['254L00000001'])

    def test_date_range_is_inclusive_in_nairobi_time(self):
        client = self.as_user(self.admin)
        # Bob submitted at 23:30 on 31 Jan; Carol at 00:30 on 1 Feb (Nairobi)
        january = client.get(BASE + 'csv/', {'from_date': '2026-01-31', 'to_date': '2026-01-31'})
        self.assertEqual(self.csv_numbers(january), ['254L00000002'])
        february = client.get(BASE + 'csv/', {'from_date': '2026-02-01'})
        self.assertEqual(self.csv_numbers(february), ['254L00000003'])

    def test_filters_combine(self):
        response = self.as_user(self.admin).get(BASE + 'csv/', {
            'employer_id': str(self.acme.id), 'status': 'submitted',
            'from_date': '2026-01-01', 'to_date': '2026-01-31',
        })
        self.assertEqual(self.csv_numbers(response), ['254L00000002'])

    def test_summary_count_matches_export(self):
        client = self.as_user(self.admin)
        params = {'employer_id': str(self.acme.id)}
        summary = client.get(BASE + 'summary/', params).json()
        self.assertEqual(summary['count'], len(self.csv_rows(client.get(BASE + 'csv/', params))))
        self.assertEqual(summary['total_principal'], '150000.00')
        self.assertEqual({s['status'] for s in summary['by_status']}, {'submitted', 'disbursed'})
        self.assertEqual(
            [s['value'] for s in summary['statuses']], list(LoanApplication.Status.values)
        )

    def test_invalid_input_is_rejected_cleanly(self):
        client = self.as_user(self.admin)
        cases = [
            ({'from_date': '2026-02-01', 'to_date': '2026-01-01'}, 'to_date'),
            ({'from_date': '01/02/2026'}, 'from_date'),
            ({'status': 'pending'}, 'status'),
            ({'employer_id': 'not-a-uuid'}, 'employer_id'),
            ({'employer_id': '00000000-0000-0000-0000-000000000000'}, 'employer_id'),
        ]
        for params, field in cases:
            for path in ('summary/', 'excel/', 'csv/', 'pdf/'):
                response = client.get(BASE + path, params)
                self.assertEqual(response.status_code, 400, (params, path))
                self.assertIn(field, response.json()['errors'], (params, path))
        self.assertFalse(AuditLog.objects.filter(target_type='LoanApplicationExport').exists())


class DatasetTests(ExportFixture):

    def test_each_application_appears_once_with_correct_repayment_figures(self):
        rows = self.csv_rows(self.as_user(self.admin).get(BASE + 'csv/'))
        numbers = [r['Application Number'] for r in rows]
        self.assertEqual(len(numbers), len(set(numbers)), 'an application was duplicated')
        self.assertEqual(len(rows), LoanApplication.objects.count())

        alice = next(r for r in rows if r['Application Number'] == '254L00000001')
        self.assertEqual(alice['Amount Repaid (KES)'], '39403.50')  # two paid installments, once each
        self.assertEqual(alice['Outstanding Balance (KES)'], '78807.00')
        self.assertEqual(alice['Decision Date'], '2026-01-11 15:00')  # latest approval

        bob = next(r for r in rows if r['Application Number'] == '254L00000002')
        self.assertEqual(bob['Amount Repaid (KES)'], '')  # not disbursed
        self.assertEqual(bob['Outstanding Balance (KES)'], '')

    def test_csv_headers_and_known_row(self):
        rows = self.csv_rows(self.as_user(self.admin).get(BASE + 'csv/', {'status': 'disbursed'}))
        self.assertEqual(list(rows[0].keys()), bulk_export.HEADERS)
        self.assertEqual(rows[0], {
            'Application Number': '254L00000001',
            'Status': 'Disbursed',
            'Employer': 'Acme Ltd',
            'Employee Name': 'Alice Wanjiru',
            'National ID': '11111111',
            'Phone Number': '+254711000001',
            'Employee ID': 'E-001',
            'Department': 'Finance',
            'Submitted On': '2026-01-10 10:00',
            'Decision Date': '2026-01-11 15:00',
            'Last Updated': rows[0]['Last Updated'],
            'Principal Amount (KES)': '100000.00',
            'Tenure (Months)': '6',
            'Interest Method': 'Reducing Balance',
            'Interest Rate (% per Month)': '5.00',
            'Monthly Deduction (KES)': '19701.75',
            'Total Interest (KES)': '18210.50',
            'Total Repayment (KES)': '118210.50',
            'Amount Repaid (KES)': '39403.50',
            'Outstanding Balance (KES)': '78807.00',
            'Disbursement Method': 'Bank Transfer',
            'Bank Name': 'KCB',
            'Bank Branch': '',
            'Bank Account Number': '0011223344',
            'M-Pesa Number': '+254711000001',
            'Disbursement Date': '2026-01-12',
            'Disbursement Reference': 'TX-1',
            'First Deduction Date': '2026-01-25',
            'Purpose': 'School fees',
        })

    def test_excel_headers_numeric_cells_and_totals(self):
        response = self.as_user(self.admin).get(BASE + 'excel/', {'employer_id': str(self.acme.id)})
        self.assertEqual(response.status_code, 200)
        ws = load_workbook(io.BytesIO(response.content))['Loan Applications']
        self.assertIn('Acme Ltd', ws['A2'].value)
        self.assertIn('Generated', ws['A3'].value)
        self.assertEqual([c.value for c in ws[5]], bulk_export.HEADERS)

        principal_col = bulk_export.HEADERS.index('Principal Amount (KES)') + 1
        first = {bulk_export.HEADERS[i]: c.value for i, c in enumerate(ws[6])}
        self.assertEqual(first['Application Number'], '254L00000002')
        principal = ws.cell(row=6, column=principal_col)
        self.assertEqual(principal.value, 50000)  # a number, so Excel can sum it
        self.assertEqual(principal.number_format, '#,##0.00')
        self.assertIsInstance(first['Submitted On'], datetime)

        self.assertEqual(ws.cell(row=9, column=1).value, 'Total (2)')
        self.assertEqual(ws.cell(row=9, column=principal_col).value, 150000)
        self.assertEqual(ws.auto_filter.ref, f'A5:{ws.cell(row=7, column=len(bulk_export.HEADERS)).column_letter}7')

    def test_pdf_is_generated_with_the_rows(self):
        response = self.as_user(self.admin).get(BASE + 'pdf/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_pdf_row_limit_points_to_excel(self):
        original = bulk_export.PDF_MAX_ROWS
        bulk_export.PDF_MAX_ROWS = 2
        try:
            response = self.as_user(self.admin).get(BASE + 'pdf/')
        finally:
            bulk_export.PDF_MAX_ROWS = original
        self.assertEqual(response.status_code, 400)
        self.assertIn('Excel or CSV', response.json()['detail'])

    def test_empty_result_still_produces_valid_files(self):
        client = self.as_user(self.admin)
        params = {'from_date': '2030-01-01'}

        rows = self.csv_rows(client.get(BASE + 'csv/', params))
        self.assertEqual(rows, [])
        text = b''.join(client.get(BASE + 'csv/', params).streaming_content).decode('utf-8-sig')
        self.assertEqual(next(csv.reader(io.StringIO(text))), bulk_export.HEADERS)

        ws = load_workbook(io.BytesIO(client.get(BASE + 'excel/', params).content))['Loan Applications']
        self.assertEqual([c.value for c in ws[5]], bulk_export.HEADERS)
        self.assertEqual(ws['A6'].value, 'No applications match these filters.')

        pdf = client.get(BASE + 'pdf/', params)
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b'%PDF'))

    def test_spreadsheet_formulas_in_user_text_are_neutralized(self):
        LoanApplication.objects.filter(pk=self.bob_loan.pk).update(purpose='=HYPERLINK("http://evil","x")')
        client = self.as_user(self.admin)
        params = {'status': 'submitted', 'employer_id': str(self.acme.id)}

        row = self.csv_rows(client.get(BASE + 'csv/', params))[0]
        self.assertEqual(row['Purpose'], '\'=HYPERLINK("http://evil","x")')
        self.assertEqual(row['Phone Number'], '+254711000002')  # numbers are left alone

        ws = load_workbook(io.BytesIO(client.get(BASE + 'excel/', params).content))['Loan Applications']
        purpose = ws.cell(row=6, column=bulk_export.HEADERS.index('Purpose') + 1)
        self.assertEqual(purpose.data_type, 's')


class ResponseTests(ExportFixture):

    def test_filename_headers_and_audit_log(self):
        response = self.as_user(self.admin).get(BASE + 'excel/', {
            'employer_id': str(self.acme.id), 'status': 'under_review_admin',
            'from_date': '2026-01-01', 'to_date': '2026-01-31',
        })
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename="loan-applications-acme-ltd-under-review-admin-2026-01-01-2026-01-31.xlsx"',
        )
        self.assertEqual(response['Cache-Control'], 'no-store')

        entry = AuditLog.objects.get(target_type='LoanApplicationExport')
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.metadata['format'], 'excel')
        self.assertEqual(entry.metadata['row_count'], 0)
        self.assertEqual(entry.metadata['filters']['employer_id'], str(self.acme.id))
        # The export reference in the file is the audit entry's target
        ws = load_workbook(io.BytesIO(response.content))['Loan Applications']
        self.assertIn(str(entry.target_id), ws['A3'].value)
        # No row data in the audit trail
        self.assertNotIn('Alice', str(entry.metadata))

    def test_unfiltered_filename(self):
        response = self.as_user(self.admin).get(BASE + 'csv/')
        self.assertEqual(
            response['Content-Disposition'], 'attachment; filename="loan-applications-all-all-any-any.csv"'
        )
