from __future__ import annotations

from projectdash.connectors import LinearConnector


def test_build_entities_maps_linear_payloads() -> None:
    connector = LinearConnector()
    entities = connector.build_entities(
        raw_projects=[
            {
                "id": "p1",
                "name": "Platform",
                "description": "Core platform work",
                "startDate": "2026-02-01",
                "targetDate": "2026-03-01",
                "state": "Active",
            }
        ],
        raw_teams=[
            {
                "id": "t1",
                "key": "ENG",
                "states": {
                    "nodes": [
                        {"id": "s1", "name": "Todo", "type": "unstarted"},
                        {"id": "s2", "name": "In Progress", "type": "started"},
                    ]
                },
            }
        ],
        raw_issues=[
            {
                "id": "lin-1",
                "identifier": "PD-1",
                "title": "Build connector layer",
                "priority": 2,
                "state": {"id": "s2", "name": "In Progress", "type": "started"},
                "dueDate": "2026-02-26",
                "project": {"id": "p1"},
                "team": {"id": "t1"},
                "assignee": {"id": "u1", "name": "Alice", "avatarUrl": None},
                "estimate": 5,
            },
            {
                "id": "lin-2",
                "identifier": "PD-2",
                "title": "Ship migration",
                "priority": 3,
                "state": {"id": "s1", "name": "Todo", "type": "unstarted"},
                "dueDate": None,
                "project": {"id": "p1"},
                "team": {"id": "t1"},
                "assignee": {"id": "u1", "name": "Alice", "avatarUrl": None},
                "estimate": 3,
            },
        ],
    )

    assert len(entities.users) == 1
    assert len(entities.projects) == 1
    assert len(entities.issues) == 2
    assert len(entities.workflow_states) == 2

    project = entities.projects[0]
    assert project.issues_count == 2
    assert project.in_progress_count == 1
    assert project.blocked_count == 0


def test_workflow_states_by_team_groups_team_states() -> None:
    connector = LinearConnector()
    grouped = connector.workflow_states_by_team(
        [
            {
                "id": "t1",
                "key": "ENG",
                "states": {"nodes": [{"id": "s1", "name": "Todo", "type": "unstarted"}]},
            },
            {
                "id": "t2",
                "key": "OPS",
                "states": {"nodes": [{"id": "s9", "name": "Blocked", "type": "backlog"}]},
            },
        ]
    )

    assert sorted(grouped.keys()) == ["t1", "t2"]
    assert grouped["t1"][0].team_key == "ENG"
    assert grouped["t2"][0].name == "Blocked"

