"""
Tests for the email that tells 254 Capital's application inbox (checkoff@ by
default) that an employee has applied.

send_email (Microsoft Graph) is mocked so no real email is sent.
"""

from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings

from apps.accounts.models import CustomUser
from apps.notifications import tasks
from apps.notifications.test_hr_emails import make_application, make_employer


class NewApplicationAdminEmailTests(TestCase):
    def setUp(self):
        self.employer = make_employer()
        self.employee = CustomUser.objects.create(
            email='employee@example.com',
            role=CustomUser.Role.EMPLOYEE,
            phone_number='0722222222',
            first_name='Eddie',
            last_name='Mployee',
        )
        self.app = make_application(self.employer, self.employee)

    def test_checkoff_inbox_is_the_default_recipient(self):
        self.assertEqual(settings.APPLICATION_ALERT_EMAILS, ['checkoff@254-capital.com'])

    @override_settings(APPLICATION_ALERT_EMAILS=['checkoff@254-capital.com'])
    @patch('apps.notifications.tasks.send_email', return_value={'success': True})
    def test_emails_the_application_inbox_with_the_details(self, mock_send):
        tasks.notify_admins_new_application(str(self.app.id))

        mock_send.assert_called_once()
        to_addr, subject, body = mock_send.call_args.args[:3]
        self.assertEqual(to_addr, 'checkoff@254-capital.com')
        self.assertEqual(subject, 'New Loan Application - Eddie Mployee (APP-001)')
        for expected in ('Eddie Mployee', '+254722222222', self.employer.name,
                         'KES 100,000.00', '6 months', 'KES 21,666.67', 'APP-001'):
            self.assertIn(expected, body)
        self.assertIsNone(mock_send.call_args.kwargs.get('cc_address'))

    @override_settings(APPLICATION_ALERT_EMAILS=[
        'checkoff@254-capital.com', ' CHECKOFF@254-capital.com ', '', 'info@254-capital.com',
    ])
    @patch('apps.notifications.tasks.send_email', return_value={'success': True})
    def test_each_configured_inbox_gets_one_email(self, mock_send):
        tasks.notify_admins_new_application(str(self.app.id))

        recipients = [c.args[0] for c in mock_send.call_args_list]
        self.assertEqual(recipients, ['checkoff@254-capital.com', 'info@254-capital.com'])

    @override_settings(APPLICATION_ALERT_EMAILS=[])
    @patch('apps.notifications.tasks.send_email')
    def test_no_configured_inbox_sends_nothing(self, mock_send):
        tasks.notify_admins_new_application(str(self.app.id))

        mock_send.assert_not_called()

    @override_settings(APPLICATION_ALERT_EMAILS=['checkoff@254-capital.com'])
    @patch('apps.notifications.tasks.send_email', return_value={'success': False, 'error': 'Graph 403'})
    def test_send_failure_is_logged_not_raised(self, mock_send):
        with self.assertLogs('apps.notifications.tasks', level='ERROR') as logs:
            tasks.notify_admins_new_application(str(self.app.id))

        self.assertIn('Graph 403', logs.output[0])
