# ProjectDash

A high-speed, terminal-native project manager for developers. An offline-first, minimalist alternative to the Linear web UI.

## Vision
ProjectDash is designed for developers who live in the terminal. It provides a keyboard-centric, monochrome interface for managing Linear issues, tracking sprint progress, and monitoring team workload without leaving your shell.

## Features (Planned & Prototype)
- **Dashboard:** At-a-glance project health with load, risk, priority-mix, and project-vs-team compare views.
- **Sprint Board:** Kanban-style issue management with Vim-style navigation.
- **Timeline View:** Project rows plus delivery-risk/completion views and dependency-blocker cues.
- **Workload View:** Team capacity tracking with table, utilization distribution, rebalance heatmap, and what-if simulation.
- **Offline-First:** Instant loads powered by a local SQLite cache.
- **Linear Integration:** Syncs directly with your Linear workspace.

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
- `uv run pd sync-history`: show recent persisted sync runs.

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
- `j` / `k`: Move selection up/down
- `h` / `l` (or `←` / `→`): Move between columns in Sprint view with wrap-around; switches tabs in other views
- `]` / `[`: Level down to project focus / level up to all-project scope (applies across Dashboard/Sprint/Timeline/Workload)
- `,` / `.`: Previous/next project while focused (and from scoped views)
- `/`: Open slash command mode with bottom command palette suggestions (`↑/↓` navigate, `Tab` autocomplete, `Enter` run)
- `?`: Toggle in-app keyboard help overlay
- `f`: Start sprint quick filter (text search + `status:`/`priority:`/`assignee:`/`id:`/`project:`), `Enter` keeps it, `Esc` clears it
- `u`: Jump to the next issue assigned to you (matches `PD_ME`, `USER`, or `Me`)
- `H`: Open full sync history screen (latest runs + diagnostics)
- `v`: Cycle visual mode in Dashboard/Timeline/Workload (multi-view analytics per tab)
- `g`: Toggle graph density (compact/detailed) in visual views
- `Enter` / `Esc`: Open/close detail panels consistently across tabs
- `=` / `-`: Increase/decrease workload what-if simulation shift
- `1` / `2` / `3`: Apply saved view presets (`Exec`, `Manager`, `IC`)
- `m`: Cycle selected issue status
- `a`: Cycle selected issue assignee
- `e`: Cycle selected issue estimate

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
- `PD_ENABLE_MOCK_SEED` (set to `true` to auto-seed mock data on empty cache)
- `PD_CONFIG_PATH`

## Prototyping Strategy
We are currently in **Stage 1: The Shell**. This phase focuses on the UI/UX experience and navigation before connecting to live APIs.

---
*Built with speed and minimalism in mind.*
