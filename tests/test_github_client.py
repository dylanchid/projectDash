import pytest

from projectdash.github import GitHubClient


@pytest.mark.asyncio
async def test_get_pull_requests_respects_limit(monkeypatch) -> None:
    client = GitHubClient(token="test-token")
    calls: list[dict] = []

    async def fake_request(_method: str, _path: str, *, params=None):
        assert params is not None
        calls.append(params)
        return [
            {"number": 3, "state": "open"},
            {"number": 2, "state": "closed"},
            {"number": 1, "state": "closed"},
        ]

    monkeypatch.setattr(client, "_request", fake_request)
    pull_requests = await client.get_pull_requests("acme", "platform", limit=2)

    assert [pr["number"] for pr in pull_requests] == [3, 2]
    assert calls[0]["state"] == "all"
    assert calls[0]["page"] == 1


@pytest.mark.asyncio
async def test_get_check_runs_returns_embedded_rows(monkeypatch) -> None:
    client = GitHubClient(token="test-token")

    async def fake_request(_method: str, _path: str, *, params=None):
        assert params == {"per_page": 100}
        return {"total_count": 2, "check_runs": [{"id": 11}, {"id": 12}]}

    monkeypatch.setattr(client, "_request", fake_request)
    checks = await client.get_check_runs("acme", "platform", "abc123")

    assert [row["id"] for row in checks] == [11, 12]


@pytest.mark.asyncio
async def test_get_user_repositories_respects_limit(monkeypatch) -> None:
    client = GitHubClient(token="test-token")
    calls: list[dict] = []

    async def fake_request(_method: str, _path: str, *, params=None):
        assert params is not None
        calls.append(params)
        return [
            {"full_name": "acme/repo-1"},
            {"full_name": "acme/repo-2"},
            {"full_name": "acme/repo-3"},
        ]

    monkeypatch.setattr(client, "_request", fake_request)
    repos = await client.get_user_repositories(limit=2)

    assert [repo["full_name"] for repo in repos] == ["acme/repo-1", "acme/repo-2"]
    assert calls[0]["page"] == 1
