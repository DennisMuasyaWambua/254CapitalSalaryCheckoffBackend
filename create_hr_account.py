"""
Script to create HR account for production use.
Creates employer and HR user with profile.
"""

from django.contrib.auth import get_user_model
from apps.employers.models import Employer
from apps.accounts.models import HRProfile

User = get_user_model()

# HR account details
email = "wamuasya23@gmail.com"
password = "muasya@123"
phone = "0720523299"
first_name = "Dennis"
last_name = "Wamuasya"

# Normalize phone number
if phone.startswith('0'):
    phone = '+254' + phone[1:]

print(f"Creating HR account for: {email}")
print(f"Phone: {phone}")

# Check if employer exists, if not create one
employer = Employer.objects.first()
if not employer:
    print("\nNo employer found. Creating default employer...")
    employer = Employer.objects.create(
        name="254 Capital Demo Company",
        registration_number="PVT-2024-001",
        address="Nairobi, Kenya",
        payroll_cycle_day=25,
        hr_contact_name=f"{first_name} {last_name}",
        hr_contact_email=email,
        hr_contact_phone=phone,
        is_active=True
    )
    print(f"✓ Created employer: {employer.name} (ID: {employer.id})")
else:
    print(f"\n✓ Using existing employer: {employer.name} (ID: {employer.id})")

# Check if user already exists
existing_user = User.objects.filter(email=email).first()
if existing_user:
    print(f"\n✗ User with email {email} already exists!")
    print(f"  User ID: {existing_user.id}")
    print(f"  Role: {existing_user.role}")
    exit(1)

existing_phone = User.objects.filter(phone_number=phone).first()
if existing_phone:
    print(f"\n✗ User with phone {phone} already exists!")
    print(f"  User ID: {existing_phone.id}")
    print(f"  Email: {existing_phone.email}")
    exit(1)

# Create HR user
print("\nCreating HR user account...")
hr_user = User.objects.create_user(
    username=email,  # Use email as username for HR
    email=email,
    password=password,
    phone_number=phone,
    first_name=first_name,
    last_name=last_name,
    role=User.Role.HR_MANAGER,
    is_active=True,
    is_staff=True,
    is_phone_verified=True
)
print(f"✓ Created user: {hr_user.get_full_name()} (ID: {hr_user.id})")

# Create HR profile
print("\nCreating HR profile...")
hr_profile = HRProfile.objects.create(
    user=hr_user,
    employer=employer,
    department="Human Resources"
)
print(f"✓ Created HR profile (ID: {hr_profile.id})")

print("\n" + "="*60)
print("HR ACCOUNT CREATED SUCCESSFULLY!")
print("="*60)
print(f"Email:    {email}")
print(f"Password: {password}")
print(f"Phone:    {phone}")
print(f"Employer: {employer.name}")
print(f"Role:     HR Manager")
print("="*60)
print("\nYou can now log in with these credentials.")
