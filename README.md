# ProjectDash

A high-speed, terminal-native project manager for developers. An offline-first, minimalist alternative to the Linear web UI.

## Vision
ProjectDash is designed for developers who live in the terminal. It provides a keyboard-centric, monochrome interface for managing Linear issues, tracking sprint progress, and monitoring team workload without leaving your shell.

## Features (Planned & Prototype)
- **Dashboard:** At-a-glance project health and velocity.
- **Sprint Board:** Kanban-style issue management with Vim-style navigation.
- **Workload View:** Team capacity tracking and point allocation.
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

## Prototyping Strategy
We are currently in **Stage 1: The Shell**. This phase focuses on the UI/UX experience and navigation before connecting to live APIs.

---
*Built with speed and minimalism in mind.*
