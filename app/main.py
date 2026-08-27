from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel

from app.agents.backlog_agent import generate_tasks
from app.ai.crypto import decrypt_secret, encrypt_secret
from app.ai.factory import build_provider, resolve_provider, validate_model_choice
from app.ai.providers.ollama_provider import OllamaProvider
from app.ai.types import AIProviderError, ProviderUnavailableError
from app.auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    STATE_COOKIE,
    STATE_MAX_AGE_SECONDS,
    AuthError,
    SessionUser,
    build_authorize_url,
    create_session_cookie,
    exchange_code_for_user,
    generate_state,
    read_session_cookie,
)
from app.autopilot import compute_schedule
from app.autopilot_scheduler import AutopilotScheduler
from app.config import Settings
from app.db import Database
from app.events import EventBus
from app.git_ops import GitOpsError, clone_repository, pull_latest
from app.github_client import GitHubClientError, list_user_repos
from app.models import (
    AIConfigRequest,
    AIConfigResponse,
    AutopilotPlanRequest,
    AutopilotPlanStatus,
    AutopilotState,
    ConnectionTestResponse,
    GitHubRepo,
    ProjectAnalysis,
    RepositoryRequest,
    RepositorySummary,
    Run,
    RunEvent,
    ScheduledRun,
    ScheduledRunStatus,
    Task,
    TaskPlan,
    WebhookAccepted,
)
from app.orchestrator import RunOrchestrator
from app.planner import TaskPlanner
from app.repository import RepositoryAnalyzer

settings = Settings.from_environment()
analyzer = RepositoryAnalyzer()
planner = TaskPlanner()
db = Database(settings.db_path)
event_bus = EventBus()
orchestrator = RunOrchestrator(db, settings, event_bus)
autopilot_scheduler = AutopilotScheduler(db, settings, orchestrator, tick_seconds=settings.autopilot_tick_seconds)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Run status only ever advances via the in-process async task that owns it -- any run
    # still at queued/running belongs to a process that no longer exists (crash, restart,
    # `--reload`), so it can never finish on its own and would otherwise sit stuck forever.
    orphaned = db.reconcile_orphaned_runs()
    if orphaned:
        print(f"Reconciled {len(orphaned)} orphaned run(s) from a previous process: {orphaned}")
    # Lives in this server process, not the browser -- Autopilot keeps working when the user
    # closes the tab or signs out, and stops cleanly (not mid-tick) on server shutdown.
    autopilot_scheduler.start()
    try:
        yield
    finally:
        await autopilot_scheduler.stop()


app = FastAPI(
    title="PR Engineer",
    version="0.2.0",
    description="Safe, PR-first autonomous engineering foundation.",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,  # the session cookie must survive a cross-origin fetch
)


def get_current_user(request: Request) -> SessionUser:
    raw = request.cookies.get(SESSION_COOKIE)
    user = read_session_cookie(raw, settings.session_secret) if raw else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


protected = APIRouter(dependencies=[Depends(get_current_user)])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "phase-2-human-gated-execution"}


@app.get("/api/v1/auth/github/login")
def github_login(request: Request) -> RedirectResponse:
    if not settings.github_oauth_client_id:
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured on this server.")
    state = generate_state()
    redirect_uri = str(request.url_for("github_callback"))
    response = RedirectResponse(build_authorize_url(settings.github_oauth_client_id, redirect_uri, state))
    response.set_cookie(STATE_COOKIE, state, max_age=STATE_MAX_AGE_SECONDS, httponly=True, samesite="lax")
    return response


@app.get("/api/v1/auth/github/callback", name="github_callback")
async def github_callback(request: Request, code: str, state: str) -> RedirectResponse:
    expected_state = request.cookies.get(STATE_COOKIE)
    if not expected_state or not secrets.compare_digest(expected_state, state):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")
    if not settings.github_oauth_client_id or not settings.github_oauth_client_secret:
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured on this server.")

    redirect_uri = str(request.url_for("github_callback"))
    try:
        user = await exchange_code_for_user(
            code=code,
            client_id=settings.github_oauth_client_id,
            client_secret=settings.github_oauth_client_secret,
            redirect_uri=redirect_uri,
        )
    except AuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    response = RedirectResponse(f"{settings.frontend_origin}/repositories")
    response.delete_cookie(STATE_COOKIE)
    response.set_cookie(
        SESSION_COOKIE,
        create_session_cookie(user, settings.session_secret),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/api/v1/auth/me")
def auth_me(user: SessionUser = Depends(get_current_user)) -> dict[str, str | None]:
    return {"login": user.login, "name": user.name, "avatar_url": user.avatar_url}


@app.post("/api/v1/auth/logout")
def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE)
    return response


@protected.post("/api/v1/repositories/analyze", response_model=TaskPlan)
def analyze_repository(request: RepositoryRequest, user: SessionUser = Depends(get_current_user)) -> TaskPlan:
    try:
        analysis = analyzer.analyze(request.path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    plan = planner.plan(analysis)
    repository_id = db.upsert_repository(analysis.root, user.login)
    analysis_id = db.insert_analysis(repository_id, analysis)
    db.sync_backlog_tasks(repository_id, analysis_id, plan.tasks)
    plan.tasks = db.list_tasks_for_repository(repository_id)
    plan.repository_id = repository_id
    return plan


@protected.get("/api/v1/github/repos", response_model=list[GitHubRepo])
async def list_github_repos(user: SessionUser = Depends(get_current_user)) -> list[GitHubRepo]:
    try:
        return await list_user_repos(user.access_token)
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@protected.post("/api/v1/github/repos/{owner}/{repo}/start", response_model=TaskPlan)
async def start_github_repo(owner: str, repo: str, user: SessionUser = Depends(get_current_user)) -> TaskPlan:
    """The GitHub-repo-picker equivalent of /repositories/analyze: clones the picked repo
    into the workspace (or pulls latest if already cloned from a previous pick) and
    analyzes it. No auth needed for the clone itself -- this app's OAuth scope is
    public_repo only, so every repo reachable here is already public."""
    dest = settings.workspace_root / "github" / f"{owner}__{repo}"
    try:
        if dest.exists():
            await asyncio.to_thread(pull_latest, dest)
        else:
            await asyncio.to_thread(clone_repository, f"https://github.com/{owner}/{repo}.git", dest)
    except GitOpsError as exc:
        raise HTTPException(status_code=502, detail=f"Could not prepare local clone: {exc}") from exc

    try:
        analysis = analyzer.analyze(dest)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    plan = planner.plan(analysis)
    repository_id = db.upsert_repository(analysis.root, user.login)
    analysis_id = db.insert_analysis(repository_id, analysis)
    db.sync_backlog_tasks(repository_id, analysis_id, plan.tasks)
    plan.tasks = db.list_tasks_for_repository(repository_id)
    plan.repository_id = repository_id
    return plan


@protected.get("/api/v1/repositories", response_model=list[RepositorySummary])
def list_repositories(user: SessionUser = Depends(get_current_user)) -> list[RepositorySummary]:
    return db.list_repositories(user.login)


@protected.get("/api/v1/repositories/{repository_id}/tasks", response_model=list[Task])
def list_repository_tasks(repository_id: int, user: SessionUser = Depends(get_current_user)) -> list[Task]:
    if not db.user_can_access_repository(repository_id, user.login):
        raise HTTPException(status_code=404, detail="Repository not found")
    return db.list_tasks_for_repository(repository_id)


@protected.get("/api/v1/repositories/{repository_id}/analysis", response_model=ProjectAnalysis | None)
def get_repository_analysis(repository_id: int, user: SessionUser = Depends(get_current_user)) -> ProjectAnalysis | None:
    if not db.user_can_access_repository(repository_id, user.login):
        raise HTTPException(status_code=404, detail="Repository not found")
    return db.get_latest_analysis(repository_id)


@protected.post("/api/v1/repositories/{repository_id}/generate-tasks", response_model=list[Task])
async def generate_repository_tasks(repository_id: int, user: SessionUser = Depends(get_current_user)) -> list[Task]:
    """Human-triggered, not automatic: unlike the deterministic planner (which always runs
    on analyze, is free, and is idempotent), this makes a real LLM call and can propose
    different tasks each time it's clicked -- so it only runs when explicitly asked for."""
    if not db.user_can_access_repository(repository_id, user.login):
        raise HTTPException(status_code=404, detail="Repository not found")
    repository = db.get_repository(repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    analysis = db.get_latest_analysis(repository_id)
    analysis_id = db.get_latest_analysis_id(repository_id)
    if analysis is None or analysis_id is None:
        raise HTTPException(status_code=409, detail="Repository has not been analyzed yet")
    try:
        ai_provider = resolve_provider(db.get_user_ai_settings(user.login), settings)
    except AIProviderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    proposed = await generate_tasks(Path(repository.path), analysis, ai_provider=ai_provider)
    db.sync_backlog_tasks(repository_id, analysis_id, proposed)
    return db.list_tasks_for_repository(repository_id)


def _ai_config_response(user_login: str) -> AIConfigResponse | None:
    saved = db.get_user_ai_settings(user_login)
    if saved is None:
        return None
    return AIConfigResponse(
        provider=saved.provider,
        model=saved.model,
        endpoint=saved.endpoint,
        configured=bool(saved.encrypted_api_key) or saved.provider == "ollama",
        enabled=saved.enabled,
        updated_at=saved.updated_at,
    )


@protected.get("/api/v1/ai-settings", response_model=AIConfigResponse | None)
def get_ai_settings(user: SessionUser = Depends(get_current_user)) -> AIConfigResponse | None:
    return _ai_config_response(user.login)


@protected.put("/api/v1/ai-settings", response_model=AIConfigResponse)
def save_ai_settings(request: AIConfigRequest, user: SessionUser = Depends(get_current_user)) -> AIConfigResponse:
    """Saves this user's single active AI configuration -- RepoPilot uses it for every AI
    operation of theirs (analysis, task generation, coding, review); there is no per-operation
    override. api_key is write-only and optional: omitting it (e.g. only changing the model)
    keeps whatever key was saved previously, since the frontend never has the real key to
    resend. The raw key is never returned -- see AIConfigResponse."""
    try:
        validate_model_choice(request.provider, request.model)
    except AIProviderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    encrypted_api_key = encrypt_secret(request.api_key, settings.ai_encryption_key) if request.api_key else None
    db.upsert_user_ai_settings(
        user.login,
        request.provider,
        request.model,
        encrypted_api_key,
        request.endpoint,
        keep_existing_key=request.api_key is None,
    )
    return _ai_config_response(user.login)


@protected.post("/api/v1/ai-settings/test-connection", response_model=ConnectionTestResponse)
async def test_ai_connection(
    request: AIConfigRequest, user: SessionUser = Depends(get_current_user)
) -> ConnectionTestResponse:
    """Tests the given configuration directly -- not necessarily what's already saved, so a
    user can verify a new API key or endpoint before committing to it. Omitting api_key falls
    back to the previously-saved key (if any), so re-testing after a save works without
    re-entering it."""
    api_key = request.api_key
    if api_key is None:
        saved = db.get_user_ai_settings(user.login)
        if saved and saved.provider == request.provider and saved.encrypted_api_key:
            api_key = decrypt_secret(saved.encrypted_api_key, settings.ai_encryption_key)
    try:
        provider = build_provider(request.provider, request.model, api_key=api_key, endpoint=request.endpoint)
    except AIProviderError as exc:
        return ConnectionTestResponse(ok=False, message=str(exc))
    result = await provider.test_connection()
    return ConnectionTestResponse(ok=result.status == "ok", message=result.message)


@protected.get("/api/v1/ai-settings/ollama-models", response_model=list[str])
async def list_ollama_models(endpoint: str | None = None) -> list[str]:
    """Backs the Settings page's "Refresh Models" button -- Ollama is the only provider RepoPilot
    can enumerate models from live; Anthropic/Gemini use a fixed, curated list shown by the
    frontend instead (app.ai.factory.KNOWN_MODELS_BY_PROVIDER)."""
    try:
        models = await OllamaProvider(host=endpoint or settings.ollama_host, model="").list_models()
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return models or []


def _autopilot_state(repository_id: int) -> AutopilotState:
    plan = db.get_autopilot_plan(repository_id)
    return AutopilotState(
        plan=plan,
        upcoming=db.list_upcoming_scheduled_runs(repository_id),
        recent=db.list_recent_scheduled_runs(repository_id),
    )


@protected.get("/api/v1/repositories/{repository_id}/autopilot", response_model=AutopilotState)
def get_autopilot(repository_id: int, user: SessionUser = Depends(get_current_user)) -> AutopilotState:
    if not db.user_can_access_repository(repository_id, user.login):
        raise HTTPException(status_code=404, detail="Repository not found")
    return _autopilot_state(repository_id)


@protected.post("/api/v1/repositories/{repository_id}/autopilot", response_model=AutopilotState)
def save_autopilot(
    repository_id: int, request: AutopilotPlanRequest, user: SessionUser = Depends(get_current_user)
) -> AutopilotState:
    """Creates or replaces this repository's plan (there is only ever one) and regenerates
    its bounded, at-most-PLAN_WINDOW_DAYS-day schedule from scratch -- any not-yet-started
    scheduled run from a previous configuration is cancelled first so the new settings are
    the only ones in effect going forward. Runs already completed/failed/in-progress are
    untouched history."""
    if not db.user_can_access_repository(repository_id, user.login):
        raise HTTPException(status_code=404, detail="Repository not found")
    plan = db.upsert_autopilot_plan(f"ap_{uuid.uuid4().hex}", repository_id, user.login, request)
    db.cancel_upcoming_scheduled_runs(plan.id)
    schedule = compute_schedule(request, datetime.now(UTC))
    db.create_scheduled_runs(plan.id, repository_id, [dt.isoformat() for dt in schedule])
    return _autopilot_state(repository_id)


@protected.post("/api/v1/repositories/{repository_id}/autopilot/pause", response_model=AutopilotState)
def pause_autopilot(repository_id: int, user: SessionUser = Depends(get_current_user)) -> AutopilotState:
    if not db.user_can_access_repository(repository_id, user.login):
        raise HTTPException(status_code=404, detail="Repository not found")
    plan = db.get_autopilot_plan(repository_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Autopilot has not been configured for this repository")
    db.set_autopilot_plan_status(plan.id, AutopilotPlanStatus.paused)
    return _autopilot_state(repository_id)


@protected.post("/api/v1/repositories/{repository_id}/autopilot/resume", response_model=AutopilotState)
def resume_autopilot(repository_id: int, user: SessionUser = Depends(get_current_user)) -> AutopilotState:
    if not db.user_can_access_repository(repository_id, user.login):
        raise HTTPException(status_code=404, detail="Repository not found")
    plan = db.get_autopilot_plan(repository_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Autopilot has not been configured for this repository")
    db.set_autopilot_plan_status(plan.id, AutopilotPlanStatus.active)
    return _autopilot_state(repository_id)


@protected.post("/api/v1/repositories/{repository_id}/autopilot/cancel", response_model=AutopilotState)
def cancel_autopilot(repository_id: int, user: SessionUser = Depends(get_current_user)) -> AutopilotState:
    if not db.user_can_access_repository(repository_id, user.login):
        raise HTTPException(status_code=404, detail="Repository not found")
    plan = db.get_autopilot_plan(repository_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Autopilot has not been configured for this repository")
    db.set_autopilot_plan_status(plan.id, AutopilotPlanStatus.cancelled)
    db.cancel_upcoming_scheduled_runs(plan.id)
    return _autopilot_state(repository_id)


def _owned_scheduled_run(scheduled_run_id: str, user: SessionUser) -> ScheduledRun:
    scheduled_run = db.get_scheduled_run(scheduled_run_id)
    if scheduled_run is None:
        raise HTTPException(status_code=404, detail="Scheduled run not found")
    if not db.user_can_access_repository(scheduled_run.repository_id, user.login):
        raise HTTPException(status_code=404, detail="Scheduled run not found")
    return scheduled_run


@protected.post("/api/v1/autopilot/scheduled-runs/{scheduled_run_id}/cancel", response_model=ScheduledRun)
def cancel_scheduled_run(scheduled_run_id: str, user: SessionUser = Depends(get_current_user)) -> ScheduledRun:
    scheduled_run = _owned_scheduled_run(scheduled_run_id, user)
    if scheduled_run.status not in (ScheduledRunStatus.scheduled, ScheduledRunStatus.waiting):
        raise HTTPException(status_code=409, detail=f"Run is already {scheduled_run.status.value} and cannot be cancelled")
    db.update_scheduled_run(scheduled_run_id, status=ScheduledRunStatus.cancelled, finished_at=datetime.now(UTC).isoformat())
    return db.get_scheduled_run(scheduled_run_id)


class _RescheduleRequest(BaseModel):
    scheduled_at: str


@protected.put("/api/v1/autopilot/scheduled-runs/{scheduled_run_id}", response_model=ScheduledRun)
def reschedule_scheduled_run(
    scheduled_run_id: str, request: _RescheduleRequest, user: SessionUser = Depends(get_current_user)
) -> ScheduledRun:
    scheduled_run = _owned_scheduled_run(scheduled_run_id, user)
    if scheduled_run.status != ScheduledRunStatus.scheduled:
        raise HTTPException(status_code=409, detail="Only a not-yet-started run can be rescheduled")
    db.update_scheduled_run(scheduled_run_id, scheduled_at=request.scheduled_at)
    return db.get_scheduled_run(scheduled_run_id)


@protected.get("/api/v1/tasks/{task_id}", response_model=Task)
def get_task(task_id: str) -> Task:
    task = db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@protected.post("/api/v1/tasks/{task_id}/approve", response_model=Task)
def approve_task(task_id: str) -> Task:
    try:
        task = db.approve_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@protected.post("/api/v1/tasks/{task_id}/runs", response_model=Run, status_code=202)
def start_run(
    task_id: str, background_tasks: BackgroundTasks, user: SessionUser = Depends(get_current_user)
) -> Run:
    try:
        run_id = orchestrator.submit(task_id, github_token=user.access_token, owner_login=user.login)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    background_tasks.add_task(orchestrator.execute, run_id)
    return db.get_run(run_id)


@protected.get("/api/v1/tasks/{task_id}/runs", response_model=list[Run])
def list_task_runs(task_id: str) -> list[Run]:
    return db.list_runs_for_task(task_id)


@protected.get("/api/v1/runs/{run_id}", response_model=Run)
def get_run(run_id: str) -> Run:
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@protected.post("/api/v1/runs/{run_id}/cancel", response_model=Run, status_code=202)
def cancel_run(run_id: str) -> Run:
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if not orchestrator.cancel(run_id):
        raise HTTPException(status_code=409, detail=f"Run is already {run.status.value} and cannot be cancelled")
    return db.get_run(run_id)


@protected.get("/api/v1/runs/{run_id}/events", response_model=list[RunEvent])
def list_run_events(run_id: str) -> list[RunEvent]:
    return db.list_events_for_run(run_id)


@protected.get("/api/v1/runs/{run_id}/events/stream")
async def stream_run_events(run_id: str) -> StreamingResponse:
    return StreamingResponse(_run_event_stream(run_id), media_type="text/event-stream")


@protected.get("/api/v1/activity/stream")
async def stream_activity() -> StreamingResponse:
    return StreamingResponse(_global_event_stream(), media_type="text/event-stream")


@protected.get("/api/v1/status")
def status() -> dict[str, object]:
    return {"max_concurrent_runs": settings.max_concurrent_runs, **db.count_active_runs()}


# A run step can legitimately produce zero events for several minutes (observed in
# production: `npm install` on a real repo ran silently for 5+ minutes during a baseline
# check). With nothing written to the response body for that whole window, the connection
# looks indistinguishable from a dead one to any layer that enforces an idle timeout --
# and because nothing ever explicitly closes it, the browser's EventSource has no signal to
# reconnect on, so the UI just freezes at the last event it saw even though the backend kept
# working the entire time. A periodic comment ping (SSE frames starting with ':' are ignored
# by EventSource but still count as traffic) keeps the connection demonstrably alive.
_SSE_KEEPALIVE_SECONDS = 15


async def _run_event_stream(run_id: str) -> AsyncIterator[str]:
    for event in db.list_events_for_run(run_id):
        yield _sse(event)
    queue = event_bus.subscribe(run_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_SSE_KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield _sse(event)
    finally:
        event_bus.unsubscribe(run_id, queue)


async def _global_event_stream() -> AsyncIterator[str]:
    for event in db.list_recent_events():
        yield _sse(event)
    queue = event_bus.subscribe_global()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_SSE_KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield _sse(event)
    finally:
        event_bus.unsubscribe_global(queue)


def _sse(event: RunEvent) -> str:
    return f"event: run-event\ndata: {event.model_dump_json()}\n\n"


app.include_router(protected)


@app.post("/api/v1/github/webhooks", response_model=WebhookAccepted)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> WebhookAccepted:
    body = await request.body()
    _verify_webhook(body, x_hub_signature_256)
    # Parsing verifies GitHub sent valid JSON. Queueing is deliberately deferred until Phase 1.1.
    try:
        json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Webhook payload is not valid JSON") from exc
    return WebhookAccepted(event=x_github_event, delivery=x_github_delivery)


def _verify_webhook(body: bytes, signature: str | None) -> None:
    if not settings.github_webhook_secret:
        return
    expected = "sha256=" + hmac.new(settings.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")
