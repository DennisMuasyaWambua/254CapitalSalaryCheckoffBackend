"""
Microsoft Graph API Email Service for 254 Capital.

This module provides email sending functionality using Microsoft Graph API
instead of traditional SMTP. All emails are sent from checkoff@254-capital.com
using Azure AD application credentials.
"""

import os
import logging
import requests
import msal

logger = logging.getLogger(__name__)

# Load Azure credentials from environment variables
AZURE_TENANT_ID = os.environ.get('AZURE_TENANT_ID')
AZURE_CLIENT_ID = os.environ.get('AZURE_CLIENT_ID')
AZURE_CLIENT_SECRET = os.environ.get('AZURE_CLIENT_SECRET')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'checkoff@254-capital.com')

# Microsoft Graph API endpoint
GRAPH_API_ENDPOINT = 'https://graph.microsoft.com/v1.0'


def _get_access_token():
    """
    Acquire access token for Microsoft Graph API using client credentials flow.

    Returns:
        str: Access token for Graph API

    Raises:
        Exception: If token acquisition fails
    """
    try:
        authority = f'https://login.microsoftonline.com/{AZURE_TENANT_ID}'
        scope = ['https://graph.microsoft.com/.default']

        app = msal.ConfidentialClientApplication(
            AZURE_CLIENT_ID,
            authority=authority,
            client_credential=AZURE_CLIENT_SECRET
        )

        result = app.acquire_token_for_client(scopes=scope)

        if 'access_token' in result:
            logger.info('Successfully acquired access token for Microsoft Graph API')
            return result['access_token']
        else:
            error_msg = result.get('error_description', 'Unknown error')
            logger.error(f'Failed to acquire access token: {error_msg}')
            raise Exception(f'Token acquisition failed: {error_msg}')

    except Exception as e:
        logger.error(f'Error acquiring access token: {str(e)}')
        raise


def send_email(to_address, subject, body_html, cc_address=None):
    """
    Send email using Microsoft Graph API.

    Args:
        to_address (str): Recipient email address
        subject (str): Email subject line
        body_html (str): HTML body content of the email
        cc_address (str, optional): CC email address. Defaults to None.

    Returns:
        dict: Response with 'success' boolean and optional 'error' message

    Example:
        >>> send_email(
        ...     to_address='user@example.com',
        ...     subject='Welcome to 254 Capital',
        ...     body_html='<h1>Welcome!</h1><p>Thank you for joining us.</p>'
        ... )
        {'success': True}
    """
    try:
        # Validate required environment variables
        if not all([AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET]):
            error_msg = 'Missing Azure credentials in environment variables'
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

        if not to_address or not subject or not body_html:
            error_msg = 'Missing required email parameters (to_address, subject, or body_html)'
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

        # Get access token
        access_token = _get_access_token()

        # Prepare email message
        message = {
            'message': {
                'subject': subject,
                'body': {
                    'contentType': 'HTML',
                    'content': body_html
                },
                'toRecipients': [
                    {
                        'emailAddress': {
                            'address': to_address
                        }
                    }
                ]
            },
            'saveToSentItems': 'true'
        }

        # Add CC if provided
        if cc_address:
            message['message']['ccRecipients'] = [
                {
                    'emailAddress': {
                        'address': cc_address
                    }
                }
            ]

        # Send email via Microsoft Graph API
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        endpoint = f'{GRAPH_API_ENDPOINT}/users/{SENDER_EMAIL}/sendMail'

        response = requests.post(
            endpoint,
            headers=headers,
            json=message,
            timeout=30
        )

        if response.status_code == 202:
            logger.info(f'Email sent successfully to {to_address} with subject: {subject}')
            return {'success': True}
        else:
            error_msg = f'Failed to send email. Status: {response.status_code}, Response: {response.text}'
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

    except Exception as e:
        error_msg = f'Exception sending email: {str(e)}'
        logger.error(error_msg)
        return {'success': False, 'error': error_msg}


def send_welcome_email(to_address, user_name, role='Employee'):
    """
    Send a welcome email to newly registered users.

    Args:
        to_address (str): User's email address
        user_name (str): User's full name
        role (str): User role (Employee, HR Manager, Admin)

    Returns:
        dict: Response from send_email()
    """
    subject = 'Welcome to 254 Capital Salary Check-Off System'

    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #2c3e50; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f9f9f9; }}
            .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
            .button {{ display: inline-block; padding: 10px 20px; background-color: #3498db; color: white; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Welcome to 254 Capital</h1>
            </div>
            <div class="content">
                <h2>Hello {user_name}!</h2>
                <p>Welcome to the 254 Capital Salary Check-Off Loan Management System.</p>
                <p>Your account has been successfully created as a <strong>{role}</strong>.</p>

                <p>With your account, you can:</p>
                <ul>
                    {'<li>Apply for salary check-off loans</li><li>Track your loan applications</li><li>View repayment schedules</li>' if role == 'Employee' else ''}
                    {'<li>Review employee loan applications</li><li>Submit salary deduction remittances</li><li>Manage employee records</li>' if role == 'HR Manager' else ''}
                    {'<li>Manage all system operations</li><li>Review and approve loan applications</li><li>Process disbursements</li>' if role == 'Admin' else ''}
                </ul>

                <p>If you have any questions or need assistance, please don't hesitate to contact our support team.</p>

                <p>Best regards,<br>
                <strong>254 Capital Team</strong></p>
            </div>
            <div class="footer">
                <p>&copy; 2026 254 Capital. All rights reserved.</p>
                <p>This is an automated message. Please do not reply to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(to_address, subject, body_html)


def send_password_reset_email(to_address, user_name, reset_token, reset_url):
    """
    Send password reset email with reset link.

    Args:
        to_address (str): User's email address
        user_name (str): User's full name
        reset_token (str): Password reset token
        reset_url (str): Base URL for password reset

    Returns:
        dict: Response from send_email()
    """
    full_reset_url = f'{reset_url}?token={reset_token}'
    subject = '254 Capital - Password Reset Request'

    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #e74c3c; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f9f9f9; }}
            .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
            .button {{ display: inline-block; padding: 12px 30px; background-color: #e74c3c; color: white; text-decoration: none; border-radius: 5px; margin: 15px 0; }}
            .warning {{ background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; margin: 15px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Password Reset Request</h1>
            </div>
            <div class="content">
                <h2>Hello {user_name},</h2>
                <p>We received a request to reset your password for your 254 Capital account.</p>

                <p>Click the button below to reset your password:</p>
                <p style="text-align: center;">
                    <a href="{full_reset_url}" class="button">Reset Password</a>
                </p>

                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; background-color: #f0f0f0; padding: 10px; border-radius: 3px;">
                    {full_reset_url}
                </p>

                <div class="warning">
                    <strong>Important:</strong>
                    <ul>
                        <li>This link will expire in 1 hour</li>
                        <li>If you didn't request this reset, please ignore this email</li>
                        <li>Your password will not change until you create a new one</li>
                    </ul>
                </div>

                <p>Best regards,<br>
                <strong>254 Capital Team</strong></p>
            </div>
            <div class="footer">
                <p>&copy; 2026 254 Capital. All rights reserved.</p>
                <p>This is an automated message. Please do not reply to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(to_address, subject, body_html)


def send_internal_alert(subject, message, alert_type='info'):
    """
    Send internal system alert to admin (david.muema@254-capital.com).

    Args:
        subject (str): Alert subject
        message (str): Alert message (can be plain text or HTML)
        alert_type (str): Type of alert ('info', 'warning', 'error', 'success')

    Returns:
        dict: Response from send_email()
    """
    admin_email = 'david.muema@254-capital.com'

    # Color coding based on alert type
    color_map = {
        'info': '#3498db',
        'warning': '#f39c12',
        'error': '#e74c3c',
        'success': '#27ae60'
    }

    alert_color = color_map.get(alert_type, '#3498db')

    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: {alert_color}; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f9f9f9; }}
            .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
            .alert-badge {{ display: inline-block; padding: 5px 10px; background-color: {alert_color}; color: white; border-radius: 3px; font-size: 12px; text-transform: uppercase; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>System Alert</h1>
            </div>
            <div class="content">
                <p><span class="alert-badge">{alert_type.upper()}</span></p>
                <h2>{subject}</h2>
                <div>
                    {message}
                </div>
                <hr>
                <p style="font-size: 12px; color: #666;">
                    This is an automated system alert from 254 Capital Salary Check-Off System.
                </p>
            </div>
            <div class="footer">
                <p>&copy; 2026 254 Capital. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(admin_email, f'[SYSTEM ALERT] {subject}', body_html)
