# Generated migration to remove HR approval statuses
from django.db import migrations, models


def migrate_hr_statuses(apps, schema_editor):
    """
    Migrate existing loans from HR approval statuses to new workflow.
    - under_review_hr -> submitted
    - under_review_admin -> submitted
    """
    LoanApplication = apps.get_model('loans', 'LoanApplication')

    # Update loans in under_review_hr status to submitted
    updated_hr = LoanApplication.objects.filter(
        status='under_review_hr'
    ).update(status='submitted')

    # Update loans in under_review_admin status to submitted
    updated_admin = LoanApplication.objects.filter(
        status='under_review_admin'
    ).update(status='submitted')

    if updated_hr or updated_admin:
        print(f"Migration complete: {updated_hr} 'under_review_hr' and {updated_admin} 'under_review_admin' loans updated to 'submitted'")


class Migration(migrations.Migration):

    dependencies = [
        ('loans', '0003_manualpayment'),
    ]

    operations = [
        # First run the data migration
        migrations.RunPython(migrate_hr_statuses, reverse_code=migrations.RunPython.noop),

        # Then update the model choices (this will be reflected in the model file)
        migrations.AlterField(
            model_name='loanapplication',
            name='status',
            field=models.CharField(
                max_length=30,
                choices=[
                    ('submitted', 'Submitted'),
                    ('approved', 'Approved'),
                    ('declined', 'Declined'),
                    ('disbursed', 'Disbursed'),
                ],
                default='submitted',
                db_index=True
            ),
        ),
    ]
