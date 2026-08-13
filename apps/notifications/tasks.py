"""
Celery tasks for notifications and SMS.
"""

from celery import shared_task
from django.conf import settings
from .models import Notification
from .sms import send_sms
from common.email_service import send_email
import logging

logger = logging.getLogger(__name__)


# 254 Capital is always copied on HR notifications so the lender retains a record.
CC_254_CAPITAL = 'david.muema@254-capital.com'


def _hr_recipients_for_employer(employer):
    """
    Resolve the email recipients for an employer's HR.

    Returns a list of (email, display_name) tuples. Prefers active HR user
    accounts linked to the employer; falls back to the employer's onboarding
    HR contact email when no HR user account exists. Returns an empty list if
    no recipient can be determined (caller should log a warning, not crash).
    """
    from apps.accounts.models import CustomUser

    recipients = []
    try:
        hr_users = CustomUser.objects.filter(
            role=CustomUser.Role.HR_MANAGER,
            hr_profile__employer=employer,
            is_active=True,
        )
        recipients = [
            (u.email, u.get_full_name() or 'HR Manager')
            for u in hr_users if u.email
        ]
    except Exception as e:
        logger.error(f'Failed to resolve HR users for employer {getattr(employer, "id", "?")}: {e}')

    # Fall back to the employer's onboarding HR contact when no HR account exists.
    if not recipients and getattr(employer, 'hr_contact_email', None):
        recipients = [(employer.hr_contact_email, employer.hr_contact_name or 'HR Team')]

    return recipients


def _hr_email_html(header_color, title, greeting_name, intro_html, detail_rows, footer_html=''):
    """
    Build an HR notification email using the same layout/styling as the rest of
    common.email_service (header / content / footer with inline styles).

    detail_rows: list of (label, value) tuples rendered as a bordered table.
    """
    rows = ''.join(
        f'<li style="margin-bottom:6px;"><strong>{label}:</strong> {value}</li>'
        for label, value in detail_rows
    )
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: {header_color}; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f9f9f9; }}
            .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
            .details {{ background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 5px; padding: 15px 20px; margin: 15px 0; }}
            .details ul {{ list-style: none; padding: 0; margin: 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{title}</h1>
            </div>
            <div class="content">
                <h2>Hello {greeting_name},</h2>
                {intro_html}
                <div class="details">
                    <ul>{rows}</ul>
                </div>
                {footer_html}
                <p>Best regards,<br><strong>254 Capital Team</strong></p>
            </div>
            <div class="footer">
                <p>&copy; 2026 254 Capital. All rights reserved.</p>
                <p>This is an automated notification. Please do not reply to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """


@shared_task(bind=True, max_retries=2)
def send_otp_sms(self, phone_number: str, otp_code: str):
    """
    Send OTP SMS to phone number.

    Args:
        phone_number: Recipient phone number
        otp_code: 6-digit OTP code
    """
    message = (
        f'Your 254 Capital verification code is {otp_code}. '
        f'Valid for 5 minutes. Do not share this code with anyone.'
    )

    try:
        result = send_sms(phone_number, message)
    except Exception as e:
        logger.error(f'OTP SMS exception for {phone_number}: {e}')
        # Don't retry in eager (sync) mode — it would block the request
        if not self.request.called_directly:
            raise self.retry(exc=e, countdown=30 * (2 ** self.request.retries))
        return {'success': False, 'error': str(e)}

    if not result['success']:
        logger.error(f'OTP SMS failed for {phone_number}: {result.get("error")}')
        if not self.request.called_directly:
            raise self.retry(
                exc=Exception(result.get('error', 'SMS send failed')),
                countdown=30 * (2 ** self.request.retries)
            )
    else:
        logger.info(f'OTP SMS sent to {phone_number}')

    return result


@shared_task(bind=True, max_retries=2)
def send_otp_email(self, email: str, otp_code: str, user_name: str = ''):
    """
    Send OTP verification code to an email address.

    Used alongside send_otp_sms so employees receive their login code on the
    email their account was created with, in addition to SMS.

    Args:
        email: Recipient email address
        otp_code: 6-digit OTP code
        user_name: Optional recipient display name for the greeting
    """
    greeting_name = user_name or 'there'
    intro_html = (
        '<p>Use the verification code below to complete your 254 Capital login. '
        'The code is valid for 5 minutes.</p>'
        f'<p style="font-size:28px; font-weight:bold; letter-spacing:6px; '
        f'color:#0a3d62; text-align:center; margin:20px 0;">{otp_code}</p>'
        '<p>If you did not request this code, please ignore this email and do '
        'not share the code with anyone.</p>'
    )
    body_html = _hr_email_html(
        header_color='#0a3d62',
        title='Your Verification Code',
        greeting_name=greeting_name,
        intro_html=intro_html,
        detail_rows=[('Valid for', '5 minutes')],
    )

    try:
        result = send_email(email, 'Your 254 Capital verification code', body_html)
    except Exception as e:
        logger.error(f'OTP email exception for {email}: {e}')
        if not self.request.called_directly:
            raise self.retry(exc=e, countdown=30 * (2 ** self.request.retries))
        return {'success': False, 'error': str(e)}

    if not result.get('success'):
        logger.error(f'OTP email failed for {email}: {result.get("error")}')
        if not self.request.called_directly:
            raise self.retry(
                exc=Exception(result.get('error', 'Email send failed')),
                countdown=30 * (2 ** self.request.retries)
            )
    else:
        logger.info(f'OTP email sent to {email}')

    return result


@shared_task
def notify_application_submitted(application_id: str):
    """
    Notify employee and HR about new application submission.

    Args:
        application_id: UUID of loan application
    """
    try:
        from apps.loans.models import LoanApplication

        app = LoanApplication.objects.select_related('employee', 'employer').get(id=application_id)

        # Notify employee
        Notification.objects.create(
            user=app.employee,
            title='Application Submitted',
            message=f'Your loan application {app.application_number} for KES {app.principal_amount:,.2f} has been submitted successfully.',
            link=f'/applications/{app.id}',
            notification_type=Notification.NotificationType.STATUS_UPDATE
        )

        # SMS to employee
        employee_sms = (
            f'Your 254 Capital loan application {app.application_number} for '
            f'KES {app.principal_amount:,.2f} has been submitted. You will be notified of the status.'
        )
        send_sms(app.employee.phone_number, employee_sms)

        logger.info(f'Application submitted notifications sent for {application_id}')

    except Exception as e:
        logger.error(f'Failed to send application submitted notifications: {str(e)}')


@shared_task
def notify_hr_new_application(application_id: str):
    """
    Notify HR managers about new application for their employer.

    Args:
        application_id: UUID of loan application
    """
    try:
        from apps.loans.models import LoanApplication
        from apps.accounts.models import CustomUser

        app = LoanApplication.objects.select_related('employee', 'employer').get(id=application_id)

        # Get HR users for this employer
        hr_users = CustomUser.objects.filter(
            role='hr_manager',
            hr_profile__employer=app.employer
        )

        for hr_user in hr_users:
            Notification.objects.create(
                user=hr_user,
                title='New Loan Application',
                message=f'New application {app.application_number} from {app.employee.get_full_name()} for KES {app.principal_amount:,.2f}',
                link=f'/hr/applications/{app.id}',
                notification_type=Notification.NotificationType.STATUS_UPDATE
            )

        logger.info(f'HR in-app notifications created for application {application_id}')

        # Trigger 1: Email the relevant HR user(s) that an application needs sign-off.
        recipients = _hr_recipients_for_employer(app.employer)
        if not recipients:
            logger.warning(
                f'No HR recipient found for employer {app.employer_id} '
                f'(application {app.application_number}). Skipping HR email.'
            )
            return

        employee_name = app.employee.get_full_name()
        application_date = app.created_at.strftime('%d %B %Y') if app.created_at else 'N/A'
        subject = f'[Action Required] New Loan Application - {employee_name} ({app.application_number})'

        for email, name in recipients:
            body_html = _hr_email_html(
                header_color='#2c3e50',
                title='New Loan Application',
                greeting_name=name,
                intro_html='<p>A new loan application has been submitted and requires your review and approval.</p>',
                detail_rows=[
                    ('Employee', employee_name),
                    ('Loan Amount Requested', f'KES {app.principal_amount:,.2f}'),
                    ('Application Date', application_date),
                    ('Application Number', app.application_number),
                ],
                footer_html=(
                    '<p style="background-color:#fff3cd;border-left:4px solid #ffc107;'
                    'padding:10px;border-radius:3px;">'
                    '<strong>Action required:</strong> Please log in to the HR portal to '
                    'review and approve this application.</p>'
                ),
            )
            result = send_email(email, subject, body_html, cc_address=CC_254_CAPITAL)
            if result.get('success'):
                logger.info(f'New-application HR email sent to {email} for {app.application_number}')
            else:
                logger.error(
                    f'Failed to send new-application HR email to {email} '
                    f'for {app.application_number}: {result.get("error")}'
                )

    except Exception as e:
        logger.error(f'Failed to send HR notifications: {str(e)}')


@shared_task
def notify_hr_disbursement(application_id: str):
    """
    Trigger 2: Notify the relevant HR user(s) by email when a loan is disbursed,
    so payroll deductions can be set up.

    Includes employee name, amount disbursed, disbursement date, monthly
    installment, tenure, and a payroll-deduction start note applying the
    15th-day rule (disbursed on/before the 15th -> deductions start the same
    month; after the 15th -> the following month).

    Args:
        application_id: UUID of loan application
    """
    try:
        from apps.loans.models import LoanApplication

        app = LoanApplication.objects.select_related('employee', 'employer').get(id=application_id)

        recipients = _hr_recipients_for_employer(app.employer)
        if not recipients:
            logger.warning(
                f'No HR recipient found for employer {app.employer_id} '
                f'(application {app.application_number}). Skipping HR disbursement email.'
            )
            return

        employee_name = app.employee.get_full_name()
        disbursement_date_str = app.disbursement_date.strftime('%d %B %Y') if app.disbursement_date else 'N/A'

        # Build the payroll deduction-start note from the 15th-day rule.
        if app.first_deduction_date:
            start_month = app.first_deduction_date.strftime('%B %Y')
            if app.disbursement_date and app.disbursement_date.day <= 15:
                rule_note = 'disbursed on or before the 15th'
            else:
                rule_note = 'disbursed after the 15th'
            deduction_note = (
                f'<p style="background-color:#e8f5e9;border-left:4px solid #27ae60;'
                f'padding:10px;border-radius:3px;">'
                f'<strong>Payroll deductions should commence from {start_month}</strong> '
                f'({rule_note}). The first deduction falls due on '
                f'{app.first_deduction_date.strftime("%d %B %Y")}.</p>'
            )
        else:
            deduction_note = (
                '<p>Please set up payroll deductions for this employee per the '
                'agreed check-off schedule.</p>'
            )

        subject = f'Loan Disbursed - {employee_name} ({app.application_number})'

        for email, name in recipients:
            body_html = _hr_email_html(
                header_color='#27ae60',
                title='Loan Disbursed',
                greeting_name=name,
                intro_html=(
                    '<p>A loan has been disbursed to one of your employees. '
                    'Please note the following details for payroll processing.</p>'
                ),
                detail_rows=[
                    ('Employee', employee_name),
                    ('Loan Amount Disbursed', f'KES {app.principal_amount:,.2f}'),
                    ('Disbursement Date', disbursement_date_str),
                    ('Monthly Installment', f'KES {app.monthly_deduction:,.2f}'),
                    ('Loan Tenure', f'{app.repayment_months} months'),
                    ('Application Number', app.application_number),
                ],
                footer_html=deduction_note,
            )
            result = send_email(email, subject, body_html, cc_address=CC_254_CAPITAL)
            if result.get('success'):
                logger.info(f'Disbursement HR email sent to {email} for {app.application_number}')
            else:
                logger.error(
                    f'Failed to send disbursement HR email to {email} '
                    f'for {app.application_number}: {result.get("error")}'
                )

    except Exception as e:
        logger.error(f'Failed to send HR disbursement notification: {str(e)}')


@shared_task
def notify_status_change(application_id: str, new_status: str):
    """
    Notify employee about application status change.

    Args:
        application_id: UUID of loan application
        new_status: New status value
    """
    try:
        from apps.loans.models import LoanApplication

        app = LoanApplication.objects.select_related('employee').get(id=application_id)

        # Map status to message
        status_messages = {
            'under_review_hr': 'Your application is now under HR review.',
            'under_review_admin': 'Your application has been approved by HR and is now under 254 Capital review.',
            'approved': 'Congratulations! Your loan application has been approved and will be disbursed soon.',
            'declined': 'Your loan application has been declined. Please contact us for more information.',
            'disbursed': f'Your loan of KES {app.principal_amount:,.2f} has been disbursed. First deduction: {app.first_deduction_date.strftime("%d %B %Y")}.'
        }

        message = status_messages.get(new_status, 'Your application status has been updated.')

        # Create notification
        Notification.objects.create(
            user=app.employee,
            title='Application Status Update',
            message=f'{app.application_number}: {message}',
            link=f'/applications/{app.id}',
            notification_type=Notification.NotificationType.STATUS_UPDATE
        )

        # Send SMS for important statuses
        if new_status in ['approved', 'declined', 'disbursed']:
            send_sms(app.employee.phone_number, f'254 Capital: {message}')

        logger.info(f'Status change notification sent for {application_id}: {new_status}')

    except Exception as e:
        logger.error(f'Failed to send status change notification: {str(e)}')


@shared_task
def notify_disbursement(application_id: str):
    """
    Notify employee about loan disbursement with details.

    Args:
        application_id: UUID of loan application
    """
    try:
        from apps.loans.models import LoanApplication

        app = LoanApplication.objects.select_related('employee').get(id=application_id)

        # Create notification
        Notification.objects.create(
            user=app.employee,
            title='Loan Disbursed',
            message=(
                f'Your loan {app.application_number} for KES {app.principal_amount:,.2f} has been disbursed via {app.get_disbursement_method_display()}. '
                f'Monthly deduction: KES {app.monthly_deduction:,.2f}. '
                f'First deduction: {app.first_deduction_date.strftime("%d %B %Y")}.'
            ),
            link=f'/applications/{app.id}',
            notification_type=Notification.NotificationType.DISBURSEMENT
        )

        # Send detailed SMS
        sms_message = (
            f'254 Capital: Your loan of KES {app.principal_amount:,.2f} has been disbursed. '
            f'Monthly deduction: KES {app.monthly_deduction:,.2f}. '
            f'First deduction: {app.first_deduction_date.strftime("%d/%m/%Y")}. '
            f'Thank you for choosing 254 Capital.'
        )
        send_sms(app.employee.phone_number, sms_message)

        logger.info(f'Disbursement notification sent for {application_id}')

    except Exception as e:
        logger.error(f'Failed to send disbursement notification: {str(e)}')


@shared_task
def notify_remittance_submitted(remittance_id: str):
    """
    Notify admins about new remittance submission.

    Args:
        remittance_id: UUID of remittance
    """
    try:
        from apps.reconciliation.models import Remittance
        from apps.accounts.models import CustomUser

        remittance = Remittance.objects.select_related('employer', 'submitted_by').get(id=remittance_id)

        # Get all admin users
        admin_users = CustomUser.objects.filter(role='admin')

        for admin_user in admin_users:
            Notification.objects.create(
                user=admin_user,
                title='New Remittance Submitted',
                message=f'{remittance.employer.name} submitted remittance for {remittance.period_display}: KES {remittance.total_amount:,.2f}',
                link=f'/admin/reconciliation/remittances/{remittance.id}',
                notification_type=Notification.NotificationType.REMITTANCE
            )

        logger.info(f'Remittance submission notifications sent for {remittance_id}')

    except Exception as e:
        logger.error(f'Failed to send remittance submitted notifications: {str(e)}')


@shared_task
def notify_remittance_confirmed(remittance_id: str):
    """
    Notify HR about remittance confirmation.

    Args:
        remittance_id: UUID of remittance
    """
    try:
        from apps.reconciliation.models import Remittance
        from apps.accounts.models import CustomUser

        remittance = Remittance.objects.select_related('employer', 'submitted_by', 'confirmed_by').get(id=remittance_id)

        # Get HR users for this employer
        hr_users = CustomUser.objects.filter(
            role='hr_manager',
            hr_profile__employer=remittance.employer
        )

        status_text = 'confirmed' if remittance.status == 'confirmed' else 'disputed'

        for hr_user in hr_users:
            Notification.objects.create(
                user=hr_user,
                title=f'Remittance {status_text.title()}',
                message=f'Your remittance for {remittance.period_display} has been {status_text} by 254 Capital.',
                link=f'/hr/remittances/{remittance.id}',
                notification_type=Notification.NotificationType.REMITTANCE
            )

        logger.info(f'Remittance confirmation notifications sent for {remittance_id}')

    except Exception as e:
        logger.error(f'Failed to send remittance confirmation notifications: {str(e)}')


@shared_task
def send_deduction_reminders():
    """
    Send reminders to employees about upcoming deductions (3 days before).

    This is a periodic task scheduled via Celery Beat.
    """
    try:
        from apps.loans.models import RepaymentSchedule
        from datetime import date, timedelta

        # Get schedules due in 3 days
        reminder_date = date.today() + timedelta(days=3)

        schedules = RepaymentSchedule.objects.filter(
            due_date=reminder_date,
            is_paid=False
        ).select_related('loan__employee', 'loan')

        for schedule in schedules:
            loan = schedule.loan
            employee = loan.employee

            # Create notification
            Notification.objects.create(
                user=employee,
                title='Upcoming Loan Deduction',
                message=f'Reminder: Loan deduction of KES {schedule.amount:,.2f} will be processed on {schedule.due_date.strftime("%d %B %Y")}.',
                link=f'/applications/{loan.id}',
                notification_type=Notification.NotificationType.REMINDER
            )

            # Send SMS
            sms_message = (
                f'254 Capital: Reminder - Loan deduction of KES {schedule.amount:,.2f} '
                f'will be processed on {schedule.due_date.strftime("%d/%m/%Y")}.'
            )
            send_sms(employee.phone_number, sms_message)

        logger.info(f'Sent {schedules.count()} deduction reminders')

    except Exception as e:
        logger.error(f'Failed to send deduction reminders: {str(e)}')


@shared_task
def send_contract_expiry_alerts():
    """
    Send alerts to contract employees and HR about upcoming contract expirations.

    This is a periodic task scheduled via Celery Beat.
    Sends alerts at 30 days, 14 days, and 7 days before expiry.
    """
    try:
        from apps.accounts.models import EmployeeProfile, CustomUser
        from datetime import date, timedelta

        today = date.today()
        alert_periods = [30, 14, 7]  # Days before expiry to send alerts

        total_alerts_sent = 0

        for days_before in alert_periods:
            expiry_date = today + timedelta(days=days_before)

            # Get contract employees with contracts expiring on this date
            expiring_profiles = EmployeeProfile.objects.filter(
                employment_type=EmployeeProfile.EmploymentType.CONTRACT,
                contract_end_date=expiry_date
            ).select_related('user', 'employer')

            for profile in expiring_profiles:
                employee = profile.user

                # Notify employee
                Notification.objects.create(
                    user=employee,
                    title='Contract Expiry Alert',
                    message=(
                        f'Your employment contract with {profile.employer.name} is expiring in {days_before} days '
                        f'(on {profile.contract_end_date.strftime("%d %B %Y")}). '
                        f'Please contact your HR department for more information.'
                    ),
                    link='/profile',
                    notification_type=Notification.NotificationType.REMINDER
                )

                # Send SMS to employee
                sms_message = (
                    f'254 Capital: Your contract with {profile.employer.name} expires in {days_before} days '
                    f'({profile.contract_end_date.strftime("%d/%m/%Y")}). Please contact HR.'
                )
                send_sms(employee.phone_number, sms_message)

                # Notify HR managers for this employer
                hr_users = CustomUser.objects.filter(
                    role='hr_manager',
                    hr_profile__employer=profile.employer
                )

                for hr_user in hr_users:
                    Notification.objects.create(
                        user=hr_user,
                        title='Contract Expiry Alert',
                        message=(
                            f'Contract employee {employee.get_full_name()} ({profile.employee_id}) '
                            f'has a contract expiring in {days_before} days ({profile.contract_end_date.strftime("%d %B %Y")}).'
                        ),
                        link='/hr/employees',
                        notification_type=Notification.NotificationType.REMINDER
                    )

                total_alerts_sent += 1

        logger.info(f'Sent {total_alerts_sent} contract expiry alerts')

    except Exception as e:
        logger.error(f'Failed to send contract expiry alerts: {str(e)}')
