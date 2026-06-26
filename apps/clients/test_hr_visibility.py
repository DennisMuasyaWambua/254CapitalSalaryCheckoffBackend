"""
Tests for Enhancement 2: HR visibility of bulk-uploaded (existing) clients.

Regression guard for the bug where HR users saw no bulk-uploaded clients
because the queryset checked role == 'hr' (real value: 'hr_manager') and
user.employer (HR's employer lives on user.hr_profile.employer).
"""

from decimal import Decimal
from datetime import date

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.accounts.models import CustomUser, HRProfile
from apps.employers.models import Employer
from apps.clients.models import ExistingClient
from apps.clients.views import ExistingClientViewSet


def make_employer(name, reg):
    return Employer.objects.create(
        name=name,
        registration_number=reg,
        address='Nairobi',
        hr_contact_name='HR Contact',
        hr_contact_email=f'contact@{reg}.com',
        hr_contact_phone='0712345678',
        interest_method='flat',
        interest_rate=Decimal('0.05'),
    )


def make_client(employer, name, nid):
    return ExistingClient.objects.create(
        full_name=name,
        national_id=nid,
        mobile='0700000000',
        employer=employer,
        loan_amount=Decimal('100000'),
        interest_rate=Decimal('0.05'),
        start_date=date(2026, 1, 1),
        repayment_period=6,
        disbursement_date=date(2026, 1, 5),
        disbursement_method='mpesa',
        total_due=Decimal('130000'),
        monthly_deduction=Decimal('21666.67'),
        outstanding_balance=Decimal('130000'),
        loan_status='Active',
        approval_status='approved',
    )


class HRClientVisibilityTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

        self.employer_a = make_employer('Employer A', 'REGA')
        self.employer_b = make_employer('Employer B', 'REGB')

        self.client_a = make_client(self.employer_a, 'Alice A', 'IDA1')
        self.client_b = make_client(self.employer_b, 'Bob B', 'IDB1')

        # HR user for employer A
        self.hr_user = CustomUser.objects.create(
            email='hr-a@example.com',
            username='hr_a',
            role=CustomUser.Role.HR_MANAGER,
            phone_number='0711111111',
            first_name='Helen',
            last_name='Resource',
        )
        HRProfile.objects.create(user=self.hr_user, employer=self.employer_a)

        # Admin user
        self.admin_user = CustomUser.objects.create(
            email='admin@example.com',
            username='admin1',
            role=CustomUser.Role.ADMIN,
            phone_number='0733333333',
            first_name='Adam',
            last_name='Min',
        )

        # HR user with no profile
        self.hr_no_profile = CustomUser.objects.create(
            email='hr-orphan@example.com',
            username='hr_orphan',
            role=CustomUser.Role.HR_MANAGER,
            phone_number='0744444444',
            first_name='No',
            last_name='Profile',
        )

    def _queryset_for(self, user):
        request = self.factory.get('/api/v1/clients/')
        request.user = user
        view = ExistingClientViewSet()
        view.request = request
        view.kwargs = {}
        view.format_kwarg = None
        return view.get_queryset()

    def test_hr_sees_only_their_employer_clients(self):
        qs = self._queryset_for(self.hr_user)
        ids = set(qs.values_list('id', flat=True))
        self.assertIn(self.client_a.id, ids)
        self.assertNotIn(self.client_b.id, ids)

    def test_admin_sees_all_clients(self):
        qs = self._queryset_for(self.admin_user)
        ids = set(qs.values_list('id', flat=True))
        self.assertIn(self.client_a.id, ids)
        self.assertIn(self.client_b.id, ids)

    def test_hr_without_profile_sees_nothing(self):
        qs = self._queryset_for(self.hr_no_profile)
        self.assertEqual(qs.count(), 0)
