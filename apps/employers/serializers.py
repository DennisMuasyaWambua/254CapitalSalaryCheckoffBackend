"""
Serializers for employer management.
"""

from rest_framework import serializers
from .models import Employer
from common.utils import validate_kenyan_phone, normalize_kenyan_phone


class EmployerListSerializer(serializers.ModelSerializer):
    """Serializer for listing employers (minimal fields for dropdown)."""

    total_employees = serializers.IntegerField(read_only=True)
    active_loans_count = serializers.IntegerField(read_only=True)
    pending_applications_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Employer
        fields = [
            'id', 'name', 'registration_number', 'address',
            'payroll_cycle_day', 'hr_contact_name', 'hr_contact_email',
            'hr_contact_phone', 'is_active', 'onboarded_by', 'onboarded_at',
            'updated_at', 'total_employees', 'active_loans_count',
            'pending_applications_count'
        ]


class EmployerDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for employer data."""

    onboarded_by_name = serializers.SerializerMethodField()
    total_employees = serializers.IntegerField(read_only=True)
    active_loans_count = serializers.IntegerField(read_only=True)
    pending_applications_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Employer
        fields = [
            'id', 'name', 'registration_number', 'address',
            'payroll_cycle_day', 'hr_contact_name', 'hr_contact_email',
            'hr_contact_phone', 'is_active', 'onboarded_by', 'onboarded_by_name',
            'onboarded_at', 'updated_at', 'total_employees',
            'active_loans_count', 'pending_applications_count'
        ]
        read_only_fields = ['id', 'onboarded_by', 'onboarded_at', 'updated_at']

    def get_onboarded_by_name(self, obj):
        """Get name of admin who onboarded this employer."""
        if obj.onboarded_by:
            return obj.onboarded_by.get_full_name() or obj.onboarded_by.username
        return None


class EmployerCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/onboarding a new employer."""

    class Meta:
        model = Employer
        fields = [
            'name', 'registration_number', 'address', 'payroll_cycle_day',
            'hr_contact_name', 'hr_contact_email', 'hr_contact_phone'
        ]

    def validate_hr_contact_phone(self, value):
        """Validate and normalize HR contact phone."""
        if not validate_kenyan_phone(value):
            raise serializers.ValidationError('Invalid Kenyan phone number.')
        return normalize_kenyan_phone(value)

    def validate_payroll_cycle_day(self, value):
        """Validate payroll cycle day is between 1 and 31."""
        if not (1 <= value <= 31):
            raise serializers.ValidationError('Payroll cycle day must be between 1 and 31.')
        return value

    def validate_name(self, value):
        """Validate employer name is unique."""
        if Employer.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError('An employer with this name already exists.')
        return value

    def validate_registration_number(self, value):
        """Validate registration number is unique."""
        if Employer.objects.filter(registration_number=value).exists():
            raise serializers.ValidationError('An employer with this registration number already exists.')
        return value


class EmployerUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating employer data."""

    class Meta:
        model = Employer
        fields = [
            'name', 'address', 'payroll_cycle_day',
            'hr_contact_name', 'hr_contact_email', 'hr_contact_phone',
            'is_active'
        ]

    def validate_hr_contact_phone(self, value):
        """Validate and normalize HR contact phone."""
        if not validate_kenyan_phone(value):
            raise serializers.ValidationError('Invalid Kenyan phone number.')
        return normalize_kenyan_phone(value)

    def validate_payroll_cycle_day(self, value):
        """Validate payroll cycle day is between 1 and 31."""
        if not (1 <= value <= 31):
            raise serializers.ValidationError('Payroll cycle day must be between 1 and 31.')
        return value
