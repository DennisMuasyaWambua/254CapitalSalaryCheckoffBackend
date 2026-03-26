# Generated manually for adding bank_branch field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_passwordresettoken'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeeprofile',
            name='bank_branch',
            field=models.CharField(blank=True, help_text='Bank branch name', max_length=100),
        ),
    ]
