from dataclasses import dataclass
from datetime import datetime

from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Vertical, Horizontal
from rich.text import Text
from projectdash.widgets.timeline_row import TimelineRow, TimelineRowSelected
from projectdash.models import Issue


@dataclass(frozen=True)
class BlockedQueueRow:
    issue: Issue
    age_days: int
    owner: str
    project: str
    linked_prs: int
    failing_checks: int


@dataclass(frozen=True)
class BlockedProjectSignal:
    blocked_count: int
    failing_checks: int


class TimelineView(Static):
    VISUAL_MODES = ("project", "risk", "progress", "blocked")
    BINDINGS = [
        ("/", "open_filter", "Filter/Search"),
        ("B", "open_project_blocked_drilldown", "Blocker Drilldown"),
        ("question_mark", "toggle_help", "Help"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.visual_mode = "project"
        self.graph_density = "compact"
        self.project_scope_id: str | None = None
        self.selected_project_id: str | None = None
        self.selected_blocked_issue_id: str | None = None
        self._project_order: list[str] = []
        self._blocked_order: list[str] = []
        self.blocked_assignee_mode = "all"
        self.detail_open = False

    def on_mount(self) -> None:
        self.refresh_view()

    def on_show(self) -> None:
        self.refresh_view()

    def compose(self) -> ComposeResult:
        with Horizontal(id="timeline-layout"):
            with Vertical(id="timeline-main"):
                yield Static("📅 TIMELINE", id="view-header")
                yield Static("SYNC FRESHNESS", id="timeline-freshness-label", classes="section-label")
                yield Static("", id="timeline-freshness", classes="placeholder-text")
                yield Static("TIMELINE DATA", classes="section-label")
                yield Vertical(id="timeline-content")
            with Vertical(id="timeline-sidebar", classes="detail-sidebar"):
                yield Static("TIMELINE DETAIL", classes="detail-sidebar-title")
                yield Static("", id="timeline-detail")
                yield Static("", id="timeline-hint", classes="detail-sidebar-hint")

    def refresh_view(self) -> None:
        if self._apply_freshness_visibility():
            self.query_one("#timeline-freshness", Static).update(self._freshness_text())
        metric_set = self.app.metrics.timeline(self.app.data_manager, project_id=self.project_scope_id)
        blocked_signals = self._blocked_project_signals()
        blocked_rows = self._blocked_queue_rows()
        self._blocked_order = [row.issue.id for row in blocked_rows]
        if self.selected_blocked_issue_id and self.selected_blocked_issue_id not in self._blocked_order:
            self.selected_blocked_issue_id = None
        if self.visual_mode == "blocked" and self.selected_blocked_issue_id is None and self._blocked_order:
            self.selected_blocked_issue_id = self._blocked_order[0]
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
            rows, start_index, end_index, total_rows = self._visible_project_rows(metric_set.project_lines)
            if rows:
                for line in rows:
                    is_selected = line.project_id == self.selected_project_id
                    classes = "timeline-row is-selected" if is_selected else "timeline-row"
                    signal = blocked_signals.get(line.project_id, BlockedProjectSignal(blocked_count=0, failing_checks=0))
                    container.mount(
                        TimelineRow(
                            line,
                            selected=is_selected,
                            blocked_count=signal.blocked_count,
                            failing_checks=signal.failing_checks,
                            classes=classes,
                        )
                    )
                if total_rows > len(rows):
                    container.mount(
                        Static(
                            f"Showing {start_index + 1}-{end_index} of {total_rows} projects (PgUp/PgDn page, g detailed).",
                            classes="placeholder-text",
                        )
                    )
                cues_text = self._dependency_cue_text(metric_set)
                if cues_text:
                    container.mount(Static(cues_text, classes="placeholder-text"))
            else:
                container.mount(Static("No project timeline data. Press y to sync.", classes="placeholder-text"))
        elif self.visual_mode == "risk":
            content = self._risk_view(metric_set)
            container.mount(Static(content, classes="placeholder-text"))
        elif self.visual_mode == "progress":
            content = self._progress_view(metric_set)
            container.mount(Static(content, classes="placeholder-text"))
        else:
            content = self._blocked_queue_view(blocked_rows)
            container.mount(Static(content, classes="placeholder-text"))
        self._refresh_detail_panel(metric_set, blocked_rows)

    def toggle_visual_mode(self) -> tuple[bool, str]:
        current_index = self.VISUAL_MODES.index(self.visual_mode)
        self.visual_mode = self.VISUAL_MODES[(current_index + 1) % len(self.VISUAL_MODES)]
        self.refresh_view()
        mode_label = "Blocked Queue" if self.visual_mode == "blocked" else self.visual_mode.title()
        return True, f"Timeline view mode: {mode_label}"

    def toggle_graph_density(self) -> tuple[bool, str]:
        self.graph_density = "detailed" if self.graph_density == "compact" else "compact"
        self.refresh_view()
        return True, f"Timeline graph density: {self.graph_density}"

    def open_primary(self) -> tuple[bool, str]:
        if self.visual_mode == "blocked" and self.selected_blocked_issue_id:
            issue = self.app.data_manager.get_issue_by_id(self.selected_blocked_issue_id)
            if issue:
                # Use standard URL builder if possible
                url = f"https://linear.app/issue/{issue.id}"
                import webbrowser
                try:
                    webbrowser.open_new_tab(url)
                    return True, f"Opened {issue.id} in Linear"
                except Exception as e:
                    return False, f"Failed to open URL: {e}"
        return False, "No primary action for current timeline selection"

    def open_secondary(self) -> tuple[bool, str]:
        return False, "No secondary action for current timeline selection"

    def copy_primary(self) -> tuple[bool, str]:
        target_id = self.selected_blocked_issue_id if self.visual_mode == "blocked" else self.selected_project_id
        if not target_id:
            return False, "No project or issue selected"
        
        # Helper for clipboard
        def _copy(value: str) -> bool:
            import shutil, subprocess
            for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
                if shutil.which(cmd[0]):
                    try:
                        subprocess.run(cmd, input=value, text=True, check=True)
                        return True
                    except Exception:
                        pass
            return False

        if _copy(target_id):
            return True, f"Copied ID: {target_id}"
        return False, "Clipboard tool not found"

    def jump_context(self) -> tuple[bool, str]:
        if self.visual_mode == "blocked" and self.selected_blocked_issue_id:
            self.app.action_switch_tab("sprint")
            sprint = self.app._active_sprint_view()
            if sprint:
                return sprint.focus_issue(self.selected_blocked_issue_id)
        return self.open_project_blocked_drilldown()

    def open_detail(self) -> None:
        if self.visual_mode == "project":
            if self.selected_project_id:
                self.open_project_blocked_drilldown()
                return
        
        if self.visual_mode == "blocked":
            if self.selected_blocked_issue_id is None and self._blocked_order:
                self.selected_blocked_issue_id = self._blocked_order[0]
        
        self.detail_open = True
        self.refresh_view()

    def close_detail(self) -> None:
        if self.detail_open:
            self.detail_open = False
            self.refresh_view()
            return
        
        if self.visual_mode == "blocked":
            self.visual_mode = "project"
            self.project_scope_id = None
            self.refresh_view()
            return

    def action_open_filter(self) -> None:
        if hasattr(self.app, "action_open_filter"):
            self.app.action_open_filter()

    def action_toggle_help(self) -> None:
        if hasattr(self.app, "action_toggle_help_overlay"):
            self.app.action_toggle_help_overlay()

    def context_summary(self) -> dict[str, str]:
        selected = self.selected_project_id or "none"
        filter_label = "none"
        if self.visual_mode == "blocked":
            selected = self.selected_blocked_issue_id or "none"
            filter_label = f"assignee:{self.blocked_assignee_mode}"
        return {
            "mode": self.visual_mode,
            "density": self.graph_density,
            "filter": filter_label,
            "selected": selected,
        }

    def capture_filter_state(self) -> dict[str, object]:
        return {
            "visual_mode": self.visual_mode,
            "graph_density": self.graph_density,
            "project_scope_id": self.project_scope_id,
            "selected_project_id": self.selected_project_id,
            "selected_blocked_issue_id": self.selected_blocked_issue_id,
            "blocked_assignee_mode": self.blocked_assignee_mode,
            "detail_open": self.detail_open,
        }

    def restore_filter_state(self, state: dict[str, object] | None) -> None:
        if not state:
            return
        visual_mode = str(state.get("visual_mode") or self.visual_mode)
        if visual_mode in self.VISUAL_MODES:
            self.visual_mode = visual_mode
        self.graph_density = str(state.get("graph_density") or self.graph_density)
        self.project_scope_id = str(state.get("project_scope_id") or "") or None
        self.selected_project_id = str(state.get("selected_project_id") or "") or None
        self.selected_blocked_issue_id = str(state.get("selected_blocked_issue_id") or "") or None
        blocked_mode = str(state.get("blocked_assignee_mode") or self.blocked_assignee_mode)
        self.blocked_assignee_mode = blocked_mode if blocked_mode in {"all", "mine", "unassigned"} else "all"
        self.detail_open = bool(state.get("detail_open", self.detail_open))
        self.refresh_view()

    def cycle_blocked_assignee_filter(self) -> tuple[bool, str]:
        modes = ("all", "mine", "unassigned")
        current_index = modes.index(self.blocked_assignee_mode)
        self.blocked_assignee_mode = modes[(current_index + 1) % len(modes)]
        self.refresh_view()
        return True, f"Blocked queue assignee filter: {self.blocked_assignee_mode}"

    def jump_blocked_owner_cluster(self, delta: int) -> tuple[bool, str]:
        return self._jump_blocked_cluster("owner", delta)

    def jump_blocked_project_cluster(self, delta: int) -> tuple[bool, str]:
        return self._jump_blocked_cluster("project", delta)

    def open_project_blocked_drilldown(self) -> tuple[bool, str]:
        if not self.selected_project_id:
            return False, "No project selected for blocker drilldown"
        self.visual_mode = "blocked"
        self.project_scope_id = self.selected_project_id
        self.blocked_assignee_mode = "all"
        rows = self._blocked_queue_rows()
        self.selected_blocked_issue_id = rows[0].issue.id if rows else None
        self.detail_open = True
        self.refresh_view()
        if not rows:
            return False, f"No blocked issues for project {self.selected_project_id}"
        return True, f"Blocked drilldown: {len(rows)} issue(s)"

    def _freshness_text(self) -> str:
        return self.app.data_manager.freshness_summary_line(("linear", "github"))

    def _apply_freshness_visibility(self) -> bool:
        visible = bool(getattr(self.app, "sync_freshness_visible", True))
        for widget_id in ("#timeline-freshness-label", "#timeline-freshness"):
            try:
                self.query_one(widget_id, Static).display = visible
            except Exception:
                pass
        return visible

    def _project_header(self, metric_set) -> Text:
        timeline_text = Text()
        timeline_text.append(f"{metric_set.title}\n", style="bold #ffffff")
        timeline_text.append(
            f"{metric_set.subtitle}  |  Mode: Project  |  Graph: {self.graph_density}\n\n",
            style="#666666",
        )
        timeline_text.append("Project             Progress     Points     Due Date     Blockers Status\n", style="bold #666666")
        timeline_text.append("------------------------------------------------------------------------\n", style="#333333")
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
        if self.visual_mode == "blocked":
            if not self._blocked_order:
                return
            if self.selected_blocked_issue_id not in self._blocked_order:
                self.selected_blocked_issue_id = self._blocked_order[0]
                self.refresh_view()
                return
            current_index = self._blocked_order.index(self.selected_blocked_issue_id)
            next_index = (current_index + delta) % len(self._blocked_order)
            self.selected_blocked_issue_id = self._blocked_order[next_index]
            self.refresh_view()
            return
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

    def page_selection(self, delta_pages: int) -> None:
        if self.visual_mode not in {"project", "blocked"}:
            return
        if delta_pages == 0:
            return
        self.move_selection(delta_pages * self._timeline_page_size())

    def _refresh_detail_panel(self, metric_set, blocked_rows: list[BlockedQueueRow]) -> None:
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
            hint.update("Enter opens project detail • r blocked drilldown • PgUp/PgDn page • v mode • g density • ] focus")
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
            hint.update("Enter opens project detail • r blocked drilldown • PgUp/PgDn page • v mode • g density")
            return
        if self.visual_mode == "blocked":
            if not blocked_rows:
                detail.update("No blocked issues in scope.")
                hint.update("v toggle mode • PgUp/PgDn page • ] focus • [ all • /blocked assignee")
                return
            if not self.detail_open or not self.selected_blocked_issue_id:
                detail.update("Select a blocked issue row for detail.\n\nPress Enter to open details.")
                hint.update("Enter open • Esc close • j/k move • PgUp/PgDn page • v mode • /blocked assignee")
                return
            selected = next((row for row in blocked_rows if row.issue.id == self.selected_blocked_issue_id), None)
            if selected is None:
                detail.update("Blocked issue not found.")
                hint.update("j/k move • PgUp/PgDn page • v mode")
                return
            issue = selected.issue
            detail.update(
                f"{issue.id}  ·  {issue.status}\n"
                f"{issue.title}\n\n"
                f"Owner: {selected.owner}\n"
                f"Project: {selected.project}\n"
                f"Age: {selected.age_days}d\n"
                f"Linked PRs: {selected.linked_prs}\n"
                f"Failing checks: {selected.failing_checks}\n"
                f"Priority: {issue.priority}\n"
                f"Due: {issue.due_date or 'N/A'}"
            )
            hint.update("Enter open • Esc close • j/k move • PgUp/PgDn page • v mode • /blocked assignee")
            return
        if not self.detail_open or not self.selected_project_id:
            detail.update("Select a project row for detail.\n\nPress Enter to open details.")
            hint.update("Enter open • r blocked drilldown • Esc close • PgUp/PgDn page • ] focus • [ all • ,/. cycle")
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
        signal = self._blocked_project_signals().get(
            selected.project_id,
            BlockedProjectSignal(blocked_count=0, failing_checks=0),
        )
        detail.update(
            f"{selected.name}\n\n"
            f"Due: {selected.due_date_label}\n"
            f"Progress: {selected.done_points}/{selected.total_points} pts\n"
            f"Completion: {completion_pct}%\n"
            f"Remaining: {remaining_points} pts\n"
            f"Blocked issues: {signal.blocked_count} (failing checks: {signal.failing_checks})\n"
            f"Status: {selected.days_remaining_label}\n"
            f"Graph: {self.graph_density}"
        )
        hint.update("Enter open • r blocked drilldown • Esc close • PgUp/PgDn page • v mode • g density • [ all")

    def _timeline_page_size(self) -> int:
        return 12 if self.graph_density == "detailed" else 6

    def _visible_project_rows(self, project_lines: list) -> tuple[list, int, int, int]:
        total = len(project_lines)
        if total == 0:
            return [], 0, 0, 0
        if self.graph_density == "detailed":
            return project_lines, 0, total, total

        page_size = self._timeline_page_size()
        selected_id = self.selected_project_id
        selected_index = 0
        if selected_id:
            for index, line in enumerate(project_lines):
                if line.project_id == selected_id:
                    selected_index = index
                    break
        start = (selected_index // page_size) * page_size
        end = min(total, start + page_size)
        return project_lines[start:end], start, end, total

    def _blocked_queue_rows(self) -> list[BlockedQueueRow]:
        issues = self.app.data_manager.get_issues()
        if self.project_scope_id:
            issues = [issue for issue in issues if issue.project_id == self.project_scope_id]
        identity_names = self._my_identity_candidates()
        rows: list[BlockedQueueRow] = []
        now = datetime.now()
        for issue in issues:
            if "blocked" not in issue.status.casefold():
                continue
            owner = issue.assignee.name if issue.assignee else "Unassigned"
            owner_key = owner.casefold()
            if self.blocked_assignee_mode == "mine" and owner_key not in identity_names:
                continue
            if self.blocked_assignee_mode == "unassigned" and issue.assignee is not None:
                continue
            project = self._project_label(issue.project_id)
            linked_prs = self.app.data_manager.get_pull_requests(issue.id)
            failing_checks = 0
            for pull_request in linked_prs:
                checks = self.app.data_manager.get_ci_checks(pull_request.id)
                failing_checks += sum(1 for check in checks if self._check_bucket(check.status, check.conclusion) == "failing")
            age_days = max(0, (now - issue.created_at).days)
            rows.append(
                BlockedQueueRow(
                    issue=issue,
                    age_days=age_days,
                    owner=owner,
                    project=project,
                    linked_prs=len(linked_prs),
                    failing_checks=failing_checks,
                )
            )
        rows.sort(key=lambda row: (-row.age_days, row.owner.casefold(), row.issue.id.casefold()))
        return rows

    def _blocked_project_signals(self) -> dict[str, BlockedProjectSignal]:
        issues = self.app.data_manager.get_issues()
        if self.project_scope_id:
            issues = [issue for issue in issues if issue.project_id == self.project_scope_id]
        counts: dict[str, int] = {}
        failing: dict[str, int] = {}
        for issue in issues:
            if "blocked" not in issue.status.casefold():
                continue
            project_id = issue.project_id or "unscoped"
            counts[project_id] = counts.get(project_id, 0) + 1
            pull_requests = self.app.data_manager.get_pull_requests(issue.id)
            fail_count = 0
            for pull_request in pull_requests:
                checks = self.app.data_manager.get_ci_checks(pull_request.id)
                fail_count += sum(1 for check in checks if self._check_bucket(check.status, check.conclusion) == "failing")
            failing[project_id] = failing.get(project_id, 0) + fail_count
        return {
            project_id: BlockedProjectSignal(blocked_count=count, failing_checks=failing.get(project_id, 0))
            for project_id, count in counts.items()
        }

    def _blocked_queue_view(self, rows: list[BlockedQueueRow]) -> Text:
        text = Text()
        text.append("BLOCKED WORK QUEUE\n", style="bold #ffffff")
        text.append(
            f"Mode: Blocked Queue  |  Graph: {self.graph_density}  |  Assignee: {self.blocked_assignee_mode}\n\n",
            style="#666666",
        )
        text.append("Issue      Age  Owner           Project         PRs  Fail  Title\n", style="bold #666666")
        text.append("-----------------------------------------------------------------\n", style="#333333")
        if not rows:
            text.append("No blocked issues in current scope.\n", style="#666666")
            return text
        visible, start, end, total = self._visible_blocked_rows(rows)
        for row in visible:
            marker = ">" if row.issue.id == self.selected_blocked_issue_id else " "
            text.append(
                f"{marker} {row.issue.id[:8].ljust(8)} {str(row.age_days).rjust(3)}d  "
                f"{row.owner[:14].ljust(14)} {row.project[:14].ljust(14)} "
                f"{str(row.linked_prs).rjust(3)}  {str(row.failing_checks).rjust(4)}  "
                f"{row.issue.title[:28]}\n",
                style="#ffffff",
            )
        if total > len(visible):
            text.append(
                f"Showing {start + 1}-{end} of {total} blocked issues (PgUp/PgDn page, g detailed)\n",
                style="#666666",
            )
        return text

    def _visible_blocked_rows(self, rows: list[BlockedQueueRow]) -> tuple[list[BlockedQueueRow], int, int, int]:
        total = len(rows)
        if total == 0:
            return [], 0, 0, 0
        if self.graph_density == "detailed":
            return rows, 0, total, total
        page_size = self._timeline_page_size()
        selected_id = self.selected_blocked_issue_id
        selected_index = 0
        if selected_id:
            for index, row in enumerate(rows):
                if row.issue.id == selected_id:
                    selected_index = index
                    break
        start = (selected_index // page_size) * page_size
        end = min(total, start + page_size)
        return rows[start:end], start, end, total

    def _project_label(self, project_id: str | None) -> str:
        if not project_id:
            return "N/A"
        for project in self.app.data_manager.get_projects():
            if project.id == project_id:
                return project.name
        return project_id

    def _jump_blocked_cluster(self, field: str, delta: int) -> tuple[bool, str]:
        if self.visual_mode != "blocked":
            return False, "Blocked cluster jump is only available in blocked queue mode"
        rows = self._blocked_queue_rows()
        if not rows:
            return False, "No blocked issues in current scope"
        if self.selected_blocked_issue_id not in [row.issue.id for row in rows]:
            self.selected_blocked_issue_id = rows[0].issue.id
            self.refresh_view()
            return True, f"Selected {rows[0].issue.id}"
        current_index = next(
            (index for index, row in enumerate(rows) if row.issue.id == self.selected_blocked_issue_id),
            0,
        )
        current_row = rows[current_index]
        current_value = current_row.owner if field == "owner" else current_row.project
        direction = 1 if delta >= 0 else -1
        for offset in range(1, len(rows)):
            index = (current_index + direction * offset) % len(rows)
            row = rows[index]
            candidate_value = row.owner if field == "owner" else row.project
            if candidate_value != current_value:
                self.selected_blocked_issue_id = row.issue.id
                self.refresh_view()
                return True, f"Jumped to {field} cluster: {candidate_value}"
        return False, f"No alternate {field} cluster in current queue"

    @staticmethod
    def _my_identity_candidates() -> set[str]:
        import os

        candidates = {"me"}
        for env_name in ("PD_ME", "USER", "GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
            value = os.getenv(env_name)
            if value:
                candidates.add(value.strip().casefold())
        return candidates

    @staticmethod
    def _check_bucket(status: str | None, conclusion: str | None) -> str:
        normalized_status = (status or "").casefold()
        if normalized_status != "completed":
            return "pending"
        normalized_conclusion = (conclusion or "").casefold()
        if normalized_conclusion in {"success", "neutral", "skipped"}:
            return "passing"
        if normalized_conclusion in {
            "failure",
            "cancelled",
            "timed_out",
            "action_required",
            "startup_failure",
            "stale",
        }:
            return "failing"
        if normalized_conclusion:
            return "failing"
        return "pending"

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
