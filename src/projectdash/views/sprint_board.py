from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Vertical, Horizontal
from projectdash.widgets.issue_card import IssueCard

class SprintBoardView(Static):
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("📋 SPRINT BOARD", id="view-header")
            yield Horizontal(id="kanban-row")

    def refresh_view(self) -> None:
        data = self.app.data_manager
        kanban_row = self.query_one("#kanban-row", Horizontal)
        kanban_row.remove_children()
        
        statuses = ["Todo", "In Progress", "Review", "Done"]
        for status in statuses:
            issues = data.get_issues_by_status(status)
            
            # Create the list of widgets first
            column_widgets = [Static(f"{status.upper()} ({len(issues)})", classes="col-header")]
            for issue in issues:
                column_widgets.append(IssueCard(issue, classes="issue-card"))
            
            # Pass them to the constructor so they are composed immediately upon mounting
            column = Vertical(*column_widgets, classes="kanban-col")
            kanban_row.mount(column)
