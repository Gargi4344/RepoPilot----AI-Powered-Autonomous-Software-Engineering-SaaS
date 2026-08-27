# PR Engineer — Phase 2

An autonomous, PR-first GitHub software-engineering service. It analyzes an already-cloned
repository, proposes low-risk candidate tasks, and — once a human explicitly approves a task —
runs a local, free (Ollama-based) coding agent in an isolated git worktree to make the change,
tests it, generates a Conventional Commits message, and (only if you've explicitly allowlisted
the target repo) pushes the branch and opens a **draft** pull request for a human to review.

**Nothing in this app can merge a pull request.** That is an intentional, structural omission —
not a runtime check — and stays true regardless of how the rest of the pipeline is configured.

## Included

- FastAPI endpoints for repository analysis, task backlog management, run orchestration, and
  a live SSE activity feed, backed by a local SQLite database (`app/db.py`) so state survives
  restarts.
- Deterministic, rule-based task planning limited to low-risk work that requires human approval
  before anything executes (`app/planner.py`).
- An optional, explicitly human-triggered LLM backlog generator (`app/agents/backlog_agent.py`)
  that reads the repo's file tree, README, and manifest to propose richer candidate tasks than
  the three fixed rule-based checks — every proposal still lands in `backlog` status and still
  requires the same human approval before anything happens to it.
- An isolated git worktree per run (`app/git_ops.py`) — the target repository's own checkout is
  never touched.
- A local coding agent (`app/agents/coding_agent.py`) driven by a self-hosted Ollama model, with
  no shell/bash tool: only path-confined file read/write/replace and one fixed, argument-less
  test-runner tool. Bounded by a hard iteration cap and wall-clock timeout.
- An allowlisted test runner (`app/test_runner.py`) that only ever executes a fixed, literal
  command per tool already detected in the target repo (pytest/ruff/npm/eslint/go test) — never
  a string built from task or model output.
- A bounded repair loop: up to two extra coding-agent attempts if tests fail, each given the
  previous failure's output.
- An advisory review agent (`app/agents/review_agent.py`) that annotates the diff but never
  gates anything — the human reviewing the PR makes the real call.
- A GitHub client (`app/github_client.py`) that pushes and opens a **draft** PR only when the
  target repo is on `ALLOWED_TARGET_REPOS` and a token is configured — refused by default.
- A React + Vite + TypeScript dashboard (`frontend/`) — analyze a repo, approve/start tasks, and
  watch a run's activity log update live via SSE, from a browser.
- Unit and integration tests across the whole pipeline, including a mocked end-to-end run.

## Local setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e ".[dev]"
```

Install [Ollama](https://ollama.com) and pull the coding-agent model (this is what the pipeline
actually runs — no API key, no per-token cost):

```powershell
winget install --id Ollama.Ollama -e
ollama pull qwen2.5-coder:7b
```

Copy `.env.example` to `.env` and adjust as needed (see the comments in that file for what each
setting does — in particular, `ALLOWED_TARGET_REPOS` must be set before any real GitHub push/PR
can happen). Then start the server:

```powershell
py -m uvicorn app.main:app --reload
```

> If a bare `uvicorn` command fails with `ModuleNotFoundError`, your `uvicorn` on `PATH` may
> resolve to a different Python installation than the one you `pip install`ed into — use
> `py -m uvicorn` (as above) to run it from the same environment.

Open **http://127.0.0.1:8000/docs** for an interactive UI to exercise every endpoint, or drive it
directly:

```powershell
$body = @{ path = "D:\path\to\cloned-repository" } | ConvertTo-Json
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/repositories/analyze -ContentType "application/json" -Body $body

Invoke-RestMethod http://127.0.0.1:8000/api/v1/repositories
Invoke-RestMethod http://127.0.0.1:8000/api/v1/repositories/1/tasks
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/tasks/<task-id>/approve
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/tasks/<task-id>/runs
Invoke-RestMethod http://127.0.0.1:8000/api/v1/runs/<run-id>
Invoke-RestMethod http://127.0.0.1:8000/api/v1/runs/<run-id>/events
```

Run checks:

```powershell
py -m pytest
py -m ruff check .
```

Pytest stores its temporary files inside this project (`.pytest-work`) so it also works on
Windows machines where the system temp directory is locked or full.

## Frontend dashboard

With the backend running (above), in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The Vite dev server proxies `/api` to `127.0.0.1:8000`, so no
CORS configuration is needed for local use. Four views: **Repositories** (everything analyzed
so far), **Analyze** (point it at a local path), a per-repository **Backlog** (approve a task,
start a run, watch its status badge update, or click **Generate more tasks (AI)** to have the
local model propose additional candidates beyond the three fixed rule-based checks), and a
**Run detail** page with a live, SSE-driven activity log — plus a global **Activity** feed
across every run at once.

## Safety boundary

- A task never executes anything until a human calls `POST /tasks/{id}/approve` then
  `POST /tasks/{id}/runs` — that click is what starts spend and any code execution.
- The coding agent has no shell tool; every file path it touches is checked against the
  worktree root and a denylist (`.git/**`, `.github/workflows/**`, `.env*`) before any
  filesystem call.
- The test runner only ever invokes a fixed, literal command per already-detected tool —
  never a string derived from task or model content.
- `git_ops.push()` refuses to push any branch outside the `pr-engineer/*` namespace, and
  `github_client.py` refuses to push/PR against any repo not explicitly on
  `ALLOWED_TARGET_REPOS` — independent of whichever path was analyzed.
- Every PR is opened as a **draft**. There is no merge endpoint anywhere in this API, and none
  is planned — merging, branch protection, and releases stay entirely human, on GitHub.
- The server binds to `127.0.0.1` by default; there is no authentication layer yet, so treat
  any exposure beyond localhost as requiring one first.

## Known limitations

- **Local model quality.** The coding agent runs against a small (7B) local model by default.
  It succeeds on small, well-scoped changes but can get confused during multi-step repairs —
  when that happens the run lands cleanly at `failed` rather than looping forever, and nothing
  gets pushed. That's the human-review gate working as intended, not a bug.
- **Single-repo, on-demand only.** No multi-repo orchestration, no scheduler for unattended
  round-the-clock work — a run happens when a human starts it, which is the primary safety
  control in this design.
