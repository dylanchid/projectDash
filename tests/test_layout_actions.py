from __future__ import annotations

from projectdash.app import ProjectDash


class _FakeCustomizableView:
    def __init__(self) -> None:
        self.edit_mode = False
        self.calls: list[tuple[str, tuple]] = []

    def set_layout_edit_mode(self, enabled: bool):
        self.edit_mode = enabled
        self.calls.append(("set_layout_edit_mode", (enabled,)))
        return True, "ok"

    def cycle_selected_section(self, delta: int):
        self.calls.append(("cycle_selected_section", (delta,)))
        return True, "cycled"

    def move_selected_section(self, delta: int):
        self.calls.append(("move_selected_section", (delta,)))
        return True, "moved"

    def resize_selected_section(self, delta: int):
        self.calls.append(("resize_selected_section", (delta,)))
        return True, "resized"

    def remove_selected_section(self):
        self.calls.append(("remove_selected_section", ()))
        return True, "removed"


def test_layout_actions_require_edit_mode(monkeypatch) -> None:
    app = ProjectDash()
    view = _FakeCustomizableView()
    published: list[tuple[bool, str]] = []

    monkeypatch.setattr(app, "_active_customizable_view", lambda: view)
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    app.action_layout_move_left()

    assert published == [(False, "Enable layout edit mode first (Ctrl+E)")]


def test_toggle_layout_edit_dispatches(monkeypatch) -> None:
    app = ProjectDash()
    view = _FakeCustomizableView()
    published: list[tuple[bool, str]] = []

    monkeypatch.setattr(app, "_active_customizable_view", lambda: view)
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    app.action_toggle_layout_edit()
    app.action_layout_move_right()

    assert view.edit_mode is True
    assert ("move_selected_section", (1,)) in view.calls
    assert published[0] == (True, "ok")
