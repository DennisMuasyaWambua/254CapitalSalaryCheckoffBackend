# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('loans', '0005_idempotencylog'),
    ]

    operations = [
        migrations.AddField(
            model_name='loanapplication',
            name='bank_name',
            field=models.CharField(blank=True, help_text='Bank name for disbursement', max_length=100),
        ),
        migrations.AddField(
            model_name='loanapplication',
            name='bank_branch',
            field=models.CharField(blank=True, help_text='Bank branch name', max_length=100),
        ),
        migrations.AddField(
            model_name='loanapplication',
            name='account_number',
            field=models.CharField(blank=True, help_text='Bank account number for disbursement', max_length=50),
        ),
    ]
