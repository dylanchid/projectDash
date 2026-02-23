from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Tabs, Tab, ContentSwitcher, Static
from projectdash.views.dashboard import DashboardView
from projectdash.views.sprint_board import SprintBoardView
from projectdash.views.workload import WorkloadView
from projectdash.views.timeline import TimelineView
from projectdash.data import DataManager
from dotenv import load_dotenv

class ProjectDash(App):
    CSS = """
    Screen {
        background: #000000;
        color: #ffffff;
    }

    #app-header {
        height: 3;
        background: #000000;
        color: #ffffff;
        border-bottom: ascii #333333;
        padding: 1 2;
    }

    #view-header {
        text-style: bold;
        background: transparent;
        padding: 1 2;
        width: 100%;
        color: #ffffff;
        border-bottom: ascii #333333;
        margin-bottom: 1;
    }

    #stats-row {
        height: 6;
        margin: 0 2;
        border-bottom: ascii #333333;
    }

    .stat-card {
        width: 33%;
        height: 5;
    }

    .section-label {
        padding: 1 2 0 2;
        color: #666666;
        text-style: bold;
    }

    #project-cards-row {
        height: 10;
        margin: 0 2;
    }

    .project-card {
        width: 33%;
        height: 8;
        padding: 1;
    }

    #kanban-row {
        height: 100%;
        margin: 0 1;
    }

    .kanban-col {
        width: 25%;
        margin: 0 1;
        padding: 1;
    }

    .col-header {
        text-align: left;
        text-style: bold;
        color: #666666;
        margin-bottom: 1;
        border-bottom: ascii #333333;
    }

    .issue-card {
        margin-bottom: 0;
        height: 4;
        border-bottom: ascii #1a1a1a;
    }

    .placeholder-text {
        padding: 2;
        color: #444444;
    }

    Tabs {
        background: #000000;
        color: #666666;
        border-bottom: ascii #333333;
        height: 3;
    }

    Tabs > Tab {
        padding: 0 2;
    }

    Tabs > Tab.-active {
        color: #ffffff;
        text-style: bold;
        background: #111111;
    }

    Footer {
        background: #000000;
        color: #444444;
    }
    """

    BINDINGS = [
        ("d", "switch_tab('dash')", "Dashboard"),
        ("s", "switch_tab('sprint')", "Sprint Board"),
        ("t", "switch_tab('timeline')", "Timeline"),
        ("w", "switch_tab('workload')", "Workload"),
        ("y", "sync_data", "Sync Linear"),
        ("h", "prev_tab", "Prev Tab"),
        ("l", "next_tab", "Next Tab"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data_manager = DataManager()
        self.tab_ids = ["dash", "sprint", "timeline", "workload"]

    async def on_mount(self) -> None:
        """Initialize data manager on startup."""
        await self.data_manager.initialize()
        self.refresh_views()

    def refresh_views(self) -> None:
        """Triggers a refresh on all view components."""
        for view_id in self.tab_ids:
            try:
                view = self.query_one(f"#{view_id}")
                if hasattr(view, "refresh_view"):
                    view.refresh_view()
            except Exception:
                pass

    async def action_sync_data(self) -> None:
        """Manually trigger a sync with Linear."""
        # Show a notification or loading state if needed
        await self.data_manager.sync_with_linear()
        self.refresh_views()

    def compose(self) -> ComposeResult:
        yield Static("PROJECT DASHBOARD — v0.1", id="app-header")
        yield Tabs(
            Tab("Dashboard", id="dash"),
            Tab("Sprint Board", id="sprint"),
            Tab("Timeline", id="timeline"),
            Tab("Workload", id="workload"),
        )
        with ContentSwitcher(initial="dash"):
            yield DashboardView(id="dash")
            yield SprintBoardView(id="sprint")
            yield TimelineView(id="timeline")
            yield WorkloadView(id="workload")
        yield Footer()

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        self.query_one(ContentSwitcher).current = event.tab.id

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(Tabs).active = tab_id

    def action_next_tab(self) -> None:
        tabs = self.query_one(Tabs)
        current_index = self.tab_ids.index(tabs.active)
        next_index = (current_index + 1) % len(self.tab_ids)
        tabs.active = self.tab_ids[next_index]

    def action_prev_tab(self) -> None:
        tabs = self.query_one(Tabs)
        current_index = self.tab_ids.index(tabs.active)
        prev_index = (current_index - 1) % len(self.tab_ids)
        tabs.active = self.tab_ids[prev_index]

def run() -> None:
    load_dotenv()
    app = ProjectDash()
    app.run()

if __name__ == "__main__":
    run()
