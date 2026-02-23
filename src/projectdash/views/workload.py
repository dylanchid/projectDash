from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Vertical, Horizontal
from rich.text import Text
from rich.table import Table
from rich import box

class WorkloadView(Static):
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("👥 TEAM WORKLOAD", id="view-header")
            yield Static("View: Team  │  Period: This Sprint  │  Sort: Utilization %", classes="section-label")
            yield WorkloadTable(id="workload-table")
            yield Static("\nRecommendations:", classes="section-label")
            yield Static(id="recommendations-text", classes="placeholder-text")

    def refresh_view(self) -> None:
        self.query_one("#workload-table", WorkloadTable).update_table()
        self.query_one("#recommendations-text", Static).update(
            "  • Reassign 1-2 items from Alice (80%) to Dave (50%)\n"
            "  • Plan for 2-3 more team members next sprint"
        )

class WorkloadTable(Static):
    def update_table(self) -> None:
        data = self.app.data_manager
        users = data.users
        issues = data.issues
        
        table = Table(show_header=True, header_style="bold #666666", box=None, padding=(0, 1), expand=True)
        table.add_column("Name", width=12)
        table.add_column("Allocation", width=12)
        table.add_column("Points", width=10)
        table.add_column("Util %", width=8)
        table.add_column("Status", width=18)
        table.add_column("Issues", width=20)

        for user in users:
            user_issues = [i for i in issues if i.assignee and i.assignee.id == user.id]
            points = sum(i.points for i in user_issues)
            capacity = 10
            util = (points / capacity) * 100
            
            bar_width = 10
            filled = int((util / 100) * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            
            status_text = "✓ Available"
            status_color = "#00ff00"
            if util >= 80:
                status_text = "⚠️ Overallocated"
                status_color = "#ff0000"
            elif util >= 70:
                status_text = "✓ At Capacity"
                status_color = "#ffff00"

            issue_list = "\n".join([f"• {i.id} ({i.points}pt)" for i in user_issues[:3]])
            if len(user_issues) > 3:
                issue_list += f"\n+ {len(user_issues)-3} more"

            table.add_row(
                user.name,
                bar,
                f"{points}/{capacity} pts",
                f"{int(util)}%",
                f"[{status_color}]{status_text}[/]",
                issue_list
            )
            table.add_row("", "", "", "", "", "", end_section=True)

        total_points = sum(sum(i.points for i in issues if i.assignee and i.assignee.id == u.id) for u in users)
        total_capacity = len(users) * 10 
        
        if total_capacity > 0:
            total_util = (total_points / total_capacity) * 100
            total_bar = "█" * 10
            status_text = "[bold #ff0000]🔴 CRITICAL[/]" if total_util > 80 else "[bold #00ff00]✓ OK[/]"
        else:
            total_util = 0
            total_bar = "░" * 10
            status_text = "[#666666]NO DATA[/]"
        
        table.add_row(
            "Team Total",
            total_bar,
            f"{total_points}/{total_capacity} pts",
            f"{int(total_util)}%",
            status_text,
            f"{len(issues)} active"
        )

        self.update(table)
