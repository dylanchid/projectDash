from __future__ import annotations

import aiosqlite
import pytest

from projectdash.database import Database
from projectdash.models import AgentRun, CiCheck, PullRequest, Repository


@pytest.mark.asyncio
async def test_init_db_creates_expansion_tables(tmp_path) -> None:
    db_path = tmp_path / "projectdash-expansion.db"
    db = Database(db_path)
    await db.init_db()

    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
            rows = await cursor.fetchall()

    table_names = {row[0] for row in rows}
    expected = {
        "repositories",
        "pull_requests",
        "ci_checks",
        "work_events",
        "agent_runs",
        "sync_cursors",
    }
    assert expected.issubset(table_names)


@pytest.mark.asyncio
async def test_sync_cursor_round_trip(tmp_path) -> None:
    db_path = tmp_path / "projectdash-expansion.db"
    db = Database(db_path)
    await db.init_db()

    assert await db.get_sync_cursor("github") is None
    await db.save_sync_cursor("github", "cursor-1")
    assert await db.get_sync_cursor("github") == "cursor-1"
    await db.save_sync_cursor("github", "cursor-2")
    assert await db.get_sync_cursor("github") == "cursor-2"


@pytest.mark.asyncio
async def test_agent_runs_round_trip(tmp_path) -> None:
    db_path = tmp_path / "projectdash-expansion.db"
    db = Database(db_path)
    await db.init_db()

    run = AgentRun(
        id="run-1",
        runtime="tmux",
        status="running",
        started_at="2026-02-25 12:00:00",
        issue_id="PD-1",
        project_id="p1",
        artifacts={"log": "session.log"},
    )
    await db.save_agent_run(run)
    saved = await db.get_agent_runs(limit=10)
    fetched = await db.get_agent_run("run-1")

    assert len(saved) == 1
    assert saved[0].id == "run-1"
    assert saved[0].runtime == "tmux"
    assert saved[0].status == "running"
    assert saved[0].artifacts == {"log": "session.log"}
    assert fetched is not None
    assert fetched.id == "run-1"


@pytest.mark.asyncio
async def test_repository_pr_and_check_round_trip(tmp_path) -> None:
    db_path = tmp_path / "projectdash-expansion.db"
    db = Database(db_path)
    await db.init_db()

    repository = Repository(
        id="github:acme/platform",
        provider="github",
        organization="acme",
        name="platform",
        default_branch="main",
        is_private=False,
        url="https://github.com/acme/platform",
        created_at="2026-02-20 10:00:00",
        updated_at="2026-02-20 10:00:00",
    )
    pull_request = PullRequest(
        id="github:acme/platform:pr:9",
        provider="github",
        repository_id=repository.id,
        number=9,
        title="PD-9 update connector",
        state="open",
        issue_id="PD-9",
        updated_at="2026-02-20 10:02:00",
    )
    check = CiCheck(
        id="github:acme/platform:pr:9:check:101",
        provider="github",
        pull_request_id=pull_request.id,
        name="ci / tests",
        status="completed",
        conclusion="success",
        updated_at="2026-02-20 10:03:00",
    )

    await db.save_repositories([repository])
    await db.save_pull_requests([pull_request])
    await db.save_ci_checks([check])

    repositories = await db.get_repositories(provider="github")
    pull_requests = await db.get_pull_requests(issue_id="PD-9")
    checks = await db.get_ci_checks(pull_request_id=pull_request.id)

    assert len(repositories) == 1
    assert repositories[0].name == "platform"
    assert len(pull_requests) == 1
    assert pull_requests[0].id == pull_request.id
    assert len(checks) == 1
    assert checks[0].conclusion == "success"
