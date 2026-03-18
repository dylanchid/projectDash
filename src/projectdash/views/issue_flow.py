from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import os
import shutil
import subprocess
import webbrowser
import json
import hashlib

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static, Header, Footer

from projectdash.models import ActionRecord, AgentRun, CiCheck, Issue, PullRequest
from projectdash.views.modals import ConfirmationScreen


@dataclass(frozen=True)
class FlowEntry:
    kind: str
    label: str
    timestamp: str | None
    sort_key: datetime | None
    issue_id: str | None = None
    pr_id: str | None = None
    check_id: str | None = None
    run_id: str | None = None
    action_id: str | None = None


class IssueFlowScreen(Screen):
    DEFAULT_TRIAGE_STALE_DAYS = 7
    BINDINGS = [
        ("j", "move_down", "Down"),
        ("k", "move_up", "Up"),
        ("enter", "open_detail", "Open Detail"),
        ("escape", "close_screen", "Close"),
        ("/", "open_filter", "Filter/Search"),
        ("question_mark", "toggle_help", "Help"),
        ("q", "close_screen", "Close"),
        ("o", "open_pr", "Open PR"),
        ("b", "copy_branch", "Copy Branch"),
        ("i", "open_issue", "Open Issue"),
        ("c", "open_check", "Open Check"),
        ("a", "run_agent", "Run Agent"),
        ("l", "view_logs", "View Logs"),
    ]

    def __init__(self, issue_id: str) -> None:
        super().__init__()
        self.issue_id = issue_id
        self.detail_open = True
        self.selected_index = 0
        self._entries: list[FlowEntry] = []
        self._issue: Issue | None = None
        self._prs_by_id: dict[str, PullRequest] = {}
        self._checks_by_id: dict[str, CiCheck] = {}
        self._agent_runs: list[AgentRun] = []
        self._actions: list[ActionRecord] = []

    def compose(self) -> ComposeResult:
        yield Static("ISSUE FLOW", id="issue-flow-header")
        yield Static("SUMMARY", classes="section-label")
        yield Static("", id="issue-flow-summary", classes="placeholder-text")
        with Horizontal(id="issue-flow-layout"):
            with Vertical(id="issue-flow-main"):
                yield Static("TIMELINE", classes="section-label")
                yield Static("", id="issue-flow-list", classes="placeholder-text")
            with Vertical(id="issue-flow-sidebar", classes="detail-sidebar"):
                yield Static("DETAIL", classes="detail-sidebar-title")
                yield Static("", id="issue-flow-detail")
                yield Static("", id="issue-flow-hint", classes="detail-sidebar-hint")

    def on_mount(self) -> None:
        self.refresh_view()
        self.app.run_worker(self._load_async_data(), exclusive=False)

    async def _load_async_data(self) -> None:
        await self._load_agent_runs()
        await self._load_actions()
        self.refresh_view()

    async def _load_agent_runs(self) -> None:
        try:
            runs = await self.app.data_manager.get_agent_runs(limit=200)
        except Exception:
            runs = []
        self._agent_runs = [
            run
            for run in runs
            if (run.issue_id and run.issue_id == self.issue_id) or run.pr_id in self._prs_by_id
        ]

    async def _load_actions(self) -> None:
        try:
            actions = await self.app.data_manager.get_action_history(limit=200)
        except Exception:
            actions = []
        
        pr_ids = set(self._prs_by_id.keys())
        self._actions = [
            action
            for action in actions
            if action.target_id == self.issue_id 
            or action.target_id in pr_ids
            or any(check.id == action.target_id for check in self._checks_by_id.values())
        ]

    def refresh_view(self) -> None:
        self._issue = self.app.data_manager.get_issue_by_id(self.issue_id)
        pull_requests = self.app.data_manager.get_pull_requests(self.issue_id)
        checks = self.app.data_manager.get_ci_checks()

        self._prs_by_id = {pr.id: pr for pr in pull_requests}
        self._checks_by_id = {check.id: check for check in checks}
        checks_by_pr = self._checks_by_pr(checks)

        self._entries = self._build_entries(
            issue=self._issue,
            pull_requests=pull_requests,
            checks_by_pr=checks_by_pr,
            agent_runs=self._agent_runs,
            actions=self._actions,
        )
        self.selected_index = max(0, min(self.selected_index, len(self._entries) - 1))

        self._refresh_summary(pull_requests, checks_by_pr)
        self._refresh_timeline()
        self._refresh_detail(pull_requests, checks_by_pr)

    def action_move_down(self) -> None:
        if not self._entries:
            return
        self.selected_index = (self.selected_index + 1) % len(self._entries)
        self._refresh_detail(self.app.data_manager.get_pull_requests(self.issue_id), self._checks_by_pr(self.app.data_manager.get_ci_checks()))
        self._refresh_timeline()

    def action_move_up(self) -> None:
        if not self._entries:
            return
        self.selected_index = (self.selected_index - 1) % len(self._entries)
        self._refresh_detail(self.app.data_manager.get_pull_requests(self.issue_id), self._checks_by_pr(self.app.data_manager.get_ci_checks()))
        self._refresh_timeline()

    def action_open_detail(self) -> None:
        self.detail_open = True
        self._refresh_detail(self.app.data_manager.get_pull_requests(self.issue_id), self._checks_by_pr(self.app.data_manager.get_ci_checks()))

    def action_close_screen(self) -> None:
        if self.detail_open:
            self.detail_open = False
            self._refresh_detail(
                self.app.data_manager.get_pull_requests(self.issue_id),
                self._checks_by_pr(self.app.data_manager.get_ci_checks()),
            )
            return
        self.dismiss(
            {
                "issue_id": self.issue_id,
                "selected_index": self.selected_index,
            }
        )

    def action_open_filter(self) -> None:
        if hasattr(self.app, "action_open_filter"):
            self.app.action_open_filter()

    def action_toggle_help(self) -> None:
        if hasattr(self.app, "action_toggle_help_overlay"):
            self.app.action_toggle_help_overlay()

    def action_open_issue(self) -> None:
        if self._issue is None:
            self._publish(False, "Issue not found")
            return
        url = self._linear_issue_url(self._issue)
        if self._open_url(url, "Issue"):
            self._publish(True, f"Opened {self._issue.id} in Linear")

    def action_open_pr(self) -> None:
        pr = self._selected_pull_request()
        if pr is None:
            self._publish(False, "No pull request selected")
            return
        if not pr.url:
            self._publish(False, f"No URL for PR #{pr.number}")
            return
        if self._open_url(pr.url, f"PR #{pr.number}"):
            self._publish(True, f"Opened PR #{pr.number}")

    def action_copy_branch(self) -> None:
        pr = self._selected_pull_request()
        if pr is None:
            self._publish(False, "No pull request selected")
            return
        branch = (pr.head_branch or "").strip()
        if not branch:
            self._publish(False, f"No head branch available for PR #{pr.number}")
            return
        if self._copy_to_clipboard(branch):
            self._publish(True, f"Copied branch: {branch}")
            return
        self._publish(False, f"No clipboard tool found. Branch: {branch}")

    def action_open_check(self) -> None:
        entry = self._selected_entry()
        check = None
        if entry and entry.check_id:
            check = self._checks_by_id.get(entry.check_id)
        if check is None:
            failing = self._failing_checks_for_selected_pr()
            check = failing[0] if failing else None
        if check is None:
            self._publish(False, "No check selected")
            return
        if not check.url:
            self._publish(False, f"No URL for check {check.name}")
            return
        if self._open_url(check.url, f"Check {check.name}"):
            self._publish(True, f"Opened check {check.name}")

    def action_view_logs(self) -> None:
        entry = self._selected_entry()
        run = None
        if entry and entry.run_id:
            run = next((candidate for candidate in self._agent_runs if candidate.id == entry.run_id), None)
        
        if run is None:
            # Fallback to most recent run for selected PR
            pr = self._selected_pull_request()
            if pr:
                run = next((r for r in self._agent_runs if r.pr_id == pr.id), None)

        if run is None:
            self._publish(False, "No agent run selected or found for this context.")
            return

        logs = run.trace_logs
        if not logs:
            # Fallback: try to read from disk if not in DB
            log_path = run.artifacts.get("log_path") if run.artifacts else None
            if log_path:
                try:
                    path = Path(log_path)
                    if path.exists():
                        logs = path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

        if not logs:
            self._publish(False, f"No logs recorded for run {run.id}")
            return

        self.app.push_screen(LogViewScreen(run.id, logs))

    async def action_run_agent(self) -> None:
        pr = self._selected_pull_request()
        if pr is None:
            self._publish(False, "No pull request selected")
            return
        
        # Guardrail: validate command env var
        command_template = os.getenv("PD_AGENT_RUN_CMD", "").strip()
        if not command_template:
            await self.app.data_manager.record_action(
                action_type="agent_launch_attempt",
                target_id=pr.id,
                status="failed",
                message="PD_AGENT_RUN_CMD not set in environment",
                payload={"pr_number": pr.number, "issue_id": pr.issue_id},
            )
            self._publish(False, "Agent command (PD_AGENT_RUN_CMD) not configured in environment.")
            return

        async def do_run():
            issue = self._issue
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            actor_id = self.app.data_manager.current_user_id()
            run = AgentRun(
                id=f"flowrun-{datetime.now().strftime('%H%M%S')}-{os.urandom(3).hex()}",
                runtime="issue-flow",
                status="queued",
                started_at=timestamp,
                actor_id=actor_id,
                issue_id=pr.issue_id,
                project_id=issue.project_id if issue else None,
                branch_name=pr.head_branch,
                pr_id=pr.id,
                prompt_text=f"Review and advance PR #{pr.number}: {pr.title}",
                prompt_fingerprint=hashlib.sha1(f"Review and advance PR #{pr.number}: {pr.title}".encode("utf-8")).hexdigest()[:8],
                artifacts={
                    "source": "issue_flow",
                    "repository_id": pr.repository_id,
                    "pull_request_number": pr.number,
                    "pull_request_url": pr.url,
                    "issue_id": pr.issue_id,
                    "head_branch": pr.head_branch,
                    "base_branch": pr.base_branch,
                },
            )
            try:
                # Audit log the attempt
                await self.app.data_manager.record_action(
                    action_type="agent_launch_attempt",
                    target_id=pr.id,
                    status="success",
                    message=f"Agent launch initiated by {actor_id}",
                    payload={
                        "pr_number": pr.number,
                        "issue_id": pr.issue_id,
                        "prompt": run.prompt_text,
                    },
                )
                await self.app.data_manager.record_agent_run(run)
                await self.app.data_manager.record_action(
                    action_type="agent_launch",
                    target_id=run.id,
                    status="success",
                    message=f"Agent record created for {run.id}",
                    payload={
                        "issue_id": pr.issue_id,
                        "pr_number": pr.number,
                    },
                )
            except Exception as error:
                self._publish(False, f"Failed to record agent run: {error}")
                return
            self._agent_runs.insert(0, run)
            dispatched, dispatch_message = await self.app.data_manager.dispatch_agent_run(run)
            self.refresh_view()
            if dispatched:
                self._publish(True, f"Queued and dispatched agent run {run.id} ({dispatch_message})")
                return
            self._publish(True, f"Queued agent run {run.id} ({dispatch_message})")

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                self.app.run_worker(do_run(), exclusive=False)

        self.app.push_screen(
            ConfirmationScreen(
                f"Launch agent for PR #{pr.number}?\n\nThis will trigger: Review and advance PR #{pr.number}",
                title="Run Agent"
            ),
            on_confirm
        )

    def _refresh_summary(self, pull_requests: list[PullRequest], checks_by_pr: dict[str, list[CiCheck]]) -> None:
        summary = self.query_one("#issue-flow-summary", Static)
        if self._issue is None:
            summary.update("Issue not found.")
            return
        assignee = self._issue.assignee.name if self._issue.assignee else "Unassigned"
        pr_count = len(pull_requests)
        check_count = sum(len(checks_by_pr.get(pr.id, [])) for pr in pull_requests)
        failing_checks = sum(
            1 for checks in checks_by_pr.values() for check in checks if self._check_bucket(check) == "failing"
        )
        review_ready = 0
        review_attention = 0
        for pr in pull_requests:
            checks = checks_by_pr.get(pr.id, [])
            review_status = self._review_status_for_pr(pr, checks)
            if review_status in {"ready", "merged"}:
                review_ready += 1
            else:
                review_attention += 1
        health = self._pull_request_health_counts(pull_requests, checks_by_pr)
        readiness = self._issue.readiness_score()
        summary.update(
            f"{self._issue.id} · {self._issue.status}\n"
            f"{self._issue.title}\n\n"
            f"Assignee: {assignee}\n"
            f"Priority: {self._issue.priority}  Points: {self._issue.points}\n"
            f"Readiness Score: {readiness}/100\n"
            f"Linked PRs: {pr_count}  Checks: {check_count} (fail {failing_checks})\n"
            f"PR states: open {health['open']}  merged {health['merged']}  closed {health['closed']}\n"
            f"Review: ready/merged {review_ready}  attention {review_attention}\n"
            f"Risk: failing PRs {health['failing_prs']}  stale reviews {health['stale_reviews']}"
        )

    def _refresh_timeline(self) -> None:
        timeline = self.query_one("#issue-flow-list", Static)
        if not self._entries:
            timeline.update("No linked GitHub activity for this issue yet.")
            return
        lines = []
        for idx, entry in enumerate(self._entries):
            marker = ">" if idx == self.selected_index else " "
            timestamp = self._format_timestamp(entry.timestamp)
            lines.append(f"{marker} {timestamp:<16} {entry.label}")
        timeline.update("\n".join(lines))

    def _refresh_detail(
        self,
        pull_requests: list[PullRequest],
        checks_by_pr: dict[str, list[CiCheck]],
    ) -> None:
        detail = self.query_one("#issue-flow-detail", Static)
        hint = self.query_one("#issue-flow-hint", Static)
        entry = self._selected_entry()
        if self._issue is None:
            detail.update("Issue not found.")
            hint.update("Esc to close")
            return

        if entry is None:
            detail.update("No timeline entries yet.")
            hint.update("Esc to close")
            return

        if not self.detail_open:
            detail.update(
                f"{entry.label}\n"
                f"{self._format_timestamp(entry.timestamp)}\n\n"
                "Press Enter for detail."
            )
            hint.update("Enter open detail • Esc close • j/k move")
            return

        if entry.kind == "issue":
            selected_pr = self._selected_pull_request()
            pr_action_text = "No linked PR actions available"
            if selected_pr is not None:
                pr_action_text = (
                    f"Default PR: #{selected_pr.number}  "
                    "[o] Open PR  [b] Copy branch  [c] Open failing check  [a] Run agent"
                )
            detail.update(
                f"{self._issue.id} · {self._issue.status}\n"
                f"{self._issue.title}\n\n"
                f"Priority: {self._issue.priority}\n"
                f"Points: {self._issue.points}\n"
                f"Due: {self._issue.due_date or 'N/A'}\n"
                f"Created: {self._issue.created_at.strftime('%Y-%m-%d') if self._issue.created_at else 'N/A'}\n"
                f"Linear: {self._linear_issue_url(self._issue)}\n\n"
                "ACTIONS\n"
                "[i] Open issue in Linear\n"
                f"{pr_action_text}"
            )
            hint.update("j/k move • i/o/b/c/a actions • Esc close")
            return

        if entry.kind == "pr":
            pr = self._prs_by_id.get(entry.pr_id or "")
            if pr is None:
                detail.update("Pull request not found.")
                hint.update("Esc close")
                return
            checks = checks_by_pr.get(pr.id, [])
            passing = sum(1 for check in checks if self._check_bucket(check) == "passing")
            pending = sum(1 for check in checks if self._check_bucket(check) == "pending")
            failing = sum(1 for check in checks if self._check_bucket(check) == "failing")
            failing_names = ", ".join(check.name for check in checks if self._check_bucket(check) == "failing") or "-"
            review_status = self._review_status_for_pr(pr, checks)
            health_label = self._pr_health_label(pr, checks)
            detail.update(
                f"PR #{pr.number} [{pr.state}]\n"
                f"{pr.title}\n\n"
                f"Branch: {pr.head_branch or '?'} -> {pr.base_branch or '?'}\n"
                f"Updated: {pr.updated_at or '-'}\n"
                f"Linked issue: {pr.issue_id or 'unlinked'}\n"
                f"Checks: {len(checks)} | pass {passing} | pend {pending} | fail {failing}\n"
                f"Health: {health_label}\n"
                f"Review status: {review_status}\n"
                f"Failing: {failing_names}\n\n"
                "ACTIONS\n"
                "[o] Open PR  [b] Copy branch\n"
                "[c] Open failing check  [a] Run agent"
            )
            hint.update("j/k move • o/b/c/a actions • Esc close")
            return

        if entry.kind == "check":
            check = self._checks_by_id.get(entry.check_id or "")
            if check is None:
                detail.update("Check not found.")
                hint.update("Esc close")
                return
            detail.update(
                f"{check.name}\n"
                f"Status: {check.status}  Conclusion: {check.conclusion or '-'}\n"
                f"Updated: {check.updated_at or '-'}\n"
                f"URL: {check.url or '-'}\n\n"
                "ACTIONS\n"
                "[c] Open check URL"
            )
            hint.update("j/k move • c open check • Esc close")
            return

        if entry.kind == "agent":
            run = next((candidate for candidate in self._agent_runs if candidate.id == entry.run_id), None)
            if run is None:
                detail.update("Agent run not found.")
                hint.update("Esc close")
                return
            
            pr_label = "none"
            if run.pr_id:
                pr = self._prs_by_id.get(run.pr_id)
                pr_label = f"#{pr.number} ({pr.state})" if pr else f"ID: {run.pr_id}"

            duration = "-"
            if run.started_at and run.finished_at:
                try:
                    s = self._parse_timestamp(run.started_at)
                    f = self._parse_timestamp(run.finished_at)
                    if s and f:
                        duration = str(f - s).split(".")[0]
                except Exception:
                    pass

            detail.update(
                f"AGENT RUN {run.id}\n\n"
                f"Status:    {run.status.upper()}\n"
                f"Actor:     {run.actor_id or 'unknown'}\n"
                f"Runtime:   {run.runtime}\n"
                f"PR Linked: {pr_label}\n"
                f"Fingerprint: {run.prompt_fingerprint or 'none'}\n\n"
                f"TIMING\n"
                f"Started:   {run.started_at}\n"
                f"Finished:  {run.finished_at or 'in progress'}\n"
                f"Duration:  {duration}\n\n"
                f"PROMPT\n"
                f"{run.prompt_text or 'No prompt recorded.'}\n\n"
                "ACTIONS\n"
                "[o] Open PR  [b] Copy branch\n"
                "[c] Open failing check  [a] Run agent\n"
                "[i] Open linked issue  [l] View Logs"
            )
            hint.update("j/k move • o/b/c/a/i/l actions • Esc close")
            return

        if entry.kind == "action":
            action = next((candidate for candidate in self._actions if candidate.id == entry.action_id), None)
            if action is None:
                detail.update("Action record not found.")
                hint.update("Esc close")
                return
            detail.update(
                f"TUI Action: {action.action_type}\n"
                f"Status: {action.status}\n"
                f"Target: {action.target_id}\n"
                f"Time: {action.timestamp}\n"
                f"Message: {action.message or '-'}\n"
                f"Payload: {json.dumps(action.payload) if action.payload else '-'}"
            )
            hint.update("j/k move • Esc close")
            return

        detail.update(entry.label)
        hint.update("Esc close")

    def _selected_entry(self) -> FlowEntry | None:
        if not self._entries:
            return None
        return self._entries[self.selected_index]

    def _selected_pull_request(self) -> PullRequest | None:
        entry = self._selected_entry()
        if entry and entry.pr_id:
            return self._prs_by_id.get(entry.pr_id)
        if entry and entry.kind == "agent" and entry.run_id:
            run = next((candidate for candidate in self._agent_runs if candidate.id == entry.run_id), None)
            if run and run.pr_id:
                return self._prs_by_id.get(run.pr_id)
        return next(iter(self._prs_by_id.values()), None)

    def _failing_checks_for_selected_pr(self) -> list[CiCheck]:
        pr = self._selected_pull_request()
        if pr is None:
            return []
        checks = [check for check in self._checks_by_id.values() if check.pull_request_id == pr.id]
        return [check for check in checks if self._check_bucket(check) == "failing"]

    def _build_entries(
        self,
        *,
        issue: Issue | None,
        pull_requests: list[PullRequest],
        checks_by_pr: dict[str, list[CiCheck]],
        agent_runs: list[AgentRun],
        actions: list[ActionRecord],
    ) -> list[FlowEntry]:
        entries: list[FlowEntry] = []
        if issue:
            entries.append(
                FlowEntry(
                    kind="issue",
                    label=f"Issue created ({issue.status})",
                    timestamp=issue.created_at.isoformat(sep=" ", timespec="minutes"),
                    sort_key=issue.created_at,
                    issue_id=issue.id,
                )
            )

        for pr in pull_requests:
            stamp = pr.updated_at or pr.opened_at or pr.merged_at or pr.closed_at
            entries.append(
                FlowEntry(
                    kind="pr",
                    label=f"PR #{pr.number} [{pr.state}] {pr.title}",
                    timestamp=stamp,
                    sort_key=self._parse_timestamp(stamp),
                    issue_id=pr.issue_id,
                    pr_id=pr.id,
                )
            )

            for check in checks_by_pr.get(pr.id, []):
                label_state = check.conclusion or check.status
                entries.append(
                    FlowEntry(
                        kind="check",
                        label=f"Check {check.name} ({label_state})",
                        timestamp=check.updated_at or check.completed_at or check.started_at,
                        sort_key=self._parse_timestamp(check.updated_at or check.completed_at or check.started_at),
                        pr_id=pr.id,
                        check_id=check.id,
                    )
                )

        for run in agent_runs:
            status_icon = self._agent_status_icon(run.status)
            entries.append(
                FlowEntry(
                    kind="agent",
                    label=f"Agent: {status_icon} {run.status} ({run.id})",
                    timestamp=run.started_at,
                    sort_key=self._parse_timestamp(run.started_at),
                    issue_id=run.issue_id,
                    pr_id=run.pr_id,
                    run_id=run.id,
                )
            )

        for action in actions:
            entries.append(
                FlowEntry(
                    kind="action",
                    label=f"TUI: {action.action_type} ({action.status})",
                    timestamp=action.timestamp,
                    sort_key=self._parse_timestamp(action.timestamp),
                    action_id=action.id,
                )
            )

        with_time = [entry for entry in entries if entry.sort_key is not None]
        without_time = [entry for entry in entries if entry.sort_key is None]
        with_time.sort(key=lambda entry: entry.sort_key, reverse=True)
        return with_time + without_time

    @staticmethod
    def _agent_status_icon(status: str) -> str:
        s = status.lower()
        if s == "queued":
            return "⏳"
        if s == "running":
            return "⚙️"
        if s == "completed":
            return "✅"
        if s == "failed":
            return "❌"
        return "❓"

    @staticmethod
    def _checks_by_pr(checks: list[CiCheck]) -> dict[str, list[CiCheck]]:
        checks_by_pr: dict[str, list[CiCheck]] = {}
        for check in checks:
            checks_by_pr.setdefault(check.pull_request_id, []).append(check)
        return checks_by_pr

    @staticmethod
    def _format_timestamp(timestamp: str | None) -> str:
        if not timestamp:
            return "unknown"
        value = timestamp.replace("T", " ").replace("Z", "")
        return value[:16]

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
            try:
                parsed = datetime.fromisoformat(normalized.replace(" ", "T"))
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone().replace(tzinfo=None)
                return parsed
            except ValueError:
                return None

    @staticmethod
    def _check_bucket(check: CiCheck) -> str:
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

    def _review_status_for_pr(self, pull_request: PullRequest, checks: list[CiCheck]) -> str:
        if pull_request.state.casefold() == "merged" or pull_request.merged_at:
            return "merged"
        failing = any(self._check_bucket(check) == "failing" for check in checks)
        pending = any(self._check_bucket(check) == "pending" for check in checks)
        if failing:
            return "changes-required"
        if pending:
            return "awaiting-checks"
        if checks:
            return "ready"
        return "needs-ci"

    def _pull_request_health_counts(
        self,
        pull_requests: list[PullRequest],
        checks_by_pr: dict[str, list[CiCheck]],
    ) -> dict[str, int]:
        counts = {
            "open": 0,
            "merged": 0,
            "closed": 0,
            "failing_prs": 0,
            "stale_reviews": 0,
        }
        for pull_request in pull_requests:
            state = (pull_request.state or "").casefold()
            if state == "merged" or pull_request.merged_at:
                counts["merged"] += 1
            elif state == "closed":
                counts["closed"] += 1
            else:
                counts["open"] += 1
            checks = checks_by_pr.get(pull_request.id, [])
            if any(self._check_bucket(check) == "failing" for check in checks):
                counts["failing_prs"] += 1
            if self._pull_request_is_stale(pull_request):
                counts["stale_reviews"] += 1
        return counts

    def _pull_request_is_stale(self, pull_request: PullRequest) -> bool:
        state = (pull_request.state or "").casefold()
        if state != "open":
            return False
        stamp = self._parse_timestamp(pull_request.updated_at or pull_request.opened_at)
        if stamp is None:
            return False
        return stamp <= datetime.now() - timedelta(days=self._triage_stale_days())

    def _triage_stale_days(self) -> int:
        raw = os.getenv("PD_TRIAGE_STALE_DAYS", str(self.DEFAULT_TRIAGE_STALE_DAYS)).strip()
        try:
            return max(1, int(raw))
        except ValueError:
            return self.DEFAULT_TRIAGE_STALE_DAYS

    def _pr_health_label(self, pull_request: PullRequest, checks: list[CiCheck]) -> str:
        review_status = self._review_status_for_pr(pull_request, checks)
        if review_status == "merged":
            return "merged"
        if review_status == "changes-required":
            return "failing checks"
        if review_status == "awaiting-checks":
            return "checks running"
        if review_status == "ready":
            return "green"
        return "no checks"

    def _linear_issue_url(self, issue: Issue) -> str:
        workspace = os.getenv("PD_LINEAR_WORKSPACE", "").strip().strip("/")
        if not workspace:
            workspace = self._issue_team_key(issue)
        if workspace:
            return f"https://linear.app/{workspace}/issue/{issue.id}"
        return f"https://linear.app/issue/{issue.id}"

    def _issue_team_key(self, issue: Issue) -> str:
        team_id = issue.team_id or ""
        if not team_id:
            return ""
        try:
            states = self.app.data_manager.workflow_states_by_team.get(team_id, [])
        except Exception:
            return ""
        for state in states:
            if state.team_key:
                return state.team_key
        return ""

    def _open_url(self, url: str, label: str) -> bool:
        try:
            return webbrowser.open_new_tab(url)
        except Exception as error:
            self._publish(False, f"Failed to open {label}: {error}")
            return False

    @staticmethod
    def _copy_to_clipboard(value: str) -> bool:
        if shutil.which("pbcopy"):
            return IssueFlowScreen._run_copy_command(["pbcopy"], value)
        if shutil.which("wl-copy"):
            return IssueFlowScreen._run_copy_command(["wl-copy"], value)
        if shutil.which("xclip"):
            return IssueFlowScreen._run_copy_command(["xclip", "-selection", "clipboard"], value)
        if shutil.which("xsel"):
            return IssueFlowScreen._run_copy_command(["xsel", "--clipboard", "--input"], value)
        return False

    @staticmethod
    def _run_copy_command(command: list[str], value: str) -> bool:
        try:
            subprocess.run(command, input=value, text=True, check=True)
            return True
        except Exception:
            return False

    def _publish(self, ok: bool, message: str) -> None:
        try:
            self.app._publish_action_result(ok, message)
        except Exception:
            self.app.update_app_status(message)


class LogViewScreen(Screen):
    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
    ]

    def __init__(self, run_id: str, logs: str) -> None:
        super().__init__()
        self.run_id = run_id
        self.logs = logs

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"TRACE LOGS: {self.run_id}", id="log-header")
        with Vertical(id="log-scroll-container"):
            yield Static(self.logs, id="log-content", expand=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#log-content").styles.height = "auto"
        self.query_one("#log-content").styles.width = "auto"
        self.query_one("#log-scroll-container").styles.overflow_y = "scroll"
        self.query_one("#log-scroll-container").styles.overflow_x = "auto"
        self.query_one("#log-scroll-container").styles.background = "#1a1a1a"
        self.query_one("#log-content").styles.color = "#cccccc"
        self.query_one("#log-content").styles.padding = (1, 2)
        self.query_one("#log-header").styles.background = "#2a2a2a"
        self.query_one("#log-header").styles.padding = (0, 1)
        self.query_one("#log-header").styles.text_style = "bold"
