from textual.widgets import Static
from rich.panel import Panel
from rich.text import Text
from projectdash.models import Issue

class IssueCard(Static):
    def __init__(self, issue: Issue, **kwargs):
        super().__init__(**kwargs)
        self.issue = issue

    def render(self):
        dot_color = "#444444"
        if self.issue.priority == "High":
            dot_color = "#ffffff"
        elif self.issue.priority == "Medium":
            dot_color = "#888888"
            
        return Text.assemble(
            (f"● ", f"bold {dot_color}"),
            (f"{self.issue.id} ", "bold #666666"),
            (f"{self.issue.title}\n", "#ffffff"),
            (f"  {self.issue.assignee.name}", "italic #444444")
        )
