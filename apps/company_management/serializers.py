"""
Serializers for Company Management API.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import Organization, Role, OrganizationUser, AuditLog
import secrets
import string

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    """Serializer for Organization model."""

    active_users_count = serializers.IntegerField(read_only=True)
    active_roles_count = serializers.IntegerField(read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'address', 'contact_email', 'contact_phone',
            'tax_id', 'is_active', 'created_at', 'updated_at',
            'created_by', 'created_by_name', 'active_users_count',
            'active_roles_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']

    def get_created_by_name(self, obj):
        """Get full name of creator."""
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return None


class RoleSerializer(serializers.ModelSerializer):
    """Serializer for Role model."""

    organization_name = serializers.CharField(source='organization.name', read_only=True)
    assigned_users_count = serializers.IntegerField(read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            'id', 'organization', 'organization_name', 'name', 'description',
            'can_view_loan_application', 'can_approve_loan_application',
            'can_decline_loan_application', 'is_active', 'created_at',
            'updated_at', 'assigned_users_count', 'permissions'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_permissions(self, obj):
        """Get dict of permissions."""
        return {
            'can_view_loan_application': obj.can_view_loan_application,
            'can_approve_loan_application': obj.can_approve_loan_application,
            'can_decline_loan_application': obj.can_decline_loan_application,
        }

    def validate(self, attrs):
        """Validate that role has at least one permission."""
        can_view = attrs.get('can_view_loan_application', False)
        can_approve = attrs.get('can_approve_loan_application', False)
        can_decline = attrs.get('can_decline_loan_application', False)

        # Warning if no permissions, but allow it (observer role)
        if not (can_view or can_approve or can_decline):
            pass  # Allow roles with no permissions

        return attrs


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user serializer for nested representations."""

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone_number']
        read_only_fields = fields


class OrganizationUserSerializer(serializers.ModelSerializer):
    """Serializer for OrganizationUser model."""

    user_details = UserBasicSerializer(source='user', read_only=True)
    role_details = RoleSerializer(source='role', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationUser
        fields = [
            'id', 'organization', 'organization_name', 'user', 'user_details',
            'role', 'role_details', 'is_active', 'force_password_change',
            'password_changed_at', 'last_login_at', 'created_at', 'updated_at',
            'permissions'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'password_changed_at', 'last_login_at'
        ]

    def get_permissions(self, obj):
        """Get list of permissions for this user."""
        return obj.get_permissions()

    def validate(self, attrs):
        """Validate that role belongs to the organization."""
        role = attrs.get('role')
        organization = attrs.get('organization')

        if role and organization:
            if role.organization_id != organization.id:
                raise serializers.ValidationError(
                    f'Role {role.name} does not belong to organization {organization.name}'
                )

        return attrs


class CreateOrganizationUserSerializer(serializers.Serializer):
    """
    Serializer for creating a new organization user with system-generated password.
    """

    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(max_length=150, required=True)
    last_name = serializers.CharField(max_length=150, required=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    role_id = serializers.UUIDField(required=True)

    def validate_email(self, value):
        """Validate email is unique."""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('User with this email already exists.')
        return value

    def validate_role_id(self, value):
        """Validate role exists and belongs to organization."""
        organization_id = self.context.get('organization_id')
        try:
            role = Role.objects.get(id=value, organization_id=organization_id, is_active=True)
            return role
        except Role.DoesNotExist:
            raise serializers.ValidationError(
                'Role not found or does not belong to this organization.'
            )

    def generate_secure_password(self, length=14):
        """Generate cryptographically secure password."""
        uppercase = string.ascii_uppercase
        lowercase = string.ascii_lowercase
        digits = string.digits
        special = '!@#$%^&*()_+-='

        # Ensure at least one of each character type
        password_chars = [
            secrets.choice(uppercase),
            secrets.choice(lowercase),
            secrets.choice(digits),
            secrets.choice(special)
        ]

        # Fill remaining length with random choices
        all_chars = uppercase + lowercase + digits + special
        for _ in range(length - 4):
            password_chars.append(secrets.choice(all_chars))

        # Shuffle to avoid predictable pattern
        import random
        random.SystemRandom().shuffle(password_chars)

        return ''.join(password_chars)

    def create(self, validated_data):
        """
        Create a new user with organization membership and role assignment.

        Returns:
            tuple: (organization_user, plain_password)
        """
        # Extract role from validated data (it was validated and converted to Role object)
        role = validated_data.pop('role_id')
        organization_id = self.context['organization_id']
        created_by = self.context['request'].user

        # Generate secure password
        plain_password = self.generate_secure_password()

        # Create user
        user = User.objects.create_user(
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone_number=validated_data.get('phone_number', ''),
            username=validated_data['email'],  # Use email as username
            password=plain_password,
            role='employee'  # Default role for organization users
        )

        # Create organization membership
        org_user = OrganizationUser.objects.create(
            organization_id=organization_id,
            user=user,
            role=role,
            is_active=True,
            force_password_change=True,
            created_by=created_by
        )

        return org_user, plain_password


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change."""

    current_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_password = serializers.CharField(required=True, write_only=True)

    def validate_current_password(self, value):
        """Validate current password is correct."""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value

    def validate_new_password(self, value):
        """Validate new password meets requirements."""
        try:
            validate_password(value, user=self.context['request'].user)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate(self, attrs):
        """Validate passwords match and new password is different."""
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': 'Passwords do not match.'
            })

        if attrs['current_password'] == attrs['new_password']:
            raise serializers.ValidationError({
                'new_password': 'New password must be different from current password.'
            })

        return attrs

    def save(self):
        """Change the user's password."""
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()

        # Update organization user if exists
        try:
            org_user = OrganizationUser.objects.get(user=user, is_active=True)
            org_user.force_password_change = False
            org_user.password_changed_at = timezone.now()
            org_user.save()
        except OrganizationUser.DoesNotExist:
            pass

        return user


class AuditLogSerializer(serializers.ModelSerializer):
    """Serializer for AuditLog model."""

    user_name = serializers.SerializerMethodField()
    target_user_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'event_type', 'user', 'user_name', 'target_user',
            'target_user_name', 'organization', 'organization_name',
            'target_resource_type', 'target_resource_id', 'ip_address',
            'user_agent', 'result', 'error_message', 'metadata', 'created_at'
        ]
        read_only_fields = fields

    def get_user_name(self, obj):
        """Get full name of actor."""
        if obj.user:
            return obj.user.get_full_name() or obj.user.email
        return 'System'

    def get_target_user_name(self, obj):
        """Get full name of target user."""
        if obj.target_user:
            return obj.target_user.get_full_name() or obj.target_user.email
        return None
