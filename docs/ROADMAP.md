# ProjectDash Roadmap (v0.3)

This roadmap supports a broader ProductDash surface (Linear + GitHub + Agent) while enforcing coherent UX, IA, and flow quality.

## Phase 1: Product Architecture and IA Alignment (Weeks 1-2)
1. Finalize module model: Core, Strategic, Experimental.
2. Define visible navigation system and view hierarchy rules.
3. Establish default profile with sensible starting tabs and compact context bars.
4. Document interaction contract for list/detail panes, drilldown, and return behavior.

## Phase 2: Interaction System Unification (Weeks 2-4)
1. Standardize action vocabulary across Sprint, GitHub, Issue Flow, Timeline, Workload.
2. Reduce command/key alias overload while keeping power-user paths available.
3. Make key help contextual but structurally consistent in every module.
4. Validate discoverability with hidden-state elimination and explicit mode signaling.

## Phase 3: End-to-End User Flow Hardening (Weeks 4-6)
1. IC Flow hardening: triage -> drilldown -> action -> context return.
2. Lead Flow hardening: blocked/failing clustering -> owner/project slicing -> escalation.
3. Cross-system Flow hardening: issue <-> PR <-> checks with low-friction navigation.
4. Add flow-level regression tests for navigation, actions, and state persistence.

## Phase 4: Trust and Reliability Program (Weeks 6-8)
1. Harden sync correctness, freshness rendering, and diagnostic recovery hints.
2. Resolve risk-metric instability (including stale-review expectation logic).
3. Add release gates for core trust suite (sync + metrics + flow regressions).
4. Validate latency budgets for high-frequency interactions and filter operations.

## Phase 5: Agent Workflow Maturity (Weeks 8-10)
1. Promote agent runs as a structured module tied to issue/PR context.
2. Keep launch/dispatch guardrailed with explicit confirmations and profiles.
3. Expand audit timeline linking: input profile, runtime mode, outputs, outcome state.
4. Add tests for launch guardrails, timeline integrity, and failure visibility.

## Phase 6: Strategic Expansion (Post-10 Weeks)
1. Advance workload and timeline analytics for lead/manager routines.
2. Continue ideation and labs as experimental tracks behind flags.
3. Introduce persona presets (IC/Lead/Manager) for defaults, filters, and thresholds.
4. Expand integrations only if they preserve shared interaction semantics.

## Operating Rules
- Rule 1: Breadth is allowed; inconsistency is not.
- Rule 2: Every new module must adopt shared interaction contracts.
- Rule 3: Reliability regressions pause feature expansion until resolved.
- Rule 4: Experimental modules do not crowd core navigation by default.

## Definition of Done
1. Linear, GitHub, and Agent surfaces feel like one product.
2. Core and advanced workflows are both discoverable and cognitively manageable.
3. User flows are test-backed end-to-end, including context restore behavior.
4. Trust indicators and diagnostics are clear enough for daily operational use.
