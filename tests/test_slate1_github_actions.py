import pytest
from unittest.mock import AsyncMock, MagicMock
from projectdash.github import GitHubClient
from projectdash.services.github_mutation_service import GitHubMutationService
from projectdash.models import PullRequest, CiCheck

@pytest.mark.asyncio
async def test_github_client_rerun_actions():
    client = GitHubClient(token="fake")
    client._request = AsyncMock(return_value={})
    
    await client.rerun_workflow("owner", "repo", 123)
    client._request.assert_called_with("POST", "/repos/owner/repo/actions/runs/123/rerun")
    
    await client.rerun_job("owner", "repo", 456)
    client._request.assert_called_with("POST", "/repos/owner/repo/actions/jobs/456/rerun")
    
    await client.rerequest_check_run("owner", "repo", 789)
    client._request.assert_called_with("POST", "/repos/owner/repo/check-runs/789/rerequest")

@pytest.mark.asyncio
async def test_github_mutation_service_rerun():
    data = MagicMock()
    service = GitHubMutationService(data)
    data.record_action = AsyncMock()
    
    pr = PullRequest(id="github:o/r:pr:1", provider="github", repository_id="github:o/r", number=1, title="T", state="open")
    check = CiCheck(id="github:o/r:pr:1:check:123", provider="github", pull_request_id="github:o/r:pr:1", name="C", status="completed", conclusion="failure")
    
    data.pull_requests = [pr]
    data.ci_checks = [check]
    data.github.rerequest_check_run = AsyncMock(return_value={})
    data.db.save_ci_checks = AsyncMock()
    
    ok, message = await service.rerun_ci_check("github:o/r:pr:1:check:123")
    
    assert ok is True
    data.github.rerequest_check_run.assert_called_with("o", "r", 123)
    assert check.status == "queued"
    assert check.conclusion is None
    data.db.save_ci_checks.assert_called_once()
    data.record_action.assert_called_once()

@pytest.mark.asyncio
async def test_github_mutation_service_approve_merge():
    data = MagicMock()
    service = GitHubMutationService(data)
    data.record_action = AsyncMock()
    
    pr = PullRequest(id="github:o/r:pr:1", provider="github", repository_id="github:o/r", number=1, title="T", state="open")
    data.pull_requests = [pr]
    data.github.create_pr_review = AsyncMock(return_value={})
    data.github.merge_pull_request = AsyncMock(return_value={})
    data.db.save_pull_requests = AsyncMock()
    
    ok, message = await service.approve_pull_request("github:o/r:pr:1", body="LGTM")
    assert ok is True
    data.github.create_pr_review.assert_called_with("o", "r", 1, event="APPROVE", body="LGTM")
    
    ok, message = await service.merge_pull_request("github:o/r:pr:1", merge_method="squash")
    assert ok is True
    data.github.merge_pull_request.assert_called_with("o", "r", 1, merge_method="squash")
    assert pr.state == "merged"
    data.db.save_pull_requests.assert_called_once()
    assert data.record_action.call_count == 2
