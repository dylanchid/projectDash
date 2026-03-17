import pytest

from projectdash.config import AppConfig
from projectdash.data import DataManager
from projectdash.database import Database


@pytest.mark.asyncio
async def test_sync_with_github_fails_without_token(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-github.db"
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    dm = DataManager(config=AppConfig(github_repositories=("acme/platform",)))
    dm.db = Database(db_path)
    await dm.initialize()

    await dm.sync_with_github()

    assert dm.last_sync_result == "failed"
    assert dm.last_sync_error == "GITHUB_TOKEN not set"
    assert dm.sync_diagnostics["github_auth"] == "failed: GITHUB_TOKEN not set"


@pytest.mark.asyncio
async def test_sync_with_github_persists_repositories_prs_and_checks(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-github.db"
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    dm = DataManager(
        config=AppConfig(
            github_repositories=("acme/platform",),
            github_pr_limit=25,
            github_sync_checks=True,
            seed_mock_data=False,
        )
    )
    dm.db = Database(db_path)
    await dm.initialize()

    async def fake_get_current_user():
        return {"login": "octocat"}

    async def fake_get_repository(full_name: str):
        assert full_name == "acme/platform"
        return {
            "full_name": "acme/platform",
            "name": "platform",
            "owner": {"login": "acme"},
            "default_branch": "main",
            "private": False,
            "html_url": "https://github.com/acme/platform",
            "created_at": "2026-02-01T00:00:00Z",
            "updated_at": "2026-02-20T00:00:00Z",
        }

    async def fake_get_pull_requests(owner: str, repo: str, *, state: str = "all", limit: int = 50):
        assert owner == "acme"
        assert repo == "platform"
        assert state == "all"
        assert limit == 25
        return [
            {
                "number": 44,
                "title": "PD-44 tighten connector contract",
                "state": "open",
                "user": {"login": "alice"},
                "head": {"ref": "feature/PD-44-connector"},
                "base": {"ref": "main"},
                "html_url": "https://github.com/acme/platform/pull/44",
                "created_at": "2026-02-22T00:00:00Z",
                "updated_at": "2026-02-23T00:00:00Z",
                "closed_at": None,
                "merged_at": None,
            }
        ]

    async def fake_get_check_runs(owner: str, repo: str, head_sha: str):
        assert owner == "acme"
        assert repo == "platform"
        assert head_sha == "abc123"
        return [
            {
                "id": 901,
                "name": "ci / unit",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/acme/platform/runs/901",
                "started_at": "2026-02-23T01:00:00Z",
                "completed_at": "2026-02-23T01:04:00Z",
                "updated_at": "2026-02-23T01:04:00Z",
            }
        ]

    monkeypatch.setattr(dm.github, "get_current_user", fake_get_current_user)
    monkeypatch.setattr(dm.github, "get_repository", fake_get_repository)
    monkeypatch.setattr(dm.github, "get_pull_requests", fake_get_pull_requests)
    monkeypatch.setattr(dm.github, "get_check_runs", fake_get_check_runs)

    # Add head SHA only where DataManager reads it, while connector reads other PR fields.
    original_pulls = await fake_get_pull_requests("acme", "platform", state="all", limit=25)
    original_pulls[0]["head"]["sha"] = "abc123"

    async def fake_get_pull_requests_with_sha(owner: str, repo: str, *, state: str = "all", limit: int = 50):
        return original_pulls

    monkeypatch.setattr(dm.github, "get_pull_requests", fake_get_pull_requests_with_sha)

    await dm.sync_with_github()

    assert dm.last_sync_result == "success"
    assert dm.sync_status_summary() == "success r:1 pr:1 c:1"
    assert len(dm.get_repositories()) == 1
    assert len(dm.get_pull_requests("PD-44")) == 1
    prs = dm.get_pull_requests("PD-44")
    checks = dm.get_ci_checks(prs[0].id)
    assert len(checks) == 1
    assert checks[0].conclusion == "success"


@pytest.mark.asyncio
async def test_sync_with_github_discovers_repository_targets_when_unconfigured(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-github.db"
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.delenv("PD_GITHUB_REPOS", raising=False)
    dm = DataManager(config=AppConfig(github_repositories=()))
    dm.db = Database(db_path)
    await dm.initialize()

    async def fake_get_current_user():
        return {"login": "octocat"}

    async def fake_get_user_repositories(*, limit: int = 500):
        assert limit == 500
        return [{"full_name": "acme/platform"}]

    async def fake_get_repository(full_name: str):
        assert full_name == "acme/platform"
        return {
            "full_name": "acme/platform",
            "name": "platform",
            "owner": {"login": "acme"},
            "default_branch": "main",
            "private": False,
            "html_url": "https://github.com/acme/platform",
            "created_at": "2026-02-01T00:00:00Z",
            "updated_at": "2026-02-20T00:00:00Z",
        }

    async def fake_get_pull_requests(_owner: str, _repo: str, *, state: str = "all", limit: int = 50):
        return []

    monkeypatch.setattr(dm.github, "get_current_user", fake_get_current_user)
    monkeypatch.setattr(dm.github, "get_user_repositories", fake_get_user_repositories)
    monkeypatch.setattr(dm.github, "get_repository", fake_get_repository)
    monkeypatch.setattr(dm.github, "get_pull_requests", fake_get_pull_requests)

    await dm.sync_with_github()

    assert dm.last_sync_result == "success"
    assert dm.sync_diagnostics["github_targets"] == "ok: 1"
    repositories = dm.get_repositories()
    assert len(repositories) == 1
    assert repositories[0].id == "github:acme/platform"


@pytest.mark.asyncio
async def test_github_sync_checkpoints_are_stable_for_identical_upstream(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-github.db"
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    dm = DataManager(
        config=AppConfig(
            github_repositories=("acme/platform",),
            github_sync_checks=True,
            seed_mock_data=False,
        )
    )
    dm.db = Database(db_path)
    await dm.initialize()

    async def fake_get_current_user():
        return {"login": "octocat"}

    async def fake_get_repository(full_name: str):
        return {
            "full_name": full_name,
            "name": "platform",
            "owner": {"login": "acme"},
            "default_branch": "main",
            "private": False,
            "html_url": "https://github.com/acme/platform",
            "created_at": "2026-02-01T00:00:00Z",
            "updated_at": "2026-02-20T00:00:00Z",
        }

    async def fake_get_pull_requests(_owner: str, _repo: str, *, state: str = "all", limit: int = 50):
        return [
            {
                "number": 44,
                "title": "PD-44 tighten connector contract",
                "state": "open",
                "user": {"login": "alice"},
                "head": {"ref": "feature/PD-44-connector", "sha": "abc123"},
                "base": {"ref": "main"},
                "html_url": "https://github.com/acme/platform/pull/44",
                "created_at": "2026-02-22T00:00:00Z",
                "updated_at": "2026-02-23T00:00:00Z",
                "closed_at": None,
                "merged_at": None,
            }
        ]

    async def fake_get_check_runs(_owner: str, _repo: str, _head_sha: str):
        return [
            {
                "id": 901,
                "name": "ci / unit",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/acme/platform/runs/901",
                "started_at": "2026-02-23T01:00:00Z",
                "completed_at": "2026-02-23T01:04:00Z",
                "updated_at": "2026-02-23T01:04:00Z",
            }
        ]

    monkeypatch.setattr(dm.github, "get_current_user", fake_get_current_user)
    monkeypatch.setattr(dm.github, "get_repository", fake_get_repository)
    monkeypatch.setattr(dm.github, "get_pull_requests", fake_get_pull_requests)
    monkeypatch.setattr(dm.github, "get_check_runs", fake_get_check_runs)

    await dm.sync_with_github()
    first_pr_cursor = await dm.get_sync_cursor("github:pull_requests")
    first_check_cursor = await dm.get_sync_cursor("github:checks")
    assert first_pr_cursor
    assert first_check_cursor

    await dm.sync_with_github()
    second_pr_cursor = await dm.get_sync_cursor("github:pull_requests")
    second_check_cursor = await dm.get_sync_cursor("github:checks")

    assert first_pr_cursor == second_pr_cursor
    assert first_check_cursor == second_check_cursor


@pytest.mark.asyncio
async def test_github_sync_checkpoints_progress_when_upstream_changes(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-github.db"
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    dm = DataManager(
        config=AppConfig(
            github_repositories=("acme/platform",),
            github_sync_checks=True,
            seed_mock_data=False,
        )
    )
    dm.db = Database(db_path)
    await dm.initialize()

    payload_state = {"updated_at": "2026-02-23T00:00:00Z"}

    async def fake_get_current_user():
        return {"login": "octocat"}

    async def fake_get_repository(full_name: str):
        return {
            "full_name": full_name,
            "name": "platform",
            "owner": {"login": "acme"},
            "default_branch": "main",
            "private": False,
            "html_url": "https://github.com/acme/platform",
            "created_at": "2026-02-01T00:00:00Z",
            "updated_at": payload_state["updated_at"],
        }

    async def fake_get_pull_requests(_owner: str, _repo: str, *, state: str = "all", limit: int = 50):
        return [
            {
                "number": 44,
                "title": "PD-44 tighten connector contract",
                "state": "open",
                "user": {"login": "alice"},
                "head": {"ref": "feature/PD-44-connector", "sha": "abc123"},
                "base": {"ref": "main"},
                "html_url": "https://github.com/acme/platform/pull/44",
                "created_at": "2026-02-22T00:00:00Z",
                "updated_at": payload_state["updated_at"],
                "closed_at": None,
                "merged_at": None,
            }
        ]

    async def fake_get_check_runs(_owner: str, _repo: str, _head_sha: str):
        return [
            {
                "id": 901,
                "name": "ci / unit",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/acme/platform/runs/901",
                "started_at": "2026-02-23T01:00:00Z",
                "completed_at": "2026-02-23T01:04:00Z",
                "updated_at": payload_state["updated_at"],
            }
        ]

    monkeypatch.setattr(dm.github, "get_current_user", fake_get_current_user)
    monkeypatch.setattr(dm.github, "get_repository", fake_get_repository)
    monkeypatch.setattr(dm.github, "get_pull_requests", fake_get_pull_requests)
    monkeypatch.setattr(dm.github, "get_check_runs", fake_get_check_runs)

    await dm.sync_with_github()
    first_pr_cursor = await dm.get_sync_cursor("github:pull_requests")
    first_check_cursor = await dm.get_sync_cursor("github:checks")
    assert first_pr_cursor
    assert first_check_cursor

    payload_state["updated_at"] = "2026-02-24T00:00:00Z"
    await dm.sync_with_github()
    second_pr_cursor = await dm.get_sync_cursor("github:pull_requests")
    second_check_cursor = await dm.get_sync_cursor("github:checks")

    assert first_pr_cursor != second_pr_cursor
    assert first_check_cursor != second_check_cursor


@pytest.mark.asyncio
async def test_github_conflict_policy_keeps_newer_pull_request_snapshot(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-github.db"
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    dm = DataManager(
        config=AppConfig(
            github_repositories=("acme/platform",),
            github_sync_checks=False,
            seed_mock_data=False,
        )
    )
    dm.db = Database(db_path)
    await dm.initialize()

    sync_state = {"old_payload": False}

    async def fake_get_current_user():
        return {"login": "octocat"}

    async def fake_get_repository(full_name: str):
        return {
            "full_name": full_name,
            "name": "platform",
            "owner": {"login": "acme"},
            "default_branch": "main",
            "private": False,
            "html_url": "https://github.com/acme/platform",
            "created_at": "2026-02-01T00:00:00Z",
            "updated_at": "2026-02-25T00:00:00Z" if not sync_state["old_payload"] else "2026-02-20T00:00:00Z",
        }

    async def fake_get_pull_requests(_owner: str, _repo: str, *, state: str = "all", limit: int = 50):
        if sync_state["old_payload"]:
            updated_at = "2026-02-20T00:00:00Z"
            title = "PD-44 stale title"
        else:
            updated_at = "2026-02-25T00:00:00Z"
            title = "PD-44 newest title"
        return [
            {
                "number": 44,
                "title": title,
                "state": "open",
                "user": {"login": "alice"},
                "head": {"ref": "feature/PD-44-connector", "sha": "abc123"},
                "base": {"ref": "main"},
                "html_url": "https://github.com/acme/platform/pull/44",
                "created_at": "2026-02-22T00:00:00Z",
                "updated_at": updated_at,
                "closed_at": None,
                "merged_at": None,
            }
        ]

    monkeypatch.setattr(dm.github, "get_current_user", fake_get_current_user)
    monkeypatch.setattr(dm.github, "get_repository", fake_get_repository)
    monkeypatch.setattr(dm.github, "get_pull_requests", fake_get_pull_requests)

    await dm.sync_with_github()
    first_pr = dm.get_pull_requests("PD-44")[0]
    assert first_pr.title == "PD-44 newest title"

    sync_state["old_payload"] = True
    await dm.sync_with_github()
    second_pr = dm.get_pull_requests("PD-44")[0]

    assert second_pr.title == "PD-44 newest title"
    assert second_pr.updated_at == "2026-02-25T00:00:00Z"


@pytest.mark.asyncio
async def test_github_partial_failure_preserves_cache_and_recovery_converges(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "projectdash-github.db"
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    dm = DataManager(
        config=AppConfig(
            github_repositories=("acme/platform",),
            github_sync_checks=False,
            seed_mock_data=False,
        )
    )
    dm.db = Database(db_path)
    await dm.initialize()

    state = {"fail_second_repo": False}

    async def fake_get_current_user():
        return {"login": "octocat"}

    async def fake_get_repository(full_name: str):
        if full_name == "acme/web" and state["fail_second_repo"]:
            raise RuntimeError("repo fetch timeout")
        repo_name = full_name.split("/", 1)[1]
        return {
            "full_name": full_name,
            "name": repo_name,
            "owner": {"login": "acme"},
            "default_branch": "main",
            "private": False,
            "html_url": f"https://github.com/{full_name}",
            "created_at": "2026-02-01T00:00:00Z",
            "updated_at": "2026-02-25T00:00:00Z",
        }

    async def fake_get_pull_requests(owner: str, repo: str, *, state: str = "all", limit: int = 50):
        number = 44 if repo == "platform" else 77
        return [
            {
                "number": number,
                "title": f"PD-{number} update {repo}",
                "state": "open",
                "user": {"login": "alice"},
                "head": {"ref": f"feature/PD-{number}", "sha": f"sha-{number}"},
                "base": {"ref": "main"},
                "html_url": f"https://github.com/{owner}/{repo}/pull/{number}",
                "created_at": "2026-02-22T00:00:00Z",
                "updated_at": "2026-02-25T00:00:00Z",
                "closed_at": None,
                "merged_at": None,
            }
        ]

    monkeypatch.setattr(dm.github, "get_current_user", fake_get_current_user)
    monkeypatch.setattr(dm.github, "get_repository", fake_get_repository)
    monkeypatch.setattr(dm.github, "get_pull_requests", fake_get_pull_requests)

    await dm.sync_with_github()
    assert dm.last_sync_result == "success"
    assert len(dm.get_repositories()) == 1
    assert len(dm.get_pull_requests()) == 1

    dm.config = AppConfig(
        github_repositories=("acme/platform", "acme/web"),
        github_sync_checks=False,
        seed_mock_data=False,
    )
    state["fail_second_repo"] = True
    await dm.sync_with_github()
    assert dm.last_sync_result == "failed"
    assert "acme/web" in (dm.last_sync_error or "")
    assert len(dm.get_repositories()) == 1
    assert len(dm.get_pull_requests()) == 1

    state["fail_second_repo"] = False
    await dm.sync_with_github()
    assert dm.last_sync_result == "success"
    repos = dm.get_repositories()
    prs = dm.get_pull_requests()
    assert len(repos) == 2
    assert len(prs) == 2
