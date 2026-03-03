#!/usr/bin/env python
"""
Comprehensive test for all login flows with OTP.

Tests:
1. Employee OTP Login (Phone-based)
2. HR Manager Login with OTP
3. Admin Login with OTP

Usage:
    python test_login_flows.py
"""

import os
import sys
import django
import json
import time
from typing import Dict, Any

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from apps.accounts.models import EmployeeProfile, HRProfile
from apps.employers.models import Employer
from apps.accounts.otp import generate_otp, store_otp, verify_otp
from django.core.cache import cache

User = get_user_model()


def print_section(title):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(success, message):
    """Print a formatted result."""
    icon = "✓" if success else "✗"
    status = "SUCCESS" if success else "FAILED"
    print(f"\n{icon} {status}: {message}")


def create_test_data():
    """Create test users for all roles."""
    print_section("CREATING TEST DATA")

    # Create employer
    employer, _ = Employer.objects.get_or_create(
        name="Test Company Ltd",
        defaults={
            'registration_number': 'TEST123',
            'kra_pin': 'A001234567Z',
            'physical_address': 'Nairobi',
            'is_active': True
        }
    )
    print(f"✓ Employer created: {employer.name}")

    # Create Employee User
    employee_phone = '+254712345678'
    employee, created = User.objects.get_or_create(
        phone_number=employee_phone,
        defaults={
            'username': employee_phone,
            'first_name': 'John',
            'last_name': 'Employee',
            'national_id': '12345678',
            'role': 'employee',
            'is_phone_verified': True,
            'is_active': True
        }
    )
    if created:
        EmployeeProfile.objects.create(
            user=employee,
            employer=employer,
            employee_id='EMP001',
            monthly_gross_salary=50000,
            bank_name='KCB',
            bank_account_number='1234567890'
        )
    print(f"✓ Employee created: {employee.get_full_name()} ({employee_phone})")

    # Create HR Manager User
    hr_user, created = User.objects.get_or_create(
        email='hr@testcompany.com',
        defaults={
            'username': 'hr@testcompany.com',
            'first_name': 'Jane',
            'last_name': 'HR Manager',
            'phone_number': '+254723456789',
            'national_id': '87654321',
            'role': 'hr_manager',
            'is_active': True
        }
    )
    if created:
        hr_user.set_password('HRPassword123!')
        hr_user.save()
        HRProfile.objects.create(
            user=hr_user,
            employer=employer,
            department='Human Resources'
        )
    print(f"✓ HR Manager created: {hr_user.get_full_name()} ({hr_user.email})")
    print(f"  Password: HRPassword123!")

    # Create Admin User
    admin_user, created = User.objects.get_or_create(
        email='admin@254capital.com',
        defaults={
            'username': 'admin@254capital.com',
            'first_name': 'Super',
            'last_name': 'Admin',
            'phone_number': '+254734567890',
            'national_id': '11223344',
            'role': 'admin',
            'is_active': True,
            'is_staff': True,
            'is_superuser': True
        }
    )
    if created:
        admin_user.set_password('AdminPassword123!')
        admin_user.save()
    print(f"✓ Admin created: {admin_user.get_full_name()} ({admin_user.email})")
    print(f"  Password: AdminPassword123!")

    return {
        'employee': employee,
        'hr': hr_user,
        'admin': admin_user,
        'employer': employer
    }


def test_employee_otp_login(client: Client, employee_phone: str):
    """Test employee OTP-based login flow."""
    print_section("TEST 1: EMPLOYEE OTP LOGIN")

    # Step 1: Send OTP
    print("\n1. Sending OTP to employee phone...")
    response = client.post('/api/v1/auth/otp/send/', {
        'phone_number': employee_phone
    }, content_type='application/json')

    print(f"   Status: {response.status_code}")
    print(f"   Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code != 200:
        print_result(False, "Failed to send OTP")
        return False

    # Get the OTP from cache (in real scenario, user would receive via SMS)
    # For testing, we'll retrieve it from Redis
    from common.utils import cache_key, mask_phone_number
    from common.utils import normalize_kenyan_phone
    normalized_phone = normalize_kenyan_phone(employee_phone)
    otp_key = cache_key('otp', normalized_phone)
    otp_data = cache.get(otp_key)

    if not otp_data:
        print_result(False, "OTP not found in cache")
        return False

    # Generate a test OTP code (we'll use a known one for testing)
    test_otp = '123456'
    store_otp(normalized_phone, test_otp)
    print(f"   ✓ OTP stored for testing: {test_otp}")

    # Step 2: Verify OTP
    print("\n2. Verifying OTP...")
    time.sleep(1)
    response = client.post('/api/v1/auth/otp/verify/', {
        'phone_number': employee_phone,
        'otp': test_otp
    }, content_type='application/json')

    print(f"   Status: {response.status_code}")
    print(f"   Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code == 200:
        data = response.json()
        if 'tokens' in data:
            print_result(True, "Employee OTP login successful!")
            print(f"   Access Token: {data['tokens']['access'][:50]}...")
            return True
        elif data.get('is_new_user'):
            print_result(True, "Phone verified (new user)")
            return True

    print_result(False, "OTP verification failed")
    return False


def test_hr_otp_login(client: Client, hr_email: str, hr_password: str, hr_phone: str):
    """Test HR manager login with OTP flow."""
    print_section("TEST 2: HR MANAGER LOGIN WITH OTP")

    # Step 1: Login with email/password
    print("\n1. Logging in with email/password...")
    response = client.post('/api/v1/auth/hr/login/', {
        'email': hr_email,
        'password': hr_password
    }, content_type='application/json')

    print(f"   Status: {response.status_code}")
    print(f"   Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code != 200:
        print_result(False, "HR login failed at step 1")
        return False

    data = response.json()
    if not data.get('requires_otp'):
        print_result(False, "OTP not required (expected OTP flow)")
        return False

    temp_token = data.get('temp_token')
    print(f"   ✓ Temp token received: {temp_token[:50]}...")
    print(f"   ✓ OTP sent to: {data.get('masked_phone')}")

    # Get OTP for testing
    from common.utils import normalize_kenyan_phone
    normalized_phone = normalize_kenyan_phone(hr_phone)
    test_otp = '654321'
    store_otp(normalized_phone, test_otp)
    print(f"   ✓ OTP stored for testing: {test_otp}")

    # Step 2: Verify OTP
    print("\n2. Verifying OTP...")
    time.sleep(1)
    response = client.post('/api/v1/auth/verify-login-otp/', {
        'temp_token': temp_token,
        'otp': test_otp
    }, content_type='application/json')

    print(f"   Status: {response.status_code}")
    print(f"   Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code == 200:
        data = response.json()
        if 'tokens' in data:
            print_result(True, "HR Manager OTP login successful!")
            print(f"   Access Token: {data['tokens']['access'][:50]}...")
            return True

    print_result(False, "HR OTP verification failed")
    return False


def test_admin_otp_login(client: Client, admin_email: str, admin_password: str, admin_phone: str):
    """Test admin login with OTP flow."""
    print_section("TEST 3: ADMIN LOGIN WITH OTP")

    # Step 1: Login with email/password
    print("\n1. Logging in with email/password...")
    response = client.post('/api/v1/auth/admin/login/', {
        'email': admin_email,
        'password': admin_password
    }, content_type='application/json')

    print(f"   Status: {response.status_code}")
    print(f"   Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code != 200:
        print_result(False, "Admin login failed at step 1")
        return False

    data = response.json()
    if not data.get('requires_otp'):
        print_result(False, "OTP not required (expected OTP flow)")
        return False

    temp_token = data.get('temp_token')
    print(f"   ✓ Temp token received: {temp_token[:50]}...")
    print(f"   ✓ OTP sent to: {data.get('masked_phone')}")

    # Get OTP for testing
    from common.utils import normalize_kenyan_phone
    normalized_phone = normalize_kenyan_phone(admin_phone)
    test_otp = '999888'
    store_otp(normalized_phone, test_otp)
    print(f"   ✓ OTP stored for testing: {test_otp}")

    # Step 2: Verify OTP
    print("\n2. Verifying OTP...")
    time.sleep(1)
    response = client.post('/api/v1/auth/verify-login-otp/', {
        'temp_token': temp_token,
        'otp': test_otp
    }, content_type='application/json')

    print(f"   Status: {response.status_code}")
    print(f"   Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code == 200:
        data = response.json()
        if 'tokens' in data:
            print_result(True, "Admin OTP login successful!")
            print(f"   Access Token: {data['tokens']['access'][:50]}...")
            return True

    print_result(False, "Admin OTP verification failed")
    return False


def main():
    """Run all tests."""
    print_section("OTP LOGIN FLOW COMPREHENSIVE TEST")
    print("Testing all login flows with OTP verification")

    # Create test data
    test_users = create_test_data()

    # Initialize test client
    client = Client()

    # Run tests
    results = []

    # Test 1: Employee OTP Login
    employee_result = test_employee_otp_login(
        client,
        test_users['employee'].phone_number
    )
    results.append(('Employee OTP Login', employee_result))

    # Test 2: HR Manager OTP Login
    hr_result = test_hr_otp_login(
        client,
        test_users['hr'].email,
        'HRPassword123!',
        test_users['hr'].phone_number
    )
    results.append(('HR Manager OTP Login', hr_result))

    # Test 3: Admin OTP Login
    admin_result = test_admin_otp_login(
        client,
        test_users['admin'].email,
        'AdminPassword123!',
        test_users['admin'].phone_number
    )
    results.append(('Admin OTP Login', admin_result))

    # Print summary
    print_section("TEST SUMMARY")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        icon = "✓" if result else "✗"
        status = "PASSED" if result else "FAILED"
        print(f"{icon} {test_name}: {status}")

    print(f"\n{'='*70}")
    print(f"TOTAL: {passed}/{total} tests passed")
    print(f"{'='*70}\n")

    if passed == total:
        print("🎉 ALL TESTS PASSED! OTP login flows are working correctly.")
        return 0
    else:
        print("⚠️  SOME TESTS FAILED. Please review the output above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
