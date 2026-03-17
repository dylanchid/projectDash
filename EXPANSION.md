# ProjectDash Expansion Plan (Living Doc)

## Purpose
Capture and iterate on how ProjectDash can expand from a Linear-focused terminal app into a full engineering project management suite.

## Current State
- ProjectDash today is centered on planning and tracking work from Linear in a terminal-native interface.
- The main strengths are keyboard-first workflows, local speed, and offline-first cache behavior.

## Expansion Thesis
ProjectDash can become an engineering command center where teams:
- Plan work (Linear and related planning systems).
- Execute work (agents, local sessions, automation runs).
- Review and ship work (GitHub PRs, CI status, approvals).
- Measure delivery health (throughput, blockers, latency, ownership).

## Product Pillars
1. Unified Work Graph
- Merge issues, pull requests, commits, reviews, CI checks, and agent run events into one project timeline.

2. Execution Console
- Start execution from an issue and run one or more agents against scoped repos/tasks.
- Track agent runs as first-class records: prompts, diffs, logs, cost, and outcome.

3. Delivery Control
- Define policies for branch rules, test gates, review requirements, and agent permissions.
- Add approval checkpoints for risky actions.

4. Ops Intelligence
- Report lead time, cycle time, review wait time, blocked states, and flow efficiency.
- Compare human-only and agent-assisted delivery performance.

## Key User Workflows
1. Issue -> Execution -> PR -> Done
- Select issue, launch agent run, create PR, sync status back to issue tracker.

2. PR Review Cockpit
- Single screen for PR diff, CI failures, reviewer comments, and agent-suggested fixes.

3. Team Standup Snapshot
- Auto-generate a daily summary from real activity, blockers, and planned next steps.

4. Incident Mode
- Create a shared response room with timeline, ownership, fixes, and postmortem export.

## Integration Surface
- Planning: Linear (first), Jira (later).
- Code Hosting: GitHub (first), GitLab (later).
- Execution Runtime: tmux-backed local sessions first, abstract runtime interface for container/k8s backends later.
- Notifications: Slack and email digests.

## Architecture Direction
- Keep a local-first event store that normalizes external system events.
- Build connectors as modular adapters with retry-safe sync semantics.
- Treat each agent run as an auditable entity linked to issue + branch + PR.
- Isolate runtime orchestration behind a provider interface so tmux is replaceable.

## Phased Rollout
### Phase 1: Foundations
- GitHub sync for PRs/commits/checks.
- Linked Issue + PR experience.
- Single-agent execution path from issue context.
- Basic activity timeline and delivery metrics.

### Phase 2: Team Adoption
- Multi-agent orchestration and queueing.
- PR review cockpit with policy checks.
- Standup snapshot generation.
- Permission model for agent actions.

### Phase 3: Org-Scale
- Cross-repo dependency views.
- Portfolio planning and capacity forecasting.
- Advanced analytics and executive reporting.
- Runtime backends beyond tmux.

## Risks and Constraints
- Scope creep across planning, SCM, and runtime orchestration.
- Security and compliance for agent credentials and repo access.
- Trust and explainability requirements for automated changes.
- Data consistency challenges across systems with different models.

## Success Metrics
- Time from issue start to first PR.
- Time from PR open to merge.
- Percent of work with clear ownership and no stale state.
- Percent of agent-assisted runs that merge without manual rework.
- Weekly active users across planning + execution flows.

## Open Questions
- Should ProjectDash remain terminal-first, or add a companion web control plane?
- What permissions model is required for safe multi-agent execution?
- How much workflow should be opinionated vs user-configurable?
- Should we optimize first for small teams or platform/infra orgs?

## PRD v0.2: Persona and Use-Case Prioritization
### Persona x Use-Case Matrix
| Persona | Core Jobs | Highest-Value Use Cases | Priority |
| --- | --- | --- | --- |
| IC (terminal-native) | Execute assigned work quickly | Solo IC flow, Issue -> PR visibility, personal blocker detection | P0 |
| Tech Lead / Senior IC | Keep delivery unblocked | PR triage desk, dependency/blocker radar, sprint risk scan | P0 |
| Engineering Manager | Maintain throughput and predictability | Sprint health check, workload rebalance, weekly review metrics | P1 |
| AI-enabled IC/Lead | Safely accelerate execution | Issue-to-execution launch, run audit trail, PR-linked agent outcomes | P1 |
| On-call Lead | Coordinate high-pressure fixes | Incident coordination lite (issues + PRs + CI timeline) | P2 |
| Program/Org Lead | Track cross-team initiatives | Multi-repo program tracking, portfolio-level risk rollups | P2 |

### Use-Case Priority Stack
1. P0 (must-win)
- Solo IC flow.
- PR triage desk.
- Dependency/blocker radar (basic).
- Shared issue + PR + CI context with fast keyboard actions.

2. P1 (adoption multipliers)
- Sprint health + workload rebalance.
- Agent run launch/tracking with strict auditability.
- Standup snapshot generation.

3. P2 (org-scale expansion)
- Incident mode.
- Multi-repo program tracking.
- Executive-grade reporting.

### Feature Requirements by Priority
1. P0 required
- Reliable Linear + GitHub sync with freshness indicators.
- Unified issue detail with linked PR/check state.
- Keyboard-first filters (`mine`, `blocked`, `failing`, `stale`).
- Fast issue actions (status/assignee/estimate/comment/open PR).
- Offline cache with deterministic conflict handling.

2. P1 required
- Workload simulation and rebalance recommendations.
- Agent run entity model (prompt, logs, diff refs, outcome, cost).
- Permission guardrails for agent-triggered actions.
- Daily standup digest generation from event history.

3. P2 required
- Cross-repo dependency graphing.
- Incident timeline workspace.
- Portfolio analytics and policy dashboards.

### MVP Cutline
- Build for IC + Tech Lead first.
- Ship P0 plus a narrow P1 slice (agent run tracking, not full orchestration).
- Defer P2 until P0 metrics show meaningful replacement of web workflows.

### Success Metrics by Persona
- IC: median time from app open to first task action.
- Tech Lead: median time to identify top 3 blockers.
- Engineering Manager: weekly reduction in stale/unowned work percentage.
- AI-enabled users: percentage of agent-assisted runs ending in mergeable PRs without major rework.

### 8-Week Execution Plan
1. Weeks 1-2
- Harden sync correctness and freshness UX.

2. Weeks 3-4
- Unify issue/PR/check action loop.
- Optimize triage filters and keyboard workflows.

3. Weeks 5-6
- Ship blocker radar and sprint risk/workload essentials.

4. Weeks 7-8
- Add agent-run audit trail and limited launch action from issue context.

## Iteration Log
Use this section to evolve strategy decisions over time.

| Date | Decision / Update | Why | Owner | Follow-up |
| --- | --- | --- | --- | --- |
| 2026-02-24 | Created initial expansion outline from brainstorming session. | Establish a living direction doc for future planning. | Team | Convert into v1 PRD when buildout starts. |
| 2026-02-25 | Started platform foundation implementation: connector abstraction, expansion schema tables, and agent-run persistence primitives. | De-risk upcoming GitHub/runtime integration by putting core storage and extension points in place. | Team | Build GitHub read-only sync on top of the new schema/connector surfaces. |
| 2026-02-25 | Added read-only GitHub connector flow (repos, PRs, checks), CLI sync path, and issue-detail PR linkage in Sprint view. | Deliver first cross-system bridge between planning and code delivery surfaces. | Team | Add dedicated Issue ↔ PR timeline screen and PR review cockpit interactions. |
| 2026-02-26 | Added PRD v0.2 persona/use-case prioritization with P0/P1/P2 cutline and 8-week plan. | Force scope discipline around Issue -> PR -> Merge loop before broader platform features. | Team | Convert P0 scope into implementation tickets and acceptance metrics. |

## Next Update Triggers
- Major scope change in integrations or runtime direction.
- First implementation milestone for GitHub + agent execution.
- New security/compliance requirements.
- Team feedback after initial dogfooding.
