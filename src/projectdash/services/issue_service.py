from __future__ import annotations

from typing import TYPE_CHECKING, Any

from projectdash.models import Issue, LinearWorkflowState, User

if TYPE_CHECKING:
    from projectdash.data import DataManager


class IssueService:
    def __init__(self, data_manager: DataManager):
        self.data = data_manager

    def get_issues(self) -> list[Issue]:
        return self.data.issues

    def get_issues_by_status(self, status: str) -> list[Issue]:
        return [issue for issue in self.data.issues if issue.status == status]

    def get_issue_by_id(self, issue_id: str) -> Issue | None:
        for issue in self.data.issues:
            if issue.id == issue_id:
                return issue
        return None

    def cache_workflow_states(self, raw_teams: list[dict[str, Any]]) -> None:
        self.data.workflow_states_by_team = self.data.linear_connector.workflow_states_by_team(raw_teams)

    def flatten_workflow_states(self) -> list[LinearWorkflowState]:
        flattened: list[LinearWorkflowState] = []
        for states in self.data.workflow_states_by_team.values():
            flattened.extend(states)
        return flattened

    async def apply_remote_issue(self, raw_issue: dict[str, Any]) -> None:
        users_dict = {user.id: user for user in self.data.users}
        assignee = None
        raw_assignee = raw_issue.get("assignee")
        if raw_assignee:
            assignee_id = raw_assignee["id"]
            user = users_dict.get(assignee_id)
            if user is None:
                user = User(assignee_id, raw_assignee["name"], raw_assignee.get("avatarUrl"))
                self.data.users.append(user)
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
        for idx, existing in enumerate(self.data.issues):
            if existing.id == remote_issue.id or (
                existing.linear_id is not None and existing.linear_id == remote_issue.linear_id
            ):
                self.data.issues[idx] = remote_issue
                replaced = True
                break
        if not replaced:
            self.data.issues.append(remote_issue)

        await self.data.db.save_users(self.data.users)
        await self.data.db.save_issues([remote_issue], project_id=remote_issue.project_id)
