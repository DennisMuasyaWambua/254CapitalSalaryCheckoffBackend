"""
Local-disk document storage (USE_S3=False): an application can be submitted,
and each document is reachable only through a signed, expiring link.
"""

import shutil
import tempfile
from unittest import mock

from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.documents.file_access import FILE_TOKEN_SALT
from apps.documents.models import Document
from apps.loans.tests import PDF, jpeg, make_employee, make_employer

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT, USE_S3=False)
@mock.patch('apps.loans.views.send_internal_alert')
@mock.patch('apps.loans.views.send_email')
@mock.patch('apps.notifications.tasks.notify_hr_new_application.delay')
class LocalDocumentStorageTests(TestCase):

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.employee = make_employee(make_employer())
        self.client = APIClient()
        self.client.force_authenticate(self.employee)

    def submit(self):
        return self.client.post('/api/v1/loans/applications/', {
            'principal_amount': '50000', 'repayment_months': '6', 'terms_accepted': 'true',
            'disbursement_method': 'mpesa',
            'national_id_front': SimpleUploadedFile('front.jpg', jpeg(), 'image/jpeg'),
            'national_id_back': SimpleUploadedFile('back.jpg', jpeg(), 'image/jpeg'),
            'payslip_1': SimpleUploadedFile('payslip.pdf', PDF, 'application/pdf'),
        }, format='multipart')

    def listed_documents(self, application_id):
        response = self.client.get(f'/api/v1/documents/application/{application_id}/')
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        return body['results'] if isinstance(body, dict) and 'results' in body else body

    def test_application_saves_and_documents_open_by_signed_link(self, *_):
        response = self.submit()
        self.assertEqual(response.status_code, 201, response.content)
        docs = {d['document_type']: d for d in self.listed_documents(response.json()['id'])}
        self.assertEqual(set(docs), {'national_id_front', 'national_id_back', 'payslip_1'})

        anonymous = APIClient()  # the link itself is the credential, as with S3 presigned URLs
        pdf = anonymous.get(docs['payslip_1']['file_url'])
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(b''.join(pdf.streaming_content), PDF)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        self.assertEqual(pdf['Cache-Control'], 'private, no-store')
        self.assertIn('inline', pdf['Content-Disposition'])

        photo = anonymous.get(docs['national_id_front']['file_url'], {'download': '1'})
        self.assertIn('attachment', photo['Content-Disposition'])
        self.assertEqual(photo['Content-Type'], 'image/jpeg')

    def test_bad_expired_and_unknown_links_are_refused(self, *_):
        docs = self.listed_documents(self.submit().json()['id'])
        good = docs[0]['file_url']
        anonymous = APIClient()

        self.assertEqual(anonymous.get(good[:-3] + 'xx/').status_code, 404)  # tampered
        self.assertEqual(anonymous.get('/api/v1/documents/file/garbage/').status_code, 404)
        unknown = signing.dumps('00000000-0000-0000-0000-000000000000', salt=FILE_TOKEN_SALT)
        self.assertEqual(anonymous.get(f'/api/v1/documents/file/{unknown}/').status_code, 404)
        with mock.patch('apps.documents.file_access.FILE_LINK_LIFETIME_SECONDS', -1):
            self.assertEqual(anonymous.get(good).status_code, 404)  # expired
        self.assertEqual(anonymous.get(good).status_code, 200)

    def test_missing_file_is_a_clean_404(self, *_):
        doc = Document.objects.get(pk=self.listed_documents(self.submit().json()['id'])[0]['id'])
        doc.file.storage.delete(doc.file.name)
        link = self.listed_documents(doc.application_id)[0]['file_url']
        self.assertEqual(APIClient().get(link).status_code, 404)

    def test_link_uses_https_behind_the_proxy(self, *_):
        application_id = self.submit().json()['id']
        response = self.client.get(
            f'/api/v1/documents/application/{application_id}/', HTTP_X_FORWARDED_PROTO='https'
        )
        body = response.json()
        docs = body['results'] if isinstance(body, dict) and 'results' in body else body
        self.assertTrue(docs[0]['file_url'].startswith('https://'))
