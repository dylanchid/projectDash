from datetime import date, datetime, timedelta
from types import SimpleNamespace
import pytest

from projectdash.views.dashboard import DashboardView
from projectdash.views.github_dashboard import GitHubDashboardView
from projectdash.views.sprint_board import SprintBoardView
from projectdash.views.timeline import TimelineView
from projectdash.views.workload import WorkloadView
from projectdash.views.ideation_gallery import IdeationGalleryView


def test_dashboard_mode_cycles_through_all_views(monkeypatch) -> None:
    view = DashboardView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)

    modes = []
    for _ in range(5):
        ok, _message = view.toggle_visual_mode()
        assert ok is True
        modes.append(view.visual_mode)

    assert modes == ["load-active", "risk", "priority", "compare", "load-total"]


def test_timeline_mode_cycles_through_all_views(monkeypatch) -> None:
    view = TimelineView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)

    modes = []
    for _ in range(4):
        ok, _message = view.toggle_visual_mode()
        assert ok is True
        modes.append(view.visual_mode)

    assert modes == ["risk", "progress", "blocked", "project"]


def test_workload_mode_cycles_through_all_views(monkeypatch) -> None:
    view = WorkloadView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)

    modes = []
    for _ in range(3):
        ok, _message = view.toggle_visual_mode()
        assert ok is True
        modes.append(view.visual_mode)

    assert modes == ["chart", "rebalance", "table"]


def test_core_views_expose_filter_and_help_bindings() -> None:
    sprint_keys = {binding[0] for binding in SprintBoardView.BINDINGS}
    timeline_keys = {binding[0] for binding in TimelineView.BINDINGS}
    workload_keys = {binding[0] for binding in WorkloadView.BINDINGS}

    assert "/" in sprint_keys
    assert "question_mark" in sprint_keys
    assert "/" in timeline_keys
    assert "question_mark" in timeline_keys
    assert "/" in workload_keys
    assert "question_mark" in workload_keys


def test_github_mode_cycles_through_all_views(monkeypatch) -> None:
    view = GitHubDashboardView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)

    modes = []
    for _ in range(3):
        ok, _message = view.toggle_visual_mode()
        assert ok is True
        modes.append(view.visual_mode)

    assert modes == ["prs", "checks", "repos"]


def test_ideation_mode_cycles_through_all_categories(monkeypatch) -> None:
    view = IdeationGalleryView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)

    modes = []
    for _ in range(6):
        ok, _message = view.toggle_visual_mode()
        assert ok is True
        modes.append(view.visual_mode)

    assert modes == ["delivery", "flow", "quality", "capacity", "portfolio", "all"]


def test_ideation_line_controls_work_for_line_concepts(monkeypatch) -> None:
    view = IdeationGalleryView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)
    view.selected_idea_id = "line-analytical"
    view._line_window_start = 0
    view._line_window_size = 8
    view._line_selected_series = 0

    ok, message = view.adjust_line_pan(1)
    assert ok is True
    assert "pan" in message
    assert view._line_window_start == 1

    ok, message = view.adjust_line_zoom(1)
    assert ok is True
    assert "zoom window" in message
    assert view._line_window_size == 7

    ok, message = view.cycle_line_series(1)
    assert ok is True
    assert "focus series" in message
    assert view._line_selected_series == 1


def test_ideation_line_controls_reject_non_line_concepts(monkeypatch) -> None:
    view = IdeationGalleryView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)
    view.selected_idea_id = "flow-aging-histogram"

    ok, message = view.adjust_line_pan(1)
    assert ok is False
    assert "line" in message.casefold()


def test_ideation_line_style_cycles(monkeypatch) -> None:
    view = IdeationGalleryView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)

    assert view._line_render_style == "classic"
    ok, message = view.cycle_line_render_style()
    assert ok is True
    assert "hires" in message
    assert view._line_render_style == "hires"


def test_dashboard_move_selection_cycles_cached_projects(monkeypatch) -> None:
    view = DashboardView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)
    view._project_order = ["p1", "p2", "p3"]

    view.selected_project_id = None
    view.move_selection(1)
    assert view.selected_project_id == "p1"

    view.move_selection(1)
    assert view.selected_project_id == "p2"

    view.move_selection(-1)
    assert view.selected_project_id == "p1"


def test_timeline_move_selection_requires_project_mode(monkeypatch) -> None:
    view = TimelineView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)
    view._project_order = ["p1", "p2"]
    view.selected_project_id = "p1"

    view.visual_mode = "risk"
    view.move_selection(1)
    assert view.selected_project_id == "p1"

    view.visual_mode = "project"
    view.move_selection(1)
    assert view.selected_project_id == "p2"


def test_timeline_capture_and_restore_filter_state(monkeypatch) -> None:
    view = TimelineView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)
    view.visual_mode = "blocked"
    view.graph_density = "detailed"
    view.project_scope_id = "p1"
    view.selected_project_id = "p1"
    view.selected_blocked_issue_id = "PD-1"
    view.blocked_assignee_mode = "mine"
    view.detail_open = True

    state = view.capture_filter_state()

    view.visual_mode = "project"
    view.graph_density = "compact"
    view.project_scope_id = None
    view.selected_project_id = None
    view.selected_blocked_issue_id = None
    view.blocked_assignee_mode = "all"
    view.detail_open = False

    view.restore_filter_state(state)

    assert view.visual_mode == "blocked"
    assert view.graph_density == "detailed"
    assert view.project_scope_id == "p1"
    assert view.selected_project_id == "p1"
    assert view.selected_blocked_issue_id == "PD-1"
    assert view.blocked_assignee_mode == "mine"
    assert view.detail_open is True


def test_timeline_blocked_queue_rows_sorted_by_age_and_filtered_by_scope(monkeypatch) -> None:
    view = TimelineView()
    now = datetime.now()
    issues = [
        SimpleNamespace(
            id="PD-1",
            title="Old blocker",
            status="Blocked",
            assignee=SimpleNamespace(name="Alice"),
            created_at=now - timedelta(days=8),
            project_id="p1",
        ),
        SimpleNamespace(
            id="PD-2",
            title="Recent blocker",
            status="Blocked",
            assignee=SimpleNamespace(name="Bob"),
            created_at=now - timedelta(days=2),
            project_id="p1",
        ),
        SimpleNamespace(
            id="PD-3",
            title="Other project blocker",
            status="Blocked",
            assignee=None,
            created_at=now - timedelta(days=10),
            project_id="p2",
        ),
        SimpleNamespace(
            id="PD-4",
            title="Not blocked",
            status="In Progress",
            assignee=SimpleNamespace(name="Alice"),
            created_at=now - timedelta(days=30),
            project_id="p1",
        ),
    ]
    projects = [SimpleNamespace(id="p1", name="API"), SimpleNamespace(id="p2", name="Web")]
    pull_requests = {
        "PD-1": [SimpleNamespace(id="pr-1")],
        "PD-2": [],
        "PD-3": [SimpleNamespace(id="pr-3")],
    }
    checks = {
        "pr-1": [SimpleNamespace(status="completed", conclusion="failure")],
        "pr-3": [SimpleNamespace(status="completed", conclusion="success")],
    }
    fake_dm = SimpleNamespace(
        get_issues=lambda: issues,
        get_projects=lambda: projects,
        get_pull_requests=lambda issue_id=None: pull_requests.get(issue_id, []),
        get_ci_checks=lambda pull_request_id=None: checks.get(pull_request_id, []),
    )
    monkeypatch.setattr(type(view), "app", property(lambda _self: SimpleNamespace(data_manager=fake_dm)))

    rows = view._blocked_queue_rows()
    assert [row.issue.id for row in rows] == ["PD-3", "PD-1", "PD-2"]
    assert rows[1].failing_checks == 1

    view.project_scope_id = "p1"
    scoped_rows = view._blocked_queue_rows()
    assert [row.issue.id for row in scoped_rows] == ["PD-1", "PD-2"]


def test_timeline_blocked_queue_assignee_filter_and_cluster_jump(monkeypatch) -> None:
    view = TimelineView()
    view.visual_mode = "blocked"
    now = datetime.now()
    issues = [
        SimpleNamespace(
            id="PD-10",
            title="A",
            status="Blocked",
            assignee=SimpleNamespace(name="Dylan"),
            created_at=now - timedelta(days=4),
            project_id="p1",
            priority="High",
            due_date=None,
        ),
        SimpleNamespace(
            id="PD-11",
            title="B",
            status="Blocked",
            assignee=SimpleNamespace(name="Alex"),
            created_at=now - timedelta(days=3),
            project_id="p1",
            priority="High",
            due_date=None,
        ),
        SimpleNamespace(
            id="PD-12",
            title="C",
            status="Blocked",
            assignee=None,
            created_at=now - timedelta(days=2),
            project_id="p2",
            priority="High",
            due_date=None,
        ),
    ]
    fake_dm = SimpleNamespace(
        get_issues=lambda: issues,
        get_projects=lambda: [SimpleNamespace(id="p1", name="API"), SimpleNamespace(id="p2", name="Web")],
        get_pull_requests=lambda issue_id=None: [],
        get_ci_checks=lambda pull_request_id=None: [],
    )
    monkeypatch.setattr(type(view), "app", property(lambda _self: SimpleNamespace(data_manager=fake_dm)))
    monkeypatch.setattr(view, "refresh_view", lambda: None)
    monkeypatch.setenv("PD_ME", "Dylan")

    rows = view._blocked_queue_rows()
    assert [row.issue.id for row in rows] == ["PD-10", "PD-11", "PD-12"]

    ok, _message = view.cycle_blocked_assignee_filter()
    assert ok is True
    mine_rows = view._blocked_queue_rows()
    assert [row.issue.id for row in mine_rows] == ["PD-10"]

    ok, _message = view.cycle_blocked_assignee_filter()
    assert ok is True
    unassigned_rows = view._blocked_queue_rows()
    assert [row.issue.id for row in unassigned_rows] == ["PD-12"]

    view.blocked_assignee_mode = "all"
    view.selected_blocked_issue_id = "PD-10"
    ok, message = view.jump_blocked_owner_cluster(1)
    assert ok is True
    assert "owner cluster" in message
    assert view.selected_blocked_issue_id == "PD-11"

    ok, message = view.jump_blocked_project_cluster(1)
    assert ok is True
    assert "project cluster" in message
    assert view.selected_blocked_issue_id == "PD-12"


def test_timeline_blocked_project_signals_and_drilldown(monkeypatch) -> None:
    view = TimelineView()
    now = datetime.now()
    issues = [
        SimpleNamespace(
            id="PD-20",
            title="Blocked 1",
            status="Blocked",
            assignee=SimpleNamespace(name="Dylan"),
            created_at=now - timedelta(days=5),
            project_id="p1",
            priority="High",
            due_date=None,
        ),
        SimpleNamespace(
            id="PD-21",
            title="Blocked 2",
            status="Blocked",
            assignee=SimpleNamespace(name="Alex"),
            created_at=now - timedelta(days=2),
            project_id="p1",
            priority="High",
            due_date=None,
        ),
    ]
    fake_dm = SimpleNamespace(
        get_issues=lambda: issues,
        get_projects=lambda: [SimpleNamespace(id="p1", name="API")],
        get_pull_requests=lambda issue_id=None: [SimpleNamespace(id="pr-1")] if issue_id == "PD-20" else [],
        get_ci_checks=lambda pull_request_id=None: [SimpleNamespace(status="completed", conclusion="failure")]
        if pull_request_id == "pr-1"
        else [],
    )
    monkeypatch.setattr(type(view), "app", property(lambda _self: SimpleNamespace(data_manager=fake_dm)))
    monkeypatch.setattr(view, "refresh_view", lambda: None)

    signals = view._blocked_project_signals()
    assert signals["p1"].blocked_count == 2
    assert signals["p1"].failing_checks == 1

    view.selected_project_id = "p1"
    ok, message = view.open_project_blocked_drilldown()
    assert ok is True
    assert "Blocked drilldown" in message
    assert view.visual_mode == "blocked"
    assert view.project_scope_id == "p1"
    assert view.selected_blocked_issue_id == "PD-20"


def test_workload_move_selection_cycles_cached_members(monkeypatch) -> None:
    view = WorkloadView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)
    view._member_order = ["Alice", "Bob"]

    view.selected_member = None
    view.move_selection(1)
    assert view.selected_member == "Alice"

    view.move_selection(1)
    assert view.selected_member == "Bob"

    view.move_selection(1)
    assert view.selected_member == "Alice"


def test_github_move_selection_cycles_cached_repositories(monkeypatch) -> None:
    view = GitHubDashboardView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)
    view._repository_order = ["github:acme/api", "github:acme/web"]

    view.selected_repository_id = None
    view.move_selection(1)
    assert view.selected_repository_id == "github:acme/api"

    view.move_selection(1)
    assert view.selected_repository_id == "github:acme/web"

    view.move_selection(1)
    assert view.selected_repository_id == "github:acme/api"


def test_dashboard_delivery_health_behind_when_past_end_date() -> None:
    view = DashboardView()
    today = date(2026, 2, 24)
    start = today - timedelta(days=20)
    end = today - timedelta(days=1)

    label, reason, expected = view._delivery_health(
        completion_pct=70,
        blocked_count=1,
        total_issues=10,
        start_date=start,
        end_date=end,
        today=today,
    )

    assert label == "Behind"
    assert "past projected end date" in reason
    assert expected == 100


def test_dashboard_delivery_health_on_track_when_completion_ahead() -> None:
    view = DashboardView()
    today = date(2026, 2, 24)
    start = today - timedelta(days=10)
    end = today + timedelta(days=10)

    label, _reason, expected = view._delivery_health(
        completion_pct=65,
        blocked_count=1,
        total_issues=20,
        start_date=start,
        end_date=end,
        today=today,
    )

    assert label == "On Track"
    assert expected == 50


def test_dashboard_overview_prefers_project_description() -> None:
    view = DashboardView()
    project = SimpleNamespace(description="Ship partner onboarding workflow.\nSecond line.")

    overview = view._project_overview_text(project, 40, 3, 1, 10)

    assert overview == "Ship partner onboarding workflow."


def test_dashboard_project_start_date_prefers_project_start_date() -> None:
    view = DashboardView()
    project = SimpleNamespace(start_date="2026-01-10")
    issues = [SimpleNamespace(created_at=datetime(2026, 2, 1, 9, 0, 0))]

    started = view._project_start_date(project, issues)

    assert started == date(2026, 1, 10)


@pytest.mark.parametrize(
    ("view", "expected_connectors"),
    [
        (DashboardView(), ("linear", "github")),
        (GitHubDashboardView(), ("github", "linear")),
        (SprintBoardView(), ("linear", "github")),
        (TimelineView(), ("linear", "github")),
        (WorkloadView(), ("linear", "github")),
    ],
)
def test_core_views_request_consistent_freshness_summary(view, expected_connectors, monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []
    fake_dm = SimpleNamespace(
        freshness_summary_line=lambda connectors: calls.append(connectors) or "Freshness (stale>30m): ..."
    )
    monkeypatch.setattr(type(view), "app", property(lambda _self: SimpleNamespace(data_manager=fake_dm)))

    text = view._freshness_text()

    assert "Freshness" in text
    assert calls == [expected_connectors]
