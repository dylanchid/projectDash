from __future__ import annotations

from typing import Any, List
from projectdash.models import AgentRun, CiCheck, LocalProject, PullRequest, Repository, Project, Issue, User, LinearWorkflowState
from projectdash.database import Database
from projectdash.connectors import GitHubConnector, LinearConnector
from projectdash.github import GitHubApiError, GitHubClient
from projectdash.linear import LinearClient
from projectdash.config import AppConfig
from projectdash.services.github_query_service import GitHubQueryService
from projectdash.services.github_mutation_service import GitHubMutationService
from projectdash.services.issue_mutation_service import IssueMutationService
from projectdash.services.issue_service import IssueService
from projectdash.services.sync_service import SyncService
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from projectdash.enums import AgentRunStatus, ConnectorFreshness, SyncResult

class DataManager:
    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig.from_env()
        self.db = Database()
        self.linear = LinearClient()
        self.github = GitHubClient()
        self.linear_connector = LinearConnector()
        self.github_connector = GitHubConnector()
        self.connectors = {
            self.github_connector.name: self.github_connector,
            self.linear_connector.name: self.linear_connector,
        }
        self.users: List[User] = []
        self.projects: List[Project] = []
        self.issues: List[Issue] = []
        self.repositories: List[Repository] = []
        self.pull_requests: List[PullRequest] = []
        self.ci_checks: List[CiCheck] = []
        self.local_projects: list[LocalProject] = []
        self.workflow_states_by_team: dict[str, list[LinearWorkflowState]] = {}
        self.is_initialized = False
        self.sync_in_progress = False
        self.last_sync_at: str | None = None
        self.last_sync_error: str | None = None
        self.last_sync_result: str = SyncResult.IDLE
        self.sync_diagnostics: dict[str, str] = {}
        self.last_sync_counts: dict[str, int] = {}
        self.sync_history: list[dict[str, Any]] = []
        self.sync_stale_minutes = SyncService.sync_stale_threshold_minutes()
        self._connector_freshness: dict[str, dict[str, str | None]] = {
            "linear": {
                "status": ConnectorFreshness.IDLE,
                "last_success_at": None,
                "last_attempt_at": None,
                "last_error": None,
            },
            "github": {
                "status": ConnectorFreshness.IDLE,
                "last_success_at": None,
                "last_attempt_at": None,
                "last_error": None,
            },
        }
        self.sync_service = SyncService(self)
        self.issue_service = IssueService(self)
        self.issue_mutation_service = IssueMutationService(self)
        self.github_query_service = GitHubQueryService(self)
        self.github_mutation_service = GitHubMutationService(self)

    async def initialize(self):
        """Initializes the database and loads initial data from cache."""
        await self.db.init_db()
        await self.load_from_cache()
        self.is_initialized = True
        
        # Seed mock data only when explicitly enabled for local/dev flows.
        if not self.users and self.config.seed_mock_data:
            await self.seed_mock_data()
            await self.load_from_cache()

    async def seed_mock_data(self):
        """Seeds the database with initial mock data."""
        mock_users = [
            User("1", "Bob"),
            User("2", "Alice"),
            User("3", "Dave"),
            User("4", "Sarah"),
            User("5", "Me"),
        ]
        
        mock_projects = [
            Project(
                "1",
                "Acme Corp",
                "Synced",
                12,
                5,
                2,
                "2024-02-28",
                "Jan Q1",
                "2024-01-15",
                "Customer onboarding delivery for enterprise accounts.",
            ),
            Project(
                "2",
                "DevTools",
                "Synced",
                8,
                3,
                0,
                "2024-03-15",
                "Feb Q1",
                "2024-01-28",
                "Internal developer productivity upgrades and platform hardening.",
            ),
            Project(
                "3",
                "Web Redesign",
                "Synced",
                7,
                2,
                1,
                "2024-03-30",
                "Design",
                "2024-02-04",
                "Cross-functional redesign for marketing and account surfaces.",
            ),
        ]
        
        mock_issues = [
            Issue("PROJ-245", "Fix Login Bug", "High", "In Progress", mock_users[1], 5, "1", "2024-02-24"),
            Issue("PROJ-234", "UI Fix", "Medium", "In Progress", mock_users[1], 3, "1", "2024-02-25"),
            Issue("PROJ-251", "CSS Bug", "Low", "Todo", mock_users[1], 2, "1", "2024-02-26"),
            Issue("PROJ-234-B", "Backend Sync", "High", "In Progress", mock_users[0], 5, "1", "2024-02-27"),
            Issue("PROJ-246", "Schema Update", "Medium", "Todo", mock_users[0], 2, "2", "2024-03-05"),
            Issue("PROJ-251-B", "API Refactor", "Medium", "In Progress", mock_users[2], 3, "2", "2024-03-07"),
            Issue("PROJ-243", "Write Tests", "Low", "Review", mock_users[2], 2, "2", "2024-03-09"),
            Issue("PROJ-246-B", "DB Setup", "Low", "Done", mock_users[3], 3, "2", "2024-03-12"),
            Issue("PROJ-250", "Migration", "Medium", "Todo", mock_users[3], 2, "3", "2024-03-16"),
            Issue("PROJ-244", "Doc Update", "Low", "Review", mock_users[3], 2, "3", "2024-03-18"),
            Issue("PROJ-245-B", "Core Refactor", "High", "In Progress", mock_users[4], 5, "3", "2024-03-19"),
            Issue("PROJ-235", "Plugin System", "Medium", "Todo", mock_users[4], 3, "3", "2024-03-21"),
            Issue("PROJ-233", "Fast Sync", "High", "Todo", mock_users[4], 2, "3", "2024-03-23"),
        ]
        
        await self.db.save_users(mock_users)
        await self.db.save_projects(mock_projects)
        await self.db.save_issues(mock_issues)

    async def load_from_cache(self):
        """Loads data from the local SQLite cache."""
        self.users = await self.db.get_users()
        self.projects = await self.db.get_projects()
        self.issues = await self.db.get_issues()
        self.repositories = await self.db.get_repositories()
        self.pull_requests = await self.db.get_pull_requests(limit=5000)
        self.ci_checks = await self.db.get_ci_checks(limit=10000)
        workflow_states = await self.db.get_workflow_states()
        workflow_states_by_team: dict[str, list[LinearWorkflowState]] = {}
        for state in workflow_states:
            workflow_states_by_team.setdefault(state.team_id, []).append(state)
        self.workflow_states_by_team = workflow_states_by_team
        self.sync_history = await self.db.get_sync_history()
        self.local_projects = await self.db.get_local_projects()

    async def sync_with_linear(self):
        """Fetches latest data from Linear and updates the cache."""
        await self.sync_service.sync_with_linear()

    async def sync_with_github(self):
        """Fetches latest GitHub repository/PR/check data and updates the cache."""
        await self.sync_service.sync_with_github()

    def sync_status_summary(self) -> str:
        return self.sync_service.sync_status_summary()

    def sync_diagnostic_lines(self) -> list[str]:
        return self.sync_service.sync_diagnostic_lines()

    def get_sync_history(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.sync_service.get_sync_history(limit=limit)

    def available_connectors(self) -> list[str]:
        return self.sync_service.available_connectors()

    async def save_sync_cursor(self, provider: str, cursor: str | None) -> None:
        await self.sync_service.save_sync_cursor(provider, cursor)

    async def get_sync_cursor(self, provider: str) -> str | None:
        return await self.sync_service.get_sync_cursor(provider)

    async def record_agent_run(self, run: AgentRun) -> None:
        await self.db.save_agent_run(run)

    async def record_action(
        self,
        action_type: str,
        target_id: str,
        status: str,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        from uuid import uuid4
        from projectdash.models import ActionRecord
        action = ActionRecord(
            id=f"act-{uuid4().hex[:12]}",
            action_type=action_type,
            target_id=target_id,
            status=status,
            message=message,
            payload=payload or {},
        )
        await self.db.save_actions([action])

    async def get_action_history(self, limit: int = 50) -> list[ActionRecord]:
        return await self.db.get_action_history(limit)

    def get_local_projects(self) -> list[LocalProject]:
        return self.local_projects

    async def scan_portfolio(self) -> None:
        root_str = self.config.portfolio_root
        if not root_str:
            return
        root = Path(root_str).expanduser()
        if not root.is_dir():
            return
        from projectdash.services.portfolio_scanner import PortfolioScanner

        scanner = PortfolioScanner()
        scanned = scanner.scan_root(root)
        manifest_path = self._resolved_manifest_path()
        manifest = scanner.load_manifest(manifest_path)
        merged = scanner.apply_manifest(scanned, manifest)
        await self.db.save_local_projects(merged)
        self.local_projects = await self.db.get_local_projects()

    async def update_local_project_field(
        self, project_id: str, field_name: str, value: str
    ) -> tuple[bool, str]:
        target = None
        for p in self.local_projects:
            if p.id == project_id:
                target = p
                break
        if target is None:
            return False, f"Project not found: {project_id}"
        if field_name not in ("status", "tier", "type"):
            return False, f"Cannot edit field: {field_name}"
        setattr(target, field_name, value)
        await self.db.save_local_projects([target])
        from projectdash.services.portfolio_scanner import PortfolioScanner

        scanner = PortfolioScanner()
        manifest_path = self._resolved_manifest_path()
        manifest = scanner.load_manifest(manifest_path)
        entry = manifest.get(project_id, {})
        if not isinstance(entry, dict):
            entry = {}
        entry[field_name] = value
        manifest[project_id] = entry
        scanner.save_manifest(manifest_path, manifest)
        return True, f"Updated {field_name}={value} for {target.name}"

    def _resolved_manifest_path(self) -> Path:
        if self.config.portfolio_manifest_path:
            return Path(self.config.portfolio_manifest_path).expanduser()
        return Path.home() / ".projectdash" / "portfolio.json"

    async def get_agent_runs(self, limit: int = 50) -> list[AgentRun]:
        return await self.db.get_agent_runs(limit=limit)

    async def complete_agent_run(
        self,
        run_id: str,
        exit_code: int,
        *,
        session_ref: str | None = None,
        log_path: str | None = None,
    ) -> tuple[bool, str]:
        run = await self.db.get_agent_run(run_id)
        if run is None:
            return False, f"Agent run not found: {run_id}"

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        artifacts = dict(run.artifacts or {})
        artifacts["exit_code"] = exit_code
        trace_logs = run.trace_logs
        if log_path:
            artifacts["log_path"] = log_path
            try:
                path = Path(log_path)
                if path.exists():
                    trace_logs = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

        run.status = AgentRunStatus.COMPLETED if exit_code == 0 else AgentRunStatus.FAILED
        run.finished_at = now
        run.updated_at = now
        run.artifacts = artifacts
        run.trace_logs = trace_logs
        if session_ref:
            run.session_ref = session_ref
        run.error_text = None if exit_code == 0 else f"Agent run exited with code {exit_code}"
        await self.record_agent_run(run)
        return True, f"Updated agent run {run_id}: status={run.status} exit_code={exit_code}"

    async def dispatch_agent_run(self, run: AgentRun) -> tuple[bool, str]:
        command_template = os.getenv("PD_AGENT_RUN_CMD", "").strip()
        if not command_template:
            return False, "PD_AGENT_RUN_CMD not set; run is queued only"

        launcher_profile, launcher_template = self._agent_launcher_profile(command_template)
        
        # Guardrail: check allowed profiles
        allowed = self.config.agent_allowed_profiles
        if launcher_profile and launcher_profile not in allowed:
            error_message = f"Agent launcher profile '{launcher_profile}' is not in allowed list: {allowed}"
            run.error_text = error_message
            run.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await self.record_agent_run(run)
            return False, error_message

        if launcher_profile == "tmux":
            return await self._dispatch_agent_run_tmux(launcher_template, run)
        if launcher_profile:
            error_message = f"Unknown PD_AGENT_RUN_CMD launcher profile: {launcher_profile}"
            run.error_text = error_message
            run.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await self.record_agent_run(run)
            return False, error_message

        command_parts, error_message = self._build_agent_command(launcher_template, run)
        if not command_parts:
            run.error_text = error_message
            run.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await self.record_agent_run(run)
            return False, error_message or "Agent dispatch command is empty"

        executable = command_parts[0]
        if not os.path.isabs(executable) and shutil.which(executable) is None:
            run.error_text = f"Executable not found: {executable}"
            run.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await self.record_agent_run(run)
            return False, run.error_text

        try:
            process = subprocess.Popen(
                command_parts,
                cwd=Path.cwd(),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as error:
            run.error_text = f"Dispatch failed: {error}"
            run.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await self.record_agent_run(run)
            return False, run.error_text

        run.status = AgentRunStatus.RUNNING
        run.session_ref = str(process.pid)
        run.error_text = None
        run.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.record_agent_run(run)
        return True, f"dispatched pid={process.pid}"

    async def _dispatch_agent_run_tmux(self, command_template: str, run: AgentRun) -> tuple[bool, str]:
        if shutil.which("tmux") is None:
            run.error_text = "Executable not found: tmux"
            run.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await self.record_agent_run(run)
            return False, run.error_text

        rendered_command, error_message = self._render_agent_command(command_template, run)
        if not rendered_command:
            run.error_text = error_message
            run.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await self.record_agent_run(run)
            return False, error_message or "Agent command template rendered empty"

        try:
            session_ref = self._tmux_session_name(run)
            log_path, launcher_path = self._write_tmux_launcher(
                run=run,
                session_ref=session_ref,
                rendered_command=rendered_command,
            )
            process = subprocess.Popen(
                [
                    "tmux",
                    "new-session",
                    "-d",
                    "-s",
                    session_ref,
                    "-c",
                    str(Path.cwd()),
                    "/bin/bash",
                    str(launcher_path),
                ],
                cwd=Path.cwd(),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as error:
            run.error_text = f"Dispatch failed: {error}"
            run.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await self.record_agent_run(run)
            return False, run.error_text

        artifacts = dict(run.artifacts or {})
        artifacts["launcher_profile"] = "tmux"
        artifacts["log_path"] = str(log_path)
        artifacts["tmux_session"] = session_ref
        artifacts["launcher_script"] = str(launcher_path)

        run.runtime = "tmux"
        run.status = AgentRunStatus.RUNNING
        run.session_ref = session_ref
        run.error_text = None
        run.artifacts = artifacts
        run.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.record_agent_run(run)
        return True, f"dispatched tmux session={session_ref} pid={process.pid}"

    def latest_sync_history_lines(self, limit: int = 3) -> list[str]:
        return self.sync_service.latest_sync_history_lines(limit=limit)

    def connector_freshness_snapshot(
        self,
        connector: str,
        *,
        reference_time: datetime | None = None,
    ) -> dict[str, Any]:
        return self.sync_service.connector_freshness_snapshot(connector, reference_time=reference_time)

    def freshness_summary_line(self, connectors: tuple[str, ...] = ("linear", "github")) -> str:
        return self.sync_service.freshness_summary_line(connectors=connectors)

    def current_user_id(self) -> str:
        """Returns the active user identity from environment."""
        for env_name in ("PD_ME", "GITHUB_USER", "USER", "GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
            value = os.getenv(env_name)
            if value:
                return value.strip()
        return "unknown-user"

    def should_show_sync_freshness(self, connectors: tuple[str, ...] = ("linear", "github")) -> bool:
        return self.sync_service.should_show_sync_freshness(connectors=connectors)

    def get_projects(self) -> List[Project]:
        return self.projects

    def get_issues(self) -> List[Issue]:
        return self.issue_service.get_issues()

    def get_repositories(self) -> List[Repository]:
        return self.github_query_service.get_repositories()

    def get_pull_requests(self, issue_id: str | None = None) -> List[PullRequest]:
        return self.github_query_service.get_pull_requests(issue_id)

    def get_ci_checks(self, pull_request_id: str | None = None) -> List[CiCheck]:
        return self.github_query_service.get_ci_checks(pull_request_id)

    def get_issues_by_status(self, status: str) -> List[Issue]:
        return self.issue_service.get_issues_by_status(status)

    def get_issue_by_id(self, issue_id: str) -> Issue | None:
        return self.issue_service.get_issue_by_id(issue_id)

    async def cycle_issue_status(self, issue_id: str, statuses: tuple[str, ...]) -> tuple[bool, str]:
        return await self.issue_mutation_service.cycle_issue_status(issue_id, statuses)

    async def cycle_issue_assignee(self, issue_id: str) -> tuple[bool, str]:
        return await self.issue_mutation_service.cycle_issue_assignee(issue_id)

    async def cycle_issue_points(self, issue_id: str, step: int = 1, max_points: int = 13) -> tuple[bool, str]:
        return await self.issue_mutation_service.cycle_issue_points(issue_id, step=step, max_points=max_points)

    def _agent_launcher_profile(self, command_template: str) -> tuple[str | None, str]:
        candidate = command_template.strip()
        if candidate.startswith("profile:"):
            remainder = candidate[len("profile:") :]
            profile, separator, profile_template = remainder.partition(":")
            normalized = profile.strip().casefold()
            return normalized or None, profile_template.strip() if separator else ""
        if candidate.startswith("tmux:"):
            return "tmux", candidate[len("tmux:") :].strip()
        return None, candidate

    def _render_agent_command(self, command_template: str, run: AgentRun) -> tuple[str | None, str | None]:
        context = self._agent_command_context(run)
        try:
            rendered = command_template.format(**context).strip()
        except KeyError as error:
            return None, f"Invalid agent command placeholder: {error}"
        if not rendered:
            return None, "Agent command template rendered empty"
        return rendered, None

    def _build_agent_command(self, command_template: str, run: AgentRun) -> tuple[list[str] | None, str | None]:
        rendered_command, error_message = self._render_agent_command(command_template, run)
        if not rendered_command:
            return None, error_message
        try:
            return shlex.split(rendered_command), None
        except ValueError as error:
            return None, f"Failed to parse PD_AGENT_RUN_CMD: {error}"

    def _agent_run_log_dir(self) -> Path:
        configured = os.getenv("PD_AGENT_RUN_LOG_DIR", ".projectdash/agent-runs").strip()
        root = Path(configured).expanduser() if configured else Path(".projectdash/agent-runs")
        if not root.is_absolute():
            root = Path.cwd() / root
        return root

    def _tmux_session_name(self, run: AgentRun) -> str:
        issue_token = re.sub(r"[^a-zA-Z0-9_-]+", "-", run.issue_id or "").strip("-")
        run_token = re.sub(r"[^a-zA-Z0-9_-]+", "-", run.id or "").strip("-")
        if not issue_token:
            issue_token = "run"
        if not run_token:
            run_token = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"pd-agent-{issue_token[:24]}-{run_token[:20]}"

    def _write_tmux_launcher(self, *, run: AgentRun, session_ref: str, rendered_command: str) -> tuple[Path, Path]:
        log_dir = self._agent_run_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)

        log_path = log_dir / f"{run.id}.log"
        launcher_path = log_dir / f"{run.id}.launcher.sh"
        status_command = [
            sys.executable,
            "-m",
            "projectdash.cli",
            "agent-run-finish",
            "--run-id",
            run.id,
            "--session-ref",
            session_ref,
            "--log-path",
            str(log_path),
        ]

        launcher_script = "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -uo pipefail",
                "",
                f"RUN_ID={shlex.quote(run.id)}",
                f"SESSION_REF={shlex.quote(session_ref)}",
                f"LOG_PATH={shlex.quote(str(log_path))}",
                f"PROJECT_ROOT={shlex.quote(str(Path.cwd()))}",
                f"AGENT_COMMAND={shlex.quote(rendered_command)}",
                f"STATUS_COMMAND=({' '.join(shlex.quote(part) for part in status_command)})",
                "",
                "mkdir -p \"$(dirname \"$LOG_PATH\")\"",
                "{",
                "  printf '[%s] dispatch profile=tmux run_id=%s session=%s\\n' \"$(date '+%Y-%m-%d %H:%M:%S')\" \"$RUN_ID\" \"$SESSION_REF\"",
                "  printf '[%s] command: %s\\n' \"$(date '+%Y-%m-%d %H:%M:%S')\" \"$AGENT_COMMAND\"",
                "} >>\"$LOG_PATH\"",
                "",
                "cd \"$PROJECT_ROOT\" || exit 1",
                "bash -lc \"$AGENT_COMMAND\" >>\"$LOG_PATH\" 2>&1",
                "EXIT_CODE=$?",
                "\"${STATUS_COMMAND[@]}\" --exit-code \"$EXIT_CODE\" >>\"$LOG_PATH\" 2>&1 || true",
                "printf '[%s] completed exit_code=%s\\n' \"$(date '+%Y-%m-%d %H:%M:%S')\" \"$EXIT_CODE\" >>\"$LOG_PATH\"",
                "exit \"$EXIT_CODE\"",
                "",
            ]
        )
        launcher_path.write_text(launcher_script, encoding="utf-8")
        launcher_path.chmod(0o700)
        return log_path, launcher_path

    def _agent_command_context(self, run: AgentRun) -> dict[str, str]:
        artifacts = run.artifacts or {}
        return {
            "run_id": run.id,
            "runtime": run.runtime or "",
            "status": run.status or "",
            "issue_id": run.issue_id or "",
            "project_id": run.project_id or "",
            "session_ref": run.session_ref or "",
            "branch_name": run.branch_name or "",
            "pr_id": run.pr_id or "",
            "prompt_text": run.prompt_text or "",
            "repository_id": str(artifacts.get("repository_id") or ""),
            "pull_request_number": str(artifacts.get("pull_request_number") or ""),
            "pull_request_url": str(artifacts.get("pull_request_url") or ""),
            "head_branch": str(artifacts.get("head_branch") or ""),
            "base_branch": str(artifacts.get("base_branch") or ""),
        }

    def _github_repository_targets(self) -> list[str]:
        return self.sync_service.github_repository_targets()

    def _cache_workflow_states(self, raw_teams: list[dict]) -> None:
        self.issue_service.cache_workflow_states(raw_teams)

    def _coerce_sync_error(self, error: Exception, *, connector: str, step: str) -> SyncError:
        return self.sync_service.coerce_sync_error(error, connector=connector, step=step)

    def _coerce_persistence_error(self, error: Exception, *, operation: str) -> PersistenceError:
        return self.sync_service.coerce_persistence_error(error, operation=operation)

    def _looks_like_missing_credentials(self, message: str) -> bool:
        return self.sync_service.looks_like_missing_credentials(message)

    async def _apply_remote_issue(self, raw_issue: dict[str, Any]) -> None:
        await self.issue_service.apply_remote_issue(raw_issue)

    def _flatten_workflow_states(self) -> list[LinearWorkflowState]:
        return self.issue_service.flatten_workflow_states()

    async def _record_sync_history(self) -> None:
        await self.sync_service.record_sync_history()

    def _sync_status_summary_core(self) -> str:
        return self.sync_service.sync_status_summary_core()

    async def _save_sync_checkpoint(self, connector: str, resource_class: str, payload: Any) -> None:
        await self.sync_service.save_sync_checkpoint(connector, resource_class, payload)

    def _payload_checkpoint(self, payload: Any) -> str:
        return self.sync_service.payload_checkpoint(payload)

    def _merge_repositories_with_policy(
        self,
        existing: list[Repository],
        incoming: list[Repository],
    ) -> list[Repository]:
        return self.sync_service.merge_repositories_with_policy(existing, incoming)

    def _merge_pull_requests_with_policy(
        self,
        existing: list[PullRequest],
        incoming: list[PullRequest],
    ) -> list[PullRequest]:
        return self.sync_service.merge_pull_requests_with_policy(existing, incoming)

    def _merge_ci_checks_with_policy(
        self,
        existing: list[CiCheck],
        incoming: list[CiCheck],
    ) -> list[CiCheck]:
        return self.sync_service.merge_ci_checks_with_policy(existing, incoming)

    def _preferred_repository(self, existing: Repository, incoming: Repository) -> Repository:
        return self.sync_service.preferred_repository(existing, incoming)

    def _preferred_pull_request(self, existing: PullRequest, incoming: PullRequest) -> PullRequest:
        return self.sync_service.preferred_pull_request(existing, incoming)

    def _preferred_ci_check(self, existing: CiCheck, incoming: CiCheck) -> CiCheck:
        return self.sync_service.preferred_ci_check(existing, incoming)

    def _prefer_newer_by_timestamp(
        self,
        existing: Any,
        incoming: Any,
        existing_value: str | None,
        incoming_value: str | None,
    ) -> Any | None:
        return self.sync_service.prefer_newer_by_timestamp(existing, incoming, existing_value, incoming_value)

    @staticmethod
    def _parse_connector_timestamp(value: str | None) -> float | None:
        return SyncService.parse_connector_timestamp(value)

    @staticmethod
    def _sync_stale_threshold_minutes() -> int:
        return SyncService.sync_stale_threshold_minutes()

    @staticmethod
    def _parse_sync_time(value: str | None) -> datetime | None:
        return SyncService.parse_sync_time(value)

    def _mark_connector_attempt(self, connector: str) -> None:
        self.sync_service.mark_connector_attempt(connector)

    def _finalize_connector_sync(self, connector: str) -> None:
        self.sync_service.finalize_connector_sync(connector)

    @staticmethod
    def _sync_recovery_hint(connector: str, error: str | None) -> str:
        return SyncService.sync_recovery_hint(connector, error)
