"""
Serializers for loan applications and repayment.
"""

from rest_framework import serializers
from decimal import Decimal
from django.conf import settings
from .models import LoanApplication, LoanStatusHistory, RepaymentSchedule, ManualPayment
from apps.accounts.serializers import UserSerializer
from apps.employers.serializers import EmployerListSerializer


class LoanStatusHistorySerializer(serializers.ModelSerializer):
    """Serializer for loan status history entries."""

    actor_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = LoanStatusHistory
        fields = [
            'id', 'status', 'status_display', 'actor', 'actor_name',
            'comment', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_actor_name(self, obj):
        """Get actor's full name."""
        if obj.actor:
            return obj.actor.get_full_name() or obj.actor.username
        return 'System'


class RepaymentScheduleSerializer(serializers.ModelSerializer):
    """Serializer for repayment schedule entries."""

    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = RepaymentSchedule
        fields = [
            'id', 'installment_number', 'due_date', 'amount',
            'running_balance', 'is_first_deduction', 'is_paid',
            'paid_date', 'is_overdue'
        ]
        read_only_fields = ['id', 'is_overdue']


class LoanApplicationListSerializer(serializers.ModelSerializer):
    """Serializer for listing loan applications (minimal fields)."""

    employee_name = serializers.SerializerMethodField()
    employer_name = serializers.CharField(source='employer.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    department = serializers.SerializerMethodField()
    bank_name = serializers.SerializerMethodField()
    bank_branch = serializers.SerializerMethodField()
    bank_account_number = serializers.SerializerMethodField()
    mpesa_number = serializers.SerializerMethodField()

    class Meta:
        model = LoanApplication
        fields = [
            'id', 'application_number', 'employee', 'employee_name',
            'employer', 'employer_name', 'principal_amount',
            'total_repayment', 'monthly_deduction', 'repayment_months',
            'status', 'status_display', 'created_at', 'disbursement_date',
            'department', 'disbursement_method', 'disbursement_reference',
            'bank_name', 'bank_branch', 'bank_account_number', 'mpesa_number'
        ]
        read_only_fields = ['id', 'application_number', 'created_at']

    def get_employee_name(self, obj):
        """Get employee's full name."""
        return obj.employee.get_full_name() or obj.employee.phone_number

    def get_department(self, obj):
        """Get employee's department from profile."""
        if hasattr(obj.employee, 'employee_profile'):
            return obj.employee.employee_profile.department or 'N/A'
        return 'N/A'

    def get_bank_name(self, obj):
        """Get employee's bank name from profile."""
        if hasattr(obj.employee, 'employee_profile'):
            return obj.employee.employee_profile.bank_name or ''
        return ''

    def get_bank_branch(self, obj):
        """Get employee's bank branch from profile."""
        if hasattr(obj.employee, 'employee_profile'):
            return obj.employee.employee_profile.bank_branch or ''
        return ''

    def get_bank_account_number(self, obj):
        """Get employee's bank account number from profile."""
        if hasattr(obj.employee, 'employee_profile'):
            return obj.employee.employee_profile.bank_account_number or ''
        return ''

    def get_mpesa_number(self, obj):
        """Get employee's M-Pesa number from profile."""
        if hasattr(obj.employee, 'employee_profile'):
            return obj.employee.employee_profile.mpesa_number or obj.employee.phone_number
        return obj.employee.phone_number


class LoanApplicationDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for loan application with timeline and schedule."""

    employee = UserSerializer(read_only=True)
    employer = EmployerListSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    disbursement_method_display = serializers.CharField(
        source='get_disbursement_method_display',
        read_only=True
    )
    status_history = LoanStatusHistorySerializer(many=True, read_only=True)
    repayment_schedule = RepaymentScheduleSerializer(many=True, read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    can_be_edited = serializers.BooleanField(read_only=True)
    total_paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    outstanding_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    # Disbursement details from employee profile
    bank_name = serializers.SerializerMethodField()
    bank_branch = serializers.SerializerMethodField()
    account_number = serializers.SerializerMethodField()
    mpesa_number = serializers.SerializerMethodField()

    class Meta:
        model = LoanApplication
        fields = [
            'id', 'application_number', 'employee', 'employer',
            'principal_amount', 'interest_rate', 'repayment_months',
            'total_repayment', 'monthly_deduction', 'purpose',
            'status', 'status_display', 'disbursement_date',
            'first_deduction_date', 'disbursement_method',
            'disbursement_method_display', 'disbursement_reference',
            'terms_accepted', 'terms_accepted_at',
            'created_at', 'updated_at', 'is_active', 'can_be_edited',
            'total_paid', 'outstanding_balance',
            'status_history', 'repayment_schedule',
            'bank_name', 'bank_branch', 'account_number', 'mpesa_number'
        ]
        read_only_fields = [
            'id', 'application_number', 'employee', 'employer',
            'total_repayment', 'monthly_deduction', 'status',
            'disbursement_date', 'first_deduction_date',
            'disbursement_method', 'disbursement_reference',
            'terms_accepted_at', 'created_at', 'updated_at'
        ]

    def get_bank_name(self, obj):
        """Get employee's bank name from profile."""
        if hasattr(obj.employee, 'employee_profile'):
            return obj.employee.employee_profile.bank_name or ''
        return ''

    def get_bank_branch(self, obj):
        """Get employee's bank branch from profile."""
        if hasattr(obj.employee, 'employee_profile'):
            return obj.employee.employee_profile.bank_branch or ''
        return ''

    def get_account_number(self, obj):
        """Get employee's bank account number from profile."""
        if hasattr(obj.employee, 'employee_profile'):
            return obj.employee.employee_profile.bank_account_number or ''
        return ''

    def get_mpesa_number(self, obj):
        """Get employee's M-Pesa number from profile."""
        if hasattr(obj.employee, 'employee_profile'):
            return obj.employee.employee_profile.mpesa_number or obj.employee.phone_number
        return obj.employee.phone_number


class LoanApplicationCreateSerializer(serializers.Serializer):
    """Serializer for creating a new loan application."""

    principal_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal(str(settings.LOAN_MIN_AMOUNT)),
        max_value=Decimal(str(settings.LOAN_MAX_AMOUNT))
    )
    repayment_months = serializers.ChoiceField(
        choices=settings.LOAN_REPAYMENT_TERMS
    )
    purpose = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True
    )
    terms_accepted = serializers.BooleanField(
        required=True,
        help_text='Confirmation that terms and conditions have been accepted'
    )

    def validate_principal_amount(self, value):
        """Validate principal amount is a multiple of 100."""
        if value % 100 != 0:
            raise serializers.ValidationError('Amount must be a multiple of 100.')
        return value

    def validate_terms_accepted(self, value):
        """Validate that terms and conditions have been accepted."""
        if not value:
            raise serializers.ValidationError(
                'You must accept the terms and conditions to proceed with the loan application.'
            )
        return value

    def validate(self, attrs):
        """Additional validation for loan affordability and eligibility."""
        # Get employee profile from context
        request = self.context.get('request')
        if request and hasattr(request.user, 'employee_profile'):
            employee_profile = request.user.employee_profile

            # Check if employee is confirmed staff (eligibility requirement)
            if not employee_profile.is_loan_eligible:
                raise serializers.ValidationError(
                    'Loan facility is only available to confirmed staff members. '
                    'Contract employees are not eligible for this facility.'
                )

            # Import here to avoid circular import
            from .services import calculate_flat_interest, calculate_loan_affordability

            # Calculate monthly deduction
            calc = calculate_flat_interest(
                attrs['principal_amount'],
                Decimal(str(settings.LOAN_INTEREST_RATE_FLAT)),
                attrs['repayment_months']
            )

            # Check affordability
            affordability = calculate_loan_affordability(
                employee_profile.monthly_gross_salary,
                attrs['principal_amount'],
                calc['monthly_deduction']
            )

            # Store calculation results for later use
            attrs['_calculation'] = calc
            attrs['_affordability'] = affordability

            # Warning (not blocking) if not affordable
            if not affordability['is_affordable']:
                # We don't block, but we could add a warning
                pass

        return attrs


class LoanCalculatorSerializer(serializers.Serializer):
    """Serializer for loan calculator endpoint."""

    principal = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal(str(settings.LOAN_MIN_AMOUNT)),
        max_value=Decimal(str(settings.LOAN_MAX_AMOUNT))
    )
    months = serializers.ChoiceField(choices=settings.LOAN_REPAYMENT_TERMS)
    calculation_type = serializers.ChoiceField(
        choices=['flat', 'amortized'],
        default='flat'
    )
    annual_rate = serializers.DecimalField(
        max_digits=5,
        decimal_places=4,
        required=False,
        default=Decimal(str(settings.LOAN_INTEREST_RATE_FLAT))
    )


class HRReviewSerializer(serializers.Serializer):
    """Serializer for HR review action (approve/decline)."""

    action = serializers.ChoiceField(choices=['approve', 'decline'])
    comment = serializers.CharField(min_length=10, max_length=1000)

    def validate_comment(self, value):
        """Ensure comment is meaningful."""
        if len(value.strip()) < 10:
            raise serializers.ValidationError('Comment must be at least 10 characters long.')
        return value.strip()


class BatchApprovalSerializer(serializers.Serializer):
    """Serializer for batch approval/decline by HR."""

    application_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=50
    )
    action = serializers.ChoiceField(choices=['approve', 'decline'])
    comment = serializers.CharField(min_length=10, max_length=1000)

    def validate_comment(self, value):
        """Ensure comment is meaningful."""
        if len(value.strip()) < 10:
            raise serializers.ValidationError('Comment must be at least 10 characters long.')
        return value.strip()


class AdminCreditAssessmentSerializer(serializers.Serializer):
    """Serializer for admin credit assessment action."""

    action = serializers.ChoiceField(choices=['approve', 'decline'])
    comment = serializers.CharField(min_length=10, max_length=1000)
    credit_score_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000
    )

    def validate_comment(self, value):
        """Ensure comment is meaningful."""
        if len(value.strip()) < 10:
            raise serializers.ValidationError('Comment must be at least 10 characters long.')
        return value.strip()


class AdminDisbursementSerializer(serializers.Serializer):
    """Serializer for recording loan disbursement."""

    disbursement_date = serializers.DateField()
    disbursement_method = serializers.ChoiceField(
        choices=LoanApplication.DisbursementMethod.choices
    )
    disbursement_reference = serializers.CharField(max_length=100)

    def validate_disbursement_date(self, value):
        """Validate disbursement date is not in the future."""
        from django.utils import timezone
        if value > timezone.now().date():
            raise serializers.ValidationError('Disbursement date cannot be in the future.')
        return value

    def validate_disbursement_reference(self, value):
        """Ensure reference is provided."""
        if not value.strip():
            raise serializers.ValidationError('Disbursement reference is required.')
        return value.strip()


class LoanApplicationUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating loan application (employee only, submitted status)."""

    class Meta:
        model = LoanApplication
        fields = ['principal_amount', 'repayment_months', 'purpose']

    def validate_principal_amount(self, value):
        """Validate principal amount."""
        if value < Decimal(str(settings.LOAN_MIN_AMOUNT)):
            raise serializers.ValidationError(f'Minimum loan amount is KES {settings.LOAN_MIN_AMOUNT:,.2f}')
        if value > Decimal(str(settings.LOAN_MAX_AMOUNT)):
            raise serializers.ValidationError(f'Maximum loan amount is KES {settings.LOAN_MAX_AMOUNT:,.2f}')
        if value % 100 != 0:
            raise serializers.ValidationError('Amount must be a multiple of 100.')
        return value

    def validate(self, attrs):
        """Check if application can be updated."""
        instance = self.instance
        if instance.status != LoanApplication.Status.SUBMITTED:
            raise serializers.ValidationError('Only submitted applications can be updated.')
        return attrs

    def update(self, instance, validated_data):
        """Update application and recalculate repayment."""
        # Import here to avoid circular import
        from .services import calculate_flat_interest

        # Update fields
        instance.principal_amount = validated_data.get('principal_amount', instance.principal_amount)
        instance.repayment_months = validated_data.get('repayment_months', instance.repayment_months)
        instance.purpose = validated_data.get('purpose', instance.purpose)

        # Recalculate repayment
        calc = calculate_flat_interest(
            instance.principal_amount,
            instance.interest_rate,
            instance.repayment_months
        )
        instance.total_repayment = calc['total_repayment']
        instance.monthly_deduction = calc['monthly_deduction']

        instance.save()
        return instance


class ManualPaymentSerializer(serializers.ModelSerializer):
    """Serializer for manual payment records."""

    loan_number = serializers.CharField(source='loan.application_number', read_only=True)
    employee_name = serializers.CharField(source='loan.employee.get_full_name', read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.get_full_name', read_only=True)

    class Meta:
        model = ManualPayment
        fields = [
            'id',
            'loan',
            'loan_number',
            'employee_name',
            'payment_date',
            'amount_received',
            'payment_method',
            'reference_number',
            'notes',
            'early_payment_discount_applied',
            'discount_amount',
            'recorded_by',
            'recorded_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'recorded_by', 'created_at', 'updated_at']

    def validate_amount_received(self, value):
        """Validate payment amount."""
        if value <= 0:
            raise serializers.ValidationError("Payment amount must be greater than 0.")
        return value

    def validate(self, attrs):
        """Validate the entire payment record."""
        loan = attrs.get('loan')

        if loan and loan.status != LoanApplication.Status.DISBURSED:
            raise serializers.ValidationError({
                'loan': 'Can only record payments for disbursed loans.'
            })

        return attrs


class LoanSearchSerializer(serializers.Serializer):
    """Serializer for loan search."""

    q = serializers.CharField(
        required=True,
        help_text='Search query (employee name, ID, mobile, or application number)'
    )


class EarlyPaymentDiscountSerializer(serializers.Serializer):
    """Serializer for early payment discount calculation."""

    loan_id = serializers.UUIDField(required=True)
    payment_date = serializers.DateField(required=True)

    def validate_loan_id(self, value):
        """Validate that loan exists."""
        from .models import LoanApplication
        try:
            loan = LoanApplication.objects.get(id=value)
            if loan.status != LoanApplication.Status.DISBURSED:
                raise serializers.ValidationError("Loan must be disbursed.")
        except LoanApplication.DoesNotExist:
            raise serializers.ValidationError("Loan not found.")
        return value


class RecordPaymentSerializer(serializers.Serializer):
    """Serializer for recording manual payments."""

    loan_id = serializers.UUIDField(required=True)
    payment_date = serializers.DateField(required=True)
    amount_received = serializers.DecimalField(max_digits=12, decimal_places=2, required=True)
    payment_method = serializers.ChoiceField(
        choices=['mpesa', 'bank', 'cash', 'cheque'],
        required=True
    )
    reference_number = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    apply_early_payment_discount = serializers.BooleanField(default=False)

    def validate_amount_received(self, value):
        """Validate payment amount."""
        if value <= 0:
            raise serializers.ValidationError("Payment amount must be greater than 0.")
        return value
