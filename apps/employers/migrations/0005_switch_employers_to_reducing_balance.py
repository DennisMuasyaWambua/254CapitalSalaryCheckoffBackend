"""
Switch all existing employers from flat interest to 5% reducing balance.

Per the client directive (Sept 2026), the interest calculation for all
companies changes from a 5% flat rate to a 5% reducing-balance ("Equal Total
Payments") rate. This only affects how NEW loans are computed going forward;
already-disbursed loans keep the figures/schedule they were created with.
"""

from decimal import Decimal
from django.db import migrations


def switch_to_reducing_balance(apps, schema_editor):
    Employer = apps.get_model('employers', 'Employer')
    Employer.objects.all().update(
        interest_method='reducing_balance',
        interest_rate=Decimal('0.0500'),
    )


def revert_to_flat(apps, schema_editor):
    Employer = apps.get_model('employers', 'Employer')
    Employer.objects.all().update(interest_method='flat')


class Migration(migrations.Migration):

    dependencies = [
        ('employers', '0004_alter_employer_interest_method_and_more'),
    ]

    operations = [
        migrations.RunPython(switch_to_reducing_balance, revert_to_flat),
    ]
