from __future__ import annotations

from types import SimpleNamespace
import asyncio

import pytest

from projectdash.app import ProjectDash
from projectdash.models import AgentRun, PullRequest
from projectdash.views.issue_flow import IssueFlowScreen
from projectdash.views.sprint_issue import SprintIssueScreen
from projectdash.views.sync_history import SyncHistoryScreen


class _FakeSprintView:
    def __init__(self) -> None:
        self.moves: list[tuple[int, int]] = []
        self.filter_active = False
        self.closed_issue = False
        self.opened_linear = False

    def move_cursor(self, col_delta: int = 0, row_delta: int = 0) -> None:
        self.moves.append((col_delta, row_delta))

    def current_issue(self):
        return SimpleNamespace(id="T-1", title="Test Issue")

    async def close_selected_issue(self):
        self.closed_issue = True
        return True, "closed"

    def open_selected_issue_in_linear(self):
        self.opened_linear = True
        return True, "opened"


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


@pytest.mark.asyncio
async def test_sprint_close_issue_dispatches_to_active_sprint(monkeypatch) -> None:
    app = ProjectDash()
    sprint = _FakeSprintView()
    published: list[tuple[bool, str]] = []

    monkeypatch.setattr(app, "_active_sprint_view", lambda: sprint)
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    def mock_push_screen(screen, callback) -> None:
        if callback:
            callback(True)
    monkeypatch.setattr(app, "push_screen", mock_push_screen)

    def mock_run_worker(coro, **kwargs):
        app._worker_task = asyncio.create_task(coro)
    monkeypatch.setattr(app, "run_worker", mock_run_worker)

    await app.action_sprint_close_issue()
    if hasattr(app, "_worker_task"):
        await app._worker_task

    assert sprint.closed_issue is True
    assert published == [(True, "closed")]


def test_sprint_open_linear_dispatches_to_active_sprint(monkeypatch) -> None:
    app = ProjectDash()
    sprint = _FakeSprintView()
    published: list[tuple[bool, str]] = []

    monkeypatch.setattr(app, "_active_sprint_view", lambda: sprint)
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    app.action_sprint_open_linear()

    assert sprint.opened_linear is True
    assert published == [(True, "opened")]


def test_sprint_open_linear_dispatches_to_github_when_active(monkeypatch) -> None:
    app = ProjectDash()
    calls: list[str] = []

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_github_view", lambda: object())
    monkeypatch.setattr(app, "action_github_open_pr", lambda: calls.append("open_pr"))

    app.action_sprint_open_linear()

    assert calls == ["open_pr"]


def test_sprint_comment_dispatches_to_github_check_when_active(monkeypatch) -> None:
    app = ProjectDash()
    calls: list[str] = []

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_github_view", lambda: object())
    monkeypatch.setattr(app, "action_github_open_check", lambda: calls.append("open_check"))

    app.action_sprint_comment_issue()

    assert calls == ["open_check"]


@pytest.mark.asyncio
async def test_sprint_assignee_dispatches_to_github_agent_when_active(monkeypatch) -> None:
    app = ProjectDash()
    calls: list[str] = []

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_github_view", lambda: object())

    async def fake_github_agent() -> None:
        calls.append("agent")

    monkeypatch.setattr(app, "action_github_trigger_agent", fake_github_agent)

    await app.action_sprint_cycle_assignee()

    assert calls == ["agent"]


def test_sprint_open_github_drilldown_switches_tab_and_focuses_issue(monkeypatch) -> None:
    app = ProjectDash()
    events: list[tuple[str, str]] = []

    class _FakeSprint:
        filter_active = False

        def current_issue(self):
            return SimpleNamespace(id="PD-123")

    class _FakeGithub:
        def focus_issue(self, issue_id: str):
            events.append(("focus", issue_id))
            return True, f"showing {issue_id}"

    monkeypatch.setattr(app, "_active_sprint_view", lambda: _FakeSprint())
    monkeypatch.setattr(app, "_active_github_view", lambda: _FakeGithub())
    monkeypatch.setattr(app, "action_switch_tab", lambda tab_id: events.append(("tab", tab_id)))
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: events.append(("result", msg)))

    app.action_sprint_open_github_drilldown()

    assert ("tab", "github") in events
    assert ("focus", "PD-123") in events
    assert any(event[0] == "result" and "PD-123" in event[1] for event in events)


def test_sprint_open_github_drilldown_falls_back_to_timeline_blocked_drilldown(monkeypatch) -> None:
    app = ProjectDash()
    events: list[tuple[bool, str]] = []

    class _FakeTimeline:
        def open_project_blocked_drilldown(self):
            return True, "Blocked drilldown: 2 issue(s)"

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_timeline_view", lambda: _FakeTimeline())
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: events.append((ok, msg)))

    app.action_sprint_open_github_drilldown()

    assert events == [(True, "Blocked drilldown: 2 issue(s)")]


def test_github_jump_issue_switches_to_sprint(monkeypatch) -> None:
    app = ProjectDash()
    events: list[tuple[str, str]] = []

    class _FakeGithub:
        def selected_issue_for_jump(self):
            return "PD-404"

    class _FakeSprint:
        def focus_issue(self, issue_id: str):
            events.append(("focus", issue_id))
            return True, f"focused {issue_id}"

    monkeypatch.setattr(app, "_active_github_view", lambda: _FakeGithub())
    monkeypatch.setattr(app, "_active_sprint_view", lambda: _FakeSprint())
    monkeypatch.setattr(app, "action_switch_tab", lambda tab_id: events.append(("tab", tab_id)))
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: events.append(("result", msg)))

    app.action_github_jump_issue()

    assert ("tab", "sprint") in events
    assert ("focus", "PD-404") in events
    assert any(event[0] == "result" and "PD-404" in event[1] for event in events)
    assert any(item.get("route") == "github_jump_issue" for item in app._navigation_context_stack)


def test_github_jump_issue_clears_context_when_focus_fails(monkeypatch) -> None:
    app = ProjectDash()
    events: list[tuple[str, str]] = []

    class _FakeGithub:
        def selected_issue_for_jump(self):
            return "PD-404"

    class _FakeSprint:
        def focus_issue(self, issue_id: str):
            events.append(("focus", issue_id))
            return False, "not found"

    monkeypatch.setattr(app, "_active_github_view", lambda: _FakeGithub())
    monkeypatch.setattr(app, "_active_sprint_view", lambda: _FakeSprint())
    monkeypatch.setattr(app, "action_switch_tab", lambda tab_id: events.append(("tab", tab_id)))
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: events.append(("result", msg)))

    app.action_github_jump_issue()

    assert ("tab", "sprint") in events
    assert ("focus", "PD-404") in events
    assert ("result", "not found") in events
    assert app._navigation_context_stack == []


def test_github_clear_drilldown_dispatches_to_active_github(monkeypatch) -> None:
    app = ProjectDash()
    events: list[tuple[bool, str]] = []

    class _FakeGithub:
        def clear_issue_drilldown(self):
            return True, "Cleared issue drilldown (PD-123)"

    monkeypatch.setattr(app, "_active_github_view", lambda: _FakeGithub())
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: events.append((ok, msg)))

    app.action_github_clear_drilldown()

    assert events == [(True, "Cleared issue drilldown (PD-123)")]


def test_github_clear_drilldown_restores_origin_context(monkeypatch) -> None:
    app = ProjectDash()
    events: list[tuple[bool, str]] = []
    switched: list[str] = []
    restored: list[tuple[str, dict[str, object] | None]] = []

    class _FakeGithub:
        def clear_issue_drilldown(self):
            return True, "Cleared issue drilldown (PD-123)"

    app._push_navigation_context(
        route="github_issue_drilldown",
        payload={"origin": {"tab_id": "sprint", "view_state": {"filter_query": "mine", "selected_issue_id": "PD-123"}}},
    )
    monkeypatch.setattr(app, "_active_github_view", lambda: _FakeGithub())
    monkeypatch.setattr(app, "action_switch_tab", lambda tab_id: switched.append(tab_id))
    monkeypatch.setattr(
        app,
        "_restore_view_state_snapshot",
        lambda view_id, state: restored.append((view_id, state)),
    )
    monkeypatch.setattr(app, "update_app_status", lambda msg=None: None)
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: events.append((ok, msg)))

    app.action_github_clear_drilldown()

    assert switched == ["sprint"]
    assert restored == [("sprint", {"filter_query": "mine", "selected_issue_id": "PD-123"})]
    assert events == [(True, "Cleared issue drilldown (PD-123)")]
    assert app._navigation_context_stack == []


def test_github_clear_drilldown_restores_jump_issue_context_when_github_inactive(monkeypatch) -> None:
    app = ProjectDash()
    switched: list[str] = []
    restored: list[tuple[str, dict[str, object] | None]] = []
    published: list[tuple[bool, str]] = []

    app._push_navigation_context(
        route="github_jump_issue",
        payload={"origin": {"tab_id": "github", "view_state": {"visual_mode": "prs", "selected_pull_request_id": "pr-7"}}},
    )
    monkeypatch.setattr(app, "_active_github_view", lambda: None)
    monkeypatch.setattr(app, "action_switch_tab", lambda tab_id: switched.append(tab_id))
    monkeypatch.setattr(
        app,
        "_restore_view_state_snapshot",
        lambda view_id, state: restored.append((view_id, state)),
    )
    monkeypatch.setattr(app, "update_app_status", lambda msg=None: None)
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    app.action_github_clear_drilldown()

    assert switched == ["github"]
    assert restored == [("github", {"visual_mode": "prs", "selected_pull_request_id": "pr-7"})]
    assert published == [(True, "Returned to GitHub context")]
    assert app._navigation_context_stack == []


def test_timeline_blocked_drilldown_back_restores_origin(monkeypatch) -> None:
    app = ProjectDash()
    events: list[tuple[bool, str]] = []
    switched: list[str] = []
    restored: list[tuple[str, dict[str, object] | None]] = []

    class _FakeTimeline:
        visual_mode = "blocked"

    app._push_navigation_context(
        route="timeline_blocked_drilldown",
        payload={"origin": {"tab_id": "timeline", "view_state": {"visual_mode": "project", "selected_project_id": "p1"}}},
    )
    monkeypatch.setattr(app, "_active_timeline_view", lambda: _FakeTimeline())
    monkeypatch.setattr(app, "action_switch_tab", lambda tab_id: switched.append(tab_id))
    monkeypatch.setattr(
        app,
        "_restore_view_state_snapshot",
        lambda view_id, state: restored.append((view_id, state)),
    )
    monkeypatch.setattr(app, "update_app_status", lambda msg=None: None)
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: events.append((ok, msg)))

    app.action_timeline_blocked_drilldown()

    assert switched == ["timeline"]
    assert restored == [("timeline", {"visual_mode": "project", "selected_project_id": "p1"})]
    assert events == [(True, "Returned from blocked drilldown")]
    assert app._navigation_context_stack == []


def test_open_issue_flow_prefers_active_sprint_issue(monkeypatch) -> None:
    app = ProjectDash()
    pushed: list[object] = []
    callbacks: list[object] = []
    published: list[tuple[bool, str]] = []

    class _FakeSprint:
        filter_active = False

        def current_issue(self):
            return SimpleNamespace(id="PD-201")

    class _FakeGithub:
        def selected_issue_for_jump(self):
            return "PD-999"

    monkeypatch.setattr(app, "_active_sprint_view", lambda: _FakeSprint())
    monkeypatch.setattr(app, "_active_github_view", lambda: _FakeGithub())
    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: (pushed.append(screen), callbacks.append(callback)))
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    app.action_open_issue_flow()

    assert len(pushed) == 1
    assert len(callbacks) == 1
    assert callable(callbacks[0])
    assert isinstance(pushed[0], IssueFlowScreen)
    assert pushed[0].issue_id == "PD-201"
    assert published == [(True, "Opened issue flow for PD-201")]


def test_open_issue_flow_uses_github_selection_when_sprint_unavailable(monkeypatch) -> None:
    app = ProjectDash()
    pushed: list[object] = []
    callbacks: list[object] = []
    published: list[tuple[bool, str]] = []

    class _FakeGithub:
        def selected_issue_for_jump(self):
            return "PD-333"

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_github_view", lambda: _FakeGithub())
    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: (pushed.append(screen), callbacks.append(callback)))
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    app.action_open_issue_flow()

    assert len(pushed) == 1
    assert len(callbacks) == 1
    assert callable(callbacks[0])
    assert pushed[0].issue_id == "PD-333"
    assert published == [(True, "Opened issue flow for PD-333")]


def test_open_issue_flow_publishes_error_when_no_issue_context(monkeypatch) -> None:
    app = ProjectDash()
    published: list[tuple[bool, str]] = []
    pushed: list[object] = []

    class _FakeSprint:
        filter_active = True

        def current_issue(self):
            return None

    class _FakeGithub:
        def selected_issue_for_jump(self):
            return None

    monkeypatch.setattr(app, "_active_sprint_view", lambda: _FakeSprint())
    monkeypatch.setattr(app, "_active_github_view", lambda: _FakeGithub())
    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append(screen))
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    app.action_open_issue_flow()

    assert pushed == []
    assert published == [(False, "No linked issue selected for issue flow")]


def test_issue_flow_close_restores_origin_tab_and_view_state(monkeypatch) -> None:
    app = ProjectDash()
    switched: list[str] = []
    restored: list[tuple[str, dict[str, object] | None]] = []
    status_updates: list[str] = []

    app._push_navigation_context(
        route="issue_flow",
        payload={
            "origin": {
                "tab_id": "github",
                "view_state": {"state_filter": "open", "selected_pull_request_id": "pr-2"},
            }
        },
    )
    monkeypatch.setattr(app, "action_switch_tab", lambda tab_id: switched.append(tab_id))
    monkeypatch.setattr(
        app,
        "_restore_view_state_snapshot",
        lambda view_id, state: restored.append((view_id, state)),
    )
    monkeypatch.setattr(app, "update_app_status", lambda msg=None: status_updates.append(msg or ""))

    app._on_issue_flow_closed()

    assert switched == ["github"]
    assert restored == [("github", {"state_filter": "open", "selected_pull_request_id": "pr-2"})]
    assert status_updates
    assert app._navigation_context_stack == []


def test_open_filter_dispatches_to_sprint_or_github(monkeypatch) -> None:
    app = ProjectDash()
    events: list[str] = []

    class _FakeGithub:
        pass

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_github_view", lambda: _FakeGithub())
    monkeypatch.setattr(app, "_activate_command_input", lambda initial: events.append(f"cmd:{initial}"))

    app.action_open_filter()

    assert events == ["cmd:github "]


def test_open_filter_prefers_sprint_filter(monkeypatch) -> None:
    app = ProjectDash()
    events: list[str] = []

    class _FakeSprint:
        pass

    monkeypatch.setattr(app, "_active_sprint_view", lambda: _FakeSprint())
    monkeypatch.setattr(app, "action_sprint_filter", lambda: events.append("sprint"))
    monkeypatch.setattr(app, "_activate_command_input", lambda initial: events.append(f"cmd:{initial}"))

    app.action_open_filter()

    assert events == ["sprint"]


def test_open_filter_prefills_timeline_and_workload(monkeypatch) -> None:
    app = ProjectDash()
    events: list[str] = []

    class _FakeTimeline:
        visual_mode = "blocked"

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_github_view", lambda: None)
    monkeypatch.setattr(app, "_active_timeline_view", lambda: _FakeTimeline())
    monkeypatch.setattr(app, "_activate_command_input", lambda initial: events.append(initial))

    app.action_open_filter()

    monkeypatch.setattr(app, "_active_timeline_view", lambda: None)
    monkeypatch.setattr(app, "_active_workload_view", lambda: object())
    app.action_open_filter()

    assert events == ["blocked ", "workload "]


def test_back_context_uses_timeline_drilldown_restore(monkeypatch) -> None:
    app = ProjectDash()
    calls: list[str] = []

    class _FakeTimeline:
        visual_mode = "blocked"

    monkeypatch.setattr(app, "_active_github_view", lambda: None)
    monkeypatch.setattr(app, "_active_timeline_view", lambda: _FakeTimeline())
    monkeypatch.setattr(app, "action_timeline_blocked_drilldown", lambda: calls.append("timeline_back"))

    app.action_back_context()

    assert calls == ["timeline_back"]


def test_back_context_falls_back_to_close_detail(monkeypatch) -> None:
    app = ProjectDash()
    calls: list[str] = []
    monkeypatch.setattr(app, "_active_github_view", lambda: None)
    monkeypatch.setattr(app, "_active_timeline_view", lambda: None)
    monkeypatch.setattr(app, "_restore_context_route", lambda route: False)
    monkeypatch.setattr(app, "action_close_detail", lambda: calls.append("close"))

    app.action_back_context()

    assert calls == ["close"]


@pytest.mark.asyncio
async def test_github_trigger_agent_records_run(monkeypatch) -> None:
    app = ProjectDash()
    published: list[tuple[bool, str]] = []
    recorded_runs = []
    refresh_queued: list[bool] = []
    monkeypatch.delenv("PD_AGENT_RUN_CMD", raising=False)
    pull_request = PullRequest(
        id="github:acme/api:pr:19",
        provider="github",
        repository_id="github:acme/api",
        number=19,
        title="Refactor routing",
        state="open",
        author_id="bob",
        head_branch="feature/routing",
        base_branch="main",
        url="https://github.com/acme/api/pull/19",
        issue_id="PD-19",
        opened_at="2026-02-20T00:00:00Z",
        merged_at=None,
        closed_at=None,
        updated_at="2026-02-25T00:00:00Z",
    )

    class _FakeGithub:
        def selected_pull_request(self):
            return pull_request

    async def fake_record_agent_run(run):
        recorded_runs.append(run)

    monkeypatch.setattr(app, "_active_github_view", lambda: _FakeGithub())
    monkeypatch.setattr(app.data_manager, "record_agent_run", fake_record_agent_run)
    monkeypatch.setattr(app.data_manager, "get_issue_by_id", lambda issue_id: SimpleNamespace(project_id="p1"))
    monkeypatch.setattr(app, "_queue_agent_run_refresh", lambda: refresh_queued.append(True))
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    await app.action_github_trigger_agent()

    assert len(recorded_runs) == 1
    run = recorded_runs[0]
    assert run.pr_id == pull_request.id
    assert run.issue_id == "PD-19"
    assert run.project_id == "p1"
    assert run.branch_name == "feature/routing"
    assert refresh_queued == [True]
    assert any(ok and "Queued agent run" in message for ok, message in published)


@pytest.mark.asyncio
async def test_agent_run_refresh_notifies_on_terminal_transition(monkeypatch) -> None:
    app = ProjectDash()
    app._agent_run_status_by_id = {"ghrun-1": "running"}
    refreshed: list[bool] = []
    notified: list[tuple[str, str]] = []
    statuses: list[str] = []

    async def fake_get_agent_runs(limit: int = 50):
        assert limit == app.AGENT_RUN_REFRESH_LIMIT
        return [
            AgentRun(
                id="ghrun-1",
                runtime="tmux",
                status="completed",
                started_at="2026-02-26 10:00:00",
                artifacts={"pull_request_number": 42},
            )
        ]

    monkeypatch.setattr(app.data_manager, "get_agent_runs", fake_get_agent_runs)
    monkeypatch.setattr(app, "refresh_views", lambda: refreshed.append(True))
    monkeypatch.setattr(app, "_notify", lambda message, severity="information": notified.append((severity, message)))
    monkeypatch.setattr(app, "update_app_status", lambda message=None: statuses.append(message or ""))

    await app._refresh_agent_run_snapshot(notify=True)

    assert refreshed == [True]
    assert notified == [("information", "Agent run ghrun-1 completed for PR #42")]
    assert statuses == ["Agent run ghrun-1 completed for PR #42"]


@pytest.mark.asyncio
async def test_agent_run_refresh_snapshot_initializes_without_notifications(monkeypatch) -> None:
    app = ProjectDash()
    refreshed: list[bool] = []
    notified: list[tuple[str, str]] = []

    async def fake_get_agent_runs(limit: int = 50):
        assert limit == app.AGENT_RUN_REFRESH_LIMIT
        return [
            AgentRun(
                id="ghrun-2",
                runtime="tmux",
                status="running",
                started_at="2026-02-26 10:01:00",
                artifacts={"pull_request_number": 43},
            )
        ]

    monkeypatch.setattr(app.data_manager, "get_agent_runs", fake_get_agent_runs)
    monkeypatch.setattr(app, "refresh_views", lambda: refreshed.append(True))
    monkeypatch.setattr(app, "_notify", lambda message, severity="information": notified.append((severity, message)))

    await app._refresh_agent_run_snapshot(notify=True)

    assert app._agent_run_status_by_id == {"ghrun-2": "running"}
    assert refreshed == []
    assert notified == []


def test_queue_agent_run_refresh_skips_when_poll_inflight(monkeypatch) -> None:
    app = ProjectDash()
    app._agent_run_refresh_inflight = True
    run_worker_called = False

    def fake_run_worker(*args, **kwargs):
        nonlocal run_worker_called
        run_worker_called = True

    monkeypatch.setattr(app, "run_worker", fake_run_worker)

    app._queue_agent_run_refresh()

    assert run_worker_called is False


def test_queue_agent_run_refresh_starts_worker_once(monkeypatch) -> None:
    app = ProjectDash()
    app._agent_run_refresh_inflight = False
    started: list[bool] = []

    def fake_run_worker(awaitable, **kwargs):
        started.append(True)
        awaitable.close()

    monkeypatch.setattr(app, "run_worker", fake_run_worker)

    app._queue_agent_run_refresh()
    app._queue_agent_run_refresh()

    assert started == [True]


def test_on_key_left_moves_sprint_cursor_and_stops_event(monkeypatch) -> None:
    app = ProjectDash()
    sprint = _FakeSprintView()
    monkeypatch.setattr(app, "_active_sprint_view", lambda: sprint)

    class _FakeKeyEvent:
        key = "left"
        character = None

        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    event = _FakeKeyEvent()
    app.on_key(event)  # type: ignore[arg-type]

    assert sprint.moves == [(-1, 0)]
    assert event.stopped is True


def test_on_key_down_moves_sprint_cursor_and_stops_event(monkeypatch) -> None:
    app = ProjectDash()
    sprint = _FakeSprintView()
    monkeypatch.setattr(app, "_active_sprint_view", lambda: sprint)

    class _FakeKeyEvent:
        key = "down"
        character = None

        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    event = _FakeKeyEvent()
    app.on_key(event)  # type: ignore[arg-type]

    assert sprint.moves == [(0, 1)]
    assert event.stopped is True


def test_on_key_space_toggles_page_focus(monkeypatch) -> None:
    app = ProjectDash()
    sprint = _FakeSprintView()
    app.page_focus_locked = True
    monkeypatch.setattr(app, "_active_sprint_view", lambda: sprint)
    monkeypatch.setattr(app, "_apply_page_focus_mode", lambda: None)
    statuses: list[str] = []
    monkeypatch.setattr(app, "update_app_status", lambda msg=None: statuses.append(msg or ""))

    class _FakeKeyEvent:
        key = "space"
        character = None

        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    first = _FakeKeyEvent()
    app.on_key(first)  # type: ignore[arg-type]
    assert app.page_focus_locked is False
    assert first.stopped is True

    second = _FakeKeyEvent()
    app.on_key(second)  # type: ignore[arg-type]
    assert app.page_focus_locked is True
    assert second.stopped is True
    assert statuses


def test_on_key_left_does_not_move_sprint_when_page_focus_disabled(monkeypatch) -> None:
    app = ProjectDash()
    sprint = _FakeSprintView()
    app.page_focus_locked = False
    monkeypatch.setattr(app, "_active_sprint_view", lambda: sprint)

    class _FakeKeyEvent:
        key = "left"
        character = None

        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    event = _FakeKeyEvent()
    app.on_key(event)  # type: ignore[arg-type]

    assert sprint.moves == []
    assert event.stopped is False


def test_on_key_down_moves_active_selection_in_page_focus(monkeypatch) -> None:
    app = ProjectDash()
    app.page_focus_locked = True
    app.page_focus_section = "main"
    moves: list[int] = []

    class _SelectionView:
        def move_selection(self, delta: int) -> None:
            moves.append(delta)

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_selection_view", lambda: _SelectionView())

    class _FakeKeyEvent:
        key = "down"
        character = None

        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    event = _FakeKeyEvent()
    app.on_key(event)  # type: ignore[arg-type]

    assert moves == [1]
    assert event.stopped is True


def test_on_key_right_switches_to_detail_section_in_page_focus(monkeypatch) -> None:
    app = ProjectDash()
    app.page_focus_locked = True
    app.page_focus_section = "main"
    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_selection_view", lambda: None)
    monkeypatch.setattr(app, "update_app_status", lambda msg=None: None)

    class _FakeKeyEvent:
        key = "right"
        character = None

        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    event = _FakeKeyEvent()
    app.on_key(event)  # type: ignore[arg-type]

    assert app.page_focus_section == "detail"
    assert event.stopped is True


def test_on_key_left_returns_to_main_section_in_page_focus(monkeypatch) -> None:
    app = ProjectDash()
    app.page_focus_locked = True
    app.page_focus_section = "detail"
    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_selection_view", lambda: None)
    monkeypatch.setattr(app, "update_app_status", lambda msg=None: None)

    class _FakeKeyEvent:
        key = "left"
        character = None

        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    event = _FakeKeyEvent()
    app.on_key(event)  # type: ignore[arg-type]

    assert app.page_focus_section == "main"
    assert event.stopped is True


def test_on_key_shift_space_opens_detail(monkeypatch) -> None:
    app = ProjectDash()
    opened: list[bool] = []
    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "action_open_detail", lambda: opened.append(True))

    class _FakeKeyEvent:
        key = "shift+space"
        character = None

        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    event = _FakeKeyEvent()
    app.on_key(event)  # type: ignore[arg-type]

    assert opened == [True]
    assert event.stopped is True


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


def test_bindings_include_vertical_level_navigation_shortcuts() -> None:
    app = ProjectDash()
    bound_keys = {binding[0]: binding[1] for binding in app.BINDINGS}

    assert bound_keys["shift+up"] == "level_up"
    assert bound_keys["shift+down"] == "level_down"
    assert bound_keys["shift+enter"] == "open_item_view"
    assert bound_keys["K"] == "toggle_hotkey_bar"


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


def test_toggle_hotkey_bar_toggles_visibility(monkeypatch) -> None:
    app = ProjectDash()
    statuses: list[str] = []
    monkeypatch.setattr(app, "update_app_status", lambda msg=None: statuses.append(msg or ""))

    assert app.hotkey_bar_visible is True
    app.action_toggle_hotkey_bar()
    assert app.hotkey_bar_visible is False
    assert statuses[-1] == "Hotkey bar hidden"

    app.action_toggle_hotkey_bar()
    assert app.hotkey_bar_visible is True
    assert statuses[-1] == "Hotkey bar shown"


def test_open_detail_dispatches_to_active_detail_view(monkeypatch) -> None:
    app = ProjectDash()
    opened: list[bool] = []
    status_updated: list[bool] = []

    class _FakeView:
        def open_detail(self):
            opened.append(True)

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_detail_view", lambda: _FakeView())
    monkeypatch.setattr(app, "update_app_status", lambda msg=None: status_updated.append(True))

    app.action_open_detail()

    assert opened == [True]
    assert status_updated == [True]


def test_open_detail_double_press_on_sprint_opens_item_screen(monkeypatch) -> None:
    app = ProjectDash()
    pushed: list[object] = []
    published: list[tuple[bool, str]] = []

    class _FakeSprint:
        filter_active = False
        detail_open = True

        def current_issue(self):
            return SimpleNamespace(id="PD-77")

    monkeypatch.setattr(app, "_active_sprint_view", lambda: _FakeSprint())
    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append(screen))
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    app.action_open_detail()

    assert len(pushed) == 1
    assert isinstance(pushed[0], SprintIssueScreen)
    assert pushed[0].issue_id == "PD-77"
    assert published == [(True, "Opened sprint item view for PD-77")]


def test_open_item_view_opens_selected_sprint_issue(monkeypatch) -> None:
    app = ProjectDash()
    pushed: list[object] = []
    published: list[tuple[bool, str]] = []

    class _FakeSprint:
        filter_active = False

        def current_issue(self):
            return SimpleNamespace(id="PD-88")

    monkeypatch.setattr(app, "_active_sprint_view", lambda: _FakeSprint())
    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append(screen))
    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    app.action_open_item_view()

    assert len(pushed) == 1
    assert isinstance(pushed[0], SprintIssueScreen)
    assert pushed[0].issue_id == "PD-88"
    assert published == [(True, "Opened sprint item view for PD-88")]


def test_close_detail_dispatches_to_active_detail_view(monkeypatch) -> None:
    app = ProjectDash()
    closed: list[bool] = []
    status_updated: list[bool] = []

    class _FakeView:
        def close_detail(self):
            closed.append(True)

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_detail_view", lambda: _FakeView())
    monkeypatch.setattr(app, "update_app_status", lambda msg=None: status_updated.append(True))

    app.action_close_detail()

    assert closed == [True]
    assert status_updated == [True]


def test_close_detail_closes_help_overlay_before_view(monkeypatch) -> None:
    app = ProjectDash()
    app.help_overlay_active = True
    closed: list[bool] = []
    statuses: list[str] = []

    class _FakeView:
        def close_detail(self):
            closed.append(True)

    monkeypatch.setattr(app, "_active_sprint_view", lambda: None)
    monkeypatch.setattr(app, "_active_detail_view", lambda: _FakeView())
    monkeypatch.setattr(app, "update_app_status", lambda msg=None: statuses.append(msg or ""))

    app.action_close_detail()

    assert app.help_overlay_active is False
    assert closed == []
    assert statuses == ["Help overlay closed"]


def test_execute_command_filter_dispatches_to_open_filter(monkeypatch) -> None:
    app = ProjectDash()
    calls: list[str] = []
    monkeypatch.setattr(app, "action_open_filter", lambda: calls.append("filter"))

    app._execute_command("filter")

    assert calls == ["filter"]


def test_execute_command_switches_to_github_tab(monkeypatch) -> None:
    app = ProjectDash()
    calls: list[tuple[str, str]] = []

    def fake_switch_tab(tab_id: str) -> None:
        calls.append(("tab", tab_id))

    monkeypatch.setattr(app, "action_switch_tab", fake_switch_tab)

    app._execute_command("github")

    assert calls
    assert all(call == ("tab", "github") for call in calls)


def test_execute_command_help_publishes_help(monkeypatch) -> None:
    app = ProjectDash()
    published: list[tuple[bool, str]] = []

    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    app._execute_command("help")

    assert published
    assert published[0][0] is True
    assert "/dashboard" in published[0][1]
    assert "Deprecated aliases:" in published[0][1]


def test_execute_command_blocked_runs_triage_filter(monkeypatch) -> None:
    app = ProjectDash()
    calls: list[str] = []

    monkeypatch.setattr(app, "action_triage_blocked", lambda: calls.append("blocked"))

    app._execute_command("blocked")

    assert calls == ["blocked"]


def test_execute_command_back_dispatches_back_context(monkeypatch) -> None:
    app = ProjectDash()
    calls: list[str] = []
    monkeypatch.setattr(app, "action_back_context", lambda: calls.append("back"))

    app._execute_command("back")

    assert calls == ["back"]


def test_execute_command_blocked_drilldown_then_back(monkeypatch) -> None:
    app = ProjectDash()
    calls: list[str] = []
    monkeypatch.setattr(app, "action_switch_tab", lambda tab_id: calls.append(f"tab:{tab_id}"))
    monkeypatch.setattr(app, "action_timeline_blocked_drilldown", lambda: calls.append("drill"))
    monkeypatch.setattr(app, "action_back_context", lambda: calls.append("back"))

    app._execute_command("blocked drilldown")
    app._execute_command("back")

    assert calls == ["tab:timeline", "drill", "back"]


def test_execute_command_unknown_publishes_error(monkeypatch) -> None:
    app = ProjectDash()
    published: list[tuple[bool, str]] = []

    monkeypatch.setattr(app, "_publish_action_result", lambda ok, msg: published.append((ok, msg)))

    app._execute_command("not-a-real-command")

    assert published == [(False, "Unknown command: /not-a-real-command. Try /help.")]


def test_execute_command_colon_q_quits(monkeypatch) -> None:
    app = ProjectDash()
    calls: list[str] = []

    monkeypatch.setattr(app, "action_quit", lambda: calls.append("quit"))

    app._execute_command(":q")

    assert calls == ["quit"]


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


def test_check_action_blocks_navigation_bindings_in_tab_focus_mode() -> None:
    app = ProjectDash()
    app.command_active = False
    app.page_focus_locked = False

    allowed = app.check_action("sprint_left", ())

    assert allowed is False


def test_check_action_allows_vertical_level_actions_in_tab_focus_mode() -> None:
    app = ProjectDash()
    app.command_active = False
    app.page_focus_locked = False

    assert app.check_action("level_up", ()) is True
    assert app.check_action("level_down", ()) is True


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


def test_view_filter_state_helpers_capture_and_restore(monkeypatch) -> None:
    app = ProjectDash()
    restored: list[dict[str, object] | None] = []

    class _FakeView:
        def capture_filter_state(self):
            return {"filter_query": "status:blocked"}

        def restore_filter_state(self, state):
            restored.append(state)

    class _FakeSwitcher:
        def __init__(self):
            self.views = {"#sprint": _FakeView()}

        def query_one(self, selector: str):
            return self.views[selector]

    switcher = _FakeSwitcher()
    monkeypatch.setattr(app, "query_one", lambda cls: switcher)

    app._persist_view_filter_state("sprint")
    assert app._view_filter_state_by_view["sprint"] == {"filter_query": "status:blocked"}

    app._restore_view_filter_state("sprint")
    assert restored == [{"filter_query": "status:blocked"}]


def test_view_filter_state_helpers_capture_and_restore_timeline(monkeypatch) -> None:
    app = ProjectDash()
    restored: list[dict[str, object] | None] = []

    class _FakeTimelineView:
        def capture_filter_state(self):
            return {"visual_mode": "blocked", "selected_project_id": "p1"}

        def restore_filter_state(self, state):
            restored.append(state)

    class _FakeSwitcher:
        def __init__(self):
            self.views = {"#timeline": _FakeTimelineView()}

        def query_one(self, selector: str):
            return self.views[selector]

    switcher = _FakeSwitcher()
    monkeypatch.setattr(app, "query_one", lambda cls: switcher)

    app._persist_view_filter_state("timeline")
    assert app._view_filter_state_by_view["timeline"] == {"visual_mode": "blocked", "selected_project_id": "p1"}

    app._restore_view_filter_state("timeline")
    assert restored == [{"visual_mode": "blocked", "selected_project_id": "p1"}]


def test_help_overlay_github_mentions_enter_and_escape_detail(monkeypatch) -> None:
    app = ProjectDash()
    monkeypatch.setattr(ProjectDash, "screen", property(lambda self: SimpleNamespace()))
    monkeypatch.setattr(app, "_active_tab_label", lambda: "GitHub")

    help_text = app._help_overlay_text()

    assert "GitHub:" in help_text
    assert "Enter/Esc detail" in help_text


def test_help_overlay_workload_mentions_enter_and_escape_detail(monkeypatch) -> None:
    app = ProjectDash()
    monkeypatch.setattr(ProjectDash, "screen", property(lambda self: SimpleNamespace()))
    monkeypatch.setattr(app, "_active_tab_label", lambda: "Workload")

    help_text = app._help_overlay_text()

    assert "Workload:" in help_text
    assert "Enter/Esc detail" in help_text


def test_help_overlay_mentions_filter_search_and_back(monkeypatch) -> None:
    app = ProjectDash()
    monkeypatch.setattr(ProjectDash, "screen", property(lambda self: SimpleNamespace()))
    monkeypatch.setattr(app, "_active_tab_label", lambda: "Timeline")

    help_text = app._help_overlay_text()

    assert "/ filter/search" in help_text
    assert "Ctrl+B back" in help_text
