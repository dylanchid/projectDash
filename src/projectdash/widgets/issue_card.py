from textual.widgets import Static
from textual.message import Message
from textual import events
from rich.text import Text
from projectdash.models import Issue


class IssueCardSelected(Message):
    def __init__(self, issue_id: str) -> None:
        super().__init__()
        self.issue_id = issue_id

class IssueCard(Static):
    can_focus = True

    def __init__(self, issue: Issue, selected: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.issue = issue
        self.selected = selected

    def on_click(self, event: events.Click) -> None:  # type: ignore[override]
        self.post_message(IssueCardSelected(self.issue.id))

    def render(self):
        dot_color = "#444444"
        priority = str(self.issue.priority).strip().lower()
        severity_symbol = "·"
        if priority in {"high", "1"}:
            dot_color = "#ffffff"
            severity_symbol = "!!"
        elif priority in {"medium", "2"}:
            dot_color = "#888888"
            severity_symbol = "!"
        assignee_name = self.issue.assignee.name if self.issue.assignee else "Unassigned"
        cursor = "▶ " if self.selected else "  "
            
        return Text.assemble(
            (cursor, "bold #ffffff" if self.selected else "#444444"),
            (f"{severity_symbol} ", f"bold {dot_color}"),
            (f"{self.issue.id} ", "bold #666666"),
            (f"{self.issue.title}\n", "#ffffff"),
            (f"  {assignee_name}", "italic #444444")
        )
