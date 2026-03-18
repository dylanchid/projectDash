from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Tabs, Tab, ContentSwitcher, Static
from textual import events
import inspect
import os
from datetime import datetime
from uuid import uuid4
from projectdash.views.dashboard import DashboardView
from projectdash.views.github_dashboard import GitHubDashboardView
from projectdash.views.blocked_queue import BlockedQueueView
from projectdash.views.sprint_board import SprintBoardView
from projectdash.views.workload import WorkloadView
from projectdash.views.timeline import TimelineView
from projectdash.views.ideation_gallery import IdeationGalleryView
from projectdash.views.portfolio import PortfolioView
from projectdash.views.sync_history import SyncHistoryScreen
from projectdash.views.issue_flow import IssueFlowScreen
from projectdash.views.sprint_issue import SprintIssueScreen
from projectdash.views.section_picker import SectionPickerScreen
from projectdash.views.modals import ConfirmationScreen
from projectdash.data import DataManager
from projectdash.config import AppConfig
from projectdash.env import load_project_env
from projectdash.models import AgentRun
from projectdash.enums import AgentRunStatus, SyncResult
from projectdash.services import MetricsService


class ProjectDash(App):
    CSS_PATH = "projectdash.tcss"
    AGENT_RUN_REFRESH_INTERVAL_SECONDS = 3.0
    AGENT_RUN_REFRESH_LIMIT = 100
    PROFILE_DEFAULT_TAB = {
        "ic": "sprint",
        "lead": "github",
        "manager": "timeline",
    }

    BINDINGS = [
        ("d", "switch_tab('dash')", "Linear Dashboard"),
        ("G", "switch_tab('github')", "GitHub Dashboard"),
        ("s", "switch_tab('sprint')", "Sprint Board"),
        ("t", "switch_tab('timeline')", "Timeline"),
        ("w", "switch_tab('workload')", "Workload"),
        ("n", "switch_tab('ideation')", "Ideation Gallery"),
        ("X", "switch_tab('portfolio')", "Portfolio"),
        ("K", "toggle_hotkey_bar", "Toggle Hotkey Bar"),
        ("z", "toggle_sidebar", "Toggle Sidebar"),
        ("9", "line_pan_left", "Line Pan Left"),
        ("0", "line_pan_right", "Line Pan Right"),
        ("7", "line_style_toggle", "Line Style Toggle"),
        ("semicolon", "line_series_prev", "Line Series Prev"),
        ("apostrophe", "line_series_next", "Line Series Next"),
        ("h", "context_left", "Left"),
        ("l", "context_right", "Right"),
        ("j", "sprint_down", "Sprint Down"),
        ("k", "sprint_up", "Sprint Up"),
        ("pageup", "page_up", "Page Up"),
        ("pagedown", "page_down", "Page Down"),
        ("[", "level_up", "All Projects"),
        ("]", "level_down", "Project Focus"),
        ("comma", "project_prev", "Prev Project"),
        (".", "project_next", "Next Project"),
        ("left", "sprint_left", "Sprint Left"),
        ("right", "sprint_right", "Sprint Right"),
        ("shift+up", "level_up", "Higher Level"),
        ("shift+down", "level_down", "Lower Level"),
        ("enter", "open_detail", "Open Detail"),
        ("shift+enter", "open_item_view", "Open Item View"),
        ("shift+space", "open_detail", "Open Detail"),
        ("escape", "close_detail", "Close Detail"),
        ("m", "cycle_status", "Cycle Status"),
        ("shift+m", "github_merge_pr", "Merge PR"),
        ("x", "close_issue", "Close Issue"),
        ("a", "sprint_cycle_assignee", "Cycle Assignee"),
        ("e", "sprint_cycle_estimate", "Cycle Estimate"),
        ("c", "comment_issue", "Draft Comment"),
        ("o", "open_primary", "Open Primary"),
        ("O", "open_secondary", "Open Secondary"),
        ("p", "sprint_open_editor", "Open In Editor"),
        ("T", "sprint_open_terminal_editor", "Terminal Editor"),
        ("f", "sprint_filter", "Filter Sprint"),
        ("/", "open_filter", "Filter/Search"),
        ("u", "sprint_jump_to_mine", "Jump To Mine"),
        ("r", "drilldown_or_rerun", "Rerun/Drilldown"),
        ("y", "sync_data", "Sync Linear"),
        ("Y", "sync_github", "Sync GitHub"),
        ("F", "toggle_sync_freshness", "Toggle Sync Freshness"),
        ("S", "github_filter_state", "GitHub Filter State"),
        ("L", "github_filter_linked", "GitHub Filter Linked"),
        ("C", "github_filter_failing", "GitHub Filter Failing"),
        ("R", "github_clear_filters", "GitHub Clear Filters"),
        ("D", "github_clear_drilldown", "GitHub Return From Drilldown"),
        ("b", "copy_primary", "Copy Primary"),
        ("i", "jump_context", "Jump Context"),
        ("B", "timeline_blocked_drilldown", "Blocker Drilldown"),
        ("A", "github_trigger_agent", "Trigger Agent Run"),
        ("I", "jump_context", "Jump Context"),
        ("v", "github_approve_pr", "Approve PR"),
        ("V", "toggle_visual_mode", "Toggle Visual Mode"),
        ("g", "toggle_graph_density", "Toggle Graph Density"),
        ("=", "simulation_increase", "Simulation +1"),
        ("-", "simulation_decrease", "Simulation -1"),
        ("?", "toggle_help_overlay", "Help Overlay"),
        ("1", "apply_preset('exec')", "Preset Exec"),
        ("2", "apply_preset('manager')", "Preset Manager"),
        ("3", "apply_preset('ic')", "Preset IC"),
        ("ctrl+e", "toggle_layout_edit", "Toggle Layout Edit"),
        ("tab", "layout_cycle_section", "Layout Next Section"),
        ("shift+tab", "layout_cycle_section_prev", "Layout Prev Section"),
        ("ctrl+shift+left", "layout_move_left", "Layout Move Left"),
        ("ctrl+shift+right", "layout_move_right", "Layout Move Right"),
        ("ctrl+left", "layout_shrink", "Layout Shrink"),
        ("ctrl+right", "layout_grow", "Layout Grow"),
        ("plus", "open_section_picker", "Add Section"),
        ("delete", "layout_remove_section", "Remove Section"),
        ("H", "open_sync_history", "Sync History"),
        ("P", "open_issue_flow", "Issue Flow"),
        ("ctrl+b", "back_context", "Back"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = AppConfig.from_env()
        self.data_manager = DataManager(self.config)
        self.metrics = MetricsService(self.config)
        self.profile = os.getenv("PD_PROFILE", "ic").strip().casefold() or "ic"
        self._default_tab_id = self.PROFILE_DEFAULT_TAB.get(self.profile, "sprint")
        self.tab_ids = ["dash", "github", "sprint", "blocked", "timeline", "workload", "ideation", "portfolio"]
        self.last_ui_error: str | None = None
        self.missing_mapping_hint_shown = False
        self.command_active = False
        self.command_query = ""
        self.command_selected_index = 0
        self.project_scope_id: str | None = None
        self.help_overlay_active = False
        self.active_preset = "custom"
        self._sync_popup_timer = None
        self._sync_freshness_popup_timer = None
        self._sync_freshness_popup_active = False
        self._last_sync_freshness_marker: tuple[tuple[str, str | None, str | None, str | None], ...] | None = None
        self._agent_run_refresh_timer = None
        self._agent_run_refresh_inflight = False
        self._agent_run_status_by_id: dict[str, str] = {}
        self.page_focus_locked = True
        self.page_focus_section = "main"
        self._view_filter_state_by_view: dict[str, dict[str, object]] = {}
        self._last_active_tab_id = self._default_tab_id
        self.detail_sidebar_visible = True
        self.hotkey_bar_visible = True
        self.sync_freshness_visible = False
        
        # X1: Performance tracking
        self.perf_log: list[dict[str, Any]] = []
        self.perf_budget_ms = 100
        self._sync_freshness_override: bool | None = None
        self.layout_edit_mode = False
        self._navigation_context_stack: list[dict[str, object]] = []

    def _track_perf(self, name: str, start_time: float) -> None:
        import time
        duration_ms = (time.time() - start_time) * 1000
        self.perf_log.append({
            "action": name,
            "duration_ms": duration_ms,
            "timestamp": datetime.now().isoformat()
        })
        # Keep log size manageable
        if len(self.perf_log) > 1000:
            self.perf_log = self.perf_log[-1000:]
            
        if duration_ms > self.perf_budget_ms:
            # We could log this to a file or show a subtle indicator in dev mode
            if os.getenv("PD_DEV") == "1":
                self.log(f"PERF WARNING: action '{name}' took {duration_ms:.2f}ms (budget {self.perf_budget_ms}ms)")

    async def on_mount(self) -> None:
        await self.data_manager.initialize()
        await self.data_manager.scan_portfolio()
        await self._refresh_agent_run_snapshot(notify=False)
        self._start_agent_run_refresh_timer()
        self.refresh_views()
        self._apply_page_focus_mode()
        self.update_app_status()

    def on_unmount(self) -> None:
        for timer_attr in ("_sync_popup_timer", "_sync_freshness_popup_timer", "_agent_run_refresh_timer"):
            timer = getattr(self, timer_attr, None)
            if timer is None:
                continue
            try:
                timer.stop()
            except Exception:
                pass
            setattr(self, timer_attr, None)

    def refresh_views(self) -> None:
        import time
        start = time.time()
        self._apply_sync_freshness_policy()
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
        self._track_perf("refresh_views", start)

    async def action_sync_data(self) -> None:
        self.update_app_status("Syncing...")
        try:
            await self.data_manager.sync_with_linear()
        except Exception:
            pass
        self.refresh_views()
        self.update_app_status()
        self._show_sync_popup()
        if self.data_manager.last_sync_result == SyncResult.SUCCESS:
            self._notify("Sync complete", severity="information")
        else:
            self._notify(f"Sync failed: {self.data_manager.sync_status_summary()}", severity="error")

    async def action_sync_github(self) -> None:
        self.update_app_status("Syncing GitHub...")
        try:
            await self.data_manager.sync_with_github()
        except Exception:
            pass
        self.refresh_views()
        self.update_app_status()
        self._show_sync_popup()
        if self.data_manager.last_sync_result == SyncResult.SUCCESS:
            self._notify("GitHub sync complete", severity="information")
        else:
            self._notify(f"GitHub sync failed: {self.data_manager.sync_status_summary()}", severity="error")

    def action_open_sync_history(self) -> None:
        self.push_screen(SyncHistoryScreen())

    def action_open_issue_flow(self) -> None:
        issue_id = None
        sprint = self._active_sprint_view()
        if sprint and not sprint.filter_active:
            issue = sprint.current_issue()
            issue_id = issue.id if issue else None
        if issue_id is None:
            github = self._active_github_view()
            if github:
                issue_id = github.selected_issue_for_jump()
        if not issue_id:
            self._publish_action_result(False, "No linked issue selected for issue flow")
            return
        self._push_navigation_context(
            route="issue_flow",
            payload={
                "issue_id": issue_id,
                "origin": self._capture_navigation_origin(),
            },
        )
        self.push_screen(IssueFlowScreen(issue_id), self._on_issue_flow_closed)
        self._publish_action_result(True, f"Opened issue flow for {issue_id}")

    def _capture_navigation_origin(self) -> dict[str, object]:
        tab_id = self._current_tab_id()
        origin: dict[str, object] = {"tab_id": tab_id}
        snapshot = self._capture_view_state_snapshot(tab_id)
        if snapshot:
            origin["view_state"] = snapshot
        return origin

    def _capture_view_state_snapshot(self, view_id: str) -> dict[str, object] | None:
        try:
            view = self.query_one(ContentSwitcher).query_one(f"#{view_id}")
        except Exception:
            return None
        if not hasattr(view, "capture_filter_state"):
            return None
        try:
            state = view.capture_filter_state()
        except Exception:
            return None
        return state if isinstance(state, dict) else None

    def _restore_view_state_snapshot(self, view_id: str, state: dict[str, object] | None) -> None:
        if not state:
            return
        try:
            view = self.query_one(ContentSwitcher).query_one(f"#{view_id}")
        except Exception:
            return
        if not hasattr(view, "restore_filter_state"):
            return
        try:
            view.restore_filter_state(state)
        except Exception:
            return

    def _push_navigation_context(self, *, route: str, payload: dict[str, object]) -> None:
        self._navigation_context_stack.append({"route": route, "payload": payload})

    def _pop_navigation_context(self, route: str) -> dict[str, object] | None:
        for index in range(len(self._navigation_context_stack) - 1, -1, -1):
            item = self._navigation_context_stack[index]
            if item.get("route") != route:
                continue
            self._navigation_context_stack.pop(index)
            payload = item.get("payload")
            return payload if isinstance(payload, dict) else None
        return None

    def _on_issue_flow_closed(self, _result: object | None = None) -> None:
        context = self._pop_navigation_context("issue_flow")
        if not context:
            return
        origin = context.get("origin")
        self._restore_navigation_origin(origin)

    def _restore_navigation_origin(self, origin: object) -> bool:
        if not isinstance(origin, dict):
            return False
        tab_id = str(origin.get("tab_id") or "").strip()
        if tab_id and tab_id in self.tab_ids:
            self.action_switch_tab(tab_id)
        snapshot = origin.get("view_state")
        if tab_id and isinstance(snapshot, dict):
            self._restore_view_state_snapshot(tab_id, snapshot)
        self.update_app_status()
        return True

    def _restore_context_route(self, route: str) -> bool:
        context = self._pop_navigation_context(route)
        if not context:
            return False
        return self._restore_navigation_origin(context.get("origin"))

    def action_open_command(self) -> None:
        self._activate_command_input("")

    def action_open_filter(self) -> None:
        sprint = self._active_sprint_view()
        if sprint is not None:
            self.action_sprint_filter()
            return
        github = self._active_github_view()
        if github is not None:
            self._activate_command_input("github ")
            return
        timeline = self._active_timeline_view()
        if timeline is not None:
            if getattr(timeline, "visual_mode", "") == "blocked":
                self._activate_command_input("blocked ")
            else:
                self._activate_command_input("timeline ")
            return
        workload = self._active_workload_view()
        if workload is not None:
            self._activate_command_input("workload ")
            return
        self._activate_command_input("")

    def _activate_command_input(self, initial_query: str) -> None:
        self.command_active = True
        self.help_overlay_active = False
        self.command_query = initial_query
        self.command_selected_index = 0
        self.update_app_status("Command/search mode: type /help, Enter to run, Esc to cancel.")

    def action_toggle_help_overlay(self) -> None:
        self.help_overlay_active = not self.help_overlay_active
        if self.help_overlay_active:
            self.command_active = False
            self.command_query = ""
            self.command_selected_index = 0
            self.update_app_status("Help overlay open. Press ? or Esc to close.")
        else:
            self.update_app_status("Help overlay closed")

    def action_toggle_sidebar(self) -> None:
        self.detail_sidebar_visible = not self.detail_sidebar_visible
        if not self.detail_sidebar_visible:
            self.page_focus_section = "main"
        self._apply_sidebar_visibility()
        state = "shown" if self.detail_sidebar_visible else "hidden"
        self.update_app_status(f"Sidebar {state}")

    def action_toggle_hotkey_bar(self) -> None:
        self.hotkey_bar_visible = not self.hotkey_bar_visible
        self.update_app_status(f"Hotkey bar {'shown' if self.hotkey_bar_visible else 'hidden'}")

    def action_toggle_sync_freshness(self) -> None:
        auto = self.data_manager.should_show_sync_freshness()
        if self._sync_freshness_override is None:
            self._sync_freshness_override = not auto
        else:
            self._sync_freshness_override = None
        self._apply_sync_freshness_policy()
        self.refresh_views()
        state = "shown" if self.sync_freshness_visible else "hidden"
        mode = "auto" if self._sync_freshness_override is None else "manual"
        self.update_app_status(f"Sync freshness {state} ({mode})")

    def action_toggle_layout_edit(self) -> None:
        view = self._active_customizable_view()
        if view is None:
            self._publish_action_result(False, "Active page does not support layout editing")
            return
        self.layout_edit_mode = not self.layout_edit_mode
        ok, message = view.set_layout_edit_mode(self.layout_edit_mode)
        self._publish_action_result(ok, message)

    def action_layout_cycle_section(self) -> None:
        self._run_layout_action("cycle_selected_section", 1)

    def action_layout_cycle_section_prev(self) -> None:
        self._run_layout_action("cycle_selected_section", -1)

    def action_layout_move_left(self) -> None:
        self._run_layout_action("move_selected_section", -1)

    def action_layout_move_right(self) -> None:
        self._run_layout_action("move_selected_section", 1)

    def action_layout_shrink(self) -> None:
        self._run_layout_action("resize_selected_section", -4)

    def action_layout_grow(self) -> None:
        self._run_layout_action("resize_selected_section", 4)

    def action_layout_remove_section(self) -> None:
        self._run_layout_action("remove_selected_section")

    def action_open_section_picker(self) -> None:
        view = self._active_customizable_view()
        if view is None:
            self._publish_action_result(False, "Active page does not support section picker")
            return
        if not self.layout_edit_mode:
            self._publish_action_result(False, "Enable layout edit mode first (Ctrl+E)")
            return
        options = [(spec.section_id, spec.title) for spec in view.available_sections_to_add()]
        self.push_screen(SectionPickerScreen(options), self._on_section_picker_closed)

    def _on_section_picker_closed(self, section_id: str | None) -> None:
        if not section_id:
            return
        view = self._active_customizable_view()
        if view is None:
            self._publish_action_result(False, "Active page does not support section picker")
            return
        ok, message = view.add_section(section_id)
        self._publish_action_result(ok, message)

    def _run_layout_action(self, method_name: str, *args) -> None:
        view = self._active_customizable_view()
        if view is None:
            self._publish_action_result(False, "Active page does not support layout editing")
            return
        if not self.layout_edit_mode:
            self._publish_action_result(False, "Enable layout edit mode first (Ctrl+E)")
            return
        method = getattr(view, method_name, None)
        if method is None:
            self._publish_action_result(False, "Layout action unavailable on this view")
            return
        ok, message = method(*args)
        self._publish_action_result(ok, message)

    def _apply_sync_freshness_policy(self) -> None:
        if self._sync_freshness_popup_active:
            self.sync_freshness_visible = True
            return
        if self._sync_freshness_override is None:
            self.sync_freshness_visible = False
            return
        self.sync_freshness_visible = self._sync_freshness_override

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
        if workload is not None and hasattr(workload, "adjust_simulation"):
            ok, message = workload.adjust_simulation(1)
            self._publish_action_result(ok, message)
            return
        ideation = self._active_ideation_view()
        if ideation is None or not hasattr(ideation, "adjust_line_zoom"):
            return
        ok, message = ideation.adjust_line_zoom(1)
        self._publish_action_result(ok, message)

    def action_simulation_decrease(self) -> None:
        workload = self._active_workload_view()
        if workload is not None and hasattr(workload, "adjust_simulation"):
            ok, message = workload.adjust_simulation(-1)
            self._publish_action_result(ok, message)
            return
        ideation = self._active_ideation_view()
        if ideation is None or not hasattr(ideation, "adjust_line_zoom"):
            return
        ok, message = ideation.adjust_line_zoom(-1)
        self._publish_action_result(ok, message)

    def action_line_pan_left(self) -> None:
        ideation = self._active_ideation_view()
        if ideation is None or not hasattr(ideation, "adjust_line_pan"):
            return
        ok, message = ideation.adjust_line_pan(-1)
        self._publish_action_result(ok, message)

    def action_line_pan_right(self) -> None:
        ideation = self._active_ideation_view()
        if ideation is None or not hasattr(ideation, "adjust_line_pan"):
            return
        ok, message = ideation.adjust_line_pan(1)
        self._publish_action_result(ok, message)

    def action_line_series_prev(self) -> None:
        ideation = self._active_ideation_view()
        if ideation is None or not hasattr(ideation, "cycle_line_series"):
            return
        ok, message = ideation.cycle_line_series(-1)
        self._publish_action_result(ok, message)

    def action_line_series_next(self) -> None:
        ideation = self._active_ideation_view()
        if ideation is None or not hasattr(ideation, "cycle_line_series"):
            return
        ok, message = ideation.cycle_line_series(1)
        self._publish_action_result(ok, message)

    def action_line_style_toggle(self) -> None:
        ideation = self._active_ideation_view()
        if ideation is None or not hasattr(ideation, "cycle_line_render_style"):
            return
        ok, message = ideation.cycle_line_render_style()
        self._publish_action_result(ok, message)

    def action_open_detail(self) -> None:
        sprint = self._active_sprint_view()
        if sprint and sprint.filter_active:
            ok, message = sprint.commit_filter()
            self._publish_action_result(ok, message)
            return
        if sprint is not None and not sprint.filter_active:
            issue = sprint.current_issue()
            if issue is None:
                return
            if sprint.detail_open:
                self.push_screen(SprintIssueScreen(issue.id))
                self._publish_action_result(True, f"Opened sprint item view for {issue.id}")
                return
        view = self._active_detail_view()
        if view is None:
            return
        if hasattr(view, "open_detail"):
            view.open_detail()
            self.update_app_status()

    def action_open_primary(self) -> None:
        import time
        start = time.time()
        view = self._active_detail_view()
        if view is None:
            return
        if hasattr(view, "open_primary"):
            ok, message = view.open_primary()
            self._publish_action_result(ok, message, track=True)
        self._track_perf("open_primary", start)

    def action_open_secondary(self) -> None:
        import time
        start = time.time()
        view = self._active_detail_view()
        if view is None:
            return
        if hasattr(view, "open_secondary"):
            ok, message = view.open_secondary()
            self._publish_action_result(ok, message, track=True)
        self._track_perf("open_secondary", start)

    def action_copy_primary(self) -> None:
        import time
        start = time.time()
        view = self._active_detail_view()
        if view is None:
            return
        if hasattr(view, "copy_primary"):
            ok, message = view.copy_primary()
            self._publish_action_result(ok, message, track=True)
        self._track_perf("copy_primary", start)

    def action_jump_context(self) -> None:
        import time
        start = time.time()
        view = self._active_detail_view()
        if view is None:
            return
        if hasattr(view, "jump_context"):
            ok, message = view.jump_context()
            self._publish_action_result(ok, message, track=True)
        self._track_perf("jump_context", start)

    async def action_cycle_status(self) -> None:
        import time
        start = time.time()
        view = self._active_detail_view()
        if view is None:
            return
        
        method = None
        if hasattr(view, "cycle_status"):
            method = view.cycle_status
        elif hasattr(view, "cycle_selected_status"):
            method = view.cycle_selected_status
            
        if method:
            result = method()
            if inspect.isawaitable(result):
                ok, message = await result
            else:
                ok, message = result
            self._publish_action_result(ok, message, track=True)
        self._track_perf("cycle_status", start)

    async def action_close_issue(self) -> None:
        import time
        start = time.time()
        view = self._active_detail_view()
        if view is None:
            return
            
        method = None
        if hasattr(view, "close_issue"):
            method = view.close_issue
        elif hasattr(view, "close_selected_issue"):
            method = view.close_selected_issue
            
        if method:
            result = method()
            if inspect.isawaitable(result):
                ok, message = await result
            else:
                ok, message = result
            self._publish_action_result(ok, message, track=True)
        self._track_perf("close_issue", start)

    def action_comment_issue(self) -> None:
        import time
        start = time.time()
        view = self._active_detail_view()
        if view is None:
            return
        if hasattr(view, "comment_issue"):
            ok, message = view.comment_issue()
            self._publish_action_result(ok, message, track=True)
        elif hasattr(view, "draft_comment_for_selected_issue"):
            ok, message = view.draft_comment_for_selected_issue()
            self._publish_action_result(ok, message, track=True)
        self._track_perf("comment_issue", start)

    def action_open_item_view(self) -> None:
        sprint = self._active_sprint_view()
        if sprint is None or sprint.filter_active:
            self._publish_action_result(False, "Item view is available from Sprint board")
            return
        issue = sprint.current_issue()
        if issue is None:
            self._publish_action_result(False, "No sprint issue selected")
            return
        self.push_screen(SprintIssueScreen(issue.id))
        self._publish_action_result(True, f"Opened sprint item view for {issue.id}")

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

    def action_back_context(self) -> None:
        try:
            if isinstance(self.screen, IssueFlowScreen):
                self.screen.action_close_screen()
                return
            if isinstance(self.screen, SprintIssueScreen):
                self.screen.action_close_screen()
                return
        except Exception:
            pass

        github = self._active_github_view()
        if github is not None and getattr(github, "drilldown_issue_id", None):
            self.action_github_clear_drilldown()
            return

        timeline = self._active_timeline_view()
        if timeline is not None and getattr(timeline, "visual_mode", None) == "blocked":
            self.action_timeline_blocked_drilldown()
            return

        if self._restore_context_route("github_jump_issue"):
            self._publish_action_result(True, "Returned to GitHub context")
            return

        self.action_close_detail()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if self.command_active:
            return False
        if not self.page_focus_locked and action in {
            "context_left",
            "context_right",
            "sprint_left",
            "sprint_right",
            "sprint_down",
            "sprint_up",
        }:
            return False
        return True

    def compose(self) -> ComposeResult:
        yield Tabs(
            Tab("Linear", id="dash"),
            Tab("GitHub", id="github"),
            Tab("Sprint Board", id="sprint"),
            Tab("Blockers", id="blocked"),
            Tab("Timeline", id="timeline"),
            Tab("Workload", id="workload"),
            Tab("Ideation", id="ideation"),
            Tab("Portfolio", id="portfolio"),
            id="app-tabs",
            active=self._default_tab_id,
        )
        with Horizontal(id="top-status-bar"):
            yield Static("Page: initializing...", id="page-indicator")
            yield Static("Context: initializing...", id="context-bar")
        yield Static("", id="sync-history")
        yield Static("", id="help-overlay")
        yield Static("", id="command-palette")
        yield Static("", id="command-prompt")
        with ContentSwitcher(initial=self._default_tab_id):
            yield DashboardView(id="dash")
            yield GitHubDashboardView(id="github")
            yield SprintBoardView(id="sprint")
            yield BlockedQueueView(id="blocked")
            yield TimelineView(id="timeline")
            yield WorkloadView(id="workload")
            yield IdeationGalleryView(id="ideation")
            yield PortfolioView(id="portfolio")
        yield Static("Keys: loading...", id="hotkey-bar")

    def update_app_status(self, override_message: str | None = None) -> None:
        data = self.data_manager
        sync_state = data.sync_status_summary()
        if data.last_sync_result == SyncResult.SUCCESS and data.last_sync_at:
            sync_state = f"{sync_state} @ {data.last_sync_at}"
        status_text = override_message or f"Sync: {sync_state}"
        try:
            self.query_one("#page-indicator", Static).update(f"Page: {self._active_tab_label()}")
        except Exception:
            pass

        try:
            self.query_one("#context-bar", Static).update(self._context_bar_text(status_text))
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
            command_prompt = self.query_one("#command-prompt", Static)
            command_prompt.update(prompt)
            command_prompt.display = self.command_active
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
            command_palette = self.query_one("#command-palette", Static)
            command_palette.update(palette_text)
            command_palette.display = self.command_active
        except Exception:
            pass

        try:
            hotkey_bar = self.query_one("#hotkey-bar", Static)
            hotkey_bar.update(self._hotkey_bar_text())
            hotkey_bar.display = self.hotkey_bar_visible and not self.command_active
        except Exception:
            pass
        self._apply_sidebar_visibility()
        self._check_sync_freshness_updates()

    def _apply_sidebar_visibility(self) -> None:
        try:
            widgets = self.query(".detail-sidebar")
        except Exception:
            return
        for widget in widgets:
            try:
                widget.display = self.detail_sidebar_visible
            except Exception:
                pass

    def _notify(self, message: str, severity: str = "information") -> None:
        try:
            self.notify(message, severity=severity)
        except Exception:
            self.update_app_status(message)

    def _show_sync_popup(self, duration_seconds: float = 2.5) -> None:
        lines = self.data_manager.latest_sync_history_lines(limit=1)
        if not lines:
            return
        try:
            popup = self.query_one("#sync-history", Static)
            popup.update(f"Recent: {lines[0]}")
            popup.display = True
        except Exception:
            return
        if self._sync_popup_timer is not None:
            try:
                self._sync_popup_timer.stop()
            except Exception:
                pass
        self._sync_popup_timer = self.set_timer(duration_seconds, self._clear_sync_popup)

    def _clear_sync_popup(self) -> None:
        try:
            popup = self.query_one("#sync-history", Static)
            popup.update("")
            popup.display = False
        except Exception:
            pass
        self._sync_popup_timer = None

    def _sync_freshness_marker(self) -> tuple[tuple[str, str | None, str | None, str | None], ...]:
        markers: list[tuple[str, str | None, str | None, str | None]] = []
        for connector in ("linear", "github"):
            snapshot = self.data_manager.connector_freshness_snapshot(connector)
            markers.append(
                (
                    str(snapshot.get("state") or "unknown"),
                    snapshot.get("last_success_at"),
                    snapshot.get("last_attempt_at"),
                    snapshot.get("last_error"),
                )
            )
        return tuple(markers)

    def _check_sync_freshness_updates(self) -> None:
        marker = self._sync_freshness_marker()
        if self._last_sync_freshness_marker is None:
            self._last_sync_freshness_marker = marker
            return
        if marker == self._last_sync_freshness_marker:
            return
        self._last_sync_freshness_marker = marker
        self._trigger_sync_freshness_popup()

    def _trigger_sync_freshness_popup(self, duration_seconds: float = 6.0) -> None:
        if self._sync_freshness_override is False:
            return
        if self._sync_freshness_override is True:
            return
        self._sync_freshness_popup_active = True
        self._apply_sync_freshness_policy()
        self.refresh_views()
        if self._sync_freshness_popup_timer is not None:
            try:
                self._sync_freshness_popup_timer.stop()
            except Exception:
                pass
        self._sync_freshness_popup_timer = self.set_timer(duration_seconds, self._clear_sync_freshness_popup)

    def _clear_sync_freshness_popup(self) -> None:
        self._sync_freshness_popup_active = False
        self._apply_sync_freshness_policy()
        self.refresh_views()
        self._sync_freshness_popup_timer = None

    def _start_agent_run_refresh_timer(self) -> None:
        if self._agent_run_refresh_timer is not None:
            try:
                self._agent_run_refresh_timer.stop()
            except Exception:
                pass
        self._agent_run_refresh_timer = self.set_interval(
            self.AGENT_RUN_REFRESH_INTERVAL_SECONDS,
            self._queue_agent_run_refresh,
        )

    def _queue_agent_run_refresh(self) -> None:
        if self._agent_run_refresh_inflight:
            return
        self._agent_run_refresh_inflight = True
        self.run_worker(self._poll_agent_run_refresh(), exclusive=False)

    async def _poll_agent_run_refresh(self) -> None:
        try:
            await self._refresh_agent_run_snapshot(notify=True)
        except Exception:
            pass
        finally:
            self._agent_run_refresh_inflight = False

    async def _refresh_agent_run_snapshot(self, *, notify: bool) -> None:
        runs = await self.data_manager.get_agent_runs(limit=self.AGENT_RUN_REFRESH_LIMIT)
        latest_status_by_id = {run.id: run.status for run in runs}
        if not self._agent_run_status_by_id:
            self._agent_run_status_by_id = latest_status_by_id
            return

        status_changed = False
        terminal_transitions: list[AgentRun] = []
        for run in runs:
            previous_status = self._agent_run_status_by_id.get(run.id)
            if previous_status == run.status:
                continue
            status_changed = True
            if previous_status in {AgentRunStatus.QUEUED, AgentRunStatus.RUNNING} and run.status in {AgentRunStatus.COMPLETED, AgentRunStatus.FAILED}:
                terminal_transitions.append(run)

        self._agent_run_status_by_id = latest_status_by_id
        if not status_changed:
            return

        self.refresh_views()
        if not notify or not terminal_transitions:
            return

        latest_message: str | None = None
        for run in terminal_transitions:
            message = self._agent_run_transition_message(run)
            latest_message = message
            self._notify(message, severity="information" if run.status == AgentRunStatus.COMPLETED else "error")
        if latest_message:
            self.update_app_status(latest_message)

    def _agent_run_transition_message(self, run: AgentRun) -> str:
        pr_number = str((run.artifacts or {}).get("pull_request_number") or "").strip()
        pr_label = f"PR #{pr_number}" if pr_number else (run.pr_id or "unlinked PR")
        if run.status == AgentRunStatus.COMPLETED:
            return f"Agent run {run.id} completed for {pr_label}"
        return f"Agent run {run.id} failed for {pr_label}"

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        import time
        start = time.time()
        previous_tab = self._last_active_tab_id
        if previous_tab and previous_tab != event.tab.id:
            self._persist_view_filter_state(previous_tab)
        self.query_one(ContentSwitcher).current = event.tab.id
        self._restore_view_filter_state(event.tab.id)
        self.page_focus_section = "main"
        self._last_active_tab_id = event.tab.id
        self._apply_page_focus_mode()
        self.update_app_status()
        self._track_perf(f"tab_activated:{event.tab.id}", start)

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(Tabs).active = tab_id

    def _current_tab_id(self) -> str:
        try:
            current = self.query_one(ContentSwitcher).current
        except Exception:
            current = None
        if current in self.tab_ids:
            return str(current)
        return self._last_active_tab_id

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

    def action_page_down(self) -> None:
        sprint = self._active_sprint_view()
        if sprint and not sprint.filter_active:
            if hasattr(sprint, "page_selection"):
                sprint.page_selection(1)
            else:
                sprint.move_cursor(row_delta=5)
            return
        view = self._active_selection_view()
        if view is None:
            return
        if hasattr(view, "page_selection"):
            view.page_selection(1)
            return
        if hasattr(view, "move_selection"):
            view.move_selection(5)

    def action_page_up(self) -> None:
        sprint = self._active_sprint_view()
        if sprint and not sprint.filter_active:
            if hasattr(sprint, "page_selection"):
                sprint.page_selection(-1)
            else:
                sprint.move_cursor(row_delta=-5)
            return
        view = self._active_selection_view()
        if view is None:
            return
        if hasattr(view, "page_selection"):
            view.page_selection(-1)
            return
        if hasattr(view, "move_selection"):
            view.move_selection(-5)

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
        if sprint and not sprint.filter_active:
            ok, message = await sprint.cycle_selected_status()
            self._publish_action_result(ok, message)
            return
            
        github = self._active_github_view()
        if github:
            issue_id = github.selected_issue_for_jump()
            if not issue_id:
                self._publish_action_result(False, "No linked issue for status update")
                return
            statuses = self.data_manager.config.linear_status_sequence
            ok, message = await self.data_manager.cycle_issue_status(issue_id, statuses)
            self._publish_action_result(ok, message)
            github.refresh_view()

    async def action_sprint_close_issue(self) -> None:
        sprint = self._active_sprint_view()
        if sprint and not sprint.filter_active:
            issue = sprint.current_issue()
            if not issue:
                return

            def on_confirm(confirmed: bool) -> None:
                if confirmed:
                    async def do_close():
                        ok, message = await sprint.close_selected_issue()
                        self._publish_action_result(ok, message)
                    self.run_worker(do_close(), exclusive=False)
            
            self.push_screen(
                ConfirmationScreen(f"Close issue {issue.id}: {issue.title}?", title="Close Issue"),
                on_confirm
            )
            return
            
        github = self._active_github_view()
        if github:
            issue_id = github.selected_issue_for_jump()
            if not issue_id:
                self._publish_action_result(False, "No linked issue to close")
                return
            
            issue = self.data_manager.get_issue_by_id(issue_id)
            if not issue:
                return

            def on_confirm_github(confirmed: bool) -> None:
                if confirmed:
                    async def do_close_github():
                        statuses = self.data_manager.config.linear_status_sequence
                        if "Done" in statuses:
                            ok, message = await self.data_manager.cycle_issue_status(issue_id, ("Done",))
                            self._publish_action_result(ok, message)
                            github.refresh_view()
                        else:
                            self._publish_action_result(False, "No 'Done' status configured")
                    self.run_worker(do_close_github(), exclusive=False)

            self.push_screen(
                ConfirmationScreen(f"Close issue {issue.id}: {issue.title}?", title="Close Issue"),
                on_confirm_github
            )

    async def action_drilldown_or_rerun(self) -> None:
        view = self._active_detail_view()
        if view is None:
            return
        if hasattr(view, "drilldown_or_rerun"):
            ok, message = await view.drilldown_or_rerun()
            # Note: _publish_action_result is already called within drilldown_or_rerun for GitHub
        elif hasattr(view, "action_rerun_ci"):
            ok, message = await view.action_rerun_ci()
            self._publish_action_result(ok, message, track=True)

    async def action_github_rerun_ci(self) -> None:
        github = self._active_github_view()
        if github:
            ok, message = await github.action_rerun_ci()
            self._publish_action_result(ok, message)
            github.refresh_view()
            return
            
        sprint = self._active_sprint_view()
        if sprint:
            self.action_sprint_open_github_drilldown()

    async def action_github_merge_pr(self) -> None:
        github = self._active_github_view()
        if github is None:
            return
        
        pr = github.selected_pull_request()
        if not pr:
            self._publish_action_result(False, "No pull request selected to merge")
            return

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                async def do_merge():
                    ok, message = await github.action_merge_pr()
                    self._publish_action_result(ok, message)
                    github.refresh_view()
                self.run_worker(do_merge(), exclusive=False)

        self.push_screen(
            ConfirmationScreen(f"Merge PR #{pr.number}: {pr.title}?", title="Merge PR"),
            on_confirm
        )

    async def action_github_approve_pr(self) -> None:
        github = self._active_github_view()
        if github is None:
            return
        ok, message = await github.action_review_pr(event="APPROVE")
        self._publish_action_result(ok, message)
        github.refresh_view()

    async def action_timeline_blocked_drilldown(self) -> None:
        timeline = self._active_timeline_view()
        if timeline is None:
            return
        ok, message = await timeline.open_project_blocked_drilldown()
        self._publish_action_result(ok, message)
        timeline.refresh_view()

    async def action_sprint_cycle_assignee(self) -> None:
        sprint = self._active_sprint_view()
        if sprint and not sprint.filter_active:
            ok, message = await sprint.cycle_selected_assignee()
            self._publish_action_result(ok, message)
            return
        github = self._active_github_view()
        if github is not None:
            await self.action_github_trigger_agent()
            return

    async def action_sprint_cycle_estimate(self) -> None:
        current = self.query_one(ContentSwitcher).current
        if current == "portfolio":
            view = self.query_one(ContentSwitcher).query_one("#portfolio", PortfolioView)
            ok, message = view.cycle_tier()
            self._publish_action_result(ok, message)
            return
        sprint = self._active_sprint_view()
        if not sprint or sprint.filter_active:
            return
        ok, message = await sprint.cycle_selected_points()
        self._publish_action_result(ok, message)

    def action_sprint_comment_issue(self) -> None:
        sprint = self._active_sprint_view()
        if sprint and not sprint.filter_active:
            ok, message = sprint.draft_comment_for_selected_issue()
            self._publish_action_result(ok, message)
            return
        github = self._active_github_view()
        if github is not None:
            self.action_github_open_check()
            return

    def action_sprint_open_linear(self) -> None:
        sprint = self._active_sprint_view()
        if sprint and not sprint.filter_active:
            ok, message = sprint.open_selected_issue_in_linear()
            self._publish_action_result(ok, message)
            return
        github = self._active_github_view()
        if github is not None:
            self.action_github_open_pr()
            return

    def action_sprint_open_editor(self) -> None:
        sprint = self._active_sprint_view()
        if not sprint or sprint.filter_active:
            return
        ok, message = sprint.open_selected_issue_in_editor()
        self._publish_action_result(ok, message)

    def action_sprint_open_terminal_editor(self) -> None:
        sprint = self._active_sprint_view()
        if not sprint or sprint.filter_active:
            return
        ok, message = sprint.open_selected_issue_in_terminal_editor()
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

    def action_triage_mine(self) -> None:
        self._apply_triage_filter("mine")

    def action_triage_blocked(self) -> None:
        self._apply_triage_filter("blocked")

    def action_triage_failing(self) -> None:
        self._apply_triage_filter("failing")

    def action_triage_stale(self) -> None:
        self._apply_triage_filter("stale")

    def action_triage_clear(self) -> None:
        view = self._active_triage_view()
        if view is None:
            self._publish_action_result(False, "Triage filters are available in Sprint or GitHub views")
            return
        if hasattr(view, "clear_triage_filters"):
            ok, message = view.clear_triage_filters()
            self._publish_action_result(ok, message)

    def action_triage_restore(self) -> None:
        view = self._active_triage_view()
        if view is None:
            self._publish_action_result(False, "Triage filters are available in Sprint or GitHub views")
            return
        if hasattr(view, "restore_triage_filters"):
            ok, message = view.restore_triage_filters()
            self._publish_action_result(ok, message)

    def _apply_triage_filter(self, name: str) -> None:
        view = self._active_triage_view()
        if view is None:
            self.action_switch_tab("sprint")
            view = self._active_triage_view()
        if view is None or not hasattr(view, "apply_triage_filter"):
            self._publish_action_result(False, "Triage filters are unavailable")
            return
        ok, message = view.apply_triage_filter(name)
        self._publish_action_result(ok, message)

    def _active_triage_view(self):
        github = self._active_github_view()
        if github is not None:
            return github
        sprint = self._active_sprint_view()
        if sprint is not None:
            return sprint
        return None

    def action_sprint_open_github_drilldown(self) -> None:
        sprint = self._active_sprint_view()
        if sprint and not sprint.filter_active:
            issue = sprint.current_issue()
            if issue is None:
                self._publish_action_result(False, "No issue selected")
                return
            self._push_navigation_context(
                route="github_issue_drilldown",
                payload={
                    "origin": self._capture_navigation_origin(),
                    "issue_id": issue.id,
                },
            )
            self.action_switch_tab("github")
            github = self._active_github_view()
            if github is None:
                self._pop_navigation_context("github_issue_drilldown")
                self._publish_action_result(False, "GitHub dashboard unavailable")
                return
            ok, message = github.focus_issue(issue.id)
            if not ok:
                self._pop_navigation_context("github_issue_drilldown")
            self._publish_action_result(ok, message)
            return
        timeline = self._active_timeline_view()
        if timeline is not None:
            self.action_timeline_blocked_drilldown()
            return
        self._publish_action_result(False, "Drilldown is available from Sprint issue or Timeline project views")

    def action_timeline_blocked_drilldown(self) -> None:
        timeline = self._active_timeline_view()
        if timeline is None:
            self._publish_action_result(False, "Timeline view is not active")
            return
        if getattr(timeline, "visual_mode", None) == "blocked":
            context = self._pop_navigation_context("timeline_blocked_drilldown")
            if context and self._restore_navigation_origin(context.get("origin")):
                self._publish_action_result(True, "Returned from blocked drilldown")
                return
        self._push_navigation_context(
            route="timeline_blocked_drilldown",
            payload={"origin": self._capture_navigation_origin()},
        )
        ok, message = timeline.open_project_blocked_drilldown()
        if not ok:
            self._pop_navigation_context("timeline_blocked_drilldown")
        self._publish_action_result(ok, message)

    def action_github_filter_state(self) -> None:
        current = self.query_one(ContentSwitcher).current
        if current == "portfolio":
            view = self.query_one(ContentSwitcher).query_one("#portfolio", PortfolioView)
            ok, message = view.cycle_tier_filter()
            self._publish_action_result(ok, message)
            return
        github = self._active_github_view()
        if github is None:
            return
        ok, message = github.cycle_state_filter()
        self._publish_action_result(ok, message)

    def action_github_filter_linked(self) -> None:
        github = self._active_github_view()
        if github is None:
            return
        ok, message = github.cycle_link_filter()
        self._publish_action_result(ok, message)

    def action_github_filter_failing(self) -> None:
        github = self._active_github_view()
        if github is None:
            return
        ok, message = github.toggle_failing_only()
        self._publish_action_result(ok, message)

    def action_github_clear_filters(self) -> None:
        github = self._active_github_view()
        if github is None:
            return
        ok, message = github.clear_filters()
        self._publish_action_result(ok, message)

    def action_github_clear_drilldown(self) -> None:
        github = self._active_github_view()
        if github is None:
            if self._restore_context_route("github_jump_issue"):
                self._publish_action_result(True, "Returned to GitHub context")
            return
        ok, message = github.clear_issue_drilldown()
        if ok:
            self._restore_context_route("github_issue_drilldown")
        self._publish_action_result(ok, message)

    def action_github_open_pr(self) -> None:
        github = self._active_github_view()
        if github is None:
            return
        ok, message = github.open_selected_pull_request()
        self._publish_action_result(ok, message)

    def action_github_open_check(self) -> None:
        github = self._active_github_view()
        if github is None:
            return
        ok, message = github.open_selected_check()
        self._publish_action_result(ok, message)

    def action_github_copy_branch(self) -> None:
        github = self._active_github_view()
        if github is None:
            return
        ok, message = github.copy_selected_branch()
        self._publish_action_result(ok, message)

    async def action_github_trigger_agent(self) -> None:
        github = self._active_github_view()
        if github is None:
            return
        pull_request = github.selected_pull_request()
        if pull_request is None:
            self._publish_action_result(False, "No pull request selected")
            return

        issue = self.data_manager.get_issue_by_id(pull_request.issue_id) if pull_request.issue_id else None
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        run = AgentRun(
            id=f"ghrun-{uuid4().hex[:12]}",
            runtime="github-manual",
            status=AgentRunStatus.QUEUED,
            started_at=timestamp,
            issue_id=pull_request.issue_id,
            project_id=issue.project_id if issue else None,
            branch_name=pull_request.head_branch,
            pr_id=pull_request.id,
            prompt_text=f"Review and advance PR #{pull_request.number}: {pull_request.title}",
            artifacts={
                "source": "github_dashboard",
                "repository_id": pull_request.repository_id,
                "pull_request_number": pull_request.number,
                "pull_request_url": pull_request.url,
                "issue_id": pull_request.issue_id,
                "head_branch": pull_request.head_branch,
                "base_branch": pull_request.base_branch,
            },
        )
        try:
            await self.data_manager.record_agent_run(run)
        except Exception as error:
            self._publish_action_result(False, f"Failed to queue agent run: {error}")
            return
        dispatched, dispatch_message = await self.data_manager.dispatch_agent_run(run)
        self._queue_agent_run_refresh()
        if dispatched:
            self._publish_action_result(
                True,
                f"Queued and dispatched agent run {run.id} for PR #{pull_request.number} ({dispatch_message})",
            )
            return
        self._publish_action_result(
            True,
            f"Queued agent run {run.id} for PR #{pull_request.number} ({dispatch_message})",
        )

    def action_github_jump_issue(self) -> None:
        github = self._active_github_view()
        if github is None:
            return
        issue_id = github.selected_issue_for_jump()
        if not issue_id:
            self._publish_action_result(False, "Selected PR is not linked to a Linear issue")
            return
        self._push_navigation_context(
            route="github_jump_issue",
            payload={
                "origin": self._capture_navigation_origin(),
                "issue_id": issue_id,
            },
        )
        self.action_switch_tab("sprint")
        sprint = self._active_sprint_view()
        if sprint is None:
            self._pop_navigation_context("github_jump_issue")
            self._publish_action_result(False, "Sprint board unavailable")
            return
        ok, message = sprint.focus_issue(issue_id)
        if ok:
            self._publish_action_result(True, f"Jumped to Linear issue {issue_id}")
            return
        self._pop_navigation_context("github_jump_issue")
        self._publish_action_result(False, message)

    def action_timeline_blocked_assignee_filter(self) -> None:
        timeline = self._active_timeline_view()
        if timeline is None:
            self._publish_action_result(False, "Timeline view is not active")
            return
        ok, message = timeline.cycle_blocked_assignee_filter()
        self._publish_action_result(ok, message)

    def action_timeline_blocked_owner_next(self) -> None:
        timeline = self._active_timeline_view()
        if timeline is None:
            self._publish_action_result(False, "Timeline view is not active")
            return
        ok, message = timeline.jump_blocked_owner_cluster(1)
        self._publish_action_result(ok, message)

    def action_timeline_blocked_owner_prev(self) -> None:
        timeline = self._active_timeline_view()
        if timeline is None:
            self._publish_action_result(False, "Timeline view is not active")
            return
        ok, message = timeline.jump_blocked_owner_cluster(-1)
        self._publish_action_result(ok, message)

    def action_timeline_blocked_project_next(self) -> None:
        timeline = self._active_timeline_view()
        if timeline is None:
            self._publish_action_result(False, "Timeline view is not active")
            return
        ok, message = timeline.jump_blocked_project_cluster(1)
        self._publish_action_result(ok, message)

    def action_timeline_blocked_project_prev(self) -> None:
        timeline = self._active_timeline_view()
        if timeline is None:
            self._publish_action_result(False, "Timeline view is not active")
            return
        ok, message = timeline.jump_blocked_project_cluster(-1)
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
            if hasattr(dash, "apply_layout_preset"):
                dash.apply_layout_preset(
                    ("sync-freshness", "key-metrics", "charts", "project-detail"),
                    widths={"sync-freshness": 34, "key-metrics": 62, "charts": 46, "project-detail": 36},
                )
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
            if hasattr(dash, "apply_layout_preset"):
                dash.apply_layout_preset(
                    ("project-explorer", "key-metrics", "charts", "project-detail"),
                    widths={"project-explorer": 44, "key-metrics": 60, "charts": 44, "project-detail": 36},
                )
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
            if hasattr(dash, "apply_layout_preset"):
                dash.apply_layout_preset(
                    ("project-explorer", "charts", "project-detail"),
                    widths={"project-explorer": 56, "charts": 56, "project-detail": 36},
                )
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
        if event.key == "shift+space" and not (sprint and sprint.filter_active):
            self.action_open_detail()
            event.stop()
            return
        if event.key == "space" and not (sprint and sprint.filter_active):
            self.page_focus_locked = not self.page_focus_locked
            self._apply_page_focus_mode()
            self.update_app_status("Focus: page" if self.page_focus_locked else "Focus: tabs")
            event.stop()
            return

        if self.page_focus_locked and not (sprint and sprint.filter_active):
            if self._handle_page_focus_arrow(event.key):
                event.stop()
                return

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

    def _handle_page_focus_arrow(self, key: str) -> bool:
        if key not in {"left", "right", "up", "down"}:
            return False

        self._normalize_page_focus_section()

        sprint = self._active_sprint_view()
        if sprint and not sprint.filter_active and self.page_focus_section == "main":
            if key == "left":
                sprint.move_cursor(col_delta=-1)
                return True
            if key == "right":
                sprint.move_cursor(col_delta=1)
                return True
            if key == "up":
                sprint.move_cursor(row_delta=-1)
                return True
            if key == "down":
                sprint.move_cursor(row_delta=1)
                return True

        if key == "right":
            return self._set_page_focus_section("detail")
        if key == "left":
            return self._set_page_focus_section("main")
        if self.page_focus_section != "main":
            return True

        delta = -1 if key == "up" else 1
        view = self._active_selection_view()
        if view and hasattr(view, "move_selection"):
            view.move_selection(delta)
            return True
        return False

    def _apply_page_focus_mode(self) -> None:
        try:
            tabs = self.query_one(Tabs)
        except Exception:
            return
        tabs.can_focus = not self.page_focus_locked
        if self.page_focus_locked:
            try:
                if tabs.has_focus:
                    self.set_focus(None)
            except Exception:
                pass
            return
        try:
            tabs.focus()
        except Exception:
            pass

    def _available_page_focus_sections(self) -> tuple[str, ...]:
        # Keep this safe for unit tests that instantiate the app without mounting.
        if self.detail_sidebar_visible:
            return ("main", "detail")

        try:
            if isinstance(self.screen, IssueFlowScreen):
                return ("main", "detail")
        except Exception:
            pass
        return ("main",)

    def _normalize_page_focus_section(self) -> None:
        sections = self._available_page_focus_sections()
        if self.page_focus_section not in sections:
            self.page_focus_section = "main"

    def _set_page_focus_section(self, section: str) -> bool:
        self._normalize_page_focus_section()
        sections = self._available_page_focus_sections()
        target = section if section in sections else "main"
        if self.page_focus_section == target:
            return False
        self.page_focus_section = target
        self.update_app_status(f"Section: {target}")
        return True

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
        for view_id in ("dash", "github", "sprint", "timeline", "workload", "ideation"):
            try:
                view = self.query_one(ContentSwitcher).query_one(f"#{view_id}")
            except Exception:
                continue
            if hasattr(view, "set_project_scope"):
                view.set_project_scope(project_id)
        self.update_app_status()

    def _persist_view_filter_state(self, view_id: str) -> None:
        try:
            view = self.query_one(ContentSwitcher).query_one(f"#{view_id}")
        except Exception:
            return
        if not hasattr(view, "capture_filter_state"):
            return
        try:
            state = view.capture_filter_state()
        except Exception:
            return
        if isinstance(state, dict):
            self._view_filter_state_by_view[view_id] = state

    def _restore_view_filter_state(self, view_id: str) -> None:
        state = self._view_filter_state_by_view.get(view_id)
        if not state:
            return
        try:
            view = self.query_one(ContentSwitcher).query_one(f"#{view_id}")
        except Exception:
            return
        if not hasattr(view, "restore_filter_state"):
            return
        try:
            view.restore_filter_state(state)
        except Exception:
            return

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
        if current == "ideation":
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

    def _active_timeline_view(self) -> TimelineView | None:
        if self.query_one(ContentSwitcher).current != "timeline":
            return None
        try:
            return self.query_one(ContentSwitcher).query_one("#timeline", TimelineView)
        except Exception:
            return None

    def _active_github_view(self) -> GitHubDashboardView | None:
        if self.query_one(ContentSwitcher).current != "github":
            return None
        try:
            return self.query_one(ContentSwitcher).query_one("#github", GitHubDashboardView)
        except Exception:
            return None

    def _active_ideation_view(self) -> IdeationGalleryView | None:
        if self.query_one(ContentSwitcher).current != "ideation":
            return None
        try:
            return self.query_one(ContentSwitcher).query_one("#ideation", IdeationGalleryView)
        except Exception:
            return None

    def _active_customizable_view(self):
        current = self.query_one(ContentSwitcher).current
        if current is None:
            return None
        try:
            view = self.query_one(ContentSwitcher).query_one(f"#{current}")
        except Exception:
            return None
        if hasattr(view, "set_layout_edit_mode"):
            return view
        return None

    def _active_detail_view(self):
        current = self.query_one(ContentSwitcher).current
        if current == "dash":
            return self.query_one(ContentSwitcher).query_one("#dash", DashboardView)
        if current == "github":
            return self.query_one(ContentSwitcher).query_one("#github", GitHubDashboardView)
        if current == "sprint":
            return self.query_one(ContentSwitcher).query_one("#sprint", SprintBoardView)
        if current == "blocked":
            return self.query_one(ContentSwitcher).query_one("#blocked", BlockedQueueView)
        if current == "timeline":
            return self.query_one(ContentSwitcher).query_one("#timeline", TimelineView)
        if current == "workload":
            return self.query_one(ContentSwitcher).query_one("#workload", WorkloadView)
        if current == "ideation":
            return self.query_one(ContentSwitcher).query_one("#ideation", IdeationGalleryView)
        if current == "portfolio":
            return self.query_one(ContentSwitcher).query_one("#portfolio", PortfolioView)
        return None

    def _active_visual_view(self):
        current = self.query_one(ContentSwitcher).current
        if current == "dash":
            return self.query_one(ContentSwitcher).query_one("#dash", DashboardView)
        if current == "github":
            return self.query_one(ContentSwitcher).query_one("#github", GitHubDashboardView)
        if current == "blocked":
            return self.query_one(ContentSwitcher).query_one("#blocked", BlockedQueueView)
        if current == "workload":
            return self.query_one(ContentSwitcher).query_one("#workload", WorkloadView)
        if current == "timeline":
            return self.query_one(ContentSwitcher).query_one("#timeline", TimelineView)
        if current == "ideation":
            return self.query_one(ContentSwitcher).query_one("#ideation", IdeationGalleryView)
        if current == "portfolio":
            return self.query_one(ContentSwitcher).query_one("#portfolio", PortfolioView)
        return None

    def _active_selection_view(self):
        current = self.query_one(ContentSwitcher).current
        if current == "dash":
            return self.query_one(ContentSwitcher).query_one("#dash", DashboardView)
        if current == "github":
            return self.query_one(ContentSwitcher).query_one("#github", GitHubDashboardView)
        if current == "blocked":
            return self.query_one(ContentSwitcher).query_one("#blocked", BlockedQueueView)
        if current == "timeline":
            return self.query_one(ContentSwitcher).query_one("#timeline", TimelineView)
        if current == "workload":
            return self.query_one(ContentSwitcher).query_one("#workload", WorkloadView)
        if current == "ideation":
            return self.query_one(ContentSwitcher).query_one("#ideation", IdeationGalleryView)
        if current == "portfolio":
            return self.query_one(ContentSwitcher).query_one("#portfolio", PortfolioView)
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
        legacy = ", ".join(f"/{name}" for name in self._deprecated_command_aliases())
        return (
            "Commands: "
            + " ".join(f"/{name}" for name in commands)
            + (f" | Deprecated aliases: {legacy}" if legacy else "")
        )

    def _deprecated_command_aliases(self) -> tuple[str, ...]:
        # Compatibility aliases kept for now; prefer canonical commands in palette.
        return ("gh", "preset eng manager", "preset engineer", ":q")

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
                "back": 0,
                "filter": 0,
                "mine": 1,
                "blocked": 2,
                "failing": 3,
                "stale": 4,
                "triage clear": 5,
                "triage restore": 6,
                "github issue": 7,
                "issue flow": 8,
                "status": 9,
                "close issue": 10,
                "assignee": 11,
                "estimate": 12,
                "comment": 13,
                "open linear": 14,
                "open editor": 15,
                "terminal note": 16,
                "detail": 17,
                "close detail": 18,
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
        if current == "github":
            return {
                "github": 0,
                "back": 1,
                "sync github": 1,
                "mine": 2,
                "blocked": 3,
                "failing": 4,
                "stale": 5,
                "triage clear": 6,
                "triage restore": 7,
                "github state": 8,
                "github linked": 9,
                "github failing": 10,
                "github clear filters": 11,
                "issue flow": 12,
                "github open pr": 13,
                "github open check": 14,
                "github copy branch": 15,
                "github run agent": 16,
                "github jump issue": 17,
                "visual": 18,
                "density": 19,
            }
        if current == "timeline":
            return {
                "visual": 0,
                "back": 1,
                "density": 1,
                "blocked assignee": 2,
                "blocked owner next": 3,
                "blocked owner prev": 4,
                "blocked project next": 5,
                "blocked project prev": 6,
                "blocked drilldown": 7,
                "preset manager": 8,
                "project focus": 9,
            }
        if current == "workload":
            return {
                "visual": 0,
                "back": 1,
                "density": 1,
                "simulate up": 2,
                "simulate down": 3,
                "preset manager": 4,
            }
        if current == "ideation":
            return {
                "ideation": 0,
                "gallery": 1,
                "back": 2,
                "visual": 2,
                "density": 3,
                "sidebar": 4,
                "line pan left": 5,
                "line pan right": 6,
                "line series prev": 7,
                "line series next": 8,
                "line style": 9,
                "line zoom in": 10,
                "line zoom out": 11,
                "detail": 12,
                "close detail": 13,
            }
        return {}

    def _command_palette_entries(self) -> list[tuple[str, str]]:
        return [
            ("dashboard", "Switch to Linear dashboard tab"),
            ("linear dashboard", "Switch to Linear dashboard tab"),
            ("github", "Switch to GitHub dashboard tab"),
            ("sprint", "Switch to sprint board tab"),
            ("timeline", "Switch to timeline tab"),
            ("workload", "Switch to workload tab"),
            ("ideation", "Switch to ideation gallery tab"),
            ("sync", "Run Linear sync now"),
            ("sync github", "Run GitHub sync now"),
            ("sync freshness", "Toggle sync freshness status display"),
            ("github state", "Cycle GitHub state filter"),
            ("github linked", "Cycle GitHub linked/unlinked filter"),
            ("github failing", "Toggle GitHub failing-check filter"),
            ("github clear filters", "Reset all GitHub filters"),
            ("github open pr", "Open selected pull request URL"),
            ("github open check", "Open selected check URL"),
            ("github copy branch", "Copy selected pull request head branch"),
            ("github run agent", "Queue an agent run for selected pull request"),
            ("github jump issue", "Jump from selected pull request to linked Linear issue"),
            ("github issue drilldown", "From Sprint issue, open GitHub pull request drilldown"),
            ("issue flow", "Open issue <-> PR timeline screen"),
            ("back", "Return from current drilldown/detail context"),
            ("history", "Open sync history screen"),
            ("visual", "Toggle chart/visual mode"),
            ("density", "Toggle chart density"),
            ("hotkeys", "Toggle bottom hotkey bar"),
            ("sidebar", "Toggle detail sidebar visibility"),
            ("freshness", "Toggle sync freshness status display"),
            ("line pan left", "Pan line chart window left (Ideation)"),
            ("line pan right", "Pan line chart window right (Ideation)"),
            ("line zoom in", "Zoom line chart in (Ideation)"),
            ("line zoom out", "Zoom line chart out (Ideation)"),
            ("line series prev", "Focus previous line series (Ideation)"),
            ("line series next", "Focus next line series (Ideation)"),
            ("line style", "Toggle classic/hires line renderer (Ideation)"),
            ("detail", "Open selected detail panel"),
            ("close detail", "Close detail panel"),
            ("project focus", "Focus a single project scope"),
            ("project next", "Focus next project"),
            ("project prev", "Focus previous project"),
            ("all projects", "Clear project scope"),
            ("blocked assignee", "Cycle blocked queue assignee filter (timeline)"),
            ("blocked owner next", "Jump to next blocked owner cluster (timeline)"),
            ("blocked owner prev", "Jump to previous blocked owner cluster (timeline)"),
            ("blocked project next", "Jump to next blocked project cluster (timeline)"),
            ("blocked project prev", "Jump to previous blocked project cluster (timeline)"),
            ("blocked drilldown", "Drill into blocked issues for selected timeline project"),
            ("mine", "Toggle triage mine filter (Sprint/GitHub)"),
            ("blocked", "Toggle triage blocked filter (Sprint/GitHub)"),
            ("failing", "Toggle triage failing filter (Sprint/GitHub)"),
            ("stale", "Toggle triage stale filter (Sprint/GitHub)"),
            ("triage clear", "Clear triage filters in active view"),
            ("triage restore", "Restore last cleared triage filters"),
            ("filter", "Open filter/search for active view"),
            ("jump mine", "Jump to your assigned sprint issue"),
            ("github issue", "From sprint, open linked GitHub pull requests"),
            ("status", "Cycle selected issue status"),
            ("close issue", "Move selected issue to a done status"),
            ("assignee", "Cycle selected issue assignee"),
            ("estimate", "Cycle selected issue estimate"),
            ("comment", "Create/open a comment draft for selected issue"),
            ("open linear", "Open selected issue in the browser"),
            ("open editor", "Open project workspace in code editor"),
            ("terminal note", "Open selected issue note in terminal editor"),
            ("simulate up", "Increase workload simulation shift"),
            ("simulate down", "Decrease workload simulation shift"),
            ("preset exec", "Apply executive layout preset"),
            ("preset manager", "Apply manager layout preset"),
            ("preset ic", "Apply IC layout preset"),
            ("quit", "Quit ProjectDash"),
            (":q", "Quit ProjectDash"),
        ]

    def _command_aliases(self) -> dict[str, tuple[str, ...]]:
        return {
            "dashboard": ("dash", "linear dashboard"),
            "linear dashboard": ("dashboard",),
            "github": ("github dashboard",),
            "ideation": ("gallery", "ideas"),
            "history": ("sync history",),
            "hotkeys": ("hotkey bar", "toggle hotkeys"),
            "sidebar": ("toggle sidebar",),
            "freshness": ("sync freshness", "toggle freshness"),
            "line pan left": ("line left", "pan left"),
            "line pan right": ("line right", "pan right"),
            "line zoom in": ("zoom in",),
            "line zoom out": ("zoom out",),
            "line series prev": ("series prev",),
            "line series next": ("series next",),
            "line style": ("style", "line renderer"),
            "sync github": ("github sync",),
            "github state": ("github filter state",),
            "github linked": ("github filter linked",),
            "github failing": ("github filter failing",),
            "github clear filters": ("github reset filters",),
            "github open pr": ("github open", "open pr"),
            "github open check": ("open check", "check url"),
            "github copy branch": ("github branch", "copy branch"),
            "github run agent": ("github agent", "run agent"),
            "github jump issue": ("github issue jump", "jump issue"),
            "github issue drilldown": ("issue drilldown", "github from issue"),
            "issue flow": ("flow", "review cockpit", "issue timeline"),
            "back": ("return", "go back", "github back", "clear drilldown"),
            "project focus": ("project", "focus project"),
            "project next": ("next project",),
            "project prev": ("prev project", "previous project"),
            "all projects": ("project all",),
            "blocked assignee": ("blocked owner filter", "blocked mine"),
            "blocked owner next": ("owner cluster next",),
            "blocked owner prev": ("owner cluster prev",),
            "blocked project next": ("project cluster next",),
            "blocked project prev": ("project cluster prev",),
            "blocked drilldown": ("blocked project drilldown", "project blockers"),
            "filter": ("sprint filter",),
            "mine": ("triage mine",),
            "blocked": ("triage blocked",),
            "failing": ("triage failing",),
            "stale": ("triage stale",),
            "triage clear": ("clear triage", "triage reset"),
            "triage restore": ("restore triage", "triage undo"),
            "jump mine": ("jump to mine",),
            "close issue": ("close",),
            "comment": ("comment draft",),
            "open linear": (),
            "open editor": (),
            "terminal note": ("shell note",),
            "preset manager": ("preset eng manager",),
            "preset ic": ("preset engineer",),
            "quit": ("exit",),
            ":q": ("quit",),
        }

    def _command_catalog(self) -> dict[str, tuple[str | None, object, tuple, str]]:
        catalog = {
            "dashboard": ("dash", self.action_switch_tab, ("dash",), "Switch to Linear dashboard tab"),
            "linear dashboard": ("dash", self.action_switch_tab, ("dash",), "Switch to Linear dashboard tab"),
            "dash": ("dash", self.action_switch_tab, ("dash",), "Switch to Linear dashboard tab"),
            "github": ("github", self.action_switch_tab, ("github",), "Switch to GitHub dashboard tab"),
            "gh": ("github", self.action_switch_tab, ("github",), "Switch to GitHub dashboard tab"),
            "sprint": ("sprint", self.action_switch_tab, ("sprint",), "Switch to sprint board tab"),
            "timeline": ("timeline", self.action_switch_tab, ("timeline",), "Switch to timeline tab"),
            "workload": ("workload", self.action_switch_tab, ("workload",), "Switch to workload tab"),
            "ideation": ("ideation", self.action_switch_tab, ("ideation",), "Switch to ideation gallery tab"),
            "gallery": ("ideation", self.action_switch_tab, ("ideation",), "Switch to ideation gallery tab"),
            "ideas": ("ideation", self.action_switch_tab, ("ideation",), "Switch to ideation gallery tab"),
            "sync": (None, self.action_sync_data, (), "Run Linear sync now"),
            "hotkeys": (None, self.action_toggle_hotkey_bar, (), "Toggle bottom hotkey bar"),
            "hotkey bar": (None, self.action_toggle_hotkey_bar, (), "Toggle bottom hotkey bar"),
            "toggle hotkeys": (None, self.action_toggle_hotkey_bar, (), "Toggle bottom hotkey bar"),
            "sidebar": (None, self.action_toggle_sidebar, (), "Toggle detail sidebar visibility"),
            "toggle sidebar": (None, self.action_toggle_sidebar, (), "Toggle detail sidebar visibility"),
            "freshness": (None, self.action_toggle_sync_freshness, (), "Toggle sync freshness status display"),
            "sync freshness": (None, self.action_toggle_sync_freshness, (), "Toggle sync freshness status display"),
            "line pan left": ("ideation", self.action_line_pan_left, (), "Pan line chart window left"),
            "line left": ("ideation", self.action_line_pan_left, (), "Pan line chart window left"),
            "pan left": ("ideation", self.action_line_pan_left, (), "Pan line chart window left"),
            "line pan right": ("ideation", self.action_line_pan_right, (), "Pan line chart window right"),
            "line right": ("ideation", self.action_line_pan_right, (), "Pan line chart window right"),
            "pan right": ("ideation", self.action_line_pan_right, (), "Pan line chart window right"),
            "line zoom in": ("ideation", self.action_simulation_increase, (), "Zoom line chart in"),
            "zoom in": ("ideation", self.action_simulation_increase, (), "Zoom line chart in"),
            "line zoom out": ("ideation", self.action_simulation_decrease, (), "Zoom line chart out"),
            "zoom out": ("ideation", self.action_simulation_decrease, (), "Zoom line chart out"),
            "line series prev": ("ideation", self.action_line_series_prev, (), "Focus previous line series"),
            "series prev": ("ideation", self.action_line_series_prev, (), "Focus previous line series"),
            "line series next": ("ideation", self.action_line_series_next, (), "Focus next line series"),
            "series next": ("ideation", self.action_line_series_next, (), "Focus next line series"),
            "line style": ("ideation", self.action_line_style_toggle, (), "Toggle line renderer style"),
            "style": ("ideation", self.action_line_style_toggle, (), "Toggle line renderer style"),
            "line renderer": ("ideation", self.action_line_style_toggle, (), "Toggle line renderer style"),
            "sync github": (None, self.action_sync_github, (), "Run GitHub sync now"),
            "github sync": (None, self.action_sync_github, (), "Run GitHub sync now"),
            "github state": ("github", self.action_github_filter_state, (), "Cycle GitHub state filter"),
            "github filter state": ("github", self.action_github_filter_state, (), "Cycle GitHub state filter"),
            "github linked": ("github", self.action_github_filter_linked, (), "Cycle GitHub link filter"),
            "github filter linked": ("github", self.action_github_filter_linked, (), "Cycle GitHub link filter"),
            "github failing": ("github", self.action_github_filter_failing, (), "Toggle GitHub failing filter"),
            "github filter failing": ("github", self.action_github_filter_failing, (), "Toggle GitHub failing filter"),
            "github clear filters": ("github", self.action_github_clear_filters, (), "Clear GitHub filters"),
            "github reset filters": ("github", self.action_github_clear_filters, (), "Clear GitHub filters"),
            "github clear drilldown": ("github", self.action_github_clear_drilldown, (), "Return from issue drilldown"),
            "github open pr": ("github", self.action_github_open_pr, (), "Open selected pull request"),
            "github open": ("github", self.action_github_open_pr, (), "Open selected pull request"),
            "open pr": ("github", self.action_github_open_pr, (), "Open selected pull request"),
            "github open check": ("github", self.action_github_open_check, (), "Open selected check"),
            "open check": ("github", self.action_github_open_check, (), "Open selected check"),
            "check url": ("github", self.action_github_open_check, (), "Open selected check"),
            "github copy branch": ("github", self.action_github_copy_branch, (), "Copy selected pull request branch"),
            "github branch": ("github", self.action_github_copy_branch, (), "Copy selected pull request branch"),
            "copy branch": ("github", self.action_github_copy_branch, (), "Copy selected pull request branch"),
            "github run agent": ("github", self.action_github_trigger_agent, (), "Queue agent run for selected pull request"),
            "github agent": ("github", self.action_github_trigger_agent, (), "Queue agent run for selected pull request"),
            "run agent": ("github", self.action_github_trigger_agent, (), "Queue agent run for selected pull request"),
            "github jump issue": ("github", self.action_github_jump_issue, (), "Jump to linked Linear issue"),
            "jump issue": ("github", self.action_github_jump_issue, (), "Jump to linked Linear issue"),
            "github issue drilldown": (
                "sprint",
                self.action_sprint_open_github_drilldown,
                (),
                "Open GitHub drilldown for selected issue",
            ),
            "github from issue": (
                "sprint",
                self.action_sprint_open_github_drilldown,
                (),
                "Open GitHub drilldown for selected issue",
            ),
            "issue drilldown": (
                "sprint",
                self.action_sprint_open_github_drilldown,
                (),
                "Open GitHub drilldown for selected issue",
            ),
            "sync history": (None, self.action_open_sync_history, (), "Open sync history screen"),
            "history": (None, self.action_open_sync_history, (), "Open sync history screen"),
            "visual": (None, self.action_toggle_visual_mode, (), "Toggle chart/visual mode"),
            "density": (None, self.action_toggle_graph_density, (), "Toggle chart density"),
            "freshness": (None, self.action_toggle_sync_freshness, (), "Toggle sync freshness status display"),
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
            "blocked assignee": (
                "timeline",
                self.action_timeline_blocked_assignee_filter,
                (),
                "Cycle blocked queue assignee filter",
            ),
            "blocked owner filter": (
                "timeline",
                self.action_timeline_blocked_assignee_filter,
                (),
                "Cycle blocked queue assignee filter",
            ),
            "blocked mine": (
                "timeline",
                self.action_timeline_blocked_assignee_filter,
                (),
                "Cycle blocked queue assignee filter",
            ),
            "blocked owner next": (
                "timeline",
                self.action_timeline_blocked_owner_next,
                (),
                "Jump to next blocked owner cluster",
            ),
            "owner cluster next": (
                "timeline",
                self.action_timeline_blocked_owner_next,
                (),
                "Jump to next blocked owner cluster",
            ),
            "blocked owner prev": (
                "timeline",
                self.action_timeline_blocked_owner_prev,
                (),
                "Jump to previous blocked owner cluster",
            ),
            "owner cluster prev": (
                "timeline",
                self.action_timeline_blocked_owner_prev,
                (),
                "Jump to previous blocked owner cluster",
            ),
            "blocked project next": (
                "timeline",
                self.action_timeline_blocked_project_next,
                (),
                "Jump to next blocked project cluster",
            ),
            "project cluster next": (
                "timeline",
                self.action_timeline_blocked_project_next,
                (),
                "Jump to next blocked project cluster",
            ),
            "blocked project prev": (
                "timeline",
                self.action_timeline_blocked_project_prev,
                (),
                "Jump to previous blocked project cluster",
            ),
            "project cluster prev": (
                "timeline",
                self.action_timeline_blocked_project_prev,
                (),
                "Jump to previous blocked project cluster",
            ),
            "blocked drilldown": (
                "timeline",
                self.action_timeline_blocked_drilldown,
                (),
                "Drill into blocked issues for selected project",
            ),
            "blocked project drilldown": (
                "timeline",
                self.action_timeline_blocked_drilldown,
                (),
                "Drill into blocked issues for selected project",
            ),
            "project blockers": (
                "timeline",
                self.action_timeline_blocked_drilldown,
                (),
                "Drill into blocked issues for selected project",
            ),
            "mine": (None, self.action_triage_mine, (), "Toggle triage mine filter"),
            "triage mine": (None, self.action_triage_mine, (), "Toggle triage mine filter"),
            "blocked": (None, self.action_triage_blocked, (), "Toggle triage blocked filter"),
            "triage blocked": (None, self.action_triage_blocked, (), "Toggle triage blocked filter"),
            "failing": (None, self.action_triage_failing, (), "Toggle triage failing filter"),
            "triage failing": (None, self.action_triage_failing, (), "Toggle triage failing filter"),
            "stale": (None, self.action_triage_stale, (), "Toggle triage stale filter"),
            "triage stale": (None, self.action_triage_stale, (), "Toggle triage stale filter"),
            "triage clear": (None, self.action_triage_clear, (), "Clear triage filters"),
            "clear triage": (None, self.action_triage_clear, (), "Clear triage filters"),
            "triage reset": (None, self.action_triage_clear, (), "Clear triage filters"),
            "triage restore": (None, self.action_triage_restore, (), "Restore triage filters"),
            "restore triage": (None, self.action_triage_restore, (), "Restore triage filters"),
            "triage undo": (None, self.action_triage_restore, (), "Restore triage filters"),
            "sprint filter": ("sprint", self.action_sprint_filter, (), "Start sprint filter input"),
            "filter": (None, self.action_open_filter, (), "Open filter/search for active view"),
            "jump mine": ("sprint", self.action_sprint_jump_to_mine, (), "Jump to your assigned issue"),
            "github issue": ("sprint", self.action_sprint_open_github_drilldown, (), "Open linked pull requests"),
            "issue flow": (None, self.action_open_issue_flow, (), "Open issue <-> PR timeline"),
            "back": (None, self.action_back_context, (), "Return from current drilldown/detail context"),
            "return": (None, self.action_back_context, (), "Return from current drilldown/detail context"),
            "go back": (None, self.action_back_context, (), "Return from current drilldown/detail context"),
            "flow": (None, self.action_open_issue_flow, (), "Open issue <-> PR timeline"),
            "review cockpit": (None, self.action_open_issue_flow, (), "Open issue <-> PR timeline"),
            "issue timeline": (None, self.action_open_issue_flow, (), "Open issue <-> PR timeline"),
            "status": ("sprint", self.action_sprint_move_status, (), "Cycle selected issue status"),
            "close issue": ("sprint", self.action_sprint_close_issue, (), "Move selected issue to done"),
            "close": ("sprint", self.action_sprint_close_issue, (), "Move selected issue to done"),
            "assignee": ("sprint", self.action_sprint_cycle_assignee, (), "Cycle selected issue assignee"),
            "estimate": ("sprint", self.action_sprint_cycle_estimate, (), "Cycle selected issue estimate"),
            "comment": ("sprint", self.action_sprint_comment_issue, (), "Create/open issue comment draft"),
            "open linear": ("sprint", self.action_sprint_open_linear, (), "Open selected issue in browser"),
            "open editor": ("sprint", self.action_sprint_open_editor, (), "Open workspace in code editor"),
            "terminal note": (
                "sprint",
                self.action_sprint_open_terminal_editor,
                (),
                "Open issue note in terminal editor",
            ),
            "simulate up": ("workload", self.action_simulation_increase, (), "Increase workload simulation"),
            "simulate down": ("workload", self.action_simulation_decrease, (), "Decrease workload simulation"),
            "preset exec": (None, self.action_apply_preset, ("exec",), "Apply executive layout preset"),
            "preset manager": (None, self.action_apply_preset, ("manager",), "Apply manager layout preset"),
            "preset eng manager": (None, self.action_apply_preset, ("manager",), "Apply manager layout preset"),
            "preset ic": (None, self.action_apply_preset, ("ic",), "Apply IC layout preset"),
            "preset engineer": (None, self.action_apply_preset, ("ic",), "Apply IC layout preset"),
            "quit": (None, self.action_quit, (), "Quit ProjectDash"),
            ":q": (None, self.action_quit, (), "Quit ProjectDash"),
        }
        catalog["exit"] = catalog["quit"]
        return catalog

    def _context_bar_text(self, status_text: str) -> str:
        summary = self._context_summary_for_active_view()
        mode = summary.get("mode", "-")
        density = summary.get("density", "-")
        filter_value = summary.get("filter", "none")
        selected = summary.get("selected", "none")
        tab_label = self._active_tab_label()
        if tab_label in {"Linear", "Timeline"} and selected not in {"none", ""}:
            selected = self._project_label(selected) if selected != "none" else selected
        ui_error = f" | UI error: {self.last_ui_error}" if self.last_ui_error else ""
        self._normalize_page_focus_section()
        return (
            f"{status_text} | Scope: {self._scope_label()} | Mode: {mode} | Density: {density} | "
            f"Filter: {filter_value} | Selected: {selected} | Preset: {self.active_preset} | "
            f"Focus: {'page' if self.page_focus_locked else 'tabs'} | Section: {self.page_focus_section} | "
            f"Config: {self.config.config_source}"
            f"{self._tab_focus_context_hint()}{ui_error}"
        )

    def _tab_focus_context_hint(self) -> str:
        if self.page_focus_locked:
            return ""
        return " | Tabs: d Linear G GitHub s Sprint t Timeline w Workload n Ideation ←/→ switch"

    def _active_tab_label(self) -> str:
        if isinstance(self.screen, IssueFlowScreen):
            return "Issue Flow"
        if isinstance(self.screen, SprintIssueScreen):
            return "Sprint Item"
        current = self.query_one(ContentSwitcher).current
        mapping = {
            "dash": "Linear",
            "github": "GitHub",
            "blocked": "Blockers",
            "sprint": "Sprint",
            "timeline": "Timeline",
            "workload": "Workload",
            "ideation": "Ideation",
        }
        return mapping.get(current, current)

    def _context_summary_for_active_view(self) -> dict[str, str]:
        if isinstance(self.screen, IssueFlowScreen):
            issue_id = getattr(self.screen, "issue_id", "none")
            return {"mode": "timeline", "density": "-", "filter": "linked", "selected": str(issue_id)}
        if isinstance(self.screen, SprintIssueScreen):
            issue_id = getattr(self.screen, "issue_id", "none")
            return {"mode": "item", "density": "-", "filter": "sprint", "selected": str(issue_id)}
        view = self._active_detail_view()
        if view is None:
            return {"mode": "-", "density": "-", "filter": "none", "selected": "none"}
        if hasattr(view, "context_summary"):
            summary = view.context_summary()
            if isinstance(summary, dict):
                return {k: str(v) for k, v in summary.items()}
        return {"mode": "-", "density": "-", "filter": "none", "selected": "none"}

    def _help_overlay_text(self) -> str:
        if isinstance(self.screen, IssueFlowScreen):
            return (
                "KEYBOARD HELP\n"
                "Issue Flow: j/k move • Enter open detail • Esc close detail/screen • o open PR • b copy branch • c open check • a run agent • i open issue\n"
                "Global: / filter/search • Ctrl+B back • ? toggle help"
            )
        if isinstance(self.screen, SprintIssueScreen):
            return (
                "KEYBOARD HELP\n"
                "Sprint Item: o open in Linear • c comment draft • p open editor • T terminal note • r github drilldown • P issue flow • Esc close\n"
                "Global: / filter/search • Ctrl+B back • ? toggle help"
            )
        tab_label = self._active_tab_label()
        tab_specific = {
            "Linear": "j/k select project, PgUp/PgDn page, v mode, g density, Enter/Esc detail, ]/[ scope",
            "GitHub": "j/k row, PgUp/PgDn, Enter/Esc detail, o open, O check, b branch, i jump, P flow, S/L/C filters, R clear",
            "Blockers": "j/k select issue, PgUp/PgDn, Enter detail, v sort mode, f assignee filter, o open, i jump",
            "Sprint": "h/j/k/l move, PgUp/PgDn, Enter/Esc detail, o open, O editor, b copy ID, i jump, P flow, m/x/a/e update, c comment",
            "Timeline": "j/k row, PgUp/PgDn, Enter/Esc detail, r blocked drilldown/back, ]/[ scope, / filter/search",
            "Workload": "j/k member, PgUp/PgDn, Enter/Esc detail, v mode, g density, =/- simulation shift",
            "Ideation": "j/k concept, PgUp/PgDn, Enter/Esc detail, v category, g density, 9/0 pan, =/- zoom, ;/' series, 7 style",
        }
        current_help = tab_specific.get(tab_label, "")
        return (
            "KEYBOARD HELP\n"
            "Global: d/G/s/t/w/n tabs • Space focus toggle • K hotkeys • z sidebar • F freshness • h/l context • j/k move • PgUp/PgDn page • ]/[ scope • Shift+Up/Down level • ,/. project • y linear sync • Y github sync • / filter/search • Ctrl+B back\n"
            "Detail: Enter or Shift+Space open/confirm • Shift+Enter item view • Esc close/clear • ? toggle help\n"
            "Presets: 1 Exec • 2 Manager • 3 IC\n"
            f"{tab_label}: {current_help}\n"
            "Quick commands: /back /filter /visual /density /freshness /hotkeys /detail /preset exec /preset manager /preset ic"
        )

    def _hotkey_bar_text(self) -> str:
        self._normalize_page_focus_section()
        if isinstance(self.screen, IssueFlowScreen):
            return (
                "Keys: j/k move | Enter or Shift+Space detail | Esc close | o open PR | c open check | "
                "b copy branch | a run agent | i open issue | / filter/search | Ctrl+B back | Space tab focus\n"
                f"{self._hotkey_context_line()}"
            )
        if isinstance(self.screen, SprintIssueScreen):
            return (
                "Keys: o linear | c comment | p editor | T terminal | r github | P issue flow | Esc close | Ctrl+B back\n"
                f"{self._hotkey_context_line()}"
            )
        if not self.page_focus_locked:
            return (
                "Keys: Left/Right switch tabs | d/G/s/t/w/n jump tabs | Space return to page controls\n"
                f"{self._hotkey_context_line()}"
            )

        tab_label = self._active_tab_label()
        sprint = self._active_sprint_view()
        if sprint is not None:
            if sprint.filter_active:
                line1 = "Keys: type to filter | Enter apply | Esc clear | Backspace delete | Space tab focus"
            elif self.page_focus_section == "detail":
                line1 = "Keys: Left section back to board | Enter or Shift+Space detail | Esc compact detail"
            elif sprint.detail_open:
                line1 = (
                    "Keys: Arrow/HJKL move cards | Enter detail view | o open | O editor | b copy ID | i jump | P flow | "
                    "m status | x close | a assignee | e estimate | c comment"
                )
            else:
                line1 = (
                    "Keys: Arrow/HJKL move cards | / filter | Enter open detail | "
                    "o open | i jump | P flow | m/x/a/e update"
                )
            return f"{line1}\n{self._hotkey_context_line()}"

        blocked = self.query_one(ContentSwitcher).query_one("#blocked", BlockedQueueView)
        if self.query_one(ContentSwitcher).current == "blocked":
            line1 = (
                "Keys: ↑/↓ select blocker | Enter detail | v sort age/proj/owner | "
                "f filter all/mine/unassigned | o open | i jump | / filter"
            )
            return f"{line1}\n{self._hotkey_context_line()}"

        github = self._active_github_view()
        if github is not None:
            mode = getattr(github, "visual_mode", "repos")
            if self.page_focus_section == "detail":
                line1 = "Keys: Left section back to list | Enter or Shift+Space detail | Esc compact detail"
            elif mode == "checks":
                line1 = (
                    "Keys: ↑/↓ select check | → detail | Enter drilldown | o open | O check | b branch | "
                    "i jump | S/L/C filters | R clear"
                )
            elif mode == "prs":
                line1 = (
                    "Keys: ↑/↓ select PR | → detail | Enter drilldown | o open | O check | b branch | "
                    "i jump | S/L/C filters | R clear"
                )
            elif mode == "failing_prs":
                line1 = (
                    "Keys: ↑/↓ select PR | → detail | r rerun failed check | o open | O check | b branch | "
                    "i jump | S/L/C filters | R clear"
                )
            else:
                line1 = (
                    "Keys: ↑/↓ select repo | → detail | Enter drilldown | "
                    "v mode | g density | S/L/C filters | R clear"
                )
            return f"{line1}\n{self._hotkey_context_line()}"

        timeline = self._active_timeline_view()
        if timeline is not None:
            mode = getattr(timeline, "visual_mode", "project")
            if self.page_focus_section == "detail":
                line1 = "Keys: Left section back to list | Enter or Shift+Space detail | Esc compact detail"
            elif mode == "blocked":
                line1 = (
                    "Keys: ↑/↓ blocked items | → detail | Enter or Shift+Space detail | v mode | g density | "
                    "r drilldown/back | / filter/search"
                )
            else:
                line1 = (
                    "Keys: ↑/↓ rows | → detail | Enter or Shift+Space detail | "
                    "v mode | g density | r blocked drilldown | ]/[ scope"
                )
            return f"{line1}\n{self._hotkey_context_line()}"

        workload = self._active_workload_view()
        if workload is not None:
            if self.page_focus_section == "detail":
                line1 = "Keys: Left section back to list | Enter or Shift+Space detail | Esc compact detail"
            else:
                line1 = (
                    "Keys: ↑/↓ members | → detail | Enter or Shift+Space detail | "
                    "v mode | g density | =/- simulation | ]/[ scope"
                )
            return f"{line1}\n{self._hotkey_context_line()}"

        ideation = self._active_ideation_view()
        if ideation is not None:
            if self.page_focus_section == "detail":
                line1 = "Keys: Left section back to gallery | Enter or Shift+Space detail | Esc compact detail"
            else:
                line1 = (
                    "Keys: ↑/↓ concepts | → detail | Enter or Shift+Space detail | v category | "
                    "g density | 9/0 pan | +/- zoom | ;/' series | 7 style"
                )
            return f"{line1}\n{self._hotkey_context_line()}"

        line1 = "Keys: ↑/↓ move | → detail | Enter or Shift+Space detail | v mode | g density | ]/[ scope"
        return f"{line1}\n{self._hotkey_context_line()}"

    def _hotkey_context_line(self) -> str:
        self._normalize_page_focus_section()
        summary = self._context_summary_for_active_view()
        mode = summary.get("mode", "-")
        selected = summary.get("selected", "none")
        filter_value = summary.get("filter", "none")
        return (
            f"Context: page={self._active_tab_label()} section={self.page_focus_section} "
            f"mode={mode} selected={selected} filter={filter_value}"
        )

    def _publish_action_result(self, ok: bool, message: str, track: bool = False) -> None:
        final_message = message
        if not ok and "linear_status_mappings." in message and not self.missing_mapping_hint_shown:
            final_message = f"{message} | Hint: update projectdash.config.json then press y to sync."
            self.missing_mapping_hint_shown = True
        
        # Track important actions in database
        if ok and track:
            try:
                # We use a worker to avoid blocking the UI thread for DB writes
                async def record():
                    view = self._active_detail_view()
                    target_id = "unknown"
                    action_type = self._active_tab_label()
                    if view:
                        if hasattr(view, "selected_issue_id") and view.selected_issue_id:
                            target_id = view.selected_issue_id
                        elif hasattr(view, "selected_pull_request_id") and view.selected_pull_request_id:
                            target_id = view.selected_pull_request_id
                        elif hasattr(view, "selected_member") and view.selected_member:
                            target_id = view.selected_member

                    await self.data_manager.record_action(
                        action_type=f"{action_type.lower()}_action",
                        target_id=target_id,
                        status="success",
                        message=message,
                        payload={"actor": self.data_manager.current_user_id()}
                    )
                self.run_worker(record(), exclusive=False)
            except Exception:
                pass

        self.update_app_status(final_message)
        self._notify(final_message, severity="information" if ok else "error")


def run() -> None:
    load_project_env()
    app = ProjectDash()
    app.run()


if __name__ == "__main__":
    run()
