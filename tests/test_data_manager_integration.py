import pytest

from projectdash.config import AppConfig
from projectdash.data import DataManager
from projectdash.database import Database


@pytest.mark.asyncio
async def test_sync_persists_cache_and_restart_loads_all_entities(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-integration.db"
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")

    dm = DataManager(config=AppConfig(seed_mock_data=False))
    dm.db = Database(db_path)
    await dm.initialize()

    async def fake_get_me():
        return {"viewer": {"id": "viewer-1", "name": "Tester", "email": "tester@example.com"}}

    async def fake_get_projects():
        return [{"id": "p1", "name": "Project One", "targetDate": "2026-03-01", "state": "Active"}]

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

    restarted = DataManager(config=AppConfig(seed_mock_data=False))
    restarted.db = Database(db_path)
    await restarted.load_from_cache()

    assert restarted.last_sync_result == "idle"
    assert len(restarted.users) == 1
    assert len(restarted.projects) == 1
    assert len(restarted.issues) == 1
    assert "team-1" in restarted.workflow_states_by_team
    assert [s.id for s in restarted.workflow_states_by_team["team-1"]] == ["state-1", "state-2"]
    assert restarted.issues[0].id == "PD-1"
    assert restarted.issues[0].linear_id == "lin-1"


@pytest.mark.asyncio
async def test_restart_can_cycle_status_using_cached_workflow_states(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-integration.db"
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")

    dm = DataManager(config=AppConfig(seed_mock_data=False))
    dm.db = Database(db_path)
    await dm.initialize()

    async def fake_get_me():
        return {"viewer": {"id": "viewer-1", "name": "Tester", "email": "tester@example.com"}}

    async def fake_get_projects():
        return [{"id": "p1", "name": "Project One", "targetDate": "2026-03-01", "state": "Active"}]

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

    restarted = DataManager(config=AppConfig(seed_mock_data=False))
    restarted.db = Database(db_path)
    await restarted.load_from_cache()

    async def fake_update_issue_status(issue_id: str, state_id: str):
        assert issue_id == "lin-1"
        assert state_id == "state-2"
        return {"success": True}

    monkeypatch.setattr(restarted.linear, "update_issue_status", fake_update_issue_status)
    ok, message = await restarted.cycle_issue_status("PD-1", ("Todo", "In Progress"))

    assert ok is True
    assert "moved to In Progress" in message
    assert restarted.issues[0].status == "In Progress"
    assert restarted.issues[0].state_id == "state-2"


@pytest.mark.asyncio
async def test_sync_history_persists_across_restart(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-integration.db"
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")

    dm = DataManager(config=AppConfig(seed_mock_data=False))
    dm.db = Database(db_path)
    await dm.initialize()

    async def fake_get_me():
        return {"viewer": {"id": "viewer-1", "name": "Tester", "email": "tester@example.com"}}

    async def fake_get_projects():
        return [{"id": "p1", "name": "Project One", "targetDate": "2026-03-01", "state": "Active"}]

    async def fake_get_team_workflow_states():
        return [{"id": "team-1", "key": "ENG", "name": "Engineering", "states": {"nodes": []}}]

    async def fake_get_issues_ok():
        return []

    async def fake_get_issues_fail():
        raise RuntimeError("rate limit")

    monkeypatch.setattr(dm.linear, "get_me", fake_get_me)
    monkeypatch.setattr(dm.linear, "get_projects", fake_get_projects)
    monkeypatch.setattr(dm.linear, "get_team_workflow_states", fake_get_team_workflow_states)
    monkeypatch.setattr(dm.linear, "get_issues", fake_get_issues_ok)
    await dm.sync_with_linear()

    monkeypatch.setattr(dm.linear, "get_issues", fake_get_issues_fail)
    await dm.sync_with_linear()

    history = dm.get_sync_history()
    assert len(history) == 2
    assert history[0]["result"] == "failed"
    assert "issues fetch failed: rate limit" in history[0]["summary"]
    assert history[1]["result"] == "success"

    restarted = DataManager(config=AppConfig(seed_mock_data=False))
    restarted.db = Database(db_path)
    await restarted.load_from_cache()
    restarted_history = restarted.get_sync_history()
    assert len(restarted_history) == 2
    assert restarted_history[0]["result"] == "failed"
