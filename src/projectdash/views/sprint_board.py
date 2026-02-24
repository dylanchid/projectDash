import os
import re
import shlex

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static

from projectdash.models import Issue
from projectdash.widgets.issue_card import IssueCard, IssueCardSelected


class SprintBoardView(Static):
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
        self.column_metrics = []
        self.raw_column_metrics = []
        self.cursor_col = 0
        self.cursor_row = 0
        self.selected_issue_id: str | None = None
        self.detail_open = False
        self.filter_active = False
        self.filter_query = ""
        self._issue_positions: dict[str, tuple[int, int]] = {}

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("📋 SPRINT BOARD", id="view-header")
            yield Static("", id="sprint-summary", classes="placeholder-text")
            with Horizontal(id="sprint-layout"):
                yield Horizontal(id="kanban-row")
                with Vertical(id="sprint-sidebar", classes="detail-sidebar"):
                    yield Static("ISSUE DETAIL", classes="detail-sidebar-title")
                    yield Static("", id="sprint-detail")
                    yield Static("", id="sprint-hint", classes="detail-sidebar-hint")

    def refresh_view(self) -> None:
        metric_set = self.app.metrics.sprint_board(self.app.data_manager, project_id=self.project_scope_id)
        self.raw_column_metrics = metric_set.columns
        self.column_metrics = self._filter_columns(self.raw_column_metrics, self.filter_query)
        self._sync_cursor_to_selected_issue()
        self._issue_positions = {}
        kanban_row = self.query_one("#kanban-row", Horizontal)
        kanban_row.remove_children()
        
        for col_index, column_metric in enumerate(self.column_metrics):
            column_widgets = [Static(f"{column_metric.status.upper()} ({len(column_metric.issues)})", classes="col-header")]
            for row_index, issue in enumerate(column_metric.issues):
                self._issue_positions[issue.id] = (col_index, row_index)
                is_selected = col_index == self.cursor_col and row_index == self.cursor_row
                card_classes = "issue-card is-selected" if is_selected else "issue-card"
                column_widgets.append(IssueCard(issue, selected=is_selected, classes=card_classes))
            
            column = Vertical(*column_widgets, classes="kanban-col")
            kanban_row.mount(column)
        self._refresh_summary_panel()
        self._refresh_detail_panel()

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

    def open_detail(self) -> None:
        self.open_selected_issue_detail()

    def close_detail(self) -> None:
        self.close_issue_detail()

    def context_summary(self) -> dict[str, str]:
        selected = self.selected_issue_id or (self.current_issue().id if self.current_issue() else "none")
        return {
            "mode": "kanban",
            "density": "-",
            "filter": self.filter_query or "none",
            "selected": selected,
        }

    def move_cursor(self, col_delta: int = 0, row_delta: int = 0) -> None:
        if not self.column_metrics:
            return
        if col_delta:
            self.cursor_col = (self.cursor_col + col_delta) % len(self.column_metrics)
        else:
            self.cursor_col = max(0, min(self.cursor_col, len(self.column_metrics) - 1))
        max_row = max(0, len(self.column_metrics[self.cursor_col].issues) - 1)
        self.cursor_row = max(0, min(self.cursor_row + row_delta, max_row))
        current = self.current_issue()
        self.selected_issue_id = current.id if current else None
        self.refresh_view()

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

    def close_issue_detail(self) -> None:
        self.detail_open = False
        self._refresh_detail_panel()

    def on_issue_card_selected(self, message: IssueCardSelected) -> None:
        if self.filter_active:
            return
        if self._select_issue_by_id(message.issue_id):
            self.detail_open = True
            self.refresh_view()

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
            detail.update(
                f"FILTER\n"
                f"{self.filter_query}_\n"
                f"Matches: {self._filtered_issue_count()}\n"
                f"Search text + key:value (status/priority/assignee/id/project).\n"
                f"Scope: {scope_label}"
            )
            hint.update("Type to search. Enter: keep filter. Esc: clear filter.")
            return
        if not self.detail_open:
            detail.update(
                "Select an issue to preview details.\n"
                f"Visible issues: {self._filtered_issue_count()}\n"
                f"Filter: {filter_text}\n"
                f"Scope: {scope_label}\n"
                "Press Enter to open details."
            )
            hint.update("Enter open • Esc close • j/k h/l move • / filter • ] focus")
            return
        if issue is None:
            detail.update(f"No issue selected.\nScope: {scope_label}")
            hint.update("j/k h/l move • / filter • ,/. project • ] focus • [ all")
            return
        assignee_name = issue.assignee.name if issue.assignee else "Unassigned"
        project_name = self._project_name(issue.project_id)
        detail.update(
            f"{issue.id}  ·  {issue.status}\n"
            f"{issue.title}\n\n"
            f"Assignee: {assignee_name}\n"
            f"Priority: {issue.priority}\n"
            f"Points: {issue.points}\n"
            f"Due: {issue.due_date or 'N/A'}\n"
            f"Project: {project_name}\n"
            f"Created: {issue.created_at.strftime('%Y-%m-%d') if issue.created_at else 'N/A'}\n"
            f"Filter: {filter_text}\n"
            f"Scope: {scope_label}"
        )
        hint.update("m status • a assignee • e points • ,/. project • [ all")

    def _refresh_summary_panel(self) -> None:
        summary = self.query_one("#sprint-summary", Static)
        total_issues = self._filtered_issue_count()
        if not self.column_metrics:
            summary.update("No sprint data available. Press y to sync.")
            return
        max_count = max((len(column.issues) for column in self.column_metrics), default=1)
        width = 14
        lines = ["BOARD SUMMARY"]
        if self.filter_query:
            lines.append(f"Filter: {self.filter_query} ({total_issues} matches)")
        else:
            lines.append(f"Visible issues: {total_issues}")
        for column in self.column_metrics:
            count = len(column.issues)
            filled = int((count / max_count) * width) if max_count else 0
            bar = "█" * filled + "░" * (width - filled)
            lines.append(f"{column.status[:10].ljust(10)} {bar} {count}")
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
            lines.append(f"Top load: {hotspot_name} ({hotspot_count} issues)")
        summary.update("\n".join(lines))

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

    def _filter_columns(self, columns, query: str):
        keyed_filters, free_terms = self._parse_filter_query(query)
        if not keyed_filters and not free_terms:
            return columns
        filtered = []
        for column in columns:
            issues = [
                issue
                for issue in column.issues
                if self._issue_matches_query(issue, keyed_filters, free_terms)
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

    def _filtered_issue_count(self) -> int:
        return sum(len(column.issues) for column in self.column_metrics)

    def _my_identity_candidates(self) -> set[str]:
        candidates = {"me"}
        for env_name in ("PD_ME", "USER", "GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
            value = os.getenv(env_name)
            if value:
                candidates.add(value.strip().casefold())
        return candidates
