"""
Tests for Enhancement 1: viewing uploaded documents across account roles.

Confirms that the per-application documents endpoint:
  - is accessible to the employee owner, HR of the same employer, and admin
  - is denied to an employee/HR of a different employer
  - returns the file URL and type flags (is_image / is_pdf / mime_type) so the
    UI can render inline previews/thumbnails for every role.
"""

import tempfile
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import CustomUser, HRProfile, EmployeeProfile
from apps.employers.models import Employer
from apps.loans.models import LoanApplication
from apps.documents.models import Document


def make_employer(reg):
    return Employer.objects.create(
        name=f'Employer {reg}',
        registration_number=reg,
        address='Nairobi',
        hr_contact_name='HR Contact',
        hr_contact_email=f'contact@{reg}.com',
        hr_contact_phone='0712345678',
        interest_method='flat',
        interest_rate=Decimal('0.05'),
    )


# A tiny valid PNG header is enough; mime_type is set explicitly on the model.
PNG_BYTES = b'\x89PNG\r\n\x1a\n' + b'0' * 32


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class DocumentViewingByRoleTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.employer_a = make_employer('REGA')
        self.employer_b = make_employer('REGB')

        # Employee who owns the application (employer A)
        self.employee_a = CustomUser.objects.create(
            email='emp-a@example.com', role=CustomUser.Role.EMPLOYEE,
            phone_number='0722222222', first_name='Eddie', last_name='Owner',
        )
        # Unrelated employee (employer B)
        self.employee_b = CustomUser.objects.create(
            email='emp-b@example.com', role=CustomUser.Role.EMPLOYEE,
            phone_number='0723333333', first_name='Otto', last_name='Other',
        )
        # HR of employer A / employer B
        self.hr_a = CustomUser.objects.create(
            email='hr-a@example.com', username='hr_a', role=CustomUser.Role.HR_MANAGER,
            phone_number='0711111111', first_name='Helen', last_name='A',
        )
        HRProfile.objects.create(user=self.hr_a, employer=self.employer_a)
        self.hr_b = CustomUser.objects.create(
            email='hr-b@example.com', username='hr_b', role=CustomUser.Role.HR_MANAGER,
            phone_number='0712222222', first_name='Hank', last_name='B',
        )
        HRProfile.objects.create(user=self.hr_b, employer=self.employer_b)
        # Admin
        self.admin = CustomUser.objects.create(
            email='admin@example.com', username='admin1', role=CustomUser.Role.ADMIN,
            phone_number='0733333333', first_name='Adam', last_name='Min',
        )

        self.application = LoanApplication.objects.create(
            application_number='APP-DOC-1',
            employee=self.employee_a,
            employer=self.employer_a,
            principal_amount=Decimal('100000'),
            interest_rate=Decimal('0.05'),
            repayment_months=6,
            total_repayment=Decimal('130000'),
            monthly_deduction=Decimal('21666.67'),
            purpose='Test',
            status='submitted',
            terms_accepted=True,
        )

        # National ID (image) + payslip (pdf)
        self.id_doc = Document.objects.create(
            application=self.application,
            uploaded_by=self.employee_a,
            document_type='national_id_front',
            file=SimpleUploadedFile('id.png', PNG_BYTES, content_type='image/png'),
            original_filename='id.png',
            file_size=len(PNG_BYTES),
            mime_type='image/png',
        )
        self.payslip = Document.objects.create(
            application=self.application,
            uploaded_by=self.employee_a,
            document_type='payslip_1',
            file=SimpleUploadedFile('payslip.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
            original_filename='payslip.pdf',
            file_size=13,
            mime_type='application/pdf',
        )

        self.url = reverse('documents:application-documents', args=[self.application.id])

    def _get_as(self, user):
        self.client.force_authenticate(user=user)
        return self.client.get(self.url)

    def _assert_viewable_payload(self, data):
        self.assertEqual(len(data), 2)
        by_type = {d['document_type']: d for d in data}
        id_doc = by_type['national_id_front']
        payslip = by_type['payslip_1']
        # File URL present so the UI can render/download
        self.assertTrue(id_doc['file_url'])
        self.assertTrue(payslip['file_url'])
        # Type flags drive image vs pdf rendering
        self.assertTrue(id_doc['is_image'])
        self.assertFalse(id_doc['is_pdf'])
        self.assertTrue(payslip['is_pdf'])
        self.assertEqual(id_doc['mime_type'], 'image/png')
        self.assertEqual(payslip['mime_type'], 'application/pdf')

    # ----- allowed roles -----
    def test_employee_owner_can_view(self):
        resp = self._get_as(self.employee_a)
        self.assertEqual(resp.status_code, 200)
        self._assert_viewable_payload(resp.json())

    def test_hr_same_employer_can_view(self):
        resp = self._get_as(self.hr_a)
        self.assertEqual(resp.status_code, 200)
        self._assert_viewable_payload(resp.json())

    def test_admin_can_view(self):
        resp = self._get_as(self.admin)
        self.assertEqual(resp.status_code, 200)
        self._assert_viewable_payload(resp.json())

    # ----- denied roles -----
    def test_other_employee_denied(self):
        resp = self._get_as(self.employee_b)
        self.assertEqual(resp.status_code, 403)

    def test_hr_other_employer_denied(self):
        resp = self._get_as(self.hr_b)
        self.assertEqual(resp.status_code, 403)
