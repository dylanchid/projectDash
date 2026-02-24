from textual.widgets import Static
from textual.message import Message
from textual import events
from rich.text import Text
from projectdash.services.metrics import TimelineProjectMetric


class TimelineRowSelected(Message):
    def __init__(self, project_id: str, project_name: str) -> None:
        super().__init__()
        self.project_id = project_id
        self.project_name = project_name


class TimelineRow(Static):
    can_focus = True

    def __init__(self, metric: TimelineProjectMetric, selected: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.metric = metric
        self.selected = selected

    def on_click(self, event: events.Click) -> None:  # type: ignore[override]
        self.post_message(TimelineRowSelected(self.metric.project_id, self.metric.name))

    def render(self):
        name = self.metric.name[:18].ljust(18)
        progress = self.metric.progress_bar.ljust(12)
        points = f"{self.metric.done_points}/{self.metric.total_points}".ljust(9)
        due = self.metric.due_date_label.ljust(12)
        highlight = "bold #ffffff" if self.selected else "#ffffff"
        label = self.metric.days_remaining_label.casefold()
        severity_symbol = "·"
        if "overdue" in label:
            severity_symbol = "!!"
        elif "today" in label or "3d" in label:
            severity_symbol = "!"
        return Text.assemble(
            (f"{name} ", highlight),
            (f"{progress} ", "#666666"),
            (f"{points} ", "#888888"),
            (f"{due} ", "#666666"),
            (f"{severity_symbol} {self.metric.days_remaining_label}", self.metric.status_color),
        )
