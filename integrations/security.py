"""
GitHub webhook signature verification.

GitHub signs every webhook payload with HMAC-SHA256 using the secret
configured on both sides (GitHub's webhook settings and our .env).
Without this check, anyone who discovers our webhook URL could send
fake events. This function proves a request actually came from GitHub.
"""

import hashlib
import hmac
from django.conf import settings


def verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    Verify the X-Hub-Signature-256 header GitHub sends with every webhook.

    payload_body: the raw, unparsed request body (bytes, not JSON-decoded)
    signature_header: the value of the X-Hub-Signature-256 header,
                       formatted as 'sha256=<hex digest>'
    """
    if not signature_header or not signature_header.startswith('sha256='):
        return False

    expected_signature = hmac.new(
        key=settings.GITHUB_WEBHOOK_SECRET.encode(),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    received_signature = signature_header.removeprefix('sha256=')

    # hmac.compare_digest prevents timing attacks — a regular ==
    # comparison can leak information about how many characters matched
    # via response time, which an attacker could exploit to guess the
    # correct signature byte by byte.
    return hmac.compare_digest(expected_signature, received_signature)
