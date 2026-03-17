from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import os
import shutil
import subprocess
import webbrowser

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from projectdash.models import CiCheck, PullRequest, Repository
from projectdash.widgets.triage_chips import TriageFilterChips


@dataclass(frozen=True)
class RepositorySnapshot:
    repository: Repository
    label: str
    total_prs: int
    open_prs: int
    merged_prs: int
    closed_prs: int
    linked_prs: int
    checks_total: int
    checks_passing: int
    checks_pending: int
    checks_failing: int
    latest_update: str | None


class GitHubDashboardView(Static):
    VISUAL_MODES = ("repos", "prs", "failing_prs", "checks")
    STATE_FILTERS = ("all", "open", "merged", "closed")
    LINK_FILTERS = ("all", "linked", "unlinked")
    TRIAGE_FILTERS = ("mine", "blocked", "failing", "stale")
    DEFAULT_TRIAGE_STALE_DAYS = 7

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.visual_mode = "repos"
        self.graph_density = "compact"
        self.state_filter = "all"
        self.link_filter = "all"
        self.failing_only = False
        self.mine_only = False
        self.blocked_only = False
        self.stale_only = False
        self.drilldown_issue_id: str | None = None
        self.triage_filters: set[str] = set()
        self._last_cleared_triage_filters: set[str] = set()

        self.selected_repository_id: str | None = None
        self.selected_pull_request_id: str | None = None
        self.selected_check_id: str | None = None
        self._repository_order: list[str] = []
        self._pull_request_order: list[str] = []
        self._check_order: list[str] = []
        self.detail_open = False

        self._filtered_pull_requests: list[PullRequest] = []
        self._filtered_checks: list[CiCheck] = []
        self._filtered_pull_requests_by_id: dict[str, PullRequest] = {}
        self._filtered_pull_requests_by_repo: dict[str, list[PullRequest]] = {}
        self._filtered_checks_by_pr: dict[str, list[CiCheck]] = {}
        self._visible_checks: list[CiCheck] = []
        self._visible_checks_by_id: dict[str, CiCheck] = {}
        self._drilldown_restore_state: dict[str, object] | None = None

    def on_mount(self) -> None:
        self.refresh_view()

    def on_show(self) -> None:
        self.refresh_view()

    def compose(self) -> ComposeResult:
        with Horizontal(id="github-layout"):
            with Vertical(id="github-main"):
                yield Static("GITHUB DASHBOARD", id="view-header")
                yield Static("SYNC FRESHNESS", id="github-freshness-label", classes="section-label")
                yield Static("", id="github-freshness", classes="placeholder-text")
                yield Static("SUMMARY", classes="section-label")
                yield Static("", id="github-summary", classes="placeholder-text")
                yield TriageFilterChips(
                    {name: False for name in self.TRIAGE_FILTERS}, id="github-triage-chips"
                )
                yield Static("DETAILS", classes="section-label")
                yield Static("", id="github-content", classes="placeholder-text")
            with Vertical(id="github-sidebar", classes="detail-sidebar"):
                yield Static("REPOSITORY DETAIL", classes="detail-sidebar-title")
                yield Static("", id="github-detail")
                yield Static("", id="github-hint", classes="detail-sidebar-hint")

    def refresh_view(self) -> None:
        if self._apply_freshness_visibility():
            self.query_one("#github-freshness", Static).update(self._freshness_text())
        repositories = self.app.data_manager.get_repositories()
        pull_requests = self.app.data_manager.get_pull_requests()
        checks = self.app.data_manager.get_ci_checks()

        checks_by_pr = self._checks_by_pull_request(checks)
        filtered_pull_requests = [
            pull_request
            for pull_request in pull_requests
            if self._pull_request_matches_filters(pull_request, checks_by_pr)
        ]
        filtered_checks = self._filter_checks(filtered_pull_requests, checks_by_pr)
        snapshots, prs_by_repo, checks_by_pr = self._build_snapshots(
            repositories,
            filtered_pull_requests,
            filtered_checks,
        )

        self._filtered_pull_requests = filtered_pull_requests
        self._filtered_checks = filtered_checks
        self._filtered_pull_requests_by_id = {pull_request.id: pull_request for pull_request in filtered_pull_requests}
        self._filtered_pull_requests_by_repo = prs_by_repo
        self._filtered_checks_by_pr = checks_by_pr

        self._repository_order = [snapshot.repository.id for snapshot in snapshots]
        if self.selected_repository_id and self.selected_repository_id not in self._repository_order:
            self.selected_repository_id = None
        if self.selected_repository_id is None and snapshots:
            self.selected_repository_id = snapshots[0].repository.id

        visible_pull_requests = self._visible_pull_requests()
        visible_checks = self._filter_checks(visible_pull_requests, checks_by_pr)
        self._pull_request_order = [pull_request.id for pull_request in visible_pull_requests]
        if self.selected_pull_request_id and self.selected_pull_request_id not in self._pull_request_order:
            self.selected_pull_request_id = None
        if self.selected_pull_request_id is None and self._pull_request_order:
            self.selected_pull_request_id = self._pull_request_order[0]
        if self.selected_pull_request_id:
            selected_pull_request = self._filtered_pull_requests_by_id.get(self.selected_pull_request_id)
            if selected_pull_request:
                self.selected_repository_id = selected_pull_request.repository_id

        self._visible_checks = visible_checks
        self._visible_checks_by_id = {check.id: check for check in visible_checks}
        self._check_order = [check.id for check in visible_checks]
        if self.selected_check_id and self.selected_check_id not in self._check_order:
            self.selected_check_id = None
        if self.selected_check_id is None and self._check_order:
            self.selected_check_id = self._check_order[0]
        if self.selected_check_id:
            selected_check = self._visible_checks_by_id.get(self.selected_check_id)
            if selected_check:
                selected_pr = self._filtered_pull_requests_by_id.get(selected_check.pull_request_id)
                if selected_pr:
                    self.selected_pull_request_id = selected_pr.id
                    self.selected_repository_id = selected_pr.repository_id

        self.query_one("#github-summary", Static).update(
            self._summary_text(
                snapshots=snapshots,
                pull_requests=filtered_pull_requests,
                checks=filtered_checks,
            )
        )
        self.query_one("#github-triage-chips", TriageFilterChips).update_filters(
            {name: name in self.triage_filters for name in self.TRIAGE_FILTERS}
        )
        self.query_one("#github-content", Static).update(
            self._content_text(
                snapshots=snapshots,
                pull_requests=visible_pull_requests,
                checks=visible_checks,
            )
        )
        self._refresh_detail_panel(
            snapshots=snapshots,
            pull_requests=visible_pull_requests,
            checks_by_pr=self._filtered_checks_by_pr,
        )

    def toggle_visual_mode(self) -> tuple[bool, str]:
        current_index = self.VISUAL_MODES.index(self.visual_mode)
        self.visual_mode = self.VISUAL_MODES[(current_index + 1) % len(self.VISUAL_MODES)]
        self.refresh_view()
        label = {
            "repos": "Repositories",
            "prs": "Pull Requests",
            "checks": "CI Checks",
        }.get(self.visual_mode, self.visual_mode)
        return True, f"GitHub mode: {label}"

    def toggle_graph_density(self) -> tuple[bool, str]:
        self.graph_density = "detailed" if self.graph_density == "compact" else "compact"
        self.refresh_view()
        return True, f"GitHub density: {self.graph_density}"

    def cycle_state_filter(self) -> tuple[bool, str]:
        current_index = self.STATE_FILTERS.index(self.state_filter)
        self.state_filter = self.STATE_FILTERS[(current_index + 1) % len(self.STATE_FILTERS)]
        self.refresh_view()
        return True, f"GitHub state filter: {self.state_filter}"

    def cycle_link_filter(self) -> tuple[bool, str]:
        current_index = self.LINK_FILTERS.index(self.link_filter)
        self.link_filter = self.LINK_FILTERS[(current_index + 1) % len(self.LINK_FILTERS)]
        if self.link_filter != "linked":
            self.drilldown_issue_id = None
        self.refresh_view()
        return True, f"GitHub link filter: {self.link_filter}"

    def toggle_failing_only(self) -> tuple[bool, str]:
        self.failing_only = not self.failing_only
        self._sync_triage_filters_from_flags()
        self.refresh_view()
        status = "on" if self.failing_only else "off"
        return True, f"GitHub failing-only filter: {status}"

    def clear_filters(self) -> tuple[bool, str]:
        self.state_filter = "all"
        self.link_filter = "all"
        self.failing_only = False
        self.mine_only = False
        self.blocked_only = False
        self.stale_only = False
        self._sync_triage_filters_from_flags()
        self.drilldown_issue_id = None
        self.refresh_view()
        return True, "GitHub filters cleared"

    def focus_issue(self, issue_id: str) -> tuple[bool, str]:
        normalized = issue_id.strip()
        if not normalized:
            return False, "No issue id provided"
        if self._drilldown_restore_state is None:
            self._drilldown_restore_state = self._capture_drilldown_restore_state()
        self.drilldown_issue_id = normalized
        self.link_filter = "linked"
        self.visual_mode = "prs"
        self.detail_open = True
        self.refresh_view()
        if not self._pull_request_order:
            self._restore_drilldown_state()
            return False, f"No linked pull requests found for {normalized}"
        return True, f"Showing PR drilldown for {normalized}"

    def clear_issue_drilldown(self) -> tuple[bool, str]:
        if not self.drilldown_issue_id:
            return False, "No issue drilldown active"
        issue_id = self.drilldown_issue_id
        self._restore_drilldown_state()
        return True, f"Cleared issue drilldown ({issue_id})"

    def move_selection(self, delta: int) -> None:
        if self.visual_mode == "prs":
            if not self._pull_request_order:
                return
            if self.selected_pull_request_id not in self._pull_request_order:
                self.selected_pull_request_id = self._pull_request_order[0]
                self.refresh_view()
                return
            current_index = self._pull_request_order.index(self.selected_pull_request_id)
            next_index = (current_index + delta) % len(self._pull_request_order)
            self.selected_pull_request_id = self._pull_request_order[next_index]
            selected_pull_request = self._filtered_pull_requests_by_id.get(self.selected_pull_request_id)
            if selected_pull_request:
                self.selected_repository_id = selected_pull_request.repository_id
            self.refresh_view()
            return
        if self.visual_mode == "checks":
            if not self._check_order:
                return
            if self.selected_check_id not in self._check_order:
                self.selected_check_id = self._check_order[0]
                selected_check = self._visible_checks_by_id.get(self.selected_check_id)
                if selected_check:
                    selected_pr = self._filtered_pull_requests_by_id.get(selected_check.pull_request_id)
                    if selected_pr:
                        self.selected_pull_request_id = selected_pr.id
                        self.selected_repository_id = selected_pr.repository_id
                self.refresh_view()
                return
            current_index = self._check_order.index(self.selected_check_id)
            next_index = (current_index + delta) % len(self._check_order)
            self.selected_check_id = self._check_order[next_index]
            selected_check = self._visible_checks_by_id.get(self.selected_check_id)
            if selected_check:
                selected_pr = self._filtered_pull_requests_by_id.get(selected_check.pull_request_id)
                if selected_pr:
                    self.selected_pull_request_id = selected_pr.id
                    self.selected_repository_id = selected_pr.repository_id
            self.refresh_view()
            return

        if not self._repository_order:
            return
        if self.selected_repository_id not in self._repository_order:
            self.selected_repository_id = self._repository_order[0]
            self.refresh_view()
            return
        current_index = self._repository_order.index(self.selected_repository_id)
        next_index = (current_index + delta) % len(self._repository_order)
        self.selected_repository_id = self._repository_order[next_index]
        self.refresh_view()

    def page_selection(self, delta_pages: int) -> None:
        if delta_pages == 0:
            return
        self.move_selection(delta_pages * self._page_size_for_mode())

    def open_primary(self) -> tuple[bool, str]:
        return self.open_selected_pull_request()

    def open_secondary(self) -> tuple[bool, str]:
        return self.open_selected_check()

    def copy_primary(self) -> tuple[bool, str]:
        return self.copy_selected_branch()

    def jump_context(self) -> tuple[bool, str]:
        issue_id = self.selected_issue_for_jump()
        if not issue_id:
            return False, "No linked issue for selected PR"
        self.app.action_switch_tab("sprint")
        sprint = self.app._active_sprint_view()
        if sprint is None:
            return False, "Sprint board unavailable"
        return sprint.focus_issue(issue_id)

    async def drilldown_or_rerun(self) -> tuple[bool, str]:
        if self.visual_mode in {"failing_prs", "checks"}:
            ok, message = await self.action_rerun_ci()
            self.app._publish_action_result(ok, message, track=True)
            return ok, message
        
        self.open_detail()
        return True, "Drilldown expanded"

    def open_detail(self) -> None:
        if self.visual_mode == "repos":
            if self.selected_repository_id:
                self.visual_mode = "prs"
                self.refresh_view()
                return
        elif self.visual_mode == "prs":
            if self.selected_pull_request_id:
                self.visual_mode = "checks"
                self.refresh_view()
                return
        
        self.detail_open = True
        self.refresh_view()

    def close_detail(self) -> None:
        if self.detail_open:
            self.detail_open = False
            self.refresh_view()
            return
            
        if self.visual_mode == "checks":
            self.visual_mode = "prs"
            self.refresh_view()
            return
        elif self.visual_mode == "prs":
            if self.drilldown_issue_id:
                self._restore_drilldown_state()
            else:
                self.visual_mode = "repos"
                self.refresh_view()
            return
            
        if self.drilldown_issue_id:
            self._restore_drilldown_state()
            return

    async def action_rerun_ci(self) -> tuple[bool, str]:
        check = self.selected_check()
        if not check:
            return False, "No check selected to rerun"
        
        return await self.app.data_manager.github_mutation_service.rerun_ci_check(check.id)

    async def action_merge_pr(self) -> tuple[bool, str]:
        pr = self.selected_pull_request()
        if not pr:
            return False, "No pull request selected to merge"
        
        # Default to squash if it's a common preference, or just 'merge'
        return await self.app.data_manager.github_mutation_service.merge_pull_request(pr.id, merge_method="squash")

    async def action_review_pr(self, event: str = "APPROVE") -> tuple[bool, str]:
        pr = self.selected_pull_request()
        if not pr:
            return False, "No pull request selected to review"
        
        return await self.app.data_manager.github_mutation_service.approve_pull_request(pr.id, body="LGTM")

    def context_summary(self) -> dict[str, str]:
        selected = self._selected_label()
        drilldown = self.drilldown_issue_id or "-"
        triage = ",".join(sorted(self.triage_filters)) if self.triage_filters else "none"
        return {
            "mode": self.visual_mode,
            "density": self.graph_density,
            "filter": (
                f"state:{self.state_filter} link:{self.link_filter} fail:{'on' if self.failing_only else 'off'} "
                f"issue:{drilldown} triage:{triage}"
            ),
            "selected": selected,
        }

    def capture_filter_state(self) -> dict[str, object]:
        return {
            "state_filter": self.state_filter,
            "link_filter": self.link_filter,
            "failing_only": self.failing_only,
            "mine_only": self.mine_only,
            "blocked_only": self.blocked_only,
            "stale_only": self.stale_only,
            "triage_filters": sorted(self.triage_filters),
            "drilldown_issue_id": self.drilldown_issue_id,
            "visual_mode": self.visual_mode,
            "graph_density": self.graph_density,
            "selected_repository_id": self.selected_repository_id,
            "selected_pull_request_id": self.selected_pull_request_id,
            "selected_check_id": self.selected_check_id,
            "detail_open": self.detail_open,
        }

    def restore_filter_state(self, state: dict[str, object] | None) -> None:
        if not state:
            return
        self.state_filter = str(state.get("state_filter") or self.state_filter)
        self.link_filter = str(state.get("link_filter") or self.link_filter)
        self.failing_only = bool(state.get("failing_only", self.failing_only))
        self.mine_only = bool(state.get("mine_only", self.mine_only))
        self.blocked_only = bool(state.get("blocked_only", self.blocked_only))
        self.stale_only = bool(state.get("stale_only", self.stale_only))
        triage_filters = state.get("triage_filters")
        if isinstance(triage_filters, list):
            self.triage_filters = {
                str(value).strip().casefold()
                for value in triage_filters
                if str(value).strip().casefold() in self.TRIAGE_FILTERS
            }
        self.drilldown_issue_id = str(state.get("drilldown_issue_id") or "") or None
        self.visual_mode = str(state.get("visual_mode") or self.visual_mode)
        self.graph_density = str(state.get("graph_density") or self.graph_density)
        self.selected_repository_id = str(state.get("selected_repository_id") or "") or None
        self.selected_pull_request_id = str(state.get("selected_pull_request_id") or "") or None
        self.selected_check_id = str(state.get("selected_check_id") or "") or None
        self.detail_open = bool(state.get("detail_open", self.detail_open))
        self._sync_triage_filters_from_flags()
        self.refresh_view()

    def apply_triage_filter(self, name: str) -> tuple[bool, str]:
        normalized = name.strip().casefold()
        if normalized not in self.TRIAGE_FILTERS:
            return False, f"Unknown GitHub triage filter: {name}"
        target_attr = {
            "mine": "mine_only",
            "blocked": "blocked_only",
            "failing": "failing_only",
            "stale": "stale_only",
        }[normalized]
        enabled = not bool(getattr(self, target_attr))
        setattr(self, target_attr, enabled)
        self._sync_triage_filters_from_flags()
        self.refresh_view()
        return True, f"GitHub triage {normalized}: {'on' if enabled else 'off'}"

    def clear_triage_filters(self) -> tuple[bool, str]:
        self._sync_triage_filters_from_flags()
        if not self.triage_filters:
            return False, "No GitHub triage filters active"
        self._last_cleared_triage_filters = set(self.triage_filters)
        self.mine_only = False
        self.blocked_only = False
        self.failing_only = False
        self.stale_only = False
        self._sync_triage_filters_from_flags()
        self.refresh_view()
        return True, "GitHub triage filters cleared"

    def restore_triage_filters(self) -> tuple[bool, str]:
        if not self._last_cleared_triage_filters:
            return False, "No GitHub triage filters to restore"
        self.mine_only = "mine" in self._last_cleared_triage_filters
        self.blocked_only = "blocked" in self._last_cleared_triage_filters
        self.failing_only = "failing" in self._last_cleared_triage_filters
        self.stale_only = "stale" in self._last_cleared_triage_filters
        self._sync_triage_filters_from_flags()
        self.refresh_view()
        active = ",".join(sorted(self.triage_filters))
        return True, f"GitHub triage filters restored: {active}"

    def selected_issue_for_jump(self) -> str | None:
        pull_request = self.selected_pull_request()
        if pull_request is None:
            return None
        return pull_request.issue_id

    def selected_pull_request(self) -> PullRequest | None:
        if self.selected_pull_request_id:
            pull_request = self._filtered_pull_requests_by_id.get(self.selected_pull_request_id)
            if pull_request:
                return pull_request
        if not self._pull_request_order:
            return None
        first_id = self._pull_request_order[0]
        return self._filtered_pull_requests_by_id.get(first_id)

    def selected_check(self) -> CiCheck | None:
        if self.selected_check_id:
            check = self._visible_checks_by_id.get(self.selected_check_id)
            if check:
                return check
        if not self._check_order:
            return None
        first_id = self._check_order[0]
        return self._visible_checks_by_id.get(first_id)

    def _freshness_text(self) -> str:
        return self.app.data_manager.freshness_summary_line(("github", "linear"))

    def _apply_freshness_visibility(self) -> bool:
        visible = bool(getattr(self.app, "sync_freshness_visible", True))
        for widget_id in ("#github-freshness-label", "#github-freshness"):
            try:
                self.query_one(widget_id, Static).display = visible
            except Exception:
                pass
        return visible

    def open_selected_pull_request(self) -> tuple[bool, str]:
        pull_request = self.selected_pull_request()
        if pull_request is None:
            return False, "No pull request selected"
        if not pull_request.url:
            return False, f"No URL for PR #{pull_request.number}"
        try:
            opened = webbrowser.open_new_tab(pull_request.url)
        except Exception as error:
            return False, f"Failed to open pull request URL: {error}"
        if not opened:
            return False, f"Could not launch browser. Open manually: {pull_request.url}"
        return True, f"Opened PR #{pull_request.number}"

    def open_selected_check(self) -> tuple[bool, str]:
        check = self._check_for_open_action()
        if check is None:
            pull_request = self.selected_pull_request()
            if pull_request is not None and self.visual_mode == "prs":
                return False, f"No checks available for PR #{pull_request.number}"
            return False, "No check selected"
        if not check.url:
            return False, f"No URL for check {check.name}"
        try:
            opened = webbrowser.open_new_tab(check.url)
        except Exception as error:
            return False, f"Failed to open check URL: {error}"
        if not opened:
            return False, f"Could not launch browser. Open manually: {check.url}"
        return True, f"Opened check {check.name}"

    def copy_selected_branch(self) -> tuple[bool, str]:
        pull_request = self.selected_pull_request()
        if pull_request is None:
            return False, "No pull request selected"
        branch = (pull_request.head_branch or "").strip()
        if not branch:
            return False, f"No head branch available for PR #{pull_request.number}"
        copied = self._copy_to_clipboard(branch)
        if copied:
            return True, f"Copied branch: {branch}"
        return False, f"No clipboard tool found. Branch: {branch}"

    def _summary_text(
        self,
        *,
        snapshots: list[RepositorySnapshot],
        pull_requests: list[PullRequest],
        checks: list[CiCheck],
    ) -> str:
        open_prs = sum(snapshot.open_prs for snapshot in snapshots)
        linked_prs = sum(snapshot.linked_prs for snapshot in snapshots)
        failing_checks = sum(snapshot.checks_failing for snapshot in snapshots)
        auth_label = "connected" if os.getenv("GITHUB_TOKEN") else "token missing"
        sync_label = self.app.data_manager.last_sync_at or "no sync"
        filter_label = self._filter_summary_label()
        return (
            f"Repos: {len(snapshots)}  |  PRs: {len(pull_requests)} ({open_prs} open)  |  "
            f"Linked: {linked_prs}  |  Checks: {len(checks)} ({failing_checks} failing)  |  "
            f"{filter_label}  |  Auth: {auth_label}  |  Last sync: {sync_label}"
        )

    def _content_text(
        self,
        *,
        snapshots: list[RepositorySnapshot],
        pull_requests: list[PullRequest],
        checks: list[CiCheck],
    ) -> Text:
        if self.visual_mode == "repos":
            return self._repositories_text(snapshots)
        if self.visual_mode == "prs":
            return self._pull_requests_text(pull_requests)
        if self.visual_mode == "failing_prs":
            failing = [pr for pr in pull_requests if any(self._check_is_failing_for_pr(pr) for pr in [pr])]
            # Wait, our pull_requests list is already filtered by other flags.
            # Let's just filter for failing ones specifically here.
            all_prs = self.app.data_manager.get_pull_requests()
            all_checks_by_pr = self._checks_by_pull_request(self.app.data_manager.get_ci_checks())
            failing_prs = []
            for pr in all_prs:
                if pr.state.casefold() != "open":
                    continue
                pr_checks = all_checks_by_pr.get(pr.id, [])
                if any(self._check_bucket(c) == "failing" for c in pr_checks):
                    failing_prs.append(pr)
            failing_prs.sort(key=lambda x: x.updated_at or "", reverse=True)
            return self._failing_prs_text(failing_prs)
        return self._checks_text(checks)

    def _check_is_failing_for_pr(self, pr: PullRequest) -> bool:
        checks = self._filtered_checks_by_pr.get(pr.id, [])
        return any(self._check_bucket(c) == "failing" for c in checks)

    def _failing_prs_text(self, pull_requests: list[PullRequest]) -> Text:
        text = Text()
        text.append("FAILING PR TRIAGE LANE\n", style="bold #ff0000")
        text.append("Fast-track triage for open PRs with failing CI checks.\n", style="#777777")
        text.append("--------------------------------------------------------------------------\n", style="#333333")
        if not pull_requests:
            text.append("No failing pull requests in current scope. Great job!\n", style="#00ff00")
            return text

        visible, start, end = self._windowed_rows(
            pull_requests,
            selected_id=self.selected_pull_request_id,
            row_id=lambda pr: pr.id,
            page_size=self._mode_page_size("prs"),
        )
        for pr in visible:
            marker = ">" if pr.id == self.selected_pull_request_id else " "
            issue_link = pr.issue_id or "unlinked"
            title = pr.title[:38]
            text.append(
                f"{marker} ✕ #{pr.number:<4} {title.ljust(38)} issue {issue_link}\n",
                style="#ffffff",
            )
            if self.graph_density == "detailed":
                updated = pr.updated_at or "?"
                text.append(f"    updated {updated}\n", style="#777777")
        if len(pull_requests) > len(visible):
            text.append(
                f"Showing {start + 1}-{end} of {len(pull_requests)} failing PRs (PgUp/PgDn page)\n",
                style="#666666",
            )
        return text

    def _repositories_text(self, snapshots: list[RepositorySnapshot]) -> Text:
        text = Text()
        text.append("REPOSITORY SNAPSHOT\n", style="bold #666666")
        text.append(
            "Repo                      PRs (o/m/c)   Linked   Checks (pass/pending/fail)\n",
            style="bold #666666",
        )
        text.append("--------------------------------------------------------------------------\n", style="#333333")
        if not snapshots:
            text.append("No GitHub data in current scope. Press Shift+Y to sync or clear filters.\n", style="#666666")
            return text

        visible, start, end = self._windowed_rows(
            snapshots,
            selected_id=self.selected_repository_id,
            row_id=lambda snapshot: snapshot.repository.id,
            page_size=self._mode_page_size("repos"),
        )
        for snapshot in visible:
            marker = ">" if snapshot.repository.id == self.selected_repository_id else " "
            counts = f"{snapshot.open_prs}/{snapshot.merged_prs}/{snapshot.closed_prs}"
            checks = f"{snapshot.checks_passing}/{snapshot.checks_pending}/{snapshot.checks_failing}"
            text.append(
                f"{marker} {snapshot.label[:24].ljust(24)} {counts:>11}   "
                f"{snapshot.linked_prs:>5}   {checks:>23}\n",
                style="#ffffff",
            )
            if self.graph_density == "detailed" and snapshot.latest_update:
                text.append(f"   updated {snapshot.latest_update}\n", style="#777777")
        if len(snapshots) > len(visible):
            text.append(
                f"Showing {start + 1}-{end} of {len(snapshots)} repositories (PgUp/PgDn page, g detailed)\n",
                style="#666666",
            )
        return text

    def _pull_requests_text(self, pull_requests: list[PullRequest]) -> Text:
        text = Text()
        text.append("PULL REQUEST FLOW\n", style="bold #666666")
        text.append(f"Scope: {self._selected_repository_label() if self.selected_repository_id else 'all repositories'}\n", style="#777777")
        text.append("--------------------------------------------------------------------------\n", style="#333333")
        if not pull_requests:
            text.append("No pull requests in current scope.\n", style="#666666")
            return text

        visible, start, end = self._windowed_rows(
            pull_requests,
            selected_id=self.selected_pull_request_id,
            row_id=lambda pull_request: pull_request.id,
            page_size=self._mode_page_size("prs"),
        )
        for pull_request in visible:
            marker = ">" if pull_request.id == self.selected_pull_request_id else " "
            state = self._pr_symbol(pull_request)
            issue_link = pull_request.issue_id or "-"
            title = pull_request.title[:38]
            text.append(
                f"{marker} {state} #{pull_request.number:<4} {title.ljust(38)} issue {issue_link}\n",
                style="#ffffff",
            )
            if self.graph_density == "detailed":
                branch = f"{pull_request.head_branch or '?'} -> {pull_request.base_branch or '?'}"
                updated = pull_request.updated_at or "?"
                text.append(f"    {branch}   updated {updated}\n", style="#777777")
        if len(pull_requests) > len(visible):
            text.append(
                f"Showing {start + 1}-{end} of {len(pull_requests)} pull requests (PgUp/PgDn page, g detailed)\n",
                style="#666666",
            )
        return text

    def _checks_text(self, checks: list[CiCheck]) -> Text:
        text = Text()
        text.append("CI CHECKS\n", style="bold #666666")
        text.append(f"Scope: {self._selected_repository_label() if self.selected_repository_id else 'all repositories'}\n", style="#777777")
        text.append("--------------------------------------------------------------------------\n", style="#333333")
        if not checks:
            text.append("No checks in current scope.\n", style="#666666")
            return text

        passing = sum(1 for check in checks if self._check_bucket(check) == "passing")
        pending = sum(1 for check in checks if self._check_bucket(check) == "pending")
        failing = sum(1 for check in checks if self._check_bucket(check) == "failing")
        max_count = max(passing, pending, failing, 1)
        width = 20 if self.graph_density == "detailed" else 12

        def _bar(value: int) -> str:
            filled = int((value / max_count) * width) if max_count else 0
            return "█" * filled + "░" * (width - filled)

        text.append(f"PASS    {_bar(passing)} {passing}\n", style="#ffffff")
        text.append(f"PENDING {_bar(pending)} {pending}\n", style="#ffffff")
        text.append(f"FAIL    {_bar(failing)} {failing}\n", style="#ffffff")
        text.append("\nCHECKS LIST\n", style="bold #666666")
        text.append("--------------------------------------------------------------------------\n", style="#333333")

        visible, start, end = self._windowed_rows(
            checks,
            selected_id=self.selected_check_id,
            row_id=lambda check: check.id,
            page_size=self._mode_page_size("checks"),
        )
        for check in visible:
            marker = ">" if check.id == self.selected_check_id else " "
            pull_request = self._filtered_pull_requests_by_id.get(check.pull_request_id)
            pull_request_number = pull_request.number if pull_request else "?"
            state = check.conclusion or check.status or "-"
            status = self._check_symbol(check)
            text.append(
                f"{marker} {status} #{pull_request_number:<4} {check.name[:40].ljust(40)} {state}\n",
                style="#ffffff",
            )
            if self.graph_density == "detailed":
                updated = self._format_timestamp(check.updated_at or check.completed_at or check.started_at)
                repo_label = "-"
                if pull_request:
                    repo_label = self._repository_label(self._repository_for_pull_request(pull_request))
                text.append(f"    {repo_label}   updated {updated}\n", style="#777777")
        if len(checks) > len(visible):
            text.append(
                f"Showing {start + 1}-{end} of {len(checks)} checks (PgUp/PgDn page, g detailed)\n",
                style="#666666",
            )
        return text

    def _build_snapshots(
        self,
        repositories: list[Repository],
        pull_requests: list[PullRequest],
        checks: list[CiCheck],
    ) -> tuple[list[RepositorySnapshot], dict[str, list[PullRequest]], dict[str, list[CiCheck]]]:
        checks_by_pr = self._checks_by_pull_request(checks)
        repository_by_id: dict[str, Repository] = {repository.id: repository for repository in repositories}
        prs_by_repo: dict[str, list[PullRequest]] = {}
        for pull_request in pull_requests:
            prs_by_repo.setdefault(pull_request.repository_id, []).append(pull_request)
            if pull_request.repository_id not in repository_by_id:
                repository_by_id[pull_request.repository_id] = self._fallback_repository(pull_request)

        sorted_repo_ids = sorted(
            repository_by_id.keys(),
            key=lambda repository_id: self._repository_label(repository_by_id[repository_id]).casefold(),
        )
        snapshots: list[RepositorySnapshot] = []
        for repository_id in sorted_repo_ids:
            repository = repository_by_id[repository_id]
            repo_pull_requests = prs_by_repo.get(repository_id, [])
            open_prs = sum(1 for pull_request in repo_pull_requests if pull_request.state.casefold() == "open")
            merged_prs = sum(
                1
                for pull_request in repo_pull_requests
                if pull_request.state.casefold() == "merged" or bool(pull_request.merged_at)
            )
            closed_prs = max(0, len(repo_pull_requests) - open_prs - merged_prs)
            linked_prs = sum(1 for pull_request in repo_pull_requests if pull_request.issue_id)

            all_checks: list[CiCheck] = []
            for pull_request in repo_pull_requests:
                all_checks.extend(checks_by_pr.get(pull_request.id, []))
            checks_passing = sum(1 for check in all_checks if self._check_bucket(check) == "passing")
            checks_pending = sum(1 for check in all_checks if self._check_bucket(check) == "pending")
            checks_failing = sum(1 for check in all_checks if self._check_bucket(check) == "failing")
            latest_update = None
            if repo_pull_requests:
                latest_update = max((pull_request.updated_at or "") for pull_request in repo_pull_requests) or None

            snapshots.append(
                RepositorySnapshot(
                    repository=repository,
                    label=self._repository_label(repository),
                    total_prs=len(repo_pull_requests),
                    open_prs=open_prs,
                    merged_prs=merged_prs,
                    closed_prs=closed_prs,
                    linked_prs=linked_prs,
                    checks_total=len(all_checks),
                    checks_passing=checks_passing,
                    checks_pending=checks_pending,
                    checks_failing=checks_failing,
                    latest_update=latest_update,
                )
            )
            repo_pull_requests.sort(key=lambda pull_request: ((pull_request.updated_at or ""), pull_request.id), reverse=True)
        return snapshots, prs_by_repo, checks_by_pr

    def _refresh_detail_panel(
        self,
        *,
        snapshots: list[RepositorySnapshot],
        pull_requests: list[PullRequest],
        checks_by_pr: dict[str, list[CiCheck]],
    ) -> None:
        detail = self.query_one("#github-detail", Static)
        hint = self.query_one("#github-hint", Static)

        if self.visual_mode == "prs":
            pull_request = self.selected_pull_request()
            if pull_request is None:
                detail.update("No pull request selected.")
                hint.update("j/k select PR • PgUp/PgDn page • S state • L link • C failing • Shift+Y sync")
                return
            if not self.detail_open:
                issue = pull_request.issue_id or "unlinked"
                detail.update(
                    "PR PREVIEW\n"
                    f"#{pull_request.number} [{pull_request.state}]\n"
                    f"{pull_request.title}\n\n"
                    f"Issue: {issue}\n"
                    f"Branch: {pull_request.head_branch or '?'} -> {pull_request.base_branch or '?'}\n"
                    f"Checks: {len(checks_by_pr.get(pull_request.id, []))}\n\n"
                    "Press Enter to expand."
                )
                hint.update("Enter expand • o open PR • b copy branch • a run agent • i jump issue • PgUp/PgDn page • P issue flow")
                return

            checks = checks_by_pr.get(pull_request.id, [])
            passing = sum(1 for check in checks if self._check_bucket(check) == "passing")
            pending = sum(1 for check in checks if self._check_bucket(check) == "pending")
            failing = sum(1 for check in checks if self._check_bucket(check) == "failing")
            failing_checks = [check for check in checks if self._check_bucket(check) == "failing"][:4]
            failing_names = ", ".join(check.name for check in failing_checks) if failing_checks else "-"
            
            # List all checks
            check_list_text = []
            for check in checks:
                sym = self._check_symbol(check)
                check_list_text.append(f"{sym} {check.name[:24]}")
            
            check_list = "\n".join(check_list_text[:10])
            if len(checks) > 10:
                check_list += f"\n... and {len(checks)-10} more"

            detail.update(
                f"PR #{pull_request.number}\n\n"
                f"Title: {pull_request.title}\n"
                f"State: {pull_request.state}\n"
                f"Linked issue: {pull_request.issue_id or 'unlinked'}\n"
                f"Author: {pull_request.author_id or '-'}\n"
                f"Branch: {pull_request.head_branch or '?'} -> {pull_request.base_branch or '?'}\n"
                f"URL: {pull_request.url or '-'}\n\n"
                f"CHECK RUNS\n"
                f"{check_list}\n\n"
                "ACTIONS\n"
                "[o] Open PR  [m] Merge PR (squash)  [v] Quick Approve\n"
                "[b] Copy branch  [a] Trigger agent  [i] Jump to issue"
            )
            hint.update("Enter checks • Esc close • j/k move • r rerun failed job • m merge • v approve")
            return
        if self.visual_mode == "checks":
            check = self.selected_check()
            if check is None:
                detail.update("No check selected.")
                hint.update("j/k select check • PgUp/PgDn page • S state • L link • C failing • Shift+Y sync")
                return
            if not self.detail_open:
                pr = self._filtered_pull_requests_by_id.get(check.pull_request_id)
                pr_label = f"#{pr.number}" if pr else "PR ?"
                detail.update(
                    "CHECK PREVIEW\n"
                    f"{check.name}\n"
                    f"{pr_label}  {check.conclusion or check.status}\n"
                    f"Updated: {check.updated_at or '-'}\n\n"
                    "Press Enter to expand."
                )
                hint.update("Enter expand • c open check • j/k move • PgUp/PgDn page • S/L/C filters • Shift+Y sync")
                return

            pr = self._filtered_pull_requests_by_id.get(check.pull_request_id)
            pr_label = f"#{pr.number}" if pr else "?"
            repo_label = self._repository_label(self._repository_for_pull_request(pr)) if pr else "-"
            issue_label = pr.issue_id if pr and pr.issue_id else "unlinked"
            triage_line = self._triage_recommendation_for_check(check, pr)
            detail.update(
                f"{check.name}\n\n"
                f"PR: {pr_label}\n"
                f"Repo: {repo_label}\n"
                f"Issue: {issue_label}\n"
                f"Status: {check.status}\n"
                f"Conclusion: {check.conclusion or '-'}\n"
                f"Started: {check.started_at or '-'}\n"
                f"Completed: {check.completed_at or '-'}\n"
                f"Updated: {check.updated_at or '-'}\n"
                f"URL: {check.url or '-'}\n\n"
                f"Triage: {triage_line}\n\n"
                "ACTIONS\n"
                "[c] Open check URL\n"
                "[a] Trigger agent run  [i] Jump to issue  [P] Open issue flow"
            )
            hint.update("Enter compact • Esc close • j/k move • PgUp/PgDn page • U/A/I/P actions • S/L/C filters • Shift+Y sync")
            return

        if not snapshots:
            detail.update("No GitHub data loaded.\n\nConfigure repositories and press Shift+Y to sync.")
            hint.update("Shift+Y sync • v mode • g density")
            return
        if not self.detail_open or not self.selected_repository_id:
            active = self._selected_repository_label()
            detail.update(
                "Select a repository for detail.\n\n"
                f"Selected: {active}\n"
                f"View: {self.visual_mode}\n"
                f"Density: {self.graph_density}\n"
                "Press Enter to open details."
            )
            hint.update("j/k select • PgUp/PgDn page • Enter open • S/L/C filters • v mode • g density")
            return

        selected_snapshot = None
        for snapshot in snapshots:
            if snapshot.repository.id == self.selected_repository_id:
                selected_snapshot = snapshot
                break
        if selected_snapshot is None:
            detail.update("Repository not found.")
            hint.update("j/k select another repository.")
            return

        repository = selected_snapshot.repository
        repo_pull_requests = self._filtered_pull_requests_by_repo.get(repository.id, [])
        recent_pull_requests = repo_pull_requests[:4]
        linked_issue_ids = sorted({pull_request.issue_id for pull_request in repo_pull_requests if pull_request.issue_id})
        visibility = "private" if repository.is_private else "public"

        lines = [
            f"{selected_snapshot.label}",
            "",
            f"Visibility: {visibility}",
            f"Default branch: {repository.default_branch or '?'}",
            f"PRs: {selected_snapshot.total_prs} "
            f"(open {selected_snapshot.open_prs} / merged {selected_snapshot.merged_prs} / closed {selected_snapshot.closed_prs})",
            f"Linked Linear issues: {selected_snapshot.linked_prs}",
            f"Checks: {selected_snapshot.checks_total} "
            f"(pass {selected_snapshot.checks_passing} / pending {selected_snapshot.checks_pending} / fail {selected_snapshot.checks_failing})",
        ]
        if repository.url:
            lines.append(f"URL: {repository.url}")
        if linked_issue_ids:
            limit = 5 if self.graph_density == "compact" else 10
            lines.append("")
            lines.append("Linked issues: " + ", ".join(linked_issue_ids[:limit]))
        if recent_pull_requests:
            lines.append("")
            lines.append("Recent PRs:")
            detail_limit = 2 if self.graph_density == "compact" else 4
            for pull_request in recent_pull_requests[:detail_limit]:
                check_count = len(checks_by_pr.get(pull_request.id, []))
                linked = pull_request.issue_id or "-"
                lines.append(
                    f"{self._pr_symbol(pull_request)} #{pull_request.number} "
                    f"{pull_request.title[:28]} [{linked}] c:{check_count}"
                )
        detail.update("\n".join(lines))
        hint.update("Enter open • Esc close • j/k move • PgUp/PgDn page • S/L/C filters • Shift+Y sync")

    def _page_size_for_mode(self) -> int:
        return self._mode_page_size(self.visual_mode)

    def _mode_page_size(self, mode: str) -> int:
        if self.graph_density == "detailed":
            return {"repos": 12, "prs": 14, "checks": 12}.get(mode, 12)
        return {"repos": 7, "prs": 8, "checks": 7}.get(mode, 7)

    def _windowed_rows(self, rows, *, selected_id, row_id, page_size: int):
        total = len(rows)
        if total == 0:
            return [], 0, 0
        if self.graph_density == "detailed":
            return rows, 0, total

        selected_index = 0
        if selected_id is not None:
            for index, row in enumerate(rows):
                if row_id(row) == selected_id:
                    selected_index = index
                    break
        start = (selected_index // page_size) * page_size
        end = min(total, start + page_size)
        return rows[start:end], start, end

    def _repository_label(self, repository: Repository) -> str:
        if repository.organization:
            return f"{repository.organization}/{repository.name}"
        repo_id = repository.id
        if repo_id.startswith("github:"):
            return repo_id.split(":", 1)[1]
        return repository.name or repo_id

    def _selected_repository_label(self) -> str:
        if not self.selected_repository_id:
            return "all repositories"
        for repository in self.app.data_manager.get_repositories():
            if repository.id == self.selected_repository_id:
                return self._repository_label(repository)
        if self.selected_repository_id.startswith("github:"):
            return self.selected_repository_id.split(":", 1)[1]
        return self.selected_repository_id

    def _selected_label(self) -> str:
        if self.visual_mode == "prs":
            pull_request = self.selected_pull_request()
            if pull_request:
                return f"#{pull_request.number}"
            return "none"
        if self.visual_mode == "checks":
            check = self.selected_check()
            if check:
                return check.name
            return "none"
        return self._selected_repository_label()

    def _repository_for_pull_request(self, pull_request: PullRequest) -> Repository:
        for repository in self.app.data_manager.get_repositories():
            if repository.id == pull_request.repository_id:
                return repository
        return self._fallback_repository(pull_request)

    def _fallback_repository(self, pull_request: PullRequest) -> Repository:
        full_name = pull_request.repository_id
        if full_name.startswith("github:"):
            full_name = full_name.split(":", 1)[1]
        organization = None
        name = full_name
        if "/" in full_name:
            organization, name = full_name.split("/", 1)
        return Repository(
            id=pull_request.repository_id,
            provider=pull_request.provider or "github",
            name=name,
            organization=organization,
            default_branch=None,
            is_private=False,
            url=None,
            created_at=None,
            updated_at=pull_request.updated_at,
        )

    def _visible_pull_requests(self) -> list[PullRequest]:
        if self.selected_repository_id and self.selected_repository_id in self._filtered_pull_requests_by_repo:
            return list(self._filtered_pull_requests_by_repo.get(self.selected_repository_id, []))
        return list(self._filtered_pull_requests)

    def _filter_summary_label(self) -> str:
        parts = [
            f"state:{self.state_filter}",
            f"link:{self.link_filter}",
            f"fail:{'on' if self.failing_only else 'off'}",
            f"mine:{'on' if self.mine_only else 'off'}",
            f"blocked:{'on' if self.blocked_only else 'off'}",
            f"stale:{'on' if self.stale_only else 'off'}",
        ]
        if self.drilldown_issue_id:
            parts.append(f"issue:{self.drilldown_issue_id}")
        return "Filters " + " ".join(parts)

    def _pull_request_matches_filters(
        self,
        pull_request: PullRequest,
        checks_by_pr: dict[str, list[CiCheck]],
    ) -> bool:
        state = pull_request.state.casefold()
        if self.state_filter != "all" and state != self.state_filter:
            return False
        has_issue = bool(pull_request.issue_id)
        if self.link_filter == "linked" and not has_issue:
            return False
        if self.link_filter == "unlinked" and has_issue:
            return False
        if self.drilldown_issue_id and pull_request.issue_id != self.drilldown_issue_id:
            return False
        if self.failing_only:
            checks = checks_by_pr.get(pull_request.id, [])
            if not any(self._check_bucket(check) == "failing" for check in checks):
                return False
        if self.mine_only and not self._linked_issue_is_mine(pull_request):
            return False
        if self.blocked_only and not self._linked_issue_is_blocked(pull_request):
            return False
        if self.stale_only and not self._pull_request_is_stale(pull_request):
            return False
        return True

    def _checks_by_pull_request(self, checks: list[CiCheck]) -> dict[str, list[CiCheck]]:
        checks_by_pr: dict[str, list[CiCheck]] = {}
        for check in checks:
            checks_by_pr.setdefault(check.pull_request_id, []).append(check)
        return checks_by_pr

    def _filter_checks(
        self,
        pull_requests: list[PullRequest],
        checks_by_pr: dict[str, list[CiCheck]],
    ) -> list[CiCheck]:
        filtered: list[CiCheck] = []
        for pull_request in pull_requests:
            for check in checks_by_pr.get(pull_request.id, []):
                if self.failing_only and self._check_bucket(check) != "failing":
                    continue
                filtered.append(check)
        filtered.sort(key=lambda check: ((check.updated_at or ""), check.id), reverse=True)
        return filtered

    def _pr_symbol(self, pull_request: PullRequest) -> str:
        state = pull_request.state.casefold()
        if state == "open":
            return "●"
        if state == "merged":
            return "✓"
        if state == "closed":
            return "×"
        return "?"

    def _check_bucket(self, check: CiCheck) -> str:
        status = (check.status or "").casefold()
        if status != "completed":
            return "pending"
        conclusion = (check.conclusion or "").casefold()
        if conclusion in {"success", "neutral", "skipped"}:
            return "passing"
        if conclusion in {
            "failure",
            "cancelled",
            "timed_out",
            "action_required",
            "startup_failure",
            "stale",
        }:
            return "failing"
        if conclusion:
            return "failing"
        return "pending"

    def _check_symbol(self, check: CiCheck) -> str:
        bucket = self._check_bucket(check)
        if bucket == "passing":
            return "✓"
        if bucket == "failing":
            return "×"
        return "●"

    def _check_for_open_action(self) -> CiCheck | None:
        if self.visual_mode == "checks":
            return self.selected_check()

        pull_request = self.selected_pull_request()
        if pull_request is not None:
            checks = self._filtered_checks_by_pr.get(pull_request.id, [])
            if checks:
                failing_checks = [check for check in checks if self._check_bucket(check) == "failing"]
                return failing_checks[0] if failing_checks else checks[0]
            return None

        return self.selected_check()

    def _triage_recommendation_for_check(self, check: CiCheck, pull_request: PullRequest | None) -> str:
        bucket = self._check_bucket(check)
        if bucket == "passing":
            if pull_request and pull_request.issue_id:
                return f"PR healthy. Jump to {pull_request.issue_id} for merge readiness."
            return "PR healthy. Validate review status before merge."
        if bucket == "pending":
            return "Wait for completion, then reopen this check."
        if pull_request and pull_request.issue_id:
            return f"Inspect logs, queue agent run, then update {pull_request.issue_id}."
        return "Inspect logs, queue agent run, and link to a Linear issue."

    @staticmethod
    def _format_timestamp(value: str | None) -> str:
        if not value:
            return "unknown"
        normalized = value.replace("T", " ").replace("Z", "")
        return normalized[:16]

    def _capture_drilldown_restore_state(self) -> dict[str, object]:
        return {
            "state_filter": self.state_filter,
            "link_filter": self.link_filter,
            "failing_only": self.failing_only,
            "mine_only": self.mine_only,
            "blocked_only": self.blocked_only,
            "stale_only": self.stale_only,
            "visual_mode": self.visual_mode,
            "selected_repository_id": self.selected_repository_id,
            "selected_pull_request_id": self.selected_pull_request_id,
            "selected_check_id": self.selected_check_id,
            "detail_open": self.detail_open,
        }

    def _restore_drilldown_state(self) -> None:
        restore = self._drilldown_restore_state
        self.drilldown_issue_id = None
        if restore is None:
            if self.link_filter == "linked":
                self.link_filter = "all"
            self.refresh_view()
            return
        self.state_filter = str(restore.get("state_filter") or "all")
        self.link_filter = str(restore.get("link_filter") or "all")
        self.failing_only = bool(restore.get("failing_only", False))
        self.mine_only = bool(restore.get("mine_only", False))
        self.blocked_only = bool(restore.get("blocked_only", False))
        self.stale_only = bool(restore.get("stale_only", False))
        self.visual_mode = str(restore.get("visual_mode") or "repos")
        self.selected_repository_id = restore.get("selected_repository_id") or None
        self.selected_pull_request_id = restore.get("selected_pull_request_id") or None
        self.selected_check_id = restore.get("selected_check_id") or None
        self.detail_open = bool(restore.get("detail_open", False))
        self._sync_triage_filters_from_flags()
        self._drilldown_restore_state = None
        self.refresh_view()

    def _sync_triage_filters_from_flags(self) -> None:
        active: set[str] = set()
        if self.mine_only:
            active.add("mine")
        if self.blocked_only:
            active.add("blocked")
        if self.failing_only:
            active.add("failing")
        if self.stale_only:
            active.add("stale")
        self.triage_filters = active

    def _linked_issue_is_mine(self, pull_request: PullRequest) -> bool:
        issue = self._linked_issue(pull_request)
        if issue is None or issue.assignee is None:
            return False
        return issue.assignee.name.casefold() in self._my_identity_candidates()

    def _linked_issue_is_blocked(self, pull_request: PullRequest) -> bool:
        issue = self._linked_issue(pull_request)
        if issue is None:
            return False
        return "blocked" in issue.status.casefold()

    def _linked_issue(self, pull_request: PullRequest):
        if not pull_request.issue_id:
            return None
        return self.app.data_manager.get_issue_by_id(pull_request.issue_id)

    def _pull_request_is_stale(self, pull_request: PullRequest) -> bool:
        if pull_request.state.casefold() != "open":
            return False
        stamp = self._parse_timestamp(pull_request.updated_at or pull_request.opened_at)
        if stamp is None:
            return False
        stale_days = self._triage_stale_days()
        return stamp <= datetime.now() - timedelta(days=stale_days)

    def _triage_stale_days(self) -> int:
        raw = os.getenv("PD_TRIAGE_STALE_DAYS", str(self.DEFAULT_TRIAGE_STALE_DAYS)).strip()
        try:
            return max(1, int(raw))
        except ValueError:
            return self.DEFAULT_TRIAGE_STALE_DAYS

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except ValueError:
            return None

    @staticmethod
    def _my_identity_candidates() -> set[str]:
        candidates = {"me"}
        for env_name in ("PD_ME", "GITHUB_USER", "USER", "GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
            value = os.getenv(env_name)
            if value:
                candidates.add(value.strip().casefold())
        return candidates

    def _copy_to_clipboard(self, value: str) -> bool:
        if shutil.which("pbcopy"):
            return self._run_copy_command(["pbcopy"], value)
        if shutil.which("wl-copy"):
            return self._run_copy_command(["wl-copy"], value)
        if shutil.which("xclip"):
            return self._run_copy_command(["xclip", "-selection", "clipboard"], value)
        if shutil.which("xsel"):
            return self._run_copy_command(["xsel", "--clipboard", "--input"], value)
        return False

    def _run_copy_command(self, command: list[str], value: str) -> bool:
        try:
            subprocess.run(command, input=value, text=True, check=True)
            return True
        except Exception:
            return False
