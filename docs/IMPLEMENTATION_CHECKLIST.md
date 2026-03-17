# ProjectDash IA + Interaction Implementation Checklist

Use this checklist to align existing views with `docs/IA_SPEC.md` and `docs/INTERACTION_CONTRACT.md`.

## 1. Cross-App Foundation
- [ ] Tabs are visible and ordered consistently for all profiles.
- [ ] Profile presets exist for IC, Lead, and Manager.
- [ ] Global context bar shows active tab, filter summary, and freshness summary.
- [ ] Global `Enter`/`Esc`/`/`/`?` semantics are mapped and documented.
- [ ] Navigation context stack supports drilldown push/pop with state restore.

## 2. Sprint View
- [ ] Supports list + detail contract.
- [ ] Supports quick filters (`mine`, `blocked`, `failing`, `stale` where applicable).
- [ ] Uses shared action verbs and key semantics.
- [ ] Preserves selection and scroll during refresh.
- [ ] Exposes freshness and sync-failure visibility.

## 3. GitHub View
- [ ] Supports PR-centric triage with shared quick filters.
- [ ] Supports issue <-> PR/check drilldown using context stack.
- [ ] Uses shared detail open/close behavior.
- [ ] Surfaces failing checks/review state consistently.
- [ ] Exposes freshness and sync-history path.

## 4. Issue Flow View
- [ ] Presents cross-system links with predictable open/back behavior.
- [ ] Uses same filter chip and clearing behavior as GitHub/Sprint.
- [ ] Supports action execution without context loss.
- [ ] Preserves prior state when returning from linked object views.

## 5. Timeline View
- [ ] Maintains list + detail model (project rows + details).
- [ ] Supports blocked/dependency drill-ins via context stack.
- [ ] Uses shared action vocabulary and key semantics.
- [ ] Shows freshness and risk signal summary in compact form.

## 6. Workload View (Strategic)
- [ ] Follows same list/detail and back semantics.
- [ ] Does not introduce conflicting action verbs.
- [ ] Keeps advanced controls discoverable but non-invasive.
- [ ] Honors profile-based visibility and default-off for IC profile.

## 7. Sync History View
- [ ] Is reachable in one step from sync failure indicators.
- [ ] Shows failure category, connector scope, and recovery hint.
- [ ] Supports fast return to prior operational tab/context.

## 8. Agent Runs View (Strategic)
- [ ] Launch/dispatch actions require confirmation.
- [ ] Every launch attempt is auditable (success or failure).
- [ ] Run timeline links to associated issue/PR context.
- [ ] Uses shared open/back/filter/help semantics.

## 9. Test Plan Checklist
- [ ] Flow test: IC path (`triage -> drilldown -> action -> return`).
- [ ] Flow test: Lead path (`risk sweep -> cluster drill -> escalation`).
- [ ] Contract tests for `Enter`/`Esc` semantics in each core module.
- [ ] Filter state persistence tests across tab switches.
- [ ] Freshness/failure visibility tests in all core modules.
- [ ] Metric logic tests for stale/failing/blocked indicators.

## 10. Recommended First Vertical Slice
- [ ] Implement `GitHub -> Issue Flow -> action -> return` with full context restore.
- [ ] Add regression tests for navigation stack + filter/selection persistence.
- [ ] Validate latency and feedback quality for this slice before scaling to other views.
