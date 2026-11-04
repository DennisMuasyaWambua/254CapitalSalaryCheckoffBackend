"""
Time-limited links to documents stored on local disk.

With S3, a document's file_url is a presigned URL: the link itself is the
credential and expires. Local storage gets the same behaviour here, because
documents are national IDs and payslips and must not sit at a guessable,
permanent public /media/ path. The token is a signed, expiring document id; the
view that serves it needs no login, so <img> and <iframe> tags can load it.
"""

from django.core import signing
from django.urls import reverse

FILE_TOKEN_SALT = 'documents.file-access'
FILE_LINK_LIFETIME_SECONDS = 3600  # matches AWS_QUERYSTRING_EXPIRE for S3


def make_file_token(document):
    return signing.dumps(str(document.pk), salt=FILE_TOKEN_SALT)


def read_file_token(token):
    """Return the document id in a valid, unexpired token, or None."""
    try:
        return signing.loads(token, salt=FILE_TOKEN_SALT, max_age=FILE_LINK_LIFETIME_SECONDS)
    except signing.BadSignature:  # includes SignatureExpired
        return None


def local_file_url(request, document):
    """Absolute, expiring URL for a locally stored document."""
    path = reverse('documents:document-file', kwargs={'token': make_file_token(document)})
    if request is None:
        return path
    url = request.build_absolute_uri(path)
    # TLS ends at nginx, so Django sees plain http. An http:// link would be
    # blocked as mixed content on the https frontend.
    if request.META.get('HTTP_X_FORWARDED_PROTO') == 'https' and url.startswith('http://'):
        url = 'https://' + url[len('http://'):]
    return url
