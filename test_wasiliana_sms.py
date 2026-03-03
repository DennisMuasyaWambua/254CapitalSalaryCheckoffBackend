#!/usr/bin/env python
"""
Test script for Wasiliana SMS integration.

This script tests:
1. Wasiliana SMS API connection
2. OTP generation and sending
3. OTP verification

Usage:
    python test_wasiliana_sms.py <phone_number>

Example:
    python test_wasiliana_sms.py 254712345678
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.notifications.wasiliana_sms import send_sms_wasiliana
from apps.accounts.otp import generate_otp, store_otp, verify_otp
from django.conf import settings


def test_sms_send(phone_number):
    """Test sending SMS via Wasiliana."""
    print("\n" + "="*60)
    print("TESTING WASILIANA SMS INTEGRATION")
    print("="*60)

    print(f"\n1. Configuration Check:")
    print(f"   - API Key: {settings.WASILIANA_API_KEY[:20]}...{settings.WASILIANA_API_KEY[-10:]}")
    print(f"   - Sender ID: {settings.WASILIANA_SENDER_ID}")

    print(f"\n2. Generating OTP...")
    otp_code = generate_otp()
    print(f"   - OTP Code: {otp_code}")

    print(f"\n3. Storing OTP in Redis...")
    otp_info = store_otp(phone_number, otp_code)
    print(f"   - Masked Phone: {otp_info['masked_phone']}")
    print(f"   - Expires In: {otp_info['expires_in']} seconds")

    print(f"\n4. Sending SMS via Wasiliana...")
    message = (
        f'Your 254 Capital verification code is {otp_code}. '
        f'Valid for 5 minutes. Do not share this code with anyone.'
    )

    result = send_sms_wasiliana(phone_number, message)

    print(f"\n5. SMS Send Result:")
    print(f"   - Success: {result.get('success')}")
    if result.get('success'):
        print(f"   - Message ID: {result.get('message_id')}")
        print(f"   - Response: {result.get('response')}")
    else:
        print(f"   - Error: {result.get('error')}")
        print(f"   - Response: {result.get('response')}")

    print("\n" + "="*60)
    print("TEST COMPLETED")
    print("="*60)

    if result.get('success'):
        print("\n✓ SMS sent successfully!")
        print(f"✓ Check phone {phone_number} for the OTP: {otp_code}")
        print("\n6. Testing OTP Verification...")

        # Prompt user to verify OTP
        user_otp = input("\nEnter the OTP you received (or press Enter to auto-verify): ").strip()
        if not user_otp:
            user_otp = otp_code

        is_valid, error_msg = verify_otp(phone_number, user_otp)
        print(f"\n   - OTP Valid: {is_valid}")
        if not is_valid:
            print(f"   - Error: {error_msg}")
        else:
            print("   - ✓ OTP verification successful!")
    else:
        print("\n✗ SMS send failed!")
        print("Please check:")
        print("  1. Wasiliana API credentials are correct")
        print("  2. Phone number format is correct (254...)")
        print("  3. Wasiliana account has sufficient balance")
        print("  4. Network connectivity is working")

    return result


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python test_wasiliana_sms.py <phone_number>")
        print("Example: python test_wasiliana_sms.py 254712345678")
        sys.exit(1)

    phone_number = sys.argv[1]
    test_sms_send(phone_number)
