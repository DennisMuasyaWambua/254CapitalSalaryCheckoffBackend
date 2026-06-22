"""
Tests for Enhancement 3: HR email notifications.

Trigger 1 - new application pending HR approval.
Trigger 2 - loan disbursed by admin (with 15th-day payroll-deduction note).

send_email (Microsoft Graph) is mocked so no real email is sent.
"""

from decimal import Decimal
from datetime import date
from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import CustomUser, HRProfile
from apps.employers.models import Employer
from apps.loans.models import LoanApplication
from apps.notifications import tasks


def make_employer(reg='REG1', hr_contact_email='contact@employer.com'):
    return Employer.objects.create(
        name=f'Employer {reg}',
        registration_number=reg,
        address='Nairobi',
        hr_contact_name='HR Contact',
        hr_contact_email=hr_contact_email,
        hr_contact_phone='0712345678',
        interest_method='flat',
        interest_rate=Decimal('0.05'),
    )


def make_application(employer, employee, **overrides):
    data = dict(
        application_number='APP-001',
        employee=employee,
        employer=employer,
        principal_amount=Decimal('100000'),
        interest_rate=Decimal('0.05'),
        repayment_months=6,
        total_repayment=Decimal('130000'),
        monthly_deduction=Decimal('21666.67'),
        purpose='Test loan',
        status='submitted',
        terms_accepted=True,
    )
    data.update(overrides)
    return LoanApplication.objects.create(**data)


class HREmailNotificationTests(TestCase):
    def setUp(self):
        self.employer = make_employer()
        self.employee = CustomUser.objects.create(
            email='employee@example.com',
            role=CustomUser.Role.EMPLOYEE,
            phone_number='0722222222',
            first_name='Eddie',
            last_name='Mployee',
        )
        self.hr_user = CustomUser.objects.create(
            email='hr@example.com',
            username='hr_user',
            role=CustomUser.Role.HR_MANAGER,
            phone_number='0711111111',
            first_name='Helen',
            last_name='Resource',
        )
        HRProfile.objects.create(user=self.hr_user, employer=self.employer)
        self.app = make_application(self.employer, self.employee)

    # ----- Trigger 1: new application -----
    @patch('apps.notifications.tasks.send_email', return_value={'success': True})
    def test_new_application_emails_hr_user(self, mock_send):
        tasks.notify_hr_new_application(str(self.app.id))

        self.assertTrue(mock_send.called)
        to_addr, subject, body = mock_send.call_args.args[:3]
        self.assertEqual(to_addr, 'hr@example.com')
        self.assertIn('Eddie Mployee', subject)
        self.assertIn('APP-001', subject)
        # body content checks
        self.assertIn('100,000', body)
        self.assertIn('log in to the HR portal', body)
        self.assertIn('review and approve', body)
        # cc to 254 Capital
        self.assertEqual(mock_send.call_args.kwargs.get('cc_address'), tasks.CC_254_CAPITAL)

    @patch('apps.notifications.tasks.send_email', return_value={'success': True})
    def test_new_application_falls_back_to_contact_email(self, mock_send):
        # Remove the HR user account -> should fall back to employer.hr_contact_email
        HRProfile.objects.all().delete()
        self.hr_user.delete()

        tasks.notify_hr_new_application(str(self.app.id))

        self.assertTrue(mock_send.called)
        to_addr = mock_send.call_args.args[0]
        self.assertEqual(to_addr, 'contact@employer.com')

    @patch('apps.notifications.tasks.send_email', return_value={'success': True})
    def test_new_application_no_recipient_does_not_send(self, mock_send):
        HRProfile.objects.all().delete()
        self.hr_user.delete()
        self.employer.hr_contact_email = ''
        self.employer.save()

        tasks.notify_hr_new_application(str(self.app.id))

        self.assertFalse(mock_send.called)

    # ----- Trigger 2: disbursement -----
    @patch('apps.notifications.tasks.send_email', return_value={'success': True})
    def test_disbursement_emails_hr_with_details(self, mock_send):
        # Disbursed on the 5th (<= 15th) -> deductions start the SAME month
        self.app.disbursement_date = date(2026, 3, 5)
        self.app.first_deduction_date = date(2026, 3, 25)
        self.app.status = 'disbursed'
        self.app.save()

        tasks.notify_hr_disbursement(str(self.app.id))

        self.assertTrue(mock_send.called)
        to_addr, subject, body = mock_send.call_args.args[:3]
        self.assertEqual(to_addr, 'hr@example.com')
        self.assertIn('Loan Disbursed', subject)
        self.assertIn('Eddie Mployee', subject)
        self.assertIn('100,000', body)            # amount disbursed
        self.assertIn('21,666', body)             # monthly installment
        self.assertIn('6 months', body)           # tenure
        self.assertIn('March 2026', body)         # deduction-start month (same month)
        self.assertIn('on or before the 15th', body)

    @patch('apps.notifications.tasks.send_email', return_value={'success': True})
    def test_disbursement_after_15th_starts_next_month(self, mock_send):
        # Disbursed on the 20th (> 15th) -> deductions start NEXT month
        self.app.disbursement_date = date(2026, 3, 20)
        self.app.first_deduction_date = date(2026, 4, 25)
        self.app.status = 'disbursed'
        self.app.save()

        tasks.notify_hr_disbursement(str(self.app.id))

        to_addr, subject, body = mock_send.call_args.args[:3]
        self.assertIn('April 2026', body)
        self.assertIn('after the 15th', body)
