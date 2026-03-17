import pytest
from datetime import datetime

from projectdash.config import AppConfig
from projectdash.data import DataManager
from projectdash.database import Database
from projectdash.github import GitHubApiError
from projectdash.linear import LinearApiError
from projectdash.models import Issue, LinearWorkflowState, User


@pytest.mark.asyncio
async def test_sync_state_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    dm = DataManager()
    await dm.sync_with_linear()
    assert dm.sync_in_progress is False
    assert dm.last_sync_result == "failed"
    assert dm.last_sync_error == "LINEAR_API_KEY not set"
    assert dm.sync_status_summary() == "failed: LINEAR_API_KEY not set"
    assert dm.sync_diagnostics["auth"] == "failed: LINEAR_API_KEY not set"


@pytest.mark.asyncio
async def test_load_from_cache_restores_workflow_states_for_status_updates(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-test.db"
    db = Database(db_path)
    await db.init_db()

    user = User("u1", "Alice")
    issue = Issue(
        id="X-1",
        linear_id="lin-1",
        title="Task",
        priority="Medium",
        status="Todo",
        state_id="state-1",
        team_id="team-1",
        assignee=user,
        points=3,
    )
    state_todo = LinearWorkflowState(id="state-1", name="Todo", type="unstarted", team_id="team-1")
    state_in_progress = LinearWorkflowState(id="state-2", name="In Progress", type="started", team_id="team-1")

    await db.save_users([user])
    await db.save_issues([issue])
    await db.save_workflow_states([state_todo, state_in_progress])

    dm = DataManager(config=AppConfig())
    dm.db = Database(db_path)
    await dm.load_from_cache()

    async def remote_ok(issue_id: str, state_id: str):
        assert issue_id == "lin-1"
        assert state_id == "state-2"
        return {"success": True}

    monkeypatch.setattr(dm.linear, "update_issue_status", remote_ok)
    ok, _ = await dm.cycle_issue_status("X-1", ("Todo", "In Progress"))

    assert ok is True
    assert dm.issues[0].status == "In Progress"
    assert dm.issues[0].state_id == "state-2"


@pytest.mark.asyncio
async def test_initialize_does_not_seed_mock_data_by_default(tmp_path) -> None:
    db_path = tmp_path / "projectdash-test.db"
    dm = DataManager(config=AppConfig(seed_mock_data=False))
    dm.db = Database(db_path)

    await dm.initialize()

    assert dm.users == []
    assert dm.projects == []
    assert dm.issues == []


@pytest.mark.asyncio
async def test_initialize_seeds_mock_data_when_enabled(tmp_path) -> None:
    db_path = tmp_path / "projectdash-test.db"
    dm = DataManager(config=AppConfig(seed_mock_data=True))
    dm.db = Database(db_path)

    await dm.initialize()

    assert len(dm.users) > 0
    assert len(dm.projects) > 0
    assert len(dm.issues) > 0


@pytest.mark.asyncio
async def test_sync_diagnostics_capture_failing_resource(monkeypatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    dm = DataManager(config=AppConfig(seed_mock_data=False))

    async def fake_get_me():
        return {"viewer": {"id": "u1", "name": "Tester", "email": "tester@example.com"}}

    async def fake_get_projects():
        return []

    async def fake_get_team_workflow_states():
        return []

    async def fake_get_issues():
        raise RuntimeError("rate limit")

    monkeypatch.setattr(dm.linear, "get_me", fake_get_me)
    monkeypatch.setattr(dm.linear, "get_projects", fake_get_projects)
    monkeypatch.setattr(dm.linear, "get_team_workflow_states", fake_get_team_workflow_states)
    monkeypatch.setattr(dm.linear, "get_issues", fake_get_issues)

    await dm.sync_with_linear()

    assert dm.last_sync_result == "failed"
    assert dm.last_sync_error == "issues fetch failed: rate limit"
    assert dm.sync_diagnostics["auth"] == "ok: Tester"
    assert dm.sync_diagnostics["projects"] == "ok: 0"
    assert dm.sync_diagnostics["workflow_states"] == "ok: 0 teams"
    assert dm.sync_diagnostics["issues"] == "failed: rate limit"
    assert "failed: issues fetch failed: rate limit" == dm.sync_status_summary()


@pytest.mark.asyncio
async def test_linear_sync_normalizes_auth_failures(monkeypatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    dm = DataManager(config=AppConfig(seed_mock_data=False))

    async def fake_get_me():
        raise LinearApiError("You don't have permission", code="FORBIDDEN")

    monkeypatch.setattr(dm.linear, "get_me", fake_get_me)

    await dm.sync_with_linear()

    assert dm.last_sync_result == "failed"
    assert dm.last_sync_error == "auth failed: You don't have permission | code=FORBIDDEN"
    assert dm.sync_diagnostics["auth"] == "failed: You don't have permission | code=FORBIDDEN"


@pytest.mark.asyncio
async def test_github_sync_normalizes_auth_failures(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-github.db"
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    dm = DataManager(config=AppConfig(github_repositories=("acme/platform",), seed_mock_data=False))
    dm.db = Database(db_path)
    await dm.initialize()

    async def fake_get_current_user():
        raise GitHubApiError("Requires authentication", status_code=401)

    monkeypatch.setattr(dm.github, "get_current_user", fake_get_current_user)

    await dm.sync_with_github()

    assert dm.last_sync_result == "failed"
    assert dm.last_sync_error == "github auth failed: Requires authentication (status=401)"
    assert dm.sync_diagnostics["github_auth"] == "failed: Requires authentication (status=401)"


@pytest.mark.asyncio
async def test_sync_history_is_capped_to_last_20_entries(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-test.db"
    dm = DataManager(config=AppConfig(seed_mock_data=False))
    dm.db = Database(db_path)
    await dm.initialize()
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)

    for _ in range(25):
        await dm.sync_with_linear()

    history = dm.get_sync_history()
    assert len(history) == 20
    assert all(entry["result"] == "failed" for entry in history)


def test_latest_sync_history_lines_formats_entries() -> None:
    dm = DataManager(config=AppConfig(seed_mock_data=False))
    dm.sync_history = [
        {
            "created_at": "2026-02-23 01:00:00",
            "result": "failed",
            "summary": "failed: issues fetch failed: rate limit",
            "diagnostics": {},
        },
        {
            "created_at": "2026-02-23 00:59:00",
            "result": "success",
            "summary": "success u:1 p:1 i:2 t:1",
            "diagnostics": {},
        },
    ]

    lines = dm.latest_sync_history_lines(limit=2)

    assert lines == [
        "2026-02-23 01:00:00 | failed | failed: issues fetch failed: rate limit",
        "2026-02-23 00:59:00 | success | success u:1 p:1 i:2 t:1",
    ]


def test_connector_freshness_snapshot_marks_stale_by_threshold() -> None:
    dm = DataManager(config=AppConfig(seed_mock_data=False))
    dm.sync_stale_minutes = 30
    dm._connector_freshness["linear"] = {
        "status": "success",
        "last_success_at": "2026-02-26 11:00:00",
        "last_attempt_at": "2026-02-26 11:00:00",
        "last_error": None,
    }

    snapshot = dm.connector_freshness_snapshot("linear", reference_time=datetime(2026, 2, 26, 12, 0, 0))

    assert snapshot["state"] == "stale"
    assert snapshot["is_stale"] is True
    assert snapshot["age_minutes"] == 60


def test_connector_freshness_snapshot_failure_includes_recovery_hint() -> None:
    dm = DataManager(config=AppConfig(seed_mock_data=False))
    dm._connector_freshness["github"] = {
        "status": "failed",
        "last_success_at": None,
        "last_attempt_at": "2026-02-26 12:00:00",
        "last_error": "GITHUB_TOKEN not set",
    }

    snapshot = dm.connector_freshness_snapshot("github", reference_time=datetime(2026, 2, 26, 12, 1, 0))
    summary = dm.freshness_summary_line(("github",))

    assert snapshot["state"] == "failed"
    assert "set GITHUB_TOKEN" in snapshot["recovery_hint"]
    assert "FAILED" in summary


@pytest.mark.asyncio
async def test_linear_sync_checkpoints_are_stable_for_identical_upstream(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-linear.db"
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    dm = DataManager(config=AppConfig(seed_mock_data=False))
    dm.db = Database(db_path)
    await dm.initialize()

    async def fake_get_me():
        return {"viewer": {"id": "viewer-1", "name": "Tester", "email": "tester@example.com"}}

    async def fake_get_projects():
        return [
            {
                "id": "p1",
                "name": "Project One",
                "targetDate": "2026-03-01",
                "state": "Active",
                "startDate": "2026-02-01",
                "description": "Alpha",
            }
        ]

    async def fake_get_team_workflow_states():
        return [
            {
                "id": "team-1",
                "key": "ENG",
                "name": "Engineering",
                "states": {"nodes": [{"id": "state-1", "name": "Todo", "type": "unstarted"}]},
            }
        ]

    async def fake_get_issues():
        return [
            {
                "id": "lin-1",
                "identifier": "PD-1",
                "title": "First issue",
                "priority": 2,
                "state": {"id": "state-1", "name": "Todo", "type": "unstarted"},
                "dueDate": "2026-03-02",
                "project": {"id": "p1"},
                "team": {"id": "team-1"},
                "assignee": {"id": "u1", "name": "Alice", "avatarUrl": None},
                "estimate": 3,
            }
        ]

    monkeypatch.setattr(dm.linear, "get_me", fake_get_me)
    monkeypatch.setattr(dm.linear, "get_projects", fake_get_projects)
    monkeypatch.setattr(dm.linear, "get_team_workflow_states", fake_get_team_workflow_states)
    monkeypatch.setattr(dm.linear, "get_issues", fake_get_issues)

    await dm.sync_with_linear()
    first_issues_cursor = await dm.get_sync_cursor("linear:issues")
    first_projects_cursor = await dm.get_sync_cursor("linear:projects")
    assert first_issues_cursor
    assert first_projects_cursor

    await dm.sync_with_linear()
    second_issues_cursor = await dm.get_sync_cursor("linear:issues")
    second_projects_cursor = await dm.get_sync_cursor("linear:projects")

    assert first_issues_cursor == second_issues_cursor
    assert first_projects_cursor == second_projects_cursor


@pytest.mark.asyncio
async def test_linear_partial_failure_preserves_cache_and_recovery_converges(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-linear.db"
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    dm = DataManager(config=AppConfig(seed_mock_data=False))
    dm.db = Database(db_path)
    await dm.initialize()

    state = {"fail_issues": False, "new_payload": False}

    async def fake_get_me():
        return {"viewer": {"id": "viewer-1", "name": "Tester", "email": "tester@example.com"}}

    async def fake_get_projects():
        return [
            {
                "id": "p1",
                "name": "Project One",
                "targetDate": "2026-03-01",
                "state": "Active",
                "startDate": "2026-02-01",
                "description": "Alpha",
            }
        ]

    async def fake_get_team_workflow_states():
        return [
            {
                "id": "team-1",
                "key": "ENG",
                "name": "Engineering",
                "states": {
                    "nodes": [
                        {"id": "state-1", "name": "Todo", "type": "unstarted"},
                        {"id": "state-2", "name": "In Progress", "type": "started"},
                    ]
                },
            }
        ]

    async def fake_get_issues():
        if state["fail_issues"]:
            raise RuntimeError("rate limit")
        rows = [
            {
                "id": "lin-1",
                "identifier": "PD-1",
                "title": "First issue",
                "priority": 2,
                "state": {"id": "state-1", "name": "Todo", "type": "unstarted"},
                "dueDate": "2026-03-02",
                "project": {"id": "p1"},
                "team": {"id": "team-1"},
                "assignee": {"id": "u1", "name": "Alice", "avatarUrl": None},
                "estimate": 3,
            }
        ]
        if state["new_payload"]:
            rows.append(
                {
                    "id": "lin-2",
                    "identifier": "PD-2",
                    "title": "Second issue",
                    "priority": 3,
                    "state": {"id": "state-2", "name": "In Progress", "type": "started"},
                    "dueDate": "2026-03-03",
                    "project": {"id": "p1"},
                    "team": {"id": "team-1"},
                    "assignee": {"id": "u1", "name": "Alice", "avatarUrl": None},
                    "estimate": 2,
                }
            )
        return rows

    monkeypatch.setattr(dm.linear, "get_me", fake_get_me)
    monkeypatch.setattr(dm.linear, "get_projects", fake_get_projects)
    monkeypatch.setattr(dm.linear, "get_team_workflow_states", fake_get_team_workflow_states)
    monkeypatch.setattr(dm.linear, "get_issues", fake_get_issues)

    await dm.sync_with_linear()
    assert dm.last_sync_result == "success"
    assert len(dm.get_issues()) == 1

    state["new_payload"] = True
    state["fail_issues"] = True
    await dm.sync_with_linear()
    assert dm.last_sync_result == "failed"
    assert "issues fetch failed" in (dm.last_sync_error or "")
    assert len(dm.get_issues()) == 1

    state["fail_issues"] = False
    await dm.sync_with_linear()
    assert dm.last_sync_result == "success"
    assert len(dm.get_issues()) == 2
