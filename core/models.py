import uuid
from django.db import models
from django.contrib.auth.models import User


class Developer(models.Model):
    """
    Extends Django's built-in User with GitHub-specific identity data.
    Kept separate from User so auth mechanics (login, sessions, password)
    stay decoupled from GitHub-specific concerns.

    Uses a UUID primary key since this ID may be exposed in API responses
    or URLs — a sequential integer would let anyone guess how many
    developers exist or enumerate other users' profiles.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='developer_profile')
    github_username = models.CharField(max_length=100, unique=True)
    github_id = models.CharField(max_length=50, unique=True)
    access_token_encrypted = models.TextField(
        help_text="GitHub OAuth access token, encrypted before storage."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.github_username


class Repository(models.Model):
    """
    A GitHub repo connected by a Developer for triage.

    Uses a UUID primary key for the same reason as Developer — repository
    IDs will appear in dashboard URLs and API responses, and a sequential
    integer would leak how many repos are connected in total.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        Developer, on_delete=models.CASCADE, related_name='repositories',
        null=True, blank=True,
        help_text='Null until a Developer authenticates and claims this repo. May be discovered via webhook first.'
    )
    full_name = models.CharField(max_length=255, help_text="e.g. 'khilav/grocerybot'")
    github_repo_id = models.CharField(max_length=50, unique=True)
    webhook_active = models.BooleanField(default=False)
    connected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "repositories"

    def __str__(self):
        return self.full_name


class PullRequest(models.Model):
    """
    A single PR tracked from a connected repository. Kept on an integer
    primary key — PRs are always accessed through their parent Repository
    (e.g. /repositories/<uuid>/pulls/<int>/), so the ID itself is never
    exposed in a way that would leak information on its own.
    """

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        MERGED = 'merged', 'Merged'
        CLOSED = 'closed', 'Closed'

    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='pull_requests')
    github_pr_number = models.IntegerField()
    title = models.CharField(max_length=500)
    author_username = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    diff_summary = models.TextField(blank=True, help_text="Raw diff stats or summary, not full diff text.")
    opened_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('repository', 'github_pr_number')
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.repository.full_name} #{self.github_pr_number}"


class ReviewerProfile(models.Model):
    """
    Tracks which file patterns a developer tends to own within a specific
    repository, derived from git blame. Powers the reviewer-match agent.
    """
    developer = models.ForeignKey(Developer, on_delete=models.CASCADE, related_name='reviewer_profiles')
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='reviewer_profiles')
    owned_file_patterns = models.JSONField(
        default=list,
        help_text="List of file path patterns this reviewer frequently edits, e.g. ['*.py', 'frontend/*']"
    )

    class Meta:
        unique_together = ('developer', 'repository')

    def __str__(self):
        return f"{self.developer.github_username} @ {self.repository.full_name}"


class TriageResult(models.Model):
    """
    The agent pipeline's structured output for a single PR. Kept separate
    from PullRequest (rather than extra columns on it) so re-triaging in
    the future doesn't require restructuring this table.
    """

    class RiskLevel(models.TextChoices):
        TRIVIAL = 'trivial', 'Trivial'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'

    pull_request = models.OneToOneField(PullRequest, on_delete=models.CASCADE, related_name='triage_result')
    suggested_reviewer = models.ForeignKey(
        ReviewerProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='suggested_for'
    )
    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices)
    summary = models.TextField(help_text="Plain-English summary of what the diff does.")
    tests_missing = models.BooleanField(default=False)
    confidence = models.FloatField(help_text="Agent's self-reported confidence, 0.0 to 1.0.")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Triage for {self.pull_request} — {self.risk_level}"


class Feedback(models.Model):
    """
    Human feedback on whether the agent's triage was correct. This is the
    accuracy-tracking loop referenced in the project's design.
    """
    pull_request = models.ForeignKey(PullRequest, on_delete=models.CASCADE, related_name='feedback_entries')
    given_by = models.ForeignKey(Developer, on_delete=models.CASCADE, related_name='feedback_given')
    agent_was_correct = models.BooleanField()
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback on {self.pull_request} by {self.given_by.github_username}"
