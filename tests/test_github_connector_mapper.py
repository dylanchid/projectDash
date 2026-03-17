from projectdash.connectors import GitHubConnector


def test_build_entities_maps_repository_pull_requests_and_checks() -> None:
    connector = GitHubConnector()
    entities = connector.build_entities(
        raw_repository={
            "full_name": "acme/platform",
            "name": "platform",
            "owner": {"login": "acme"},
            "default_branch": "main",
            "private": True,
            "html_url": "https://github.com/acme/platform",
            "created_at": "2026-02-01T00:00:00Z",
            "updated_at": "2026-02-20T00:00:00Z",
        },
        raw_pull_requests=[
            {
                "number": 42,
                "title": "PD-101 implement connector",
                "state": "open",
                "user": {"login": "alice"},
                "head": {"ref": "feature/PD-101-connector"},
                "base": {"ref": "main"},
                "html_url": "https://github.com/acme/platform/pull/42",
                "created_at": "2026-02-20T00:00:00Z",
                "updated_at": "2026-02-21T00:00:00Z",
                "closed_at": None,
                "merged_at": None,
            }
        ],
        raw_checks_by_pr_number={
            42: [
                {
                    "id": 7001,
                    "name": "ci / test",
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "https://github.com/acme/platform/runs/7001",
                    "started_at": "2026-02-20T01:00:00Z",
                    "completed_at": "2026-02-20T01:05:00Z",
                    "updated_at": "2026-02-20T01:05:00Z",
                }
            ]
        },
    )

    assert len(entities.repositories) == 1
    assert len(entities.pull_requests) == 1
    assert len(entities.ci_checks) == 1
    assert entities.repositories[0].id == "github:acme/platform"
    assert entities.pull_requests[0].issue_id == "PD-101"
    assert entities.ci_checks[0].pull_request_id == entities.pull_requests[0].id


def test_pr_state_uses_merged_at_for_merged_state() -> None:
    connector = GitHubConnector()
    entities = connector.build_entities(
        raw_repository={
            "full_name": "acme/platform",
            "name": "platform",
            "owner": {"login": "acme"},
        },
        raw_pull_requests=[
            {
                "number": 7,
                "title": "release prep",
                "state": "closed",
                "user": {"login": "alice"},
                "head": {"ref": "release"},
                "base": {"ref": "main"},
                "updated_at": "2026-02-21T00:00:00Z",
                "merged_at": "2026-02-21T00:00:00Z",
            }
        ],
    )

    assert entities.pull_requests[0].state == "merged"

