from __future__ import annotations

from typing import TYPE_CHECKING, Any
from datetime import datetime
from projectdash.github import GitHubApiError

if TYPE_CHECKING:
    from projectdash.data import DataManager
    from projectdash.models import PullRequest, CiCheck

class GitHubMutationService:
    def __init__(self, data_manager: DataManager):
        self.data = data_manager

    async def approve_pull_request(self, pull_request_id: str, body: str | None = None) -> tuple[bool, str]:
        pr = self._get_pr(pull_request_id)
        if not pr:
            return False, f"Pull request not found: {pull_request_id}"
        
        owner, repo = self._parse_repo_id(pr.repository_id)
        try:
            await self.data.github.create_pr_review(
                owner, repo, pr.number, event="APPROVE", body=body
            )
            await self.data.record_action(
                action_type="approve_pr",
                target_id=pr.id,
                status="success",
                message=f"Approved PR #{pr.number}",
                payload={"body": body}
            )
            return True, f"Approved PR #{pr.number}"
        except GitHubApiError as e:
            await self.data.record_action(
                action_type="approve_pr",
                target_id=pr.id,
                status="error",
                message=str(e)
            )
            return False, f"Failed to approve PR: {e}"

    async def merge_pull_request(self, pull_request_id: str, merge_method: str = "merge") -> tuple[bool, str]:
        pr = self._get_pr(pull_request_id)
        if not pr:
            return False, f"Pull request not found: {pull_request_id}"
        
        owner, repo = self._parse_repo_id(pr.repository_id)
        try:
            await self.data.github.merge_pull_request(
                owner, repo, pr.number, merge_method=merge_method
            )
            
            # Local update
            pr.state = "merged"
            pr.merged_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            await self.data.db.save_pull_requests([pr])
            
            await self.data.record_action(
                action_type="merge_pr",
                target_id=pr.id,
                status="success",
                message=f"Merged PR #{pr.number}",
                payload={"merge_method": merge_method}
            )
            
            return True, f"Merged PR #{pr.number}"
        except GitHubApiError as e:
            await self.data.record_action(
                action_type="merge_pr",
                target_id=pr.id,
                status="error",
                message=str(e)
            )
            return False, f"Failed to merge PR: {e}"

    async def rerun_ci_check(self, ci_check_id: str) -> tuple[bool, str]:
        check = self._get_check(ci_check_id)
        if not check:
            return False, f"CI check not found: {ci_check_id}"
        
        pr = self._get_pr(check.pull_request_id)
        if not pr:
            return False, f"Pull request not found for check: {check.pull_request_id}"
        
        owner, repo = self._parse_repo_id(pr.repository_id)
        
        parts = ci_check_id.split(":check:")
        if len(parts) < 2:
            return False, f"Invalid CI check ID format: {ci_check_id}"
        
        github_check_id = int(parts[1])
        
        try:
            await self.data.github.rerequest_check_run(owner, repo, github_check_id)
            
            check.status = "queued"
            check.conclusion = None
            await self.data.db.save_ci_checks([check])
            
            await self.data.record_action(
                action_type="rerun_check",
                target_id=ci_check_id,
                status="success",
                message=f"Rerequested CI check: {check.name}"
            )
            
            return True, f"Rerequested CI check: {check.name}"
        except GitHubApiError as e:
            await self.data.record_action(
                action_type="rerun_check",
                target_id=ci_check_id,
                status="error",
                message=str(e)
            )
            return False, f"Failed to rerun CI check: {e}"

    async def rerun_workflow(self, repository_id: str, run_id: int) -> tuple[bool, str]:
        owner, repo = self._parse_repo_id(repository_id)
        try:
            await self.data.github.rerun_workflow(owner, repo, run_id)
            await self.data.record_action(
                action_type="rerun_workflow",
                target_id=f"{repository_id}:run:{run_id}",
                status="success",
                message=f"Reran workflow run {run_id}"
            )
            return True, f"Reran workflow run {run_id}"
        except GitHubApiError as e:
            await self.data.record_action(
                action_type="rerun_workflow",
                target_id=f"{repository_id}:run:{run_id}",
                status="error",
                message=str(e)
            )
            return False, f"Failed to rerun workflow: {e}"

    async def rerun_job(self, repository_id: str, job_id: int) -> tuple[bool, str]:
        owner, repo = self._parse_repo_id(repository_id)
        try:
            await self.data.github.rerun_job(owner, repo, job_id)
            await self.data.record_action(
                action_type="rerun_job",
                target_id=f"{repository_id}:job:{job_id}",
                status="success",
                message=f"Reran job {job_id}"
            )
            return True, f"Reran job {job_id}"
        except GitHubApiError as e:
            await self.data.record_action(
                action_type="rerun_job",
                target_id=f"{repository_id}:job:{job_id}",
                status="error",
                message=str(e)
            )
            return False, f"Failed to rerun job: {e}"

    def _get_pr(self, pull_request_id: str) -> PullRequest | None:
        for pr in self.data.pull_requests:
            if pr.id == pull_request_id:
                return pr
        return None

    def _get_check(self, ci_check_id: str) -> CiCheck | None:
        for check in self.data.ci_checks:
            if check.id == ci_check_id:
                return check
        return None

    def _parse_repo_id(self, repo_id: str) -> tuple[str, str]:
        # github:owner/repo
        parts = repo_id.split(":")
        if len(parts) < 2:
            raise ValueError(f"Invalid repository ID: {repo_id}")
        repo_full_name = parts[1]
        owner, repo = repo_full_name.split("/", 1)
        return owner, repo
