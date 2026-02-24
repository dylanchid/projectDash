from __future__ import annotations

from projectdash.models import Issue, User
from projectdash.services.metrics import SprintColumnMetric
from projectdash.views.sprint_board import SprintBoardView


def _issue(
    issue_id: str,
    title: str,
    assignee: User | None = None,
    *,
    status: str = "Todo",
    priority: str = "Medium",
    project_id: str | None = None,
) -> Issue:
    return Issue(
        id=issue_id,
        title=title,
        priority=priority,
        status=status,
        assignee=assignee,
        points=3,
        project_id=project_id,
    )


def test_move_cursor_wraps_across_columns(monkeypatch) -> None:
    view = SprintBoardView()
    alice = User("u1", "Alice")
    bob = User("u2", "Bob")
    view.column_metrics = [
        SprintColumnMetric(status="Todo", issues=[_issue("T-1", "One", alice)]),
        SprintColumnMetric(status="Done", issues=[_issue("D-1", "Two", bob)]),
    ]
    monkeypatch.setattr(view, "refresh_view", lambda: None)

    view.cursor_col = 0
    view.move_cursor(col_delta=-1)
    assert view.cursor_col == 1
    assert view.selected_issue_id == "D-1"

    view.move_cursor(col_delta=1)
    assert view.cursor_col == 0
    assert view.selected_issue_id == "T-1"


def test_filter_columns_matches_id_title_and_assignee() -> None:
    view = SprintBoardView()
    alice = User("u1", "Alice")
    todo = SprintColumnMetric(
        status="Todo",
        issues=[_issue("PD-1", "Fix login bug", alice), _issue("PD-2", "Docs cleanup")],
    )
    done = SprintColumnMetric(status="Done", issues=[_issue("PD-3", "Release checklist")])

    by_id = view._filter_columns([todo, done], "pd-3")
    assert [issue.id for issue in by_id[1].issues] == ["PD-3"]

    by_title = view._filter_columns([todo, done], "login")
    assert [issue.id for issue in by_title[0].issues] == ["PD-1"]

    by_assignee = view._filter_columns([todo, done], "alice")
    assert [issue.id for issue in by_assignee[0].issues] == ["PD-1"]


def test_filter_columns_supports_keyed_status_priority_assignee() -> None:
    view = SprintBoardView()
    alice = User("u1", "Alice")
    bob = User("u2", "Bob")
    todo = SprintColumnMetric(
        status="Todo",
        issues=[
            _issue(
                "PD-10",
                "Ship release",
                alice,
                status="In Progress",
                priority="High",
                project_id="p1",
            ),
            _issue(
                "PD-11",
                "QA pass",
                bob,
                status="Review",
                priority="High",
                project_id="p1",
            ),
        ],
    )
    done = SprintColumnMetric(
        status="Done",
        issues=[
            _issue(
                "PD-12",
                "Publish changelog",
                alice,
                status="Done",
                priority="Medium",
                project_id="p2",
            ),
        ],
    )

    filtered = view._filter_columns(
        [todo, done],
        'status:"in progress" priority:high assignee:alice',
    )

    assert [issue.id for issue in filtered[0].issues] == ["PD-10"]
    assert filtered[1].issues == []


def test_filter_columns_supports_mixed_text_and_keyed_terms() -> None:
    view = SprintBoardView()
    alice = User("u1", "Alice")
    todo = SprintColumnMetric(
        status="Todo",
        issues=[
            _issue("PD-20", "Fix login guard", alice, status="Todo", priority="High"),
            _issue("PD-21", "Fix login docs", alice, status="Done", priority="High"),
            _issue("PD-22", "Refactor auth", alice, status="Todo", priority="Low"),
        ],
    )

    filtered = view._filter_columns([todo], "fix status:todo priority:high")

    assert [issue.id for issue in filtered[0].issues] == ["PD-20"]


def test_jump_to_my_issue_uses_identity_candidates(monkeypatch) -> None:
    view = SprintBoardView()
    view.column_metrics = [
        SprintColumnMetric(
            status="Todo",
            issues=[_issue("PD-9", "Infra", User("u2", "Bob")), _issue("PD-11", "Polish", User("u3", "Dylan"))],
        ),
        SprintColumnMetric(status="Done", issues=[_issue("PD-12", "Ship", User("u4", "Eve"))]),
    ]
    monkeypatch.setattr(view, "refresh_view", lambda: None)
    monkeypatch.setenv("PD_ME", "Dylan")

    ok, message = view.jump_to_my_issue()

    assert ok is True
    assert "PD-11" in message
    assert view.cursor_col == 0
    assert view.cursor_row == 1
    assert view.selected_issue_id == "PD-11"
