"""
Wasiliana SMS gateway integration.

This module provides SMS functionality using the Wasiliana API.
API Documentation: https://docs.wasiliana.com/
"""

import logging
from django.conf import settings
from wasiliana import APIClient

logger = logging.getLogger(__name__)


# Initialize Wasiliana API Client
def get_wasiliana_client():
    """Get initialized Wasiliana API client."""
    return APIClient(apiKey=settings.WASILIANA_API_KEY)


def send_sms_wasiliana(phone_number: str, message: str) -> dict:
    """
    Send SMS via Wasiliana API.

    Args:
        phone_number: Recipient phone number (format: 254712345678 or +254712345678)
        message: SMS message content

    Returns:
        dict with:
            - success: Boolean
            - message_id: Message ID if successful (correlator from response)
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

        # Normalize phone number (remove + if present)
        phone_normalized = phone_number.replace('+', '').strip()

        # Ensure phone number starts with 254 (Kenya country code)
        if not phone_normalized.startswith('254'):
            if phone_normalized.startswith('0'):
                phone_normalized = '254' + phone_normalized[1:]
            else:
                logger.error(f'Invalid phone number format: {phone_number}')
                return {
                    'success': False,
                    'error': 'Invalid phone number format. Must be Kenyan number (254...)'
                }

        # Initialize client
        client = get_wasiliana_client()

        # Send SMS
        response = client.send_sms(
            sender_id=settings.WASILIANA_SENDER_ID,
            recipients=[phone_normalized],
            message=message
        )

        # Parse response
        # Expected success response format: {"correlator": "...", "status": "success", ...}
        # Expected error response format: {"error": "...", "status": "failed", ...}

        if response and isinstance(response, dict):
            status = response.get('status', '').lower()

            if status == 'success' or 'correlator' in response:
                logger.info(f'SMS sent successfully to {phone_normalized}')
                return {
                    'success': True,
                    'message_id': response.get('correlator', response.get('message_id', 'N/A')),
                    'response': response
                }
            else:
                error_msg = response.get('error', response.get('message', 'Unknown error'))
                logger.error(f'SMS send failed for {phone_normalized}: {error_msg}')
                return {
                    'success': False,
                    'error': error_msg,
                    'response': response
                }
        else:
            logger.error(f'SMS send failed for {phone_normalized}: Invalid response format')
            return {
                'success': False,
                'error': 'Invalid response from SMS gateway',
                'response': response
            }

    except Exception as e:
        logger.error(f'SMS send exception for {phone_number}: {str(e)}', exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }


def send_bulk_sms_wasiliana(recipients: list, message: str) -> dict:
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
    try:
        if not recipients or not message:
            return {
                'success_count': 0,
                'failure_count': 0,
                'results': [],
                'error': 'Recipients and message are required'
            }

        # Normalize all phone numbers
        normalized_recipients = []
        for phone in recipients:
            phone_normalized = phone.replace('+', '').strip()
            if not phone_normalized.startswith('254'):
                if phone_normalized.startswith('0'):
                    phone_normalized = '254' + phone_normalized[1:]
            normalized_recipients.append(phone_normalized)

        # Initialize client
        client = get_wasiliana_client()

        # Send bulk SMS
        response = client.send_bulk_sms(
            sender_id=settings.WASILIANA_SENDER_ID,
            recipients=normalized_recipients,
            message=message
        )

        # Parse response
        results = []
        success_count = 0
        failure_count = 0

        if response and isinstance(response, dict):
            status = response.get('status', '').lower()

            if status == 'success':
                # Assume all succeeded if bulk request succeeded
                success_count = len(normalized_recipients)
                results = [
                    {'phone': phone, 'success': True, 'message_id': response.get('correlator', 'N/A')}
                    for phone in normalized_recipients
                ]
            else:
                # Bulk request failed
                failure_count = len(normalized_recipients)
                error_msg = response.get('error', 'Bulk SMS failed')
                results = [
                    {'phone': phone, 'success': False, 'error': error_msg}
                    for phone in normalized_recipients
                ]

        logger.info(f'Bulk SMS sent: {success_count} success, {failure_count} failed')

        return {
            'success_count': success_count,
            'failure_count': failure_count,
            'results': results,
            'response': response
        }

    except Exception as e:
        logger.error(f'Bulk SMS exception: {str(e)}', exc_info=True)
        return {
            'success_count': 0,
            'failure_count': len(recipients),
            'results': [],
            'error': str(e)
        }


# Alias for backward compatibility
send_sms = send_sms_wasiliana
send_bulk_sms = send_bulk_sms_wasiliana
