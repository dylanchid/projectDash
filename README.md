# ProjectDash

A high-speed, terminal-native project manager for developers. An offline-first, minimalist alternative to the Linear web UI.

## Vision
ProjectDash is designed for developers who live in the terminal. It provides a keyboard-centric, monochrome interface for managing Linear issues, tracking sprint progress, and monitoring team workload without leaving your shell.

## Planning Docs
- [PRD.md](PRD.md)
- [EXPANSION.md](EXPANSION.md) (living strategy for growing into a broader engineering command center)
- [ROADMAP.md](ROADMAP.md) (implementation-ready epics/tickets aligned to PRD v0.2)

## Features (Planned & Prototype)
- **Linear Dashboard:** At-a-glance project health with load, risk, priority-mix, and project-vs-team compare views.
- **GitHub Dashboard:** Repository, pull request, and CI-check health in a dedicated tab.
- **Sprint Board:** Kanban-style issue management with Vim-style navigation.
- **Timeline View:** Project rows plus delivery-risk/completion views and dependency-blocker cues.
- **Workload View:** Team capacity tracking with table, utilization distribution, rebalance heatmap, and what-if simulation.
- **Offline-First:** Instant loads powered by a local SQLite cache.
- **Linear Integration:** Syncs directly with your Linear workspace.
- **GitHub Integration (Foundational):** Syncs repositories, pull requests, and check runs for configured repos.

## Tech Stack
- **Framework:** [Textual](https://textual.textualize.io/) (TUI)
- **Runtime:** Python 3.12+
- **Manager:** [uv](https://github.com/astral-sh/uv)
- **Database:** SQLite

## Getting Started

### Prerequisites
- Python 3.12+
- `uv` package manager

### Installation
1. Clone the repository
2. Install dependencies:
   ```bash
   uv sync
   ```

### Running the App
```bash
uv run src/projectdash/app.py
```

### CLI Commands
- `uv run pd sync`: run a sync now and print per-step diagnostics.
- `uv run pd sync-github`: run a GitHub sync now and print per-step diagnostics.
- `uv run pd sync-history`: show recent persisted sync runs.
- `uv run pd connectors`: list configured connectors.
- `uv run pd agent-runs`: show recent persisted agent execution runs.

### Hot Reload (TUI Dev)
1. Install dev tools:
   ```bash
   uv sync --group dev
   ```
2. Style hot reload (Textual dev mode):
   ```bash
   uv run textual run --dev src/projectdash/app.py
   ```
3. Full auto-restart on `.py` and `.tcss` saves:
   ```bash
   uv run pd dev
   ```

### Sprint Controls
- `d` / `Shift+G` / `s` / `t` / `w` / `n`: Jump to Linear, GitHub, Sprint, Timeline, Workload, and Ideation tabs
- `j` / `k`: Move selection up/down
- `h` / `l` (or `←` / `→`): Move between columns in Sprint view with wrap-around; switches tabs in other views
- `]` / `[`: Level down to project focus / level up to all-project scope (applies across Linear/Sprint/Timeline/Workload)
- `,` / `.`: Previous/next project while focused (and from scoped views)
- `/`: Open slash command mode with bottom command palette suggestions (`↑/↓` navigate, `Tab` autocomplete, `Enter` run)
- `?`: Toggle in-app keyboard help overlay
- `z`: Toggle the right detail sidebar
- `f`: Start sprint quick filter (text search + `status:`/`priority:`/`assignee:`/`id:`/`project:`), `Enter` keeps it, `Esc` clears it
- `u`: Jump to the next issue assigned to you (matches `PD_ME`, `USER`, or `Me`)
- `r` (from Sprint): Open GitHub PR drilldown for the selected Linear issue
- `y`: Run Linear sync
- `Shift+Y`: Run GitHub sync
- `H`: Open full sync history screen (latest runs + diagnostics)
- `v`: Cycle visual mode in Linear/GitHub/Timeline/Workload (multi-view analytics per tab)
- `g`: Toggle graph density (compact/detailed) in visual views
- `v`/`g` in Ideation: Cycle concept categories and compact/detailed gallery density
- `9` / `0` / `;` / `'` / `=` / `-` / `7` (in Ideation line concepts): Pan left/right, change focused series, zoom in/out, toggle classic/hires renderer
- Ideation chart backend now auto-uses `textual-plotext` when installed (with native renderer fallback)
- `S` / `L` / `C` / `R` (from GitHub): Cycle state filter, cycle linked/unlinked filter, toggle failing-only, clear all GitHub filters
- `O` / `B` / `A` / `I` (from GitHub): Open selected PR URL, copy branch, queue agent run for PR, jump to linked Linear issue
- `Enter` / `Esc`: Open/close detail panels consistently across tabs
- `=` / `-`: Increase/decrease workload what-if simulation shift
- `1` / `2` / `3`: Apply saved view presets (`Exec`, `Manager`, `IC`)
- `m`: Cycle selected issue status
- `x`: Close selected issue (moves it to a done status)
- `a`: Cycle selected issue assignee
- `e`: Cycle selected issue estimate
- `c`: Create/open a comment draft for selected issue
- `o`: Open selected issue in Linear (browser)
- `p`: Open workspace in code editor
- `Shift+T`: Open selected issue draft in terminal editor (requires config)

### Configuration
ProjectDash supports persisted config overrides via `projectdash.config.json` (or `PD_CONFIG_PATH`).

1. Copy the example:
   ```bash
   cp projectdash.config.example.json projectdash.config.json
   ```
2. Edit values such as Kanban statuses and per-user capacities.
   Use `seed_mock_data: true` only for local prototyping/demo data.

You can also override selected values with env vars:
- `PD_DEFAULT_CAPACITY_POINTS`
- `PD_WORKLOAD_WARNING_PCT`
- `PD_WORKLOAD_CRITICAL_PCT`
- `PD_WORKLOAD_BAR_WIDTH`
- `PD_WORKLOAD_ISSUE_PREVIEW_LIMIT`
- `PD_TIMELINE_HORIZON_DAYS`
- `PD_TIMELINE_MAX_PROJECTS`
- `PD_SPRINT_RISK_BLOCKED_THRESHOLD`
- `PD_SPRINT_RISK_FAILING_PR_THRESHOLD`
- `PD_SPRINT_RISK_STALE_REVIEW_DAYS`
- `PD_SPRINT_RISK_STALE_REVIEW_THRESHOLD`
- `PD_SPRINT_RISK_OVERLOADED_OWNERS_THRESHOLD`
- `PD_SPRINT_RISK_OVERLOADED_UTIL_PCT`
- `PD_ENABLE_MOCK_SEED` (set to `true` to auto-seed mock data on empty cache)
- `PD_CONFIG_PATH`
- `PD_GITHUB_REPOS` (comma-separated `owner/repo` targets for GitHub sync)
- `PD_GITHUB_PR_LIMIT` (max PRs per configured repository during GitHub sync)
- `PD_GITHUB_SYNC_CHECKS` (set to `false` to skip CI check-run ingestion)
- `PD_AGENT_RUN_CMD` (optional command template to auto-dispatch queued agent runs from GitHub PR action; supports `{run_id}`, `{issue_id}`, `{project_id}`, `{pr_id}`, `{branch_name}`, `{repository_id}`, `{pull_request_number}`, `{pull_request_url}`, `{prompt_text}`. Use `tmux:<command-template>` or `profile:tmux:<command-template>` for managed tmux launch/profile mode with session naming, per-run log capture, and completion status updates.)
- `PD_AGENT_RUN_LOG_DIR` (optional directory for tmux launcher logs/scripts; defaults to `.projectdash/agent-runs`)
- `PD_LINEAR_WORKSPACE` (optional Linear workspace slug for issue URLs)
- `PD_CODE_EDITOR_CMD` (optional launch template; supports `{project_root}`, `{issue_id}`, `{issue_title}`, `{linear_url}`, `{comment_file}`)
- `PD_COMMENT_EDITOR_CMD` (optional launch template for comment drafts)
- `PD_TERMINAL_EDITOR_CMD` (optional launch template for terminal editor note flow)

## Prototyping Strategy
We are currently in **Stage 1: The Shell**. This phase focuses on the UI/UX experience and navigation before connecting to live APIs.

---
*Built with speed and minimalism in mind.*
