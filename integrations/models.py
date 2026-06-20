from django.db import models
from core.models import Repository, PullRequest


class WebhookEvent(models.Model):
    """
    Raw log of every webhook GitHub sends us, stored before processing.
    This is the replay/audit layer: if processing fails or has a bug,
    we can inspect or reprocess the exact payload without needing
    GitHub to resend it.
    """

    class ProcessingStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSED = 'processed', 'Processed'
        FAILED = 'failed', 'Failed'
        IGNORED = 'ignored', 'Ignored'

    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name='webhook_events'
    )
    pull_request = models.ForeignKey(
        PullRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='webhook_events',
        help_text="Set once this event has been linked to a specific PR."
    )
    event_type = models.CharField(
        max_length=50, help_text="GitHub event type, e.g. 'pull_request', 'push'."
    )
    delivery_id = models.CharField(
        max_length=100, unique=True,
        help_text="GitHub's X-GitHub-Delivery header, used to detect duplicate deliveries."
    )
    raw_payload = models.JSONField(help_text="The full webhook payload, exactly as received.")
    processing_status = models.CharField(
        max_length=10, choices=ProcessingStatus.choices, default=ProcessingStatus.PENDING
    )
    error_message = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-received_at']

    def __str__(self):
        return f"{self.event_type} for {self.repository.full_name} ({self.processing_status})"