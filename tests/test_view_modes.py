from projectdash.views.dashboard import DashboardView
from projectdash.views.timeline import TimelineView
from projectdash.views.workload import WorkloadView


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
    for _ in range(3):
        ok, _message = view.toggle_visual_mode()
        assert ok is True
        modes.append(view.visual_mode)

    assert modes == ["risk", "progress", "project"]


def test_workload_mode_cycles_through_all_views(monkeypatch) -> None:
    view = WorkloadView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)

    modes = []
    for _ in range(3):
        ok, _message = view.toggle_visual_mode()
        assert ok is True
        modes.append(view.visual_mode)

    assert modes == ["chart", "rebalance", "table"]


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
