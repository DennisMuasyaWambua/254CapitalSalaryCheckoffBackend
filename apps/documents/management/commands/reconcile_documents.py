"""
Read-only reconciliation between document storage (S3 or local) and the
Document table.

This command NEVER deletes, moves, or modifies anything. It only reports:

  * ORPHANED files  — objects present in storage with no matching Document row
                      (e.g. rows removed directly in the DB, bypassing the
                      model delete() that would have cleaned up the file).
  * MISSING files   — Document rows whose underlying file is absent from storage
                      (the DB references a file that no longer exists).

Use it to get a safe inventory before deciding what, if anything, to clean up.
Any actual cleanup must be done deliberately and separately — it is intentionally
not implemented here.

Usage:
    python manage.py reconcile_documents
    python manage.py reconcile_documents --prefix documents/2026/06/
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.files.storage import default_storage

from apps.documents.models import Document


class Command(BaseCommand):
    help = 'Read-only report of orphaned/missing document files. Deletes nothing.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--prefix',
            default='documents/',
            help='Storage key prefix to scan (default: documents/).',
        )

    def _list_storage_keys(self, prefix):
        """Return the set of object keys currently in storage under `prefix`.

        Uses boto3 directly for S3 (handles pagination); falls back to walking
        the local FileSystemStorage tree otherwise. Read-only.
        """
        if getattr(settings, 'USE_S3', False):
            import boto3
            client = boto3.client('s3', region_name=settings.AWS_S3_REGION_NAME)
            keys = set()
            token = None
            while True:
                kwargs = {'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Prefix': prefix}
                if token:
                    kwargs['ContinuationToken'] = token
                resp = client.list_objects_v2(**kwargs)
                for obj in resp.get('Contents', []):
                    keys.add(obj['Key'])
                if resp.get('IsTruncated'):
                    token = resp.get('NextContinuationToken')
                else:
                    break
            return keys

        # Local filesystem storage: walk directories under the prefix.
        keys = set()

        def walk(path):
            try:
                dirs, files = default_storage.listdir(path)
            except (FileNotFoundError, NotADirectoryError):
                return
            for f in files:
                keys.add(f'{path}{f}' if path.endswith('/') or not path else f'{path}/{f}')
            for d in dirs:
                walk(f'{path}{d}/' if path.endswith('/') else f'{path}/{d}')

        walk(prefix)
        return keys

    def handle(self, *args, **options):
        prefix = options['prefix']

        storage_keys = self._list_storage_keys(prefix)
        db_keys = set(
            Document.objects.exclude(file='').values_list('file', flat=True)
        )

        orphaned = sorted(storage_keys - db_keys)
        missing = sorted(db_keys - storage_keys)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\nDocument reconciliation (prefix="{prefix}") — READ ONLY, nothing modified\n'
        ))
        self.stdout.write(f'  Files in storage : {len(storage_keys)}')
        self.stdout.write(f'  Rows in database : {len(db_keys)}')
        self.stdout.write(f'  Orphaned files   : {len(orphaned)}')
        self.stdout.write(f'  Missing files    : {len(missing)}\n')

        if orphaned:
            self.stdout.write(self.style.WARNING('\nORPHANED (in storage, no DB row):'))
            for key in orphaned:
                self.stdout.write(f'  - {key}')

        if missing:
            self.stdout.write(self.style.ERROR('\nMISSING (DB row references absent file):'))
            for key in missing:
                doc = Document.objects.filter(file=key).first()
                ident = f' [id={doc.id}, type={doc.document_type}]' if doc else ''
                self.stdout.write(f'  - {key}{ident}')

        if not orphaned and not missing:
            self.stdout.write(self.style.SUCCESS('\nStorage and database are fully consistent.'))

        self.stdout.write(self.style.MIGRATE_HEADING(
            '\nThis command made no changes. Cleanup, if any, must be done separately.\n'
        ))
