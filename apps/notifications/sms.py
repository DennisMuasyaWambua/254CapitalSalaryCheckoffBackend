"""
SMS gateway integration using Wasiliana.
"""

import logging
from django.conf import settings
from .wasiliana_sms import send_sms_wasiliana, send_bulk_sms_wasiliana

logger = logging.getLogger(__name__)


def send_sms(phone_number: str, message: str) -> dict:
    """
    Send SMS via Wasiliana API.

    Args:
        phone_number: Recipient phone number (format: +254712345678 or 254712345678)
        message: SMS message content

    Returns:
        dict with:
            - success: Boolean
            - message_id: Message ID if successful
            - error: Error message if failed
    """
    return send_sms_wasiliana(phone_number, message)


def send_bulk_sms(recipients: list, message: str) -> dict:
    """
    Send bulk SMS to multiple recipients via Wasiliana.

    Args:
        recipients: List of phone numbers
        message: SMS message content

    Returns:
        dict with:
            - success_count: Number of successful sends
            - failure_count: Number of failed sends
            - results: List of individual results
    """
    return send_bulk_sms_wasiliana(recipients, message)


def get_sms_balance() -> dict:
    """
    Get SMS account balance.

    Returns:
        dict with balance info or error

    Note: Wasiliana API may not have a direct balance endpoint.
    This is a placeholder for future implementation.
    """
    logger.info('SMS balance check not implemented for Wasiliana API')
    return {
        'success': False,
        'error': 'Balance check not implemented for Wasiliana API'
    }
