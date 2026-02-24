import pytest

from projectdash.config import AppConfig
from projectdash.data import DataManager
from projectdash.database import Database
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
