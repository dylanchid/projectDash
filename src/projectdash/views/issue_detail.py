from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from projectdash.models import Issue


class IssueDetailScreen(Screen):
    BINDINGS = [
        ("escape", "close_screen", "Close"),
        ("q", "close_screen", "Close"),
        ("m", "move_status", "Move Status"),
        ("a", "cycle_assignee", "Cycle Assignee"),
        ("e", "cycle_estimate", "Cycle Estimate"),
        ("j", "scroll_down", "Scroll Down"),
        ("k", "scroll_up", "Scroll Up"),
    ]

    def __init__(self, issue: Issue) -> None:
        super().__init__()
        self.issue = issue

    def compose(self) -> ComposeResult:
        yield Static("", id="issue-detail-header")
        yield Static("", id="issue-detail-meta")
        yield Static("", id="issue-detail-description")
        yield Static("", id="issue-detail-hint")

    def on_mount(self) -> None:
        self._render()

    def _render(self) -> None:
        issue = self.issue
        assignee_name = issue.assignee.name if issue.assignee else "Unassigned"
        project_name = self._project_name(issue.project_id)
        priority_label = self._priority_label(issue.priority)

        header_text = f"{issue.linear_id or issue.id}  ·  {issue.title}"
        self.query_one("#issue-detail-header", Static).update(header_text)

        meta_lines = [
            f"Status     {issue.status}",
            f"Priority   {priority_label}",
            f"Assignee   {assignee_name}",
            f"Points     {issue.points if issue.points else '–'}",
            f"Due        {issue.due_date or '–'}",
            f"Project    {project_name}",
            f"Team       {issue.team_id or '–'}",
            f"Created    {issue.created_at.strftime('%Y-%m-%d') if issue.created_at else '–'}",
        ]
        self.query_one("#issue-detail-meta", Static).update("\n".join(meta_lines))

        if issue.description:
            desc_text = f"DESCRIPTION\n\n{issue.description}"
        else:
            desc_text = "DESCRIPTION\n\nNo description provided."
        self.query_one("#issue-detail-description", Static).update(desc_text)

        self.query_one("#issue-detail-hint", Static).update(
            "m status  ·  a assignee  ·  e points  ·  Esc / q close"
        )

    def action_close_screen(self) -> None:
        self.app.pop_screen()

    def action_move_status(self) -> None:
        self.run_worker(self._do_move_status(), exclusive=False)

    def action_cycle_assignee(self) -> None:
        self.run_worker(self._do_cycle_assignee(), exclusive=False)

    def action_cycle_estimate(self) -> None:
        self.run_worker(self._do_cycle_estimate(), exclusive=False)

    async def _do_move_status(self) -> None:
        ok, message = await self.app.data_manager.cycle_issue_status(
            self.issue.id, self.app.config.kanban_statuses
        )
        updated = self.app.data_manager.get_issue_by_id(self.issue.id)
        if updated:
            self.issue = updated
        self._render()
        self.app._publish_action_result(ok, message)

    async def _do_cycle_assignee(self) -> None:
        ok, message = await self.app.data_manager.cycle_issue_assignee(self.issue.id)
        updated = self.app.data_manager.get_issue_by_id(self.issue.id)
        if updated:
            self.issue = updated
        self._render()
        self.app._publish_action_result(ok, message)

    async def _do_cycle_estimate(self) -> None:
        ok, message = await self.app.data_manager.cycle_issue_points(self.issue.id)
        updated = self.app.data_manager.get_issue_by_id(self.issue.id)
        if updated:
            self.issue = updated
        self._render()
        self.app._publish_action_result(ok, message)

    def _project_name(self, project_id: str | None) -> str:
        if not project_id:
            return "–"
        for project in self.app.data_manager.get_projects():
            if project.id == project_id:
                return project.name
        return project_id

    def _priority_label(self, raw: str) -> str:
        mapping = {"0": "No Priority", "1": "Urgent", "2": "High", "3": "Medium", "4": "Low"}
        return mapping.get(raw, raw or "–")
