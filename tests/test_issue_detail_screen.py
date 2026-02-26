from __future__ import annotations

from datetime import datetime

import pytest

from projectdash.models import Issue, User, Project
from projectdash.views.issue_detail import IssueDetailScreen


def _issue(
    issue_id: str = "PROJ-1",
    title: str = "Test issue",
    *,
    status: str = "In Progress",
    priority: str = "2",
    assignee: User | None = None,
    points: int = 3,
    project_id: str | None = "p1",
    description: str | None = None,
    due_date: str | None = "2024-03-01",
    team_id: str | None = "team-1",
    linear_id: str | None = "lin-abc",
    created_at: datetime | None = None,
) -> Issue:
    return Issue(
        id=issue_id,
        title=title,
        priority=priority,
        status=status,
        assignee=assignee,
        points=points,
        project_id=project_id,
        description=description,
        due_date=due_date,
        team_id=team_id,
        linear_id=linear_id,
        created_at=created_at or datetime(2024, 1, 15),
    )


class TestIssueDetailScreenPriorityLabel:
    def test_numeric_priorities_map_to_labels(self) -> None:
        screen = IssueDetailScreen(_issue())
        assert screen._priority_label("0") == "No Priority"
        assert screen._priority_label("1") == "Urgent"
        assert screen._priority_label("2") == "High"
        assert screen._priority_label("3") == "Medium"
        assert screen._priority_label("4") == "Low"

    def test_empty_priority_returns_dash(self) -> None:
        screen = IssueDetailScreen(_issue())
        assert screen._priority_label("") == "–"

    def test_unknown_priority_returned_as_is(self) -> None:
        screen = IssueDetailScreen(_issue())
        assert screen._priority_label("critical") == "critical"


class TestIssueDetailScreenDescription:
    def test_issue_with_description_is_stored(self) -> None:
        desc = "This is a detailed description of the issue."
        issue = _issue(description=desc)
        screen = IssueDetailScreen(issue)
        assert screen.issue.description == desc

    def test_issue_without_description_is_none(self) -> None:
        issue = _issue(description=None)
        screen = IssueDetailScreen(issue)
        assert screen.issue.description is None

    def test_issue_with_empty_description(self) -> None:
        issue = _issue(description="")
        screen = IssueDetailScreen(issue)
        assert screen.issue.description == ""


class TestIssueDetailScreenMetadata:
    def test_screen_holds_correct_issue(self) -> None:
        alice = User("u1", "Alice")
        issue = _issue(
            "PROJ-42",
            "Fix the bug",
            status="Review",
            priority="1",
            assignee=alice,
            points=5,
        )
        screen = IssueDetailScreen(issue)
        assert screen.issue.id == "PROJ-42"
        assert screen.issue.title == "Fix the bug"
        assert screen.issue.status == "Review"
        assert screen.issue.priority == "1"
        assert screen.issue.assignee is alice
        assert screen.issue.points == 5

    def test_screen_uses_linear_id_when_set(self) -> None:
        issue = _issue(linear_id="lin-xyz")
        screen = IssueDetailScreen(issue)
        assert screen.issue.linear_id == "lin-xyz"

    def test_screen_falls_back_to_issue_id_when_no_linear_id(self) -> None:
        issue = _issue(issue_id="PROJ-99", linear_id=None)
        screen = IssueDetailScreen(issue)
        assert screen.issue.linear_id is None
        assert screen.issue.id == "PROJ-99"


class TestIssueModel:
    def test_issue_description_defaults_to_none(self) -> None:
        issue = Issue(id="X-1", title="No desc", priority="2", status="Todo")
        assert issue.description is None

    def test_issue_with_description(self) -> None:
        issue = Issue(
            id="X-2",
            title="Has desc",
            priority="3",
            status="In Progress",
            description="Some detailed text here.",
        )
        assert issue.description == "Some detailed text here."

    def test_issue_description_persists_through_copy(self) -> None:
        issue = Issue(
            id="X-3",
            title="Copy test",
            priority="2",
            status="Todo",
            description="Keep this.",
        )
        screen = IssueDetailScreen(issue)
        assert screen.issue.description == "Keep this."


class TestMockDataDescriptions:
    """Verify that mock data seeds provide descriptions for issues."""

    @pytest.mark.asyncio
    async def test_seed_then_load_preserves_descriptions(self, tmp_path) -> None:
        from projectdash.config import AppConfig
        from projectdash.data import DataManager
        from projectdash.database import Database

        config = AppConfig(seed_mock_data=True)
        manager = DataManager(config)
        manager.db = Database(db_path=tmp_path / "test.db")

        await manager.db.init_db()
        await manager.seed_mock_data()
        await manager.load_from_cache()

        issues_with_desc = [i for i in manager.issues if i.description]
        assert len(issues_with_desc) > 0, "At least some mock issues should have descriptions"
        # Verify a known issue has the expected description substring
        login_bug = next((i for i in manager.issues if i.id == "PROJ-245"), None)
        assert login_bug is not None
        assert login_bug.description is not None
        assert "login" in login_bug.description.lower() or "2fa" in login_bug.description.lower()

    @pytest.mark.asyncio
    async def test_all_mock_issues_have_descriptions(self, tmp_path) -> None:
        from projectdash.config import AppConfig
        from projectdash.data import DataManager
        from projectdash.database import Database

        config = AppConfig(seed_mock_data=True)
        manager = DataManager(config)
        manager.db = Database(db_path=tmp_path / "test_all.db")

        await manager.db.init_db()
        await manager.seed_mock_data()
        await manager.load_from_cache()

        assert len(manager.issues) == 13, "Expected 13 mock issues"
        issues_without_desc = [i for i in manager.issues if not i.description]
        assert issues_without_desc == [], "All mock issues should have descriptions"
