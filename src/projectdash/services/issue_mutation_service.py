from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable

from projectdash.linear import LinearApiError
from projectdash.models import Issue, User

if TYPE_CHECKING:
    from projectdash.data import DataManager


class IssueMutationService:
    def __init__(self, data_manager: DataManager):
        self.data = data_manager

    async def cycle_issue_status(self, issue_id: str, statuses: tuple[str, ...]) -> tuple[bool, str]:
        issue = self.data.get_issue_by_id(issue_id)
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
            lambda: self.data.linear.update_issue_status(self._remote_issue_id(issue), issue.state_id or ""),
            "Status update failed",
        )
        if not ok:
            return False, error or "Status update failed"
        if warning:
            return True, f"{issue.id} moved to {next_status} (warning: {warning})"
        return True, f"{issue.id} moved to {next_status}"

    async def cycle_issue_assignee(self, issue_id: str) -> tuple[bool, str]:
        issue = self.data.get_issue_by_id(issue_id)
        if issue is None:
            return False, f"Issue not found: {issue_id}"
        cycle: list[User | None] = [None, *self.data.users]
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
            lambda: self.data.linear.update_issue_assignee(
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
        issue = self.data.get_issue_by_id(issue_id)
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
            lambda: self.data.linear.update_issue_estimate(self._remote_issue_id(issue), issue.points),
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
        except Exception as error:
            self._restore_issue_fields(issue, previous_values)
            reconcile_message = ""
            if self._should_reconcile_remote_failure(error):
                reconcile_message = await self._reconcile_issue_after_remote_failure(issue)
            return False, f"{failure_prefix}: {self._format_remote_error(error)}{reconcile_message}"

        ok, error = await self._persist_issue_with_rollback(issue, previous_values)
        if not ok:
            return False, f"{failure_prefix}: {error}"
        return True, None

    async def _persist_issue_with_rollback(
        self,
        issue: Issue,
        previous_values: dict[str, object],
    ) -> tuple[bool, str | None]:
        try:
            await self.data.db.save_issues([issue], project_id=issue.project_id)
            return True, None
        except Exception as error:
            self._restore_issue_fields(issue, previous_values)
            return False, str(error)

    def _restore_issue_fields(self, issue: Issue, previous_values: dict[str, object]) -> None:
        for field_name, previous_value in previous_values.items():
            setattr(issue, field_name, previous_value)

    def _resolve_state_id_for_status(self, issue: Issue, status: str) -> tuple[str | None, str | None]:
        status_key = status.strip().casefold()
        configured_mapping = self.data.config.linear_status_mappings.get(status_key)
        team_states = self.data.workflow_states_by_team.get(issue.team_id or "", [])

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
        if not self.data.linear.api_key:
            return ""
        if issue.linear_id:
            try:
                raw_issue = await self.data.linear.get_issue(issue.linear_id)
                if raw_issue:
                    await self.data.issue_service.apply_remote_issue(raw_issue)
                    return " (re-fetched latest issue)"
            except Exception:
                pass
        try:
            await self.data.sync_with_linear()
            if self.data.last_sync_result == "success":
                return " (triggered full re-sync)"
        except Exception:
            pass
        return ""
