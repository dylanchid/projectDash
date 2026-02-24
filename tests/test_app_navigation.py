from __future__ import annotations

from types import SimpleNamespace

from projectdash.app import ProjectDash
from projectdash.views.sync_history import SyncHistoryScreen


class _FakeSprintView:
    def __init__(self) -> None:
        self.moves: list[tuple[int, int]] = []
        self.filter_active = False

    def move_cursor(self, col_delta: int = 0, row_delta: int = 0) -> None:
        self.moves.append((col_delta, row_delta))


def _project(project_id: str, name: str):
    return SimpleNamespace(id=project_id, name=name)


def test_context_left_moves_sprint_cursor_when_sprint_active(monkeypatch) -> None:
    app = ProjectDash()
    sprint = _FakeSprintView()
    prev_tab_called = False

    def fake_prev_tab() -> None:
        nonlocal prev_tab_called
        prev_tab_called = True

    monkeypatch.setattr(app, "_active_sprint_view", lambda: sprint)
    monkeypatch.setattr(app, "action_prev_tab", fake_prev_tab)

    app.action_context_left()

    assert sprint.moves == [(-1, 0)]
    assert prev_tab_called is False


def test_context_right_switches_tab_when_sprint_inactive(monkeypatch) -> None:
    app = ProjectDash()
    next_tab_called = False

    def fake_next_tab() -> None:
        nonlocal next_tab_called
        next_tab_called = True

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "action_next_tab", fake_next_tab)

    app.action_context_right()

    assert next_tab_called is True


def test_context_left_does_not_move_when_filter_active(monkeypatch) -> None:
    app = ProjectDash()
    sprint = _FakeSprintView()
    sprint.filter_active = True
    prev_tab_called = False

    def fake_prev_tab() -> None:
        nonlocal prev_tab_called
        prev_tab_called = True

    monkeypatch.setattr(app, "_active_sprint_view", lambda: sprint)
    monkeypatch.setattr(app, "action_prev_tab", fake_prev_tab)

    app.action_context_left()

    assert sprint.moves == []
    assert prev_tab_called is False


def test_context_right_cycles_project_when_scope_is_active(monkeypatch) -> None:
    app = ProjectDash()
    app.project_scope_id = "p1"
    called_project_next = False
    called_next_tab = False

    def fake_project_next() -> None:
        nonlocal called_project_next
        called_project_next = True

    def fake_next_tab() -> None:
        nonlocal called_next_tab
        called_next_tab = True

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "action_project_next", fake_project_next)
    monkeypatch.setattr(app, "action_next_tab", fake_next_tab)

    app.action_context_right()

    assert called_project_next is True
    assert called_next_tab is False


def test_sprint_down_dispatches_to_active_selection_view(monkeypatch) -> None:
    app = ProjectDash()
    deltas: list[int] = []

    class _SelectionView:
        def move_selection(self, delta: int) -> None:
            deltas.append(delta)

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_selection_view", lambda: _SelectionView())

    app.action_sprint_down()
    app.action_sprint_up()

    assert deltas == [1, -1]


def test_sprint_down_does_not_fallback_when_sprint_filter_active(monkeypatch) -> None:
    app = ProjectDash()
    sprint = _FakeSprintView()
    sprint.filter_active = True
    selection_called = False

    class _SelectionView:
        def move_selection(self, delta: int) -> None:
            nonlocal selection_called
            selection_called = True

    monkeypatch.setattr(app, "_active_sprint_view", lambda: sprint)
    monkeypatch.setattr(app, "_active_selection_view", lambda: _SelectionView())

    app.action_sprint_down()

    assert sprint.moves == []
    assert selection_called is False


def test_level_down_focuses_first_project_when_scope_is_global(monkeypatch) -> None:
    app = ProjectDash()
    monkeypatch.setattr(app.data_manager, "get_projects", lambda: [_project("p1", "API"), _project("p2", "UI")])
    monkeypatch.setattr(app, "_preferred_project_id_from_active_view", lambda: None)
    events: list[tuple[str, str]] = []

    def fake_set_project_scope(project_id: str | None) -> None:
        events.append(("scope", project_id or "none"))

    monkeypatch.setattr(app, "_set_project_scope", fake_set_project_scope)
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: events.append(("message", msg)))

    app.action_level_down()

    assert events == [("scope", "p1"), ("message", "Project focus: API")]


def test_level_up_clears_project_scope(monkeypatch) -> None:
    app = ProjectDash()
    app.project_scope_id = "p2"
    events: list[tuple[str, str]] = []

    def fake_set_project_scope(project_id: str | None) -> None:
        events.append(("scope", project_id or "none"))

    monkeypatch.setattr(app, "_set_project_scope", fake_set_project_scope)
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: events.append(("message", msg)))

    app.action_level_up()

    assert events == [("scope", "none"), ("message", "Viewing all projects")]


def test_project_next_cycles_scope(monkeypatch) -> None:
    app = ProjectDash()
    app.project_scope_id = "p1"
    monkeypatch.setattr(
        app.data_manager,
        "get_projects",
        lambda: [_project("p1", "API"), _project("p2", "UI"), _project("p3", "Ops")],
    )
    events: list[tuple[str, str]] = []

    def fake_set_project_scope(project_id: str | None) -> None:
        events.append(("scope", project_id or "none"))

    monkeypatch.setattr(app, "_set_project_scope", fake_set_project_scope)
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: events.append(("message", msg)))

    app.action_project_next()

    assert events == [("scope", "p2"), ("message", "Project focus: UI")]


def test_open_sync_history_pushes_screen(monkeypatch) -> None:
    app = ProjectDash()
    pushed: list[object] = []

    def fake_push_screen(screen: object) -> None:
        pushed.append(screen)

    monkeypatch.setattr(app, "push_screen", fake_push_screen)

    app.action_open_sync_history()

    assert len(pushed) == 1
    assert isinstance(pushed[0], SyncHistoryScreen)


def test_toggle_visual_mode_dispatches_to_active_view(monkeypatch) -> None:
    app = ProjectDash()
    called: list[str] = []

    class _FakeView:
        def toggle_visual_mode(self):
            called.append("mode")
            return True, "ok"

    monkeypatch.setattr(app, "_active_visual_view", lambda: _FakeView())
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, message: called.append(message))

    app.action_toggle_visual_mode()

    assert called == ["mode", "ok"]


def test_toggle_graph_density_dispatches_to_active_view(monkeypatch) -> None:
    app = ProjectDash()
    called: list[str] = []

    class _FakeView:
        def toggle_graph_density(self):
            called.append("density")
            return True, "ok"

    monkeypatch.setattr(app, "_active_visual_view", lambda: _FakeView())
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, message: called.append(message))

    app.action_toggle_graph_density()

    assert called == ["density", "ok"]


def test_execute_command_switches_to_sprint_before_filter(monkeypatch) -> None:
    app = ProjectDash()
    calls: list[tuple[str, str]] = []

    def fake_switch_tab(tab_id: str) -> None:
        calls.append(("tab", tab_id))

    def fake_sprint_filter() -> None:
        calls.append(("action", "filter"))

    monkeypatch.setattr(app, "action_switch_tab", fake_switch_tab)
    monkeypatch.setattr(app, "action_sprint_filter", fake_sprint_filter)

    app._execute_command("filter")

    assert calls == [("tab", "sprint"), ("action", "filter")]


def test_execute_command_help_publishes_help(monkeypatch) -> None:
    app = ProjectDash()
    published: list[tuple[bool, str]] = []

    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    app._execute_command("help")

    assert published
    assert published[0][0] is True
    assert "/dashboard" in published[0][1]


def test_execute_command_unknown_publishes_error(monkeypatch) -> None:
    app = ProjectDash()
    published: list[tuple[bool, str]] = []

    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    app._execute_command("not-a-real-command")

    assert published == [(False, "Unknown command: /not-a-real-command. Try /help.")]


def test_command_suggestions_match_partial_query() -> None:
    app = ProjectDash()

    suggestions = app._command_suggestions("his", limit=5)

    assert suggestions
    names = [name for name, _desc in suggestions]
    assert "history" in names


def test_command_suggestions_empty_query_returns_catalog_entries() -> None:
    app = ProjectDash()

    suggestions = app._command_suggestions("", limit=3)

    assert len(suggestions) == 3
    assert all(name for name, _desc in suggestions)


def test_check_action_blocks_bindings_while_command_active() -> None:
    app = ProjectDash()
    app.command_active = True

    allowed = app.check_action("switch_tab", ("dash",))

    assert allowed is False


def test_check_action_allows_bindings_when_command_inactive() -> None:
    app = ProjectDash()
    app.command_active = False

    allowed = app.check_action("open_command", ())

    assert allowed is True


def test_handle_command_key_consumes_unhandled_keys() -> None:
    app = ProjectDash()
    app.command_active = True

    class _FakeKeyEvent:
        key = "up"
        character = None

    handled = app._handle_command_key(_FakeKeyEvent())

    assert handled is True


def test_command_mode_down_key_moves_palette_selection() -> None:
    app = ProjectDash()
    app.command_active = True
    app.command_query = "h"
    app.command_selected_index = 0

    class _FakeKeyEvent:
        key = "down"
        character = None

    app._handle_command_key(_FakeKeyEvent())

    assert app.command_selected_index == 1


def test_command_mode_tab_autocompletes_selected_command() -> None:
    app = ProjectDash()
    app.command_active = True
    app.command_query = "his"
    app.command_selected_index = 0

    class _FakeKeyEvent:
        key = "tab"
        character = None

    app._handle_command_key(_FakeKeyEvent())

    assert app.command_query == "history"


def test_command_mode_enter_executes_selected_suggestion_when_partial(monkeypatch) -> None:
    app = ProjectDash()
    app.command_active = True
    app.command_query = "his"
    app.command_selected_index = 0
    executed: list[str] = []

    monkeypatch.setattr(app, "_execute_command", lambda cmd: executed.append(cmd))

    class _FakeKeyEvent:
        key = "enter"
        character = None

    app._handle_command_key(_FakeKeyEvent())

    assert executed == ["history"]
    assert app.command_active is False
