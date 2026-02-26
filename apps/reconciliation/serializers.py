"""
Serializers for reconciliation and remittance.
"""

from rest_framework import serializers
from decimal import Decimal
from .models import Remittance, ReconciliationRecord
from apps.loans.serializers import LoanApplicationListSerializer


class ReconciliationRecordSerializer(serializers.ModelSerializer):
    """Serializer for reconciliation records."""

    loan_application = LoanApplicationListSerializer(read_only=True)
    variance = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    variance_percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = ReconciliationRecord
        fields = [
            'id', 'remittance', 'loan_application', 'expected_amount',
            'received_amount', 'is_matched', 'variance',
            'variance_percentage', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class RemittanceListSerializer(serializers.ModelSerializer):
    """Serializer for listing remittances."""

    employer_name = serializers.CharField(source='employer.name', read_only=True)
    submitted_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    period_display = serializers.CharField(read_only=True)
    reconciliation_status = serializers.CharField(read_only=True)

    class Meta:
        model = Remittance
        fields = [
            'id', 'employer', 'employer_name', 'submitted_by',
            'submitted_by_name', 'period_month', 'period_year',
            'period_display', 'total_amount', 'status',
            'status_display', 'reconciliation_status',
            'created_at', 'confirmed_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_submitted_by_name(self, obj):
        """Get submitter's name."""
        if obj.submitted_by:
            return obj.submitted_by.get_full_name() or obj.submitted_by.username
        return None


class RemittanceDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for remittance with reconciliation records."""

    employer_name = serializers.CharField(source='employer.name', read_only=True)
    submitted_by_name = serializers.SerializerMethodField()
    confirmed_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    period_display = serializers.CharField(read_only=True)
    reconciliation_status = serializers.CharField(read_only=True)
    reconciliation_records = ReconciliationRecordSerializer(many=True, read_only=True)
    proof_document_url = serializers.SerializerMethodField()

    class Meta:
        model = Remittance
        fields = [
            'id', 'employer', 'employer_name', 'submitted_by',
            'submitted_by_name', 'period_month', 'period_year',
            'period_display', 'total_amount', 'proof_document',
            'proof_document_url', 'status', 'status_display',
            'confirmed_by', 'confirmed_by_name', 'confirmed_at',
            'notes', 'reconciliation_status', 'reconciliation_records',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'submitted_by', 'confirmed_by', 'confirmed_at',
            'created_at', 'updated_at'
        ]

    def get_submitted_by_name(self, obj):
        """Get submitter's name."""
        if obj.submitted_by:
            return obj.submitted_by.get_full_name() or obj.submitted_by.username
        return None

    def get_confirmed_by_name(self, obj):
        """Get confirmer's name."""
        if obj.confirmed_by:
            return obj.confirmed_by.get_full_name() or obj.confirmed_by.username
        return None

    def get_proof_document_url(self, obj):
        """Get proof document URL."""
        if obj.proof_document:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.proof_document.url)
            return obj.proof_document.url
        return None


class RemittanceCreateSerializer(serializers.Serializer):
    """Serializer for creating a remittance submission."""

    employer_id = serializers.UUIDField()
    period_month = serializers.IntegerField(min_value=1, max_value=12)
    period_year = serializers.IntegerField(min_value=2020, max_value=2050)
    total_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01')
    )
    proof_document = serializers.FileField()
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000
    )

    def validate_proof_document(self, value):
        """Validate proof document."""
        # Check file size (max 10 MB)
        max_size = 10 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError(
                f'File size must not exceed 10 MB. '
                f'Your file is {value.size / (1024 * 1024):.1f} MB.'
            )

        # Check file extension
        import os
        ext = os.path.splitext(value.name)[1].lower()
        allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
        if ext not in allowed_extensions:
            raise serializers.ValidationError(
                f'File type not allowed. Allowed types: {", ".join(allowed_extensions)}'
            )

        return value

    def validate(self, attrs):
        """Validate employer and period uniqueness."""
        from apps.employers.models import Employer

        # Validate employer exists
        employer_id = attrs['employer_id']
        try:
            employer = Employer.objects.get(id=employer_id)
            attrs['_employer'] = employer
        except Employer.DoesNotExist:
            raise serializers.ValidationError({'employer_id': 'Invalid employer ID.'})

        # Check for duplicate submission (same employer + period)
        period_month = attrs['period_month']
        period_year = attrs['period_year']

        if Remittance.objects.filter(
            employer_id=employer_id,
            period_month=period_month,
            period_year=period_year
        ).exists():
            raise serializers.ValidationError(
                f'A remittance for {period_month}/{period_year} has already been submitted for this employer.'
            )

        # Validate period is not in the future
        from datetime import date
        today = date.today()
        if period_year > today.year or (period_year == today.year and period_month > today.month):
            raise serializers.ValidationError('Period cannot be in the future.')

        return attrs


class ReconciliationRunSerializer(serializers.Serializer):
    """Serializer for running reconciliation on a remittance."""

    remittance_id = serializers.UUIDField()

    def validate_remittance_id(self, value):
        """Validate remittance exists."""
        try:
            remittance = Remittance.objects.get(id=value)
            return value
        except Remittance.DoesNotExist:
            raise serializers.ValidationError('Invalid remittance ID.')


class RemittanceConfirmSerializer(serializers.Serializer):
    """Serializer for admin confirming a remittance."""

    status = serializers.ChoiceField(choices=['confirmed', 'disputed'])
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000
    )


class ReconciliationRecordUpdateSerializer(serializers.Serializer):
    """Serializer for updating a reconciliation record."""

    received_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.00')
    )
    is_matched = serializers.BooleanField()
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000
    )
