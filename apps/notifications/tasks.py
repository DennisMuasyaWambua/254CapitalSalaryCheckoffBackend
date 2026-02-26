"""
Celery tasks for notifications and SMS.
"""

from celery import shared_task
from django.conf import settings
from .models import Notification
from .sms import send_sms
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_otp_sms(self, phone_number: str, otp_code: str):
    """
    Send OTP SMS to phone number.

    Args:
        phone_number: Recipient phone number
        otp_code: 6-digit OTP code
    """
    try:
        message = (
            f'Your 254 Capital verification code is {otp_code}. '
            f'Valid for 5 minutes. Do not share this code with anyone.'
        )

        result = send_sms(phone_number, message)

        if not result['success']:
            logger.error(f'OTP SMS failed for {phone_number}: {result.get("error")}')
            # Retry on failure
            raise Exception(result.get('error', 'SMS send failed'))

        logger.info(f'OTP SMS sent to {phone_number}')
        return result

    except Exception as e:
        logger.error(f'OTP SMS task failed: {str(e)}')
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


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

        logger.info(f'HR notifications sent for application {application_id}')

    except Exception as e:
        logger.error(f'Failed to send HR notifications: {str(e)}')


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
