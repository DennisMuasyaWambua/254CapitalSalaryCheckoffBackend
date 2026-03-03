"""
Serializers for authentication and user profiles.
"""

from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from decimal import Decimal
from .models import CustomUser, EmployeeProfile, HRProfile
from apps.employers.models import Employer
from common.utils import validate_kenyan_phone, normalize_kenyan_phone, validate_national_id


class EmployeeProfileSerializer(serializers.ModelSerializer):
    """Serializer for employee profile data."""

    employer_name = serializers.CharField(source='employer.name', read_only=True)
    employer_id_display = serializers.UUIDField(source='employer.id', read_only=True)
    employment_type_display = serializers.CharField(source='get_employment_type_display', read_only=True)
    is_loan_eligible = serializers.BooleanField(read_only=True)
    days_until_contract_expiry = serializers.IntegerField(read_only=True)

    class Meta:
        model = EmployeeProfile
        fields = [
            'id', 'employer', 'employer_name', 'employer_id_display',
            'employee_id', 'department', 'employment_type', 'employment_type_display',
            'contract_end_date', 'work_email', 'personal_email', 'residential_location',
            'monthly_gross_salary', 'bank_name', 'bank_account_number', 'mpesa_number',
            'is_loan_eligible', 'days_until_contract_expiry',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_monthly_gross_salary(self, value):
        """Validate salary is positive."""
        if value < Decimal('0.01'):
            raise serializers.ValidationError('Salary must be greater than zero.')
        return value

    def validate(self, attrs):
        """Validate contract end date for contract employees."""
        employment_type = attrs.get('employment_type', getattr(self.instance, 'employment_type', None))
        contract_end_date = attrs.get('contract_end_date', getattr(self.instance, 'contract_end_date', None))

        if employment_type == EmployeeProfile.EmploymentType.CONTRACT and not contract_end_date:
            raise serializers.ValidationError({
                'contract_end_date': 'Contract end date is required for contract employees.'
            })

        return attrs


class HRProfileSerializer(serializers.ModelSerializer):
    """Serializer for HR profile data."""

    employer_name = serializers.CharField(source='employer.name', read_only=True)

    class Meta:
        model = HRProfile
        fields = [
            'id', 'employer', 'employer_name',
            'department', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user data with role-specific profile."""

    employee_profile = EmployeeProfileSerializer(read_only=True)
    hr_profile = HRProfileSerializer(read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'phone_number', 'national_id', 'role', 'is_phone_verified',
            'employee_profile', 'hr_profile', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'role', 'is_phone_verified', 'created_at', 'updated_at']

    def get_full_name(self, obj):
        """Get user's full name."""
        return obj.get_full_name() or ''


class SendOTPSerializer(serializers.Serializer):
    """Serializer for sending OTP to phone number."""

    phone_number = serializers.CharField(max_length=20)

    def validate_phone_number(self, value):
        """Validate and normalize phone number."""
        if not validate_kenyan_phone(value):
            raise serializers.ValidationError(
                'Invalid Kenyan phone number. Use format: +254712345678, 254712345678, or 0712345678'
            )
        return normalize_kenyan_phone(value)


class VerifyOTPSerializer(serializers.Serializer):
    """Serializer for verifying OTP."""

    phone_number = serializers.CharField(max_length=20)
    otp = serializers.CharField(min_length=6, max_length=6)

    def validate_phone_number(self, value):
        """Validate and normalize phone number."""
        if not validate_kenyan_phone(value):
            raise serializers.ValidationError('Invalid Kenyan phone number.')
        return normalize_kenyan_phone(value)

    def validate_otp(self, value):
        """Validate OTP format."""
        if not value.isdigit():
            raise serializers.ValidationError('OTP must contain only digits.')
        return value


class RegisterEmployeeSerializer(serializers.Serializer):
    """
    Serializer for employee registration.

    Requires phone number to be already verified via OTP.
    """

    # Personal info
    phone_number = serializers.CharField(max_length=20)
    national_id = serializers.CharField(max_length=20)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)

    # Employment info
    employer_id = serializers.UUIDField()
    employee_id = serializers.CharField(max_length=50)
    department = serializers.CharField(max_length=100, required=False, allow_blank=True)
    employment_type = serializers.ChoiceField(
        choices=EmployeeProfile.EmploymentType.choices,
        default=EmployeeProfile.EmploymentType.CONFIRMED
    )
    contract_end_date = serializers.DateField(required=False, allow_null=True)
    work_email = serializers.EmailField(required=False, allow_blank=True)
    personal_email = serializers.EmailField(required=False, allow_blank=True)
    residential_location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    monthly_gross_salary = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01')
    )

    # Bank details
    bank_name = serializers.CharField(max_length=100)
    bank_account_number = serializers.CharField(max_length=50)
    mpesa_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_phone_number(self, value):
        """Validate and normalize phone number."""
        if not validate_kenyan_phone(value):
            raise serializers.ValidationError('Invalid Kenyan phone number.')
        normalized = normalize_kenyan_phone(value)

        # Check if phone number already exists
        if CustomUser.objects.filter(phone_number=normalized).exists():
            raise serializers.ValidationError('This phone number is already registered.')

        return normalized

    def validate_national_id(self, value):
        """Validate national ID."""
        if not validate_national_id(value):
            raise serializers.ValidationError('Invalid Kenyan National ID format.')

        # Check if national ID already exists
        if CustomUser.objects.filter(national_id=value).exists():
            raise serializers.ValidationError('This National ID is already registered.')

        return value

    def validate_employer_id(self, value):
        """Validate employer exists and is active."""
        try:
            employer = Employer.objects.get(id=value)
            if not employer.is_active:
                raise serializers.ValidationError('This employer is not currently active.')
            return value
        except Employer.DoesNotExist:
            raise serializers.ValidationError('Invalid employer.')

    def validate_mpesa_number(self, value):
        """Validate M-Pesa number if provided."""
        if value:
            if not validate_kenyan_phone(value):
                raise serializers.ValidationError('Invalid M-Pesa number.')
            return normalize_kenyan_phone(value)
        return value

    def validate(self, attrs):
        """Additional validation."""
        # Check unique employee_id per employer
        employer_id = attrs.get('employer_id')
        employee_id = attrs.get('employee_id')

        if EmployeeProfile.objects.filter(
            employer_id=employer_id,
            employee_id=employee_id
        ).exists():
            raise serializers.ValidationError({
                'employee_id': 'This employee ID already exists for this employer.'
            })

        # Validate contract end date for contract employees
        employment_type = attrs.get('employment_type', EmployeeProfile.EmploymentType.CONFIRMED)
        contract_end_date = attrs.get('contract_end_date')

        if employment_type == EmployeeProfile.EmploymentType.CONTRACT and not contract_end_date:
            raise serializers.ValidationError({
                'contract_end_date': 'Contract end date is required for contract employees.'
            })

        return attrs

    def create(self, validated_data):
        """Create user and employee profile."""
        # Extract employer_id and profile data
        employer_id = validated_data.pop('employer_id')
        employee_id = validated_data.pop('employee_id')
        department = validated_data.pop('department', '')
        employment_type = validated_data.pop('employment_type', EmployeeProfile.EmploymentType.CONFIRMED)
        contract_end_date = validated_data.pop('contract_end_date', None)
        work_email = validated_data.pop('work_email', '')
        personal_email = validated_data.pop('personal_email', '')
        residential_location = validated_data.pop('residential_location', '')
        monthly_gross_salary = validated_data.pop('monthly_gross_salary')
        bank_name = validated_data.pop('bank_name')
        bank_account_number = validated_data.pop('bank_account_number')
        mpesa_number = validated_data.pop('mpesa_number', '')

        # Create user
        user = CustomUser.objects.create(
            username=validated_data['phone_number'],
            phone_number=validated_data['phone_number'],
            national_id=validated_data['national_id'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            email=validated_data.get('email', ''),
            role='employee',
            is_phone_verified=True,
        )

        # Create employee profile
        EmployeeProfile.objects.create(
            user=user,
            employer_id=employer_id,
            employee_id=employee_id,
            department=department,
            employment_type=employment_type,
            contract_end_date=contract_end_date,
            work_email=work_email,
            personal_email=personal_email,
            residential_location=residential_location,
            monthly_gross_salary=monthly_gross_salary,
            bank_name=bank_name,
            bank_account_number=bank_account_number,
            mpesa_number=mpesa_number,
        )

        return user


class HRLoginSerializer(serializers.Serializer):
    """Serializer for HR manager email/password login."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        """Validate credentials and role."""
        email = attrs.get('email')
        password = attrs.get('password')

        # Authenticate
        user = authenticate(username=email, password=password)

        if not user:
            raise serializers.ValidationError('Invalid email or password.')

        if user.role != 'hr_manager':
            raise serializers.ValidationError('Invalid credentials for HR login.')

        if not user.is_active:
            raise serializers.ValidationError('This account is inactive.')

        attrs['user'] = user
        return attrs


class AdminLoginSerializer(serializers.Serializer):
    """Serializer for admin email/password login."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        """Validate credentials and role."""
        email = attrs.get('email')
        password = attrs.get('password')

        # Authenticate
        user = authenticate(username=email, password=password)

        if not user:
            raise serializers.ValidationError('Invalid email or password.')

        if user.role != 'admin':
            raise serializers.ValidationError('Invalid credentials for admin login.')

        if not user.is_active:
            raise serializers.ValidationError('This account is inactive.')

        attrs['user'] = user
        return attrs


class AdminVerify2FASerializer(serializers.Serializer):
    """Serializer for verifying admin 2FA TOTP code."""

    temp_token = serializers.CharField()
    totp_code = serializers.CharField(min_length=6, max_length=6)

    def validate_totp_code(self, value):
        """Validate TOTP code format."""
        if not value.isdigit():
            raise serializers.ValidationError('TOTP code must contain only digits.')
        return value


class VerifyLoginOTPSerializer(serializers.Serializer):
    """
    Serializer for verifying OTP sent after login (for HR/Admin).

    Used in the OTP-after-login flow where credentials are verified first,
    then an OTP is sent to the user's phone, and finally the OTP must be
    verified before issuing tokens.
    """

    temp_token = serializers.CharField(help_text="Temporary token from login step")
    otp = serializers.CharField(min_length=6, max_length=6, help_text="6-digit OTP code")

    def validate_otp(self, value):
        """Validate OTP format."""
        if not value.isdigit():
            raise serializers.ValidationError('OTP must contain only digits.')
        return value


class UpdateProfileSerializer(serializers.Serializer):
    """Serializer for updating user profile."""

    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False)

    # Employee-specific fields
    department = serializers.CharField(max_length=100, required=False)
    employment_type = serializers.ChoiceField(
        choices=EmployeeProfile.EmploymentType.choices,
        required=False
    )
    contract_end_date = serializers.DateField(required=False, allow_null=True)
    work_email = serializers.EmailField(required=False, allow_blank=True)
    personal_email = serializers.EmailField(required=False, allow_blank=True)
    residential_location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    bank_name = serializers.CharField(max_length=100, required=False)
    bank_account_number = serializers.CharField(max_length=50, required=False)
    mpesa_number = serializers.CharField(max_length=20, required=False)

    def validate_mpesa_number(self, value):
        """Validate M-Pesa number if provided."""
        if value:
            if not validate_kenyan_phone(value):
                raise serializers.ValidationError('Invalid M-Pesa number.')
            return normalize_kenyan_phone(value)
        return value

    def update(self, instance, validated_data):
        """Update user and profile fields."""
        # Update user fields
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.email = validated_data.get('email', instance.email)
        instance.save()

        # Update profile fields if employee
        if instance.role == 'employee' and hasattr(instance, 'employee_profile'):
            profile = instance.employee_profile
            profile.department = validated_data.get('department', profile.department)
            profile.employment_type = validated_data.get('employment_type', profile.employment_type)
            profile.contract_end_date = validated_data.get('contract_end_date', profile.contract_end_date)
            profile.work_email = validated_data.get('work_email', profile.work_email)
            profile.personal_email = validated_data.get('personal_email', profile.personal_email)
            profile.residential_location = validated_data.get('residential_location', profile.residential_location)
            profile.bank_name = validated_data.get('bank_name', profile.bank_name)
            profile.bank_account_number = validated_data.get(
                'bank_account_number', profile.bank_account_number
            )
            profile.mpesa_number = validated_data.get('mpesa_number', profile.mpesa_number)
            profile.save()

        # Update profile fields if HR
        elif instance.role == 'hr_manager' and hasattr(instance, 'hr_profile'):
            profile = instance.hr_profile
            profile.department = validated_data.get('department', profile.department)
            profile.save()

        return instance
