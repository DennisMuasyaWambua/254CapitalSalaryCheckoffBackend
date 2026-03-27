# Generated migration for IdempotencyLog model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('loans', '0004_remove_hr_approval_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='IdempotencyLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('idempotency_key', models.CharField(db_index=True, help_text='Unique key provided by client to ensure idempotency', max_length=100, unique=True)),
                ('endpoint', models.CharField(help_text='API endpoint that was called', max_length=255)),
                ('request_hash', models.CharField(help_text='SHA256 hash of request body for verification', max_length=64)),
                ('response_status', models.IntegerField(help_text='HTTP status code of the response')),
                ('response_body', models.JSONField(help_text='JSON response body')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(help_text='When this idempotency record expires')),
                ('admin', models.ForeignKey(help_text='Admin who made the request', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='idempotency_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Idempotency Log',
                'verbose_name_plural': 'Idempotency Logs',
                'db_table': 'idempotency_logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='idempotencylog',
            index=models.Index(fields=['idempotency_key'], name='idempotency_idempot_a5f8c3_idx'),
        ),
        migrations.AddIndex(
            model_name='idempotencylog',
            index=models.Index(fields=['expires_at'], name='idempotency_expires_2f7d91_idx'),
        ),
    ]
