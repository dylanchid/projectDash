# ProjectDash Interaction Contract (v0.3)

## 1. Purpose
Ensure every view behaves like one product by standardizing actions, drilldowns, and state behavior.

## 2. Global Verbs
- `move`: navigate list rows, tabs, and focus regions.
- `open`: open detail or jump to linked object.
- `back`: return from detail/drilldown to previous context.
- `filter`: apply triage filters and query changes.
- `act`: execute mutations (status/assign/comment/launch/etc.).
- `sync`: refresh connector data and show outcome.
- `help`: show contextual key guide.

## 3. Required Key Semantics
- `Enter`: open selected item detail or linked drill target.
- `Esc`: close current detail/modal and return one level.
- `/`: open filter/search input.
- `Tab` and `Shift+Tab`: cycle focus regions when multiple are active.
- `?`: toggle contextual key help for current module.

Exact letter bindings can vary, but semantics cannot.

## 4. List/Detail Behavior
1. List selection always drives detail content.
2. Detail panel opens without losing list selection.
3. Detail panel close returns focus to same list row.
4. Empty states must show next action hint.
5. Loading states must preserve previous content until replacement is ready.

## 5. Drilldown Contract
### Drilldown Entry
- Opening linked entities (issue -> PR, PR -> checks, timeline row -> blocked queue) pushes a navigation context frame.

### Drilldown Exit
- `Esc` or explicit back pops exactly one frame.
- Return restores origin tab, origin filter set, origin list selection, and origin scroll offset.

## 6. Filter Contract
1. Quick filters (`mine`, `blocked`, `failing`, `stale`) are first-class and visible.
2. Active filters are always visible and individually clearable.
3. Clearing filters does not clear list selection unless selected row disappears.
4. Filter execution must meet responsiveness budget for typical dataset sizes.

## 7. Action Safety Contract
1. Destructive or high-impact actions require explicit confirmation.
2. Agent launch/dispatch always records an audit entry.
3. Failure feedback is immediate and includes recovery hint when available.
4. Success feedback is concise and non-blocking.

## 8. Freshness and Trust Contract
1. Freshness status is visible in every core module.
2. Failed sync status is visible from primary surfaces, not only logs.
3. Sync history is reachable in one action from failure status.
4. Risk indicators (stale/failing/blocked) must map to tested logic.

## 9. Accessibility and Cognitive Load
1. One primary list and one detail panel at a time.
2. No mode-dependent meaning changes for the same key semantic.
3. Help text must use the same verb language as docs.
4. Avoid hidden navigation mechanics as the only discovery path.
