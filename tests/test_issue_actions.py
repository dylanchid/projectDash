import pytest

from projectdash.config import AppConfig
from projectdash.data import DataManager
from projectdash.linear import LinearApiError
from projectdash.models import Issue, LinearWorkflowState, User


@pytest.mark.asyncio
async def test_cycle_issue_status_success_write_through(monkeypatch) -> None:
    dm = DataManager(config=AppConfig())
    dm.users = [User("u1", "Alice")]
    dm.workflow_states_by_team = {
        "team-1": [LinearWorkflowState(id="state-2", name="In Progress", type="started", team_id="team-1")]
    }
    dm.issues = [Issue("X-1", "Task", "Medium", "Todo", dm.users[0], 3, team_id="team-1", linear_id="lin-1")]

    async def save_ok(_issues, project_id=None):
        return None

    async def remote_ok(issue_id: str, state_id: str):
        assert issue_id == "lin-1"
        assert state_id == "state-2"
        return {"success": True}

    monkeypatch.setattr(dm.linear, "update_issue_status", remote_ok)
    monkeypatch.setattr(dm.db, "save_issues", save_ok)
    ok, message = await dm.cycle_issue_status("X-1", ("Todo", "In Progress", "Done"))
    assert ok is True
    assert dm.issues[0].status == "In Progress"
    assert "moved to In Progress" in message


@pytest.mark.asyncio
async def test_cycle_issue_points_rolls_back_on_remote_failure(monkeypatch) -> None:
    dm = DataManager(config=AppConfig())
    dm.users = [User("u1", "Alice")]
    dm.issues = [Issue("X-1", "Task", "Medium", "Todo", dm.users[0], 5, linear_id="lin-1")]

    async def remote_fail(_issue_id: str, _estimate: int):
        raise LinearApiError("Issue is archived", code="FORBIDDEN")

    async def save_ok(_issues, project_id=None):
        return None

    monkeypatch.setattr(dm.linear, "update_issue_estimate", remote_fail)
    monkeypatch.setattr(dm.db, "save_issues", save_ok)
    ok, message = await dm.cycle_issue_points("X-1")
    assert ok is False
    assert "Estimate update failed" in message
    assert "issue is archived" in message.casefold()
    assert dm.issues[0].points == 5


@pytest.mark.asyncio
async def test_cycle_issue_status_uses_configured_linear_mapping(monkeypatch) -> None:
    dm = DataManager(config=AppConfig(linear_status_mappings={"in progress": "state-2"}))
    dm.users = [User("u1", "Alice")]
    dm.workflow_states_by_team = {
        "team-1": [LinearWorkflowState(id="state-2", name="Started", type="started", team_id="team-1")]
    }
    dm.issues = [Issue("X-1", "Task", "Medium", "Todo", dm.users[0], 3, team_id="team-1", linear_id="lin-1")]

    async def save_ok(_issues, project_id=None):
        return None

    async def remote_ok(_issue_id: str, _state_id: str):
        return {"success": True}

    monkeypatch.setattr(dm.linear, "update_issue_status", remote_ok)
    monkeypatch.setattr(dm.db, "save_issues", save_ok)
    ok, message = await dm.cycle_issue_status("X-1", ("Todo", "In Progress", "Done"))
    assert ok is True
    assert "warning:" not in message
    assert dm.issues[0].state_id == "state-2"


@pytest.mark.asyncio
async def test_cycle_issue_status_fails_when_mapping_missing(monkeypatch) -> None:
    dm = DataManager(config=AppConfig())
    dm.users = [User("u1", "Alice")]
    dm.workflow_states_by_team = {
        "team-1": [LinearWorkflowState(id="state-3", name="Started", type="started", team_id="team-1")]
    }
    dm.issues = [Issue("X-1", "Task", "Medium", "Todo", dm.users[0], 3, team_id="team-1", linear_id="lin-1")]

    async def save_ok(_issues, project_id=None):
        return None

    called_remote = False

    async def remote_should_not_run(_issue_id: str, _state_id: str):
        nonlocal called_remote
        called_remote = True
        return {"success": True}

    monkeypatch.setattr(dm.linear, "update_issue_status", remote_should_not_run)
    monkeypatch.setattr(dm.db, "save_issues", save_ok)
    ok, message = await dm.cycle_issue_status("X-1", ("Todo", "In Progress", "Done"))
    assert ok is False
    assert "no mapping for status" in message
    assert called_remote is False
    assert dm.issues[0].state_id is None


@pytest.mark.asyncio
async def test_cycle_issue_assignee_rolls_back_on_permission_error(monkeypatch) -> None:
    dm = DataManager(config=AppConfig())
    dm.users = [User("u1", "Alice"), User("u2", "Bob")]
    dm.issues = [Issue("X-1", "Task", "Medium", "Todo", dm.users[0], 2, linear_id="lin-1")]

    async def remote_fail(_issue_id, _assignee_id):
        raise LinearApiError("You don't have permission", code="FORBIDDEN")

    async def save_ok(_issues, project_id=None):
        return None

    monkeypatch.setattr(dm.linear, "update_issue_assignee", remote_fail)
    monkeypatch.setattr(dm.db, "save_issues", save_ok)
    ok, message = await dm.cycle_issue_assignee("X-1")
    assert ok is False
    assert "permission denied" in message.casefold()
    assert dm.issues[0].assignee is dm.users[0]


@pytest.mark.asyncio
async def test_cycle_issue_points_reconciles_with_targeted_refetch(monkeypatch) -> None:
    dm = DataManager(config=AppConfig())
    dm.linear.api_key = "test-key"
    dm.users = [User("u1", "Alice")]
    dm.issues = [Issue("X-1", "Task", "Medium", "Todo", dm.users[0], 5, linear_id="lin-1")]

    async def remote_fail(_issue_id: str, _estimate: int):
        raise LinearApiError("stale issue", code="CONFLICT")

    async def get_issue_ok(_issue_id: str):
        return {
            "id": "lin-1",
            "identifier": "X-1",
            "title": "Task (Remote)",
            "priority": 2,
            "state": {"id": "st-1", "name": "In Progress", "type": "started"},
            "dueDate": None,
            "project": {"id": "p1"},
            "team": {"id": "t1"},
            "assignee": {"id": "u1", "name": "Alice", "avatarUrl": None},
            "estimate": 8,
        }

    async def save_issues_ok(_issues, project_id=None):
        return None

    async def save_users_ok(_users):
        return None

    monkeypatch.setattr(dm.linear, "update_issue_estimate", remote_fail)
    monkeypatch.setattr(dm.linear, "get_issue", get_issue_ok)
    monkeypatch.setattr(dm.db, "save_issues", save_issues_ok)
    monkeypatch.setattr(dm.db, "save_users", save_users_ok)

    ok, message = await dm.cycle_issue_points("X-1")
    assert ok is False
    assert "re-fetched latest issue" in message
    assert dm.issues[0].title == "Task (Remote)"
    assert dm.issues[0].points == 8


@pytest.mark.asyncio
async def test_cycle_issue_points_reconciles_with_full_sync_fallback(monkeypatch) -> None:
    dm = DataManager(config=AppConfig())
    dm.linear.api_key = "test-key"
    dm.users = [User("u1", "Alice")]
    dm.issues = [Issue("X-1", "Task", "Medium", "Todo", dm.users[0], 5, linear_id="lin-1")]

    async def remote_fail(_issue_id: str, _estimate: int):
        raise LinearApiError("stale issue", code="CONFLICT")

    async def get_issue_missing(_issue_id: str):
        return None

    async def sync_ok():
        dm.last_sync_result = "success"
        return None

    async def save_issues_ok(_issues, project_id=None):
        return None

    monkeypatch.setattr(dm.linear, "update_issue_estimate", remote_fail)
    monkeypatch.setattr(dm.linear, "get_issue", get_issue_missing)
    monkeypatch.setattr(dm, "sync_with_linear", sync_ok)
    monkeypatch.setattr(dm.db, "save_issues", save_issues_ok)

    ok, message = await dm.cycle_issue_points("X-1")
    assert ok is False
    assert "triggered full re-sync" in message
    assert dm.issues[0].points == 5


@pytest.mark.asyncio
async def test_cycle_issue_points_remote_failure_without_reconcile_suffix(monkeypatch) -> None:
    dm = DataManager(config=AppConfig())
    dm.linear.api_key = "test-key"
    dm.users = [User("u1", "Alice")]
    dm.issues = [Issue("X-1", "Task", "Medium", "Todo", dm.users[0], 5, linear_id="lin-1")]

    async def remote_fail(_issue_id: str, _estimate: int):
        raise LinearApiError("stale issue", code="CONFLICT")

    async def get_issue_fails(_issue_id: str):
        raise RuntimeError("network")

    async def sync_fails():
        raise RuntimeError("network")

    async def save_issues_ok(_issues, project_id=None):
        return None

    monkeypatch.setattr(dm.linear, "update_issue_estimate", remote_fail)
    monkeypatch.setattr(dm.linear, "get_issue", get_issue_fails)
    monkeypatch.setattr(dm, "sync_with_linear", sync_fails)
    monkeypatch.setattr(dm.db, "save_issues", save_issues_ok)

    ok, message = await dm.cycle_issue_points("X-1")
    assert ok is False
    assert "stale issue data" in message
    assert "re-fetched latest issue" not in message
    assert "triggered full re-sync" not in message
    assert dm.issues[0].points == 5


@pytest.mark.asyncio
async def test_apply_remote_issue_replaces_existing_by_linear_id(monkeypatch) -> None:
    dm = DataManager(config=AppConfig())
    dm.users = [User("u1", "Alice")]
    dm.issues = [Issue("X-OLD", "Old", "Low", "Todo", dm.users[0], 1, linear_id="lin-1")]

    async def save_issues_ok(_issues, project_id=None):
        return None

    async def save_users_ok(_users):
        return None

    monkeypatch.setattr(dm.db, "save_issues", save_issues_ok)
    monkeypatch.setattr(dm.db, "save_users", save_users_ok)

    await dm._apply_remote_issue(
        {
            "id": "lin-1",
            "identifier": "X-1",
            "title": "New",
            "priority": 2,
            "state": {"id": "st-1", "name": "In Progress", "type": "started"},
            "dueDate": None,
            "project": {"id": "p1"},
            "team": {"id": "t1"},
            "assignee": {"id": "u1", "name": "Alice", "avatarUrl": None},
            "estimate": 3,
        }
    )

    assert len(dm.issues) == 1
    assert dm.issues[0].id == "X-1"
    assert dm.issues[0].title == "New"


@pytest.mark.asyncio
async def test_apply_remote_issue_replaces_existing_by_identifier(monkeypatch) -> None:
    dm = DataManager(config=AppConfig())
    dm.users = [User("u1", "Alice")]
    dm.issues = [Issue("X-1", "Old", "Low", "Todo", dm.users[0], 1, linear_id=None)]

    async def save_issues_ok(_issues, project_id=None):
        return None

    async def save_users_ok(_users):
        return None

    monkeypatch.setattr(dm.db, "save_issues", save_issues_ok)
    monkeypatch.setattr(dm.db, "save_users", save_users_ok)

    await dm._apply_remote_issue(
        {
            "id": "lin-1",
            "identifier": "X-1",
            "title": "Updated",
            "priority": 2,
            "state": {"id": "st-1", "name": "In Progress", "type": "started"},
            "dueDate": None,
            "project": {"id": "p1"},
            "team": {"id": "t1"},
            "assignee": {"id": "u1", "name": "Alice", "avatarUrl": None},
            "estimate": 5,
        }
    )

    assert len(dm.issues) == 1
    assert dm.issues[0].id == "X-1"
    assert dm.issues[0].title == "Updated"
