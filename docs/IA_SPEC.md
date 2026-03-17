# ProjectDash Information Architecture Spec (v0.3)

## 1. Goal
Define a clear, scalable navigation model for Linear + GitHub + Agent workflows without sacrificing discoverability or consistency.

## 2. Module Tiers
### Core Modules (Default On)
- Sprint
- GitHub
- Issue Flow
- Timeline
- Sync History

### Strategic Modules (Profile On by default for Lead/Manager)
- Workload
- Agent Runs

### Experimental Modules (Flag Only)
- Ideation Lab
- Any future non-operational prototype views

## 3. Default Profiles
### IC Profile
- Landing tab: Sprint
- Visible tabs: Sprint, GitHub, Issue Flow, Timeline, Sync History
- Optional tabs off by default: Workload, Agent Runs, Ideation Lab

### Lead Profile
- Landing tab: GitHub
- Visible tabs: Sprint, GitHub, Issue Flow, Timeline, Sync History, Workload, Agent Runs
- Experimental tabs off by default

### Manager Profile
- Landing tab: Timeline
- Visible tabs: Sprint, GitHub, Issue Flow, Timeline, Sync History, Workload, Agent Runs
- Experimental tabs off by default

## 4. Navigation Rules
1. Tabs are always visible.
2. Tab order is stable across profiles.
3. Hidden modules are hidden by profile/flag only, never by accidental styling.
4. Navigation state is shown in a compact global context bar.
5. Returning from drilldown restores prior tab + list selection + filter state.

## 5. Global Layout Contract
- Top: tab row + compact freshness bar.
- Center-left: primary list region.
- Center-right: detail/inspector region.
- Bottom: contextual key hints + transient status line.

## 6. Cross-Module Consistency Rules
1. Every module must expose a list anchor (selectable records).
2. Every module must expose a detail anchor (selected record context).
3. Every module must support uniform back/escape behavior.
4. Every module must surface connector freshness and sync health access.
5. Advanced actions cannot replace baseline core actions.

## 7. Visibility and State
- Persist last active tab per profile.
- Persist last used filter set per core triage module.
- Persist list scroll + selection on tab switch.
- Reset only on explicit user action (not implicit refresh).

## 8. Governance
- New modules must be classified as Core, Strategic, or Experimental.
- Experimental modules cannot enter default IC profile without product review.
- Any module violating interaction contract is blocked from promotion.
