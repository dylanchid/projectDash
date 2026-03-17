# ProjectDash Roadmap (PRD v0.2 Execution)

## Scope and Intent
- This roadmap operationalizes `EXPANSION.md` PRD v0.2.
- Primary goal: win the P0 loop (`Issue -> PR -> Merge`) for ICs and Tech Leads.
- Secondary goal: ship a narrow P1 slice (agent run audit trail only).

## Milestones (8 Weeks)
1. Weeks 1-2: Sync correctness and freshness UX.
2. Weeks 3-4: Unified issue/PR/check action loop + triage ergonomics.
3. Weeks 5-6: Blocker radar + sprint risk/workload essentials.
4. Weeks 7-8: Agent run audit trail + limited launch action.

## Epic E1: Sync Correctness and Freshness (P0)
### Ticket E1-T1: Sync Freshness Indicators Across Views
- Priority: P0
- Problem: Users cannot quickly tell if displayed state is stale.
- Deliverables:
- Add per-connector freshness metadata (`last_success_at`, `last_attempt_at`, `status`) to top-level UI surfaces.
- Show stale warning thresholds and failed sync state consistently.
- Acceptance Criteria:
- Every core view (Linear, GitHub, Sprint, Timeline, Workload) shows freshness state.
- Failed connector sync is visible without opening logs/history.
- Sync history screen links back to actionable recovery hints.
- Test Requirements:
- Unit tests for freshness-state mapping and stale threshold logic.
- View tests asserting stale/failure badges render correctly.

### Ticket E1-T2: Deterministic Sync Conflict Policy
- Priority: P0
- Problem: Local cache coherence can degrade with partial/overlapping updates.
- Deliverables:
- Define and enforce deterministic conflict policy (source precedence + updated-at tie-breakers).
- Persist sync cursor/checkpoint per connector resource class.
- Acceptance Criteria:
- Re-running sync on identical upstream data is idempotent.
- Partial failures do not corrupt existing valid cached records.
- Recovery sync after failure converges to expected state.
- Test Requirements:
- Integration tests for idempotence and partial-failure recovery.
- Connector tests for cursor/checkpoint progression.

### Ticket E1-T3: Sync Diagnostics CLI Hardening
- Priority: P0
- Problem: Troubleshooting sync issues is slow and manual.
- Deliverables:
- Expand `pd sync`, `pd sync-github`, and `pd sync-history` outputs with failure category, retry hint, and connector scope.
- Add exit codes suitable for CI/automation checks.
- Acceptance Criteria:
- Operators can identify failure class and affected connector from one command run.
- CLI exits non-zero on sync failure and zero on success/clean no-op.
- Test Requirements:
- CLI tests for exit codes and diagnostic output contracts.

## Epic E2: Issue/PR/CI Unified Action Loop (P0)
### Ticket E2-T1: Linked Issue <-> PR Drilldown Completion
- Priority: P0
- Problem: Cross-navigation exists but does not fully support triage decisions.
- Deliverables:
- Expand drilldown to include PR state, CI summary, review status, and direct actions.
- Ensure jump-back context retention (return to prior issue selection/filter).
- Acceptance Criteria:
- From an issue, user can see linked PR health and execute at least 3 actions without leaving TUI.
- Returning from PR drilldown restores prior issue list context.
- Test Requirements:
- View-navigation tests for drilldown, action execution, and context restore.

### Ticket E2-T2: Triage Filter Pack (`mine`, `blocked`, `failing`, `stale`)
- Priority: P0
- Problem: Leads cannot isolate high-risk work quickly.
- Deliverables:
- Add first-class quick filters and slash-command aliases for triage set.
- Persist last-used filter set per view session.
- Acceptance Criteria:
- Applying any quick filter updates results within target interaction latency.
- Filter state is visible, clearable, and restorable.
- Test Requirements:
- Unit tests for filter composition logic.
- View tests for filter chips/state indicators and clear behavior.

### Ticket E2-T3: Keyboard Action Consistency Pass
- Priority: P0
- Problem: Similar actions differ subtly across views, causing friction.
- Deliverables:
- Standardize action keys and detail panel behavior across core views.
- Add contextual key help entries for issue + PR workflows.
- Acceptance Criteria:
- `Enter`/`Esc` detail behavior is consistent in all core views.
- Action keys for open/copy/jump/status updates follow one shared convention.
- Test Requirements:
- Navigation/action regression tests for shared keymap behavior.

## Epic E3: Blocker Radar and Sprint Risk (P0)
### Ticket E3-T1: Blocked Work Queue
- Priority: P0
- Problem: Blocked issues are scattered and easy to miss.
- Deliverables:
- Add a dedicated blocked queue view mode with age, owner, project, and linked PR/check context.
- Include blocker-age sorting and quick jump to owner/project clusters.
- Acceptance Criteria:
- Users can rank blocked work by age and ownership in one screen.
- Queue can be filtered by project and assignee.
- Test Requirements:
- Data-manager tests for blocked-state derivation and age calculations.
- View tests for queue sorting/filtering behavior.

### Ticket E3-T2: Dependency/Blocker Signals in Timeline
- Priority: P0
- Problem: Timeline risk lacks explicit blocker-chain visibility.
- Deliverables:
- Add visual markers and summary counts for dependencies and blockers per project row.
- Add drill-in shortcut to list contributing blocked issues.
- Acceptance Criteria:
- Timeline highlights projects with active blocker load.
- Drill-in from timeline reveals underlying blocked issues.
- Test Requirements:
- Timeline rendering tests for blocker markers/counts.
- Interaction tests for drill-in flow.

### Ticket E3-T3: Sprint Risk Summary Card
- Priority: P0
- Problem: Leads need a compact risk scan, not only board-level detail.
- Deliverables:
- Add sprint risk summary: blocked count, failing PR count, stale review count, overloaded owners.
- Add thresholds configurable via config/env.
- Acceptance Criteria:
- Summary is visible at sprint entry point and updates after sync.
- Threshold breaches are clearly indicated and actionable.
- Test Requirements:
- Metrics aggregation tests for each summary dimension.
- Config tests for threshold overrides.

## Epic E4: Agent Run Audit Trail (Narrow P1)
### Ticket E4-T1: Agent Run Timeline Linking
- Priority: P1 (slice)
- Problem: Agent execution context is not consistently visible in delivery history.
- Deliverables:
- Link agent runs to issue + PR timeline events with status transitions.
- Show run metadata: prompt fingerprint, runtime mode, start/end timestamps, outcome.
- Acceptance Criteria:
- For an issue with agent activity, timeline includes run lifecycle events in order.
- Users can inspect run metadata from issue/PR context.
- Test Requirements:
- Persistence tests for run-event linking integrity.
- View tests for timeline display and metadata inspection.

### Ticket E4-T2: Limited Launch Action Guardrails
- Priority: P1 (slice)
- Problem: Launching runs without guardrails creates trust/safety risk.
- Deliverables:
- Restrict launch action to configured command template and explicit confirmation.
- Record immutable audit entry for launch initiator, parameters, and command profile.
- Acceptance Criteria:
- Launch is blocked when required config is missing.
- Every launch attempt (success/fail) is auditable from history.
- Test Requirements:
- CLI/action tests for config guardrails and confirmation gating.
- Audit-log tests for launch attempt persistence.

## Cross-Cutting Tickets
### Ticket X1: Performance Budget Validation
- Priority: P0
- Goal: keep core interactions responsive under realistic dataset sizes.
- Acceptance Criteria:
- Core navigation/filter actions meet target median response budget locally.
- Regressions are surfaced in test/dev workflow.

### Ticket X2: Release Readiness Test Matrix
- Priority: P0
- Goal: reduce regressions across connectors and views.
- Acceptance Criteria:
- Test matrix covers sync, mapping, navigation, filters, and issue/PR action loop.
- CI target includes smoke suite for all P0 flows.

## Suggested GitHub Issue Labels
- `priority:P0`
- `priority:P1`
- `area:sync`
- `area:github`
- `area:linear`
- `area:tui`
- `area:agents`
- `type:epic`
- `type:feature`
- `type:hardening`

## Definition of Done (P0 Program)
- IC can complete daily issue triage and PR follow-through in TUI without browser dependency for core checks/actions.
- Tech Lead can identify top blockers/failing work in under 60 seconds.
- Sync freshness and failures are visible and diagnosable from app + CLI.
- P0 test suite is green and covers all critical flows above.

## Expansion Ideas Backlog (To Fold Into Future Roadmaps)
### Immediate P0+ (Issue -> PR -> Merge Loop)
- Issue-to-PR readiness score (spec completeness, linked branch, tests selected, reviewer assigned).
- PR failure triage lane with one-key actions (re-run checks, nudge reviewers, open logs).
- Diff-aware issue detail (PR summary with files touched, LOC, risk heuristics).
- Stale ownership radar (assigned but inactive, last activity age, suggested next action).
- Sync health explain mode from freshness badges (scope, last success, recovery steps).

### P1 Adoption Multipliers
- Agent run compare view (side-by-side diff, prompt fingerprint, run profile).
- Guardrailed action packs (bundled actions with confirmation and audit trail).
- Standup snapshot templates (IC, team, exec styles with deterministic sections).
- PR review cockpit (diff, comments, checks, linked issues, agent suggestions).
- Runbook overlays by issue type (incident, bug, feature) with required steps.

### P2 Org-Scale
- Cross-repo dependency graph (chain visibility, cycle detection, blast radius alerts).
- Portfolio risk rollups (blocked rate, stale reviews, CI flakiness).
- Policy-as-code enforcement (branch/review rules, inline violations, suggested fixes).
- Incident mode light (timeline, ownership, fixes, postmortem export).
- Executive report generator (weekly narrative + charts from unified work graph).

### Foundational Enablers
- Unified event timeline (issues, PRs, checks, agent runs) with stable IDs for linking/analytics.
- Connector extensibility (Jira/GitLab) with identical sync semantics and freshness UX.
- Persona presets (IC/Lead/Manager) for default views, filters, thresholds.
- Search DSL upgrades (boolean, saved queries, one-keystroke triage).
- Local what-if simulations (workload/risk based on estimates or PR outcomes).
