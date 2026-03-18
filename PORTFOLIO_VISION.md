# Portfolio Vision: ProjectDash as Top-Level Project Manager

## Purpose

This document captures the vision for ProjectDash as a **general-purpose portfolio manager** — a top-level view of all software projects across a developer's practice, not just the subset tracked in Linear or GitHub.

This is a companion to `EXPANSION.md` and represents a distinct product direction: the zoom-out layer that sits above the sprint/issue workflow already built.

---

## The Problem

A solo developer or small team typically has 20–50 software projects at various stages of life. This landscape — ideas, experiments, active builds, shipped tools, paused explorations — currently has no home. It lives fragmented across:

- The filesystem (directories you have to `ls` to remember exist)
- Linear (only the projects actively tracked there)
- GitHub (only the repos that have been pushed)
- Your own memory

The result: no single surface answers "what do I have, what's worth working on, what's my best work, what's half-baked?"

ProjectDash is already open in your terminal. It should answer that question.

---

## The Vision

**ProjectDash is the top-level view of your entire software practice** — for developers who live in the terminal, and for the AI agents that work alongside them.

The portfolio layer sits above the existing sprint/issue layer as a higher zoom level:

```
Portfolio Gallery       ← this doc
  └── Project Focus     (] to drill in)
        └── Sprint Board, Timeline, Workload, GitHub
              └── Issue Detail, PR, CI, Agent Runs
```

Navigation already supports this: `]` scopes down to a project, `[` scopes back up. The portfolio gallery is what `[` eventually lands on at the top.

---

## What Makes a Project

A "project" in the portfolio sense is broader than a Linear project. It is any software effort worth tracking — a git repo, an idea doc, a prototype, a shipped tool.

### LocalProject Model

```
id               str       — stable local ID
name             str       — display name
path             str       — absolute filesystem path
type             str       — category (see taxonomy below)
status           str       — lifecycle stage (see taxonomy below)
tier             str       — quality/priority tier (S/A/B/C/D)
tags             list[str] — freeform labels
description      str       — one-paragraph brief (human or agent-written)
last_commit_at   datetime  — from git log
has_readme       bool      — README.md present
has_tests        bool      — test directory/files detected
has_ci           bool      — .github/workflows or similar present
auto_score       int       — 0–100 computed from signals
linked_linear_id str|None  — linked Linear project ID
linked_repo      str|None  — linked GitHub owner/repo
created_at       datetime
archived_at      datetime|None
```

---

## Taxonomies

### Status — Lifecycle Stages

| Status        | Meaning                                               |
|---------------|-------------------------------------------------------|
| `idea`        | Concept or stub — folder exists, minimal code        |
| `exploration` | Active prototyping, no clear scope or commitment     |
| `active`      | Being worked with intent; current focus              |
| `paused`      | Intentionally on hold, not abandoned                 |
| `shipped`     | Released, deployed, or published                     |
| `archived`    | Done or consciously shelved                          |

### Type — Project Category

| Type        | Examples                                              |
|-------------|-------------------------------------------------------|
| `tui`       | projectDash, ptui                                     |
| `cli`       | cmdref, pd                                            |
| `ai-agent`  | ag-ui, agent_orchestration, agui                     |
| `game`      | holdemHub, poker, triviape, cardhaus                 |
| `plugin`    | obsidian-chronology, obsidian-word-count, obs_plugins|
| `web-app`   | dchid.com, homescreen                                |
| `media`     | mediarank, music, playlist                           |
| `system`    | terminal, tmux, kbLayouts, mt                        |
| `library`   | snippets, dsa                                        |
| `learning`  | cpp, python, operatingSystems                        |
| `creative`  | Lorelin, presswork                                   |

### Tier — Quality / Priority Signal

Tier is **manually curated** — it represents your intent, not just activity.

| Tier | Meaning                                                       |
|------|---------------------------------------------------------------|
| `S`  | Flagship — production-quality, actively maintained           |
| `A`  | Solid — worth shipping or continuing, near-production        |
| `B`  | Promising — good prototype, needs focused effort to mature   |
| `C`  | Experiment — interesting but low priority                    |
| `D`  | Stub / idea — not yet worth investing in                     |

The **auto_score** (0–100, computed from git signals, README/test/CI presence) reflects *activity and maturity*, while tier reflects *intent*. Where they diverge is informative — a high-activity C-tier project often means you're avoiding something higher priority.

---

## Discovery Model

Two data sources combined:

**1. Filesystem scan** — configured root directory (e.g. `~/Documents/Software/`):
- Detect git repos (`git rev-parse --git-dir`)
- Read last commit timestamp
- Detect README, test dirs, CI config
- Infer language from file extensions
- Auto-populate a new `LocalProject` with defaults

**2. Local manifest** (`~/.projectdash/projects.yaml` or `projectdash.config.json`):
- Enrichment layer: tier, status, type, tags, description
- Projects that live outside the configured root
- Manual overrides of auto-detected fields

On first scan of a directory, ProjectDash creates a skeleton entry. The developer enriches it (tier, status, description) over time, either via TUI inline editing or by editing the manifest.

---

## The Portfolio Gallery View

### Layout Concept

```
[ PORTFOLIO ]  status:active  type:all  tier:all  sort:tier ↓    18 projects
──────────────────────────────────────────────────────────────────────────────
> [S] projectDash         tui / ai-agent    active      3h ago    94/100
  [S] Lorelin             creative          active      2d ago    88/100
  [A] agui                ai-agent          active      5d ago    76/100
  [A] presswork           creative          paused      2w ago    71/100
  [B] ptui                tui               exploration 1mo ago   52/100
  [B] holdemHub           game              paused      3mo ago   48/100
  [C] canvasPipe          cli               exploration 6mo ago   31/100
  [D] triviape            game              idea        1yr ago   12/100
──────────────────────────────────────────────────────────────────────────────
SIDEBAR: projectDash
  Path:    ~/Documents/Software/projectDash
  Type:    tui / ai-agent     Tier: S
  Status:  active             Score: 94/100
  Commits: 3h ago             README: yes  Tests: yes  CI: yes

  Linear:  linked — 12 open issues
  GitHub:  dylanchidambaram/projectDash — 2 open PRs

  p    open in editor
  ]    drill into sprint board
  o    open GitHub
  e    edit tier / status / tags
```

### Filtering and Sorting

- Filter by `status`, `type`, `tier` — quick-key cycle or slash filter
- Sort by: `tier` (default), `last_commit_at`, `auto_score`, `name`, `status`
- `v`/`V` cycle visual modes: `all`, `active`, `paused`, `shipped`, `ideas`

---

## The Tier Divergence Signal

One of the most useful outputs of this system: **projects where tier and activity diverge**.

- High activity, low tier → you might be procrastinating on something more important
- High tier, no activity → stale flagship work; might need a decision (pause/archive/focus)
- Low score, high tier → promising project that needs investment to prove itself

This could surface as a dedicated "attention" filter or a periodic digest.

---

## Agentic Integration

The portfolio layer is the missing context for AI agents working in your codebase.

### What agents can do with portfolio access:

1. **Auto-categorize on first scan** — agent reads README + file structure, assigns type + suggested tier + description, writes to manifest
2. **Generate project briefs** — one-paragraph summary of what a project is, its current state, and the next meaningful action
3. **Priority surfacing** — "you haven't touched `presswork` in 6 weeks but it's tier A — should it be paused?"
4. **Cross-project awareness** — an agent working in `projectDash` can read the portfolio to understand what it's building *for*
5. **AgentRun linking** — runs are linked to `LocalProject`, not just Linear issues. Agent work appears in the portfolio view.

### The loop:
```
Agent reads portfolio → picks up project → does work →
marks issue done → logs run trace → human reviews in portfolio view
```

No browser. The TUI is the review interface for agentic output at every zoom level.

---

## Relationship to Existing Concepts

| Concept            | Relationship                                                  |
|--------------------|---------------------------------------------------------------|
| Linear `Project`   | A `LocalProject` can link to a Linear project via `linked_linear_id`. They are different layers — Linear tracks sprint execution, the portfolio tracks intent and lifecycle. |
| `project_scope_id` | Already exists on the app. Portfolio sets this when you drill in with `]`. |
| `IdeationGallery`  | Currently a chart lab. Long-term: either renamed/repurposed as portfolio gallery, or portfolio becomes a new top-level tab. |
| `AgentRun`         | Already has `project_id`. This links to the `LocalProject` id once the portfolio model exists. |
| Sync               | Portfolio data is local-first by design. No external sync needed for the manifest layer. Git activity is read locally. |

---

## MVP Definition

The smallest version that makes ProjectDash worth opening instead of running `ls ~/Documents/Software/`:

1. Filesystem scan of a configured root → auto-detect git repos + last-commit date
2. Gallery view: name, type, status, tier, last-commit, auto_score
3. Keyboard navigation (j/k select, `]` to drill in, `[` to return)
4. Inline tier/status editing written back to local manifest
5. Sidebar with project metadata and quick-action hints

Everything else (agent briefs, divergence signals, agentic integration) is additive on top of that foundation.

---

## Open Questions

1. **Discovery scope**: user-configured root path(s) only, or support multiple roots?
2. **Manifest location**: per-repo (`projectdash.config.json`) vs centralized (`~/.projectdash/projects.yaml`)?
3. **Tier assignment UX**: edit inline in TUI, or always edit manifest directly?
4. **Linear project relationship**: same `Project` entity with a `source` field, or two models that link?
5. **IdeationGallery fate**: repurpose it as the portfolio gallery, or keep chart lab separate and add a new tab?
6. **Agent brief generation**: on-demand (keybinding triggers a Claude run), or background on first scan?

---

## Iteration Log

| Date       | Update                                                    | Why                                                                    |
|------------|-----------------------------------------------------------|------------------------------------------------------------------------|
| 2026-03-17 | Created this document from product ideation session.     | Establish the portfolio vision as a first-class product direction separate from the Linear/GitHub sprint workflow. |
