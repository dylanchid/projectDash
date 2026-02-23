from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Vertical, Horizontal
from rich.text import Text

class DashboardView(Static):
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("OVERVIEW", id="view-header")
            
            with Horizontal(id="stats-row"):
                yield Static(id="dash-stats-status", classes="stat-card")
                yield Static(id="dash-stats-performance", classes="stat-card")
                yield Static(id="dash-stats-network", classes="stat-card")

            yield Static("PROJECTS", classes="section-label")
            yield Horizontal(id="project-cards-row")

    def refresh_view(self) -> None:
        data = self.app.data_manager
        projects = data.get_projects()
        
        # Update stats
        self.query_one("#dash-stats-status", Static).update(Text.assemble(
            ("STATUS\n", "bold #666666"),
            (f"Projects: {len(projects)}\n", "#ffffff"),
            (f"Issues: {len(data.get_issues())}", "#888888")
        ))
        
        self.query_one("#dash-stats-performance", Static).update(Text.assemble(
            ("PERFORMANCE\n", "bold #666666"),
            ("Velocity: 32 pts\n", "#ffffff"),
            ("Blocked: 2", "#888888")
        ))
        
        import os
        connected = "✓ Connected" if os.getenv("LINEAR_API_KEY") else "✕ Offline"
        self.query_one("#dash-stats-network", Static).update(Text.assemble(
            ("NETWORK\n", "bold #666666"),
            (f"{connected}\n", "#ffffff"),
            ("Day: 3/10", "#888888")
        ))
        
        # Update projects row
        projects_row = self.query_one("#project-cards-row", Horizontal)
        projects_row.remove_children()
        for project in projects:
            projects_row.mount(Static(Text.assemble(
                (f"{project.name.upper()}\n", "bold #ffffff"),
                (f"Total: {project.issues_count}\n", "#666666"),
                (f"Active: {project.in_progress_count}", "#ffffff")
            ), classes="project-card"))
