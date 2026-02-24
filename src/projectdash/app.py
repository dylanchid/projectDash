from textual.app import App, ComposeResult
from textual.widgets import Footer, Tabs, Tab, ContentSwitcher, Static
from textual import events
import inspect
from projectdash.views.dashboard import DashboardView
from projectdash.views.sprint_board import SprintBoardView
from projectdash.views.workload import WorkloadView
from projectdash.views.timeline import TimelineView
from projectdash.views.sync_history import SyncHistoryScreen
from projectdash.data import DataManager
from projectdash.config import AppConfig
from projectdash.services import MetricsService
from dotenv import load_dotenv


class ProjectDash(App):
    CSS_PATH = "projectdash.tcss"

    BINDINGS = [
        ("d", "switch_tab('dash')", "Dashboard"),
        ("s", "switch_tab('sprint')", "Sprint Board"),
        ("t", "switch_tab('timeline')", "Timeline"),
        ("w", "switch_tab('workload')", "Workload"),
        ("h", "context_left", "Left"),
        ("l", "context_right", "Right"),
        ("j", "sprint_down", "Sprint Down"),
        ("k", "sprint_up", "Sprint Up"),
        ("[", "level_up", "All Projects"),
        ("]", "level_down", "Project Focus"),
        ("comma", "project_prev", "Prev Project"),
        (".", "project_next", "Next Project"),
        ("left", "sprint_left", "Sprint Left"),
        ("right", "sprint_right", "Sprint Right"),
        ("enter", "open_detail", "Open Detail"),
        ("escape", "close_detail", "Close Detail"),
        ("m", "sprint_move_status", "Move Status"),
        ("a", "sprint_cycle_assignee", "Cycle Assignee"),
        ("e", "sprint_cycle_estimate", "Cycle Estimate"),
        ("f", "sprint_filter", "Filter Sprint"),
        ("/", "open_command", "Command"),
        ("u", "sprint_jump_to_mine", "Jump To Mine"),
        ("y", "sync_data", "Sync Linear"),
        ("v", "toggle_visual_mode", "Toggle Visual Mode"),
        ("g", "toggle_graph_density", "Toggle Graph Density"),
        ("=", "simulation_increase", "Simulation +1"),
        ("-", "simulation_decrease", "Simulation -1"),
        ("?", "toggle_help_overlay", "Help Overlay"),
        ("1", "apply_preset('exec')", "Preset Exec"),
        ("2", "apply_preset('manager')", "Preset Manager"),
        ("3", "apply_preset('ic')", "Preset IC"),
        ("H", "open_sync_history", "Sync History"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = AppConfig.from_env()
        self.data_manager = DataManager(self.config)
        self.metrics = MetricsService(self.config)
        self.tab_ids = ["dash", "sprint", "timeline", "workload"]
        self.last_ui_error: str | None = None
        self.missing_mapping_hint_shown = False
        self.command_active = False
        self.command_query = ""
        self.command_selected_index = 0
        self.project_scope_id: str | None = None
        self.help_overlay_active = False
        self.active_preset = "custom"

    async def on_mount(self) -> None:
        await self.data_manager.initialize()
        self.refresh_views()
        self.update_app_status()

    def refresh_views(self) -> None:
        errors: list[str] = []
        switcher = self.query_one(ContentSwitcher)
        for view_id in self.tab_ids:
            try:
                view = switcher.query_one(f"#{view_id}")
                if hasattr(view, "refresh_view"):
                    view.refresh_view()
            except Exception as e:
                errors.append(f"{view_id}: {e}")
        if errors:
            self.last_ui_error = errors[0]
            self.update_app_status()
            self._notify("View refresh error", severity="error")
        else:
            self.last_ui_error = None

    async def action_sync_data(self) -> None:
        self.update_app_status("Syncing...")
        try:
            await self.data_manager.sync_with_linear()
        except Exception:
            pass
        self.refresh_views()
        self.update_app_status()
        if self.data_manager.last_sync_result == "success":
            self._notify("Sync complete", severity="information")
        else:
            self._notify(f"Sync failed: {self.data_manager.sync_status_summary()}", severity="error")

    def action_open_sync_history(self) -> None:
        self.push_screen(SyncHistoryScreen())

    def action_open_command(self) -> None:
        self.command_active = True
        self.help_overlay_active = False
        self.command_query = ""
        self.command_selected_index = 0
        self.update_app_status("Command mode: type /help, Enter to run, Esc to cancel.")

    def action_toggle_help_overlay(self) -> None:
        self.help_overlay_active = not self.help_overlay_active
        if self.help_overlay_active:
            self.command_active = False
            self.command_query = ""
            self.command_selected_index = 0
            self.update_app_status("Help overlay open. Press ? or Esc to close.")
        else:
            self.update_app_status("Help overlay closed")

    def action_toggle_visual_mode(self) -> None:
        view = self._active_visual_view()
        if view is None or not hasattr(view, "toggle_visual_mode"):
            return
        ok, message = view.toggle_visual_mode()
        self._publish_action_result(ok, message)

    def action_toggle_graph_density(self) -> None:
        view = self._active_visual_view()
        if view is None or not hasattr(view, "toggle_graph_density"):
            return
        ok, message = view.toggle_graph_density()
        self._publish_action_result(ok, message)

    def action_simulation_increase(self) -> None:
        workload = self._active_workload_view()
        if workload is None or not hasattr(workload, "adjust_simulation"):
            return
        ok, message = workload.adjust_simulation(1)
        self._publish_action_result(ok, message)

    def action_simulation_decrease(self) -> None:
        workload = self._active_workload_view()
        if workload is None or not hasattr(workload, "adjust_simulation"):
            return
        ok, message = workload.adjust_simulation(-1)
        self._publish_action_result(ok, message)

    def action_open_detail(self) -> None:
        sprint = self._active_sprint_view()
        if sprint and sprint.filter_active:
            ok, message = sprint.commit_filter()
            self._publish_action_result(ok, message)
            return
        view = self._active_detail_view()
        if view is None:
            return
        if hasattr(view, "open_detail"):
            view.open_detail()
            self.update_app_status()

    def action_close_detail(self) -> None:
        if self.help_overlay_active:
            self.help_overlay_active = False
            self.update_app_status("Help overlay closed")
            return
        sprint = self._active_sprint_view()
        if sprint and sprint.filter_active:
            ok, message = sprint.clear_filter()
            self._publish_action_result(ok, message)
            return
        view = self._active_detail_view()
        if view is None:
            return
        if hasattr(view, "close_detail"):
            view.close_detail()
            self.update_app_status()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if self.command_active:
            return False
        return True

    def compose(self) -> ComposeResult:
        yield Static("PROJECT DASHBOARD — v0.1", id="app-header")
        yield Tabs(
            Tab("Dashboard", id="dash"),
            Tab("Sprint Board", id="sprint"),
            Tab("Timeline", id="timeline"),
            Tab("Workload", id="workload"),
        )
        yield Static("Status: initializing...", id="app-status")
        yield Static("Context: initializing...", id="context-bar")
        yield Static("", id="sync-history")
        yield Static("", id="help-overlay")
        yield Static("", id="command-palette")
        yield Static("", id="command-prompt")
        with ContentSwitcher(initial="dash"):
            yield DashboardView(id="dash")
            yield SprintBoardView(id="sprint")
            yield TimelineView(id="timeline")
            yield WorkloadView(id="workload")
        yield Footer()

    def update_app_status(self, override_message: str | None = None) -> None:
        data = self.data_manager
        sync_state = data.sync_status_summary()
        if data.last_sync_result == "success" and data.last_sync_at:
            sync_state = f"{sync_state} @ {data.last_sync_at}"
        scope_label = self._scope_label()
        config_label = self.config.config_source
        ui_error = f" | UI error: {self.last_ui_error}" if self.last_ui_error else ""
        status_text = override_message or f"Sync: {sync_state} | Scope: {scope_label} | Config: {config_label}{ui_error}"
        try:
            self.query_one("#app-status", Static).update(status_text)
        except Exception:
            pass

        try:
            self.query_one("#context-bar", Static).update(self._context_bar_text())
        except Exception:
            pass

        if override_message:
            history_text = ""
        else:
            history_lines = data.latest_sync_history_lines(limit=3)
            history_text = "\n".join(f"Recent: {line}" for line in history_lines)
        try:
            self.query_one("#sync-history", Static).update(history_text)
        except Exception:
            pass

        try:
            overlay = self.query_one("#help-overlay", Static)
            overlay.update(self._help_overlay_text() if self.help_overlay_active else "")
            overlay.display = self.help_overlay_active
        except Exception:
            pass

        prompt = f"/{self.command_query}_" if self.command_active else ""
        try:
            self.query_one("#command-prompt", Static).update(prompt)
        except Exception:
            pass

        palette_text = ""
        if self.command_active:
            suggestions = self._command_suggestions(self.command_query, limit=8)
            lines = [f"> /{self.command_query}"]
            if suggestions:
                for index, (name, description) in enumerate(suggestions):
                    marker = ">" if index == self.command_selected_index else " "
                    lines.append(f"{marker} /{name:<16} {description}")
            else:
                lines.append("  No matches")
            palette_text = "\n".join(lines)
        try:
            self.query_one("#command-palette", Static).update(palette_text)
        except Exception:
            pass

        try:
            footer = self.query_one(Footer)
            footer.display = not self.command_active
        except Exception:
            pass

    def _notify(self, message: str, severity: str = "information") -> None:
        try:
            self.notify(message, severity=severity)
        except Exception:
            self.update_app_status(message)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        self.query_one(ContentSwitcher).current = event.tab.id
        self.update_app_status()

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

    def action_context_left(self) -> None:
        sprint = self._active_sprint_view()
        if sprint:
            if sprint.filter_active:
                return
            sprint.move_cursor(col_delta=-1)
            return
        if self.project_scope_id:
            self.action_project_prev()
            return
        self.action_prev_tab()

    def action_context_right(self) -> None:
        sprint = self._active_sprint_view()
        if sprint:
            if sprint.filter_active:
                return
            sprint.move_cursor(col_delta=1)
            return
        if self.project_scope_id:
            self.action_project_next()
            return
        self.action_next_tab()

    def action_level_down(self) -> None:
        if self.project_scope_id:
            return
        project_id = self._preferred_project_id_from_active_view() or self._first_project_id()
        if project_id is None:
            self._publish_action_result(False, "No projects available")
            return
        self._set_project_scope(project_id)
        self._publish_action_result(True, f"Project focus: {self._project_label(project_id)}")

    def action_level_up(self) -> None:
        if self.project_scope_id is None:
            return
        self._set_project_scope(None)
        self._publish_action_result(True, "Viewing all projects")

    def action_project_prev(self) -> None:
        self._cycle_project_scope(-1)

    def action_project_next(self) -> None:
        self._cycle_project_scope(1)

    def action_sprint_down(self) -> None:
        sprint = self._active_sprint_view()
        if sprint:
            if not sprint.filter_active:
                sprint.move_cursor(row_delta=1)
            return
        view = self._active_selection_view()
        if view and hasattr(view, "move_selection"):
            view.move_selection(1)

    def action_sprint_up(self) -> None:
        sprint = self._active_sprint_view()
        if sprint:
            if not sprint.filter_active:
                sprint.move_cursor(row_delta=-1)
            return
        view = self._active_selection_view()
        if view and hasattr(view, "move_selection"):
            view.move_selection(-1)

    def action_sprint_left(self) -> None:
        sprint = self._active_sprint_view()
        if sprint and not sprint.filter_active:
            sprint.move_cursor(col_delta=-1)

    def action_sprint_right(self) -> None:
        sprint = self._active_sprint_view()
        if sprint and not sprint.filter_active:
            sprint.move_cursor(col_delta=1)

    def action_sprint_open_detail(self) -> None:
        sprint = self._active_sprint_view()
        if sprint and not sprint.filter_active:
            sprint.open_selected_issue_detail()

    def action_sprint_close_detail(self) -> None:
        sprint = self._active_sprint_view()
        if sprint and not sprint.filter_active:
            sprint.close_issue_detail()

    async def action_sprint_move_status(self) -> None:
        sprint = self._active_sprint_view()
        if not sprint or sprint.filter_active:
            return
        ok, message = await sprint.cycle_selected_status()
        self._publish_action_result(ok, message)

    async def action_sprint_cycle_assignee(self) -> None:
        sprint = self._active_sprint_view()
        if not sprint or sprint.filter_active:
            return
        ok, message = await sprint.cycle_selected_assignee()
        self._publish_action_result(ok, message)

    async def action_sprint_cycle_estimate(self) -> None:
        sprint = self._active_sprint_view()
        if not sprint or sprint.filter_active:
            return
        ok, message = await sprint.cycle_selected_points()
        self._publish_action_result(ok, message)

    def action_sprint_filter(self) -> None:
        sprint = self._active_sprint_view()
        if not sprint:
            return
        ok, message = sprint.start_filter()
        self._publish_action_result(ok, message)

    def action_sprint_jump_to_mine(self) -> None:
        sprint = self._active_sprint_view()
        if not sprint or sprint.filter_active:
            return
        ok, message = sprint.jump_to_my_issue()
        self._publish_action_result(ok, message)

    def action_apply_preset(self, preset_name: str) -> None:
        normalized = preset_name.strip().casefold()
        switcher = self.query_one(ContentSwitcher)
        dash = switcher.query_one("#dash", DashboardView)
        timeline = switcher.query_one("#timeline", TimelineView)
        workload = switcher.query_one("#workload", WorkloadView)

        if normalized == "exec":
            self._set_project_scope(None)
            dash.visual_mode = "risk"
            dash.chart_density = "compact"
            timeline.visual_mode = "risk"
            timeline.graph_density = "compact"
            workload.visual_mode = "rebalance"
            workload.graph_density = "compact"
            self.active_preset = "exec"
            self.action_switch_tab("dash")
        elif normalized in {"manager", "eng manager"}:
            self._set_project_scope(None)
            dash.visual_mode = "compare"
            dash.chart_density = "detailed"
            timeline.visual_mode = "progress"
            timeline.graph_density = "detailed"
            workload.visual_mode = "chart"
            workload.graph_density = "detailed"
            self.active_preset = "manager"
            self.action_switch_tab("timeline")
        elif normalized == "ic":
            preferred = self._preferred_project_id_from_active_view() or self._first_project_id()
            if preferred:
                self._set_project_scope(preferred)
            dash.visual_mode = "load-active"
            dash.chart_density = "compact"
            timeline.visual_mode = "project"
            timeline.graph_density = "compact"
            workload.visual_mode = "table"
            workload.graph_density = "compact"
            self.active_preset = "ic"
            self.action_switch_tab("sprint")
        else:
            self._publish_action_result(False, f"Unknown preset: {preset_name}")
            return

        self.refresh_views()
        self._publish_action_result(True, f"Preset applied: {self.active_preset}")

    def on_key(self, event: events.Key) -> None:
        if self.command_active:
            handled = self._handle_command_key(event)
            if handled:
                event.stop()
            return
        if self.help_overlay_active and event.key == "escape":
            self.help_overlay_active = False
            self.update_app_status("Help overlay closed")
            event.stop()
            return

        sprint = self._active_sprint_view()
        if not sprint or not sprint.filter_active:
            return
        handled = True
        if event.key == "enter":
            ok, message = sprint.commit_filter()
            self._publish_action_result(ok, message)
        elif event.key == "escape":
            ok, message = sprint.clear_filter()
            self._publish_action_result(ok, message)
        elif event.key == "backspace":
            sprint.backspace_filter()
        elif event.key == "space":
            sprint.append_filter_character(" ")
        elif event.character and event.character.isprintable():
            sprint.append_filter_character(event.character)
        else:
            handled = False
        if handled:
            event.stop()

    def _handle_command_key(self, event: events.Key) -> bool:
        suggestions = self._command_suggestions(self.command_query, limit=20)
        if event.key == "enter":
            self.command_active = False
            command = self.command_query.strip().casefold()
            if suggestions and command not in self._command_catalog():
                selected = suggestions[min(self.command_selected_index, len(suggestions) - 1)][0]
                command = selected
            self.command_query = ""
            self.command_selected_index = 0
            self.update_app_status()
            if command:
                self._execute_command(command)
            return True
        if event.key == "escape":
            self.command_active = False
            self.command_query = ""
            self.command_selected_index = 0
            self.update_app_status("Command cancelled")
            return True
        if event.key == "down":
            if suggestions:
                self.command_selected_index = (self.command_selected_index + 1) % len(suggestions)
                self.update_app_status()
            return True
        if event.key == "up":
            if suggestions:
                self.command_selected_index = (self.command_selected_index - 1) % len(suggestions)
                self.update_app_status()
            return True
        if event.key == "tab":
            if suggestions:
                self.command_query = suggestions[self.command_selected_index][0]
                self.command_selected_index = 0
                self.update_app_status()
            return True
        if event.key == "backspace":
            self.command_query = self.command_query[:-1]
            self.command_selected_index = 0
            self.update_app_status()
            return True
        if event.key == "space":
            self.command_query += " "
            self.command_selected_index = 0
            self.update_app_status()
            return True
        if event.character and event.character.isprintable():
            self.command_query += event.character
            self.command_selected_index = 0
            self.update_app_status()
            return True
        return True

    def _cycle_project_scope(self, delta: int) -> None:
        projects = self.data_manager.get_projects()
        if not projects:
            self._publish_action_result(False, "No projects available")
            return
        project_ids = [project.id for project in projects]
        current = self.project_scope_id or self._preferred_project_id_from_active_view() or project_ids[0]
        try:
            current_index = project_ids.index(current)
        except ValueError:
            current_index = 0
        next_index = (current_index + delta) % len(project_ids)
        project_id = project_ids[next_index]
        self._set_project_scope(project_id)
        self._publish_action_result(True, f"Project focus: {self._project_label(project_id)}")

    def _set_project_scope(self, project_id: str | None) -> None:
        self.project_scope_id = project_id
        for view_id in ("dash", "sprint", "timeline", "workload"):
            try:
                view = self.query_one(ContentSwitcher).query_one(f"#{view_id}")
            except Exception:
                continue
            if hasattr(view, "set_project_scope"):
                view.set_project_scope(project_id)
        self.update_app_status()

    def _scope_label(self) -> str:
        if self.project_scope_id is None:
            return "All projects"
        return self._project_label(self.project_scope_id)

    def _project_label(self, project_id: str) -> str:
        for project in self.data_manager.get_projects():
            if project.id == project_id:
                return project.name
        return project_id

    def _first_project_id(self) -> str | None:
        projects = self.data_manager.get_projects()
        if not projects:
            return None
        return projects[0].id

    def _preferred_project_id_from_active_view(self) -> str | None:
        try:
            switcher = self.query_one(ContentSwitcher)
        except Exception:
            return None
        current = switcher.current
        if current == "workload":
            return None
        try:
            view = switcher.query_one(f"#{current}")
        except Exception:
            return None
        if hasattr(view, "preferred_project_id"):
            preferred = view.preferred_project_id()
            if isinstance(preferred, str):
                return preferred
        return None

    def _active_sprint_view(self) -> SprintBoardView | None:
        if self.query_one(ContentSwitcher).current != "sprint":
            return None
        try:
            return self.query_one(ContentSwitcher).query_one("#sprint", SprintBoardView)
        except Exception:
            return None

    def _active_workload_view(self) -> WorkloadView | None:
        if self.query_one(ContentSwitcher).current != "workload":
            return None
        try:
            return self.query_one(ContentSwitcher).query_one("#workload", WorkloadView)
        except Exception:
            return None

    def _active_detail_view(self):
        current = self.query_one(ContentSwitcher).current
        if current == "dash":
            return self.query_one(ContentSwitcher).query_one("#dash", DashboardView)
        if current == "sprint":
            return self.query_one(ContentSwitcher).query_one("#sprint", SprintBoardView)
        if current == "timeline":
            return self.query_one(ContentSwitcher).query_one("#timeline", TimelineView)
        if current == "workload":
            return self.query_one(ContentSwitcher).query_one("#workload", WorkloadView)
        return None

    def _active_visual_view(self):
        current = self.query_one(ContentSwitcher).current
        if current == "dash":
            return self.query_one(ContentSwitcher).query_one("#dash", DashboardView)
        if current == "workload":
            return self.query_one(ContentSwitcher).query_one("#workload", WorkloadView)
        if current == "timeline":
            return self.query_one(ContentSwitcher).query_one("#timeline", TimelineView)
        return None

    def _active_selection_view(self):
        current = self.query_one(ContentSwitcher).current
        if current == "dash":
            return self.query_one(ContentSwitcher).query_one("#dash", DashboardView)
        if current == "timeline":
            return self.query_one(ContentSwitcher).query_one("#timeline", TimelineView)
        if current == "workload":
            return self.query_one(ContentSwitcher).query_one("#workload", WorkloadView)
        return None

    def _execute_command(self, raw: str) -> None:
        command = raw.strip().casefold()
        if command in {"help", "?", "commands"}:
            self._publish_action_result(True, self._command_help_text())
            return
        spec = self._command_catalog().get(command)
        if spec is None:
            self._publish_action_result(False, f"Unknown command: /{raw}. Try /help.")
            return
        tab_id, action, args, _description = spec
        if tab_id:
            self.action_switch_tab(tab_id)
        self._invoke_action(action, *args)

    def _invoke_action(self, action, *args) -> None:
        result = action(*args)
        if inspect.isawaitable(result):
            self.run_worker(result, exclusive=False)

    def _command_help_text(self) -> str:
        commands = [name for name, _desc in self._command_palette_entries()]
        return "Commands: " + " ".join(f"/{name}" for name in commands)

    def _command_suggestions(self, query: str, limit: int = 8) -> list[tuple[str, str]]:
        normalized = query.strip().casefold()
        context_priority = self._command_context_priority()
        candidates: list[tuple[str, str, int, int]] = []
        for name, description in self._command_palette_entries():
            aliases = self._command_aliases().get(name, ())
            search_blob = " ".join([name, *aliases]).casefold()
            if not normalized or normalized in search_blob:
                prefix_score = 0 if name.startswith(normalized) else 1
                context_score = context_priority.get(name, 50)
                candidates.append((name, description, prefix_score, context_score))
        candidates.sort(key=lambda row: (row[2], row[3], row[0]))
        names = [(name, description) for name, description, _prefix, _context in candidates]
        limited = names[:limit]
        self.command_selected_index = min(self.command_selected_index, max(0, len(limited) - 1))
        if self.command_selected_index < 0:
            self.command_selected_index = 0
        return limited

    def _command_context_priority(self) -> dict[str, int]:
        try:
            current = self.query_one(ContentSwitcher).current
        except Exception:
            return {}
        if current == "sprint":
            return {
                "filter": 0,
                "mine": 1,
                "status": 2,
                "assignee": 3,
                "estimate": 4,
                "detail": 5,
                "close detail": 6,
            }
        if current == "dash":
            return {
                "visual": 0,
                "density": 1,
                "project focus": 2,
                "project next": 3,
                "project prev": 4,
                "preset exec": 5,
            }
        if current == "timeline":
            return {
                "visual": 0,
                "density": 1,
                "preset manager": 2,
                "project focus": 3,
            }
        if current == "workload":
            return {
                "visual": 0,
                "density": 1,
                "simulate up": 2,
                "simulate down": 3,
                "preset manager": 4,
            }
        return {}

    def _command_palette_entries(self) -> list[tuple[str, str]]:
        return [
            ("dashboard", "Switch to dashboard tab"),
            ("sprint", "Switch to sprint board tab"),
            ("timeline", "Switch to timeline tab"),
            ("workload", "Switch to workload tab"),
            ("sync", "Run Linear sync now"),
            ("history", "Open sync history screen"),
            ("visual", "Toggle chart/visual mode"),
            ("density", "Toggle chart density"),
            ("detail", "Open selected detail panel"),
            ("close detail", "Close detail panel"),
            ("project focus", "Focus a single project scope"),
            ("project next", "Focus next project"),
            ("project prev", "Focus previous project"),
            ("all projects", "Clear project scope"),
            ("filter", "Start sprint filter input"),
            ("mine", "Jump to your assigned issue"),
            ("status", "Cycle selected issue status"),
            ("assignee", "Cycle selected issue assignee"),
            ("estimate", "Cycle selected issue estimate"),
            ("simulate up", "Increase workload simulation shift"),
            ("simulate down", "Decrease workload simulation shift"),
            ("preset exec", "Apply executive layout preset"),
            ("preset manager", "Apply manager layout preset"),
            ("preset ic", "Apply IC layout preset"),
            ("quit", "Quit ProjectDash"),
        ]

    def _command_aliases(self) -> dict[str, tuple[str, ...]]:
        return {
            "dashboard": ("dash",),
            "history": ("sync history",),
            "project focus": ("project", "focus project"),
            "project next": ("next project",),
            "project prev": ("prev project", "previous project"),
            "all projects": ("project all",),
            "filter": ("sprint filter",),
            "preset manager": ("preset eng manager",),
            "preset ic": ("preset engineer",),
            "quit": ("exit",),
        }

    def _command_catalog(self) -> dict[str, tuple[str | None, object, tuple, str]]:
        catalog = {
            "dashboard": ("dash", self.action_switch_tab, ("dash",), "Switch to dashboard tab"),
            "dash": ("dash", self.action_switch_tab, ("dash",), "Switch to dashboard tab"),
            "sprint": ("sprint", self.action_switch_tab, ("sprint",), "Switch to sprint board tab"),
            "timeline": ("timeline", self.action_switch_tab, ("timeline",), "Switch to timeline tab"),
            "workload": ("workload", self.action_switch_tab, ("workload",), "Switch to workload tab"),
            "sync": (None, self.action_sync_data, (), "Run Linear sync now"),
            "sync history": (None, self.action_open_sync_history, (), "Open sync history screen"),
            "history": (None, self.action_open_sync_history, (), "Open sync history screen"),
            "visual": (None, self.action_toggle_visual_mode, (), "Toggle chart/visual mode"),
            "density": (None, self.action_toggle_graph_density, (), "Toggle chart density"),
            "detail": (None, self.action_open_detail, (), "Open selected detail panel"),
            "close detail": (None, self.action_close_detail, (), "Close detail panel"),
            "project focus": (None, self.action_level_down, (), "Focus a single project scope"),
            "project": (None, self.action_level_down, (), "Focus a single project scope"),
            "focus project": (None, self.action_level_down, (), "Focus a single project scope"),
            "project next": (None, self.action_project_next, (), "Focus next project"),
            "next project": (None, self.action_project_next, (), "Focus next project"),
            "project prev": (None, self.action_project_prev, (), "Focus previous project"),
            "prev project": (None, self.action_project_prev, (), "Focus previous project"),
            "previous project": (None, self.action_project_prev, (), "Focus previous project"),
            "all projects": (None, self.action_level_up, (), "Clear project scope"),
            "project all": (None, self.action_level_up, (), "Clear project scope"),
            "sprint filter": ("sprint", self.action_sprint_filter, (), "Start sprint filter input"),
            "filter": ("sprint", self.action_sprint_filter, (), "Start sprint filter input"),
            "mine": ("sprint", self.action_sprint_jump_to_mine, (), "Jump to your assigned issue"),
            "status": ("sprint", self.action_sprint_move_status, (), "Cycle selected issue status"),
            "assignee": ("sprint", self.action_sprint_cycle_assignee, (), "Cycle selected issue assignee"),
            "estimate": ("sprint", self.action_sprint_cycle_estimate, (), "Cycle selected issue estimate"),
            "simulate up": ("workload", self.action_simulation_increase, (), "Increase workload simulation"),
            "simulate down": ("workload", self.action_simulation_decrease, (), "Decrease workload simulation"),
            "preset exec": (None, self.action_apply_preset, ("exec",), "Apply executive layout preset"),
            "preset manager": (None, self.action_apply_preset, ("manager",), "Apply manager layout preset"),
            "preset eng manager": (None, self.action_apply_preset, ("manager",), "Apply manager layout preset"),
            "preset ic": (None, self.action_apply_preset, ("ic",), "Apply IC layout preset"),
            "preset engineer": (None, self.action_apply_preset, ("ic",), "Apply IC layout preset"),
            "quit": (None, self.action_quit, (), "Quit ProjectDash"),
        }
        catalog["exit"] = catalog["quit"]
        return catalog

    def _context_bar_text(self) -> str:
        tab_label = self._active_tab_label()
        summary = self._context_summary_for_active_view()
        mode = summary.get("mode", "-")
        density = summary.get("density", "-")
        filter_value = summary.get("filter", "none")
        selected = summary.get("selected", "none")
        if tab_label in {"Dashboard", "Timeline"} and selected not in {"none", ""}:
            selected = self._project_label(selected) if selected != "none" else selected
        return (
            f"Context | Tab: {tab_label} | Scope: {self._scope_label()} | Mode: {mode} | Density: {density} | "
            f"Filter: {filter_value} | Selected: {selected} | Preset: {self.active_preset}"
        )

    def _active_tab_label(self) -> str:
        current = self.query_one(ContentSwitcher).current
        mapping = {
            "dash": "Dashboard",
            "sprint": "Sprint",
            "timeline": "Timeline",
            "workload": "Workload",
        }
        return mapping.get(current, current)

    def _context_summary_for_active_view(self) -> dict[str, str]:
        view = self._active_detail_view()
        if view is None:
            return {"mode": "-", "density": "-", "filter": "none", "selected": "none"}
        if hasattr(view, "context_summary"):
            summary = view.context_summary()
            if isinstance(summary, dict):
                return {k: str(v) for k, v in summary.items()}
        return {"mode": "-", "density": "-", "filter": "none", "selected": "none"}

    def _help_overlay_text(self) -> str:
        tab_label = self._active_tab_label()
        tab_specific = {
            "Dashboard": "j/k select project, v mode, g density, Enter/Esc detail, ]/[ scope",
            "Sprint": "h/j/k/l move, / filter, m/a/e quick actions",
            "Timeline": "j/k select row (project mode), v mode, g density, Enter/Esc detail, ]/[ scope",
            "Workload": "j/k select member, v mode, g density, =/- simulation shift",
        }
        current_help = tab_specific.get(tab_label, "")
        return (
            "KEYBOARD HELP\n"
            "Global: d/s/t/w tabs • h/l context • ]/[ scope • ,/. project • / command\n"
            "Detail: Enter open/confirm • Esc close/clear • ? toggle help\n"
            "Presets: 1 Exec • 2 Manager • 3 IC\n"
            f"{tab_label}: {current_help}\n"
            "Quick commands: /visual /density /detail /preset exec /preset manager /preset ic"
        )

    def _publish_action_result(self, ok: bool, message: str) -> None:
        final_message = message
        if not ok and "linear_status_mappings." in message and not self.missing_mapping_hint_shown:
            final_message = f"{message} | Hint: update projectdash.config.json then press y to sync."
            self.missing_mapping_hint_shown = True
        self.update_app_status(final_message)
        self._notify(final_message, severity="information" if ok else "error")


def run() -> None:
    load_dotenv()
    app = ProjectDash()
    app.run()


if __name__ == "__main__":
    run()
