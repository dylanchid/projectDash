# ProjectDash PRD (v0.3)

## 1. Product Vision
ProjectDash is a terminal-native engineering command center that unifies:
- Linear planning and issue execution
- GitHub PR and CI triage
- Agent-assisted work with auditable runs

It should support more than a minimal tracker, while still feeling coherent, fast, and operationally clear.

## 2. Product Positioning
ProjectDash is a multi-surface product, not a single-screen tool.

The product strategy is:
1. Keep a strong core delivery loop (`Issue -> PR -> Merge`).
2. Add broader planning/risk/agent workflows as first-class modules.
3. Enforce interaction and IA consistency so breadth does not become chaos.

## 3. Primary Users
- ICs: execute issues, track PR health, and run next actions.
- Tech leads: identify blockers/failing work, coordinate delivery risk.
- Engineering managers: review workload/risk and team-level signals.

## 4. Product Pillars
- `Linear`: source of planning truth, priorities, ownership, status.
- `GitHub`: source of code execution truth, reviews, checks, merge readiness.
- `Agent`: acceleration layer with explicit guardrails and auditability.

## 5. Experience Principles
- One interaction model across modules: stable verbs, stable detail behavior.
- One primary focus region at a time: list + detail, with compact context bars.
- Discoverability over cleverness: visible navigation and clear mode indicators.
- Defaults should be useful instantly; complexity should be progressive.
- Reliability signals (freshness/failure) are always visible and actionable.

## 6. Information Architecture
### Core Navigation (Default)
- Sprint
- GitHub
- Issue Flow
- Timeline
- Sync History

### Extended Navigation (Enabled by profile/flag)
- Workload
- Agent Runs / Dispatch
- Ideation Lab

### Navigation Rules
- Tabs are visible.
- Global context bar is compact and consistent.
- Secondary modules cannot break core action vocabulary.

## 7. User Flows
### Flow A: IC Daily Execution
1. Open Sprint/GitHub.
2. Apply quick triage filters (`mine`, `failing`, `stale`).
3. Drill from issue to PR/check state.
4. Execute actions (status, open, copy, jump, assign/comment where applicable).
5. Return to prior filtered context without losing place.

### Flow B: Lead Risk Sweep
1. Open GitHub/Timeline blocked and failing clusters.
2. Rank by age/owner/project.
3. Jump into Issue Flow for cross-system diagnosis.
4. Trigger recovery or escalation actions.

### Flow C: Agent-Assisted Execution
1. Start from issue/PR context.
2. Launch approved agent profile (with confirmation).
3. Track run lifecycle and artifacts in audit timeline.
4. Correlate run outcomes with issue/PR state transitions.

## 8. Scope Policy
### Essential and Must-Harden
- Linear + GitHub sync correctness and freshness.
- Sprint/GitHub triage and issue/PR drilldown.
- Sync diagnostics and recovery path clarity.

### Strategic and Active
- Timeline risk clustering.
- Workload and rebalance insights.
- Agent run queue, dispatch, and audit trail.

### Experimental
- Ideation experiences and advanced labs.
- New high-complexity command packs.

## 9. Configuration Policy
### Core Config
- Connector credentials and explicit repo/workspace targeting.
- Core thresholds (freshness/staleness/risk).
- Default profile and view preferences.

### Advanced Config
- Agent command profiles and runtime policies.
- Capacity/rebalance tuning.
- Experimental feature flags.

## 10. Reliability and Trust
- Deterministic and idempotent sync behavior.
- Failed connector state visible without deep navigation.
- Metrics logic (especially stale/failing risk indicators) must be test-backed.
- Agent launch/dispatch actions require audit entries and guardrails.

## 11. Success Criteria
1. Users can execute core delivery actions quickly without workflow fragmentation.
2. Leads can identify top delivery risk in under 60 seconds.
3. Expanded modules remain consistent in design and interaction semantics.
4. Reliability suite for sync + risk metrics + key flows remains green.
