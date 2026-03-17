from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional
from datetime import datetime

@dataclass
class User:
    id: str
    name: str
    avatar_url: Optional[str] = None

@dataclass
class Project:
    id: str
    name: str
    status: str
    issues_count: int
    in_progress_count: int
    blocked_count: int
    due_date: str
    cycle: str
    start_date: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class LinearWorkflowState:
    id: str
    name: str
    type: str
    team_id: str
    team_key: str | None = None


@dataclass
class Issue:
    id: str
    title: str
    priority: str
    status: str
    assignee: Optional[User] = None
    points: int = 0
    project_id: Optional[str] = None
    due_date: Optional[str] = None
    linear_id: Optional[str] = None
    team_id: Optional[str] = None
    state_id: Optional[str] = None
    description: str | None = None
    labels: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def readiness_score(self) -> int:
        """Calculate a readiness score from 0 to 100."""
        score = 0
        if self.description and len(self.description) > 50:
            score += 40
        elif self.description:
            score += 20
        
        if self.assignee:
            score += 20
        
        if self.project_id:
            score += 20
        
        if self.points > 0:
            score += 20
            
        return score


@dataclass
class Repository:
    id: str
    provider: str
    name: str
    organization: str | None = None
    default_branch: str | None = None
    is_private: bool = False
    url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class PullRequest:
    id: str
    provider: str
    repository_id: str
    number: int
    title: str
    state: str
    author_id: str | None = None
    head_branch: str | None = None
    base_branch: str | None = None
    url: str | None = None
    issue_id: str | None = None
    opened_at: str | None = None
    merged_at: str | None = None
    closed_at: str | None = None
    updated_at: str | None = None


@dataclass
class CiCheck:
    id: str
    provider: str
    pull_request_id: str
    name: str
    status: str
    conclusion: str | None = None
    url: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str | None = None


@dataclass
class WorkEvent:
    id: int | None
    event_type: str
    source_provider: str
    source_id: str
    occurred_at: str
    payload: dict[str, Any] = field(default_factory=dict)
    issue_id: str | None = None
    project_id: str | None = None
    pull_request_id: str | None = None
    actor_id: str | None = None


@dataclass
class ActionRecord:
    id: str
    action_type: str
    target_id: str
    status: str
    message: str | None = None
    timestamp: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentRun:
    id: str
    runtime: str
    status: str
    started_at: str
    actor_id: str | None = None
    issue_id: str | None = None
    project_id: str | None = None
    session_ref: str | None = None
    finished_at: str | None = None
    branch_name: str | None = None
    pr_id: str | None = None
    prompt_text: str | None = None
    prompt_fingerprint: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    error_text: str | None = None
    trace_logs: str | None = None
    cost_usd: float | None = None
    token_input: int | None = None
    token_output: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
