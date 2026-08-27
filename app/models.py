from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TaskStatus(str, Enum):
    backlog = "backlog"
    approved = "approved"
    running = "running"
    needs_human_review = "needs_human_review"
    pr_open = "pr_open"
    failed = "failed"
    cancelled = "cancelled"


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    needs_human_review = "needs_human_review"
    pr_open = "pr_open"
    failed = "failed"
    cancelled = "cancelled"


class RepositoryRequest(BaseModel):
    path: Path = Field(description="Absolute path to an already-cloned repository.")


class ProjectAnalysis(BaseModel):
    root: str
    languages: dict[str, int]
    manifests: list[str]
    readme_present: bool
    test_directories: list[str]
    todo_items: list[str]
    source_files: int
    ignored_files: int
    detected_tools: list[str]
    summary: str


class Task(BaseModel):
    id: str
    repository_id: int | None = None
    title: str
    description: str
    priority: int = Field(ge=1, le=5)
    risk: RiskLevel
    affected_files: list[str] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    source: str
    requires_human_approval: bool = True
    status: TaskStatus = TaskStatus.backlog
    approved_at: str | None = None


class TaskPlan(BaseModel):
    analysis: ProjectAnalysis
    tasks: list[Task]
    repository_id: int | None = None


class RepositorySummary(BaseModel):
    id: int
    path: str
    created_at: str


class GitHubRepo(BaseModel):
    """A repo from the logged-in user's own GitHub account (GET /user/repos), shown so they
    can pick one to clone and analyze -- distinct from RepositorySummary, which is a repo
    already analyzed and persisted locally."""

    name: str
    full_name: str
    description: str | None
    html_url: str
    clone_url: str
    default_branch: str
    private: bool
    fork: bool
    updated_at: str


class TestOutcome(BaseModel):
    tool: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


class ReviewResult(BaseModel):
    approved: bool
    summary: str
    concerns: list[str] = Field(default_factory=list)
    risk: RiskLevel


class Run(BaseModel):
    id: str
    task_id: str
    status: RunStatus
    triggered_by: str | None = None  # None (started manually) or "autopilot"
    owner_login: str | None = None  # whose AI settings this run resolves against -- a public
    # GitHub login, not a secret, so it's fine to expose alongside everything else here.
    branch_name: str | None = None
    worktree_path: str | None = None
    base_branch: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    pr_url: str | None = None
    error_message: str | None = None
    commit_sha: str | None = None
    review_result: ReviewResult | None = None
    test_results: list[TestOutcome] = Field(default_factory=list)
    # A snapshot of which AI configuration actually executed this run, captured once at
    # start time -- so activity history stays accurate even after the user later changes
    # their AI settings. Never the API key itself.
    ai_provider: str | None = None
    ai_model: str | None = None


class RunEvent(BaseModel):
    id: int
    run_id: str
    ts: str
    phase: str
    level: str
    message: str
    data: dict | None = None


class WebhookAccepted(BaseModel):
    event: str
    delivery: str | None = None
    accepted: bool = True


class AutonomyLevel(str, Enum):
    conservative = "conservative"  # analyze + propose only -- a human must approve before coding starts
    balanced = "balanced"  # auto-approves and runs one matching task per scheduled slot, drafts a PR
    autopilot = "autopilot"  # same as balanced, but ranks/selects among matches rather than just filtering


class FocusArea(str, Enum):
    bug_fixes = "bug_fixes"
    tests = "tests"
    documentation = "documentation"
    code_cleanup = "code_cleanup"
    dependencies = "dependencies"
    security = "security"
    performance = "performance"
    major_features = "major_features"


class ScheduleType(str, Enum):
    daily = "daily"
    weekdays = "weekdays"
    weekly = "weekly"
    custom = "custom"


class AutopilotPlanStatus(str, Enum):
    active = "active"
    paused = "paused"
    cancelled = "cancelled"


class ScheduledRunStatus(str, Enum):
    scheduled = "scheduled"  # in the future, not yet due
    waiting = "waiting"  # due now, briefly held back by a concurrency/dedup conflict
    running = "running"
    completed = "completed"  # a real run finished (PR opened, or awaiting human review)
    failed = "failed"
    skipped = "skipped"  # no matching work found, or blocked by pause/cap -- not an error
    cancelled = "cancelled"


class AutopilotPlanRequest(BaseModel):
    """What the user configures on the Autopilot page. A repository has at most one plan --
    submitting this again replaces the existing plan's settings and regenerates any
    not-yet-started scheduled runs, leaving history (running/completed/failed/cancelled)
    alone."""

    schedule_type: ScheduleType
    run_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="24h HH:MM, in `timezone`.")
    timezone: str = "UTC"
    weekly_day: int | None = Field(default=None, ge=0, le=6, description="0=Monday..6=Sunday, only for 'weekly'.")
    custom_days: list[int] = Field(default_factory=list, description="0=Monday..6=Sunday, only for 'custom'.")
    max_runs_per_day: int = Field(default=1, ge=1, le=5)
    focus_areas: list[FocusArea] = Field(default_factory=list)
    autonomy_level: AutonomyLevel = AutonomyLevel.balanced


class AutopilotPlan(BaseModel):
    id: str
    repository_id: int
    owner_login: str
    status: AutopilotPlanStatus
    schedule_type: ScheduleType
    run_time: str
    timezone: str
    weekly_day: int | None
    custom_days: list[int]
    max_runs_per_day: int
    focus_areas: list[FocusArea]
    autonomy_level: AutonomyLevel
    created_at: str
    updated_at: str


class ScheduledRun(BaseModel):
    id: str
    plan_id: str
    repository_id: int
    scheduled_at: str
    status: ScheduledRunStatus
    task_id: str | None = None
    run_id: str | None = None
    result_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class AutopilotState(BaseModel):
    """Everything the Autopilot page needs in one call."""

    plan: AutopilotPlan | None
    upcoming: list[ScheduledRun]
    recent: list[ScheduledRun]


class AIProviderName(str, Enum):
    ollama = "ollama"
    anthropic = "anthropic"
    gemini = "gemini"


class UserAISettings(BaseModel):
    """One user's persisted AI configuration -- internal shape only, used between the
    database and the provider resolver. Never returned from an API endpoint as-is: the
    encrypted_api_key field must never reach the frontend, see AIConfigResponse below."""

    owner_login: str
    provider: AIProviderName
    model: str
    encrypted_api_key: str | None = None
    endpoint: str | None = None  # Ollama's base URL; unused by hosted providers
    enabled: bool = True
    created_at: str
    updated_at: str


class AIConfigRequest(BaseModel):
    """What the Settings page submits to save or test an AI configuration. api_key is
    write-only: omit it on an update to keep the previously-saved key (e.g. only changing
    the model), matching how the frontend never has the real key to resend."""

    provider: AIProviderName
    model: str
    api_key: str | None = None
    endpoint: str | None = None


class AIConfigResponse(BaseModel):
    """The only shape of AI configuration ever sent to the frontend -- safe metadata about
    what's configured, never the credential itself."""

    provider: AIProviderName
    model: str
    endpoint: str | None = None
    configured: bool
    enabled: bool
    updated_at: str | None = None


class ConnectionTestResponse(BaseModel):
    ok: bool
    message: str
