"""
Celery tasks for processing GitHub webhook events asynchronously.
The webhook view's only job is to log the raw event and return fast;
all the real work (parsing the payload, creating/updating PullRequest
rows) happens here, off the request/response cycle.
"""

from datetime import datetime
from celery import shared_task
from django.utils import timezone

from core.models import PullRequest
from integrations.models import WebhookEvent


@shared_task
def process_webhook_event(webhook_event_id):
    """
    Process a single WebhookEvent: parse its payload and create or
    update the corresponding PullRequest row. Updates the event's
    processing_status to reflect the outcome, success or failure.
    """
    try:
        event = WebhookEvent.objects.get(id=webhook_event_id)
    except WebhookEvent.DoesNotExist:
        return f"WebhookEvent {webhook_event_id} not found"

    if event.event_type != 'pull_request':
        event.processing_status = WebhookEvent.ProcessingStatus.IGNORED
        event.processed_at = timezone.now()
        event.save()
        return f"Ignored event type: {event.event_type}"

    try:
        payload = event.raw_payload
        pr_data = payload['pull_request']

        pull_request, _ = PullRequest.objects.update_or_create(
            repository=event.repository,
            github_pr_number=pr_data['number'],
            defaults={
                'title': pr_data['title'],
                'author_username': pr_data['user']['login'],
                'status': PullRequest.Status.MERGED if pr_data.get('merged') else (
                    PullRequest.Status.CLOSED if pr_data['state'] == 'closed'
                    else PullRequest.Status.OPEN
                ),
                'opened_at': datetime.fromisoformat(
                    pr_data['created_at'].replace('Z', '+00:00')
                ),
            },
        )

        event.pull_request = pull_request
        event.processing_status = WebhookEvent.ProcessingStatus.PROCESSED
        event.processed_at = timezone.now()
        event.save()

        return f"Processed PR #{pull_request.github_pr_number}: {pull_request.title}"

    except (KeyError, ValueError) as e:
        event.processing_status = WebhookEvent.ProcessingStatus.FAILED
        event.error_message = str(e)
        event.processed_at = timezone.now()
        event.save()
        return f"Failed to process event {webhook_event_id}: {e}"
