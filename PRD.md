# PRD: ProjectDash (v0.1)

## 1. Vision
A high-speed, terminal-native project manager for developers. An offline-first, minimalist alternative to the Linear web UI.

## 2. Design Principles
- **Minimalist Monochrome:** Pure `#000000` background, `#ffffff` text, `#333333` separators.
- **Typography-First:** Hierarchy via font weight and gray-scaling. No heavy borders or boxes.
- **Keyboard-Centric:** 100% navigable via Vim-style motions (`h/j/k/l`).

## 3. Core Features
### 3.1 Views
- **Dashboard:** Aggregated stats (Velocity, Blocked items, Upcoming milestones).
- **Sprint Board:** Kanban columns (Todo, In Progress, Review, Done).
- **Timeline:** ASCII Gantt chart for roadmap and dependency tracking.
- **Workload:** Team capacity matrix with individual allocations, utilization %, and rebalancing recommendations. Includes issue lists and point totals per member.
- **Issue Detail:** Modal/Panel for descriptions, activity logs, and metadata.

### 3.2 Functionality
- **Linear Sync:** Mirror issues, projects, cycles, and teams from Linear.
- **Offline-First:** Local SQLite cache for instant loading and offline reads.
- **Actionable:** Quick hotkeys for status changes, assignments, and commenting.
- **Natural Search:** Query engine for filtering issues by status, priority, or assignee.
- **Navigation:** Deeply keyboard-centric. Vim-style motions (`h/j/k/l`) for switching tabs, navigating cards, and scrolling.

## 4. Technical Stack
- **Language:** Python 3.12+
- **TUI Framework:** Textual (v0.8.0+)
- **Data Engine:** Linear GraphQL API + SQLite
- **Environment:** `uv` for dependency management.

## 5. Success Criteria
1. **Speed:** Under 100ms for any view transition or search query.
2. **Reliability:** Full functionality (reading) when disconnected from the internet.
3. **Ergonomics:** Zero mouse usage required for daily task management.

## 6. Prototyping Strategy
- **Stage 1: The Shell (UI/UX Prototype):** Build the primary layout using Python + Textual. Implement Dashboard and Sprint Board views with mock data to test navigation, hotkeys, and the "feel" of ASCII visualizations.
- **Stage 2: The Data Engine (Cache & Sync):** Implement the SQLite/JSON storage layer and a basic Linear API client. Decouple data fetching from rendering for a responsive TUI.
- **Stage 3: Interactive Features:** Add "Quick Actions" (assign, status changes), real-time polling, and advanced visualizations.

## 7. Development Roadmap
- **Phase 1 (Active):** UI/UX Shell and Mock Data.
- **Phase 2:** Vim-navigation, Issue Selection, and Detailed View.
- **Phase 3:** SQLite Cache and Linear API Integration.
- **Phase 4:** Interactive Actions and Advanced Charts.
