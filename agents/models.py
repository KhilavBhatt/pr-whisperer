from django.db import models
from core.models import PullRequest


class AgentRun(models.Model):
    """
    One execution of the full triage pipeline for a PR. Separate from
    core.TriageResult, which stores only the final answer — this stores
    the execution record, so a PR can have a history of runs over time
    even though it only has one current TriageResult.
    """

    class Status(models.TextChoices):
        RUNNING = 'running', 'Running'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Failed'

    pull_request = models.ForeignKey(
        PullRequest, on_delete=models.CASCADE, related_name='agent_runs'
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    model_used = models.CharField(max_length=50, help_text="e.g. 'gemini-2.0-flash'")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_latency_seconds = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Run for {self.pull_request} ({self.status})"


class AgentStep(models.Model):
    """
    A single step within an AgentRun. Captures the prompt, raw response,
    timing, and token usage for that step — this is what makes the
    pipeline observable and debuggable, not just a black-box LLM call.
    """

    class StepName(models.TextChoices):
        SUMMARIZE = 'summarize', 'Summarize diff'
        CLASSIFY_RISK = 'classify_risk', 'Classify risk'
        MATCH_REVIEWER = 'match_reviewer', 'Match reviewer'
        CHECK_TESTS = 'check_tests', 'Check tests included'

    agent_run = models.ForeignKey(
        AgentRun, on_delete=models.CASCADE, related_name='steps'
    )
    step_name = models.CharField(max_length=20, choices=StepName.choices)
    step_order = models.PositiveSmallIntegerField(
        help_text="Execution order within the run, supports parallel steps sharing an order."
    )
    prompt_sent = models.TextField(blank=True, help_text="Empty for non-LLM steps like check_tests.")
    raw_response = models.TextField(blank=True)
    success = models.BooleanField(default=True)
    tokens_used = models.PositiveIntegerField(null=True, blank=True)
    latency_seconds = models.FloatField(null=True, blank=True)
    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['agent_run', 'step_order']

    def __str__(self):
        return f"{self.step_name} (run {self.agent_run_id})"
