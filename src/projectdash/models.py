from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
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
    description: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
