from enum import StrEnum


class SyncResult(StrEnum):
    IDLE = "idle"
    SYNCING = "syncing"
    SUCCESS = "success"
    FAILED = "failed"


class ConnectorFreshness(StrEnum):
    IDLE = "idle"
    SYNCING = "syncing"
    FAILED = "failed"
    FRESH = "fresh"
    STALE = "stale"
    NEVER = "never"


class PullRequestState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class CiConclusion(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    NEUTRAL = "neutral"
    SKIPPED = "skipped"


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkloadStatus(StrEnum):
    OVERALLOCATED = "Overallocated"
    AT_CAPACITY = "At Capacity"
    AVAILABLE = "Available"
