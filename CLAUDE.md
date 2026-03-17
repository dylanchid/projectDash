# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

ProjectDash is a keyboard-first, offline-first TUI project manager built with Textual. It syncs from Linear and GitHub into a local SQLite cache and presents data across tabbed views. Python 3.12+, managed with `uv`.

## Commands

```bash
uv sync                              # Install dependencies
uv sync --group dev                  # Install with dev tools (watchfiles, etc.)

uv run projectdash                   # Launch the TUI app
uv run pd sync                       # Linear sync
uv run pd sync-github                # GitHub sync
uv run pd doctor                     # Check setup/env

uv run pytest                        # Run all tests
uv run pytest tests/test_config.py   # Run one test file
uv run pytest tests/test_config.py::test_config_merge_file_json  # Single test

uv run textual run --dev src/projectdash/app.py  # CSS hot reload
uv run pd dev                        # Full auto-restart watcher (needs dev group)
```

## Architecture

### Data Flow

```
Linear/GitHub API (httpx async)
  → Connector.build_entities() (raw dicts → domain dataclasses)
    → Database (aiosqlite, SQLite INSERT OR REPLACE)
      → DataManager (in-memory entity lists)
        → MetricsService (pure computation → frozen metric dataclasses)
          → Views (Static.update() with computed data)
```

### Key Modules (src/projectdash/)

- **app.py** — `ProjectDash(App)` Textual app; owns bindings, tab switching, action handlers
- **models.py** — Pure dataclasses: `User`, `Project`, `Issue`, `Repository`, `PullRequest`, `CiCheck`, `WorkEvent`, `AgentRun`, `LinearWorkflowState`
- **data.py** — `DataManager` — central data hub; in-memory entity lists, orchestrates sync, write-through mutations
- **database.py** — `Database` — async aiosqlite wrapper; `init_db()` creates tables with additive `ALTER TABLE` migrations (no framework)
- **linear.py / github.py** — Async API clients (httpx); GraphQL for Linear, REST for GitHub
- **config.py** — `AppConfig` frozen dataclass; `from_env()` reads env vars then merges JSON/YAML config file
- **services/metrics.py** — `MetricsService` — pure computation layer; views call this, never the DB
- **connectors/** — Stateless mappers: `LinearConnector`, `GitHubConnector` — zero I/O, just dict→model transforms
- **views/** — Six `Static`-based views + two modal `Screen` classes
- **widgets/** — Reusable Textual widgets (`IssueCard`, `ProjectCard`, etc.)
- **projectdash.tcss** — Single TCSS file; monochrome palette (#000/#fff/#666/#888)

### View Pattern

All views are `textual.widgets.Static` subclasses following this contract:
- `compose()` — static widget tree
- `on_mount()` / `on_show()` — call `self.refresh_view()`
- `refresh_view()` — calls `self.app.metrics.<method>(self.app.data_manager)` → updates DOM nodes by ID

Views never touch the database or API directly. Many views define `VISUAL_MODES` tuples for cycling sub-views with `v`/`V` keys.

### Write-Through Mutations

Issue mutations (status, assignee, estimate) in `DataManager`:
1. Optimistically update in-memory model
2. Call Linear API mutation
3. On failure: restore previous values
4. On success: persist to SQLite

### Project Scope Navigation

`project_scope_id: str | None` on the app. `]` = scope down to project, `[` = scope up (clear). When set, all views filter to that project.

## Testing Patterns

- Async tests require `@pytest.mark.asyncio` (uses `pytest-asyncio`)
- Integration tests use `tmp_path` for isolated SQLite DBs
- No mock library — hand-rolled fakes and `SimpleNamespace` stubs
- `MetricsService` tests use a `DummyData` class matching the `DataManager` interface
- No `conftest.py` — each test file is self-contained

## Config

- Copy `projectdash.config.example.json` → `projectdash.config.json`
- `.env` file auto-loaded from cwd or repo root
- Required env vars: `LINEAR_API_KEY`, `GITHUB_TOKEN`
- GitHub repos: `PD_GITHUB_REPOS` env var (comma-separated `owner/repo`) or `github_repositories` in config JSON
