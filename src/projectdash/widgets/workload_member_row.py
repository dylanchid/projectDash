from textual.widgets import Static
from textual.message import Message
from textual import events
from rich.text import Text
from projectdash.services.metrics import WorkloadMemberMetric


class WorkloadMemberSelected(Message):
    def __init__(self, member_name: str) -> None:
        super().__init__()
        self.member_name = member_name


class WorkloadMemberRow(Static):
    can_focus = True

    def __init__(self, metric: WorkloadMemberMetric, selected: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.metric = metric
        self.selected = selected

    def on_click(self, event: events.Click) -> None:  # type: ignore[override]
        self.post_message(WorkloadMemberSelected(self.metric.name))

    def render(self):
        name = self.metric.name[:14].ljust(14)
        util = f"{self.metric.utilization_pct}%".rjust(4)
        points = f"{self.metric.points}/{self.metric.capacity} pts".ljust(12)
        status = self.metric.status_text.ljust(10)
        severity_symbol = "·"
        if self.metric.status_text == "Overallocated":
            severity_symbol = "!!"
        elif self.metric.status_text == "At Capacity":
            severity_symbol = "!"
        highlight = "bold #ffffff" if self.selected else "#ffffff"
        return Text.assemble(
            (f"{name} ", highlight),
            (f"{self.metric.allocation_bar} ", "#666666"),
            (f"{points} ", "#888888"),
            (f"{util} ", "#bbbbbb"),
            (f"{severity_symbol} {status}", self.metric.status_color),
        )
