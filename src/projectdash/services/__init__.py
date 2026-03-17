from __future__ import annotations

__all__ = ["GitHubQueryService", "IssueMutationService", "IssueService", "MetricsService", "SyncService"]


def __getattr__(name: str):
    if name == "GitHubQueryService":
        from projectdash.services.github_query_service import GitHubQueryService

        return GitHubQueryService
    if name == "IssueMutationService":
        from projectdash.services.issue_mutation_service import IssueMutationService

        return IssueMutationService
    if name == "IssueService":
        from projectdash.services.issue_service import IssueService

        return IssueService
    if name == "MetricsService":
        from projectdash.services.metrics import MetricsService

        return MetricsService
    if name == "SyncService":
        from projectdash.services.sync_service import SyncService

        return SyncService
    raise AttributeError(name)
