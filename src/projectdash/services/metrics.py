from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from projectdash.config import AppConfig
from projectdash.data import DataManager
from projectdash.enums import CiConclusion, PullRequestState, WorkloadStatus
from projectdash.models import CiCheck, Issue, Project, PullRequest, User


@dataclass(frozen=True)
class ProjectCardMetric:
    project_id: str
    name: str
    total: int
    active: int
    blocked: int


@dataclass(frozen=True)
class StaleWorkMetric:
    issue_id: str
    title: str
    owner_name: str
    days_stale: int


@dataclass(frozen=True)
class DashboardMetricSet:
    projects_total: int
    issues_total: int
    velocity_points: int
    blocked_total: int
    connected: bool
    loaded_users: int
    project_cards: list[ProjectCardMetric]
    stale_work: list[StaleWorkMetric] = field(default_factory=list)


@dataclass(frozen=True)
class SprintColumnMetric:
    status: str
    issues: list[Issue]


@dataclass(frozen=True)
class SprintBoardMetricSet:
    columns: list[SprintColumnMetric]
    risk: "SprintRiskMetric"


@dataclass(frozen=True)
class SprintRiskMetric:
    blocked_issues: int
    failing_prs: int
    stale_reviews: int
    overloaded_owners: int
    blocked_breached: bool
    failing_prs_breached: bool
    stale_reviews_breached: bool
    overloaded_owners_breached: bool


@dataclass(frozen=True)
class WorkloadMemberMetric:
    name: str
    allocation_bar: str
    points: int
    capacity: int
    utilization_pct: int
    status_text: str
    status_color: str
    issues_preview: str


@dataclass(frozen=True)
class WorkloadTeamMetric:
    allocation_bar: str
    total_points: int
    total_capacity: int
    utilization_pct: int
    status_markup: str
    active_issues: int


@dataclass(frozen=True)
class WorkloadMetricSet:
    members: list[WorkloadMemberMetric]
    team: WorkloadTeamMetric
    recommendations: list[str]


@dataclass(frozen=True)
class TimelineProjectMetric:
    project_id: str
    name: str
    due_date_label: str
    days_remaining_label: str
    progress_bar: str
    done_points: int
    total_points: int
    status_color: str
    blocked_count: int


@dataclass(frozen=True)
class TimelineMetricSet:
    title: str
    subtitle: str
    project_lines: list[TimelineProjectMetric]


class MetricsService:
    def __init__(self, config: AppConfig):
        self.config = config

    def dashboard(self, data: DataManager, project_id: str | None = None) -> DashboardMetricSet:
        issues = data.get_issues()
        projects = data.get_projects()
        if project_id:
            projects = [project for project in projects if project.id == project_id]
            issues = [issue for issue in issues if issue.project_id == project_id]
        blocked_total = self._count_blocked_issues(issues)
        velocity_points = self._velocity_points(issues)
        connected = bool(os.getenv("LINEAR_API_KEY"))
        issues_by_project: dict[str, list[Issue]] = {}
        for issue in issues:
            if issue.project_id:
                issues_by_project.setdefault(issue.project_id, []).append(issue)

        project_cards = [
            ProjectCardMetric(
                project_id=project.id,
                name=project.name,
                total=(
                    len(issues_by_project.get(project.id, []))
                    if project.id in issues_by_project
                    else max(0, project.issues_count)
                ),
                active=(
                    self._active_count(issues_by_project.get(project.id, []))
                    if project.id in issues_by_project
                    else max(0, project.in_progress_count)
                ),
                blocked=(
                    self._count_blocked_issues(issues_by_project.get(project.id, []))
                    if project.id in issues_by_project
                    else max(0, project.blocked_count)
                ),
            )
            for project in projects
        ]

        stale_work = self._stale_work(issues)

        return DashboardMetricSet(
            projects_total=len(projects),
            issues_total=len(issues),
            velocity_points=velocity_points,
            blocked_total=blocked_total,
            connected=connected,
            loaded_users=len(data.users),
            project_cards=project_cards,
            stale_work=stale_work,
        )

    def _stale_work(self, issues: list[Issue]) -> list[StaleWorkMetric]:
        active_statuses = {s.lower() for s in self.config.active_statuses}
        stale_days = self.config.dashboard_stale_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
        
        stale = []
        for issue in issues:
            if issue.status.lower() not in active_statuses:
                continue
            if not issue.assignee:
                continue
                
            # Use updated_at or created_at if missing
            updated_at = getattr(issue, "updated_at", None) or issue.created_at
            if isinstance(updated_at, datetime):
                # Ensure it's offset-aware for comparison
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                else:
                    updated_at = updated_at.astimezone(timezone.utc)
                    
                if updated_at <= cutoff:
                    days = (datetime.now(timezone.utc) - updated_at).days
                    stale.append(
                        StaleWorkMetric(
                            issue_id=issue.id,
                            title=issue.title,
                            owner_name=issue.assignee.name,
                            days_stale=days,
                        )
                    )
        
        stale.sort(key=lambda x: x.days_stale, reverse=True)
        return stale

    def sprint_board(self, data: DataManager, project_id: str | None = None) -> SprintBoardMetricSet:
        configured = set(self.config.kanban_statuses)
        all_issues = data.get_issues()
        if project_id:
            all_issues = [issue for issue in all_issues if issue.project_id == project_id]
        columns = []
        for status in self.config.kanban_statuses:
            columns.append(
                SprintColumnMetric(
                    status=status,
                    issues=[issue for issue in all_issues if issue.status == status],
                )
            )

        overflow_issues = [issue for issue in all_issues if issue.status not in configured]
        if overflow_issues:
            overflow_issues.sort(key=lambda issue: (issue.status, issue.id))
            columns.append(
                SprintColumnMetric(
                    status=self.config.sprint_overflow_column_label,
                    issues=overflow_issues,
                )
            )
        return SprintBoardMetricSet(columns=columns, risk=self._sprint_risk(data, all_issues))

    def blocked_board(self, data: DataManager, project_id: str | None = None) -> SprintBoardMetricSet:
        all_issues = data.get_issues()
        if project_id:
            all_issues = [issue for issue in all_issues if issue.project_id == project_id]
        
        blocked_issues = []
        for issue in all_issues:
            is_blocked = "blocked" in issue.status.lower()
            if is_blocked:
                blocked_issues.append(issue)
                continue
            
            pull_requests = data.get_pull_requests(issue.id)
            has_failing_pr = False
            for pr in pull_requests:
                if not self._pull_request_is_open(pr):
                    continue
                checks = data.get_ci_checks(pr.id)
                if any(self._check_is_failing(check) for check in checks):
                    has_failing_pr = True
                    break
            
            if has_failing_pr:
                blocked_issues.append(issue)

        # Sort by creation date (oldest first to highlight stale work)
        blocked_issues.sort(key=lambda x: x.created_at or datetime.min.replace(tzinfo=timezone.utc))

        columns = []
        for status in self.config.kanban_statuses:
            issues = [issue for issue in blocked_issues if issue.status == status]
            if issues:
                columns.append(SprintColumnMetric(status=status, issues=issues))
        
        configured = set(self.config.kanban_statuses)
        overflow_issues = [issue for issue in blocked_issues if issue.status not in configured]
        if overflow_issues:
            columns.append(SprintColumnMetric(status="Overflow", issues=overflow_issues))

        return SprintBoardMetricSet(columns=columns, risk=self._sprint_risk(data, all_issues))

    def workload(self, data: DataManager, project_id: str | None = None) -> WorkloadMetricSet:
        users = data.users
        issues = data.issues
        if project_id:
            issues = [issue for issue in issues if issue.project_id == project_id]
        member_metrics: list[WorkloadMemberMetric] = []
        utilization_map: dict[str, int] = {}
        points_map: dict[str, int] = {}

        for user in users:
            user_issues = [i for i in issues if i.assignee and i.assignee.id == user.id]
            points = sum(i.points for i in user_issues)
            capacity = self._user_capacity(user)
            utilization = int((points / capacity) * 100) if capacity else 0
            status_text, status_color = self._utilization_status(utilization)
            member_metrics.append(
                WorkloadMemberMetric(
                    name=user.name,
                    allocation_bar=self._utilization_bar(utilization),
                    points=points,
                    capacity=capacity,
                    utilization_pct=utilization,
                    status_text=status_text,
                    status_color=status_color,
                    issues_preview=self._issues_preview(user_issues),
                )
            )
            utilization_map[user.name] = utilization
            points_map[user.name] = points

        total_points = sum(points_map.values())
        total_capacity = sum(self._user_capacity(user) for user in users)
        total_util = int((total_points / total_capacity) * 100) if total_capacity else 0
        team_status_markup = self._team_status_markup(total_util)

        team_metric = WorkloadTeamMetric(
            allocation_bar=self._utilization_bar(total_util),
            total_points=total_points,
            total_capacity=total_capacity,
            utilization_pct=total_util,
            status_markup=team_status_markup,
            active_issues=self._active_count(issues),
        )

        recommendations = self._recommendations(utilization_map, points_map, total_util)
        return WorkloadMetricSet(members=member_metrics, team=team_metric, recommendations=recommendations)

    def timeline(self, data: DataManager, project_id: str | None = None) -> TimelineMetricSet:
        projects = self._timeline_projects(data.get_projects(), project_id=project_id)
        issues = data.get_issues()
        if project_id:
            issues = [issue for issue in issues if issue.project_id == project_id]
        lines: list[TimelineProjectMetric] = []
        done_statuses = {s.lower() for s in self.config.done_statuses}
        for project in projects:
            project_issues = [issue for issue in issues if issue.project_id == project.id]
            total_points = max(1, sum(issue.points for issue in project_issues))
            done_points = sum(issue.points for issue in project_issues if issue.status.lower() in done_statuses)
            progress_pct = int((done_points / total_points) * 100) if total_points else 0
            due_date = self._parse_date(project.due_date)
            due_label = due_date.isoformat() if due_date else "N/A"
            remaining = self._days_remaining_label(due_date)
            blocked_count = self._count_blocked_issues(project_issues)
            lines.append(
                TimelineProjectMetric(
                    project_id=project.id,
                    name=project.name,
                    due_date_label=due_label,
                    days_remaining_label=remaining,
                    progress_bar=self._utilization_bar(progress_pct),
                    done_points=done_points,
                    total_points=total_points,
                    status_color=self._timeline_color(due_date),
                    blocked_count=blocked_count,
                )
            )

        subtitle = f"Horizon: {self.config.timeline_horizon_days}d  Projects: {len(lines)}"
        return TimelineMetricSet(
            title="ROADMAP & DELIVERY OUTLOOK",
            subtitle=subtitle,
            project_lines=lines,
        )

    def _timeline_projects(self, projects: list[Project], project_id: str | None = None) -> list[Project]:
        if project_id:
            return [project for project in projects if project.id == project_id][:1]
        today = date.today()
        horizon = self.config.timeline_horizon_days

        def sort_key(project):
            parsed = self._parse_date(project.due_date)
            return (parsed is None, parsed or date.max)

        sorted_projects = sorted(projects, key=sort_key)
        horizon_projects = []
        for project in sorted_projects:
            parsed = self._parse_date(project.due_date)
            if parsed is None:
                horizon_projects.append(project)
                continue
            if (parsed - today).days <= horizon:
                horizon_projects.append(project)
        return horizon_projects[: self.config.timeline_max_projects]

    def _active_count(self, issues: list[Issue]) -> int:
        active = {status.lower() for status in self.config.active_statuses}
        return sum(1 for issue in issues if issue.status.lower() in active)

    def _count_blocked_issues(self, issues: list[Issue]) -> int:
        return sum(1 for issue in issues if "blocked" in issue.status.lower())

    def _sprint_risk(self, data: DataManager, issues: list[Issue]) -> SprintRiskMetric:
        blocked_issues = self._count_blocked_issues(issues)
        issue_ids = {issue.id for issue in issues}
        linked_pull_requests: list[PullRequest] = []
        if hasattr(data, "get_pull_requests"):
            linked_pull_requests = [
                pull_request
                for pull_request in data.get_pull_requests()
                if pull_request.issue_id and pull_request.issue_id in issue_ids
            ]

        failing_prs = 0
        stale_reviews = 0
        stale_cutoff = datetime.now(timezone.utc) - timedelta(days=self.config.sprint_risk_stale_review_days)
        for pull_request in linked_pull_requests:
            if not self._pull_request_is_open(pull_request):
                continue
            checks = data.get_ci_checks(pull_request.id) if hasattr(data, "get_ci_checks") else []
            if any(self._check_is_failing(check) for check in checks):
                failing_prs += 1
            stamp = self._parse_timestamp(pull_request.updated_at) or self._parse_timestamp(pull_request.opened_at)
            if stamp is not None and stamp <= stale_cutoff:
                stale_reviews += 1

        overloaded_owners = self._count_overloaded_owners(issues)

        return SprintRiskMetric(
            blocked_issues=blocked_issues,
            failing_prs=failing_prs,
            stale_reviews=stale_reviews,
            overloaded_owners=overloaded_owners,
            blocked_breached=blocked_issues >= self.config.sprint_risk_blocked_threshold,
            failing_prs_breached=failing_prs >= self.config.sprint_risk_failing_pr_threshold,
            stale_reviews_breached=stale_reviews >= self.config.sprint_risk_stale_review_threshold,
            overloaded_owners_breached=(
                overloaded_owners >= self.config.sprint_risk_overloaded_owners_threshold
            ),
        )

    def _count_overloaded_owners(self, issues: list[Issue]) -> int:
        points_by_owner: dict[str, int] = {}
        users_by_owner: dict[str, User] = {}
        for issue in issues:
            if issue.assignee is None:
                continue
            owner_key = issue.assignee.id or issue.assignee.name
            points_by_owner[owner_key] = points_by_owner.get(owner_key, 0) + max(0, issue.points)
            users_by_owner[owner_key] = issue.assignee

        overloaded = 0
        for owner_key, points in points_by_owner.items():
            user = users_by_owner[owner_key]
            capacity = self._user_capacity(user)
            if capacity <= 0:
                continue
            utilization = int((points / capacity) * 100)
            if utilization >= self.config.sprint_risk_overloaded_utilization_pct:
                overloaded += 1
        return overloaded

    def _velocity_points(self, issues: list[Issue]) -> int:
        done = {status.lower() for status in self.config.done_statuses}
        return sum(issue.points for issue in issues if issue.status.lower() in done)

    def _user_capacity(self, user: User) -> int:
        return self.config.user_capacity_overrides.get(user.id, self.config.user_capacity_overrides.get(user.name, self.config.default_user_capacity_points))

    def _utilization_status(self, utilization: int) -> tuple[str, str]:
        if utilization >= self.config.workload_critical_pct:
            return WorkloadStatus.OVERALLOCATED, "#ff0000"
        if utilization >= self.config.workload_warning_pct:
            return WorkloadStatus.AT_CAPACITY, "#ffff00"
        return WorkloadStatus.AVAILABLE, "#00ff00"

    def _utilization_bar(self, utilization: int) -> str:
        width = self.config.workload_bar_width
        capped = max(0, min(utilization, 100))
        filled = int((capped / 100) * width)
        return "█" * filled + "░" * (width - filled)

    def _issues_preview(self, issues: list[Issue]) -> str:
        if not issues:
            return "-"
        limited = issues[: self.config.workload_issue_preview_limit]
        preview = "\n".join(f"• {issue.id} ({issue.points}pt)" for issue in limited)
        overflow = len(issues) - len(limited)
        if overflow > 0:
            preview += f"\n+ {overflow} more"
        return preview

    def _team_status_markup(self, utilization: int) -> str:
        if utilization >= self.config.workload_critical_pct:
            return "[bold #ff0000]CRITICAL[/]"
        if utilization >= self.config.workload_warning_pct:
            return "[bold #ffff00]AT CAPACITY[/]"
        return "[bold #00ff00]OK[/]"

    def _recommendations(
        self, utilization_map: dict[str, int], points_map: dict[str, int], total_util: int
    ) -> list[str]:
        overloaded = sorted(
            (name for name, util in utilization_map.items() if util >= self.config.workload_critical_pct),
            key=lambda name: utilization_map[name],
            reverse=True,
        )
        available = sorted(
            (name for name, util in utilization_map.items() if util < self.config.workload_warning_pct),
            key=lambda name: utilization_map[name],
        )

        recommendations: list[str] = []
        if overloaded and available:
            donor = overloaded[0]
            receiver = available[0]
            points_to_move = max(1, (points_map.get(donor, 0) - points_map.get(receiver, 0)) // 4)
            recommendations.append(
                f"Reassign around {points_to_move} pts from {donor} to {receiver} to reduce peak load."
            )

        if total_util >= self.config.workload_critical_pct:
            recommendations.append(
                "Current sprint load is above target capacity. De-scope or add temporary support."
            )
        elif not recommendations:
            recommendations.append("Load distribution is healthy. Keep monitoring as new issues are added.")

        return recommendations

    def _parse_date(self, value: str | None) -> date | None:
        if not value or value == "N/A":
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None

    def _parse_timestamp(self, value: str | None) -> datetime | None:
        if not value:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _pull_request_is_open(pull_request: PullRequest) -> bool:
        state = (pull_request.state or "").casefold()
        return state not in {PullRequestState.CLOSED, PullRequestState.MERGED}

    @staticmethod
    def _check_is_failing(check: CiCheck) -> bool:
        status = (check.status or "").casefold()
        if status != "completed":
            return False
        conclusion = (check.conclusion or "").casefold()
        return conclusion not in {CiConclusion.SUCCESS, CiConclusion.NEUTRAL, CiConclusion.SKIPPED, ""}

    def _days_remaining_label(self, due_date: date | None) -> str:
        if due_date is None:
            return "No due date"
        days = (due_date - date.today()).days
        if days < 0:
            return f"{abs(days)}d overdue"
        if days == 0:
            return "Due today"
        return f"{days}d left"

    def _timeline_color(self, due_date: date | None) -> str:
        if due_date is None:
            return "#666666"
        days = (due_date - date.today()).days
        if days < 0:
            return "#ff0000"
        if days <= 7:
            return "#ffff00"
        return "#00ff00"
