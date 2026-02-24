from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Vertical, Horizontal
from rich.text import Text
from projectdash.services.metrics import WorkloadMetricSet
from projectdash.widgets.workload_member_row import WorkloadMemberRow, WorkloadMemberSelected


class WorkloadView(Static):
    VISUAL_MODES = ("table", "chart", "rebalance")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.visual_mode = "table"
        self.graph_density = "compact"
        self.project_scope_id: str | None = None
        self.selected_member: str | None = None
        self._member_order: list[str] = []
        self.detail_open = False
        self.simulation_points = 2

    def on_mount(self) -> None:
        self.refresh_view()

    def on_show(self) -> None:
        self.refresh_view()

    def compose(self) -> ComposeResult:
        with Horizontal(id="workload-layout"):
            with Vertical(id="workload-main"):
                yield Static("👥 TEAM WORKLOAD", id="view-header")
                yield Static(id="workload-controls", classes="section-label")
                yield Vertical(id="workload-list")
                yield Static(id="workload-chart", classes="placeholder-text")
                yield Static("\nRecommendations:", classes="section-label")
                yield Static(id="recommendations-text", classes="placeholder-text")
            with Vertical(id="workload-sidebar", classes="detail-sidebar"):
                yield Static("MEMBER DETAIL", classes="detail-sidebar-title")
                yield Static("", id="workload-detail")
                yield Static("", id="workload-hint", classes="detail-sidebar-hint")

    def refresh_view(self) -> None:
        metric_set = self.app.metrics.workload(self.app.data_manager, project_id=self.project_scope_id)
        self._member_order = [member.name for member in metric_set.members]
        scope = self._scope_label()
        controls = (
            f"View: {self.visual_mode.title()}  │  Graph: {self.graph_density.title()}  │  "
            f"Scope: {scope}  │  Sim shift: {self.simulation_points}pt  │  Toggle: v mode, g density"
        )
        self.query_one("#workload-controls", Static).update(controls)

        list_container = self.query_one("#workload-list", Vertical)
        chart_widget = self.query_one("#workload-chart", Static)
        if self.visual_mode == "table":
            list_container.display = True
            chart_widget.display = False
            list_container.remove_children()
            header = Static(self._table_header_text(), classes="placeholder-text")
            list_container.mount(header)
            members = metric_set.members
            if self.graph_density == "compact":
                members = members[:7]
            for member in members:
                is_selected = member.name == self.selected_member
                classes = "workload-row is-selected" if is_selected else "workload-row"
                list_container.mount(WorkloadMemberRow(member, selected=is_selected, classes=classes))
            if not metric_set.members:
                list_container.mount(Static("No team members loaded yet. Press y to sync.", classes="placeholder-text"))
            list_container.mount(Static("", classes="placeholder-text"))
            list_container.mount(Static(self._team_summary_text(metric_set), classes="placeholder-text"))
            if self.graph_density == "detailed":
                list_container.mount(Static(self._table_footer_text(metric_set), classes="placeholder-text"))
        elif self.visual_mode == "chart":
            list_container.display = False
            chart_widget.display = True
            chart_widget.update(self._chart_text(metric_set, detailed=self.graph_density == "detailed"))
        else:
            list_container.display = False
            chart_widget.display = True
            chart_widget.update(self._rebalance_text(metric_set, detailed=self.graph_density == "detailed"))

        recommendations = metric_set.recommendations
        if self.graph_density == "compact":
            recommendations = recommendations[:2]
        recommendations_text = "\n".join(f"  • {line}" for line in recommendations)
        recommendations = recommendations_text or "  • No recommendations yet."
        self.query_one("#recommendations-text", Static).update(recommendations)
        self._refresh_detail_panel(metric_set)

    def toggle_visual_mode(self) -> tuple[bool, str]:
        current_index = self.VISUAL_MODES.index(self.visual_mode)
        self.visual_mode = self.VISUAL_MODES[(current_index + 1) % len(self.VISUAL_MODES)]
        self.refresh_view()
        return True, f"Workload view mode: {self.visual_mode}"

    def toggle_graph_density(self) -> tuple[bool, str]:
        self.graph_density = "detailed" if self.graph_density == "compact" else "compact"
        self.refresh_view()
        return True, f"Workload graph density: {self.graph_density}"

    def open_detail(self) -> None:
        if self.selected_member is None:
            members = self.app.metrics.workload(self.app.data_manager, project_id=self.project_scope_id).members
            if members:
                self.selected_member = members[0].name
        self.detail_open = True
        self.refresh_view()

    def close_detail(self) -> None:
        self.detail_open = False
        self.refresh_view()

    def context_summary(self) -> dict[str, str]:
        return {
            "mode": self.visual_mode,
            "density": self.graph_density,
            "filter": f"sim {self.simulation_points}pt",
            "selected": self.selected_member or "none",
        }

    def move_selection(self, delta: int) -> None:
        if not self._member_order:
            return
        if self.selected_member not in self._member_order:
            self.selected_member = self._member_order[0]
            self.refresh_view()
            return
        current_index = self._member_order.index(self.selected_member)
        next_index = (current_index + delta) % len(self._member_order)
        self.selected_member = self._member_order[next_index]
        self.refresh_view()

    def set_project_scope(self, project_id: str | None) -> None:
        self.project_scope_id = project_id
        if self.selected_member:
            metric_set = self.app.metrics.workload(self.app.data_manager, project_id=self.project_scope_id)
            visible_members = {member.name for member in metric_set.members}
            if self.selected_member not in visible_members:
                self.selected_member = None
        self.refresh_view()

    def adjust_simulation(self, delta: int) -> tuple[bool, str]:
        next_value = max(1, min(8, self.simulation_points + delta))
        if next_value == self.simulation_points:
            return False, "Simulation shift unchanged"
        self.simulation_points = next_value
        self.refresh_view()
        return True, f"Simulation shift: {self.simulation_points} pts"

    def on_workload_member_selected(self, message: WorkloadMemberSelected) -> None:
        self.selected_member = message.member_name
        self.detail_open = True
        self.refresh_view()

    def _table_header_text(self) -> Text:
        text = Text()
        text.append("Name           Allocation   Points       Util  Status\n", style="bold #666666")
        text.append("----------------------------------------------------\n", style="#333333")
        return text

    def _team_summary_text(self, metric_set: WorkloadMetricSet) -> Text:
        team = metric_set.team
        text = Text()
        text.append("TEAM TOTAL\n", style="bold #666666")
        text.append(
            f"{team.allocation_bar}  {team.utilization_pct}%  "
            f"{team.total_points}/{team.total_capacity} pts  "
            f"{team.active_issues} active\n",
            style="#ffffff",
        )
        return text

    def _scope_label(self) -> str:
        if not self.project_scope_id:
            return "All projects"
        for project in self.app.data_manager.get_projects():
            if project.id == self.project_scope_id:
                return project.name
        return self.project_scope_id

    def _table_footer_text(self, metric_set: WorkloadMetricSet) -> Text:
        text = Text()
        status_counts = self._status_distribution(metric_set)
        text.append("TEAM MIX\n", style="bold #666666")
        text.append(
            f"Overallocated: {status_counts['Overallocated']}  "
            f"At Capacity: {status_counts['At Capacity']}  "
            f"Available: {status_counts['Available']}",
            style="#ffffff",
        )
        return text

    def _chart_text(self, metric_set: WorkloadMetricSet, detailed: bool = False) -> Text:
        text = Text()
        text.append("UTILIZATION DISTRIBUTION\n", style="bold #666666")
        members = sorted(metric_set.members, key=lambda member: member.utilization_pct, reverse=True)
        width = 26 if detailed else 18
        for member in members:
            capped = max(0, min(100, member.utilization_pct))
            filled = int((capped / 100) * width)
            bar = "█" * filled + "░" * (width - filled)
            text.append(f"{member.name[:12].ljust(12)} {bar} {member.utilization_pct:>3}%\n", style="#ffffff")
            if detailed:
                text.append(f"   pts {member.points}/{member.capacity}  status {member.status_text}\n", style="#777777")
        if not members:
            text.append("No workload data. Press y to sync.\n", style="#666666")

        team = metric_set.team
        text.append("\nTEAM\n", style="bold #666666")
        text.append(
            f"{team.allocation_bar} {team.utilization_pct}%  ({team.total_points}/{team.total_capacity} pts)\n",
            style="#ffffff",
        )
        return text

    def _rebalance_text(self, metric_set: WorkloadMetricSet, detailed: bool = False) -> Text:
        text = Text()
        text.append("REBALANCE HEATMAP\n", style="bold #666666")
        status_counts = self._status_distribution(metric_set)
        max_status = max(status_counts.values(), default=1)
        width = 20 if detailed else 12
        for label in ("Overallocated", "At Capacity", "Available"):
            value = status_counts[label]
            filled = int((value / max_status) * width) if max_status else 0
            bar = "█" * filled + "░" * (width - filled)
            symbol = "!!" if label == "Overallocated" else "!" if label == "At Capacity" else "·"
            text.append(f"{symbol} {label[:10].ljust(10)} {bar} {value}\n", style="#ffffff")

        text.append("\nCapacity gaps\n", style="bold #666666")
        gaps = sorted(
            metric_set.members,
            key=lambda member: abs(member.points - member.capacity),
            reverse=True,
        )
        limit = 6 if detailed else 4
        for member in gaps[:limit]:
            gap = member.points - member.capacity
            if gap > 0:
                gap_label = f"+{gap} pts over"
            elif gap < 0:
                gap_label = f"{abs(gap)} pts free"
            else:
                gap_label = "balanced"
            text.append(f"{member.name[:14].ljust(14)} {gap_label}\n", style="#ffffff")

        simulation = self._simulation_preview(metric_set)
        text.append("\nWHAT-IF SIMULATION\n", style="bold #666666")
        if simulation is None:
            text.append("Select a loaded member to simulate rebalance.\n", style="#666666")
        else:
            donor, receiver, shift, donor_after, receiver_after = simulation
            text.append(
                f"Shift {shift}pt: {donor.name} -> {receiver.name}\n"
                f"{donor.name}: {donor.utilization_pct}% -> {donor_after}%\n"
                f"{receiver.name}: {receiver.utilization_pct}% -> {receiver_after}%\n",
                style="#ffffff",
            )
        text.append("Use = / - to change simulated shift.", style="#777777")
        return text

    def _refresh_detail_panel(self, metric_set: WorkloadMetricSet) -> None:
        detail = self.query_one("#workload-detail", Static)
        hint = self.query_one("#workload-hint", Static)
        if not self.detail_open or not self.selected_member:
            detail.update(
                "Select a member to view detail.\n\n"
                f"Team util: {metric_set.team.utilization_pct}%\n"
                f"View: {self.visual_mode}\n"
                f"Graph: {self.graph_density}\n"
                f"Simulation: {self.simulation_points}pt"
            )
            hint.update("Enter open • Esc close • =/- simulation • v mode • g density")
            return

        selected = None
        for member in metric_set.members:
            if member.name == self.selected_member:
                selected = member
                break
        if not selected:
            detail.update("Member not found.")
            hint.update("Click a member row to pin details.")
            return

        issues_preview = selected.issues_preview
        if self.graph_density == "compact":
            issues_preview = issues_preview.split("\n", 2)[0]
        capacity_gap = selected.points - selected.capacity
        if capacity_gap > 0:
            gap_label = f"+{capacity_gap} pts over"
        elif capacity_gap < 0:
            gap_label = f"{abs(capacity_gap)} pts available"
        else:
            gap_label = "balanced"

        peer_hint = self._peer_rebalance_hint(metric_set, selected.name)
        simulation = self._simulation_preview(metric_set)
        simulation_text = "n/a"
        if simulation is not None:
            donor, receiver, shift, donor_after, receiver_after = simulation
            simulation_text = (
                f"{shift}pt {donor.name}->{receiver.name} "
                f"({donor_after}%/{receiver_after}%)"
            )

        detail.update(
            f"{selected.name}\n\n"
            f"Allocation: {selected.allocation_bar}\n"
            f"Utilization: {selected.utilization_pct}%\n"
            f"Points: {selected.points}/{selected.capacity}\n"
            f"Capacity gap: {gap_label}\n"
            f"Status: {selected.status_text}\n\n"
            f"Rebalance: {peer_hint}\n"
            f"Simulation: {simulation_text}\n\n"
            f"Issues:\n{issues_preview}"
        )
        hint.update("Enter open • Esc close • =/- simulation • v mode • g density")

    def _status_distribution(self, metric_set: WorkloadMetricSet) -> dict[str, int]:
        counts = {"Overallocated": 0, "At Capacity": 0, "Available": 0}
        for member in metric_set.members:
            status = member.status_text
            if status in counts:
                counts[status] += 1
            else:
                counts["Available"] += 1
        return counts

    def _peer_rebalance_hint(self, metric_set: WorkloadMetricSet, member_name: str) -> str:
        selected = None
        for member in metric_set.members:
            if member.name == member_name:
                selected = member
                break
        if selected is None:
            return "n/a"
        if selected.points <= selected.capacity:
            return "No rebalance needed"
        available = [
            member
            for member in metric_set.members
            if member.name != member_name and member.points < member.capacity
        ]
        if not available:
            return "No available teammate"
        receiver = sorted(available, key=lambda member: member.utilization_pct)[0]
        shift = max(1, min(selected.points - selected.capacity, receiver.capacity - receiver.points))
        return f"Shift ~{shift} pts to {receiver.name}"

    def _simulation_preview(self, metric_set: WorkloadMetricSet):
        members = metric_set.members
        if not members:
            return None

        donor = None
        if self.selected_member:
            for member in members:
                if member.name == self.selected_member:
                    donor = member
                    break
        if donor is None or donor.points <= donor.capacity:
            overloaded = sorted(
                (member for member in members if member.points > member.capacity),
                key=lambda member: (member.points - member.capacity, member.utilization_pct),
                reverse=True,
            )
            donor = overloaded[0] if overloaded else sorted(members, key=lambda member: member.utilization_pct, reverse=True)[0]

        receivers = [
            member for member in members
            if member.name != donor.name and member.points < member.capacity
        ]
        if not receivers:
            return None
        receiver = sorted(receivers, key=lambda member: member.utilization_pct)[0]

        max_shift = min(
            self.simulation_points,
            max(0, donor.points),
            max(0, receiver.capacity - receiver.points),
        )
        if max_shift <= 0:
            return None

        donor_after_points = donor.points - max_shift
        receiver_after_points = receiver.points + max_shift
        donor_after = int((donor_after_points / max(1, donor.capacity)) * 100)
        receiver_after = int((receiver_after_points / max(1, receiver.capacity)) * 100)
        return donor, receiver, max_shift, donor_after, receiver_after
