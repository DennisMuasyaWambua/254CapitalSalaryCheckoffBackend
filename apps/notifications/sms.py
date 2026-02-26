"""
SMS gateway integration using Africa's Talking.
"""

import logging
from django.conf import settings
import africastalking

logger = logging.getLogger(__name__)


# Initialize Africa's Talking
africastalking.initialize(
    username=settings.AFRICASTALKING_USERNAME,
    api_key=settings.AFRICASTALKING_API_KEY
)

# Get SMS service
sms_service = africastalking.SMS


def send_sms(phone_number: str, message: str) -> dict:
    """
    Send SMS via Africa's Talking API.

    Args:
        phone_number: Recipient phone number (format: +254712345678)
        message: SMS message content

    Returns:
        dict with:
            - success: Boolean
            - message_id: Message ID if successful
            - error: Error message if failed
    """
    try:
        # Validate inputs
        if not phone_number or not message:
            logger.error('SMS send failed: Missing phone number or message')
            return {
                'success': False,
                'error': 'Phone number and message are required'
            }

        # Send SMS
        response = sms_service.send(
            message=message,
            recipients=[phone_number],
            sender_id=settings.AFRICASTALKING_SENDER_ID
        )

        # Parse response
        if response and 'SMSMessageData' in response:
            message_data = response['SMSMessageData']
            recipients = message_data.get('Recipients', [])

            if recipients and len(recipients) > 0:
                recipient = recipients[0]
                status_code = recipient.get('statusCode')

                if status_code == 101:  # Success code
                    logger.info(f'SMS sent successfully to {phone_number}')
                    return {
                        'success': True,
                        'message_id': recipient.get('messageId'),
                        'cost': recipient.get('cost'),
                        'status': recipient.get('status')
                    }
                else:
                    error_msg = recipient.get('status', 'Unknown error')
                    logger.error(f'SMS send failed for {phone_number}: {error_msg}')
                    return {
                        'success': False,
                        'error': error_msg
                    }

        logger.error(f'SMS send failed for {phone_number}: Invalid response format')
        return {
            'success': False,
            'error': 'Invalid response from SMS gateway'
        }

    except Exception as e:
        logger.error(f'SMS send exception for {phone_number}: {str(e)}', exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }


def send_bulk_sms(recipients: list, message: str) -> dict:
    """
    Send bulk SMS to multiple recipients.

    Args:
        recipients: List of phone numbers
        message: SMS message content

    Returns:
        dict with:
            - success_count: Number of successful sends
            - failure_count: Number of failed sends
            - results: List of individual results
    """
    try:
        if not recipients or not message:
            return {
                'success_count': 0,
                'failure_count': 0,
                'results': [],
                'error': 'Recipients and message are required'
            }

        # Send bulk SMS
        response = sms_service.send(
            message=message,
            recipients=recipients,
            sender_id=settings.AFRICASTALKING_SENDER_ID
        )

        # Parse response
        results = []
        success_count = 0
        failure_count = 0

        if response and 'SMSMessageData' in response:
            message_data = response['SMSMessageData']
            recipients_data = message_data.get('Recipients', [])

            for recipient in recipients_data:
                phone = recipient.get('number')
                status_code = recipient.get('statusCode')

                if status_code == 101:
                    success_count += 1
                    results.append({
                        'phone': phone,
                        'success': True,
                        'message_id': recipient.get('messageId')
                    })
                else:
                    failure_count += 1
                    results.append({
                        'phone': phone,
                        'success': False,
                        'error': recipient.get('status')
                    })

        logger.info(f'Bulk SMS sent: {success_count} success, {failure_count} failed')

        return {
            'success_count': success_count,
            'failure_count': failure_count,
            'results': results
        }

    except Exception as e:
        logger.error(f'Bulk SMS exception: {str(e)}', exc_info=True)
        return {
            'success_count': 0,
            'failure_count': len(recipients),
            'results': [],
            'error': str(e)
        }


def get_sms_balance() -> dict:
    """
    Get SMS account balance.

    Returns:
        dict with balance info or error
    """
    try:
        # Get account service
        account = africastalking.Application

        # Fetch balance
        balance = account.fetch_application_data()

        logger.info(f'SMS balance fetched: {balance}')

        return {
            'success': True,
            'balance': balance
        }

    except Exception as e:
        logger.error(f'Failed to fetch SMS balance: {str(e)}')
        return {
            'success': False,
            'error': str(e)
        }
