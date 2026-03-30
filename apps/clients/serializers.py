"""
Serializers for client management.
"""

from rest_framework import serializers
from .models import ExistingClient
from apps.employers.models import Employer


class ExistingClientSerializer(serializers.ModelSerializer):
    """Serializer for ExistingClient model."""

    employer_name = serializers.CharField(source='employer.name', read_only=True)
    payment_progress = serializers.DecimalField(
        source='payment_progress_percentage',
        max_digits=5,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = ExistingClient
        fields = [
            'id',
            'full_name',
            'national_id',
            'mobile',
            'email',
            'employer',
            'employer_name',
            'employee_id',
            'loan_amount',
            'interest_rate',
            'start_date',
            'repayment_period',
            'disbursement_date',
            'disbursement_method',
            'total_due',
            'monthly_deduction',
            'amount_paid',
            'outstanding_balance',
            'loan_status',
            'approval_status',
            'entered_by',
            'rejection_reason',
            'payment_progress',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'total_due',
            'monthly_deduction',
            'outstanding_balance',
            'created_at',
            'updated_at',
            'payment_progress',
        ]

    def validate_employer(self, value):
        """Validate that employer exists and is active."""
        if not value.is_active:
            raise serializers.ValidationError("This employer is not active.")
        return value

    def validate_national_id(self, value):
        """Validate national ID format."""
        if not value.isdigit():
            raise serializers.ValidationError("National ID must contain only digits.")
        if len(value) < 7 or len(value) > 10:
            raise serializers.ValidationError("National ID must be between 7 and 10 digits.")
        return value

    def validate_mobile(self, value):
        """Validate and normalize mobile number format."""
        # Remove any spaces or dashes
        cleaned = value.replace(' ', '').replace('-', '').replace('+', '')

        # Strip leading zeros
        cleaned = cleaned.lstrip('0')

        # If it starts with 7 or 1 (Kenyan mobile prefixes), add 254
        if cleaned.startswith('7') or cleaned.startswith('1'):
            cleaned = '254' + cleaned
        # If it already starts with 254, keep it
        elif not cleaned.startswith('254'):
            raise serializers.ValidationError("Mobile number must be a valid Kenyan number.")

        # Validate length (254 + 9 digits = 12 digits total)
        if len(cleaned) != 12:
            raise serializers.ValidationError("Mobile number must be in format 254XXXXXXXXX (12 digits).")

        # Validate all digits
        if not cleaned.isdigit():
            raise serializers.ValidationError("Mobile number must contain only digits.")

        return cleaned

    def validate_repayment_period(self, value):
        """Validate repayment period."""
        if value < 1:
            raise serializers.ValidationError("Repayment period must be at least 1 month.")
        if value > 36:
            raise serializers.ValidationError("Repayment period cannot exceed 36 months.")
        return value

    def validate(self, attrs):
        """Validate the entire object."""
        # Ensure disbursement date is after or equal to start date
        if 'disbursement_date' in attrs and 'start_date' in attrs:
            if attrs['disbursement_date'] < attrs['start_date']:
                raise serializers.ValidationError({
                    'disbursement_date': 'Disbursement date cannot be before start date.'
                })

        return attrs


class ExistingClientBulkUploadSerializer(serializers.Serializer):
    """Serializer for bulk upload validation."""

    file = serializers.FileField(
        help_text='Excel or CSV file containing client records'
    )

    def validate_file(self, value):
        """Validate uploaded file."""
        # Check file extension
        allowed_extensions = ['.xlsx', '.xls', '.csv']
        file_name = value.name.lower()

        if not any(file_name.endswith(ext) for ext in allowed_extensions):
            raise serializers.ValidationError(
                f"Invalid file format. Allowed formats: {', '.join(allowed_extensions)}"
            )

        # Check file size (max 10MB)
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("File size cannot exceed 10MB.")

        return value


class ExistingClientApprovalSerializer(serializers.Serializer):
    """Serializer for client approval/rejection."""

    rejection_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text='Reason for rejection (required if rejecting)'
    )


class BulkApprovalSerializer(serializers.Serializer):
    """Serializer for bulk approval of clients."""

    client_ids = serializers.ListField(
        child=serializers.UUIDField(),
        help_text='List of client IDs to approve'
    )

    def validate_client_ids(self, value):
        """Validate that all client IDs exist and are pending."""
        if not value:
            raise serializers.ValidationError("At least one client ID is required.")

        existing_clients = ExistingClient.objects.filter(id__in=value)

        if existing_clients.count() != len(value):
            raise serializers.ValidationError("Some client IDs are invalid.")

        non_pending = existing_clients.exclude(approval_status='pending')
        if non_pending.exists():
            raise serializers.ValidationError(
                f"{non_pending.count()} client(s) are not in pending status."
            )

        return value
