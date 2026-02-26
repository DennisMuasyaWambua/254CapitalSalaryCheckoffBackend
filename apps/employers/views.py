"""
Employer management APIViews.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from .models import Employer
from .serializers import (
    EmployerListSerializer, EmployerDetailSerializer,
    EmployerCreateSerializer, EmployerUpdateSerializer
)
from apps.accounts.permissions import IsAdmin, IsHROrAdmin
from common.pagination import StandardPagination
from common.utils import get_client_ip
from apps.audit.models import AuditLog
import logging

logger = logging.getLogger(__name__)


class EmployerListView(APIView):
    """
    GET /api/v1/employers/
    List all active employers.

    Supports:
    - ?search= — search by name
    - Pagination

    Used for registration dropdown (employees) and browsing (HR/Admin).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List employers."""
        # Get all active employers
        employers = Employer.objects.filter(is_active=True)

        # Apply search filter
        search = request.query_params.get('search', '').strip()
        if search:
            employers = employers.filter(
                Q(name__icontains=search) |
                Q(registration_number__icontains=search)
            )

        # Order by name
        employers = employers.order_by('name')

        # Paginate
        paginator = StandardPagination()
        page = paginator.paginate_queryset(employers, request)

        serializer = EmployerListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class EmployerCreateView(APIView):
    """
    POST /api/v1/employers/
    Onboard a new employer (Admin only).
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        """Create new employer."""
        serializer = EmployerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create employer
        employer = serializer.save(onboarded_by=request.user)

        # Log onboarding
        AuditLog.log(
            action=f'Employer onboarded: {employer.name}',
            actor=request.user,
            target_type='Employer',
            target_id=employer.id,
            metadata={'employer_name': employer.name},
            ip_address=get_client_ip(request)
        )

        logger.info(f'Employer onboarded: {employer.name} by {request.user.id}')

        return Response(
            EmployerDetailSerializer(employer).data,
            status=status.HTTP_201_CREATED
        )


class EmployerDetailView(APIView):
    """
    GET  /api/v1/employers/<uuid:pk>/  — Get employer details
    PUT  /api/v1/employers/<uuid:pk>/  — Update employer (Admin only)
    """

    permission_classes = [IsAuthenticated, IsHROrAdmin]

    def get_object(self, pk, user):
        """Get employer with permission check."""
        try:
            employer = Employer.objects.get(pk=pk)

            # HR can only view their own employer
            if user.role == 'hr_manager':
                hr_profile = getattr(user, 'hr_profile', None)
                if not hr_profile or hr_profile.employer != employer:
                    return None

            return employer

        except Employer.DoesNotExist:
            return None

    def get(self, request, pk):
        """Get employer details."""
        employer = self.get_object(pk, request.user)

        if not employer:
            return Response(
                {'detail': 'Employer not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = EmployerDetailSerializer(employer)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        """Update employer (Admin only)."""
        # Check admin permission
        if request.user.role != 'admin':
            return Response(
                {'detail': 'Only admins can update employer information.'},
                status=status.HTTP_403_FORBIDDEN
            )

        employer = self.get_object(pk, request.user)

        if not employer:
            return Response(
                {'detail': 'Employer not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = EmployerUpdateSerializer(employer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_employer = serializer.save()

        # Log update
        AuditLog.log(
            action=f'Employer updated: {employer.name}',
            actor=request.user,
            target_type='Employer',
            target_id=employer.id,
            metadata={'fields_updated': list(serializer.validated_data.keys())},
            ip_address=get_client_ip(request)
        )

        logger.info(f'Employer updated: {employer.name} by {request.user.id}')

        return Response(
            EmployerDetailSerializer(updated_employer).data,
            status=status.HTTP_200_OK
        )
