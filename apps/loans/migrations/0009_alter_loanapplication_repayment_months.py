from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('loans', '0008_loanapplication_interest_method_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='loanapplication',
            name='repayment_months',
            field=models.IntegerField(
                choices=[(1, '1 month'), (2, '2 months'), (3, '3 months'), (4, '4 months'), (5, '5 months'), (6, '6 months'), (7, '7 months'), (8, '8 months'), (9, '9 months'), (10, '10 months'), (11, '11 months'), (12, '12 months')],
                help_text='Number of months for repayment',
            ),
        ),
    ]
