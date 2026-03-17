from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from rich.text import Text

from projectdash.models import Issue, User
from projectdash.services.metrics import SprintColumnMetric, SprintRiskMetric
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


def test_open_and_close_detail_toggle_sidebar_width(monkeypatch) -> None:
    view = SprintBoardView()
    monkeypatch.setattr(view, "_refresh_detail_panel", lambda: None)
    monkeypatch.setattr(view, "_apply_detail_layout", lambda: None)

    assert view._detail_sidebar_width_cells() == view.COMPACT_SIDEBAR_WIDTH

    view.open_selected_issue_detail()
    assert view.detail_open is True
    assert view._detail_sidebar_width_cells() == view.EXPANDED_SIDEBAR_WIDTH

    view.close_issue_detail()
    assert view.detail_open is False
    assert view._detail_sidebar_width_cells() == view.COMPACT_SIDEBAR_WIDTH


def test_open_detail_keeps_focus_open(monkeypatch) -> None:
    view = SprintBoardView()
    monkeypatch.setattr(view, "_refresh_detail_panel", lambda: None)
    monkeypatch.setattr(view, "_apply_detail_layout", lambda: None)

    assert view.detail_open is False
    view.open_detail()
    assert view.detail_open is True
    view.open_detail()
    assert view.detail_open is True


def test_linear_issue_url_uses_workspace_env(monkeypatch) -> None:
    view = SprintBoardView()
    monkeypatch.setenv("PD_LINEAR_WORKSPACE", "acme")

    url = view._linear_issue_url(_issue("PD-70", "Investigate latency"))

    assert url == "https://linear.app/acme/issue/PD-70"


@pytest.mark.asyncio
async def test_close_selected_issue_cycles_until_done(monkeypatch) -> None:
    view = SprintBoardView()
    issue = _issue("PD-30", "Ship release", status="Todo")
    view.column_metrics = [SprintColumnMetric(status="Todo", issues=[issue])]
    calls: list[str] = []

    async def fake_cycle(issue_id: str, statuses: tuple[str, ...]):
        calls.append(issue_id)
        current_index = statuses.index(issue.status)
        issue.status = statuses[(current_index + 1) % len(statuses)]
        return True, "ok"

    fake_app = SimpleNamespace(
        config=SimpleNamespace(
            kanban_statuses=("Todo", "In Progress", "Done"),
            done_statuses=("Done",),
        ),
        data_manager=SimpleNamespace(cycle_issue_status=fake_cycle),
    )
    monkeypatch.setattr(SprintBoardView, "app", property(lambda self: fake_app))
    monkeypatch.setattr(view, "refresh_view", lambda: None)

    ok, message = await view.close_selected_issue()

    assert ok is True
    assert "closed" in message
    assert issue.status == "Done"
    assert calls == ["PD-30", "PD-30"]


def test_triage_filters_compose_mine_blocked_failing_and_stale(monkeypatch) -> None:
    view = SprintBoardView()
    dylan = User("u1", "Dylan")
    other = User("u2", "Alex")
    match = _issue("PD-50", "Blocked failing", dylan, status="Blocked", priority="High")
    match.created_at = datetime.now() - timedelta(days=10)
    wrong_owner = _issue("PD-51", "Blocked failing", other, status="Blocked", priority="High")
    wrong_owner.created_at = datetime.now() - timedelta(days=10)
    no_failing = _issue("PD-52", "Blocked no failing", dylan, status="Blocked", priority="High")
    no_failing.created_at = datetime.now() - timedelta(days=10)
    fresh = _issue("PD-53", "Blocked fresh", dylan, status="Blocked", priority="High")
    fresh.created_at = datetime.now() - timedelta(days=1)

    pr = SimpleNamespace(id="pr-1")
    check_fail = SimpleNamespace(status="completed", conclusion="failure")
    check_pass = SimpleNamespace(status="completed", conclusion="success")

    data_manager = SimpleNamespace(
        get_pull_requests=lambda issue_id=None: [pr] if issue_id in {"PD-50", "PD-51", "PD-53"} else [],
        get_ci_checks=lambda pull_request_id=None: [check_fail] if pull_request_id == "pr-1" else [check_pass],
    )
    fake_app = SimpleNamespace(
        config=SimpleNamespace(done_statuses=("Done",)),
        data_manager=data_manager,
    )
    monkeypatch.setattr(SprintBoardView, "app", property(lambda self: fake_app))
    monkeypatch.setenv("PD_ME", "Dylan")
    monkeypatch.setenv("PD_TRIAGE_STALE_DAYS", "7")

    view.triage_filters = {"mine", "blocked", "failing", "stale"}
    filtered = view._filter_columns(
        [SprintColumnMetric(status="Todo", issues=[match, wrong_owner, no_failing, fresh])],
        "",
    )

    assert [issue.id for issue in filtered[0].issues] == ["PD-50"]


def test_clear_and_restore_triage_filters(monkeypatch) -> None:
    view = SprintBoardView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)
    view.triage_filters = {"mine", "blocked"}

    ok, message = view.clear_triage_filters()
    assert ok is True
    assert "cleared" in message
    assert view.triage_filters == set()

    ok, message = view.restore_triage_filters()
    assert ok is True
    assert "restored" in message
    assert view.triage_filters == {"mine", "blocked"}


def test_sprint_risk_text_shows_thresholds_and_breach_emphasis(monkeypatch) -> None:
    view = SprintBoardView()
    fake_app = SimpleNamespace(
        config=SimpleNamespace(
            sprint_risk_blocked_threshold=1,
            sprint_risk_failing_pr_threshold=2,
            sprint_risk_stale_review_threshold=1,
            sprint_risk_stale_review_days=3,
            sprint_risk_overloaded_owners_threshold=1,
            sprint_risk_overloaded_utilization_pct=80,
        )
    )
    monkeypatch.setattr(SprintBoardView, "app", property(lambda self: fake_app))

    text = view._sprint_risk_text(
        SprintRiskMetric(
            blocked_issues=2,
            failing_prs=1,
            stale_reviews=1,
            overloaded_owners=0,
            blocked_breached=True,
            failing_prs_breached=False,
            stale_reviews_breached=True,
            overloaded_owners_breached=False,
        )
    )
    plain = text.plain

    assert "Risk:" in plain
    assert "blocked 2 [BREACH >=1]" in plain
    assert "failing PRs 1 [ok >=2]" in plain
    assert "stale reviews 1 [BREACH >=1 @3d]" in plain
    assert "overloaded owners 0 [ok >=1 @80%]" in plain
    assert any(str(span.style) == "bold #ff5f5f" for span in text.spans)
    assert any(str(span.style) == "bold #5fd787" for span in text.spans)


def test_refresh_summary_panel_renders_full_summary_with_risk_and_load(monkeypatch) -> None:
    view = SprintBoardView()
    alice = User("u1", "Alice")
    bob = User("u2", "Bob")
    view.column_metrics = [
        SprintColumnMetric(status="Todo", issues=[_issue("PD-1", "One", alice), _issue("PD-2", "Two", bob)]),
        SprintColumnMetric(status="Done", issues=[_issue("PD-3", "Three", alice, status="Done")]),
    ]
    captured: list[Text] = []

    class _SummaryWidget:
        def update(self, value):
            captured.append(value)

    fake_app = SimpleNamespace(
        config=SimpleNamespace(
            sprint_risk_blocked_threshold=1,
            sprint_risk_failing_pr_threshold=1,
            sprint_risk_stale_review_threshold=1,
            sprint_risk_stale_review_days=3,
            sprint_risk_overloaded_owners_threshold=1,
            sprint_risk_overloaded_utilization_pct=80,
        )
    )
    monkeypatch.setattr(SprintBoardView, "app", property(lambda self: fake_app))
    monkeypatch.setattr(view, "query_one", lambda selector, _type=None: _SummaryWidget())

    view._refresh_summary_panel(
        SprintRiskMetric(
            blocked_issues=2,
            failing_prs=1,
            stale_reviews=1,
            overloaded_owners=1,
            blocked_breached=True,
            failing_prs_breached=True,
            stale_reviews_breached=True,
            overloaded_owners_breached=True,
        )
    )

    assert len(captured) == 1
    assert isinstance(captured[0], Text)
    summary = captured[0].plain
    assert "BOARD SUMMARY" in summary
    assert "Visible issues: 3" in summary
    assert "Risk:" in summary
    assert "blocked 2 [BREACH >=1]" in summary
    assert "failing PRs 1 [BREACH >=1]" in summary
    assert "stale reviews 1 [BREACH >=1 @3d]" in summary
    assert "overloaded owners 1 [BREACH >=1 @80%]" in summary
    assert "Todo" in summary
    assert "Done" in summary
    assert "Top load: Alice (2 issues)" in summary
