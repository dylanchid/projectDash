import pytest

from projectdash.linear import LinearClient


@pytest.mark.asyncio
async def test_get_projects_paginates(monkeypatch) -> None:
    client = LinearClient(api_key="test-key")
    calls: list[dict] = []

    async def fake_query(_query: str, variables: dict | None = None) -> dict:
        assert variables is not None
        calls.append(variables)
        if len(calls) == 1:
            return {
                "projects": {
                    "nodes": [{"id": "p1", "name": "One", "targetDate": None, "state": "started"}],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cur-1"},
                }
            }
        return {
            "projects": {
                "nodes": [{"id": "p2", "name": "Two", "targetDate": None, "state": "started"}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }

    monkeypatch.setattr(client, "_query", fake_query)
    projects = await client.get_projects()

    assert [p["id"] for p in projects] == ["p1", "p2"]
    assert calls == [{"first": 100, "after": None}, {"first": 100, "after": "cur-1"}]


@pytest.mark.asyncio
async def test_get_issues_paginates(monkeypatch) -> None:
    client = LinearClient(api_key="test-key")
    calls: list[dict] = []

    async def fake_query(_query: str, variables: dict | None = None) -> dict:
        assert variables is not None
        calls.append(variables)
        if len(calls) == 1:
            return {
                "issues": {
                    "nodes": [
                        {
                            "id": "i1",
                            "identifier": "PD-1",
                            "title": "First",
                            "priority": 1,
                            "state": {"id": "s1", "name": "Todo", "type": "unstarted"},
                            "dueDate": None,
                            "project": {"id": "p1"},
                            "team": {"id": "t1"},
                            "assignee": None,
                            "estimate": 2,
                        }
                    ],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cur-1"},
                }
            }
        return {
            "issues": {
                "nodes": [
                    {
                        "id": "i2",
                        "identifier": "PD-2",
                        "title": "Second",
                        "priority": 2,
                        "state": {"id": "s2", "name": "In Progress", "type": "started"},
                        "dueDate": None,
                        "project": {"id": "p1"},
                        "team": {"id": "t1"},
                        "assignee": None,
                        "estimate": 3,
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }

    monkeypatch.setattr(client, "_query", fake_query)
    issues = await client.get_issues()

    assert [i["id"] for i in issues] == ["i1", "i2"]
    assert calls == [{"first": 100, "after": None}, {"first": 100, "after": "cur-1"}]


@pytest.mark.asyncio
async def test_get_team_workflow_states_paginates(monkeypatch) -> None:
    client = LinearClient(api_key="test-key")
    calls: list[dict] = []

    async def fake_query(_query: str, variables: dict | None = None) -> dict:
        assert variables is not None
        calls.append(variables)
        if len(calls) == 1:
            return {
                "teams": {
                    "nodes": [{"id": "t1", "key": "ENG", "name": "Eng", "states": {"nodes": []}}],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cur-1"},
                }
            }
        return {
            "teams": {
                "nodes": [{"id": "t2", "key": "OPS", "name": "Ops", "states": {"nodes": []}}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }

    monkeypatch.setattr(client, "_query", fake_query)
    teams = await client.get_team_workflow_states()

    assert [t["id"] for t in teams] == ["t1", "t2"]
    assert calls == [{"first": 100, "after": None}, {"first": 100, "after": "cur-1"}]
