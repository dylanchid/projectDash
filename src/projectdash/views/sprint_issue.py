from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from projectdash.views.issue_flow import IssueFlowScreen


class SprintIssueScreen(Screen[None]):
    BINDINGS = [
        ("escape", "close_screen", "Close"),
        ("q", "close_screen", "Close"),
        ("o", "open_linear", "Open Linear"),
        ("c", "open_comment", "Comment"),
        ("p", "open_editor", "Open Editor"),
        ("T", "open_terminal", "Terminal Note"),
        ("r", "open_github", "GitHub Drilldown"),
        ("P", "open_issue_flow", "Issue Flow"),
        ("question_mark", "toggle_help", "Help"),
    ]

    def __init__(self, issue_id: str) -> None:
        super().__init__()
        self.issue_id = issue_id

    def compose(self) -> ComposeResult:
        yield Static("SPRINT ITEM", id="sprint-item-header")
        yield Static("DETAIL", classes="section-label")
        yield Static("", id="sprint-item-detail", classes="placeholder-text")
        yield Static("", id="sprint-item-hint", classes="detail-sidebar-hint")

    def on_mount(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        issue = self.app.data_manager.get_issue_by_id(self.issue_id)
        detail = self.query_one("#sprint-item-detail", Static)
        hint = self.query_one("#sprint-item-hint", Static)
        if issue is None:
            detail.update(f"Issue not found: {self.issue_id}")
            hint.update("Esc close")
            return
        assignee = issue.assignee.name if issue.assignee else "Unassigned"
        linked_prs = self.app.data_manager.get_pull_requests(issue.id)
        top_prs = linked_prs[:5]
        pr_lines = "\n".join(f"- #{pr.number} [{pr.state}] {pr.title}" for pr in top_prs) if top_prs else "- none"
        detail.update(
            f"{issue.id} · {issue.status}\n"
            f"{issue.title}\n\n"
            f"Assignee: {assignee}\n"
            f"Priority: {issue.priority}\n"
            f"Points: {issue.points}\n"
            f"Due: {issue.due_date or 'N/A'}\n"
            f"Project: {issue.project_id or 'N/A'}\n\n"
            f"Linked PRs: {len(linked_prs)}\n"
            f"{pr_lines}"
        )
        hint.update("o linear • c comment • p editor • T terminal • r github • P issue flow • Esc close")

    def action_close_screen(self) -> None:
        self.dismiss(None)

    def action_open_linear(self) -> None:
        self.app.action_sprint_open_linear()

    def action_open_comment(self) -> None:
        self.app.action_sprint_comment_issue()

    def action_open_editor(self) -> None:
        self.app.action_sprint_open_editor()

    def action_open_terminal(self) -> None:
        self.app.action_sprint_open_terminal_editor()

    def action_open_issue_flow(self) -> None:
        self.app.push_screen(IssueFlowScreen(self.issue_id))

    def action_open_github(self) -> None:
        self.app.action_switch_tab("github")
        github = self.app._active_github_view()
        if github is None:
            self.app._publish_action_result(False, "GitHub dashboard unavailable")
            return
        ok, message = github.focus_issue(self.issue_id)
        self.app._publish_action_result(ok, message)

    def action_toggle_help(self) -> None:
        self.app.action_toggle_help_overlay()
