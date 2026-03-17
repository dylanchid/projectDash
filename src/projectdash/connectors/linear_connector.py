from __future__ import annotations

from projectdash.connectors.base import ConnectorEntities
from projectdash.models import Issue, LinearWorkflowState, Project, User


class LinearConnector:
    name = "linear"
    required_env = ("LINEAR_API_KEY",)

    def build_entities(
        self,
        *,
        raw_projects: list[dict],
        raw_teams: list[dict],
        raw_issues: list[dict],
    ) -> ConnectorEntities:
        workflow_states = self._workflow_states(raw_teams)
        users_by_id: dict[str, User] = {}
        issues: list[Issue] = []
        for raw_issue in raw_issues:
            assignee = None
            raw_assignee = raw_issue.get("assignee")
            if raw_assignee:
                assignee_id = raw_assignee["id"]
                assignee = users_by_id.get(assignee_id)
                if assignee is None:
                    assignee = User(
                        id=assignee_id,
                        name=raw_assignee["name"],
                        avatar_url=raw_assignee.get("avatarUrl"),
                    )
                    users_by_id[assignee_id] = assignee

            issues.append(
                Issue(
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
                    description=raw_issue.get("description"),
                    labels=[l["name"] for l in raw_issue.get("labels", {}).get("nodes", [])] if raw_issue.get("labels") else [],
                )
            )

        issues_by_project: dict[str, list[Issue]] = {}
        for issue in issues:
            if issue.project_id:
                issues_by_project.setdefault(issue.project_id, []).append(issue)

        projects: list[Project] = []
        for raw_project in raw_projects:
            project_issues = issues_by_project.get(raw_project["id"], [])
            projects.append(
                Project(
                    id=raw_project["id"],
                    name=raw_project["name"],
                    status=raw_project.get("state") or "Active",
                    issues_count=len(project_issues),
                    in_progress_count=sum(
                        1 for issue in project_issues if issue.status in {"In Progress", "Review"}
                    ),
                    blocked_count=sum(
                        1 for issue in project_issues if "blocked" in issue.status.casefold()
                    ),
                    due_date=raw_project.get("targetDate") or "N/A",
                    cycle="Current",
                    start_date=raw_project.get("startDate"),
                    description=raw_project.get("description"),
                )
            )

        return ConnectorEntities(
            users=list(users_by_id.values()),
            projects=projects,
            issues=issues,
            workflow_states=workflow_states,
        )

    def workflow_states_by_team(self, raw_teams: list[dict]) -> dict[str, list[LinearWorkflowState]]:
        grouped: dict[str, list[LinearWorkflowState]] = {}
        for state in self._workflow_states(raw_teams):
            grouped.setdefault(state.team_id, []).append(state)
        return grouped

    def _workflow_states(self, raw_teams: list[dict]) -> list[LinearWorkflowState]:
        states: list[LinearWorkflowState] = []
        for team in raw_teams:
            team_id = team.get("id")
            if not team_id:
                continue
            team_key = team.get("key")
            for node in team.get("states", {}).get("nodes", []):
                state_id = node.get("id")
                state_name = node.get("name")
                if not state_id or not state_name:
                    continue
                states.append(
                    LinearWorkflowState(
                        id=state_id,
                        name=state_name,
                        type=node.get("type") or "unstarted",
                        team_id=team_id,
                        team_key=team_key,
                    )
                )
        return states

