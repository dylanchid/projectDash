from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Vertical, Horizontal
from rich.text import Text
from projectdash.widgets.timeline_row import TimelineRow, TimelineRowSelected


class TimelineView(Static):
    VISUAL_MODES = ("project", "risk", "progress")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.visual_mode = "project"
        self.graph_density = "compact"
        self.project_scope_id: str | None = None
        self.selected_project_id: str | None = None
        self._project_order: list[str] = []
        self.detail_open = False

    def on_mount(self) -> None:
        self.refresh_view()

    def on_show(self) -> None:
        self.refresh_view()

    def compose(self) -> ComposeResult:
        with Horizontal(id="timeline-layout"):
            with Vertical(id="timeline-main"):
                yield Static("📅 TIMELINE", id="view-header")
                yield Vertical(id="timeline-content")
            with Vertical(id="timeline-sidebar", classes="detail-sidebar"):
                yield Static("TIMELINE DETAIL", classes="detail-sidebar-title")
                yield Static("", id="timeline-detail")
                yield Static("", id="timeline-hint", classes="detail-sidebar-hint")

    def refresh_view(self) -> None:
        metric_set = self.app.metrics.timeline(self.app.data_manager, project_id=self.project_scope_id)
        self._project_order = [line.project_id for line in metric_set.project_lines]
        if self.selected_project_id and not any(
            line.project_id == self.selected_project_id for line in metric_set.project_lines
        ):
            self.selected_project_id = None
        if self.project_scope_id and not self.selected_project_id:
            self.selected_project_id = self.project_scope_id
            self.detail_open = True

        container = self.query_one("#timeline-content", Vertical)
        container.remove_children()
        if self.visual_mode == "project":
            header = Static(self._project_header(metric_set), classes="placeholder-text")
            container.mount(header)
            rows = metric_set.project_lines
            if self.graph_density == "compact":
                rows = rows[:6]
            if rows:
                for line in rows:
                    is_selected = line.project_id == self.selected_project_id
                    classes = "timeline-row is-selected" if is_selected else "timeline-row"
                    container.mount(TimelineRow(line, selected=is_selected, classes=classes))
                cues_text = self._dependency_cue_text(metric_set)
                if cues_text:
                    container.mount(Static(cues_text, classes="placeholder-text"))
            else:
                container.mount(Static("No project timeline data. Press y to sync.", classes="placeholder-text"))
        elif self.visual_mode == "risk":
            content = self._risk_view(metric_set)
            container.mount(Static(content, classes="placeholder-text"))
        else:
            content = self._progress_view(metric_set)
            container.mount(Static(content, classes="placeholder-text"))
        self._refresh_detail_panel(metric_set)

    def toggle_visual_mode(self) -> tuple[bool, str]:
        current_index = self.VISUAL_MODES.index(self.visual_mode)
        self.visual_mode = self.VISUAL_MODES[(current_index + 1) % len(self.VISUAL_MODES)]
        self.refresh_view()
        return True, f"Timeline view mode: {self.visual_mode.title()}"

    def toggle_graph_density(self) -> tuple[bool, str]:
        self.graph_density = "detailed" if self.graph_density == "compact" else "compact"
        self.refresh_view()
        return True, f"Timeline graph density: {self.graph_density}"

    def open_detail(self) -> None:
        if self.visual_mode != "project":
            self.visual_mode = "project"
        if self.selected_project_id is None:
            lines = self.app.metrics.timeline(self.app.data_manager, project_id=self.project_scope_id).project_lines
            if lines:
                self.selected_project_id = lines[0].project_id
        self.detail_open = True
        self.refresh_view()

    def close_detail(self) -> None:
        self.detail_open = False
        self.refresh_view()

    def context_summary(self) -> dict[str, str]:
        selected = self.selected_project_id or "none"
        return {
            "mode": self.visual_mode,
            "density": self.graph_density,
            "filter": "none",
            "selected": selected,
        }

    def _project_header(self, metric_set) -> Text:
        timeline_text = Text()
        timeline_text.append(f"{metric_set.title}\n", style="bold #ffffff")
        timeline_text.append(
            f"{metric_set.subtitle}  |  Mode: Project  |  Graph: {self.graph_density}\n\n",
            style="#666666",
        )
        timeline_text.append("Project             Progress     Points     Due Date     Status\n", style="bold #666666")
        timeline_text.append("---------------------------------------------------------------\n", style="#333333")
        return timeline_text

    def _risk_view(self, metric_set) -> Text:
        timeline_text = Text()
        timeline_text.append("DELIVERY RISK HISTOGRAM\n", style="bold #ffffff")
        timeline_text.append(f"Mode: Due-Risk  |  Graph: {self.graph_density}\n\n", style="#666666")
        buckets = self._risk_bucket_counts(metric_set)
        width = 24 if self.graph_density == "detailed" else 14
        max_value = max(buckets.values()) if buckets else 1
        for name, value in buckets.items():
            filled = int((value / max_value) * width) if max_value else 0
            bar = "█" * filled + "░" * (width - filled)
            symbol = "!!" if name == "Overdue" else "!" if "<=3" in name else "·"
            timeline_text.append(f"{symbol} {name.ljust(8)} {bar} {value}\n", style="#ffffff")
        if self.graph_density == "detailed":
            risky = [
                line for line in metric_set.project_lines
                if line.days_remaining_label.casefold().find("overdue") >= 0
                or line.days_remaining_label.casefold().find("today") >= 0
            ]
            if risky:
                timeline_text.append("\nTop immediate risks:\n", style="bold #666666")
                for line in risky[:4]:
                    timeline_text.append(
                        f"{line.name[:18].ljust(18)} {line.days_remaining_label}\n",
                        style=line.status_color,
                    )
            cues = self._dependency_cues(metric_set)
            if cues:
                timeline_text.append("\nLikely dependency blockers:\n", style="bold #666666")
                for cue in cues[:4]:
                    timeline_text.append(f"{cue}\n", style="#bbbbbb")
        return timeline_text

    def _progress_view(self, metric_set) -> Text:
        timeline_text = Text()
        timeline_text.append("DELIVERY COMPLETION DISTRIBUTION\n", style="bold #ffffff")
        timeline_text.append(f"Mode: Progress  |  Graph: {self.graph_density}\n\n", style="#666666")
        if not metric_set.project_lines:
            timeline_text.append("No projects in scope. Press y to sync.", style="#666666")
            return timeline_text

        buckets = {"0-25%": 0, "26-50%": 0, "51-75%": 0, "76-99%": 0, "100%": 0}
        lagging: list[tuple[int, object]] = []
        for line in metric_set.project_lines:
            pct = self._project_progress_pct(line)
            if pct >= 100:
                buckets["100%"] += 1
            elif pct >= 76:
                buckets["76-99%"] += 1
            elif pct >= 51:
                buckets["51-75%"] += 1
            elif pct >= 26:
                buckets["26-50%"] += 1
            else:
                buckets["0-25%"] += 1
            lagging.append((pct, line))

        width = 24 if self.graph_density == "detailed" else 14
        max_value = max(buckets.values()) if buckets else 1
        for name, value in buckets.items():
            filled = int((value / max_value) * width) if max_value else 0
            bar = "█" * filled + "░" * (width - filled)
            timeline_text.append(f"{name.ljust(7)} {bar} {value}\n", style="#ffffff")

        lagging.sort(key=lambda row: row[0])
        limit = 5 if self.graph_density == "detailed" else 3
        if lagging:
            timeline_text.append("\nLowest completion:\n", style="bold #666666")
            for pct, line in lagging[:limit]:
                remaining = max(0, line.total_points - line.done_points)
                timeline_text.append(
                    f"{line.name[:18].ljust(18)} {pct:>3}%  {remaining} pts left\n",
                    style="#ffffff",
                )
        return timeline_text

    def on_timeline_row_selected(self, message: TimelineRowSelected) -> None:
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
        if self.visual_mode != "project":
            return
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

    def _refresh_detail_panel(self, metric_set) -> None:
        detail = self.query_one("#timeline-detail", Static)
        hint = self.query_one("#timeline-hint", Static)
        if self.visual_mode == "risk":
            buckets = self._risk_bucket_counts(metric_set)
            cue_count = len(self._dependency_cues(metric_set))
            detail.update(
                "Risk Overview\n\n"
                f"Overdue: {buckets['Overdue']}\n"
                f"Due <=3d: {buckets['Due <=3d']}\n"
                f"Due <=7d: {buckets['Due <=7d']}\n"
                f"Due >7d: {buckets['Due >7d']}\n"
                f"No due: {buckets['No due']}\n"
                f"Dependency cues: {cue_count}"
            )
            hint.update("Enter opens project detail • v mode • g density • ] focus")
            return
        if self.visual_mode == "progress":
            if not metric_set.project_lines:
                detail.update("No projects in timeline scope. Press y to sync.")
                hint.update("v toggle mode • g density • ] focus • [ all")
                return
            percentages = [self._project_progress_pct(line) for line in metric_set.project_lines]
            avg_completion = int(sum(percentages) / len(percentages))
            stalled = sum(1 for value in percentages if value <= 25)
            complete = sum(1 for value in percentages if value >= 100)
            detail.update(
                "Progress Overview\n\n"
                f"Average completion: {avg_completion}%\n"
                f"Stalled projects: {stalled}\n"
                f"Completed projects: {complete}\n"
                f"Projects tracked: {len(percentages)}"
            )
            hint.update("Enter opens project detail • v mode • g density")
            return
        if not self.detail_open or not self.selected_project_id:
            detail.update("Select a project row for detail.\n\nPress Enter to open details.")
            hint.update("Enter open • Esc close • ] focus • [ all • ,/. cycle")
            return

        selected = None
        for line in metric_set.project_lines:
            if line.project_id == self.selected_project_id:
                selected = line
                break
        if not selected:
            detail.update("Project not found.")
            hint.update("] focus project • [ all projects • ,/. cycle project")
            return

        completion_pct = self._project_progress_pct(selected)
        remaining_points = max(0, selected.total_points - selected.done_points)
        detail.update(
            f"{selected.name}\n\n"
            f"Due: {selected.due_date_label}\n"
            f"Progress: {selected.done_points}/{selected.total_points} pts\n"
            f"Completion: {completion_pct}%\n"
            f"Remaining: {remaining_points} pts\n"
            f"Status: {selected.days_remaining_label}\n"
            f"Graph: {self.graph_density}"
        )
        hint.update("Enter open • Esc close • v mode • g density • [ all")

    def _risk_bucket_counts(self, metric_set) -> dict[str, int]:
        buckets = {
            "Overdue": 0,
            "Due <=3d": 0,
            "Due <=7d": 0,
            "Due >7d": 0,
            "No due": 0,
        }
        for line in metric_set.project_lines:
            label = line.days_remaining_label
            normalized = label.casefold()
            if "overdue" in normalized:
                buckets["Overdue"] += 1
                continue
            if "due today" in normalized:
                buckets["Due <=3d"] += 1
                continue
            if "d left" in normalized:
                try:
                    days = int(normalized.split("d", 1)[0])
                except ValueError:
                    buckets["No due"] += 1
                    continue
                if days <= 3:
                    buckets["Due <=3d"] += 1
                elif days <= 7:
                    buckets["Due <=7d"] += 1
                else:
                    buckets["Due >7d"] += 1
                continue
            buckets["No due"] += 1
        return buckets

    def _dependency_cues(self, metric_set) -> list[str]:
        overdue = []
        upcoming = []
        for line in metric_set.project_lines:
            progress = self._project_progress_pct(line)
            label = line.days_remaining_label.casefold()
            if "overdue" in label and progress < 80:
                overdue.append(line)
            elif "d left" in label and progress < 85:
                try:
                    days = int(label.split("d", 1)[0])
                except ValueError:
                    continue
                if days <= 7:
                    upcoming.append(line)
        cues: list[str] = []
        if overdue and upcoming:
            blocker = overdue[0]
            for project in upcoming[:4]:
                if project.project_id == blocker.project_id:
                    continue
                cues.append(f"! {project.name[:16]} may depend on overdue {blocker.name[:16]}")
        elif overdue:
            names = ", ".join(project.name[:12] for project in overdue[:3])
            cues.append(f"! Overdue work may block delivery: {names}")
        return cues

    def _dependency_cue_text(self, metric_set) -> str:
        cues = self._dependency_cues(metric_set)
        if not cues:
            return ""
        lines = ["Dependency Cues"]
        lines.extend(cues)
        return "\n".join(lines)

    def _project_progress_pct(self, line) -> int:
        return int((line.done_points / max(1, line.total_points)) * 100)
