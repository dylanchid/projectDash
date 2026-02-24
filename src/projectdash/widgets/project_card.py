from textual.widgets import Static
from textual.message import Message
from textual import events
from rich.text import Text
from projectdash.services.metrics import ProjectCardMetric


class ProjectCardSelected(Message):
    def __init__(self, project_id: str, project_name: str) -> None:
        super().__init__()
        self.project_id = project_id
        self.project_name = project_name


class ProjectCard(Static):
    can_focus = True

    def __init__(self, metric: ProjectCardMetric, selected: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.metric = metric
        self.selected = selected

    def on_click(self, event: events.Click) -> None:  # type: ignore[override]
        self.post_message(ProjectCardSelected(self.metric.project_id, self.metric.name))

    def render(self):
        title_style = "bold #ffffff" if self.selected else "bold #dddddd"
        meta_style = "#666666" if self.selected else "#555555"
        return Text.assemble(
            (f"{self.metric.name.upper()}\n", title_style),
            (f"Total: {self.metric.total}\n", meta_style),
            (f"Active: {self.metric.active}  Blocked: {self.metric.blocked}", "#ffffff"),
        )
