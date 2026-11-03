"""
Loan application submission tests.

Requests mirror the frontend: multipart FormData with every scalar
stringified and the files under national_id_front / national_id_back /
payslip_N.
"""

import io
import shutil
import tempfile
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import CustomUser, EmployeeProfile
from apps.employers.models import Employer
from apps.loans.models import LoanApplication
from apps.loans.terms import CURRENT_TERMS_VERSION

MEDIA_ROOT = tempfile.mkdtemp()
PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'


def jpeg(padding_mb=0):
    buf = io.BytesIO()
    Image.new('RGB', (40, 40), 'blue').save(buf, 'JPEG')
    return buf.getvalue() + b'\0' * int(padding_mb * 1024 * 1024)


def make_employee(employer, phone='0712345678', **profile):
    user = CustomUser.objects.create_user(
        username=f'+254{phone[1:]}', phone_number=phone, password='x',
        role='employee', first_name='Jane', last_name='Doe', email='jane@acme.test',
    )
    EmployeeProfile.objects.create(
        user=user, employer=employer, employee_id=f'E-{phone}',
        monthly_gross_salary=Decimal('150000'), bank_name='KCB', bank_account_number='123',
        **profile,
    )
    return user


def make_employer():
    return Employer.objects.create(
        name='Acme Ltd', registration_number='REG-1', address='Nairobi',
        hr_contact_name='HR', hr_contact_email='hr@acme.test', hr_contact_phone='0712000000',
    )


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
@mock.patch('apps.loans.views.send_internal_alert')
@mock.patch('apps.loans.views.send_email')
@mock.patch('apps.notifications.tasks.notify_hr_new_application.delay')
class LoanApplicationSubmissionTests(TestCase):

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.employee = make_employee(make_employer())
        self.client = APIClient()
        self.client.force_authenticate(self.employee)

    def submit(self, fields=None, files=None):
        data = {
            'principal_amount': '50000', 'repayment_months': '6', 'purpose': 'Personal loan',
            'terms_accepted': 'true', 'disbursement_method': 'mpesa',
            **(fields or {}),
        }
        if files is None:
            files = self.documents()
        data.update({k: v for k, v in files.items() if v is not None})
        return self.client.post('/api/v1/loans/applications/', data, format='multipart')

    def documents(self, **overrides):
        docs = {
            'national_id_front': SimpleUploadedFile('front.jpg', jpeg(), 'image/jpeg'),
            'national_id_back': SimpleUploadedFile('back.jpg', jpeg(), 'image/jpeg'),
            'payslip_1': SimpleUploadedFile('payslip.pdf', PDF, 'application/pdf'),
        }
        docs.update(overrides)
        return docs

    def test_phone_camera_sized_id_photo_is_accepted(self, *_):
        """A 6 MB photo used to fail the old 5 MB cap."""
        response = self.submit(files=self.documents(
            national_id_front=SimpleUploadedFile('IMG_2041.jpg', jpeg(padding_mb=6), 'image/jpeg'),
        ))

        self.assertEqual(response.status_code, 201, response.content)
        loan = LoanApplication.objects.get(id=response.json()['id'])
        self.assertEqual(loan.documents.count(), 3)
        self.assertEqual(loan.terms_version, CURRENT_TERMS_VERSION)
        self.assertIsNotNone(loan.terms_accepted_at)

    def test_bank_account_number_alias_is_accepted(self, *_):
        response = self.submit(fields={
            'disbursement_method': 'bank', 'bank_name': 'KCB', 'bank_branch': 'CBD',
            'bank_account_number': '0011223344',
        })

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(LoanApplication.objects.get().account_number, '0011223344')

    def test_all_problems_reported_at_once_and_named_by_document(self, *_):
        response = self.submit(fields={'principal_amount': '3000'}, files=self.documents(
            national_id_front=SimpleUploadedFile('IMG.jpg', jpeg(padding_mb=11), 'image/jpeg'),
            national_id_back=SimpleUploadedFile('back.HEIC', jpeg(), 'image/heic'),
            payslip_1=None,
        ))

        self.assertEqual(response.status_code, 400)
        body = response.json()
        errors = body['errors']
        self.assertEqual(
            set(errors), {'principal_amount', 'national_id_front', 'national_id_back', 'payslip_1'}
        )
        self.assertEqual(errors['principal_amount'], ['The minimum loan amount is KES 5,000.'])
        self.assertTrue(errors['national_id_front'][0].startswith('National ID (Front): File size'))
        self.assertTrue(errors['national_id_back'][0].startswith('National ID (Back): .heic files'))
        self.assertEqual(errors['payslip_1'], ['Payslip 1 (Most Recent) is required.'])
        # Clients that only show `detail` still get a concrete reason
        self.assertEqual(body['detail'], 'The minimum loan amount is KES 5,000.')
        self.assertFalse(LoanApplication.objects.exists())

    def test_empty_and_extensionless_files_are_named(self, *_):
        response = self.submit(files=self.documents(
            national_id_front=SimpleUploadedFile('image', jpeg(), 'image/jpeg'),
            national_id_back=SimpleUploadedFile('back.jpg', b'', 'image/jpeg'),
        ))

        self.assertEqual(response.status_code, 400)
        errors = response.json()['errors']
        self.assertIn('Files without an extension', errors['national_id_front'][0])
        self.assertIn('The file is empty', errors['national_id_back'][0])

    def test_amount_must_be_multiple_of_100(self, *_):
        response = self.submit(fields={'principal_amount': '50050'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()['errors']['principal_amount'],
            ['The loan amount must be a multiple of KES 100.'],
        )

    def test_contract_staff_are_still_ineligible(self, *_):
        profile = self.employee.employee_profile
        profile.employment_type = 'contract'
        profile.contract_end_date = '2027-01-01'
        profile.save()
        self.client.force_authenticate(CustomUser.objects.get(pk=self.employee.pk))

        response = self.submit()

        self.assertEqual(response.status_code, 400)
        self.assertIn('confirmed staff', response.json()['detail'])
