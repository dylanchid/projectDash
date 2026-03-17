from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from projectdash.models import Issue, PullRequest, CiCheck
from projectdash.enums import SyncResult

if TYPE_CHECKING:
    from projectdash.app import ProjectDash


@dataclass(frozen=True)
class BlockedQueueRow:
    issue: Issue
    age_days: int
    owner: str
    project: str
    linked_prs: int
    failing_checks: int


class BlockedQueueView(Static):
    """Dedicated screen for identifying and triaging blocked work."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.graph_density = "compact"
        self.project_scope_id: str | None = None
        self.selected_issue_id: str | None = None
        self._issue_order: list[str] = []
        self.assignee_filter = "all"  # all, mine, unassigned
        self.sort_mode = "age"  # age, project, owner
        self.detail_open = False

    def on_mount(self) -> None:
        self.refresh_view()

    def on_show(self) -> None:
        self.refresh_view()

    def compose(self) -> ComposeResult:
        with Horizontal(id="blocked-layout"):
            with Vertical(id="blocked-main"):
                yield Static("🛑 BLOCKED WORK QUEUE", id="view-header")
                yield Static("SYNC FRESHNESS", id="blocked-freshness-label", classes="section-label")
                yield Static("", id="blocked-freshness", classes="placeholder-text")
                yield Static("BLOCKED ISSUES", classes="section-label")
                yield Static("", id="blocked-content", classes="placeholder-text")
            with Vertical(id="blocked-sidebar", classes="detail-sidebar"):
                yield Static("BLOCKED DETAIL", classes="detail-sidebar-title")
                yield Static("", id="blocked-detail")
                yield Static("", id="blocked-hint", classes="detail-sidebar-hint")

    def refresh_view(self) -> None:
        if self._apply_freshness_visibility():
            self.query_one("#blocked-freshness", Static).update(self._freshness_text())
        
        rows = self._build_rows()
        self._issue_order = [row.issue.id for row in rows]
        
        if self.selected_issue_id and self.selected_issue_id not in self._issue_order:
            self.selected_issue_id = None
        if self.selected_issue_id is None and self._issue_order:
            self.selected_issue_id = self._issue_order[0]

        self.query_one("#blocked-content", Static).update(self._content_text(rows))
        self._refresh_detail_panel(rows)

    def _build_rows(self) -> list[BlockedQueueRow]:
        data = self.app.data_manager
        all_issues = data.get_issues()
        if self.project_scope_id:
            all_issues = [i for i in all_issues if i.project_id == self.project_scope_id]
        
        identity_names = self._my_identity_candidates()
        rows: list[BlockedQueueRow] = []
        now = datetime.now(timezone.utc)
        
        for issue in all_issues:
            # Check if blocked by status or by failing PR
            is_blocked = "blocked" in issue.status.casefold()
            linked_prs = data.get_pull_requests(issue.id)
            failing_checks = 0
            has_failing_pr = False
            
            for pr in linked_prs:
                if pr.state.casefold() != "open":
                    continue
                pr_checks = data.get_ci_checks(pr.id)
                fails = sum(1 for c in pr_checks if self._check_bucket(c) == "failing")
                failing_checks += fails
                if fails > 0:
                    has_failing_pr = True
            
            if not (is_blocked or has_failing_pr):
                continue
                
            owner = issue.assignee.name if issue.assignee else "Unassigned"
            owner_key = owner.casefold()
            
            # Apply assignee filter
            if self.assignee_filter == "mine" and owner_key not in identity_names:
                continue
            if self.assignee_filter == "unassigned" and issue.assignee is not None:
                continue
                
            project = self._project_label(issue.project_id)
            
            # Ensure issue.created_at is offset-aware
            created_at = issue.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            else:
                created_at = created_at.astimezone(timezone.utc)
                
            age_days = max(0, (now - created_at).days)
            
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
            
        # Apply sorting
        if self.sort_mode == "project":
            rows.sort(key=lambda r: (r.project.casefold(), -r.age_days))
        elif self.sort_mode == "owner":
            rows.sort(key=lambda r: (r.owner.casefold(), -r.age_days))
        else:  # default: age
            rows.sort(key=lambda r: (-r.age_days, r.owner.casefold()))
            
        return rows

    def _content_text(self, rows: list[BlockedQueueRow]) -> Text:
        text = Text()
        text.append(f"Mode: Blocked Queue  |  Sort: {self.sort_mode}  |  Filter: {self.assignee_filter}

", style="#666666")
        text.append("Issue      Age  Owner           Project         PRs  Fail  Title
", style="bold #666666")
        text.append("--------------------------------------------------------------------------
", style="#333333")
        
        if not rows:
            text.append("No blocked issues found.
", style="#666666")
            return text
            
        visible, start, end = self._windowed_rows(rows)
        for row in visible:
            marker = ">" if row.issue.id == self.selected_issue_id else " "
            style = "#ffffff"
            if row.age_days > 7:
                style = "#ff8888"
            if row.age_days > 14:
                style = "bold #ff5555"
                
            text.append(
                f"{marker} {row.issue.id[:8].ljust(8)} {str(row.age_days).rjust(3)}d  "
                f"{row.owner[:14].ljust(14)} {row.project[:14].ljust(14)} "
                f"{str(row.linked_prs).rjust(3)}  {str(row.failing_checks).rjust(4)}  "
                f"{row.issue.title[:28]}
",
                style=style,
            )
            
        if len(rows) > len(visible):
            text.append(
                f"
Showing {start + 1}-{end} of {len(rows)} blockers (PgUp/PgDn page)
",
                style="#666666",
            )
        return text

    def _refresh_detail_panel(self, rows: list[BlockedQueueRow]) -> None:
        detail = self.query_one("#blocked-detail", Static)
        hint = self.query_one("#blocked-hint", Static)
        
        row = next((r for r in rows if r.issue.id == self.selected_issue_id), None)
        if not row:
            detail.update("No issue selected.")
            hint.update("j/k select • PgUp/PgDn page")
            return
            
        issue = row.issue
        lines = [
            f"{issue.id} · {issue.status}",
            f"{issue.title}",
            "",
            f"Owner:   {row.owner}",
            f"Project: {row.project}",
            f"Age:     {row.age_days} days",
            f"Points:  {issue.points}",
            "",
            f"REASON FOR BLOCK",
            "----------------",
        ]
        
        if "blocked" in issue.status.casefold():
            lines.append("• Explicitly marked as BLOCKED in Linear.")
        if row.failing_checks > 0:
            lines.append(f"• {row.failing_checks} CI check(s) failing on linked PRs.")
            
        if issue.description:
            lines.append("")
            lines.append("DESCRIPTION")
            lines.append("-----------")
            lines.append(issue.description[:200] + ("..." if len(issue.description) > 200 else ""))

        detail.update("
".join(lines))
        hint.update("Enter detail • o open • i jump • m status • v sort • f filter")

    def move_selection(self, delta: int) -> None:
        if not self._issue_order:
            return
        if self.selected_issue_id not in self._issue_order:
            self.selected_issue_id = self._issue_order[0]
        else:
            idx = self._issue_order.index(self.selected_issue_id)
            self.selected_issue_id = self._issue_order[(idx + delta) % len(self._issue_order)]
        self.refresh_view()

    def page_selection(self, delta_pages: int) -> None:
        self.move_selection(delta_pages * 10)

    def toggle_visual_mode(self) -> tuple[bool, str]:
        # Use V/v to cycle sort modes
        modes = ["age", "project", "owner"]
        idx = (modes.index(self.sort_mode) + 1) % len(modes)
        self.sort_mode = modes[idx]
        self.refresh_view()
        return True, f"Blocked queue sorted by: {self.sort_mode}"

    def action_open_filter(self) -> None:
        # Use f or / to cycle assignee filters
        filters = ["all", "mine", "unassigned"]
        idx = (filters.index(self.assignee_filter) + 1) % len(filters)
        self.assignee_filter = filters[idx]
        self.refresh_view()
        self.app._publish_action_result(True, f"Assignee filter: {self.assignee_filter}")

    def open_primary(self) -> tuple[bool, str]:
        if not self.selected_issue_id:
            return False, "No issue selected"
        url = f"https://linear.app/issue/{self.selected_issue_id}"
        try:
            webbrowser.open_new_tab(url)
            return True, f"Opened {self.selected_issue_id} in Linear"
        except Exception as e:
            return False, f"Failed to open URL: {e}"

    def jump_context(self) -> tuple[bool, str]:
        if not self.selected_issue_id:
            return False, "No issue selected"
        self.app.action_switch_tab("sprint")
        sprint = self.app._active_sprint_view()
        if sprint:
            return sprint.focus_issue(self.selected_issue_id)
        return False, "Sprint board unavailable"

    def open_detail(self) -> None:
        if not self.selected_issue_id:
            return
        from projectdash.views.sprint_issue import SprintIssueScreen
        self.app.push_screen(SprintIssueScreen(self.selected_issue_id))

    def close_detail(self) -> None:
        if self.detail_open:
            self.detail_open = False
            self.refresh_view()
        elif self.project_scope_id:
            self.app.action_level_up()

    def _windowed_rows(self, rows: list[BlockedQueueRow]) -> tuple[list[BlockedQueueRow], int, int]:
        total = len(rows)
        if total == 0:
            return [], 0, 0
        page_size = 15
        selected_index = 0
        if self.selected_issue_id:
            for index, row in enumerate(rows):
                if row.issue.id == self.selected_issue_id:
                    selected_index = index
                    break
        start = (selected_index // page_size) * page_size
        end = min(total, start + page_size)
        return rows[start:end], start, end

    def _my_identity_candidates(self) -> set[str]:
        candidates = {"me"}
        for env_name in ("PD_ME", "USER", "GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
            value = os.getenv(env_name)
            if value:
                candidates.add(value.strip().casefold())
        return candidates

    def _project_label(self, project_id: str | None) -> str:
        if not project_id:
            return "Unscoped"
        for p in self.app.data_manager.projects:
            if p.id == project_id:
                return p.name
        return project_id

    def _check_bucket(self, check: CiCheck) -> str:
        status = (check.status or "").casefold()
        if status != "completed":
            return "pending"
        conclusion = (check.conclusion or "").casefold()
        if conclusion in {"success", "neutral", "skipped"}:
            return "passing"
        return "failing"

    def _freshness_text(self) -> str:
        return self.app.data_manager.freshness_summary_line(("github", "linear"))

    def _apply_freshness_visibility(self) -> bool:
        visible = bool(getattr(self.app, "sync_freshness_visible", True))
        for widget_id in ("#blocked-freshness-label", "#blocked-freshness"):
            try:
                self.query_one(widget_id, Static).display = visible
            except Exception:
                pass
        return visible
