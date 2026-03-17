import os
import re
import shlex
import shutil
import subprocess
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static
from rich.text import Text

from projectdash.models import Issue
from projectdash.services.metrics import SprintRiskMetric
from projectdash.widgets.issue_card import IssueCard, IssueCardSelected
from projectdash.widgets.triage_chips import TriageFilterChips
from projectdash.views.sprint_issue import SprintIssueScreen


class SprintBoardView(Static):
    BINDINGS = [
        ("/", "open_filter", "Filter/Search"),
        ("question_mark", "toggle_help", "Help"),
    ]
    COMPACT_SIDEBAR_WIDTH = 36
    EXPANDED_SIDEBAR_WIDTH = 56
    TRIAGE_FILTERS = ("mine", "blocked", "failing", "stale")
    DEFAULT_TRIAGE_STALE_DAYS = 7

    FILTER_KEY_ALIASES = {
        "status": "status",
        "state": "status",
        "priority": "priority",
        "prio": "priority",
        "assignee": "assignee",
        "owner": "assignee",
        "id": "id",
        "key": "id",
        "project": "project",
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.project_scope_id: str | None = None
        self.visual_mode = "kanban"  # kanban or blocked
        self.column_metrics = []
        self.raw_column_metrics = []
        self.cursor_col = 0
        self.cursor_row = 0
        self.selected_issue_id: str | None = None
        self.detail_open = False
        self.filter_active = False
        self.filter_query = ""
        self.triage_filters: set[str] = set()
        self._last_cleared_triage_filters: set[str] = set()
        self._issue_positions: dict[str, tuple[int, int]] = {}
        self._issue_cards: dict[str, IssueCard] = {}

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("📋 SPRINT BOARD", id="view-header")
            yield Static("SYNC FRESHNESS", id="sprint-freshness-label", classes="section-label")
            yield Static("", id="sprint-freshness", classes="placeholder-text")
            yield Static("SPRINT SUMMARY", classes="section-label")
            yield Static("", id="sprint-summary", classes="placeholder-text")
            yield TriageFilterChips(
                {name: False for name in self.TRIAGE_FILTERS}, id="sprint-triage-chips"
            )
            with Horizontal(id="sprint-layout"):
                with Vertical(id="sprint-board-pane"):
                    yield Static("KANBAN BOARD", id="board-type-label", classes="section-label")
                    yield Horizontal(id="kanban-row")
                with Vertical(id="sprint-sidebar", classes="detail-sidebar"):
                    yield Static("ISSUE DETAIL", classes="detail-sidebar-title")
                    yield Static("", id="sprint-detail")
                    yield Static("", id="sprint-hint", classes="detail-sidebar-hint")

    def toggle_visual_mode(self) -> tuple[bool, str]:
        if self.visual_mode == "kanban":
            self.visual_mode = "blocked"
        else:
            self.visual_mode = "kanban"
        self.selected_issue_id = None
        self.cursor_col = 0
        self.cursor_row = 0
        self.refresh_view()
        return True, f"Sprint view mode: {self.visual_mode}"

    def refresh_view(self) -> None:
        if self._apply_freshness_visibility():
            self.query_one("#sprint-freshness", Static).update(self._freshness_text())
        
        if self.visual_mode == "blocked":
            metric_set = self.app.metrics.blocked_board(self.app.data_manager, project_id=self.project_scope_id)
            self.query_one("#board-type-label", Static).update("BLOCKED QUEUE")
        else:
            metric_set = self.app.metrics.sprint_board(self.app.data_manager, project_id=self.project_scope_id)
            self.query_one("#board-type-label", Static).update("KANBAN BOARD")

        self.raw_column_metrics = metric_set.columns
        self.column_metrics = self._filter_columns(self.raw_column_metrics, self.filter_query)
        
        # Update risk summary
        risk = metric_set.risk
        risk_lines = []
        
        def _fmt(label, value, breached):
            color = "#ff0000" if breached else "#00ff00"
            status = "!!" if breached else "ok"
            return f"{label:16} {value:3} [{color}]{status}[/]"

        risk_lines.append(_fmt("Blocked Issues", risk.blocked_issues, risk.blocked_breached))
        risk_lines.append(_fmt("Failing PRs", risk.failing_prs, risk.failing_prs_breached))
        risk_lines.append(_fmt("Stale Reviews", risk.stale_reviews, risk.stale_reviews_breached))
        risk_lines.append(_fmt("Overloaded Owners", risk.overloaded_owners, risk.overloaded_owners_breached))
        
        self.query_one("#sprint-summary", Static).update("\n".join(risk_lines))
        self.query_one("#sprint-triage-chips", TriageFilterChips).update_filters(
            {name: name in self.triage_filters for name in self.TRIAGE_FILTERS}
        )
        self._sync_cursor_to_selected_issue()
        self._issue_positions = {}
        self._issue_cards = {}
        kanban_row = self.query_one("#kanban-row", Horizontal)
        kanban_row.remove_children()
        
        for col_index, column_metric in enumerate(self.column_metrics):
            column_widgets = [Static(f"{column_metric.status.upper()} ({len(column_metric.issues)})", classes="col-header")]
            for row_index, issue in enumerate(column_metric.issues):
                self._issue_positions[issue.id] = (col_index, row_index)
                is_selected = col_index == self.cursor_col and row_index == self.cursor_row
                card_classes = "issue-card is-selected" if is_selected else "issue-card"
                card = IssueCard(issue, selected=is_selected, classes=card_classes)
                self._issue_cards[issue.id] = card
                column_widgets.append(card)
            
            column = Vertical(*column_widgets, classes="kanban-col")
            kanban_row.mount(column)
        self._refresh_summary_panel(metric_set.risk)
        self._refresh_detail_panel()
        self._apply_detail_layout()

    def set_project_scope(self, project_id: str | None) -> None:
        self.project_scope_id = project_id
        self.selected_issue_id = None
        self.cursor_col = 0
        self.cursor_row = 0
        self.detail_open = False
        self.refresh_view()

    def preferred_project_id(self) -> str | None:
        issue = self.current_issue()
        return issue.project_id if issue else None

    def open_primary(self) -> tuple[bool, str]:
        return self.open_selected_issue_in_linear()

    def open_secondary(self) -> tuple[bool, str]:
        return self.open_selected_issue_in_editor()

    def copy_primary(self) -> tuple[bool, str]:
        issue = self.current_issue()
        if issue is None:
            return False, "No issue selected"
        if self._copy_to_clipboard(issue.id):
            return True, f"Copied issue ID: {issue.id}"
        return False, "Clipboard tool not found"

    def jump_context(self) -> tuple[bool, str]:
        issue = self.current_issue()
        if issue is None:
            return False, "No issue selected"
        self.app.action_switch_tab("github")
        github = self.app._active_github_view()
        if github is None:
            return False, "GitHub dashboard unavailable"
        return github.focus_issue(issue.id)

    def open_detail(self) -> None:
        if self.detail_open:
            current = self.current_issue()
            if current:
                self.app.push_screen(SprintIssueScreen(current.id))
            return
        self.open_selected_issue_detail()

    def close_detail(self) -> None:
        if self.detail_open:
            self.close_issue_detail()
            return
        # Go back to higher project level if unscoped
        if self.project_scope_id:
            self.app.action_level_up()

    def action_open_filter(self) -> None:
        if hasattr(self.app, "action_open_filter"):
            self.app.action_open_filter()

    def action_toggle_help(self) -> None:
        if hasattr(self.app, "action_toggle_help_overlay"):
            self.app.action_toggle_help_overlay()

    def context_summary(self) -> dict[str, str]:
        selected = self.selected_issue_id or (self.current_issue().id if self.current_issue() else "none")
        triage = ",".join(sorted(self.triage_filters)) if self.triage_filters else "none"
        return {
            "mode": "kanban",
            "density": "-",
            "filter": f"{self.filter_query or 'none'} triage:{triage}",
            "selected": selected,
        }

    def capture_filter_state(self) -> dict[str, object]:
        return {
            "visual_mode": self.visual_mode,
            "filter_query": self.filter_query,
            "triage_filters": sorted(self.triage_filters),
            "selected_issue_id": self.selected_issue_id,
            "cursor_col": self.cursor_col,
            "cursor_row": self.cursor_row,
            "detail_open": self.detail_open,
        }

    def restore_filter_state(self, state: dict[str, object] | None) -> None:
        if not state:
            return
        visual_mode = state.get("visual_mode")
        if visual_mode in {"kanban", "blocked"}:
            self.visual_mode = str(visual_mode)
        filter_query = state.get("filter_query")
        triage_filters = state.get("triage_filters")
        if isinstance(filter_query, str):
            self.filter_query = filter_query
        if isinstance(triage_filters, list):
            normalized = {
                str(value).strip().casefold()
                for value in triage_filters
                if str(value).strip().casefold() in self.TRIAGE_FILTERS
            }
            self.triage_filters = normalized
        selected_issue_id = state.get("selected_issue_id")
        self.selected_issue_id = str(selected_issue_id) if isinstance(selected_issue_id, str) else None
        try:
            self.cursor_col = int(state.get("cursor_col", self.cursor_col))
        except (TypeError, ValueError):
            pass
        try:
            self.cursor_row = int(state.get("cursor_row", self.cursor_row))
        except (TypeError, ValueError):
            pass
        self.detail_open = bool(state.get("detail_open", self.detail_open))
        self.filter_active = False
        self.refresh_view()

    def apply_triage_filter(self, name: str) -> tuple[bool, str]:
        normalized = name.strip().casefold()
        if normalized not in self.TRIAGE_FILTERS:
            return False, f"Unknown sprint triage filter: {name}"
        if normalized in self.triage_filters:
            self.triage_filters.remove(normalized)
            state_label = "off"
        else:
            self.triage_filters.add(normalized)
            state_label = "on"
        self.filter_active = False
        self.refresh_view()
        return (
            True,
            f"Sprint triage {normalized}: {state_label} ({self._filtered_issue_count()} issue(s))",
        )

    def clear_triage_filters(self) -> tuple[bool, str]:
        if not self.triage_filters:
            return False, "No sprint triage filters active"
        self._last_cleared_triage_filters = set(self.triage_filters)
        self.triage_filters.clear()
        self.filter_active = False
        self.refresh_view()
        return True, "Sprint triage filters cleared"

    def restore_triage_filters(self) -> tuple[bool, str]:
        if not self._last_cleared_triage_filters:
            return False, "No sprint triage filters to restore"
        self.triage_filters = set(self._last_cleared_triage_filters)
        self.filter_active = False
        self.refresh_view()
        active = ",".join(sorted(self.triage_filters))
        return True, f"Sprint triage filters restored: {active}"

    def move_cursor(self, col_delta: int = 0, row_delta: int = 0) -> None:
        if not self.column_metrics:
            return
        previous_issue_id = self.current_issue().id if self.current_issue() else None
        if col_delta:
            self.cursor_col = (self.cursor_col + col_delta) % len(self.column_metrics)
        else:
            self.cursor_col = max(0, min(self.cursor_col, len(self.column_metrics) - 1))
        max_row = max(0, len(self.column_metrics[self.cursor_col].issues) - 1)
        self.cursor_row = max(0, min(self.cursor_row + row_delta, max_row))
        current = self.current_issue()
        self.selected_issue_id = current.id if current else None
        if self._issue_cards:
            self._update_issue_selection(previous_issue_id, self.selected_issue_id)
            self._refresh_detail_panel()
            return
        self.refresh_view()

    def page_selection(self, delta_pages: int) -> None:
        if delta_pages == 0:
            return
        self.move_cursor(row_delta=delta_pages * 5)

    def start_filter(self) -> tuple[bool, str]:
        self.filter_active = True
        self._refresh_detail_panel()
        return (
            True,
            "Filter mode: text or key:value (status/priority/assignee/id/project). Enter keeps, Esc clears.",
        )

    def append_filter_character(self, value: str) -> None:
        if not value:
            return
        self.filter_query += value
        self.refresh_view()

    def backspace_filter(self) -> None:
        if not self.filter_query:
            return
        self.filter_query = self.filter_query[:-1]
        self.refresh_view()

    def commit_filter(self) -> tuple[bool, str]:
        self.filter_active = False
        self.refresh_view()
        return True, f"Filter applied: {self._filtered_issue_count()} issue(s)"

    def clear_filter(self) -> tuple[bool, str]:
        self.filter_active = False
        self.filter_query = ""
        self.selected_issue_id = None
        self.refresh_view()
        return True, "Filter cleared"

    def jump_to_my_issue(self) -> tuple[bool, str]:
        target_names = self._my_identity_candidates()
        for col_index, column in enumerate(self.column_metrics):
            for row_index, issue in enumerate(column.issues):
                if issue.assignee and issue.assignee.name.casefold() in target_names:
                    self.cursor_col = col_index
                    self.cursor_row = row_index
                    self.selected_issue_id = issue.id
                    self.refresh_view()
                    return True, f"Jumped to {issue.id}"
        if self.filter_query:
            return False, "No matching issue assigned to you in current filter"
        return False, "No issues assigned to you"

    def open_selected_issue_detail(self) -> None:
        self.detail_open = True
        current = self.current_issue()
        self.selected_issue_id = current.id if current else None
        self._refresh_detail_panel()
        self._apply_detail_layout()

    def focus_issue(self, issue_id: str) -> tuple[bool, str]:
        if not issue_id:
            return False, "No issue id provided"
        self.filter_active = False
        self.filter_query = ""
        self.triage_filters = set()
        self._last_cleared_triage_filters = set()
        self.refresh_view()
        if not self._select_issue_by_id(issue_id):
            return False, f"Issue not found in board: {issue_id}"
        self.detail_open = True
        self.refresh_view()
        return True, f"Focused issue {issue_id}"

    def close_issue_detail(self) -> None:
        self.detail_open = False
        self._refresh_detail_panel()
        self._apply_detail_layout()

    def on_issue_card_selected(self, message: IssueCardSelected) -> None:
        if self.filter_active:
            return
        previous_issue_id = self.current_issue().id if self.current_issue() else None
        if self._select_issue_by_id(message.issue_id):
            self.detail_open = True
            self._update_issue_selection(previous_issue_id, self.selected_issue_id)
            self._refresh_detail_panel()
            self._apply_detail_layout()

    async def cycle_selected_status(self) -> tuple[bool, str]:
        issue = self.current_issue()
        if issue is None:
            return False, "No issue selected"
        ok, message = await self.app.data_manager.cycle_issue_status(
            issue.id, self.app.config.kanban_statuses
        )
        self.selected_issue_id = issue.id
        self.refresh_view()
        return ok, message

    async def cycle_selected_assignee(self) -> tuple[bool, str]:
        issue = self.current_issue()
        if issue is None:
            return False, "No issue selected"
        ok, message = await self.app.data_manager.cycle_issue_assignee(issue.id)
        self.selected_issue_id = issue.id
        self.refresh_view()
        return ok, message

    async def cycle_selected_points(self) -> tuple[bool, str]:
        issue = self.current_issue()
        if issue is None:
            return False, "No issue selected"
        ok, message = await self.app.data_manager.cycle_issue_points(issue.id)
        self.selected_issue_id = issue.id
        self.refresh_view()
        return ok, message

    async def close_selected_issue(self) -> tuple[bool, str]:
        issue = self.current_issue()
        if issue is None:
            return False, "No issue selected"
        statuses = self.app.config.kanban_statuses
        if not statuses:
            return False, "No configured statuses"

        done_statuses = {status.casefold() for status in self.app.config.done_statuses}
        if not done_statuses:
            done_statuses = {statuses[-1].casefold()}
        if issue.status.casefold() in done_statuses:
            return True, f"{issue.id} is already closed ({issue.status})"

        attempts = len(statuses) + 1
        for _ in range(attempts):
            ok, message = await self.app.data_manager.cycle_issue_status(issue.id, statuses)
            if not ok:
                return False, message
            if issue.status.casefold() in done_statuses:
                self.selected_issue_id = issue.id
                self.refresh_view()
                return True, f"{issue.id} closed as {issue.status}"
        return False, f"Unable to close {issue.id} with configured statuses"

    def open_selected_issue_in_linear(self) -> tuple[bool, str]:
        issue = self.current_issue()
        if issue is None:
            return False, "No issue selected"
        url = self._linear_issue_url(issue)
        try:
            opened = webbrowser.open_new_tab(url)
        except Exception as error:
            return False, f"Failed to open Linear URL: {error}"
        if opened:
            return True, f"Opened {issue.id} in Linear"
        return False, f"Could not launch browser. Open manually: {url}"

    def open_selected_issue_in_editor(self) -> tuple[bool, str]:
        issue = self.current_issue()
        if issue is None:
            return False, "No issue selected"
        command = os.getenv("PD_CODE_EDITOR_CMD", "").strip()
        if not command:
            if shutil.which("code"):
                command = "code {project_root}"
            elif shutil.which("cursor"):
                command = "cursor {project_root}"
            else:
                return False, "Set PD_CODE_EDITOR_CMD to launch a code editor"
        return self._launch_issue_command(command, issue, action_label="Opened code editor")

    def draft_comment_for_selected_issue(self) -> tuple[bool, str]:
        issue = self.current_issue()
        if issue is None:
            return False, "No issue selected"
        draft_path = self._ensure_comment_draft(issue)
        command = os.getenv("PD_COMMENT_EDITOR_CMD", "").strip()
        if not command:
            command = os.getenv("PD_CODE_EDITOR_CMD", "").strip()
        if not command:
            if shutil.which("code"):
                command = "code {comment_file}"
            elif shutil.which("cursor"):
                command = "cursor {comment_file}"
        if not command:
            return True, f"Comment draft ready: {draft_path}"
        return self._launch_issue_command(
            command,
            issue,
            comment_file=draft_path,
            action_label="Opened comment draft",
        )

    def open_selected_issue_in_terminal_editor(self) -> tuple[bool, str]:
        issue = self.current_issue()
        if issue is None:
            return False, "No issue selected"
        draft_path = self._ensure_comment_draft(issue)
        command = os.getenv("PD_TERMINAL_EDITOR_CMD", "").strip()
        if not command:
            return (
                False,
                f"Draft ready at {draft_path}. Set PD_TERMINAL_EDITOR_CMD to auto-launch a terminal editor.",
            )
        return self._launch_issue_command(
            command,
            issue,
            comment_file=draft_path,
            action_label="Opened terminal editor",
        )

    def _freshness_text(self) -> str:
        return self.app.data_manager.freshness_summary_line(("linear", "github"))

    def _apply_freshness_visibility(self) -> bool:
        visible = bool(getattr(self.app, "sync_freshness_visible", True))
        for widget_id in ("#sprint-freshness-label", "#sprint-freshness"):
            try:
                self.query_one(widget_id, Static).display = visible
            except Exception:
                pass
        return visible

    def current_issue(self) -> Issue | None:
        if not self.column_metrics:
            return None
        if self.cursor_col >= len(self.column_metrics):
            return None
        issues = self.column_metrics[self.cursor_col].issues
        if not issues:
            return None
        if self.cursor_row >= len(issues):
            return None
        return issues[self.cursor_row]

    def _sync_cursor_to_selected_issue(self) -> None:
        if not self.column_metrics:
            self.cursor_col = 0
            self.cursor_row = 0
            return
        if self.selected_issue_id:
            for col_index, column in enumerate(self.column_metrics):
                for row_index, issue in enumerate(column.issues):
                    if issue.id == self.selected_issue_id:
                        self.cursor_col = col_index
                        self.cursor_row = row_index
                        return
        self.cursor_col = max(0, min(self.cursor_col, len(self.column_metrics) - 1))
        issues = self.column_metrics[self.cursor_col].issues
        self.cursor_row = max(0, min(self.cursor_row, max(0, len(issues) - 1)))
        current = self.current_issue()
        self.selected_issue_id = current.id if current else None

    def _refresh_detail_panel(self) -> None:
        detail = self.query_one("#sprint-detail", Static)
        hint = self.query_one("#sprint-hint", Static)
        issue = self.current_issue()
        filter_text = self.filter_query or "none"
        scope_label = self._project_scope_label()
        if self.filter_active:
            triage_text = ", ".join(sorted(self.triage_filters)) if self.triage_filters else "none"
            detail.update(
                f"FILTER\n"
                f"{self.filter_query}_\n"
                f"Matches: {self._filtered_issue_count()}\n"
                f"Triage: {triage_text}\n"
                f"Search text + key:value (status/priority/assignee/id/project).\n"
                f"Scope: {scope_label}"
            )
            hint.update("Type to search. Enter: keep filter. Esc: clear filter.")
            return
        if issue is None:
            detail.update(
                "No issue selected.\n"
                f"Visible issues: {self._filtered_issue_count()}\n"
                f"Filter: {filter_text}\n"
                f"Scope: {scope_label}"
            )
            hint.update("j/k h/l move • / filter • ,/. project • ] focus • [ all")
            return
        assignee_name = issue.assignee.name if issue.assignee else "Unassigned"
        project_name = self._project_name(issue.project_id)
        linked_prs = self.app.data_manager.get_pull_requests(issue.id)
        pr_label = f"{len(linked_prs)} linked PR(s)"
        top_prs = linked_prs[:3]
        top_pr_lines = (
            "\n".join(f"- #{pr.number} [{pr.state}] {pr.title}" for pr in top_prs)
            if top_prs
            else "- none"
        )
        if not self.detail_open:
            detail.update(
                "ISSUE PREVIEW\n"
                f"{issue.id}  ·  {issue.status}\n"
                f"{issue.title}\n\n"
                f"Assignee: {assignee_name}\n"
                f"Priority: {issue.priority}\n"
                f"Points: {issue.points}\n"
                f"Project: {project_name}\n"
                f"GitHub: {pr_label}\n"
                f"Filter: {filter_text}\n"
                f"Scope: {scope_label}\n\n"
                "Press Enter to expand details."
            )
            hint.update(
                "Enter expand • r github links • P issue flow • m move • x close • c comment • o linear • p editor • T terminal"
            )
            return
        linear_url = self._linear_issue_url(issue)
        comment_file = self._issue_comment_path(issue)
        detail.update(
            f"{issue.id}  ·  {issue.status}\n"
            f"{issue.title}\n\n"
            f"Assignee: {assignee_name}\n"
            f"Priority: {issue.priority}\n"
            f"Points: {issue.points}\n"
            f"Due: {issue.due_date or 'N/A'}\n"
            f"Project: {project_name}\n"
            f"Created: {issue.created_at.strftime('%Y-%m-%d') if issue.created_at else 'N/A'}\n"
            f"Linear URL: {linear_url}\n"
            f"Comment Draft: {comment_file}\n"
            f"GitHub: {pr_label}\n"
            f"{top_pr_lines}\n"
            f"Filter: {filter_text}\n"
            f"Scope: {scope_label}\n\n"
            "NEXT STEPS\n"
            "[r] GitHub links\n"
            "[m] Move status   [x] Close issue\n"
            "[a] Reassign      [e] Change estimate\n"
            "[c] Comment draft [o] Open in Linear\n"
            "[p] Open editor   [T] Terminal note"
        )
        hint.update(
            "Enter item view • Esc compact • PgUp/PgDn page • P issue flow • m/x/a/e update • c/o/p/T next steps • ,/. project"
        )

    def _refresh_summary_panel(self, risk: SprintRiskMetric) -> None:
        summary = self.query_one("#sprint-summary", Static)
        total_issues = self._filtered_issue_count()
        if not self.column_metrics:
            summary.update("No sprint data available. Press y to sync.")
            return
        max_count = max((len(column.issues) for column in self.column_metrics), default=1)
        width = 14
        text = Text()
        text.append("BOARD SUMMARY\n", style="bold #ffffff")
        triage_text = ", ".join(sorted(self.triage_filters)) if self.triage_filters else "none"
        text.append(f"Triage: {triage_text}\n", style="#cccccc")
        if self.filter_query:
            text.append(f"Filter: {self.filter_query} ({total_issues} matches)\n", style="#cccccc")
        else:
            text.append(f"Visible issues: {total_issues}\n", style="#cccccc")
        text.append_text(self._sprint_risk_text(risk))
        for column in self.column_metrics:
            count = len(column.issues)
            filled = int((count / max_count) * width) if max_count else 0
            bar = "█" * filled + "░" * (width - filled)
            text.append(f"{column.status[:10].ljust(10)} {bar} {count}\n", style="#ffffff")
        assignee_counts: dict[str, int] = {}
        for column in self.column_metrics:
            for issue in column.issues:
                name = issue.assignee.name if issue.assignee else "Unassigned"
                assignee_counts[name] = assignee_counts.get(name, 0) + 1
        if assignee_counts:
            hotspot_name, hotspot_count = sorted(
                assignee_counts.items(),
                key=lambda row: (row[1], row[0]),
                reverse=True,
            )[0]
            text.append(f"Top load: {hotspot_name} ({hotspot_count} issues)", style="#cccccc")
        summary.update(text)

    def _sprint_risk_text(self, risk: SprintRiskMetric) -> Text:
        text = Text()
        text.append("Risk:\n", style="bold #ffffff")
        self._append_risk_line(
            text,
            "blocked",
            risk.blocked_issues,
            risk.blocked_breached,
            f">={self.app.config.sprint_risk_blocked_threshold}",
        )
        self._append_risk_line(
            text,
            "failing PRs",
            risk.failing_prs,
            risk.failing_prs_breached,
            f">={self.app.config.sprint_risk_failing_pr_threshold}",
        )
        self._append_risk_line(
            text,
            "stale reviews",
            risk.stale_reviews,
            risk.stale_reviews_breached,
            (
                f">={self.app.config.sprint_risk_stale_review_threshold} "
                f"@{self.app.config.sprint_risk_stale_review_days}d"
            ),
        )
        self._append_risk_line(
            text,
            "overloaded owners",
            risk.overloaded_owners,
            risk.overloaded_owners_breached,
            (
                f">={self.app.config.sprint_risk_overloaded_owners_threshold} "
                f"@{self.app.config.sprint_risk_overloaded_utilization_pct}%"
            ),
        )
        return text

    def _append_risk_line(
        self,
        text: Text,
        label: str,
        value: int,
        breached: bool,
        threshold_text: str,
    ) -> None:
        status_label = "BREACH" if breached else "ok"
        status_style = "bold #ff5f5f" if breached else "bold #5fd787"
        text.append(f"  {label} {value} [", style="#cccccc")
        text.append(status_label, style=status_style)
        text.append(f" {threshold_text}]\n", style="#cccccc")

    def _project_name(self, project_id: str | None) -> str:
        if not project_id:
            return "N/A"
        for project in self.app.data_manager.get_projects():
            if project.id == project_id:
                return project.name
        return project_id

    def _select_issue_by_id(self, issue_id: str) -> bool:
        position = self._issue_positions.get(issue_id)
        if position:
            self.cursor_col, self.cursor_row = position
            self.selected_issue_id = issue_id
            return True
        for col_index, column in enumerate(self.column_metrics):
            for row_index, issue in enumerate(column.issues):
                if issue.id == issue_id:
                    self.cursor_col = col_index
                    self.cursor_row = row_index
                    self.selected_issue_id = issue_id
                    return True
        return False

    def _update_issue_selection(self, previous_issue_id: str | None, current_issue_id: str | None) -> None:
        if previous_issue_id and previous_issue_id != current_issue_id:
            previous_card = self._issue_cards.get(previous_issue_id)
            if previous_card is not None:
                previous_card.selected = False
                previous_card.remove_class("is-selected")
                previous_card.refresh()
        if current_issue_id:
            current_card = self._issue_cards.get(current_issue_id)
            if current_card is not None:
                current_card.selected = True
                current_card.add_class("is-selected")
                current_card.refresh()

    def _filter_columns(self, columns, query: str):
        keyed_filters, free_terms = self._parse_filter_query(query)
        if not keyed_filters and not free_terms and not self.triage_filters:
            return columns
        filtered = []
        for column in columns:
            issues = [
                issue
                for issue in column.issues
                if self._issue_matches_query(issue, keyed_filters, free_terms)
                and self._issue_matches_triage(issue)
            ]
            filtered.append(type(column)(status=column.status, issues=issues))
        return filtered

    def _issue_matches_query(
        self,
        issue: Issue,
        keyed_filters: dict[str, list[str]],
        free_terms: list[str],
    ) -> bool:
        assignee_name = issue.assignee.name if issue.assignee else ""
        searchable = self._issue_search_blob(issue, assignee_name)
        for term in free_terms:
            if term not in searchable:
                return False

        for key, values in keyed_filters.items():
            if not values:
                continue
            field_value = self._issue_field_blob(issue, key, assignee_name)
            if not any(value in field_value for value in values):
                return False
        return True

    def _issue_search_blob(self, issue: Issue, assignee_name: str) -> str:
        project_name = self._safe_project_name(issue.project_id)
        parts = [
            issue.id,
            issue.title,
            assignee_name,
            issue.priority,
            issue.status,
            issue.project_id or "",
            project_name,
        ]
        return " ".join(parts).casefold()

    def _issue_field_blob(self, issue: Issue, key: str, assignee_name: str) -> str:
        if key == "status":
            return issue.status.casefold()
        if key == "priority":
            return issue.priority.casefold()
        if key == "assignee":
            return assignee_name.casefold()
        if key == "id":
            return issue.id.casefold()
        if key == "project":
            project_name = self._safe_project_name(issue.project_id).casefold()
            project_id = (issue.project_id or "").casefold()
            return f"{project_id} {project_name}".strip()
        return ""

    def _safe_project_name(self, project_id: str | None) -> str:
        if not project_id:
            return ""
        try:
            return self._project_name(project_id)
        except Exception:
            return project_id

    def _issue_matches_triage(self, issue: Issue) -> bool:
        if not self.triage_filters:
            return True
        for triage_filter in self.triage_filters:
            if triage_filter == "mine" and not self._issue_is_mine(issue):
                return False
            if triage_filter == "blocked" and "blocked" not in issue.status.casefold():
                return False
            if triage_filter == "failing" and not self._issue_has_failing_checks(issue):
                return False
            if triage_filter == "stale" and not self._issue_is_stale(issue):
                return False
        return True

    def _issue_is_mine(self, issue: Issue) -> bool:
        if issue.assignee is None:
            return False
        return issue.assignee.name.casefold() in self._my_identity_candidates()

    def _issue_has_failing_checks(self, issue: Issue) -> bool:
        pull_requests = self.app.data_manager.get_pull_requests(issue.id)
        for pull_request in pull_requests:
            checks = self.app.data_manager.get_ci_checks(pull_request.id)
            for check in checks:
                if self._check_bucket(check.status, check.conclusion) == "failing":
                    return True
        return False

    def _issue_is_stale(self, issue: Issue) -> bool:
        stale_days = self._triage_stale_days()
        done_statuses = {status.casefold() for status in self.app.config.done_statuses}
        if issue.status.casefold() in done_statuses:
            return False
        return issue.created_at <= datetime.now() - timedelta(days=stale_days)

    def _triage_stale_days(self) -> int:
        raw = os.getenv("PD_TRIAGE_STALE_DAYS", str(self.DEFAULT_TRIAGE_STALE_DAYS)).strip()
        try:
            return max(1, int(raw))
        except ValueError:
            return self.DEFAULT_TRIAGE_STALE_DAYS

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

    def _parse_filter_query(self, query: str) -> tuple[dict[str, list[str]], list[str]]:
        text = query.strip()
        if not text:
            return {}, []

        pattern = re.compile(r"(?i)\b(status|state|priority|prio|assignee|owner|id|key|project):")
        matches = list(pattern.finditer(text))
        if not matches:
            return {}, self._split_filter_terms(text)

        keyed: dict[str, list[str]] = {}
        consumed_ranges: list[tuple[int, int]] = []
        for index, match in enumerate(matches):
            key = match.group(1).casefold()
            canonical_key = self.FILTER_KEY_ALIASES.get(key)
            value_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            consumed_ranges.append((match.start(), value_end))
            if canonical_key is None:
                continue
            raw_value = text[match.end():value_end].strip()
            if not raw_value:
                continue
            values = self._split_filter_values(raw_value)
            if values:
                keyed.setdefault(canonical_key, []).extend(values)

        free_chunks: list[str] = []
        cursor = 0
        for start, end in consumed_ranges:
            if cursor < start:
                free_chunks.append(text[cursor:start])
            cursor = max(cursor, end)
        if cursor < len(text):
            free_chunks.append(text[cursor:])
        free_text = " ".join(chunk.strip() for chunk in free_chunks if chunk.strip())
        free_terms = self._split_filter_terms(free_text)
        return keyed, free_terms

    def _split_filter_values(self, value_text: str) -> list[str]:
        values = []
        for chunk in value_text.split(","):
            normalized = chunk.strip().strip("\"'")
            if normalized:
                values.append(normalized.casefold())
        return values

    def _split_filter_terms(self, text: str) -> list[str]:
        normalized = text.strip()
        if not normalized:
            return []
        try:
            tokens = shlex.split(normalized)
        except ValueError:
            tokens = normalized.split()
        return [token.casefold() for token in tokens if token.strip()]

    def _project_scope_label(self) -> str:
        if not self.project_scope_id:
            return "All projects"
        return self._project_name(self.project_scope_id)

    def _detail_sidebar_width_cells(self) -> int:
        return self.EXPANDED_SIDEBAR_WIDTH if self.detail_open else self.COMPACT_SIDEBAR_WIDTH

    def _apply_detail_layout(self) -> None:
        try:
            sidebar = self.query_one("#sprint-sidebar", Vertical)
        except Exception:
            return
        sidebar.styles.width = self._detail_sidebar_width_cells()

    def _linear_issue_url(self, issue: Issue) -> str:
        workspace = os.getenv("PD_LINEAR_WORKSPACE", "").strip().strip("/")
        if not workspace:
            workspace = self._issue_team_key(issue)
        if workspace:
            return f"https://linear.app/{workspace}/issue/{issue.id}"
        return f"https://linear.app/issue/{issue.id}"

    def _issue_team_key(self, issue: Issue) -> str:
        team_id = issue.team_id or ""
        if not team_id:
            return ""
        try:
            states = self.app.data_manager.workflow_states_by_team.get(team_id, [])
        except Exception:
            return ""
        for state in states:
            if state.team_key:
                return state.team_key
        return ""

    def _issue_comment_path(self, issue: Issue) -> Path:
        return Path.cwd() / ".projectdash" / "comments" / f"{issue.id}.md"

    def _ensure_comment_draft(self, issue: Issue) -> Path:
        draft_path = self._issue_comment_path(issue)
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        if not draft_path.exists():
            project_name = self._project_name(issue.project_id)
            assignee_name = issue.assignee.name if issue.assignee else "Unassigned"
            draft_path.write_text(
                (
                    f"# {issue.id} - {issue.title}\n\n"
                    f"- Status: {issue.status}\n"
                    f"- Assignee: {assignee_name}\n"
                    f"- Project: {project_name}\n"
                    f"- Linear: {self._linear_issue_url(issue)}\n\n"
                    "## Comment Draft\n\n"
                ),
                encoding="utf-8",
            )
        return draft_path

    def _launch_issue_command(
        self,
        command_template: str,
        issue: Issue,
        *,
        comment_file: Path | None = None,
        action_label: str,
    ) -> tuple[bool, str]:
        context = {
            "project_root": str(Path.cwd()),
            "issue_id": issue.id,
            "issue_title": issue.title,
            "linear_url": self._linear_issue_url(issue),
            "comment_file": str(comment_file) if comment_file else "",
        }
        try:
            formatted_command = command_template.format(**context).strip()
        except KeyError as error:
            return False, f"Invalid command template placeholder: {error}"
        if not formatted_command:
            return False, "Command template is empty"
        try:
            command_parts = shlex.split(formatted_command)
        except ValueError as error:
            return False, f"Failed to parse command template: {error}"
        if not command_parts:
            return False, "Command template produced no executable command"
        executable = command_parts[0]
        if not os.path.isabs(executable) and shutil.which(executable) is None:
            return False, f"Executable not found: {executable}"
        try:
            subprocess.Popen(
                command_parts,
                cwd=Path.cwd(),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as error:
            return False, f"Failed to launch command: {error}"
        return True, f"{action_label}: {formatted_command}"

    def _filtered_issue_count(self) -> int:
        return sum(len(column.issues) for column in self.column_metrics)

    def _my_identity_candidates(self) -> set[str]:
        candidates = {"me"}
        for env_name in ("PD_ME", "USER", "GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
            value = os.getenv(env_name)
            if value:
                candidates.add(value.strip().casefold())
        return candidates
