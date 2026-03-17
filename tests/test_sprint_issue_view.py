from __future__ import annotations

from types import SimpleNamespace

from projectdash.views.issue_flow import IssueFlowScreen
from projectdash.views.sprint_issue import SprintIssueScreen


def test_sprint_issue_screen_open_issue_flow_pushes_screen(monkeypatch) -> None:
    screen = SprintIssueScreen("PD-9")
    pushed: list[object] = []

    class _FakeApp:
        def push_screen(self, next_screen):
            pushed.append(next_screen)

    monkeypatch.setattr(SprintIssueScreen, "app", property(lambda self: _FakeApp()))

    screen.action_open_issue_flow()

    assert len(pushed) == 1
    assert isinstance(pushed[0], IssueFlowScreen)
    assert pushed[0].issue_id == "PD-9"


def test_sprint_issue_screen_open_github_focuses_issue(monkeypatch) -> None:
    screen = SprintIssueScreen("PD-11")
    events: list[tuple[str, object]] = []

    class _FakeGithub:
        def focus_issue(self, issue_id: str):
            events.append(("focus", issue_id))
            return True, f"Focused {issue_id}"

    class _FakeApp:
        def action_switch_tab(self, tab_id: str):
            events.append(("tab", tab_id))

        def _active_github_view(self):
            return _FakeGithub()

        def _publish_action_result(self, ok: bool, message: str):
            events.append(("result", (ok, message)))

    monkeypatch.setattr(SprintIssueScreen, "app", property(lambda self: _FakeApp()))

    screen.action_open_github()

    assert ("tab", "github") in events
    assert ("focus", "PD-11") in events
    assert ("result", (True, "Focused PD-11")) in events


def test_sprint_issue_screen_open_actions_delegate_to_sprint_actions(monkeypatch) -> None:
    screen = SprintIssueScreen("PD-22")
    calls: list[str] = []

    class _FakeApp:
        def action_sprint_open_linear(self):
            calls.append("linear")

        def action_sprint_comment_issue(self):
            calls.append("comment")

        def action_sprint_open_editor(self):
            calls.append("editor")

        def action_sprint_open_terminal_editor(self):
            calls.append("terminal")

    monkeypatch.setattr(SprintIssueScreen, "app", property(lambda self: _FakeApp()))

    screen.action_open_linear()
    screen.action_open_comment()
    screen.action_open_editor()
    screen.action_open_terminal()

    assert calls == ["linear", "comment", "editor", "terminal"]


def test_sprint_issue_screen_refresh_view_handles_missing_issue(monkeypatch) -> None:
    screen = SprintIssueScreen("PD-404")
    updated: dict[str, str] = {}

    class _Widget:
        def __init__(self, key: str) -> None:
            self.key = key

        def update(self, value) -> None:
            updated[self.key] = str(value)

    widgets = {
        "#sprint-item-detail": _Widget("detail"),
        "#sprint-item-hint": _Widget("hint"),
    }

    class _FakeApp:
        data_manager = SimpleNamespace(get_issue_by_id=lambda issue_id: None)

    monkeypatch.setattr(SprintIssueScreen, "app", property(lambda self: _FakeApp()))
    screen.query_one = lambda selector, _type=None: widgets[selector]  # type: ignore[method-assign]

    screen.refresh_view()

    assert updated["detail"] == "Issue not found: PD-404"
    assert updated["hint"] == "Esc close"
