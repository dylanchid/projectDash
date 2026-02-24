from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List
from projectdash.models import Project, Issue, User, LinearWorkflowState
from projectdash.database import Database
from projectdash.linear import LinearApiError, LinearClient
from projectdash.config import AppConfig
import os
from datetime import datetime

class DataManager:
    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig.from_env()
        self.db = Database()
        self.linear = LinearClient()
        self.users: List[User] = []
        self.projects: List[Project] = []
        self.issues: List[Issue] = []
        self.workflow_states_by_team: dict[str, list[LinearWorkflowState]] = {}
        self.is_initialized = False
        self.sync_in_progress = False
        self.last_sync_at: str | None = None
        self.last_sync_error: str | None = None
        self.last_sync_result: str = "idle"
        self.sync_diagnostics: dict[str, str] = {}
        self.last_sync_counts: dict[str, int] = {}
        self.sync_history: list[dict[str, Any]] = []

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
            Project("1", "Acme Corp", "Synced", 12, 5, 2, "2024-02-28", "Jan Q1"),
            Project("2", "DevTools", "Synced", 8, 3, 0, "2024-03-15", "Feb Q1"),
            Project("3", "Web Redesign", "Synced", 7, 2, 1, "2024-03-30", "Design"),
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
        workflow_states = await self.db.get_workflow_states()
        workflow_states_by_team: dict[str, list[LinearWorkflowState]] = {}
        for state in workflow_states:
            workflow_states_by_team.setdefault(state.team_id, []).append(state)
        self.workflow_states_by_team = workflow_states_by_team
        self.sync_history = await self.db.get_sync_history()

    async def sync_with_linear(self):
        """Fetches latest data from Linear and updates the cache."""
        self.sync_in_progress = True
        self.last_sync_error = None
        self.last_sync_result = "syncing"
        self.sync_diagnostics = {}
        self.last_sync_counts = {}
        try:
            api_key = os.getenv("LINEAR_API_KEY")
            if not api_key:
                self.last_sync_error = "LINEAR_API_KEY not set"
                self.last_sync_result = "failed"
                self.sync_diagnostics["auth"] = "failed: LINEAR_API_KEY not set"
                return

            print("   - Testing connection...")
            try:
                me = await self.linear.get_me()
                print(f"   - Authenticated as: {me['viewer']['name']}")
                self.sync_diagnostics["auth"] = f"ok: {me['viewer']['name']}"
            except Exception as e:
                print(f"   - Connection failed: {e}")
                self.last_sync_error = f"auth failed: {e}"
                self.last_sync_result = "failed"
                self.sync_diagnostics["auth"] = f"failed: {e}"
                return

            print("   - Fetching projects...")
            try:
                raw_projects = await self.linear.get_projects()
            except Exception as e:
                self.last_sync_error = f"projects fetch failed: {e}"
                self.last_sync_result = "failed"
                self.sync_diagnostics["projects"] = f"failed: {e}"
                return
            self.sync_diagnostics["projects"] = f"ok: {len(raw_projects)}"
            print("   - Fetching workflow states...")
            try:
                raw_teams = await self.linear.get_team_workflow_states()
            except Exception as e:
                self.last_sync_error = f"workflow states fetch failed: {e}"
                self.last_sync_result = "failed"
                self.sync_diagnostics["workflow_states"] = f"failed: {e}"
                return
            self.sync_diagnostics["workflow_states"] = f"ok: {len(raw_teams)} teams"
            print("   - Fetching issues...")
            try:
                raw_issues = await self.linear.get_issues()
            except Exception as e:
                self.last_sync_error = f"issues fetch failed: {e}"
                self.last_sync_result = "failed"
                self.sync_diagnostics["issues"] = f"failed: {e}"
                return
            self.sync_diagnostics["issues"] = f"ok: {len(raw_issues)}"
            self._cache_workflow_states(raw_teams)

            users_dict = {}
            issues = []
            for i in raw_issues:
                assignee = None
                if i["assignee"]:
                    u_id = i["assignee"]["id"]
                    if u_id not in users_dict:
                        users_dict[u_id] = User(u_id, i["assignee"]["name"], i["assignee"]["avatarUrl"])
                    assignee = users_dict[u_id]

                issues.append(Issue(
                    id=i["identifier"],
                    linear_id=i["id"],
                    title=i["title"],
                    priority=str(i["priority"]),
                    status=i["state"]["name"] if i["state"] else "Todo",
                    state_id=i["state"]["id"] if i["state"] else None,
                    team_id=i["team"]["id"] if i.get("team") else None,
                    assignee=assignee,
                    points=i["estimate"] or 0,
                    project_id=i["project"]["id"] if i.get("project") else None,
                    due_date=i.get("dueDate"),
                ))

            issues_by_project: Dict[str, List[Issue]] = {}
            for issue in issues:
                if issue.project_id:
                    issues_by_project.setdefault(issue.project_id, []).append(issue)

            projects = []
            for p in raw_projects:
                project_issues = issues_by_project.get(p["id"], [])
                status_name = p.get("state") or "Active"
                projects.append(Project(
                    id=p["id"],
                    name=p["name"],
                    status=status_name,
                    issues_count=len(project_issues),
                    in_progress_count=sum(1 for issue in project_issues if issue.status in {"In Progress", "Review"}),
                    blocked_count=sum(1 for issue in project_issues if "blocked" in issue.status.lower()),
                    due_date=p.get("targetDate") or "N/A",
                    cycle="Current",
                ))

            try:
                await self.db.save_users(list(users_dict.values()))
                await self.db.save_projects(projects)
                await self.db.save_issues(issues)
                await self.db.save_workflow_states(self._flatten_workflow_states())
            except Exception as e:
                self.last_sync_error = f"persist failed: {e}"
                self.last_sync_result = "failed"
                self.sync_diagnostics["persist"] = f"failed: {e}"
                return
            self.sync_diagnostics["persist"] = "ok"
            try:
                await self.load_from_cache()
            except Exception as e:
                self.last_sync_error = f"reload failed: {e}"
                self.last_sync_result = "failed"
                self.sync_diagnostics["reload"] = f"failed: {e}"
                return
            self.sync_diagnostics["reload"] = "ok"
            self.last_sync_counts = {
                "users": len(self.users),
                "projects": len(self.projects),
                "issues": len(self.issues),
                "teams": len(self.workflow_states_by_team),
            }
            self.last_sync_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.last_sync_result = "success"
        except Exception as e:
            self.last_sync_error = str(e)
            self.last_sync_result = "failed"
            self.sync_diagnostics["unexpected"] = f"failed: {e}"
            raise
        finally:
            await self._record_sync_history()
            self.sync_in_progress = False

    def sync_status_summary(self) -> str:
        if self.sync_in_progress:
            return "syncing"
        return self._sync_status_summary_core()

    def sync_diagnostic_lines(self) -> list[str]:
        return [f"{step}: {status}" for step, status in self.sync_diagnostics.items()]

    def get_sync_history(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.sync_history[:limit]

    def latest_sync_history_lines(self, limit: int = 3) -> list[str]:
        entries = self.get_sync_history(limit=limit)
        lines: list[str] = []
        for entry in entries:
            timestamp = entry.get("created_at", "?")
            result = entry.get("result", "?")
            summary = entry.get("summary", "")
            lines.append(f"{timestamp} | {result} | {summary}")
        return lines

    def get_projects(self) -> List[Project]:
        return self.projects

    def get_issues(self) -> List[Issue]:
        return self.issues

    def get_issues_by_status(self, status: str) -> List[Issue]:
        return [i for i in self.issues if i.status == status]

    def get_issue_by_id(self, issue_id: str) -> Issue | None:
        for issue in self.issues:
            if issue.id == issue_id:
                return issue
        return None

    async def cycle_issue_status(self, issue_id: str, statuses: tuple[str, ...]) -> tuple[bool, str]:
        issue = self.get_issue_by_id(issue_id)
        if issue is None:
            return False, f"Issue not found: {issue_id}"
        if not statuses:
            return False, "No configured statuses"
        if issue.status in statuses:
            next_index = (statuses.index(issue.status) + 1) % len(statuses)
        else:
            next_index = 0
        next_status = statuses[next_index]
        previous_status = issue.status
        previous_state_id = issue.state_id

        issue.status = next_status
        resolved_state_id, warning = self._resolve_state_id_for_status(issue, next_status)
        if resolved_state_id is None:
            issue.status = previous_status
            issue.state_id = previous_state_id
            message = warning or f"no Linear state mapping for status '{next_status}'"
            return False, f"Status update failed: {message}"
        issue.state_id = resolved_state_id

        ok, error = await self._write_through_issue_update(
            issue,
            {"status": previous_status, "state_id": previous_state_id},
            lambda: self.linear.update_issue_status(self._remote_issue_id(issue), issue.state_id or ""),
            "Status update failed",
        )
        if not ok:
            return False, error or "Status update failed"
        if warning:
            return True, f"{issue.id} moved to {next_status} (warning: {warning})"
        return True, f"{issue.id} moved to {next_status}"

    async def cycle_issue_assignee(self, issue_id: str) -> tuple[bool, str]:
        issue = self.get_issue_by_id(issue_id)
        if issue is None:
            return False, f"Issue not found: {issue_id}"
        cycle: list[User | None] = [None, *self.users]
        if not cycle:
            return False, "No assignees available"

        current_index = 0
        for idx, assignee in enumerate(cycle):
            if (issue.assignee is None and assignee is None) or (
                issue.assignee is not None and assignee is not None and issue.assignee.id == assignee.id
            ):
                current_index = idx
                break
        next_assignee = cycle[(current_index + 1) % len(cycle)]
        previous_assignee = issue.assignee
        issue.assignee = next_assignee

        ok, error = await self._write_through_issue_update(
            issue,
            {"assignee": previous_assignee},
            lambda: self.linear.update_issue_assignee(
                self._remote_issue_id(issue),
                issue.assignee.id if issue.assignee else None,
            ),
            "Assignee update failed",
        )
        if not ok:
            return False, error or "Assignee update failed"
        assignee_name = issue.assignee.name if issue.assignee else "Unassigned"
        return True, f"{issue.id} assigned to {assignee_name}"

    async def cycle_issue_points(self, issue_id: str, step: int = 1, max_points: int = 13) -> tuple[bool, str]:
        issue = self.get_issue_by_id(issue_id)
        if issue is None:
            return False, f"Issue not found: {issue_id}"
        previous_points = issue.points
        next_points = issue.points + step
        if next_points > max_points:
            next_points = 0
        issue.points = next_points

        ok, error = await self._write_through_issue_update(
            issue,
            {"points": previous_points},
            lambda: self.linear.update_issue_estimate(self._remote_issue_id(issue), issue.points),
            "Estimate update failed",
        )
        if not ok:
            return False, error or "Estimate update failed"
        return True, f"{issue.id} estimate set to {issue.points}"

    async def _write_through_issue_update(
        self,
        issue: Issue,
        previous_values: dict[str, object],
        remote_update: Callable[[], Awaitable[dict[str, Any]]],
        failure_prefix: str,
    ) -> tuple[bool, str | None]:
        try:
            remote_result = await remote_update()
            if not remote_result.get("success", False):
                raise RuntimeError("Linear rejected update")
        except Exception as e:
            self._restore_issue_fields(issue, previous_values)
            reconcile_message = ""
            if self._should_reconcile_remote_failure(e):
                reconcile_message = await self._reconcile_issue_after_remote_failure(issue)
            return False, f"{failure_prefix}: {self._format_remote_error(e)}{reconcile_message}"

        ok, error = await self._persist_issue_with_rollback(issue, previous_values)
        if not ok:
            return False, f"{failure_prefix}: {error}"
        return True, None

    async def _persist_issue_with_rollback(self, issue: Issue, previous_values: dict[str, object]) -> tuple[bool, str | None]:
        try:
            await self.db.save_issues([issue], project_id=issue.project_id)
            return True, None
        except Exception as e:
            self._restore_issue_fields(issue, previous_values)
            return False, str(e)

    def _restore_issue_fields(self, issue: Issue, previous_values: dict[str, object]) -> None:
        for field_name, previous_value in previous_values.items():
            setattr(issue, field_name, previous_value)

    def _cache_workflow_states(self, raw_teams: list[dict]) -> None:
        workflow_states_by_team: dict[str, list[LinearWorkflowState]] = {}
        for team in raw_teams:
            team_id = team.get("id")
            if not team_id:
                continue
            state_nodes = team.get("states", {}).get("nodes", [])
            workflow_states_by_team[team_id] = [
                LinearWorkflowState(
                    id=state["id"],
                    name=state["name"],
                    type=state.get("type") or "unstarted",
                    team_id=team_id,
                    team_key=team.get("key"),
                )
                for state in state_nodes
                if state.get("id") and state.get("name")
            ]
        self.workflow_states_by_team = workflow_states_by_team

    def _resolve_state_id_for_status(self, issue: Issue, status: str) -> tuple[str | None, str | None]:
        status_key = status.strip().casefold()
        configured_mapping = self.config.linear_status_mappings.get(status_key)
        team_states = self.workflow_states_by_team.get(issue.team_id or "", [])

        if configured_mapping:
            configured_key = configured_mapping.casefold()
            for state in team_states:
                if state.id == configured_mapping or state.name.casefold() == configured_key:
                    return state.id, None
            if team_states:
                return None, f"configured mapping '{configured_mapping}' not found for team workflow states"
            return None, f"configured mapping '{configured_mapping}' could not be validated (no team workflow states cached)"

        for state in team_states:
            if state.name.casefold() == status_key:
                return state.id, None

        if not issue.team_id:
            return None, f"no team id on {issue.id}; unable to map status '{status}' to Linear state id"
        if not team_states:
            return None, f"no workflow states cached for team {issue.team_id}; run sync to populate state mapping"
        return (
            None,
            f"no mapping for status '{status}' in team {issue.team_id}; "
            f"add linear_status_mappings.{status_key} in projectdash.config.json",
        )

    def _remote_issue_id(self, issue: Issue) -> str:
        return issue.linear_id or issue.id

    def _format_remote_error(self, error: Exception) -> str:
        if isinstance(error, LinearApiError):
            message = error.message
            lowered = message.casefold()
            if "archived" in lowered:
                reason = "issue is archived"
            elif "permission" in lowered or error.code in {"FORBIDDEN", "UNAUTHORIZED"}:
                reason = "permission denied"
            elif "state" in lowered and ("invalid" in lowered or "not found" in lowered):
                reason = "invalid state"
            elif "stale" in lowered or "conflict" in lowered:
                reason = "stale issue data"
            elif "not found" in lowered:
                reason = "issue not found or inaccessible"
            else:
                reason = "Linear API error"
            suffix = []
            if error.code:
                suffix.append(f"code={error.code}")
            if error.type:
                suffix.append(f"type={error.type}")
            suffix_text = f" ({', '.join(suffix)})" if suffix else ""
            return f"{reason}: {message}{suffix_text}"
        return str(error)

    def _should_reconcile_remote_failure(self, error: Exception) -> bool:
        if not isinstance(error, LinearApiError):
            return False
        if error.code in {"CONFLICT", "NOT_FOUND"}:
            return True
        lowered = error.message.casefold()
        return "stale" in lowered or "conflict" in lowered

    async def _reconcile_issue_after_remote_failure(self, issue: Issue) -> str:
        if not self.linear.api_key:
            return ""
        if issue.linear_id:
            try:
                raw_issue = await self.linear.get_issue(issue.linear_id)
                if raw_issue:
                    await self._apply_remote_issue(raw_issue)
                    return " (re-fetched latest issue)"
            except Exception:
                pass
        try:
            await self.sync_with_linear()
            if self.last_sync_result == "success":
                return " (triggered full re-sync)"
        except Exception:
            pass
        return ""

    async def _apply_remote_issue(self, raw_issue: dict[str, Any]) -> None:
        users_dict: dict[str, User] = {user.id: user for user in self.users}
        assignee = None
        raw_assignee = raw_issue.get("assignee")
        if raw_assignee:
            assignee_id = raw_assignee["id"]
            user = users_dict.get(assignee_id)
            if user is None:
                user = User(assignee_id, raw_assignee["name"], raw_assignee.get("avatarUrl"))
                self.users.append(user)
            assignee = user

        remote_issue = Issue(
            id=raw_issue["identifier"],
            linear_id=raw_issue["id"],
            title=raw_issue["title"],
            priority=str(raw_issue["priority"]),
            status=raw_issue["state"]["name"] if raw_issue.get("state") else "Todo",
            state_id=raw_issue["state"]["id"] if raw_issue.get("state") else None,
            team_id=raw_issue["team"]["id"] if raw_issue.get("team") else None,
            assignee=assignee,
            points=raw_issue.get("estimate") or 0,
            project_id=raw_issue["project"]["id"] if raw_issue.get("project") else None,
            due_date=raw_issue.get("dueDate"),
        )

        replaced = False
        for idx, existing in enumerate(self.issues):
            if existing.id == remote_issue.id or (
                existing.linear_id is not None and existing.linear_id == remote_issue.linear_id
            ):
                self.issues[idx] = remote_issue
                replaced = True
                break
        if not replaced:
            self.issues.append(remote_issue)

        await self.db.save_users(self.users)
        await self.db.save_issues([remote_issue], project_id=remote_issue.project_id)

    def _flatten_workflow_states(self) -> list[LinearWorkflowState]:
        flattened: list[LinearWorkflowState] = []
        for states in self.workflow_states_by_team.values():
            flattened.extend(states)
        return flattened

    async def _record_sync_history(self) -> None:
        if self.last_sync_result == "syncing":
            return
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary = self._sync_status_summary_core()
        try:
            await self.db.append_sync_history(
                created_at=created_at,
                result=self.last_sync_result,
                summary=summary,
                diagnostics=self.sync_diagnostics,
            )
            self.sync_history = await self.db.get_sync_history()
        except Exception:
            pass

    def _sync_status_summary_core(self) -> str:
        if self.last_sync_result == "success":
            users = self.last_sync_counts.get("users", len(self.users))
            projects = self.last_sync_counts.get("projects", len(self.projects))
            issues = self.last_sync_counts.get("issues", len(self.issues))
            teams = self.last_sync_counts.get("teams", len(self.workflow_states_by_team))
            return f"success u:{users} p:{projects} i:{issues} t:{teams}"
        if self.last_sync_error:
            return f"failed: {self.last_sync_error}"
        return self.last_sync_result
