from __future__ import annotations

from typing import TYPE_CHECKING

from projectdash.models import CiCheck, PullRequest, Repository

if TYPE_CHECKING:
    from projectdash.data import DataManager


class GitHubQueryService:
    def __init__(self, data_manager: DataManager):
        self.data = data_manager

    def get_repositories(self) -> list[Repository]:
        return self.data.repositories

    def get_pull_requests(self, issue_id: str | None = None) -> list[PullRequest]:
        if issue_id is None:
            return self.data.pull_requests
        return [pull_request for pull_request in self.data.pull_requests if pull_request.issue_id == issue_id]

    def get_ci_checks(self, pull_request_id: str | None = None) -> list[CiCheck]:
        if pull_request_id is None:
            return self.data.ci_checks
        return [check for check in self.data.ci_checks if check.pull_request_id == pull_request_id]
