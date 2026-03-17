from dataclasses import dataclass

from projectdash.config import AppConfig
from projectdash.models import CiCheck, Issue, Project, PullRequest, User
from projectdash.services.metrics import MetricsService


@dataclass
class DummyData:
    users: list[User]
    projects: list[Project]
    issues: list[Issue]
    pull_requests: list[PullRequest]
    ci_checks: list[CiCheck]

    def get_users(self) -> list[User]:
        return self.users

    def get_projects(self) -> list[Project]:
        return self.projects

    def get_issues(self) -> list[Issue]:
        return self.issues

    def get_issues_by_status(self, status: str) -> list[Issue]:
        return [issue for issue in self.issues if issue.status == status]

    def get_pull_requests(self, issue_id: str | None = None) -> list[PullRequest]:
        if issue_id is None:
            return self.pull_requests
        return [pull_request for pull_request in self.pull_requests if pull_request.issue_id == issue_id]

    def get_ci_checks(self, pull_request_id: str | None = None) -> list[CiCheck]:
        if pull_request_id is None:
            return self.ci_checks
        return [check for check in self.ci_checks if check.pull_request_id == pull_request_id]


def _sample_data() -> DummyData:
    users = [User("u1", "Alice"), User("u2", "Bob")]
    projects = [
        Project("p1", "API", "Active", 0, 0, 0, "2026-03-01", "Current"),
        Project("p2", "UI", "Active", 0, 0, 0, "2026-03-10", "Current"),
    ]
    issues = [
        Issue("A-1", "Task 1", "High", "Todo", users[0], 3, "p1", "2026-02-28"),
        Issue("A-2", "Task 2", "Medium", "In Progress", users[0], 5, "p1", "2026-02-27"),
        Issue("A-3", "Task 3", "Low", "Done", users[1], 2, "p1", "2026-02-26"),
        Issue("B-1", "Task 4", "Low", "Blocked", None, 1, "p2", "2026-03-02"),
    ]
    pull_requests = [
        PullRequest(
            id="pr-1",
            provider="github",
            repository_id="github:acme/api",
            number=1,
            title="PR one",
            state="open",
            issue_id="A-2",
            updated_at="2026-02-20T00:00:00Z",
        ),
        PullRequest(
            id="pr-2",
            provider="github",
            repository_id="github:acme/api",
            number=2,
            title="PR two",
            state="open",
            issue_id="B-1",
            updated_at="2026-03-11T00:00:00Z",
        ),
    ]
    ci_checks = [
        CiCheck(
            id="check-1",
            provider="github",
            pull_request_id="pr-1",
            name="ci",
            status="completed",
            conclusion="failure",
        ),
        CiCheck(
            id="check-2",
            provider="github",
            pull_request_id="pr-2",
            name="ci",
            status="completed",
            conclusion="success",
        ),
    ]
    return DummyData(users=users, projects=projects, issues=issues, pull_requests=pull_requests, ci_checks=ci_checks)


def test_sprint_board_adds_overflow_column() -> None:
    data = _sample_data()
    config = AppConfig(
        kanban_statuses=("Todo", "In Progress", "Done"),
        sprint_overflow_column_label="Other",
    )
    metrics = MetricsService(config).sprint_board(data)
    assert [column.status for column in metrics.columns] == ["Todo", "In Progress", "Done", "Other"]
    assert [issue.id for issue in metrics.columns[-1].issues] == ["B-1"]


def test_dashboard_and_workload_metrics_are_data_driven() -> None:
    data = _sample_data()
    config = AppConfig(default_user_capacity_points=10)
    service = MetricsService(config)

    dashboard = service.dashboard(data)
    assert dashboard.projects_total == 2
    assert dashboard.issues_total == 4
    assert dashboard.velocity_points == 2
    assert dashboard.blocked_total == 1

    workload = service.workload(data)
    assert len(workload.members) == 2
    assert workload.team.total_points == 10
    assert workload.team.total_capacity == 20
    assert workload.team.utilization_pct == 50
    assert workload.team.active_issues == 1


def test_workload_active_issues_uses_configured_active_statuses() -> None:
    data = _sample_data()
    config = AppConfig(default_user_capacity_points=10, active_statuses=("Todo", "Blocked"))
    service = MetricsService(config)

    workload = service.workload(data)

    # Todo + Blocked should count as active for this custom configuration.
    assert workload.team.active_issues == 2


def test_metrics_support_project_scope_filtering() -> None:
    data = _sample_data()
    config = AppConfig(kanban_statuses=("Todo", "In Progress", "Done"))
    service = MetricsService(config)

    dashboard = service.dashboard(data, project_id="p1")
    assert dashboard.projects_total == 1
    assert dashboard.issues_total == 3
    assert [card.project_id for card in dashboard.project_cards] == ["p1"]

    sprint = service.sprint_board(data, project_id="p1")
    assert [len(column.issues) for column in sprint.columns] == [1, 1, 1]
    assert [column.status for column in sprint.columns] == ["Todo", "In Progress", "Done"]

    timeline = service.timeline(data, project_id="p1")
    assert len(timeline.project_lines) == 1
    assert timeline.project_lines[0].project_id == "p1"

    workload = service.workload(data, project_id="p1")
    assert workload.team.total_points == 10
    assert workload.team.active_issues == 1


def test_sprint_risk_metrics_count_and_thresholds() -> None:
    data = _sample_data()
    config = AppConfig(
        default_user_capacity_points=10,
        sprint_risk_blocked_threshold=1,
        sprint_risk_failing_pr_threshold=1,
        sprint_risk_stale_review_days=3,
        sprint_risk_stale_review_threshold=1,
        sprint_risk_overloaded_owners_threshold=1,
        sprint_risk_overloaded_utilization_pct=80,
    )
    service = MetricsService(config)

    sprint = service.sprint_board(data)

    assert sprint.risk.blocked_issues == 1
    assert sprint.risk.failing_prs == 1
    assert sprint.risk.stale_reviews == 2
    assert sprint.risk.overloaded_owners == 1
    assert sprint.risk.blocked_breached is True
    assert sprint.risk.failing_prs_breached is True
    assert sprint.risk.stale_reviews_breached is True
    assert sprint.risk.overloaded_owners_breached is True
