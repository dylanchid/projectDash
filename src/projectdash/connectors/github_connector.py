from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from projectdash.enums import PullRequestState
from projectdash.models import CiCheck, PullRequest, Repository

ISSUE_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


@dataclass
class GitHubConnectorEntities:
    repositories: list[Repository] = field(default_factory=list)
    pull_requests: list[PullRequest] = field(default_factory=list)
    ci_checks: list[CiCheck] = field(default_factory=list)


class GitHubConnector:
    name = "github"
    required_env = ("GITHUB_TOKEN",)

    def build_entities(
        self,
        *,
        raw_repository: dict,
        raw_pull_requests: list[dict],
        raw_checks_by_pr_number: dict[int, list[dict]] | None = None,
    ) -> GitHubConnectorEntities:
        repository = self._build_repository(raw_repository)
        pull_requests = self._build_pull_requests(repository.id, raw_pull_requests)
        checks_by_pr_number = raw_checks_by_pr_number or {}
        ci_checks: list[CiCheck] = []
        for pr in pull_requests:
            raw_checks = checks_by_pr_number.get(pr.number, [])
            ci_checks.extend(self._build_checks(pr.id, raw_checks))
        return GitHubConnectorEntities(
            repositories=[repository],
            pull_requests=pull_requests,
            ci_checks=ci_checks,
        )

    def _build_repository(self, raw_repository: dict) -> Repository:
        full_name = str(raw_repository.get("full_name") or "").strip().lower()
        if not full_name:
            owner = raw_repository.get("owner", {}).get("login", "")
            name = raw_repository.get("name", "")
            full_name = f"{owner}/{name}".strip("/").lower()
        repo_id = f"github:{full_name}"
        owner_login = raw_repository.get("owner", {}).get("login")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return Repository(
            id=repo_id,
            provider="github",
            name=raw_repository.get("name") or full_name.split("/")[-1],
            organization=owner_login,
            default_branch=raw_repository.get("default_branch"),
            is_private=bool(raw_repository.get("private", False)),
            url=raw_repository.get("html_url"),
            created_at=raw_repository.get("created_at") or now,
            updated_at=raw_repository.get("updated_at") or now,
        )

    def _build_pull_requests(self, repository_id: str, raw_pull_requests: list[dict]) -> list[PullRequest]:
        pull_requests: list[PullRequest] = []
        for raw_pr in raw_pull_requests:
            pr_number = int(raw_pr.get("number", 0))
            if pr_number <= 0:
                continue
            pr_id = f"{repository_id}:pr:{pr_number}"
            title = str(raw_pr.get("title") or "").strip()
            head_branch = raw_pr.get("head", {}).get("ref")
            base_branch = raw_pr.get("base", {}).get("ref")
            state = self._pr_state(raw_pr)
            issue_id = self._resolve_issue_id(title, head_branch, base_branch)
            pull_requests.append(
                PullRequest(
                    id=pr_id,
                    provider="github",
                    repository_id=repository_id,
                    number=pr_number,
                    title=title or f"PR #{pr_number}",
                    state=state,
                    author_id=raw_pr.get("user", {}).get("login"),
                    head_branch=head_branch,
                    base_branch=base_branch,
                    url=raw_pr.get("html_url"),
                    issue_id=issue_id,
                    opened_at=raw_pr.get("created_at"),
                    merged_at=raw_pr.get("merged_at"),
                    closed_at=raw_pr.get("closed_at"),
                    updated_at=raw_pr.get("updated_at"),
                )
            )
        return pull_requests

    def _build_checks(self, pull_request_id: str, raw_checks: list[dict]) -> list[CiCheck]:
        checks: list[CiCheck] = []
        for raw_check in raw_checks:
            check_id = raw_check.get("id")
            if check_id is None:
                continue
            checks.append(
                CiCheck(
                    id=f"{pull_request_id}:check:{check_id}",
                    provider="github",
                    pull_request_id=pull_request_id,
                    name=raw_check.get("name") or str(check_id),
                    status=raw_check.get("status") or "unknown",
                    conclusion=raw_check.get("conclusion"),
                    url=raw_check.get("html_url") or raw_check.get("details_url"),
                    started_at=raw_check.get("started_at"),
                    completed_at=raw_check.get("completed_at"),
                    updated_at=raw_check.get("updated_at"),
                )
            )
        return checks

    def _resolve_issue_id(self, title: str, head_branch: str | None, base_branch: str | None) -> str | None:
        for candidate in (title, head_branch or "", base_branch or ""):
            match = ISSUE_KEY_PATTERN.search(candidate)
            if match:
                return match.group(1)
        return None

    def _pr_state(self, raw_pr: dict) -> str:
        if raw_pr.get("merged_at"):
            return PullRequestState.MERGED
        state = str(raw_pr.get("state") or "").strip().casefold()
        if state in {PullRequestState.OPEN, PullRequestState.CLOSED}:
            return state
        return "unknown"

