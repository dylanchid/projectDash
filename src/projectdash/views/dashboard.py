from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Vertical, Horizontal
from rich.text import Text
from projectdash.widgets.project_card import ProjectCard, ProjectCardSelected


class DashboardView(Static):
    VISUAL_MODES = ("load-total", "load-active", "risk", "priority", "compare")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.visual_mode = "load-total"
        self.chart_density = "compact"
        self.project_scope_id: str | None = None
        self.selected_project_id: str | None = None
        self._project_order: list[str] = []
        self.detail_open = False
        self._sync_marker: str | None = None
        self._sync_baseline = {
            "issues": 0,
            "blocked": 0,
            "velocity": 0,
        }
        self._trend_series = {
            "issues": [],
            "blocked": [],
            "velocity": [],
        }

    def on_mount(self) -> None:
        self.refresh_view()

    def on_show(self) -> None:
        self.refresh_view()

    def compose(self) -> ComposeResult:
        with Horizontal(id="dashboard-layout"):
            with Vertical(id="dashboard-main"):
                yield Static("OVERVIEW", id="view-header")
                with Horizontal(id="stats-row"):
                    yield Static(id="dash-stats-status", classes="stat-card")
                    yield Static(id="dash-stats-performance", classes="stat-card")
                    yield Static(id="dash-stats-network", classes="stat-card")

                yield Static("PROJECTS", classes="section-label")
                yield Horizontal(id="project-cards-row")
                yield Static("CHARTS", classes="section-label")
                yield Static(id="dash-chart", classes="placeholder-text")
            with Vertical(id="dashboard-sidebar", classes="detail-sidebar"):
                yield Static("PROJECT DETAIL", classes="detail-sidebar-title")
                yield Static("", id="dashboard-detail")
                yield Static("", id="dashboard-hint", classes="detail-sidebar-hint")

    def refresh_view(self) -> None:
        metric_set = self.app.metrics.dashboard(self.app.data_manager, project_id=self.project_scope_id)
        self._project_order = [project.project_id for project in metric_set.project_cards]
        scoped_issues = self._scoped_issues()
        if self.selected_project_id and not any(
            project.project_id == self.selected_project_id for project in metric_set.project_cards
        ):
            self.selected_project_id = None
        if self.project_scope_id and not self.selected_project_id:
            self.selected_project_id = self.project_scope_id
            self.detail_open = True

        done_total = self._done_issue_count(scoped_issues)
        done_pct = int((done_total / len(scoped_issues)) * 100) if scoped_issues else 0
        active_pct = int((sum(card.active for card in metric_set.project_cards) / metric_set.issues_total) * 100) if metric_set.issues_total else 0

        self._update_sync_baseline(metric_set)
        self._append_trend("issues", metric_set.issues_total)
        self._append_trend("blocked", metric_set.blocked_total)
        self._append_trend("velocity", metric_set.velocity_points)

        issue_delta = metric_set.issues_total - self._sync_baseline["issues"]
        blocked_delta = metric_set.blocked_total - self._sync_baseline["blocked"]
        velocity_delta = metric_set.velocity_points - self._sync_baseline["velocity"]

        self.query_one("#dash-stats-status", Static).update(Text.assemble(
            ("STATUS\n", "bold #666666"),
            (f"Projects: {metric_set.projects_total}\n", "#ffffff"),
            (f"Issues: {metric_set.issues_total}  {self._delta_label(issue_delta)}\n", "#888888"),
            (f"Trend {self._sparkline(self._trend_series['issues'])}  Done: {done_pct}%", "#777777")
        ))

        self.query_one("#dash-stats-performance", Static).update(Text.assemble(
            ("PERFORMANCE\n", "bold #666666"),
            (f"Velocity: {metric_set.velocity_points} pts  {self._delta_label(velocity_delta)}\n", "#ffffff"),
            (f"Blocked: {metric_set.blocked_total}  {self._delta_label(blocked_delta)}\n", "#888888"),
            (f"Trend {self._sparkline(self._trend_series['velocity'])}  Active: {active_pct}%", "#777777")
        ))

        connected = "✓ Connected" if metric_set.connected else "✕ Offline"
        scope = self._scope_label()
        sync_label = self.app.data_manager.last_sync_at or "no sync"
        self.query_one("#dash-stats-network", Static).update(Text.assemble(
            ("NETWORK\n", "bold #666666"),
            (f"{connected}\n", "#ffffff"),
            (f"Users: {metric_set.loaded_users}  Scope: {scope}\n", "#888888"),
            (f"Baseline: {sync_label[-8:] if sync_label != 'no sync' else sync_label}", "#777777")
        ))

        projects_row = self.query_one("#project-cards-row", Horizontal)
        projects_row.remove_children()
        for project in metric_set.project_cards:
            is_selected = project.project_id == self.selected_project_id
            classes = "project-card is-selected" if is_selected else "project-card"
            projects_row.mount(ProjectCard(project, selected=is_selected, classes=classes))
        if not metric_set.project_cards:
            projects_row.mount(Static("No projects loaded. Press y to sync.", classes="placeholder-text"))

        self.query_one("#dash-chart", Static).update(self._chart_text(metric_set, scoped_issues))
        self._refresh_detail_panel(metric_set, scoped_issues)

    def on_project_card_selected(self, message: ProjectCardSelected) -> None:
        self.selected_project_id = message.project_id
        self.detail_open = True
        self.refresh_view()

    def set_project_scope(self, project_id: str | None) -> None:
        self.project_scope_id = project_id
        if project_id is None:
            self.detail_open = False
        self.selected_project_id = project_id
        self.refresh_view()

    def preferred_project_id(self) -> str | None:
        return self.selected_project_id

    def move_selection(self, delta: int) -> None:
        if not self._project_order:
            return
        if self.selected_project_id not in self._project_order:
            self.selected_project_id = self._project_order[0]
            self.refresh_view()
            return
        current_index = self._project_order.index(self.selected_project_id)
        next_index = (current_index + delta) % len(self._project_order)
        self.selected_project_id = self._project_order[next_index]
        self.refresh_view()

    def open_detail(self) -> None:
        if self.selected_project_id is None:
            cards = self.app.metrics.dashboard(self.app.data_manager, project_id=self.project_scope_id).project_cards
            if cards:
                self.selected_project_id = cards[0].project_id
        self.detail_open = True
        self.refresh_view()

    def close_detail(self) -> None:
        self.detail_open = False
        self.refresh_view()

    def context_summary(self) -> dict[str, str]:
        selected = self._project_label(self.selected_project_id) if self.selected_project_id else "none"
        return {
            "mode": self.visual_mode,
            "density": self.chart_density,
            "filter": "none",
            "selected": selected,
        }

    def toggle_visual_mode(self) -> tuple[bool, str]:
        current_index = self.VISUAL_MODES.index(self.visual_mode)
        self.visual_mode = self.VISUAL_MODES[(current_index + 1) % len(self.VISUAL_MODES)]
        self.refresh_view()
        label_map = {
            "load-total": "Project Load",
            "load-active": "Active Load",
            "risk": "Delivery Risk",
            "priority": "Priority Mix",
            "compare": "Project Compare",
        }
        label = label_map.get(self.visual_mode, self.visual_mode)
        return True, f"Dashboard chart mode: {label}"

    def toggle_graph_density(self) -> tuple[bool, str]:
        self.chart_density = "detailed" if self.chart_density == "compact" else "compact"
        self.refresh_view()
        return True, f"Dashboard chart density: {self.chart_density}"

    def _chart_text(self, metric_set, scoped_issues) -> Text:
        if self.visual_mode in {"load-total", "load-active"}:
            return self._load_chart(metric_set)
        if self.visual_mode == "risk":
            return self._risk_chart(metric_set)
        if self.visual_mode == "priority":
            return self._priority_chart(scoped_issues)
        return self._compare_chart(metric_set)

    def _load_chart(self, metric_set) -> Text:
        text = Text()
        active_mode = self.visual_mode == "load-active"
        mode_label = "ACTIVE LOAD" if active_mode else "TOTAL ISSUES"
        density_label = "DETAIL" if self.chart_density == "detailed" else "COMPACT"
        text.append(f"{mode_label}  |  {density_label}\n", style="bold #666666")
        cards = sorted(
            metric_set.project_cards,
            key=(lambda card: card.active if active_mode else card.total),
            reverse=True,
        )
        limit = 8 if self.chart_density == "detailed" else 4
        rows = cards[:limit]
        max_value = max(
            [card.active if active_mode else card.total for card in rows],
            default=1,
        )
        width = 24 if self.chart_density == "detailed" else 16
        if not rows:
            text.append("No project data available. Press y to sync.", style="#666666")
            return text
        for card in rows:
            value = card.active if active_mode else card.total
            filled = int((value / max_value) * width) if max_value else 0
            bar = "█" * filled + "░" * (width - filled)
            blocked_suffix = f"  blocked {card.blocked}" if self.chart_density == "detailed" else ""
            text.append(f"{card.name[:14].ljust(14)} {bar} {value}{blocked_suffix}\n", style="#ffffff")
        return text

    def _risk_chart(self, metric_set) -> Text:
        text = Text()
        density_label = "DETAIL" if self.chart_density == "detailed" else "COMPACT"
        text.append(f"DELIVERY RISK  |  {density_label}\n", style="bold #666666")
        cards = sorted(
            metric_set.project_cards,
            key=lambda card: (
                int((card.blocked / max(1, card.total)) * 100),
                card.blocked,
                card.total,
            ),
            reverse=True,
        )
        if self.chart_density == "compact":
            cards = cards[:4]
        width = 22 if self.chart_density == "detailed" else 14
        for card in cards:
            risk_pct = int((card.blocked / max(1, card.total)) * 100)
            filled = int((risk_pct / 100) * width)
            bar = "█" * filled + "░" * (width - filled)
            symbol = self._risk_symbol(risk_pct)
            text.append(
                f"{symbol} {card.name[:13].ljust(13)} {bar} {risk_pct:>3}% ({card.blocked}/{card.total})\n",
                style="#ffffff",
            )
        if not cards:
            text.append("No risk data available. Press y to sync.", style="#666666")
        return text

    def _priority_chart(self, scoped_issues) -> Text:
        text = Text()
        density_label = "DETAIL" if self.chart_density == "detailed" else "COMPACT"
        text.append(f"PRIORITY MIX  |  {density_label}\n", style="bold #666666")
        if not scoped_issues:
            text.append("No issues in scope. Press y to sync or clear scope.", style="#666666")
            return text
        buckets = {"Urgent": 0, "High": 0, "Medium": 0, "Low": 0, "No Pri": 0}
        for issue in scoped_issues:
            buckets[self._priority_bucket(issue.priority)] += 1
        max_value = max(buckets.values(), default=1)
        width = 20 if self.chart_density == "detailed" else 12
        for name, value in buckets.items():
            filled = int((value / max_value) * width) if max_value else 0
            bar = "█" * filled + "░" * (width - filled)
            pct = int((value / len(scoped_issues)) * 100) if scoped_issues else 0
            text.append(f"{name.ljust(7)} {bar} {value:>2} ({pct:>2}%)\n", style="#ffffff")
        if self.chart_density == "detailed":
            active_total = sum(
                1
                for issue in scoped_issues
                if issue.status.strip().casefold() in {status.casefold() for status in self.app.config.active_statuses}
            )
            text.append(f"\nActive issues in scope: {active_total}/{len(scoped_issues)}", style="#888888")
        return text

    def _compare_chart(self, metric_set) -> Text:
        text = Text()
        density_label = "DETAIL" if self.chart_density == "detailed" else "COMPACT"
        text.append(f"PROJECT VS TEAM AVG  |  {density_label}\n", style="bold #666666")
        if not metric_set.project_cards:
            text.append("No project data available. Press y to sync.", style="#666666")
            return text
        selected = self._selected_project_metric(metric_set)
        if selected is None:
            text.append("No project selected for comparison.", style="#666666")
            return text

        avg_total = sum(card.total for card in metric_set.project_cards) / len(metric_set.project_cards)
        avg_active = sum(card.active for card in metric_set.project_cards) / len(metric_set.project_cards)
        avg_blocked = sum(card.blocked for card in metric_set.project_cards) / len(metric_set.project_cards)
        text.append(f"Project: {selected.name}\n\n", style="#ffffff")

        width = 18 if self.chart_density == "detailed" else 12
        lines = [
            ("Total", selected.total, avg_total),
            ("Active", selected.active, avg_active),
            ("Blocked", selected.blocked, avg_blocked),
        ]
        max_value = max([project for _label, project, _avg in lines] + [int(avg_total), int(avg_active), int(avg_blocked)] + [1])
        for label, project_value, avg_value in lines:
            project_bar = self._bar(project_value, max_value, width)
            avg_bar = self._bar(int(avg_value), max_value, width)
            text.append(
                f"{label.ljust(7)} P {project_bar} {project_value:>3}  |  A {avg_bar} {int(avg_value):>3}\n",
                style="#ffffff",
            )

        project_risk = int((selected.blocked / max(1, selected.total)) * 100)
        avg_risk = int((avg_blocked / max(1, avg_total)) * 100)
        diff = project_risk - avg_risk
        text.append(
            f"\nRisk {self._risk_symbol(project_risk)} {project_risk}% vs avg {avg_risk}% ({self._delta_label(diff)})",
            style="#888888",
        )
        return text

    def _refresh_detail_panel(self, metric_set, scoped_issues) -> None:
        detail = self.query_one("#dashboard-detail", Static)
        hint = self.query_one("#dashboard-hint", Static)
        if not self.detail_open or not self.selected_project_id:
            detail.update(
                "Select a project to view detail.\n\n"
                f"Scope: {self._scope_label()}\n"
                f"Visual: {self.visual_mode}\n"
                f"Density: {self.chart_density}\n"
                "Press Enter to open details."
            )
            hint.update("Enter open • Esc close • ] focus • [ all • ,/. switch")
            return
        selected = self._selected_project_metric(metric_set)
        if not selected:
            detail.update("Project not found.")
            hint.update("] focus project • [ all projects • ,/. cycle project")
            return
        project_issues = [issue for issue in scoped_issues if issue.project_id == selected.project_id]
        done_total = self._done_issue_count(project_issues)
        done_pct = int((done_total / len(project_issues)) * 100) if project_issues else 0
        active_total = sum(
            1
            for issue in project_issues
            if issue.status.strip().casefold() in {status.casefold() for status in self.app.config.active_statuses}
        )
        top_status = self._top_status_text(project_issues)
        blocker_ratio = int((selected.blocked / max(1, selected.total)) * 100)
        detail.update(
            f"{selected.name}\n\n"
            f"Total issues: {selected.total}\n"
            f"Active: {selected.active} ({active_total} scoped)\n"
            f"Done: {done_total} ({done_pct}%)\n"
            f"Blocked: {selected.blocked} ({self._risk_symbol(blocker_ratio)} {blocker_ratio}%)\n"
            f"Top statuses: {top_status}\n"
            f"Visual: {self.visual_mode}\n"
            f"Chart density: {self.chart_density}"
        )
        hint.update("Enter open • Esc close • v mode • g density • [ all")

    def _scoped_issues(self):
        issues = self.app.data_manager.get_issues()
        if self.project_scope_id:
            issues = [issue for issue in issues if issue.project_id == self.project_scope_id]
        return issues

    def _selected_project_metric(self, metric_set):
        if self.selected_project_id:
            for project in metric_set.project_cards:
                if project.project_id == self.selected_project_id:
                    return project
        if metric_set.project_cards:
            return sorted(metric_set.project_cards, key=lambda card: card.total, reverse=True)[0]
        return None

    def _done_issue_count(self, issues) -> int:
        done_statuses = {status.casefold() for status in self.app.config.done_statuses}
        return sum(1 for issue in issues if issue.status.strip().casefold() in done_statuses)

    def _top_status_text(self, issues) -> str:
        if not issues:
            return "none"
        counts: dict[str, int] = {}
        for issue in issues:
            counts[issue.status] = counts.get(issue.status, 0) + 1
        ordered = sorted(counts.items(), key=lambda row: row[1], reverse=True)
        top_rows = ordered[:3] if self.chart_density == "detailed" else ordered[:2]
        return " | ".join(f"{name}:{count}" for name, count in top_rows)

    def _scope_label(self) -> str:
        if not self.project_scope_id:
            return "All"
        return self._project_label(self.project_scope_id)

    def _project_label(self, project_id: str | None) -> str:
        if not project_id:
            return "none"
        for project in self.app.data_manager.get_projects():
            if project.id == project_id:
                return project.name
        return project_id

    def _priority_bucket(self, raw_priority: str) -> str:
        value = (raw_priority or "").strip().casefold()
        if not value or value in {"0", "none", "no priority", "n/a"}:
            return "No Pri"
        if value in {"1", "urgent", "critical", "critical+"}:
            return "Urgent"
        if value in {"2", "high", "p1"}:
            return "High"
        if value in {"3", "medium", "normal", "p2"}:
            return "Medium"
        if value in {"4", "low", "p3"}:
            return "Low"
        try:
            number = int(value)
        except ValueError:
            return "Medium"
        if number <= 1:
            return "Urgent"
        if number == 2:
            return "High"
        if number == 3:
            return "Medium"
        return "Low"

    def _update_sync_baseline(self, metric_set) -> None:
        marker = self.app.data_manager.last_sync_at or "initial"
        if self._sync_marker == marker:
            return
        self._sync_marker = marker
        self._sync_baseline = {
            "issues": metric_set.issues_total,
            "blocked": metric_set.blocked_total,
            "velocity": metric_set.velocity_points,
        }

    def _append_trend(self, key: str, value: int) -> None:
        series = self._trend_series[key]
        series.append(value)
        if len(series) > 12:
            series.pop(0)

    def _sparkline(self, values: list[int]) -> str:
        if not values:
            return "-"
        if len(values) == 1:
            return "▁"
        blocks = "▁▂▃▄▅▆▇█"
        low = min(values)
        high = max(values)
        spread = max(1, high - low)
        chars = []
        for value in values[-8:]:
            index = int(((value - low) / spread) * (len(blocks) - 1))
            chars.append(blocks[index])
        return "".join(chars)

    def _delta_label(self, delta: int) -> str:
        if delta > 0:
            return f"▲ +{delta}"
        if delta < 0:
            return f"▼ {delta}"
        return "· 0"

    def _risk_symbol(self, risk_pct: int) -> str:
        if risk_pct >= 30:
            return "!!"
        if risk_pct >= 15:
            return "!"
        return "·"

    def _bar(self, value: int, max_value: int, width: int) -> str:
        capped = max(0, value)
        filled = int((capped / max(1, max_value)) * width)
        return "█" * filled + "░" * (width - filled)
