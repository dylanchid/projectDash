from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Vertical
from rich.text import Text

class TimelineView(Static):
    def compose(self) -> ComposeResult:
        yield Static("📅 TIMELINE", id="view-header")
        yield Static(id="timeline-content", classes="placeholder-text")

    def refresh_view(self) -> None:
        timeline_text = Text.assemble(
            ("ROADMAP & CRITICAL PATH\n\n", "bold #ffffff"),
            ("Feb 23  Feb 28  Mar 05  Mar 10  Mar 15  Mar 20\n", "#666666"),
            ("   |-------|-------|-------|-------|-------|\n", "#333333"),
            ("Acme Corp      [", "#ffffff"), ("▓▓▓▓▓", "#00ff00"), ("░░░░░░░░] ", "#444444"), ("5/12d\n", "#888888"),
            ("  └─ Sync API         [", "#666666"), ("▓▓▓", "#00ff00"), ("░]        ", "#444444"), ("(Critical)\n", "#ff0000"),
            ("\n"),
            ("DevTools       [", "#ffffff"), ("▓▓▓▓▓▓▓", "#ffff00"), ("░░░░]     ", "#444444"), ("7/10d\n", "#888888"),
            ("  └─ Auth Module      [", "#666666"), ("▓▓▓▓▓", "#ffff00"), ("░]       \n", "#444444"),
            ("\n"),
            ("Web Redesign   [", "#ffffff"), ("▓", "#00ffff"), ("░░░░░░░░░░░░] ", "#444444"), ("1/15d\n", "#888888"),
        )
        self.query_one("#timeline-content", Static).update(timeline_text)
